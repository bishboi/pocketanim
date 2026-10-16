import Foundation
import XCTest
@testable import PanimCore

/** The container decoder, both versions: varints, zigzag deltas, elided points, the rounding shift, delta instances. */
final class PanmTests: XCTestCase {
    private func fixture(_ name: String) throws -> [UInt8] {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Fixtures/\(name)")
        return [UInt8](try Data(contentsOf: url))
    }

    /** A little-endian byte builder for hand-made containers. */
    private struct Bytes {
        var out: [UInt8] = []
        mutating func u8(_ v: Int) { out.append(UInt8(v)) }
        mutating func u16(_ v: Int) { out += [UInt8(v & 0xFF), UInt8((v >> 8) & 0xFF)] }
        mutating func u32(_ v: UInt32) { for i in 0..<4 { out.append(UInt8((v >> (8 * UInt32(i))) & 0xFF)) } }
        mutating func f32(_ v: Float) { u32(v.bitPattern) }
        mutating func varint(_ v: Int) {
            var value = v
            while true {
                let byte = value & 0x7F
                value >>= 7
                if value != 0 { u8(byte | 0x80) } else { u8(byte); return }
            }
        }
        mutating func zigzag(_ v: Int) { varint(v >= 0 ? v << 1 : ((-v) << 1) - 1) }
    }

    func testHandMadeVersion2() throws {
        var b = Bytes()
        b.u32(0x4D4E4150)
        b.u16(2)                  // version
        b.u16(2 | 8 | (1 << 4))   // flat, elided, one low bit rounded away
        b.u16(30)                 // fps
        b.u32(2)                  // records
        b.u32(1)                  // atlas shapes
        for v: Float in [0, 0, 5] { b.f32(v) }               // lo
        for v: Float in [65535, 65535, 5] { b.f32(v) }       // hi: with one bit rounded away, a unit is 2
        // One shape, two cubics (8 points). Cubic 0: straight (code 2), so only its ends are written; cubic 1:
        // starts where cubic 0 ended and is straight (code 3), so only its end is written.
        b.varint(8)
        b.u8(2 | (3 << 2))
        b.zigzag(10); b.zigzag(20)        // p0 = (10, 20) quantised
        b.zigzag(300); b.zigzag(-5)       // p3 = (310, 15): a two-byte varint and a negative delta
        b.zigzag(-310); b.zigzag(0)       // p7 = (0, 15)
        // Record 0, a snapshot: slot 3, every field but the normal.
        b.u8(0)
        b.varint(1)
        b.varint(3)
        b.u8(0x7F)
        b.varint(0)                         // atlas id
        b.u8(0)                             // flags
        for k in 0..<9 { b.u16(k % 4 == 0 ? 0x3C00 : 0) } // identity, as float16
        for v: Float in [1.5, -2, 0] { b.f32(v) }
        b.u8(0x11); b.u8(0x22); b.u8(0x33); b.u8(0xFF)     // fill rgba
        b.u8(0xAA); b.u8(0xBB); b.u8(0xCC); b.u8(0x80)     // stroke rgba
        b.u16(128)                                          // width 2.0
        // Record 1, a keyframe: slot 3 moves, nothing else is written.
        b.u8(1)
        b.varint(1)
        b.varint(3)
        b.u8(8)
        for v: Float in [4, 5, 6] { b.f32(v) }

        let scene = try Scene.parse(b.out)
        XCTAssertEqual(scene.fps, 30)
        XCTAssertEqual(scene.frameCount, 2)
        let pts = scene.atlas[0]
        XCTAssertEqual(pts.count, 24)
        // Quantised q dequantises to (q << 1) / 65535 * 65535 = 2q, z to lo (flat).
        let expected: [[Float]] = [
            [20, 40], [20 + 600.0 / 3, 40 - 10.0 / 3], [20 + 1200.0 / 3, 40 - 20.0 / 3], [620, 30],
            [620, 30], [620 - 620.0 / 3, 30], [620 - 1240.0 / 3, 30], [0, 30],
        ]
        for (p, xy) in expected.enumerated() {
            XCTAssertEqual(pts[p * 3], xy[0], accuracy: 1e-2, "x of point \(p)")
            XCTAssertEqual(pts[p * 3 + 1], xy[1], accuracy: 1e-2, "y of point \(p)")
            XCTAssertEqual(pts[p * 3 + 2], 5, "z of point \(p)")
        }

        let first = try scene.instances(0)
        XCTAssertEqual(first.count, 1)
        XCTAssertEqual(first[0].slot, 3)
        XCTAssertEqual(first[0].transform, [1, 0, 0, 1.5, 0, 1, 0, -2, 0, 0, 1, 0])
        XCTAssertEqual(first[0].fill, Int32(bitPattern: 0xFF11_2233))
        XCTAssertEqual(first[0].stroke, Int32(bitPattern: 0x80AA_BBCC))
        XCTAssertEqual(first[0].strokeWidth, 2)
        XCTAssertNil(first[0].normal)
        // The keyframe carried only a translation; everything else is the slot's previous instance.
        let second = try scene.instances(1)
        XCTAssertEqual(second[0].transform, [1, 0, 0, 4, 0, 1, 0, 5, 0, 0, 1, 6])
        XCTAssertEqual(second[0].fill, first[0].fill)
        XCTAssertEqual(second[0].strokeWidth, 2)
        XCTAssertEqual(scene.records[1].kind, 1)
    }

    /** The same shape as tools.build_library packs it (version 2) and as the exporter wrote it (version 1). */
    func testFixtureVersion2MatchesVersion1() throws {
        let v1 = try Scene.parse(try fixture("8b7feb8659.v1.panm"))
        let v2bytes = try fixture("8b7feb8659.v2.panm")
        XCTAssertEqual(Int(v2bytes[4]) | Int(v2bytes[5]) << 8, 2)
        let flags = Int(v2bytes[6]) | Int(v2bytes[7]) << 8
        XCTAssertNotEqual(flags & 8, 0, "the fixture should have elided points")
        let shift = (flags >> 4) & 0xF
        XCTAssertGreaterThan(shift, 0, "the fixture should have rounded bits away")
        let v2 = try Scene.parse(v2bytes)

        XCTAssertEqual(v2.fps, v1.fps)
        XCTAssertEqual(v2.frameCount, v1.frameCount)
        XCTAssertEqual(v2.lo, v1.lo)
        XCTAssertEqual(v2.hi, v1.hi)
        XCTAssertEqual(v2.atlas.count, v1.atlas.count)
        for (a, b) in zip(v1.atlas, v2.atlas) {
            XCTAssertEqual(a.count, b.count)
            for i in 0..<a.count {
                let axis = i % 3
                let span = v1.hi[axis] - v1.lo[axis]
                // Rounding to the shift's step moves a point by at most half a step; an elided handle is
                // recomputed at the third it already sat at, to within the same.
                let tolerance = Float(1 << shift) / 65535 * abs(span) + 1e-5
                XCTAssertEqual(a[i], b[i], accuracy: tolerance, "point float \(i)")
            }
        }
        for r in 0..<v1.frameCount {
            let a = try v1.instances(r), b = try v2.instances(r)
            XCTAssertEqual(a.count, b.count)
            for (x, y) in zip(a, b) {
                // Instances are kept bit for bit.
                XCTAssertEqual(x.slot, y.slot)
                XCTAssertEqual(x.atlasId, y.atlasId)
                XCTAssertEqual(x.flags, y.flags)
                XCTAssertEqual(x.transform.map { $0.bitPattern }, y.transform.map { $0.bitPattern })
                XCTAssertEqual(x.fill, y.fill)
                XCTAssertEqual(x.stroke, y.stroke)
                XCTAssertEqual(x.strokeWidth, y.strokeWidth)
            }
        }
    }

    func testHalfFloat() {
        XCTAssertEqual(Scene.halfToFloat(0x3C00), 1)
        XCTAssertEqual(Scene.halfToFloat(0xC000), -2)
        XCTAssertEqual(Scene.halfToFloat(0x7BFF), 65504)
        XCTAssertEqual(Scene.halfToFloat(0x0001), Float(bitPattern: 0x3380_0000)) // the smallest subnormal, 2^-24
        XCTAssertEqual(Scene.halfToFloat(0x8000).bitPattern, (-0.0 as Float).bitPattern)
        XCTAssertEqual(Scene.halfToFloat(0x7C00), .infinity)
        XCTAssertTrue(Scene.halfToFloat(0x7E00).isNaN)
    }

    func testTruncatedContainerThrows() throws {
        let bytes = try fixture("8b7feb8659.v2.panm")
        XCTAssertThrowsError(try Scene.parse(Array(bytes.prefix(bytes.count - 3)))) { error in
            XCTAssertEqual(error as? PanimError, .bufferUnderflow)
        }
        XCTAssertThrowsError(try Scene.parse([1, 2, 3, 4, 5, 6, 7, 8])) { error in
            XCTAssertEqual(error as? PanimError, .illegalArgument("not a pocketanim IR"))
        }
    }

    /** Floats in dumps and traces are Java's %f: the shortest decimal, rounded half up; the sign of zero kept. */
    func testJavaFormat() {
        XCTAssertEqual(JavaFormat.fixed(0.125, 2), "0.13")
        XCTAssertEqual(JavaFormat.fixed(-0.0, 4), "-0.0000")
        XCTAssertEqual(JavaFormat.fixed(-0.00001, 4), "-0.0000")
        XCTAssertEqual(JavaFormat.fixed(Float(0.1), 6), "0.100000")
        XCTAssertEqual(JavaFormat.fixed(9.9999995, 6), "10.000000")
        XCTAssertEqual(JavaFormat.fixed(1e20, 1), "100000000000000000000.0")
        XCTAssertEqual(JavaFormat.format("%-6s|%5d|%6.2f|%%", .string("ab"), .int(42), .double(3.14159)), "ab    |   42|  3.14|%")
    }
}
