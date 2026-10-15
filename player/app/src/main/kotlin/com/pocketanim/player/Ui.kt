package com.pocketanim.player

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.view.Gravity
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import java.util.Locale

/**
 * The app's look, in code: colours, sizes, and the icons, drawn as paths (the app has no resources and no
 * libraries, so it builds its views itself). Dark throughout, like a video app: the picture is the bright thing.
 */
object Ui {
    /**
     * An error as a report: what was being done, the phone and app, and the whole exception -- its class, message
     * and stack, through every cause -- so a failure on the phone can be read (and copied) without a cable and
     * logcat.
     */
    fun errorText(context: Context, what: String, error: Throwable): String {
        val stack = java.io.StringWriter().also { error.printStackTrace(java.io.PrintWriter(it)) }.toString()
        val version = runCatching {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName
        }.getOrNull() ?: "?"
        return buildString {
            append(what).append("\n\n")
            append("${error.javaClass.name}: ${error.message ?: "(no message)"}\n")
            var cause = error.cause
            while (cause != null && cause !== cause.cause) {
                append("caused by ${cause.javaClass.name}: ${cause.message ?: "(no message)"}\n")
                cause = cause.cause
            }
            append("\napp $version · Android ${android.os.Build.VERSION.RELEASE} (API ${android.os.Build.VERSION.SDK_INT})")
            append(" · ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}\n\n")
            append(stack)
        }
    }

    /** The full error in a dialog: selectable, scrollable, with Copy. [onClose] runs when it is dismissed. */
    fun showError(activity: android.app.Activity, what: String, error: Throwable, onClose: (() -> Unit)? = null) {
        if (activity.isFinishing) return
        val text = errorText(activity, what, error)
        android.util.Log.e("Pocketanim", text)
        val body = TextView(activity).apply {
            setText(text)
            setTextIsSelectable(true)
            typeface = Typeface.MONOSPACE
            textSize = 11f
            setTextColor(TEXT)
            val pad = (16 * activity.resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, pad / 2)
        }
        val scroll = android.widget.ScrollView(activity).apply { addView(body) }
        android.app.AlertDialog.Builder(activity, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle(what)
            .setView(scroll)
            .setPositiveButton("Copy") { _, _ ->
                val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Pocketanim error", text))
                android.widget.Toast.makeText(activity, "Error copied", android.widget.Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Close", null)
            .setOnDismissListener { onClose?.invoke() }
            .show()
    }

    const val BG = 0xFF0E1014.toInt()
    const val SURFACE = 0xFF171A20.toInt()
    const val SURFACE_HIGH = 0xFF20242C.toInt()
    const val LINE = 0xFF2A2F38.toInt()
    const val TEXT = 0xFFF2F3F5.toInt()
    const val MUTED = 0xFF9AA1AD.toInt()
    const val FAINT = 0xFF6B7280.toInt()
    const val ACCENT = 0xFFF5B83D.toInt()          // the lectures' gold
    const val ACCENT_DARK = 0xFF3A2E12.toInt()
    const val GOOD = 0xFF5BC489.toInt()
    const val SCRIM = 0x99000000.toInt()

    val MEDIUM: Typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
    val REGULAR: Typeface = Typeface.create("sans-serif", Typeface.NORMAL)
    val MONO: Typeface = Typeface.create("monospace", Typeface.NORMAL)

    fun dp(context: Context, value: Float): Int = (value * context.resources.displayMetrics.density + 0.5f).toInt()
    fun dp(view: View, value: Float): Int = dp(view.context, value)

    fun text(context: Context, size: Float, color: Int = TEXT, face: Typeface = REGULAR, lines: Int = 0): TextView =
        TextView(context).apply {
            textSize = size
            setTextColor(color)
            typeface = face
            if (lines > 0) {
                maxLines = lines
                ellipsize = android.text.TextUtils.TruncateAt.END
            }
            includeFontPadding = false
        }

    fun rounded(color: Int, radius: Float, stroke: Int = 0, strokeColor: Int = 0): GradientDrawable =
        GradientDrawable().apply {
            setColor(color)
            cornerRadius = radius
            if (stroke > 0) setStroke(stroke, strokeColor)
        }

    /** A background that shows a touch: [base] with a ripple over it (or a bare ripple, bounded by [radius]). */
    fun pressable(base: Int, radius: Float, ripple: Int = 0x33FFFFFF): Drawable =
        RippleDrawable(ColorStateList.valueOf(ripple), if (base == 0) null else rounded(base, radius),
            rounded(Color.WHITE, radius))

    /** A round icon button. */
    fun iconButton(context: Context, icon: Icon, size: Float = 44f, tint: Int = TEXT, fill: Int = 0,
                   description: String, onClick: () -> Unit): ImageView =
        ImageView(context).apply {
            setImageDrawable(IconDrawable(icon, tint))
            val pad = dp(context, size * 0.22f)
            setPadding(pad, pad, pad, pad)
            background = pressable(fill, dp(context, size / 2).toFloat())
            contentDescription = description
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(dp(context, size), dp(context, size))
        }

    /** A small rounded label: "On phone", "Streams", "Sample". */
    fun chip(context: Context, label: String, color: Int, background: Int): TextView =
        text(context, 11f, color, MEDIUM).apply {
            text = label
            val h = dp(context, 8f)
            val v = dp(context, 3f)
            setPadding(h, v, h, v)
            this.background = rounded(background, dp(context, 10f).toFloat())
            gravity = Gravity.CENTER
        }

    /** 1:05:09, 24:05, 0:42. */
    fun clock(seconds: Double): String {
        val total = seconds.coerceAtLeast(0.0).toInt()
        val h = total / 3600
        val m = (total / 60) % 60
        val s = total % 60
        return if (h > 0) String.format(Locale.ROOT, "%d:%02d:%02d", h, m, s)
        else String.format(Locale.ROOT, "%d:%02d", m, s)
    }

    /** "24 min", "1 h 5 min", "45 s". */
    fun length(seconds: Double): String {
        val total = seconds.toInt()
        return when {
            total < 60 -> "$total s"
            total < 3600 -> "${(total + 30) / 60} min"
            else -> "${total / 3600} h ${((total % 3600) + 30) / 60} min"
        }
    }

    fun bytes(count: Long): String = when {
        count >= 1_000_000 -> String.format(Locale.ROOT, "%.1f MB", count / 1e6)
        count >= 1_000 -> String.format(Locale.ROOT, "%.0f kB", count / 1e3)
        else -> "$count B"
    }
}

enum class Icon { PLAY, PAUSE, REPLAY, BACK10, FORWARD10, BACK, CHAPTERS, FULLSCREEN, EXIT_FULLSCREEN, CLOUD, CHECK,
    IMPORT, REFRESH, MORE, NEXT, SPEED, DOWNLOAD }

/**
 * The app's icons, drawn on a 24-unit grid scaled to the bounds: no image files to ship or scale, crisp at any
 * size, tinted by colour.
 */
class IconDrawable(private val icon: Icon, color: Int) : Drawable() {
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        this.color = color
    }
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.2f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        this.color = color
    }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        this.color = color
        textAlign = Paint.Align.CENTER
        textSize = 7.5f
        typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
    }
    private val path = Path()

    override fun draw(canvas: Canvas) {
        val b = bounds
        val scale = minOf(b.width(), b.height()) / 24f
        canvas.save()
        canvas.translate(b.left + (b.width() - 24 * scale) / 2, b.top + (b.height() - 24 * scale) / 2)
        canvas.scale(scale, scale)
        path.reset()
        when (icon) {
            Icon.PLAY -> {
                path.moveTo(8f, 5.5f); path.lineTo(19f, 12f); path.lineTo(8f, 18.5f); path.close()
                canvas.drawPath(path, fill)
            }
            Icon.PAUSE -> {
                canvas.drawRoundRect(RectF(6.5f, 5f, 10f, 19f), 1f, 1f, fill)
                canvas.drawRoundRect(RectF(14f, 5f, 17.5f, 19f), 1f, 1f, fill)
            }
            Icon.REPLAY, Icon.REFRESH -> {
                path.addArc(RectF(4.5f, 4.5f, 19.5f, 19.5f), -70f, 300f)
                canvas.drawPath(path, line)
                arrowHead(canvas, 9.2f, 3.2f, 0f)
            }
            Icon.BACK10, Icon.FORWARD10 -> {
                val back = icon == Icon.BACK10
                canvas.save()
                if (!back) canvas.scale(-1f, 1f, 12f, 12f)
                path.addArc(RectF(3.5f, 3.5f, 20.5f, 20.5f), -60f, 290f)
                canvas.drawPath(path, line)
                arrowHead(canvas, 9.5f, 2.6f, 0f)
                canvas.restore()
                canvas.drawText("10", 12f, 15f, label)
            }
            Icon.BACK -> {
                path.moveTo(19f, 12f); path.lineTo(5.5f, 12f)
                path.moveTo(11f, 6f); path.lineTo(5f, 12f); path.lineTo(11f, 18f)
                canvas.drawPath(path, line)
            }
            Icon.CHAPTERS -> {
                for (y in floatArrayOf(7f, 12f, 17f)) {
                    canvas.drawCircle(5f, y, 1.3f, fill)
                    canvas.drawLine(9f, y, 20f, y, line)
                }
            }
            Icon.FULLSCREEN, Icon.EXIT_FULLSCREEN -> {
                val inward = icon == Icon.EXIT_FULLSCREEN
                for ((cx, cy) in listOf(4f to 4f, 20f to 4f, 4f to 20f, 20f to 20f)) {
                    val dx = if (cx < 12) 1f else -1f
                    val dy = if (cy < 12) 1f else -1f
                    val x = if (inward) cx + dx * 5f else cx
                    val y = if (inward) cy + dy * 5f else cy
                    val sx = if (inward) -dx else dx
                    val sy = if (inward) -dy else dy
                    path.moveTo(x + sx * 5f, y); path.lineTo(x, y); path.lineTo(x, y + sy * 5f)
                }
                canvas.drawPath(path, line)
            }
            Icon.CLOUD -> {
                path.addCircle(9f, 13f, 4.5f, Path.Direction.CW)
                path.addCircle(14f, 10.5f, 5.5f, Path.Direction.CW)
                path.addRoundRect(RectF(4.5f, 12.5f, 20.5f, 18f), 2.75f, 2.75f, Path.Direction.CW)
                canvas.drawPath(path, fill)
            }
            Icon.CHECK -> {
                path.moveTo(5f, 12.5f); path.lineTo(10f, 17.5f); path.lineTo(19.5f, 7f)
                canvas.drawPath(path, line)
            }
            Icon.IMPORT -> {
                path.moveTo(12f, 4f); path.lineTo(12f, 15f)
                path.moveTo(7.5f, 10.5f); path.lineTo(12f, 15f); path.lineTo(16.5f, 10.5f)
                path.moveTo(5f, 15.5f); path.lineTo(5f, 19.5f); path.lineTo(19f, 19.5f); path.lineTo(19f, 15.5f)
                canvas.drawPath(path, line)
            }
            Icon.DOWNLOAD -> {
                path.moveTo(12f, 4f); path.lineTo(12f, 16f)
                path.moveTo(7f, 11f); path.lineTo(12f, 16f); path.lineTo(17f, 11f)
                path.moveTo(5.5f, 20f); path.lineTo(18.5f, 20f)
                canvas.drawPath(path, line)
            }
            Icon.MORE -> for (y in floatArrayOf(5.5f, 12f, 18.5f)) canvas.drawCircle(12f, y, 1.9f, fill)
            Icon.NEXT -> {
                path.moveTo(6f, 6f); path.lineTo(15f, 12f); path.lineTo(6f, 18f); path.close()
                canvas.drawPath(path, fill)
                canvas.drawRoundRect(RectF(16f, 6f, 18.5f, 18f), 0.8f, 0.8f, fill)
            }
            Icon.SPEED -> {
                path.addArc(RectF(3.5f, 5f, 20.5f, 22f), 180f, 180f)
                canvas.drawPath(path, line)
                canvas.drawLine(12f, 13.5f, 16.5f, 9f, line)
                canvas.drawCircle(12f, 13.5f, 1.6f, fill)
            }
        }
        canvas.restore()
    }

    /** A small filled arrowhead at (x, y), pointing along [degrees] (0: right). */
    private fun arrowHead(canvas: Canvas, x: Float, y: Float, degrees: Float) {
        canvas.save()
        canvas.rotate(degrees, x, y)
        val head = Path()
        head.moveTo(x + 3.2f, y); head.lineTo(x - 1.6f, y - 2.8f); head.lineTo(x - 1.6f, y + 2.8f); head.close()
        canvas.drawPath(head, fill)
        canvas.restore()
    }

    override fun setAlpha(alpha: Int) {
        fill.alpha = alpha
        line.alpha = alpha
        label.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        fill.colorFilter = colorFilter
        line.colorFilter = colorFilter
        label.colorFilter = colorFilter
    }

    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT

    override fun getIntrinsicWidth(): Int = 48
    override fun getIntrinsicHeight(): Int = 48
}
