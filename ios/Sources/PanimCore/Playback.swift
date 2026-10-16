// Ported from player/core/src/main/kotlin/com/pocketanim/core/Playback.kt.
import Foundation

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
public protocol TimeSource: AnyObject {
    /** Seconds of media played, or nil when this source cannot answer yet. */
    func positionSeconds() -> Double?
}

/** A [TimeSource] from a closure, as Kotlin's `fun interface` lets a lambda be one. */
public final class TimeSourceFunction: TimeSource {
    private let body: () -> Double?
    public init(_ body: @escaping () -> Double?) { self.body = body }
    public func positionSeconds() -> Double? { body() }
}

/** The monotonic clock in nanoseconds, as System.nanoTime. */
public func systemNanos() -> Int64 { Int64(bitPattern: DispatchTime.now().uptimeNanoseconds) }

/**
 * Monotonic wall clock, used when audio cannot say where it is.
 *
 * Kotlin declares it a TimeSource whose answer is never null; Swift will not let a non-optional answer stand for
 * the protocol's optional one, and nothing hands this clock out as a TimeSource, so it is a plain class here and
 * [positionSeconds] answers a Double.
 */
public final class SystemTimeSource {
    private let nanos: () -> Int64
    private var origin: Int64? = nil
    private var accumulated = 0.0

    public init(_ nanos: @escaping () -> Int64 = systemNanos) {
        self.nanos = nanos
    }

    /** Media seconds per wall-clock second: 1.5 plays a lecture half as fast again. */
    public var speed: Double = 1.0 {
        willSet {
            // What has played so far at the old speed is kept; the new one counts from now.
            if let it = origin {
                let now = nanos()
                accumulated += Double(now - it) / 1e9 * speed
                origin = now
            }
        }
    }

    public func start() { if origin == nil { origin = nanos() } }

    public func pause() {
        if let it = origin { accumulated += Double(nanos() - it) / 1e9 * speed }
        origin = nil
    }

    public func seekTo(_ seconds: Double) {
        accumulated = seconds
        if origin != nil { origin = nanos() }
    }

    public func positionSeconds() -> Double {
        accumulated + (origin.map { Double(nanos() - $0) / 1e9 * speed } ?? 0.0)
    }
}

/**
 * Drives frame selection from a clock.
 *
 * Deliberately stateless about *rendering*: it answers "which frame should be
 * on screen now", and the view decides whether that is worth a redraw. Seeking
 * is exact rather than approximate because keyframes carry absolute values (see
 * [Scene.frame]), so this can jump anywhere without replaying from zero.
 *
 * Not synchronised: Kotlin marks [shown] volatile so the UI thread reads what the render thread wrote; on iOS
 * the display link and the controls share the main thread, and a caller that splits them must serialise calls.
 */
public final class Playback {
    private let scene: Frames
    private let system: SystemTimeSource

    public init(_ scene: Frames, _ system: SystemTimeSource = SystemTimeSource()) {
        self.scene = scene
        self.system = system
    }

    /** Set once audio is running; cleared for silent scenes. */
    public var audio: TimeSource? = nil

    public var looping = false
    public private(set) var playing = false

    /**
     * Called with the frame playback wrapped to when a looping scene passes
     * its end. The picture wraps by itself; narration has to be told, or it
     * plays on past the end (and as the master clock, holds the picture there).
     */
    public var onLoop: ((Int) -> Void)? = nil

    private var lastFrame = -1

    public var frameCount: Int { scene.frameCount }
    public var durationSeconds: Double { Double(scene.frameCount) / Double(scene.fps) }

    /**
     * How fast it plays (1.0 as made). The wall clock runs at it here; narration, when there is some, is sped up by
     * its own player (pitch kept) and, being the master clock, carries the picture with it.
     */
    public var speed: Double {
        get { system.speed }
        set { system.speed = Swift.min(Swift.max(newValue, 0.25), 3.0) }
    }

    public func play() {
        playing = true
        system.start()
    }

    public func pause() {
        playing = false
        system.pause()
        // Paused where the picture is, so playing on starts from the frame on screen.
        if shown >= 0 { system.seekTo(Double(shown) / Double(scene.fps)) }
        shown = -1
    }

    public func seekToFrame(_ index: Int) {
        let clamped = coerceIn(index, 0, scene.frameCount - 1)
        system.seekTo(Double(clamped) / Double(scene.fps))
        lastFrame = -1
        shown = -1
    }

    /** The latest frame given while playing, since the last seek: the picture does not step back from it. */
    private var shown = -1

    /**
     * The frame index for now. Audio wins when it can answer; otherwise the
     * system clock does, which is also what happens for the first few calls
     * before an AudioTrack reports a position.
     */
    public func currentFrame() -> Int {
        let seconds = audio?.positionSeconds() ?? system.positionSeconds()
        var index = kToInt(seconds * Double(scene.fps))
        if index >= scene.frameCount {
            if looping && scene.frameCount > 0 {
                index %= scene.frameCount
                // Re-anchor the wall clock at the wrapped frame, so it -- the
                // fallback while audio restarts -- agrees with the picture.
                system.seekTo(Double(index) / Double(scene.fps))
                shown = -1
                onLoop?(index)
            } else {
                index = scene.frameCount - 1
                playing = false
            }
        }
        index = Swift.max(index, 0)
        // Handing the clock from the wall to the narration (it starts a little behind the wall's count after a seek
        // or a pause) and a timestamp's jitter would show as the picture stepping back a frame or a few: a stutter.
        // While playing, the picture holds instead, until the clock passes it; a real step back is only a seek.
        let ahead = shown
        if playing && ahead > index && ahead - index <= scene.fps / 2 { return ahead }
        if playing { shown = index }
        return index
    }

    /** The frame to draw, or -1 when the last drawn frame is still current. */
    public func frameToDraw() -> Int {
        let index = currentFrame()
        if index == lastFrame { return -1 }
        lastFrame = index
        return index
    }
}

/**
 * Kotlin's `coerceIn`, which throws when the range is empty (a scene with no frames asked to seek); here the
 * lower bound wins instead, which is what the player would have shown had it not stopped.
 */
@inline(__always)
func coerceIn(_ value: Int, _ low: Int, _ high: Int) -> Int {
    if value < low { return low }
    if value > high { return Swift.max(high, low) }
    return value
}

@inline(__always)
func coerceIn(_ value: Double, _ low: Double, _ high: Double) -> Double {
    if value < low { return low }
    if value > high { return high }
    return value
}
