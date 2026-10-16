// Ported from player/core/src/main/kotlin/com/pocketanim/core/Panm.kt.
import Foundation

/**
 * The .panm container, decoded.
 *
 * This is the fourth independent implementation of the format, after
 * exporter/decode.py, client/PanimDecoder.java and the Kotlin core it is ported
 * from, and it is the one that ships on iOS. Half-float conversion is written
 * out rather than delegated (Float16 is not on every platform Swift builds for),
 * so the same code is exercised by the Linux cross-check and by the phone.
 */
public enum Panm {
    public static let MAGIC: Int32 = 0x4D4E4150 // "PANM" little-endian
    public static let FLAG_CAMERA = 1
    public static let SHADE_IN_3D = 1

    /**
     * The face belongs to a closed solid, so one pointing away from the camera
     * is behind one pointing towards it and cannot be seen. Only the exporter
     * can know this -- it saw the class that built the shape, where the device
     * sees an anonymous quad.
     */
    public static let CLOSED_SOLID = 2

    /**
     * The stored normal points into that solid rather than out of it. Shading
     * wants the normal Manim derived, sign and all; culling wants to know
     * which way is out. One bit serves both rather than a second normal
     * serving neither.
     */
    public static let NORMAL_INWARD = 4
    public static let CAMERA_FLOATS = 17
    public static let REC_SNAPSHOT = 0
}

/**
 * Little-endian reads off a byte array, as java.nio.ByteBuffer in LITTLE_ENDIAN order does them. The one place
 * bytes become numbers: assembled from bytes, never by casting unaligned memory. Reading past the end throws, as
 * ByteBuffer's BufferUnderflowException does.
 */
public struct ByteReader {
    public let bytes: [UInt8]
    public private(set) var position = 0

    public init(_ bytes: [UInt8]) { self.bytes = bytes }

    @inline(__always)
    public mutating func u8() throws -> UInt8 {
        guard position < bytes.count else { throw PanimError.bufferUnderflow }
        let b = bytes[position]
        position += 1
        return b
    }

    /** `buf.short.toInt() and 0xFFFF`. */
    @inline(__always)
    public mutating func u16() throws -> UInt16 {
        guard position + 2 <= bytes.count else { throw PanimError.bufferUnderflow }
        let v = UInt16(bytes[position]) | UInt16(bytes[position + 1]) << 8
        position += 2
        return v
    }

    @inline(__always)
    public mutating func u32() throws -> UInt32 {
        guard position + 4 <= bytes.count else { throw PanimError.bufferUnderflow }
        let v = UInt32(bytes[position]) | UInt32(bytes[position + 1]) << 8 |
            UInt32(bytes[position + 2]) << 16 | UInt32(bytes[position + 3]) << 24
        position += 4
        return v
    }

    /** `buf.int`. */
    @inline(__always)
    public mutating func int() throws -> Int32 { Int32(bitPattern: try u32()) }

    /** `buf.float`. */
    @inline(__always)
    public mutating func float() throws -> Float { Float(bitPattern: try u32()) }

    /** `buf.get(dst)`. */
    public mutating func bytes(_ count: Int) throws -> [UInt8] {
        guard count >= 0, position + count <= bytes.count else { throw PanimError.bufferUnderflow }
        let out = Array(bytes[position..<(position + count)])
        position += count
        return out
    }
}

/** One drawable: an atlas shape placed by an affine transform and styled. */
public final class Instance {
    public let slot: Int
    public let atlasId: Int
    public let flags: Int
    /** Row-major 3x4: the linear part in columns 0..2, translation in column 3. */
    public let transform: [Float]
    public let fill: Int32          // ARGB
    public let stroke: Int32        // ARGB
    public let strokeWidth: Float
    public let normal: [Float]?     // nil unless SHADE_IN_3D

    public init(
        slot: Int, atlasId: Int, flags: Int, transform: [Float], fill: Int32, stroke: Int32, strokeWidth: Float,
        normal: [Float]?
    ) {
        self.slot = slot
        self.atlasId = atlasId
        self.flags = flags
        self.transform = transform
        self.fill = fill
        self.stroke = stroke
        self.strokeWidth = strokeWidth
        self.normal = normal
    }
}

public final class Record {
    public let kind: Int
    public let instances: [Instance]

    public init(kind: Int, instances: [Instance]) {
        self.kind = kind
        self.instances = instances
    }
}

public final class Scene: Frames {
    public let fps: Int
    /** Per shape, flat xyz triples, already dequantised. */
    public let atlas: [[Float]]
    /** Per record, [Panm.CAMERA_FLOATS] floats; nil when the scene is 2D. */
    public let cameras: [[Float]]?
    public let records: [Record]
    public let lo: [Float]
    public let hi: [Float]

    public init(fps: Int, atlas: [[Float]], cameras: [[Float]]?, records: [Record], lo: [Float], hi: [Float]) {
        self.fps = fps
        self.atlas = atlas
        self.cameras = cameras
        self.records = records
        self.lo = lo
        self.hi = hi
    }

    public var frameCount: Int { records.count }

    public func shape(_ atlasId: Int) -> [Float] { atlas[atlasId] }

    public func camera(_ index: Int) throws -> [Float]? {
        guard let cameras = cameras, index >= 0, index < cameras.count else { return nil }
        return cameras[index]
    }

    public func instances(_ index: Int) throws -> [Instance] { try frame(index) }

    /**
     * Resolve a frame to its ordered instance list.
     *
     * Walk back to the preceding snapshot and replay keyframes forward.
     * Keyframes carry absolute values, so replay is an overwrite and never
     * accumulates -- which is what makes seeking exact rather than approximate,
     * and what lets the player scrub without replaying from frame zero.
     */
    public func frame(_ index: Int) throws -> [Instance] {
        guard index >= 0 && index < records.count else {
            throw PanimError.indexOutOfBounds("Index \(index) out of bounds for length \(records.count)")
        }
        var start = index
        while start > 0 && records[start].kind != Panm.REC_SNAPSHOT { start -= 1 }

        var order: [Int] = []
        var state: [Int: Instance] = [:]
        for r in start...index {
            let record = records[r]
            if record.kind == Panm.REC_SNAPSHOT {
                order.removeAll(keepingCapacity: true)
                state.removeAll(keepingCapacity: true)
                for inst in record.instances {
                    order.append(inst.slot)
                    state[inst.slot] = inst
                }
            } else {
                for inst in record.instances {
                    if state[inst.slot] == nil { order.append(inst.slot) }
                    state[inst.slot] = inst
                }
            }
        }

        var out: [Instance] = []
        out.reserveCapacity(order.count)
        for slot in order { if let inst = state[slot] { out.append(inst) } }
        return out
    }

    public static func parse(_ bytes: [UInt8]) throws -> Scene {
        var buf = ByteReader(bytes)

        try require(try buf.int() == Panm.MAGIC, "not a pocketanim IR")
        let version = Int(try buf.u16())
        let flags = Int(try buf.u16())
        let fps = Int(try buf.u16())
        let recordCount = Int(try buf.int())
        let atlasCount = Int(try buf.int())

        var lo = [Float](repeating: 0, count: 3)
        for i in 0..<3 { lo[i] = try buf.float() }
        var hi = [Float](repeating: 0, count: 3)
        for i in 0..<3 { hi[i] = try buf.float() }
        var span = [Float](repeating: 0, count: 3)
        for i in 0..<3 {
            let d = hi[i] - lo[i]
            span[i] = Swift.abs(d) < 1e-9 as Float ? 1.0 : d
        }

        var cameras: [[Float]]? = nil
        if flags & Panm.FLAG_CAMERA != 0 {
            var all: [[Float]] = []
            all.reserveCapacity(Swift.max(recordCount, 0))
            for _ in 0..<Swift.max(recordCount, 0) {
                var camera = [Float](repeating: 0, count: Panm.CAMERA_FLOATS)
                for k in 0..<Panm.CAMERA_FLOATS { camera[k] = try buf.float() }
                all.append(camera)
            }
            cameras = all
        }
        if version == 2 {
            return try parseCompact(&buf, flags, fps, recordCount, atlasCount, lo, hi, span, cameras)
        }

        // Atlas geometry is quantised to uint16 over the scene bounding box.
        var atlas: [[Float]] = []
        atlas.reserveCapacity(Swift.max(atlasCount, 0))
        for _ in 0..<Swift.max(atlasCount, 0) {
            let pointCount = Int(try buf.int())
            var points = [Float](repeating: 0, count: pointCount * 3)
            for p in 0..<pointCount {
                for axis in 0..<3 {
                    let raw = try buf.u16()
                    points[p * 3 + axis] = lo[axis] + (Float(raw) / 65535.0) * span[axis]
                }
            }
            atlas.append(points)
        }

        var records: [Record] = []
        records.reserveCapacity(Swift.max(recordCount, 0))
        for _ in 0..<Swift.max(recordCount, 0) {
            let kind = Int(try buf.u8())
            let instanceCount = Int(try buf.int())
            var instances: [Instance] = []
            instances.reserveCapacity(Swift.max(instanceCount, 0))
            for _ in 0..<Swift.max(instanceCount, 0) {
                let slot = Int(try buf.int())
                let atlasId = Int(try buf.int())
                let instFlags = Int(try buf.u8())

                // The linear part is float16; translation stays float32
                // because at 720p half precision is visible in position.
                var transform = [Float](repeating: 0, count: 12)
                for k in 0..<9 {
                    transform[(k / 3) * 4 + (k % 3)] = halfToFloat(Int(try buf.u16()))
                }
                for row in 0..<3 { transform[row * 4 + 3] = try buf.float() }

                let fill = try readColor(&buf)
                let stroke = try readColor(&buf)
                let strokeWidth = Float(try buf.u16()) / 64.0

                var normal: [Float]? = nil
                if instFlags & Panm.SHADE_IN_3D != 0 {
                    var n = [Float](repeating: 0, count: 3)
                    for k in 0..<3 { n[k] = halfToFloat(Int(try buf.u16())) }
                    normal = n
                }

                instances.append(Instance(
                    slot: slot, atlasId: atlasId, flags: instFlags, transform: transform, fill: fill,
                    stroke: stroke, strokeWidth: strokeWidth, normal: normal
                ))
            }
            records.append(Record(kind: kind, instances: instances))
        }

        if version != 1 {
            FileHandle.standardError.write("warning: unexpected IR version \(version)\n".data(using: .utf8)!)
        }
        return Scene(fps: fps, atlas: atlas, cameras: cameras, records: records, lo: lo, hi: hi)
    }

    /** A varint as tools/panm_compact.py writes it, accumulated in a 32-bit Int as the Kotlin decoder does. */
    private static func varint(_ buf: inout ByteReader) throws -> Int32 {
        var value: Int32 = 0
        var shift: Int32 = 0
        while true {
            let b = Int32(try buf.u8())
            value = value | ((b & 0x7F) &<< shift)
            if b & 0x80 == 0 { return value }
            shift += 7
        }
    }

    /**
     * Version 2 (tools/panm_compact.py): points delta-coded as zigzag varints (z left out of a flat scene,
     * low bits rounded away as the header's flags say), and each instance stored as what changed since its
     * slot's previous one. Decodes to what exporter/decode.py does.
     */
    private static func parseCompact(
        _ buf: inout ByteReader, _ flags: Int, _ fps: Int, _ recordCount: Int, _ atlasCount: Int,
        _ lo: [Float], _ hi: [Float], _ span: [Float], _ cameras: [[Float]]?
    ) throws -> Scene {
        let axes = flags & 2 != 0 ? 2 : 3
        let shift = Int32((flags >> 4) & 0xF)
        let elided = flags & 8 != 0
        var atlas: [[Float]] = []
        atlas.reserveCapacity(Swift.max(atlasCount, 0))
        for _ in 0..<Swift.max(atlasCount, 0) {
            let pointCount = Int(try varint(&buf))
            var points = [Float](repeating: 0, count: pointCount * 3)
            var prev: [Int32] = [0, 0, 0]
            // The next written point, delta-decoded, into points[p].
            func read(_ p: Int) throws {
                for axis in 0..<3 {
                    if axis < axes {
                        let z = try varint(&buf)
                        prev[axis] = prev[axis] &+ (ushr(z, 1) ^ (0 &- (z & 1)))
                    }
                    points[p * 3 + axis] = lo[axis] + (Float(prev[axis] &<< shift) / 65535.0) * span[axis]
                }
            }
            if elided && pointCount % 4 == 0 && pointCount > 0 {
                // Per cubic two bits (tools/panm_compact.py): 1, its start is the previous end; 2, it is
                // straight and its handles sit at a third and two thirds of the way.
                let cubics = pointCount / 4
                let codes = try buf.bytes((cubics + 3) / 4)
                for k in 0..<cubics {
                    let code = (Int(codes[k / 4]) >> (2 * (k % 4))) & 3
                    let a = 4 * k
                    if code & 1 != 0 {
                        guard a >= 1 else {
                            throw PanimError.indexOutOfBounds("Index -3 out of bounds for length \(points.count)")
                        }
                        for axis in 0..<3 { points[a * 3 + axis] = points[(a - 1) * 3 + axis] }
                    } else {
                        try read(a)
                    }
                    if code & 2 == 0 {
                        try read(a + 1)
                        try read(a + 2)
                    }
                    try read(a + 3)
                    if code & 2 != 0 {
                        for axis in 0..<3 {
                            let start = points[a * 3 + axis]
                            let end = points[(a + 3) * 3 + axis]
                            points[(a + 1) * 3 + axis] = start + (end - start) / 3
                            points[(a + 2) * 3 + axis] = start + 2 * (end - start) / 3
                        }
                    }
                }
            } else {
                for p in 0..<pointCount { try read(p) }
            }
            atlas.append(points)
        }

        var last: [Int: Instance] = [:]
        // A slot's last normal, kept while it is drawn unshaded (its normal is null then) for when it is shaded
        // again with the same normal, which is not written twice.
        var lastNormal: [Int: [Float]] = [:]
        var records: [Record] = []
        records.reserveCapacity(Swift.max(recordCount, 0))
        for _ in 0..<Swift.max(recordCount, 0) {
            let kind = Int(try buf.u8())
            let instanceCount = Int(try varint(&buf))
            var instances: [Instance] = []
            instances.reserveCapacity(Swift.max(instanceCount, 0))
            for _ in 0..<Swift.max(instanceCount, 0) {
                let slot = Int(try varint(&buf))
                let mask = Int(try buf.u8())
                let before = last[slot]
                let atlasId = mask & 1 != 0 ? Int(try varint(&buf)) : (before?.atlasId ?? 0)
                let instFlags = mask & 2 != 0 ? Int(try buf.u8()) : (before?.flags ?? 0)
                var transform = before?.transform ?? [Float](repeating: 0, count: 12)
                if mask & 4 != 0 {
                    for k in 0..<9 { transform[(k / 3) * 4 + (k % 3)] = halfToFloat(Int(try buf.u16())) }
                }
                if mask & 8 != 0 {
                    for row in 0..<3 { transform[row * 4 + 3] = try buf.float() }
                }
                let fill = mask & 16 != 0 ? try readColor(&buf) : (before?.fill ?? 0)
                let stroke = mask & 32 != 0 ? try readColor(&buf) : (before?.stroke ?? 0)
                let strokeWidth: Float = mask & 64 != 0 ? Float(try buf.u16()) / 64.0 : (before?.strokeWidth ?? 0)
                var normal: [Float]?
                if mask & 128 != 0 {
                    var n = [Float](repeating: 0, count: 3)
                    for k in 0..<3 { n[k] = halfToFloat(Int(try buf.u16())) }
                    normal = n
                } else {
                    normal = before?.normal ?? lastNormal[slot]
                }
                if let n = normal { lastNormal[slot] = n }
                if instFlags & Panm.SHADE_IN_3D == 0 { normal = nil }
                let inst = Instance(
                    slot: slot, atlasId: atlasId, flags: instFlags, transform: transform, fill: fill,
                    stroke: stroke, strokeWidth: strokeWidth, normal: normal
                )
                last[slot] = inst
                instances.append(inst)
            }
            records.append(Record(kind: kind, instances: instances))
        }
        return Scene(fps: fps, atlas: atlas, cameras: cameras, records: records, lo: lo, hi: hi)
    }

    /** Four bytes r,g,b,a off the wire into one ARGB int. */
    private static func readColor(_ buf: inout ByteReader) throws -> Int32 {
        let r = UInt32(try buf.u8())
        let g = UInt32(try buf.u8())
        let b = UInt32(try buf.u8())
        let a = UInt32(try buf.u8())
        return Int32(bitPattern: (a << 24) | (r << 16) | (g << 8) | b)
    }

    /**
     * IEEE 754 half to single. Written out rather than delegated: Float16 is missing from Swift on Intel Macs,
     * and the device and the cross-check must run the same code or the cross-check proves nothing about the
     * device.
     */
    public static func halfToFloat(_ h: Int) -> Float {
        let sign = UInt32(h & 0x8000) << 16
        let exp = (h & 0x7C00) >> 10
        let man = UInt32(h & 0x03FF)
        if exp == 0x1F { return Float(bitPattern: sign | 0x7F80_0000 | (man << 13)) }
        if exp != 0 { return Float(bitPattern: sign | (UInt32(exp - 15 + 127) << 23) | (man << 13)) }
        if man == 0 { return Float(bitPattern: sign) }
        // Subnormal: shift the leading one up into place and pay
        // for each shift out of the exponent.
        var shifts: UInt32 = 0
        var m = man
        while m & 0x0400 == 0 {
            m <<= 1
            shifts += 1
        }
        return Float(bitPattern: sign | ((113 - shifts) << 23) | ((m & 0x03FF) << 13))
    }
}
