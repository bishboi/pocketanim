package com.pocketanim.core.dsl

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.sin
import kotlin.math.tan

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
object Verbs {
    /** Points per cubic, Manim's n_points_per_cubic_curve. */
    const val NPPC = 4
    /** Floats per cubic: four points, three components each. */
    const val STRIDE = NPPC * 3

    /** Manim's default rate function. */
    fun smooth(t: Double, inflection: Double = 10.0): Double {
        fun sigmoid(x: Double) = 1.0 / (1.0 + exp(-x))
        val error = sigmoid(-inflection / 2)
        return ((sigmoid(inflection * (t - 0.5)) - error) / (1 - 2 * error)).coerceIn(0.0, 1.0)
    }

    /** Manim's linear rate function -- the default for Write and Wait. */
    fun linear(t: Double) = t

    fun rate(name: String): (Double) -> Double = if (name == "linear") ::linear else { t -> smooth(t) }

    private fun comb(n: Int, k: Int): Double {
        var result = 1.0
        for (i in 0 until k) result = result * (n - i) / (i + 1)
        return result
    }

    /** Evaluate the Bezier through [points] (xyz triples) at t, into [out]. */
    private fun bezier(points: DoubleArray, from: Int, count: Int, t: Double, out: DoubleArray, at: Int) {
        val n = count - 1
        out[at] = 0.0; out[at + 1] = 0.0; out[at + 2] = 0.0
        for (i in 0..n) {
            val w = comb(n, i) * Math.pow(1 - t, (n - i).toDouble()) * Math.pow(t, i.toDouble())
            out[at] += w * points[from + i * 3]
            out[at + 1] += w * points[from + i * 3 + 1]
            out[at + 2] += w * points[from + i * 3 + 2]
        }
    }

    /** Manim's partial_bezier_points: the sub-curve of one cubic over [a, b]. */
    fun partialBezier(curve: DoubleArray, offset: Int, a: Double, b: Double): DoubleArray {
        val out = DoubleArray(STRIDE)
        if (a == 1.0) {
            for (i in 0 until NPPC) {
                out[i * 3] = curve[offset + 9]
                out[i * 3 + 1] = curve[offset + 10]
                out[i * 3 + 2] = curve[offset + 11]
            }
            return out
        }
        // Split at a, then take the front of what remains at the rescaled b.
        val aTo1 = DoubleArray(STRIDE)
        for (i in 0 until NPPC) {
            bezier(curve, offset + i * 3, NPPC - i, a, aTo1, i * 3)
        }
        val endProp = (b - a) / (1.0 - a)
        for (i in 0 until NPPC) {
            bezier(aTo1, 0, i + 1, endProp, out, i * 3)
        }
        return out
    }

    /** Manim's integer_interpolate: which curve, and how far into it. */
    fun integerInterpolate(start: Int, end: Int, alpha: Double): Pair<Int, Double> {
        if (alpha >= 1) return Pair(end - 1, 1.0)
        if (alpha <= 0) return Pair(start, 0.0)
        val scaled = (end - start) * alpha
        return Pair((start + scaled).toInt(), scaled - floor(scaled))
    }

    /** Manim's VMobject.pointwise_become_partial -- what drives Create and Write. */
    fun pointwiseBecomePartial(points: DoubleArray, a: Double, b: Double): DoubleArray {
        if (a <= 0 && b >= 1) return points.copyOf()
        val curves = points.size / STRIDE
        if (curves == 0) return points.copyOf()

        val (lowerIndex, lowerResidue) = integerInterpolate(0, curves, a)
        val (upperIndex, upperResidue) = integerInterpolate(0, curves, b)

        if (lowerIndex == upperIndex) {
            return partialBezier(points, lowerIndex * STRIDE, lowerResidue, upperResidue)
        }

        val head = partialBezier(points, lowerIndex * STRIDE, lowerResidue, 1.0)
        val middle = if (upperIndex > lowerIndex + 1) {
            points.copyOfRange((lowerIndex + 1) * STRIDE, upperIndex * STRIDE)
        } else DoubleArray(0)
        val tail = partialBezier(points, upperIndex * STRIDE, 0.0, upperResidue)

        val out = DoubleArray(head.size + middle.size + tail.size)
        head.copyInto(out, 0)
        middle.copyInto(out, head.size)
        tail.copyInto(out, head.size + middle.size)
        return out
    }

    /**
     * Resample a path to exactly [targetCurves] cubics.
     *
     * Mirrors Manim's bezier_remap, used by align_points before interpolating
     * between two shapes with different curve counts.
     */
    fun remapCurves(points: DoubleArray, targetCurves: Int): DoubleArray {
        val current = points.size / STRIDE
        if (current == 0 || targetCurves <= current) return points.copyOf()

        val splits = IntArray(current) { targetCurves / current }
        for (i in 0 until targetCurves % current) splits[i]++

        val out = DoubleArray(targetCurves * STRIDE)
        var written = 0
        for (index in 0 until current) {
            val count = splits[index]
            for (k in 0 until count) {
                val piece = partialBezier(
                    points, index * STRIDE, k.toDouble() / count, (k + 1).toDouble() / count,
                )
                piece.copyInto(out, written)
                written += STRIDE
            }
        }
        return out
    }

    /** Bring two paths to a common curve count so they can be interpolated. */
    fun align(a: DoubleArray, b: DoubleArray): Pair<DoubleArray, DoubleArray> {
        val target = maxOf(a.size / STRIDE, b.size / STRIDE)
        return Pair(remapCurves(a, target), remapCurves(b, target))
    }

    /** Manim's Circle: `segments` cubic arcs, handles at 4/3*tan(d/4)*r. */
    fun circle(radius: Double, segments: Int = 8): DoubleArray {
        val step = 2 * Math.PI / segments
        val handle = (4.0 / 3.0) * tan(step / 4) * radius
        val out = DoubleArray(segments * STRIDE)
        for (i in 0 until segments) {
            val t0 = i * step
            val t1 = (i + 1) * step
            val p0x = radius * cos(t0); val p0y = radius * sin(t0)
            val p3x = radius * cos(t1); val p3y = radius * sin(t1)
            val o = i * STRIDE
            out[o] = p0x; out[o + 1] = p0y
            out[o + 3] = p0x + -sin(t0) * handle; out[o + 4] = p0y + cos(t0) * handle
            out[o + 6] = p3x - -sin(t1) * handle; out[o + 7] = p3y - cos(t1) * handle
            out[o + 9] = p3x; out[o + 10] = p3y
        }
        return out
    }

    /** Manim's Rectangle: corners counter-clockwise from top-right, straight edges. */
    fun rectangle(width: Double, height: Double): DoubleArray {
        val w = width / 2
        val h = height / 2
        val corners = doubleArrayOf(w, h, -w, h, -w, -h, w, -h, w, h)
        val out = DoubleArray(4 * STRIDE)
        for (edge in 0 until 4) {
            val ax = corners[edge * 2]; val ay = corners[edge * 2 + 1]
            val bx = corners[edge * 2 + 2]; val by = corners[edge * 2 + 3]
            for ((k, t) in doubleArrayOf(0.0, 1.0 / 3, 2.0 / 3, 1.0).withIndex()) {
                val o = edge * STRIDE + k * 3
                out[o] = ax + (bx - ax) * t
                out[o + 1] = ay + (by - ay) * t
            }
        }
        return out
    }

    fun square(side: Double): DoubleArray = rectangle(side, side)

    fun nearlyEqual(a: DoubleArray, i: Int, b: DoubleArray, j: Int, tol: Double = 1e-6): Boolean =
        abs(a[i] - b[j]) <= tol && abs(a[i + 1] - b[j + 1]) <= tol && abs(a[i + 2] - b[j + 2]) <= tol
}
