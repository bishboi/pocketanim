// The narration as mono PCM from any place in it: the platform-neutral half of NarrationPlayer.
//
// AudioPlayer.kt leaves this to MediaExtractor and MediaCodec: read a sample, decode it, and after a seek start
// from the sync point before the target. Here the Ogg is split by OggOpusDemuxer, each packet decoded by an
// OpusPacketDecoder (AudioToolbox on Apple; a stand-in in the tests), and a seek lands on the exact sample: decoding
// starts 80 ms before the target, so the decoder has settled, and what comes before the target is dropped -- the
// same mechanism that drops the stream's pre-skip at its start. The last page's granule trims the final packet.
// Pure Swift, so the seeking and trimming arithmetic is tested on Linux.

import Foundation

/// Decodes one Opus packet at a time.
public protocol OpusPacketDecoder: AnyObject {
    /// The packet's samples, 48 kHz, interleaved when there are two channels.
    func decode(_ packet: OpusPacket) throws -> [Float]
    /// Forget the decoder's state: the next packet does not follow the last one (a seek).
    func reset()
}

public final class NarrationReader {
    /// What [next] produced.
    public enum Step: Equatable {
        /// Mono samples at [sampleRate], following the last ones (or starting at the place sought).
        case pcm([Float])
        /// The next samples have not arrived yet: a stream that has fallen behind.
        case waiting
        /// Past the end.
        case ended
    }

    public let source: NarrationSource
    public let format: NarrationFormat
    public var sampleRate: Int { format.sampleRate }

    private let makeDecoder: (OpusHead) throws -> OpusPacketDecoder
    private var decoder: OpusPacketDecoder?
    private let demuxer = OggOpusDemuxer()
    private var fed = 0                     // bytes of the source given to the demuxer
    private var nextPacket = 0
    private var discard: Int64 = 0          // samples still to drop: pre-skip, or the way to a seek target
    private var nextFrame = 0               // WAV: the next frame to read
    private var seekTarget: Double? = 0     // starts as a seek to 0, which is what drops the pre-skip

    /// Frames read from WAV per step; packets are one step each (20 ms for the narration).
    private static let wavChunk = 4096

    public init(source: NarrationSource, format: NarrationFormat,
                decoder makeDecoder: @escaping (OpusHead) throws -> OpusPacketDecoder) {
        self.source = source
        self.format = format
        self.makeDecoder = makeDecoder
    }

    /// The narration's length, once known (a stream's when its last page is in).
    public var durationSeconds: Double? {
        switch format {
        case .oggOpus: return demuxer.durationSeconds
        case .wav(let header): return header.durationSeconds
        }
    }

    /// Continue from [seconds] of narration (clamped at 0); takes effect on the next [next].
    public func seek(to seconds: Double) {
        seekTarget = max(0, seconds)
    }

    /// The next piece of the narration. Throws when the bytes are not a readable narration, or stopped coming.
    public func next() throws -> Step {
        switch format {
        case .oggOpus(let head): return try nextOpus(head)
        case .wav(let header): return try nextWav(header)
        }
    }

    // MARK: Ogg Opus

    private func nextOpus(_ head: OpusHead) throws -> Step {
        while true {
            try feed()
            if let target = seekTarget {
                let granule = Int64(head.preSkip) + Int64((target * Double(Opus.sampleRate)).rounded())
                guard demuxer.endOfStream || demuxer.availableEndGranule > granule else { return try notHere() }
                seekTarget = nil
                decoder?.reset()
                if demuxer.endOfStream && granule >= demuxer.lastGranule {
                    nextPacket = demuxer.packets.count
                    return .ended
                }
                let from = demuxer.packetIndex(containing: granule - Int64(Opus.seekPreRoll)) ?? 0
                nextPacket = from
                discard = demuxer.packets.isEmpty ? 0 : max(0, granule - demuxer.packets[from].startGranule)
            }
            guard nextPacket < demuxer.packets.count else {
                return demuxer.endOfStream ? .ended : try notHere()
            }
            let packet = demuxer.packets[nextPacket]
            nextPacket += 1
            if decoder == nil { decoder = try makeDecoder(head) }
            var pcm = mono(try decoder!.decode(packet), channels: head.channels)
            if demuxer.endOfStream {
                let keep = max(0, Int(demuxer.lastGranule - packet.startGranule))
                if pcm.count > keep { pcm.removeLast(pcm.count - keep) }
            }
            if discard > 0 {
                let drop = Int(min(discard, Int64(pcm.count)))
                pcm.removeFirst(drop)
                discard -= Int64(drop)
            }
            if pcm.isEmpty { continue }
            let gain = head.outputGainLinear
            if head.outputGain != 0 { for i in pcm.indices { pcm[i] *= gain } }
            return .pcm(pcm)
        }
    }

    /// Give the demuxer what has arrived since last time.
    private func feed() throws {
        let have = source.count
        while fed < have {
            let chunk = source.bytes(fed..<min(have, fed + 256 * 1024))
            if chunk.isEmpty { break }
            try demuxer.append(chunk)
            fed += chunk.count
        }
    }

    /// Nothing more here: waiting for it, or -- when no more is coming -- the end, or why it stopped.
    private func notHere() throws -> Step {
        guard source.isComplete else { return .waiting }
        if let failure = source.failure { throw NarrationFormatError.badPage(failure) }
        // Every byte has come; anything left in the demuxer is a truncated last page.
        if fed < source.count { return .waiting }
        return .ended
    }

    private func mono(_ samples: [Float], channels: Int) -> [Float] {
        guard channels > 1 else { return samples }
        let frames = samples.count / channels
        var out = [Float](repeating: 0, count: frames)
        let scale = 1 / Float(channels)
        for f in 0..<frames {
            var sum: Float = 0
            for c in 0..<channels { sum += samples[f * channels + c] }
            out[f] = sum * scale
        }
        return out
    }

    // MARK: WAV

    private func nextWav(_ header: WavHeader) throws -> Step {
        if let target = seekTarget {
            seekTarget = nil
            nextFrame = Int((target * Double(header.sampleRate)).rounded())
        }
        if let total = header.totalFrames, nextFrame >= total { return .ended }
        let have = header.frameCount(available: source.count)
        guard nextFrame < have else {
            if source.isComplete {
                if let failure = source.failure { throw NarrationFormatError.badPage(failure) }
                return .ended
            }
            return .waiting
        }
        let frames = nextFrame..<min(have, nextFrame + Self.wavChunk)
        let start = header.dataOffset + frames.lowerBound * header.blockAlign
        let bytes = source.bytes(start..<(start + frames.count * header.blockAlign))
        nextFrame = frames.upperBound
        // monoSamples reads from the file's start: hand it a header whose data begins at this slice.
        let slice = WavHeader(channels: header.channels, sampleRate: header.sampleRate,
                              bitsPerSample: header.bitsPerSample, isFloat: header.isFloat,
                              blockAlign: header.blockAlign, dataOffset: 0, dataLength: nil)
        return .pcm(slice.monoSamples(bytes, frames: 0..<frames.count))
    }
}
