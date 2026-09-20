package com.pocketanim.core

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
class CountingSink(private val delegate: PathSink? = null) : PathSink {
    var verbs = 0L
        private set
    var draws = 0L
        private set
    var maxPathVerbs = 0
        private set

    private var current = 0

    fun reset() {
        verbs = 0
        draws = 0
        maxPathVerbs = 0
        current = 0
    }

    override fun beginPath() {
        current = 0
        delegate?.beginPath()
    }

    override fun moveTo(x: Float, y: Float) {
        verbs++; current++
        delegate?.moveTo(x, y)
    }

    override fun cubicTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float) {
        verbs++; current++
        delegate?.cubicTo(x1, y1, x2, y2, x3, y3)
    }

    override fun closeSubpath() {
        verbs++; current++
        if (current > maxPathVerbs) maxPathVerbs = current
        delegate?.closeSubpath()
    }

    override fun fillPath(argb: Int) {
        draws++
        delegate?.fillPath(argb)
    }

    override fun strokePath(argb: Int, widthInSceneUnits: Float) {
        draws++
        delegate?.strokePath(argb, widthInSceneUnits)
    }
}
