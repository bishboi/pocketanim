package com.pocketanim.android

import android.graphics.Canvas
import android.os.Build
import android.view.SurfaceHolder

/**
 * Acquiring a frame buffer to draw into, on the GPU where possible.
 *
 * This distinction is the whole of §5's substrate decision and it is easy to
 * lose. `SurfaceHolder.lockCanvas()` returns a **software** canvas: Skia
 * rasterises into a CPU buffer and the GPU only composites the result.
 * `lockHardwareCanvas()` returns a canvas backed by HWUI's GPU pipeline, which
 * is what "Skia via the Canvas API" is supposed to mean.
 *
 * The first benchmark run used `lockCanvas`, so it measured CPU rasterisation
 * on a phone -- the one thing the architecture exists to avoid. Fill-bound
 * scenes suffer worst from that, since filling pixels is nearly free on a GPU
 * and decidedly not free on a CPU.
 *
 * A hardware canvas cannot be read back and does not preserve the previous
 * frame's contents, so every frame must draw its own background. The renderer
 * already does.
 */
class SurfaceCanvas(private val holder: SurfaceHolder) {

    /** Which path the last [acquire] actually used. Reported, never assumed. */
    var usingHardware: Boolean = false
        private set

    /** True when this device can give us a GPU-backed canvas at all. */
    val hardwareAvailable: Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M

    fun acquire(): Canvas? {
        if (hardwareAvailable) {
            // Falls back rather than failing: a surface can refuse a hardware
            // canvas (no GPU context yet, an emulator without acceleration),
            // and a software frame is better than a dropped one.
            val canvas = try {
                holder.lockHardwareCanvas()
            } catch (_: IllegalStateException) {
                null
            } catch (_: UnsupportedOperationException) {
                null
            }
            if (canvas != null) {
                usingHardware = true
                return canvas
            }
        }
        usingHardware = false
        return holder.lockCanvas()
    }

    fun release(canvas: Canvas) = holder.unlockCanvasAndPost(canvas)

    val description: String
        get() = if (usingHardware) "hardware (HWUI/GPU)" else "software (CPU raster)"
}
