// Ported from player/core/src/main/kotlin/com/pocketanim/core/dsl/Verbs.kt.
import Foundation

/**
 * Manim's animation semantics, reimplemented for the device.
 *
 * This is the part that decides whether shipping the program instead of its
 * samples is honest: if any of it drifts from Manim, the phone draws something
 * subtly different from the video the author previewed. Each function names the
 * Manim function it mirrors so it can be rechecked when Manim changes.
 *
 * Arithmetic here is in Double even though the renderer consumes Float. The
 * cost is a few hundred kilobytes of scratch; the benefit is that iterated
 * Bezier subdivision does not accumulate error the desktop cross-check would
 * then have to excuse.
 */
public enum Verbs {
    /** Points per cubic, Manim's n_points_per_cubic_curve. */
    public static let NPPC = 4
    /** Floats per cubic: four points, three components each. */
    public static let STRIDE = NPPC * 3

    /** Manim's default rate function. */
    public static func smooth(_ t: Double, _ inflection: Double = 10.0) -> Double {
        func sigmoid(_ x: Double) -> Double { 1.0 / (1.0 + exp(-x)) }
        let error = sigmoid(-inflection / 2)
        return coerceIn((sigmoid(inflection * (t - 0.5)) - error) / (1 - 2 * error), 0.0, 1.0)
    }

    /** Manim's linear rate function -- the default for Write and Wait. */
    public static func linear(_ t: Double) -> Double { t }

    public static func thereAndBack(_ t: Double) -> Double { smooth(t < 0.5 ? 2 * t : 2 * (1 - t)) }
    public static func rushInto(_ t: Double) -> Double { 2 * smooth(t / 2) }
    public static func rushFrom(_ t: Double) -> Double { 2 * smooth(t / 2 + 0.5) - 1 }
    public static func slowInto(_ t: Double) -> Double { Swift.max(1 - (1 - t) * (1 - t), 0.0).squareRoot() }
    public static func doubleSmooth(_ t: Double) -> Double {
        t < 0.5 ? 0.5 * smooth(2 * t) : 0.5 * (1 + smooth(2 * t - 1))
    }

    // Manim's rate_functions easings, for the lecture engine's modern entrances.
    public static func easeOutCubic(_ t: Double) -> Double { 1 - pow(1 - t, 3.0) }
    public static func easeInCubic(_ t: Double) -> Double { t * t * t }
    public static func easeOutExpo(_ t: Double) -> Double { t >= 1.0 ? 1.0 : 1 - pow(2.0, -10 * t) }
    public static func easeOutBack(_ t: Double) -> Double {
        let c1 = 1.70158
        let c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3.0) + c1 * pow(t - 1, 2.0)
    }

    public static func rate(_ name: String) -> (Double) -> Double {
        switch name {
        case "linear": return linear
        case "there_and_back": return thereAndBack
        case "rush_into": return rushInto
        case "rush_from": return rushFrom
        case "slow_into": return slowInto
        case "double_smooth": return doubleSmooth
        case "ease_out_cubic": return easeOutCubic
        case "ease_in_cubic": return easeInCubic
        case "ease_out_expo": return easeOutExpo
        case "ease_out_back": return easeOutBack
        default: return { t in smooth(t) }
        }
    }

    private static func comb(_ n: Int, _ k: Int) -> Double {
        var result = 1.0
        for i in 0..<Swift.max(k, 0) { result = result * Double(n - i) / Double(i + 1) }
        return result
    }

    /** Evaluate the Bezier through [points] (xyz triples) at t, into [out]. */
    private static func bezier(
        _ points: [Double], _ from: Int, _ count: Int, _ t: Double, _ out: inout [Double], _ at: Int
    ) {
        let n = count - 1
        out[at] = 0.0; out[at + 1] = 0.0; out[at + 2] = 0.0
        if n < 0 { return }
        for i in 0...n {
            let w = comb(n, i) * pow(1 - t, Double(n - i)) * pow(t, Double(i))
            out[at] += w * points[from + i * 3]
            out[at + 1] += w * points[from + i * 3 + 1]
            out[at + 2] += w * points[from + i * 3 + 2]
        }
    }

    /** Manim's partial_bezier_points: the sub-curve of one cubic over [a, b]. */
    public static func partialBezier(_ curve: [Double], _ offset: Int, _ a: Double, _ b: Double) -> [Double] {
        var out = [Double](repeating: 0, count: STRIDE)
        if a == 1.0 {
            for i in 0..<NPPC {
                out[i * 3] = curve[offset + 9]
                out[i * 3 + 1] = curve[offset + 10]
                out[i * 3 + 2] = curve[offset + 11]
            }
            return out
        }
        // Split at a, then take the front of what remains at the rescaled b.
        var aTo1 = [Double](repeating: 0, count: STRIDE)
        for i in 0..<NPPC {
            bezier(curve, offset + i * 3, NPPC - i, a, &aTo1, i * 3)
        }
        let endProp = (b - a) / (1.0 - a)
        for i in 0..<NPPC {
            bezier(aTo1, 0, i + 1, endProp, &out, i * 3)
        }
        return out
    }

    /** Manim's integer_interpolate: which curve, and how far into it. */
    public static func integerInterpolate(_ start: Int, _ end: Int, _ alpha: Double) -> (Int, Double) {
        if alpha >= 1 { return (end - 1, 1.0) }
        if alpha <= 0 { return (start, 0.0) }
        let scaled = Double(end - start) * alpha
        return (kToInt(Double(start) + scaled), scaled - floor(scaled))
    }

    /** Manim's VMobject.pointwise_become_partial -- what drives Create and Write. */
    public static func pointwiseBecomePartial(_ points: [Double], _ a: Double, _ b: Double) -> [Double] {
        if a <= 0 && b >= 1 { return points }
        let curves = points.count / STRIDE
        if curves == 0 { return points }

        let (lowerIndex, lowerResidue) = integerInterpolate(0, curves, a)
        let (upperIndex, upperResidue) = integerInterpolate(0, curves, b)

        if lowerIndex == upperIndex {
            return partialBezier(points, lowerIndex * STRIDE, lowerResidue, upperResidue)
        }

        let head = partialBezier(points, lowerIndex * STRIDE, lowerResidue, 1.0)
        let middle: ArraySlice<Double> = upperIndex > lowerIndex + 1
            ? points[((lowerIndex + 1) * STRIDE)..<(upperIndex * STRIDE)]
            : []
        let tail = partialBezier(points, upperIndex * STRIDE, 0.0, upperResidue)

        var out: [Double] = []
        out.reserveCapacity(head.count + middle.count + tail.count)
        out.append(contentsOf: head)
        out.append(contentsOf: middle)
        out.append(contentsOf: tail)
        return out
    }

    /**
     * Resample a path to exactly [targetCurves] cubics.
     *
     * Mirrors Manim's bezier_remap, used by align_points before interpolating
     * between two shapes with different curve counts.
     */
    public static func remapCurves(_ points: [Double], _ targetCurves: Int) -> [Double] {
        let current = points.count / STRIDE
        if current == 0 || targetCurves <= current { return points }

        var splits = [Int](repeating: targetCurves / current, count: current)
        for i in 0..<(targetCurves % current) { splits[i] += 1 }

        var out = [Double](repeating: 0, count: targetCurves * STRIDE)
        var written = 0
        for index in 0..<current {
            let count = splits[index]
            for k in 0..<count {
                let piece = partialBezier(points, index * STRIDE, Double(k) / Double(count), Double(k + 1) / Double(count))
                out.replaceSubrange(written..<(written + STRIDE), with: piece)
                written += STRIDE
            }
        }
        return out
    }

    /** Bring two paths to a common curve count so they can be interpolated. */
    public static func align(_ a: [Double], _ b: [Double]) -> ([Double], [Double]) {
        let target = Swift.max(a.count / STRIDE, b.count / STRIDE)
        return (remapCurves(a, target), remapCurves(b, target))
    }

    /** Manim's Circle: `segments` cubic arcs, handles at 4/3*tan(d/4)*r. */
    public static func circle(_ radius: Double, _ segments: Int = 8) -> [Double] {
        let step = 2 * Double.pi / Double(segments)
        let handle = (4.0 / 3.0) * tan(step / 4) * radius
        var out = [Double](repeating: 0, count: segments * STRIDE)
        for i in 0..<segments {
            let t0 = Double(i) * step
            let t1 = Double(i + 1) * step
            let p0x = radius * cos(t0), p0y = radius * sin(t0)
            let p3x = radius * cos(t1), p3y = radius * sin(t1)
            let o = i * STRIDE
            out[o] = p0x; out[o + 1] = p0y
            out[o + 3] = p0x + -sin(t0) * handle; out[o + 4] = p0y + cos(t0) * handle
            out[o + 6] = p3x - -sin(t1) * handle; out[o + 7] = p3y - cos(t1) * handle
            out[o + 9] = p3x; out[o + 10] = p3y
        }
        return out
    }

    /** Manim's Rectangle: corners counter-clockwise from top-right, straight edges. */
    public static func rectangle(_ width: Double, _ height: Double) -> [Double] {
        let w = width / 2
        let h = height / 2
        let corners = [w, h, -w, h, -w, -h, w, -h, w, h]
        var out = [Double](repeating: 0, count: 4 * STRIDE)
        let ts = [0.0, 1.0 / 3, 2.0 / 3, 1.0]
        for edge in 0..<4 {
            let ax = corners[edge * 2], ay = corners[edge * 2 + 1]
            let bx = corners[edge * 2 + 2], by = corners[edge * 2 + 3]
            for (k, t) in ts.enumerated() {
                let o = edge * STRIDE + k * 3
                out[o] = ax + (bx - ax) * t
                out[o + 1] = ay + (by - ay) * t
            }
        }
        return out
    }

    public static func square(_ side: Double) -> [Double] { rectangle(side, side) }

    public static func nearlyEqual(_ a: [Double], _ i: Int, _ b: [Double], _ j: Int, _ tol: Double = 1e-6) -> Bool {
        Swift.abs(a[i] - b[j]) <= tol && Swift.abs(a[i + 1] - b[j + 1]) <= tol && Swift.abs(a[i + 2] - b[j + 2]) <= tol
    }
}
