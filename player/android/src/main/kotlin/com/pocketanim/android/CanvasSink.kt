package com.pocketanim.android

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.util.LruCache
import com.pocketanim.core.FRAME_HEIGHT
import com.pocketanim.core.FRAME_WIDTH
import com.pocketanim.core.ImageDraw
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

    override fun strokeStyle(round: Boolean) {
        val join = if (round) Paint.Join.ROUND else Paint.Join.BEVEL
        strokePaint.strokeJoin = join
        bothPaint.strokeJoin = join
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

    private val imagePaint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private val imageMatrix = Matrix()
    private val imageValues = FloatArray(9)

    /**
     * Decoded pictures, by file, up to [IMAGE_CACHE_BYTES]: a lecture holds dozens and a frame shows one or two,
     * so the ones on screen stay decoded and the rest are dropped. A picture is decoded no larger than
     * [IMAGE_MAX_PX] on its long side -- more than a phone screen's worth of the stage.
     */
    private val bitmaps = object : LruCache<String, Bitmap>(IMAGE_CACHE_BYTES) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    private val unreadable: MutableSet<String> = java.util.Collections.synchronizedSet(HashSet())

    private fun bitmapFor(image: ImageDraw, bytes: (String) -> ByteArray?): Bitmap? = decode(image.src, bytes)

    /** Pictures being decoded ahead of their frames ([prefetch]). */
    private val pending: MutableSet<String> = java.util.Collections.synchronizedSet(HashSet())

    /**
     * Decode [src] on the sink's own thread, ahead of the frame that shows it, so drawing it costs only the draw.
     * Ready ones (and ones already being decoded) are left alone.
     */
    fun prefetch(src: String, bytes: (String) -> ByteArray?) {
        if (bitmaps.get(src) != null || src in unreadable || !pending.add(src)) return
        decoder.execute {
            try {
                decode(src, bytes)?.prepareToDraw()
            } catch (_: Throwable) {
                // OutOfMemoryError included: it is decoded when it is drawn, or not at all.
            } finally {
                pending.remove(src)
            }
        }
    }

    private val decoder = java.util.concurrent.Executors.newSingleThreadExecutor { r ->
        Thread(r, "panim-images").apply {
            isDaemon = true
            priority = Thread.MIN_PRIORITY
        }
    }

    private fun decode(src: String, bytes: (String) -> ByteArray?): Bitmap? {
        bitmaps.get(src)?.let { return it }
        if (src in unreadable) return null
        val data = bytes(src)
        val decoded = data?.let {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(it, 0, it.size, bounds)
            var sample = 1
            while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= IMAGE_MAX_PX) sample *= 2
            BitmapFactory.decodeByteArray(it, 0, it.size, BitmapFactory.Options().apply { inSampleSize = sample })
        }
        if (decoded == null) {
            unreadable.add(src)
            return null
        }
        bitmaps.put(src, decoded)
        return decoded
    }

    override fun drawImage(image: ImageDraw, bytes: (String) -> ByteArray?) {
        val target = canvas ?: return
        val bitmap = bitmapFor(image, bytes) ?: return
        val c = image.corners
        // Bitmap pixel (u, v) -> scene: UL + u/w (UR - UL) + v/h (DL - UL), w and h the decoded bitmap's (a
        // sampled decode is smaller than the file, and covers the same corners).
        val w = bitmap.width.toFloat()
        val h = bitmap.height.toFloat()
        imageValues[0] = (c[2] - c[0]) / w; imageValues[1] = (c[4] - c[0]) / h; imageValues[2] = c[0]
        imageValues[3] = (c[3] - c[1]) / w; imageValues[4] = (c[5] - c[1]) / h; imageValues[5] = c[1]
        imageValues[6] = 0f; imageValues[7] = 0f; imageValues[8] = 1f
        imageMatrix.setValues(imageValues)
        imagePaint.alpha = (image.alpha * 255f).toInt().coerceIn(0, 255)
        target.drawBitmap(bitmap, imageMatrix, imagePaint)
    }

    /** Drop decoded pictures (a new scene, or the view going away). */
    fun clearImages() {
        bitmaps.evictAll()
        unreadable.clear()
    }

    private companion object {
        const val IMAGE_CACHE_BYTES = 48 * 1024 * 1024
        const val IMAGE_MAX_PX = 2048
    }
}
