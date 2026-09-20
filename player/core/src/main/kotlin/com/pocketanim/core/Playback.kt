package com.pocketanim.core

/**
 * Where playback thinks it is.
 *
 * Audio is the master clock whenever audio is playing: a frame dropped under
 * CPU contention is invisible, a half-second of drifting narration is not. When
 * there is no audio, or the audio device has not started producing positions
 * yet, this falls back to the system clock -- silent scenes must still play at
 * the right speed, and a clock that returns nothing is worse than one that is
 * merely not authoritative.
 */
interface TimeSource {
    /** Seconds of media played, or null when this source cannot answer yet. */
    fun positionSeconds(): Double?
}

/** Monotonic wall clock, used when audio cannot say where it is. */
class SystemTimeSource(private val nanos: () -> Long = System::nanoTime) : TimeSource {
    private var origin: Long? = null
    private var accumulated = 0.0

    fun start() { if (origin == null) origin = nanos() }

    fun pause() {
        origin?.let { accumulated += (nanos() - it) / 1e9 }
        origin = null
    }

    fun seekTo(seconds: Double) {
        accumulated = seconds
        if (origin != null) origin = nanos()
    }

    override fun positionSeconds(): Double =
        accumulated + (origin?.let { (nanos() - it) / 1e9 } ?: 0.0)
}

/**
 * Drives frame selection from a clock.
 *
 * Deliberately stateless about *rendering*: it answers "which frame should be
 * on screen now", and the view decides whether that is worth a redraw. Seeking
 * is exact rather than approximate because keyframes carry absolute values (see
 * [Scene.frame]), so this can jump anywhere without replaying from zero.
 */
class Playback(
    private val scene: Frames,
    private val system: SystemTimeSource = SystemTimeSource(),
) {
    /** Set once audio is running; cleared for silent scenes. */
    var audio: TimeSource? = null

    var looping = false
    var playing = false
        private set

    private var lastFrame = -1

    val frameCount: Int get() = scene.frameCount
    val durationSeconds: Double get() = scene.frameCount.toDouble() / scene.fps

    fun play() {
        playing = true
        system.start()
    }

    fun pause() {
        playing = false
        system.pause()
    }

    fun seekToFrame(index: Int) {
        val clamped = index.coerceIn(0, scene.frameCount - 1)
        system.seekTo(clamped.toDouble() / scene.fps)
        lastFrame = -1
    }

    /**
     * The frame index for now. Audio wins when it can answer; otherwise the
     * system clock does, which is also what happens for the first few calls
     * before an AudioTrack reports a position.
     */
    fun currentFrame(): Int {
        val seconds = audio?.positionSeconds() ?: system.positionSeconds()
        var index = (seconds * scene.fps).toInt()
        if (index >= scene.frameCount) {
            if (looping && scene.frameCount > 0) {
                index %= scene.frameCount
            } else {
                index = scene.frameCount - 1
                playing = false
            }
        }
        return index.coerceAtLeast(0)
    }

    /** The frame to draw, or -1 when the last drawn frame is still current. */
    fun frameToDraw(): Int {
        val index = currentFrame()
        if (index == lastFrame) return -1
        lastFrame = index
        return index
    }
}
