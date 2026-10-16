// Ported from player/android/src/main/kotlin/com/pocketanim/android/PanimView.kt.
//
// PanimAudio API used:
//   AudioClock(sampleRate: Int); .play(); .pause(); .release(); .speed: Float; .problem: String?;
//     .onSystemPause: (() -> Void)?; .positionSeconds() -> Double?
//   NarrationPlayer(source: NarrationSource, format: NarrationFormat, clock: AudioClock); .start(); .stop();
//     .seekTo(_ seconds: Double); .buffering: Bool; .failed: String?; .source
//   NarrationSource.cancel(); NarrationFormat.sampleRate: Int
import PanimAudio
import PanimCore
import QuartzCore
import UIKit

/**
 * A view that plays a lecture.
 *
 * The frame is made and rasterised on a serial queue of its own, never on the main thread: a heavy frame costs tens
 * of milliseconds and would otherwise jank the whole app. A CADisplayLink on the main thread paces it; a tick that
 * finds the last frame still being drawn is dropped, which is what a slow frame should cost.
 */
final class PanimView: UIView {

    private let sink = CGSink()
    private let surface = SurfaceCanvas()
    private let contentLayer = CALayer()
    private let renderQueue = DispatchQueue(label: "panim-render", qos: .userInteractive)
    private var displayLink: CADisplayLink?

    /**
     * Held while a frame is made and drawn. The scene's frames are made by a state machine that only one thread may
     * drive; [release] takes it so no frame is mid-draw when the scene goes.
     */
    private let drawLock = NSLock()

    /** Set by [release], under [drawLock]: no frame is made after it. */
    private var released = false
    /** True while a frame is on the render queue. Main thread only. */
    private var rendering = false
    private var forceRedraw = false
    private var widthPx = 0
    private var heightPx = 0

    /** The picture is never drawn wider than this many pixels per point: CoreGraphics rasterises on the CPU. */
    var maxScale: CGFloat = 2

    var backgroundColorArgb: Int32 = PanimView.BLACK

    private(set) var scene: Frames?
    private(set) var playback: Playback?

    private var audio: NarrationPlayer?
    private var audioClock: AudioClock?

    /** Told (on the main thread) when the system stopped the narration: a call, other audio, headphones out. */
    var onAudioSystemPause: (() -> Void)?

    /**
     * Told (on the main thread) when a frame could not be made or drawn: the frame is dropped either way, but a
     * lecture whose frames all fail was a blank screen with the reason only in the console.
     */
    var onFrameError: ((Int, Error) -> Void)?

    private(set) var framesDrawn: Int64 = 0
    private(set) var framesSkipped: Int64 = 0
    private(set) var lastFrameMillis: Double = 0

    // Render-queue state: what is on screen.
    private var drawnKey = PanimView.UNKNOWN
    private var drawnScene: AnyObject?
    private var prefetchedAt = Int.min

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .black
        isOpaque = true
        contentLayer.contentsGravity = .resize
        contentLayer.backgroundColor = UIColor.black.cgColor
        contentLayer.actions = ["contents": NSNull(), "bounds": NSNull(), "position": NSNull()]
        layer.addSublayer(contentLayer)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    /**
     * Fit the scene's own aspect ratio inside whatever space the view is given.
     *
     * Manim composes for 16:9, so a picture that simply fills a 19.5:9 phone shows a stretched scene -- a circle
     * becomes an ellipse. The view refuses to do it at all rather than each host remembering not to ask.
     */
    override func layoutSubviews() {
        super.layoutSubviews()
        let aspect = CGFloat(FRAME_WIDTH / FRAME_HEIGHT)
        var width = bounds.width
        var height = width / aspect
        if height > bounds.height {
            height = bounds.height
            width = height * aspect
        }
        let fit = CGRect(x: ((bounds.width - width) / 2).rounded(), y: ((bounds.height - height) / 2).rounded(),
                         width: width.rounded(), height: height.rounded())
        contentLayer.frame = fit
        let scale = min(window?.screen.scale ?? UIScreen.main.scale, maxScale)
        let w = Int(fit.width * scale), h = Int(fit.height * scale)
        if w != widthPx || h != heightPx {
            widthPx = w
            heightPx = h
            forceRedraw = true
        }
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        displayLink?.invalidate()
        displayLink = nil
        guard window != nil else { return }
        let link = CADisplayLink(target: DisplayLinkProxy(self), selector: #selector(DisplayLinkProxy.tick))
        if let fps = scene?.fps { pace(link, fps) }
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    private func pace(_ link: CADisplayLink, _ fps: Int) {
        let rate = Float(max(fps, 1))
        link.preferredFrameRateRange = CAFrameRateRange(minimum: min(15, rate), maximum: rate, preferred: rate)
    }

    func load(_ scene: Frames) {
        releaseAudio()
        // A picture another library could not supply may be in this one.
        sink.clearImages()
        self.scene = scene
        let playback = Playback(scene)
        playback.onLoop = { [weak self] index in self?.audio?.seekTo(Double(index) / Double(scene.fps)) }
        self.playback = playback
        if let link = displayLink { pace(link, scene.fps) }
        forceRedraw = true
    }

    /**
     * Attach narration: [source] (a file on the phone, or a stream still arriving) in [format], read off the main
     * thread first (`source.format()` waits for a stream's first bytes). Starts where the picture is, at the
     * picture's speed.
     *
     * Optional by design: a scene routinely plays before its narration exists. Attaching switches the master clock
     * from the system clock to the audio device; until the device reports a position, [AudioClock] returns nil and
     * [Playback] keeps using the system clock, which is what covers the start-up gap.
     */
    func attachAudio(_ source: NarrationSource, _ format: NarrationFormat) {
        releaseAudio()
        let clock = AudioClock(sampleRate: format.sampleRate)
        clock.speed = Float(playback?.speed ?? 1.0)
        clock.onSystemPause = { [weak self] in self?.onAudioSystemPause?() }
        audioClock = clock
        let player = NarrationPlayer(source: source, format: format, clock: clock)
        audio = player
        playback?.audio = NarrationClock(clock)
        let at = playback?.currentFrame() ?? 0
        if let scene = scene, at > 0 { player.seekTo(Double(at) / Double(scene.fps)) }
        if playback?.playing == true {
            clock.play()
            player.start()
        }
    }

    /** Whether the narration is waiting on the network for its next piece (a stream buffering). */
    var audioBuffering: Bool { audio?.buffering == true }

    /** Why the narration cannot play, when it cannot (the picture plays on silent). */
    var audioProblem: String? { audio?.failed ?? audioClock?.problem }

    /** Whether narration is attached. */
    var hasAudio: Bool { audio != nil }

    func play() {
        playback?.play()
        audioClock?.play()
        audio?.start()
    }

    func pause() {
        playback?.pause()
        audioClock?.pause()
    }

    /** Play faster or slower (1.0 as made), the narration's pitch kept. */
    func setSpeed(_ speed: Double) {
        playback?.speed = speed
        audioClock?.speed = Float(playback?.speed ?? speed)
    }

    func seekToFrame(_ index: Int) {
        playback?.seekToFrame(index)
        if let scene = scene { audio?.seekTo(Double(index) / Double(scene.fps)) }
        // Draw the sought frame immediately: a scrub that waits for the next tick to show anything feels broken
        // even when it is only 16 ms.
        requestRedraw()
    }

    private var scrubResume = false

    /**
     * A finger on the seek bar: the picture follows it ([scrubTo]) and the narration waits, paused, to be sought
     * once where the finger lifts ([endScrub]). Seeking the narration at every move asked a stream for a new place
     * dozens of times a second, and the voice stuttered over the drag.
     */
    func beginScrub() {
        scrubResume = playback?.playing == true
        if scrubResume { pause() }
    }

    /** The picture at [index] while scrubbing; the narration is left where it is until [endScrub]. */
    func scrubTo(_ index: Int) {
        playback?.seekToFrame(index)
        requestRedraw()
    }

    /** The finger lifted at [index]: the narration is sought there, and playing goes on if it was playing. */
    func endScrub(_ index: Int) {
        seekToFrame(index)
        if scrubResume { play() }
        scrubResume = false
    }

    /** Call when the player goes: the audio engine outlives the view otherwise. */
    func release() {
        releaseAudio()
        displayLink?.invalidate()
        displayLink = nil
        drawLock.lock()
        released = true
        drawLock.unlock()
    }

    private func releaseAudio() {
        audio?.stop()
        // A stream still arriving stops arriving.
        audio?.source.cancel()
        audio = nil
        audioClock?.release()
        audioClock = nil
        playback?.audio = nil
    }

    private func requestRedraw() {
        forceRedraw = true
        tick()
    }

    // ---- the render loop ------------------------------------------------------------------------------------------

    fileprivate func tick() {
        guard !rendering, !released, let active = scene, let clock = playback, widthPx > 0, heightPx > 0 else { return }
        // frameToDraw returns -1 when the current frame is already on screen, so a paused or slow-moving scene costs
        // nothing.
        var index = clock.frameToDraw()
        if index < 0 {
            if !forceRedraw { return }
            index = clock.currentFrame()
        }
        let redraw = forceRedraw
        forceRedraw = false
        rendering = true
        let width = widthPx, height = heightPx
        let background = backgroundColorArgb
        renderQueue.async { [weak self] in
            guard let self = self else { return }
            let started = DispatchTime.now().uptimeNanoseconds
            var picture: CGImage?
            var failure: Error?
            self.drawLock.lock()
            // Released meanwhile ([release] takes the lock): the scene is gone, nothing is drawn.
            if !self.released {
                self.prefetchImages(active, index)
                do {
                    picture = try self.drawFrame(active, index, redraw, width, height, background)
                } catch {
                    // A frame that cannot be made or drawn is dropped, not the app: the scene starts again from a
                    // kept boundary, and the frame after is drawn whole.
                    failure = error
                    active.recover()
                    self.drawnKey = PanimView.UNKNOWN
                }
            }
            self.drawLock.unlock()
            let millis = Double(DispatchTime.now().uptimeNanoseconds - started) / 1e6
            DispatchQueue.main.async {
                self.rendering = false
                if let error = failure {
                    NSLog("PanimView: frame %d dropped: %@", index, String(describing: error))
                    self.forceRedraw = true
                    self.onFrameError?(index, error)
                    return
                }
                guard let image = picture else { return }
                self.contentLayer.contents = image
                self.lastFrameMillis = millis
                self.framesDrawn += 1
                // Frames the clock moved past while this one was being drawn: dropping frames is survivable, and
                // counting them is how we find out.
                if let now = self.playback?.currentFrame(), now > index + 1 {
                    self.framesSkipped += Int64(now - index - 1)
                }
            }
        }
    }

    /** Frame [index] as a picture; nil when it was not drawn (the same picture as on screen, or nothing to draw on). */
    private func drawFrame(_ active: Frames, _ index: Int, _ redraw: Bool, _ width: Int, _ height: Int,
                           _ background: Int32) throws -> CGImage? {
        // A lecture is mostly holds: a frame that shows what is already on screen is not drawn again.
        let key = try active.contentKey(index)
        if !redraw && key != PanimView.UNKNOWN && key == drawnKey && drawnScene === (active as AnyObject) {
            return nil
        }
        guard let context = surface.acquire(width, height) else { return nil }
        // The scene's own clear colour: a paper or whiteboard style drawn on black is a different picture, not a
        // letterbox.
        let clear = active.background != PanimView.BLACK ? active.background : background
        sink.begin(context, width, height, clear)
        defer { sink.end() }
        // Options, not defaults: the only one that depends on the target is level of detail, and half a pixel is a
        // promise about pixels rather than about scene units.
        try Renderer.drawFrame(active, index, sink, RenderOptions.forSurface(width))
        drawnKey = key
        drawnScene = active as AnyObject
        return surface.release(context)
    }

    /**
     * Pictures due in the next few seconds, decoded now on another queue: decoding one as it first appeared held
     * that frame for tens of milliseconds, and its fade-in visibly caught.
     */
    private func prefetchImages(_ active: Frames, _ index: Int) {
        if prefetchedAt != Int.min && abs(index - prefetchedAt) < active.fps { return }
        prefetchedAt = index
        let ahead = active.imagesBetween(index, index + active.fps * PanimView.PREFETCH_SECONDS)
        for src in ahead { sink.prefetch(src) { [weak active] in active?.imageBytes($0) } }
    }

    static let BLACK = Int32(bitPattern: 0xFF00_0000)
    static let UNKNOWN = FramesConstants.UNKNOWN
    private static let PREFETCH_SECONDS = 4
}

/** CADisplayLink holds its target strongly; the view is held weakly through this. */
private final class DisplayLinkProxy: NSObject {
    private weak var view: PanimView?
    init(_ view: PanimView) { self.view = view }
    @objc func tick() { view?.tick() }
}

/**
 * PanimAudio's [AudioClock] as PanimCore's [TimeSource] (PanimAudio does not depend on PanimCore, so the clock
 * cannot say so itself). Its position is nil before the device reports one, mid-seek and while paused, which makes
 * [Playback] fall back to the system clock for exactly those windows.
 */
private final class NarrationClock: TimeSource {
    private weak var clock: AudioClock?
    init(_ clock: AudioClock) { self.clock = clock }
    func positionSeconds() -> Double? { clock?.positionSeconds() }
}
