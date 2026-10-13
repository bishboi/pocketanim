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

    /**
     * Held while a frame is made and drawn. The scene's frames are made by a state machine that only one thread
     * may drive, and a surface may not be drawn on once it is destroyed: turning the phone (or the whole-screen
     * switch) destroys and remakes the surface, and the old thread, given half a second to stop, could still be
     * mid-frame when the new one began -- two threads driving one scene crashed the app, or left a part of one frame
     * drawn into the next.
     */
    private val drawLock = Any()

    /** Whether frames are going through the GPU pipeline. See [SurfaceCanvas]. */
    val usingHardwareCanvas: Boolean
        get() = thread?.surface?.usingHardware == true

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
        // A picture another library could not supply may be in this one.
        sink.clearImages()
        this.scene = scene
        this.playback = Playback(scene).also { playback ->
            playback.onLoop = { index -> audio?.seekTo(index.toDouble() / scene.fps) }
        }
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
    fun attachAudio(file: File, sampleRate: Int, channelCount: Int) =
        attachAudio(file.absolutePath, sampleRate, channelCount)

    /**
     * Attach narration from [source]: a file's path, or a URL it is streamed from. Starts where the picture is, at
     * the picture's speed.
     */
    fun attachAudio(source: String, sampleRate: Int, channelCount: Int) {
        releaseAudio()
        val clock = AudioClock(sampleRate, channelCount)
        clock.speed = (playback?.speed ?: 1.0).toFloat()
        audioClock = clock
        val player = AudioPlayer(source, clock)
        audio = player
        playback?.audio = clock
        val at = playback?.currentFrame() ?: 0
        scene?.let { if (at > 0) player.seekTo(at.toDouble() / it.fps) }
        if (playback?.playing == true) {
            clock.play()
            player.start()
        }
    }

    /** Whether the narration is waiting on the network for its next piece (a stream buffering). */
    val audioBuffering: Boolean get() = audio?.buffering == true

    /** Why the narration cannot play, when it cannot (the picture plays on silent). */
    val audioProblem: String? get() = audio?.failed

    /** Whether narration is attached. */
    val hasAudio: Boolean get() = audio != null

    fun play() {
        playback?.play()
        audioClock?.play()
        audio?.start()
    }

    fun pause() {
        playback?.pause()
        audioClock?.pause()
    }

    /** Play faster or slower (1.0 as made), the narration's pitch kept. */
    fun setSpeed(speed: Double) {
        playback?.speed = speed
        audioClock?.speed = (playback?.speed ?: speed).toFloat()
    }

    fun seekToFrame(index: Int) {
        playback?.seekToFrame(index)
        scene?.let { audio?.seekTo(index.toDouble() / it.fps) }
        // Draw the sought frame immediately: a scrub that waits for the next
        // tick to show anything feels broken even when it is only 16 ms.
        thread?.requestRedraw()
    }

    private var scrubResume = false

    /**
     * A finger on the seek bar: the picture follows it ([scrubTo]) and the narration waits, paused, to be sought
     * once where the finger lifts ([endScrub]). Seeking the narration at every move asked a stream for a new place
     * dozens of times a second, and the voice stuttered over the drag.
     */
    fun beginScrub() {
        scrubResume = playback?.playing == true
        if (scrubResume) pause()
    }

    /** The picture at [index] while scrubbing; the narration is left where it is until [endScrub]. */
    fun scrubTo(index: Int) {
        playback?.seekToFrame(index)
        thread?.requestRedraw()
    }

    /** The finger lifted at [index]: the narration is sought there, and playing goes on if it was playing. */
    fun endScrub(index: Int) {
        seekToFrame(index)
        if (scrubResume) play()
        scrubResume = false
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
        thread?.shutdown()
        thread = RenderThread(SurfaceCanvas(holder)).also { it.start() }
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        thread?.resize(width, height)
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        thread?.shutdown()
        thread = null
    }

    private inner class RenderThread(val surface: SurfaceCanvas) : Thread("panim-render") {
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

        /** Stop, and return only once no frame of this thread is being made or drawn (the surface may then go). */
        fun shutdown() {
            running = false
            synchronized(drawLock) {}
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
                val redraw = forceRedraw
                forceRedraw = false

                prefetchImages(active, index)
                val started = System.nanoTime()
                val drawn = synchronized(drawLock) {
                    if (!running) return
                    try {
                        drawFrame(active, index, redraw)
                    } catch (e: Throwable) {
                        // A frame that cannot be made or drawn is dropped, not the app: the scene starts again from
                        // a kept boundary, and the frame after is drawn whole. (A surface going away mid-frame is
                        // one such; an OutOfMemoryError another.)
                        android.util.Log.w("PanimView", "frame $index dropped", e)
                        runCatching { active.recover() }
                        drawnKey = Frames.UNKNOWN
                        forceRedraw = true
                        false
                    }
                }
                if (!drawn) {
                    idle()
                    continue
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

        /** Frame [index] on the surface; false when it was not drawn (the same picture, or no canvas to draw on). */
        private fun drawFrame(active: Frames, index: Int, redraw: Boolean): Boolean {
            // A lecture is mostly holds: a frame that shows what is already on screen is not drawn again.
            val key = active.contentKey(index)
            if (!redraw && key != Frames.UNKNOWN && key == drawnKey && active === drawnScene) return false
            // GPU-backed where the device allows it; see SurfaceCanvas for
            // why lockCanvas alone is the wrong call.
            val canvas = surface.acquire() ?: return false
            try {
                // The scene's own clear colour: a paper or whiteboard style
                // drawn on black is a different picture, not a letterbox.
                val clear = if (active.background != BLACK) active.background else backgroundColorArgb
                val depth = sink.begin(canvas, widthPx, heightPx, clear)
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
            drawnKey = key
            drawnScene = active
            return true
        }

        private var drawnKey = Frames.UNKNOWN
        private var drawnScene: Frames? = null
        private var prefetchedAt = Int.MIN_VALUE

        /**
         * Pictures due in the next few seconds, decoded now on another thread: decoding one as it first appeared
         * held that frame for tens of milliseconds, and its fade-in visibly caught.
         */
        private fun prefetchImages(active: Frames, index: Int) {
            if (kotlin.math.abs(index - prefetchedAt) < active.fps) return
            prefetchedAt = index
            val ahead = active.imagesBetween(index, index + active.fps * PREFETCH_SECONDS)
            for (src in ahead) sink.prefetch(src, active::imageBytes)
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

private val BLACK = 0xFF000000.toInt()
private const val PREFETCH_SECONDS = 4
