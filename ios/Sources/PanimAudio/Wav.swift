// The narration's fallback container: a RIFF WAV, as tools/build_library.py ships it when its ffmpeg has no Opus
// encoder. Android's MediaExtractor reads it; here it is parsed in Swift so a streamed WAV plays as it arrives,
// the same as the Ogg (AVAudioFile wants the whole file). Pure Swift, built and tested on Linux.

import Foundation

/// A WAV file's format and where its samples are.
public struct WavHeader: Equatable {
    public let channels: Int
    public let sampleRate: Int
    /// 16 (integer) or 32 (float).
    public let bitsPerSample: Int
    public let isFloat: Bool
    /// Bytes per frame (all channels).
    public let blockAlign: Int
    /// Byte offset of the first sample in the file.
    public let dataOffset: Int
    /// Bytes of samples the data chunk says it holds; nil when the size is unset (a WAV written as it streamed).
    public let dataLength: Int?

    /// Whole frames present when [available] bytes of the file are.
    public func frameCount(available: Int) -> Int {
        var bytes = max(0, available - dataOffset)
        if let dataLength { bytes = min(bytes, dataLength) }
        return bytes / blockAlign
    }

    /// Frames in the file, when the header says.
    public var totalFrames: Int? { dataLength.map { $0 / blockAlign } }

    public var durationSeconds: Double? { totalFrames.map { Double($0) / Double(sampleRate) } }

    /// The header of a WAV starting [bytes]; nil while too few bytes have arrived to reach its data chunk.
    public static func parse(_ bytes: [UInt8]) throws -> WavHeader? {
        guard bytes.count >= 12 else { return nil }
        guard Array(bytes[0..<4]) == Array("RIFF".utf8), Array(bytes[8..<12]) == Array("WAVE".utf8) else {
            throw NarrationFormatError.notWav("no RIFF/WAVE header")
        }
        var at = 12
        var format: (channels: Int, rate: Int, bits: Int, float: Bool, align: Int)?
        while true {
            guard bytes.count >= at + 8 else { return nil }
            let id = String(decoding: bytes[at..<(at + 4)], as: UTF8.self)
            let size = Int(le32(bytes, at + 4))
            let body = at + 8
            if id == "fmt " {
                guard size >= 16 else { throw NarrationFormatError.notWav("short fmt chunk") }
                guard bytes.count >= body + size else { return nil }
                var tag = Int(le16(bytes, body))
                if tag == 0xFFFE && size >= 26 { tag = Int(le16(bytes, body + 24)) }   // WAVE_FORMAT_EXTENSIBLE
                let channels = Int(le16(bytes, body + 2))
                let rate = Int(le32(bytes, body + 4))
                let align = Int(le16(bytes, body + 12))
                let bits = Int(le16(bytes, body + 14))
                let ok = (tag == 1 && bits == 16) || (tag == 3 && bits == 32)
                guard ok, channels > 0, rate > 0, align == channels * bits / 8 else {
                    throw NarrationFormatError.notWav("format \(tag), \(bits) bits, \(channels) channels")
                }
                format = (channels, rate, bits, tag == 3, align)
            } else if id == "data" {
                guard let f = format else { throw NarrationFormatError.notWav("data before fmt") }
                let length: Int? = (size == 0 || size == 0xFFFF_FFFF) ? nil : size
                return WavHeader(channels: f.channels, sampleRate: f.rate, bitsPerSample: f.bits, isFloat: f.float,
                                 blockAlign: f.align, dataOffset: body, dataLength: length)
            }
            at = body + size + (size & 1)    // chunks are padded to even sizes
        }
    }

    /// Frames [frames] of [bytes] (the file from its start), mixed down to mono floats in -1...1.
    public func monoSamples(_ bytes: [UInt8], frames: Range<Int>) -> [Float] {
        var out = [Float](repeating: 0, count: frames.count)
        let scale = 1 / Float(channels)
        for (n, frame) in frames.enumerated() {
            var sum: Float = 0
            let base = dataOffset + frame * blockAlign
            for c in 0..<channels {
                if isFloat {
                    sum += Float(bitPattern: le32(bytes, base + c * 4))
                } else {
                    sum += Float(Int16(bitPattern: le16(bytes, base + c * 2))) / 32768
                }
            }
            out[n] = sum * scale
        }
        return out
    }
}
