package com.pocketanim.player

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View

/**
 * The seek bar: what has played, what is here to play (a lecture still arriving), the chapters as gaps in the
 * track, and while a finger is on it, a bubble with the time and the chapter it would land in.
 */
class TimelineView(context: Context) : View(context) {

    interface Listener {
        fun onScrubStart()
        fun onScrub(fraction: Float)
        fun onScrubEnd(fraction: Float)
    }

    var listener: Listener? = null

    /** 0..1 played. Ignored while scrubbing (the finger wins). */
    var played = 0f
        set(value) {
            field = value.coerceIn(0f, 1f)
            if (!scrubbing) invalidate()
        }

    /** 0..1 of the lecture on the phone (the rest still coming); 1 when it all is. */
    var loaded = 1f
        set(value) {
            field = value.coerceIn(0f, 1f)
            invalidate()
        }

    /** Where each chapter begins, 0..1, and their titles (for the bubble). */
    var chapters: List<Pair<Float, String>> = emptyList()
        set(value) {
            field = value.sortedBy { it.first }
            invalidate()
        }

    /** The lecture's length, for the bubble's time. */
    var durationSeconds = 0.0

    var scrubbing = false
        private set
    private var scrubAt = 0f

    private val density = resources.displayMetrics.density
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x40FFFFFF }
    private val buffered = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x70FFFFFF }
    private val progress = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Ui.ACCENT }
    private val thumb = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Ui.ACCENT }
    private val bubble = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xE6202329.toInt() }
    private val bubbleTime = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Ui.TEXT
        textSize = 14 * density
        typeface = Ui.MEDIUM
        textAlign = Paint.Align.CENTER
    }
    private val bubbleTitle = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Ui.MUTED
        textSize = 11.5f * density
        typeface = Ui.REGULAR
        textAlign = Paint.Align.CENTER
    }
    private val rect = RectF()

    private val pad get() = 10 * density
    private val barHeight get() = (if (scrubbing) 5f else 3.5f) * density

    init {
        isClickable = true
        contentDescription = "Seek"
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        // Room above the bar for the bubble while scrubbing; the touch area stays generous for a thumb.
        val height = (64 * density).toInt()
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), resolveSize(height, heightMeasureSpec))
    }

    private val barY get() = height - 18 * density

    override fun onDraw(canvas: Canvas) {
        val left = pad
        val right = width - pad
        val span = right - left
        val y = barY
        val h = barHeight
        val at = if (scrubbing) scrubAt else played
        val gap = 2 * density
        // The track as chapter segments: a gap where each chapter begins.
        val cuts = chapters.map { it.first }.filter { it > 0.002f && it < 0.998f }
        var start = 0f
        for (end in cuts + 1f) {
            val x0 = left + span * start + if (start > 0f) gap / 2 else 0f
            val x1 = left + span * end - if (end < 1f) gap / 2 else 0f
            if (x1 > x0) {
                segment(canvas, x0, x1, y, h, track)
                val lx = minOf(x1, left + span * loaded)
                if (lx > x0) segment(canvas, x0, lx, y, h, buffered)
                val px = minOf(x1, left + span * at)
                if (px > x0) segment(canvas, x0, px, y, h, progress)
            }
            start = end
        }
        val tx = left + span * at
        canvas.drawCircle(tx, y, (if (scrubbing) 9f else 6.5f) * density, thumb)

        if (scrubbing && durationSeconds > 0) {
            val title = chapters.lastOrNull { it.first <= at + 1e-4f }?.second.orEmpty()
            val time = Ui.clock(durationSeconds * at)
            val w = maxOf(bubbleTime.measureText(time), bubbleTitle.measureText(title.take(34))) + 24 * density
            val bh = (if (title.isEmpty()) 30f else 46f) * density
            val bx = (tx - w / 2).coerceIn(0f, width - w)
            val by = y - 16 * density - bh
            rect.set(bx, by, bx + w, by + bh)
            canvas.drawRoundRect(rect, 8 * density, 8 * density, bubble)
            canvas.drawText(time, bx + w / 2, by + 20 * density, bubbleTime)
            if (title.isNotEmpty()) canvas.drawText(title.take(34), bx + w / 2, by + 38 * density, bubbleTitle)
        }
    }

    private fun segment(canvas: Canvas, x0: Float, x1: Float, y: Float, h: Float, paint: Paint) {
        rect.set(x0, y - h / 2, x1, y + h / 2)
        canvas.drawRoundRect(rect, h / 2, h / 2, paint)
    }

    private fun fractionAt(x: Float): Float = ((x - pad) / (width - 2 * pad)).coerceIn(0f, 1f)

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                scrubbing = true
                scrubAt = fractionAt(event.x)
                listener?.onScrubStart()
                listener?.onScrub(scrubAt)
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> if (scrubbing) {
                scrubAt = fractionAt(event.x)
                listener?.onScrub(scrubAt)
                invalidate()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> if (scrubbing) {
                scrubAt = fractionAt(event.x)
                scrubbing = false
                played = scrubAt
                listener?.onScrubEnd(scrubAt)
                invalidate()
                if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
            }
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
