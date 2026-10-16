import Foundation
import XCTest
@testable import PanimAudio

/// Expected values come from `ffprobe -show_packets` on the same files (see each test).
final class OggOpusTests: XCTestCase {
    static func resource(_ name: String) throws -> [UInt8] {
        // Read beside this file rather than through Bundle.module, whose lookup is unreliable in Linux Foundation.
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Resources").appendingPathComponent(name)
        return [UInt8](try Data(contentsOf: url))
    }

    /// The streamed-lecture fixture in the repository (encoded at the old 46 kbit/s).
    static func fixture() throws -> [UInt8] {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("player/fixtures/streamed-lecture/audio/GeneratedScene.ogg")
        return [UInt8](try Data(contentsOf: url))
    }

    // ffmpeg -f lavfi -i sine=f=440:d=3 -ac 1 -c:a libopus -application voip -b:a 8k sine8k.ogg
    // ffprobe: 151 packets, 2422 bytes, all 960 samples; last pts 143688 + 312 => 144000 samples.
    func testEightKbitVoip() throws {
        let demuxer = try OggOpusDemuxer(bytes: try Self.resource("sine8k.ogg"))
        let head = try XCTUnwrap(demuxer.head)
        XCTAssertEqual(head.channels, 1)
        XCTAssertEqual(head.preSkip, 312)
        XCTAssertEqual(head.inputSampleRate, 48000)
        XCTAssertEqual(head.outputGain, 0)
        XCTAssertEqual(demuxer.packets.count, 151)
        XCTAssertEqual(demuxer.packets.reduce(0) { $0 + $1.data.count }, 2422)
        XCTAssertEqual(demuxer.packets.first?.data.count, 24)
        XCTAssertTrue(demuxer.packets.allSatisfy { $0.sampleCount == 960 })
        XCTAssertTrue(demuxer.endOfStream)
        XCTAssertEqual(demuxer.lastGranule, 144312)
        XCTAssertEqual(demuxer.durationSamples, 144000)
        XCTAssertEqual(demuxer.durationSeconds!, 3.0, accuracy: 1e-9)
        XCTAssertEqual(demuxer.packets.first?.startGranule, 0)
        for (i, p) in demuxer.packets.enumerated() { XCTAssertEqual(p.startGranule, Int64(i * 960)) }
    }

    // The same, from 24 kHz input (what the exporter's WAV often is): OpusHead keeps the input rate.
    func testTwentyFourKilohertzInput() throws {
        let demuxer = try OggOpusDemuxer(bytes: try Self.resource("sine24k.ogg"))
        XCTAssertEqual(demuxer.head?.inputSampleRate, 24000)
        XCTAssertEqual(demuxer.packets.count, 151)
        XCTAssertEqual(demuxer.packets.reduce(0) { $0 + $1.data.count }, 2394)
        XCTAssertEqual(demuxer.durationSamples, 144000)
    }

    // -ac 2 -frame_duration 40 -b:a 24k, 1 s: 26 packets of 1920, 4382 bytes, 48000 samples.
    func testStereoFortyMillisecondFrames() throws {
        let demuxer = try OggOpusDemuxer(bytes: try Self.resource("stereo40.ogg"))
        XCTAssertEqual(demuxer.head?.channels, 2)
        XCTAssertEqual(demuxer.packets.count, 26)
        XCTAssertTrue(demuxer.packets.allSatisfy { $0.sampleCount == 1920 })
        XCTAssertEqual(demuxer.packets.reduce(0) { $0 + $1.data.count }, 4382)
        XCTAssertEqual(demuxer.durationSamples, 48000)
    }

    // ffprobe: 2292 packets, 262262 bytes; last pts 2199048 + 952 => 2200000 samples (45.8333 s).
    func testRepositoryFixture() throws {
        let demuxer = try OggOpusDemuxer(bytes: try Self.fixture())
        XCTAssertEqual(demuxer.head?.channels, 1)
        XCTAssertEqual(demuxer.head?.preSkip, 312)
        XCTAssertEqual(demuxer.packets.count, 2292)
        XCTAssertEqual(demuxer.packets.reduce(0) { $0 + $1.data.count }, 262262)
        XCTAssertEqual(demuxer.packets.first?.data.count, 97)
        XCTAssertEqual(demuxer.durationSamples, 2_200_000)
        XCTAssertEqual(demuxer.packetIndex(containing: 312 + 48000), 50)
        XCTAssertEqual(demuxer.packetIndex(containing: 0), 0)
        XCTAssertEqual(demuxer.packetIndex(containing: 10_000_000), 2291)
    }

    func testIncrementalFeedMatchesWhole() throws {
        let bytes = try Self.fixture()
        let whole = try OggOpusDemuxer(bytes: bytes)
        let parts = OggOpusDemuxer()
        var rng = SystemRandomNumberGenerator()
        var at = 0
        var sawPartial = false
        while at < bytes.count {
            let n = min(bytes.count - at, Int.random(in: 1...3000, using: &rng))
            try parts.append(Array(bytes[at..<(at + n)]))
            at += n
            if !parts.endOfStream && parts.packets.count > 0 { sawPartial = true }
            XCTAssertEqual(parts.durationSamples == nil, !parts.endOfStream)
        }
        XCTAssertTrue(sawPartial)
        XCTAssertEqual(parts.packets, whole.packets)
        XCTAssertEqual(parts.durationSamples, whole.durationSamples)
        XCTAssertEqual(parts.bytesParsed, bytes.count)
    }

    func testRejectsBrokenInput() throws {
        var bytes = try Self.resource("sine8k.ogg")
        XCTAssertThrowsError(try OggOpusDemuxer(bytes: Array("RIFF....WAVE".utf8))) {
            XCTAssertEqual($0 as? NarrationFormatError, .notOgg)
        }
        bytes[200] ^= 0xFF
        XCTAssertThrowsError(try OggOpusDemuxer(bytes: bytes)) {
            guard case .badPage = $0 as? NarrationFormatError else { return XCTFail("\($0)") }
        }
    }

    func testTocArithmetic() {
        XCTAssertEqual(Opus.frameSize(toc: 0 << 3), 480)      // SILK NB 10 ms
        XCTAssertEqual(Opus.frameSize(toc: 1 << 3), 960)      // SILK NB 20 ms
        XCTAssertEqual(Opus.frameSize(toc: 3 << 3), 2880)     // SILK NB 60 ms
        XCTAssertEqual(Opus.frameSize(toc: 13 << 3), 960)     // hybrid 20 ms
        XCTAssertEqual(Opus.frameSize(toc: 16 << 3), 120)     // CELT 2.5 ms
        XCTAssertEqual(Opus.frameSize(toc: 31 << 3), 960)     // CELT 20 ms
        XCTAssertEqual(Opus.sampleCount([1 << 3 | 0]), 960)
        XCTAssertEqual(Opus.sampleCount([1 << 3 | 1, 0]), 1920)
        XCTAssertEqual(Opus.sampleCount([1 << 3 | 2, 0]), 1920)
        XCTAssertEqual(Opus.sampleCount([1 << 3 | 3, 3]), 2880)
        XCTAssertEqual(Opus.sampleCount([3 << 3 | 3, 3]), nil)   // 180 ms: over the limit
        XCTAssertEqual(Opus.sampleCount([1 << 3 | 3]), nil)
        XCTAssertEqual(Opus.sampleCount([]), nil)
    }
}

/// A decoder whose every sample is its own granule position, so seeking and trimming can be read off the output.
final class GranuleDecoder: OpusPacketDecoder {
    let channels: Int
    var resets = 0
    init(channels: Int) { self.channels = channels }
    func decode(_ packet: OpusPacket) throws -> [Float] {
        var out: [Float] = []
        for i in 0..<packet.sampleCount {
            for _ in 0..<channels { out.append(Float(packet.startGranule + Int64(i))) }
        }
        return out
    }
    func reset() { resets += 1 }
}

final class NarrationReaderTests: XCTestCase {
    private func drain(_ reader: NarrationReader) throws -> [Float] {
        var all: [Float] = []
        loop: while true {
            switch try reader.next() {
            case .pcm(let s): all += s
            case .ended: break loop
            case .waiting: XCTFail("waiting on a complete source"); break loop
            }
        }
        return all
    }

    private func reader(_ bytes: [UInt8]) throws -> NarrationReader {
        let source = NarrationSource(data: Data(bytes))
        return NarrationReader(source: source, format: try source.format()) { GranuleDecoder(channels: $0.channels) }
    }

    func testPreSkipAndEndTrim() throws {
        let all = try drain(try reader(try OggOpusTests.fixture()))
        XCTAssertEqual(all.count, 2_200_000)
        XCTAssertEqual(all.first, 312)
        XCTAssertEqual(all.last, Float(312 + 2_200_000 - 1))
    }

    func testStereoMixesDown() throws {
        let all = try drain(try reader(try OggOpusTests.resource("stereo40.ogg")))
        XCTAssertEqual(all.count, 48000)
        XCTAssertEqual(all[100], 412)
    }

    func testSeekLandsOnTheSample() throws {
        let r = try reader(try OggOpusTests.fixture())
        r.seek(to: 12.345)
        let rest = try drain(r)
        let target = Int((12.345 * 48000).rounded())
        XCTAssertEqual(rest.first, Float(312 + target))
        XCTAssertEqual(rest.count, 2_200_000 - target)
        r.seek(to: 50)
        XCTAssertEqual(try r.next(), .ended)
        r.seek(to: 0)
        XCTAssertEqual(try r.next(), .pcm((312..<960).map { Float($0) }))
    }

    func testStreamWaitsAndResumes() throws {
        let bytes = try OggOpusTests.fixture()
        let source = NarrationSource()
        source.append(Data(bytes[0..<20000]))
        let r = NarrationReader(source: source, format: try source.format()) { GranuleDecoder(channels: $0.channels) }
        var got: [Float] = []
        var waits = 0
        var at = 20000
        loop: while true {
            switch try r.next() {
            case .pcm(let s): got += s
            case .ended: break loop
            case .waiting:
                waits += 1
                if waits == 3 { r.seek(to: 30) }        // a seek ahead of what has arrived waits for it
                let n = min(bytes.count - at, 7000)
                source.append(Data(bytes[at..<(at + n)]))
                at += n
                if at == bytes.count { source.finish() }
            }
        }
        XCTAssertGreaterThan(waits, 10)
        let before = got.firstIndex(of: Float(312 + 30 * 48000))
        XCTAssertNotNil(before)
        XCTAssertEqual(got.last, Float(312 + 2_200_000 - 1))
        XCTAssertNil(r.source.failure)
    }

    func testFailedStreamThrows() throws {
        let bytes = try OggOpusTests.fixture()
        let source = NarrationSource()
        source.append(Data(bytes[0..<5000]))
        let r = NarrationReader(source: source, format: try source.format()) { GranuleDecoder(channels: $0.channels) }
        source.fail("offline")
        XCTAssertThrowsError(try drain(r))
    }

    func testWav() throws {
        let bytes = try OggOpusTests.resource("tone.wav")
        let header = try XCTUnwrap(try WavHeader.parse(bytes))
        XCTAssertEqual(header.channels, 2)
        XCTAssertEqual(header.sampleRate, 22050)
        XCTAssertEqual(header.totalFrames, 5513)          // ffprobe duration_ts
        XCTAssertEqual(header.monoSamples(bytes, frames: 0..<3), [0, Float(361) / 32768, Float(718) / 32768])
        XCTAssertNil(try WavHeader.parse(Array(bytes[0..<30])))   // not yet at the data chunk
        let all = try drain(try reader(bytes))
        XCTAssertEqual(all.count, 5513)
        let r = try reader(bytes)
        r.seek(to: 0.1)
        XCTAssertEqual(try drain(r).count, 5513 - 2205)
    }
}

final class PCMRingTests: XCTestCase {
    func testWrapsAndReportsSpace() {
        var ring = PCMRing(capacity: 5)
        XCTAssertEqual(ring.write([1, 2, 3, 4]), 4)
        XCTAssertEqual(ring.write([5, 6, 7], from: 0), 1)
        var out = [Float](repeating: 0, count: 5)
        XCTAssertEqual(out.withUnsafeMutableBufferPointer { ring.read(into: $0.baseAddress!, frames: 3) }, 3)
        XCTAssertEqual(Array(out[0..<3]), [1, 2, 3])
        XCTAssertEqual(ring.write([6, 7, 8, 9], from: 1), 3)
        XCTAssertEqual(ring.count, 5)
        XCTAssertEqual(out.withUnsafeMutableBufferPointer { ring.read(into: $0.baseAddress!, frames: 9) }, 5)
        XCTAssertEqual(out, [4, 5, 7, 8, 9])
        ring.clear()
        XCTAssertEqual(ring.space, 5)
    }

    func testClockMath() {
        // 960 frames handed over at t=10 ending at frame 48000; heard 0.05 s later, at 1x.
        func at(_ now: Double, speed: Double = 1) -> Double {
            NarrationClockMath.position(now: now, pulledAt: 10, pulledEnd: 48000, pulled: 960, latency: 0.05,
                                        speed: speed, sampleRate: 48000, startOffset: 2)
        }
        XCTAssertEqual(at(10.05), 2 + 47040.0 / 48000, accuracy: 1e-9)
        XCTAssertEqual(at(10.06), 2 + 47520.0 / 48000, accuracy: 1e-9)
        XCTAssertEqual(at(10.06, speed: 2), 2 + 48000.0 / 48000, accuracy: 1e-9)
        XCTAssertEqual(at(11), 3, accuracy: 1e-9)     // the queue ran dry: held at what was handed over
    }
}

final class NarrationSourceTests: XCTestCase {
    func testFormatWaitsForTheHeader() throws {
        let bytes = try OggOpusTests.resource("sine8k.ogg")
        let source = NarrationSource()
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.05) {
            source.append(Data(bytes[0..<10]))
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.05) { source.append(Data(bytes[10...])) }
        }
        guard case .oggOpus(let head) = try source.format(timeout: 5) else { return XCTFail() }
        XCTAssertEqual(head.preSkip, 312)
        XCTAssertEqual(try NarrationSource(data: Data(try OggOpusTests.resource("tone.wav"))).format().sampleRate,
                       22050)
        XCTAssertThrowsError(try NarrationSource(data: Data("hello".utf8)).format())
    }
}
