package com.pocketanim.android

import android.graphics.Bitmap
import android.graphics.Canvas
import com.pocketanim.core.FRAME_HEIGHT
import com.pocketanim.core.FRAME_WIDTH
import com.pocketanim.core.Frames
import com.pocketanim.core.RenderOptions
import com.pocketanim.core.Renderer
import java.io.File

/**
 * A still of a lecture, for the library's cards: one frame drawn off screen by the same renderer that plays it.
 *
 * A lecture is a program, not a video, so there is no poster frame to read: this computes one. Opening a lecture
 * costs a moment, so a still is made once and kept as a PNG beside the lecture ([cached]).
 */
object Thumbnails {

    /** A good frame to show: a little into the first chapter's body (past its title card), else a fifth in. */
    fun pick(frames: Frames, chapterStarts: List<Int>): Int {
        val count = frames.frameCount
        if (count <= 1) return 0
        val second = chapterStarts.getOrNull(1)
        val first = chapterStarts.firstOrNull()
        val guess = when {
            first != null && second != null -> first + ((second - first) * 0.35).toInt()
            first != null -> first + frames.fps * 8
            else -> count / 5
        }
        return guess.coerceIn(0, count - 1)
    }

    /** Frame [index] drawn into a bitmap [width] pixels wide (16:9). */
    fun render(frames: Frames, index: Int, width: Int): Bitmap {
        val height = (width * FRAME_HEIGHT / FRAME_WIDTH).toInt()
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val sink = CanvasSink()
        val depth = sink.begin(canvas, width, height, frames.background)
        try {
            Renderer.drawFrame(frames, index.coerceIn(0, frames.frameCount - 1), sink, RenderOptions.forSurface(width))
        } finally {
            sink.end(depth)
        }
        return bitmap
    }

    /** The still kept at [file], made by [make] the first time. Null when it cannot be made. */
    fun cached(file: File, make: () -> Bitmap): Bitmap? {
        if (file.isFile) {
            android.graphics.BitmapFactory.decodeFile(file.absolutePath)?.let { return it }
        }
        return try {
            val bitmap = make()
            file.parentFile?.mkdirs()
            val part = File(file.path + ".part")
            part.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 90, it) }
            part.renameTo(file)
            bitmap
        } catch (e: Throwable) {
            // OutOfMemoryError included: a card without its picture, not the app closing.
            null
        }
    }
}
