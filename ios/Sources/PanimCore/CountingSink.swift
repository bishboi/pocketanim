// Ported from player/core/src/main/kotlin/com/pocketanim/core/CountingSink.kt.
import Foundation

/**
 * A [PathSink] that draws nothing and counts everything.
 *
 * Wrapping a real sink separates two costs that look the same from outside: the
 * geometry work (decode, transform, project, depth sort, shade) and the
 * rasterisation. On a device the second dominates, and the only way to know by
 * how much is to measure the first on its own.
 *
 * The counts it keeps are the ones that predict device behaviour. Draws, because
 * per-draw CPU overhead is what stalls a floor-segment phone. Verbs in the
 * largest single path, because Skia falls back to CPU rasterisation past
 * kMaxGPUPathRendererVerbs (16,384) and that limit is per path, not per frame.
 */
public final class CountingSink: PathSink {
    private let delegate: PathSink?

    public private(set) var verbs: Int64 = 0
    public private(set) var draws: Int64 = 0
    public private(set) var maxPathVerbs = 0

    private var current = 0

    public init(_ delegate: PathSink? = nil) {
        self.delegate = delegate
    }

    public func reset() {
        verbs = 0
        draws = 0
        maxPathVerbs = 0
        current = 0
    }

    public func beginPath() {
        current = 0
        delegate?.beginPath()
    }

    public func moveTo(_ x: Float, _ y: Float) {
        verbs += 1; current += 1
        delegate?.moveTo(x, y)
    }

    public func cubicTo(_ x1: Float, _ y1: Float, _ x2: Float, _ y2: Float, _ x3: Float, _ y3: Float) {
        verbs += 1; current += 1
        delegate?.cubicTo(x1, y1, x2, y2, x3, y3)
    }

    public func lineTo(_ x: Float, _ y: Float) {
        verbs += 1; current += 1
        delegate?.lineTo(x, y)
    }

    public func closeSubpath() {
        verbs += 1; current += 1
        if current > maxPathVerbs { maxPathVerbs = current }
        delegate?.closeSubpath()
    }

    public func fillPath(_ argb: Int32) {
        draws += 1
        delegate?.fillPath(argb)
    }

    public func strokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        draws += 1
        delegate?.strokePath(argb, widthInSceneUnits)
    }

    public func fillAndStrokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        // One draw, which is the whole reason the renderer asks for it.
        draws += 1
        delegate?.fillAndStrokePath(argb, widthInSceneUnits)
    }

    public func strokeStyle(round: Bool) {
        delegate?.strokeStyle(round: round)
    }

    public func drawImage(_ image: ImageDraw, _ bytes: (String) -> [UInt8]?) {
        draws += 1
        delegate?.drawImage(image, bytes)
    }
}
