package com.pocketanim.android

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import com.pocketanim.core.FRAME_HEIGHT
import com.pocketanim.core.FRAME_WIDTH
import com.pocketanim.core.PathSink

/**
 * [PathSink] on Skia.
 *
 * The canvas is put into *scene* coordinates -- y up, origin centred -- rather
 * than converting points as they arrive. Manim expresses stroke_width in scene
 * units, so letting Skia scale the stroke is what makes widths match Cairo
 * instead of approximating them.
 *
 * One Path and two Paints are reused for the whole frame. Vector playback lives
 * or dies on allocation and draw-call count, not on arithmetic, and a fresh
 * Path per instance would put a few thousand allocations into every frame.
 */
class CanvasSink : PathSink {
    private val path = Path()
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeJoin = Paint.Join.ROUND
        strokeCap = Paint.Cap.ROUND
    }
    // Same geometry, one traversal: Skia fills and strokes from a single
    // drawPath when the style asks for both, and the renderer only asks when
    // the two colours are identical and opaque.
    private val bothPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL_AND_STROKE
        strokeJoin = Paint.Join.ROUND
        strokeCap = Paint.Cap.ROUND
    }

    private var canvas: Canvas? = null

    /**
     * Point the sink at a canvas for one frame.
     *
     * Returns the number of canvas save levels to restore. The caller owns the
     * restore so an exception mid-frame cannot leave the canvas transformed.
     */
    fun begin(target: Canvas, widthPx: Int, heightPx: Int, background: Int): Int {
        canvas = target
        val depth = target.save()
        target.drawColor(background)
        target.translate(widthPx / 2f, heightPx / 2f)
        target.scale(widthPx / FRAME_WIDTH, -heightPx / FRAME_HEIGHT)
        return depth
    }

    fun end(depth: Int) {
        canvas?.restoreToCount(depth)
        canvas = null
    }

    override fun beginPath() {
        path.rewind()
    }

    override fun moveTo(x: Float, y: Float) {
        path.moveTo(x, y)
    }

    override fun cubicTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float) {
        path.cubicTo(x1, y1, x2, y2, x3, y3)
    }

    override fun lineTo(x: Float, y: Float) {
        path.lineTo(x, y)
    }

    override fun closeSubpath() {
        path.close()
    }

    override fun fillPath(argb: Int) {
        fillPaint.color = argb
        canvas?.drawPath(path, fillPaint)
    }

    override fun strokePath(argb: Int, widthInSceneUnits: Float) {
        strokePaint.color = argb
        strokePaint.strokeWidth = widthInSceneUnits
        canvas?.drawPath(path, strokePaint)
    }

    override fun fillAndStrokePath(argb: Int, widthInSceneUnits: Float) {
        bothPaint.color = argb
        bothPaint.strokeWidth = widthInSceneUnits
        canvas?.drawPath(path, bothPaint)
    }
}
