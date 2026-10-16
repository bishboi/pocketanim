// The narration's container, read in Swift.
//
// No Kotlin counterpart: on Android MediaExtractor opens the Ogg Opus narration that tools/build_library.py
// (compress_narration) makes, and on iOS nothing does -- AVFoundation and AudioToolbox decode Opus packets
// (kAudioFormatOpus) but cannot open an Ogg file. So this splits the file into its Opus packets, each with the
// place (granule, 48 kHz samples) its first sample has, for NarrationPlayer to hand to the decoder one at a time.
//
// It is incremental, because a saved lecture's narration is streamed: bytes are appended as they arrive and every
// page complete so far yields its packets; a packet split across pages waits for the page that finishes it.
// Pure Swift (Foundation only), so it builds and is tested on Linux.

import Foundation

/// Why a narration file could not be read.
public enum NarrationFormatError: Error, Equatable, CustomStringConvertible {
    case notOgg
    case badPage(String)
    case notOpus(String)
    case notWav(String)

    public var description: String {
        switch self {
        case .notOgg: return "not an Ogg stream"
        case .badPage(let why): return "broken Ogg page: \(why)"
        case .notOpus(let why): return "not Ogg Opus: \(why)"
        case .notWav(let why): return "not a PCM WAV file: \(why)"
        }
    }
}

/// Little-endian reads from a byte array, bounds already checked by the caller.
@inline(__always) func le16(_ b: [UInt8], _ i: Int) -> UInt16 { UInt16(b[i]) | UInt16(b[i + 1]) << 8 }
@inline(__always) func le32(_ b: [UInt8], _ i: Int) -> UInt32 {
    UInt32(b[i]) | UInt32(b[i + 1]) << 8 | UInt32(b[i + 2]) << 16 | UInt32(b[i + 3]) << 24
}
@inline(__always) func le64(_ b: [UInt8], _ i: Int) -> UInt64 { UInt64(le32(b, i)) | UInt64(le32(b, i + 4)) << 32 }

/// The identification header (RFC 7845 §5.1).
public struct OpusHead: Equatable {
    public let version: UInt8
    public let channels: Int
    /// Samples (at 48 kHz) the decoder makes before the first one that belongs to the narration: dropped.
    public let preSkip: Int
    /// What the encoder was given (24000 for the narration, typically); informational, Opus always decodes at 48 kHz.
    public let inputSampleRate: Int
    /// Gain to apply on output, Q7.8 dB.
    public let outputGain: Int16
    public let mappingFamily: Int

    /// The output gain as a factor.
    public var outputGainLinear: Float { Float(pow(10.0, Double(outputGain) / (20.0 * 256.0))) }

    public static func parse(_ packet: [UInt8]) throws -> OpusHead {
        guard packet.count >= 19, Array(packet[0..<8]) == Array("OpusHead".utf8) else {
            throw NarrationFormatError.notOpus("the first packet is not an OpusHead")
        }
        let version = packet[8]
        guard version & 0xF0 == 0 else { throw NarrationFormatError.notOpus("OpusHead version \(version)") }
        let channels = Int(packet[9])
        guard channels > 0 else { throw NarrationFormatError.notOpus("no channels") }
        let family = Int(packet[18])
        if family == 0 && channels > 2 { throw NarrationFormatError.notOpus("\(channels) channels in mapping family 0") }
        return OpusHead(
            version: version, channels: channels, preSkip: Int(le16(packet, 10)),
            inputSampleRate: Int(le32(packet, 12)), outputGain: Int16(bitPattern: le16(packet, 16)),
            mappingFamily: family)
    }
}

/// One Opus packet of the narration.
public struct OpusPacket: Equatable {
    public let data: [UInt8]
    /// Granule position (48 kHz samples, pre-skip included) of the packet's first sample.
    public let startGranule: Int64
    /// Samples (48 kHz) it decodes to, from its TOC byte.
    public let sampleCount: Int
    public var endGranule: Int64 { startGranule + Int64(sampleCount) }
}

/// Opus packet arithmetic (RFC 6716 §3.1).
public enum Opus {
    /// Opus always decodes at 48 kHz; granules count in it.
    public static let sampleRate = 48000
    /// How far before a seek target decoding starts, so the decoder has converged by the target (RFC 7845 §4.6).
    public static let seekPreRoll = 3840

    /// Samples per frame, from the TOC byte's configuration (top five bits).
    public static func frameSize(toc: UInt8) -> Int {
        let config = Int(toc >> 3)
        switch config {
        case 0...11: return [480, 960, 1920, 2880][config & 3]      // SILK: 10, 20, 40, 60 ms
        case 12...15: return [480, 960][config & 1]                 // hybrid: 10, 20 ms
        default: return [120, 240, 480, 960][config & 3]            // CELT: 2.5, 5, 10, 20 ms
        }
    }

    /// Frames in the packet: code 0 one, codes 1 and 2 two, code 3 the count in the second byte. Nil when malformed.
    public static func frameCount(_ packet: [UInt8]) -> Int? {
        guard let toc = packet.first else { return nil }
        switch toc & 3 {
        case 0: return 1
        case 1, 2: return 2
        default:
            guard packet.count >= 2 else { return nil }
            let n = Int(packet[1] & 0x3F)
            return n == 0 ? nil : n
        }
    }

    /// Samples (48 kHz) the packet decodes to; nil when malformed or over 120 ms.
    public static func sampleCount(_ packet: [UInt8]) -> Int? {
        guard let toc = packet.first, let frames = frameCount(packet) else { return nil }
        let n = frames * frameSize(toc: toc)
        return n > 5760 ? nil : n
    }
}

/// An Ogg Opus stream split into packets, fed as its bytes arrive.
public final class OggOpusDemuxer {
    public private(set) var head: OpusHead?
    /// The audio packets complete so far, in order.
    public private(set) var packets: [OpusPacket] = []
    /// The last page (end of stream) has been read: [durationSamples] is known.
    public private(set) var endOfStream = false
    /// Granule of the last page read that had one.
    public private(set) var lastGranule: Int64 = -1
    /// Bytes of the stream taken so far (pages fully parsed).
    public private(set) var bytesParsed = 0

    private var buffer: [UInt8] = []        // bytes after the last whole page
    private var serial: UInt32?
    private var pending: [UInt8] = []       // a packet continued onto the next page
    private var headerPackets = 0           // OpusHead and OpusTags seen
    private var unplaced: [[UInt8]] = []    // audio packets read before any page gave a granule
    private var nextGranule: Int64?         // where the next audio packet starts, once known

    public init() {}

    /// Parse a whole file at once.
    public convenience init(bytes: [UInt8]) throws {
        self.init()
        try append(bytes)
    }

    /// Samples of narration (48 kHz, pre-skip removed), known once the last page is in.
    public var durationSamples: Int64? {
        guard endOfStream, let head else { return nil }
        return max(0, lastGranule - Int64(head.preSkip))
    }

    public var durationSeconds: Double? { durationSamples.map { Double($0) / Double(Opus.sampleRate) } }

    /// Granule where decodable audio ends so far: the end of the last whole packet, or the final granule.
    public var availableEndGranule: Int64 {
        if endOfStream { return lastGranule }
        return packets.last?.endGranule ?? 0
    }

    /// The packet holding [granule]: the last one starting at or before it. Nil when none is in yet.
    public func packetIndex(containing granule: Int64) -> Int? {
        guard let first = packets.first else { return nil }
        if granule <= first.startGranule { return 0 }
        var lo = 0, hi = packets.count - 1
        while lo < hi {
            let mid = (lo + hi + 1) / 2
            if packets[mid].startGranule <= granule { lo = mid } else { hi = mid - 1 }
        }
        return lo
    }

    /// The next bytes of the stream, in order. Every page they complete is parsed now.
    public func append(_ bytes: [UInt8]) throws {
        buffer.append(contentsOf: bytes)
        var at = 0
        while let size = try pageSize(at: at) {
            try parsePage(at: at, size: size)
            at += size
        }
        if at > 0 {
            buffer.removeFirst(at)
            bytesParsed += at
        }
    }

    /// Size of the whole page at [at], or nil when it has not all arrived.
    private func pageSize(at: Int) throws -> Int? {
        let b = buffer
        guard b.count - at >= 27 else {
            if b.count - at >= 4 && !(b[at] == 0x4F && b[at + 1] == 0x67 && b[at + 2] == 0x67 && b[at + 3] == 0x53) {
                throw bytesParsed + at == 0 ? NarrationFormatError.notOgg : NarrationFormatError.badPage("no capture pattern")
            }
            return nil
        }
        guard b[at] == 0x4F, b[at + 1] == 0x67, b[at + 2] == 0x67, b[at + 3] == 0x53 else {
            throw bytesParsed + at == 0 ? NarrationFormatError.notOgg : NarrationFormatError.badPage("no capture pattern")
        }
        guard b[at + 4] == 0 else { throw NarrationFormatError.badPage("version \(b[at + 4])") }
        let segments = Int(b[at + 26])
        guard b.count - at >= 27 + segments else { return nil }
        var body = 0
        for i in 0..<segments { body += Int(b[at + 27 + i]) }
        let size = 27 + segments + body
        return b.count - at >= size ? size : nil
    }

    private func parsePage(at: Int, size: Int) throws {
        let b = buffer
        let flags = b[at + 5]
        let granule = Int64(bitPattern: le64(b, at + 6))
        let pageSerial = le32(b, at + 14)
        let expected = le32(b, at + 22)
        var crc: UInt32 = 0
        for i in at..<(at + size) {
            let byte = (i >= at + 22 && i < at + 26) ? 0 : b[i]
            crc = (crc << 8) ^ OggCRC.table[Int((crc >> 24) ^ UInt32(byte))]
        }
        guard crc == expected else { throw NarrationFormatError.badPage("checksum at byte \(bytesParsed + at)") }

        if serial == nil {
            guard flags & 0x02 != 0 else { throw NarrationFormatError.notOpus("the stream does not begin a page") }
            serial = pageSerial
        }
        guard pageSerial == serial, !endOfStream else { return }   // another logical stream, or past the end

        let segments = Int(b[at + 26])
        var offset = at + 27 + segments
        var finished: [[UInt8]] = []
        if flags & 0x01 == 0 { pending.removeAll() }               // not a continuation: nothing carried over
        for i in 0..<segments {
            let lace = Int(b[at + 27 + i])
            pending.append(contentsOf: b[offset..<(offset + lace)])
            offset += lace
            if lace < 255 {
                finished.append(pending)
                pending.removeAll(keepingCapacity: true)
            }
        }
        let last = flags & 0x04 != 0

        var audio: [[UInt8]] = []
        for packet in finished {
            if headerPackets == 0 {
                head = try OpusHead.parse(packet)
                headerPackets = 1
            } else if headerPackets == 1 {
                guard packet.count >= 8, Array(packet[0..<8]) == Array("OpusTags".utf8) else {
                    throw NarrationFormatError.notOpus("the second packet is not OpusTags")
                }
                headerPackets = 2
            } else if !packet.isEmpty {
                audio.append(packet)
            }
        }
        try place(audio, pageGranule: finished.isEmpty ? -1 : granule, last: last)
        if granule != -1 && !finished.isEmpty { lastGranule = granule }
        if last { endOfStream = true }
    }

    /// Give each audio packet its start granule. The first page with a granule fixes where the stream starts (its
    /// granule less the samples of every packet finished so far); after that each packet starts where the previous
    /// one ended. The last page's granule may cut the final packet short -- that is [durationSamples], not here.
    private func place(_ audio: [[UInt8]], pageGranule: Int64, last: Bool) throws {
        if nextGranule == nil {
            unplaced.append(contentsOf: audio)
            guard pageGranule != -1, headerPackets == 2 else { return }
            var total: Int64 = 0
            for packet in unplaced {
                guard let n = Opus.sampleCount(packet) else { throw NarrationFormatError.notOpus("malformed packet") }
                total += Int64(n)
            }
            // A start before zero is only allowed on a stream that ends on its first page (end trimming).
            nextGranule = max(0, pageGranule - total)
            let early = unplaced
            unplaced.removeAll()
            try add(early)
        } else {
            try add(audio)
        }
    }

    private func add(_ audio: [[UInt8]]) throws {
        guard var at = nextGranule else { return }
        for packet in audio {
            guard let n = Opus.sampleCount(packet) else { throw NarrationFormatError.notOpus("malformed packet") }
            packets.append(OpusPacket(data: packet, startGranule: at, sampleCount: n))
            at += Int64(n)
        }
        nextGranule = at
    }
}

/// Ogg's CRC-32: polynomial 0x04C11DB7, not reflected, zero start, no final xor.
enum OggCRC {
    static let table: [UInt32] = (0..<256).map { i -> UInt32 in
        var r = UInt32(i) << 24
        for _ in 0..<8 { r = r & 0x8000_0000 != 0 ? (r << 1) ^ 0x04C1_1DB7 : r << 1 }
        return r
    }
}
