// Ported from player/core/src/main/kotlin/com/pocketanim/core/dsl/ProgramFrames.kt.
import Foundation

/**
 * A tier-1 program presented as frames.
 *
 * Holds one frame, not all of them. The timeline is a state machine that can be
 * stepped, and verb boundaries are checkpointed, so playing forward costs one
 * verb body per frame and seeking backwards costs a replay bounded by the
 * longest verb rather than by the distance seeked.
 *
 * Not thread-safe, deliberately: producing a frame mutates the machine, so the
 * render thread owns it and nothing else touches it. That is also why
 * [instances] must be called before [shape] for a given frame.
 */
public final class ProgramFrames: Frames {
    private let builder: Builder

    init(_ builder: Builder) {
        self.builder = builder
    }

    public var fps: Int { builder.fps }
    public var frameCount: Int { builder.frameCount }
    public var background: Int32 { builder.background }

    private var positioned = -1

    private func position(_ index: Int) throws {
        if index != positioned {
            try builder.seek(index)
            positioned = index
        }
    }

    public func shape(_ atlasId: Int) -> [Float] { builder.shape(atlasId) }

    public func camera(_ index: Int) throws -> [Float]? {
        try position(index)
        return builder.frameCamera()
    }

    public func instances(_ index: Int) throws -> [Instance] {
        try position(index)
        let frame = builder.frameInstances()
        let drifting = builder.currentDrifting
        if drifting.isEmpty { return frame }
        // A drifting backdrop or picture moves every frame, from the clock (Drift.at), not from the timeline.
        var out = frame
        let seconds = Double(index) / Double(builder.fps)
        for (name, span) in drifting {
            guard let outer = builder.drift(name)?.at(seconds) else { continue }
            if span[0] < span[1] {
                for slot in span[0]..<span[1] { out[slot] = moved(frame[slot], outer) }
            }
        }
        return out
    }

    private func moved(_ inst: Instance, _ outer: [Double]) -> Instance {
        let t = inst.transform
        var out = [Float](repeating: 0, count: 12)
        for row in 0..<3 {
            for col in 0..<3 {
                var sum = 0.0
                for k in 0..<3 { sum += outer[row * 4 + k] * Double(t[k * 4 + col]) }
                out[row * 4 + col] = Float(sum)
            }
            var tr = outer[row * 4 + 3]
            for k in 0..<3 { tr += outer[row * 4 + k] * Double(t[k * 4 + 3]) }
            out[row * 4 + 3] = Float(tr)
        }
        return Instance(slot: inst.slot, atlasId: inst.atlasId, flags: inst.flags, transform: out, fill: inst.fill,
                        stroke: inst.stroke, strokeWidth: inst.strokeWidth, normal: inst.normal)
    }

    /** Lower z first, declaration order between equals: then each goes in no earlier than the one before it. */
    private lazy var byZ: [ImageSpec] = builder.images.stableSortedByDouble { $0.z }
    private var corners = [Float](repeating: 0, count: 6)

    public func images(_ index: Int) throws -> [ImageDraw] {
        let specs = byZ
        if specs.isEmpty { return [] }
        try position(index)
        var out: [ImageDraw] = []
        let frame = Double(Swift.min(Swift.max(index, 0), Swift.max(frameCount - 1, 0)))
        for spec in specs {
            var corners = [Float](repeating: 0, count: 6)
            let alpha = spec.at(frame, &corners)
            if alpha <= 0 { continue }
            spec.drift?.move(&corners, Double(index) / Double(builder.fps))
            out.append(ImageDraw(src: spec.src, width: spec.width, height: spec.height, alpha: alpha, corners: corners,
                                 before: builder.instancesAtOrBelow(spec.z)))
        }
        return out
    }

    public func imageBytes(_ src: String) -> [UInt8]? { builder.imageBytes(src) }

    public func recover() {
        builder.recover()
        positioned = -1
    }

    /** The frame built for [index] and where each picture stands in it. */
    public func contentKey(_ index: Int) throws -> Int64 {
        try position(index)
        var key = builder.version
        // A drifting backdrop or picture changes the picture every frame.
        if !builder.currentDrifting.isEmpty { key = key &* 31 &+ Int64(index) }
        let frame = Double(Swift.min(Swift.max(index, 0), Swift.max(frameCount - 1, 0)))
        for spec in byZ {
            let alpha = spec.at(frame, &corners)
            if alpha > 0, let drift = spec.drift { drift.move(&corners, Double(index) / Double(builder.fps)) }
            key = key &* 31 &+ Int64(rawBits(alpha))
            if alpha > 0 { for c in corners { key = key &* 31 &+ Int64(rawBits(c)) } }
        }
        return key
    }

    public func imagesBetween(_ from: Int, _ to: Int) -> [String] {
        var out: [String] = []
        for spec in byZ {
            var showing = false
            var k = 0
            while k < spec.keyCount {
                let at = spec.keys[k * ImageSpec.KEY]
                let alpha = spec.keys[k * ImageSpec.KEY + 1]
                // Showing at some frame of [from, to]: a key in the window, or the key before it still visible.
                if at > Double(to) { break }
                if alpha > 0.004 && (at >= Double(from) || k + 1 >= spec.keyCount ||
                        spec.keys[(k + 1) * ImageSpec.KEY] >= Double(from)) { showing = true }
                k += 1
            }
            if showing && !out.contains(spec.src) { out.append(spec.src) }
        }
        return out
    }
}
