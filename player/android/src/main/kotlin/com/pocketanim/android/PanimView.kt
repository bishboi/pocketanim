package com.pocketanim.android

import android.content.Context
import android.graphics.Color
import android.util.AttributeSet
import android.view.SurfaceHolder
import android.view.SurfaceView
import com.pocketanim.core.FRAME_HEIGHT
import com.pocketanim.core.FRAME_WIDTH
import com.pocketanim.core.Frames
import com.pocketanim.core.Playback
import com.pocketanim.core.RenderOptions
import com.pocketanim.core.Renderer
import java.io.File

/**
 * A SurfaceView that plays a .panm.
 *
 * SurfaceView rather than a custom View: rendering happens on its own thread
 * with no dependence on the UI thread's frame pacing, which matters because a
 * heavy frame here costs tens of milliseconds and would otherwise jank the
 * whole app. The trade is that the surface's lifecycle is not the view's, so
 * the thread is owned by the surface callbacks below, not by attach/detach.
 */
class PanimView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : SurfaceView(context, attrs), SurfaceHolder.Callback {

    private val sink = CanvasSink()
    private var thread: RenderThread? = null
    private var surfaceCanvas: SurfaceCanvas? = null

    /** Whether frames are going through the GPU pipeline. See [SurfaceCanvas]. */
    val usingHardwareCanvas: Boolean
        get() = surfaceCanvas?.usingHardware == true

    var backgroundColorArgb: Int = Color.BLACK

    var scene: Frames? = null
        private set
    var playback: Playback? = null
        private set

    private var audio: AudioPlayer? = null
    private var audioClock: AudioClock? = null

    /** Statistics the throughput gate needs; see docs/SPEC.md §11. */
    @Volatile var framesDrawn: Long = 0L
        private set
    @Volatile var framesSkipped: Long = 0L
        private set
    @Volatile var lastFrameMillis: Double = 0.0
        private set

    init {
        holder.addCallback(this)
    }

    /**
     * Fit the scene's own aspect ratio inside whatever space the host offers.
     *
     * Manim composes for 16:9, so a surface that simply fills a 20:9 phone
     * shows a stretched scene -- a circle becomes an ellipse. The benchmark
     * spent three device runs reporting numbers from a 2148x411 surface before
     * anyone noticed, which is a good argument for the view refusing to do it
     * at all rather than each host remembering not to ask.
     */
    override fun onMeasure(widthSpec: Int, heightSpec: Int) {
        val availableWidth = MeasureSpec.getSize(widthSpec)
        val availableHeight = MeasureSpec.getSize(heightSpec)
        if (availableWidth <= 0 || availableHeight <= 0) {
            super.onMeasure(widthSpec, heightSpec)
            return
        }
        val aspect = FRAME_WIDTH / FRAME_HEIGHT
        var width = availableWidth
        var height = (width / aspect).toInt()
        if (height > availableHeight) {
            height = availableHeight
            width = (height * aspect).toInt()
        }
        setMeasuredDimension(width, height)
    }

    fun load(scene: Frames) {
        releaseAudio()
        this.scene = scene
        this.playback = Playback(scene)
    }

    /**
     * Attach narration.
     *
     * Optional by design: §5.3 downloads audio only on request, so a scene
     * routinely plays before its narration exists. Attaching switches the
     * master clock from the system clock to the audio device; until the track
     * reports a position, [AudioClock] returns null and [Playback] keeps using
     * the system clock, which is what covers the start-up gap.
     */
    fun attachAudio(file: File, sampleRate: Int, channelCount: Int) {
        releaseAudio()
        val clock = AudioClock(sampleRate, channelCount)
        audioClock = clock
        audio = AudioPlayer(file, clock)
        playback?.audio = clock
    }

    fun play() {
        playback?.play()
        audioClock?.play()
        audio?.start()
    }

    fun pause() {
        playback?.pause()
        audioClock?.pause()
    }

    fun seekToFrame(index: Int) {
        playback?.seekToFrame(index)
        scene?.let { audio?.seekTo(index.toDouble() / it.fps) }
        // Draw the sought frame immediately: a scrub that waits for the next
        // tick to show anything feels broken even when it is only 16 ms.
        thread?.requestRedraw()
    }

    /** Call from the host's onDestroy; an AudioTrack outlives the view otherwise. */
    fun release() {
        releaseAudio()
    }

    private fun releaseAudio() {
        audio?.stop()
        audio = null
        audioClock?.release()
        audioClock = null
        playback?.audio = null
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        surfaceCanvas = SurfaceCanvas(holder)
        thread = RenderThread(holder).also { it.start() }
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        thread?.resize(width, height)
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        thread?.shutdown()
        thread = null
    }

    private inner class RenderThread(private val holder: SurfaceHolder) : Thread("panim-render") {
        @Volatile private var running = true
        @Volatile private var widthPx = 0
        @Volatile private var heightPx = 0
        @Volatile private var forceRedraw = false

        fun resize(w: Int, h: Int) {
            widthPx = w
            heightPx = h
            forceRedraw = true
        }

        fun requestRedraw() {
            forceRedraw = true
        }

        fun shutdown() {
            running = false
            interrupt()
            try {
                join(500)
            } catch (_: InterruptedException) {
                currentThread().interrupt()
            }
        }

        override fun run() {
            while (running) {
                val active = scene
                val clock = playback
                if (active == null || clock == null || widthPx == 0 || heightPx == 0) {
                    idle()
                    continue
                }

                // frameToDraw returns -1 when the current frame is already on
                // screen, so a paused or slow-moving scene costs nothing.
                var index = clock.frameToDraw()
                if (index < 0) {
                    if (!forceRedraw) {
                        idle()
                        continue
                    }
                    index = clock.currentFrame()
                }
                forceRedraw = false

                val started = System.nanoTime()
                // GPU-backed where the device allows it; see SurfaceCanvas for
                // why lockCanvas alone is the wrong call.
                val surface = surfaceCanvas ?: continue
                val canvas = surface.acquire() ?: continue
                try {
                    val depth = sink.begin(canvas, widthPx, heightPx, backgroundColorArgb)
                    try {
                        // Options, not defaults: the only one that depends on
                        // the target is level of detail, and half a pixel is a
                        // promise about pixels rather than about scene units.
                        Renderer.drawFrame(active, index, sink, RenderOptions.forSurface(widthPx))
                    } finally {
                        sink.end(depth)
                    }
                } finally {
                    surface.release(canvas)
                }

                lastFrameMillis = (System.nanoTime() - started) / 1e6
                framesDrawn++

                // Frames the clock moved past while this one was being drawn.
                // This is the number the device gate cares about: dropping
                // frames is survivable, and counting them is how we find out.
                val now = clock.currentFrame()
                if (now > index + 1) framesSkipped += (now - index - 1).toLong()
            }
        }

        private fun idle() {
            try {
                sleep(2)
            } catch (_: InterruptedException) {
                currentThread().interrupt()
                running = false
            }
        }
    }
}
