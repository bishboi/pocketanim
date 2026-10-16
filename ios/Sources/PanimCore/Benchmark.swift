// Ported from player/core/src/main/kotlin/com/pocketanim/core/Benchmark.kt.
import Foundation

/**
 * The measurement issue #6 asks for, as a function of the real player.
 *
 * Two questions, and they are not the same question:
 *
 *  - **Can it keep up?** Render every frame at the scene's own rate and count
 *    the ones that arrive late. This is the verdict on live rendering.
 *  - **How much headroom is there?** Render as fast as possible and take the
 *    distribution of frame times. A mean says almost nothing here: dropping one
 *    frame in fifty is invisible, and the same mean with a fat tail is a visible
 *    stutter every second. So the report leads with p95 and p99.
 *
 * Geometry is timed separately from rasterisation by running the same frame
 * through a sink that counts and draws nothing. On a phone the ratio is the
 * whole answer, because it says whether to attack the maths or the draw calls.
 */
public final class SceneResult {
    public let name: String
    public let tier: Int
    public let frames: Int
    public let fps: Int
    /** Sorted frame times in milliseconds, full render including rasterisation. */
    public let renderMs: [Double]
    /** Sorted frame times for geometry alone, no rasterisation. */
    public let geometryMs: [Double]
    public let lateFrames: Int
    public let pacedFrames: Int
    public let drawsPerFrame: Double
    public let verbsPerFrame: Double
    public let maxPathVerbs: Int
    public let error: String?
    /** Which option set produced this row, when the run was a sweep. */
    public let variant: String?

    public init(
        name: String, tier: Int, frames: Int, fps: Int, renderMs: [Double], geometryMs: [Double], lateFrames: Int,
        pacedFrames: Int, drawsPerFrame: Double, verbsPerFrame: Double, maxPathVerbs: Int, error: String? = nil,
        variant: String? = nil
    ) {
        self.name = name
        self.tier = tier
        self.frames = frames
        self.fps = fps
        self.renderMs = renderMs
        self.geometryMs = geometryMs
        self.lateFrames = lateFrames
        self.pacedFrames = pacedFrames
        self.drawsPerFrame = drawsPerFrame
        self.verbsPerFrame = verbsPerFrame
        self.maxPathVerbs = maxPathVerbs
        self.error = error
        self.variant = variant
    }

    private func percentile(_ sorted: [Double], _ p: Double) -> Double {
        if sorted.isEmpty { return 0.0 }
        let index = coerceIn(kToInt(Double(sorted.count - 1) * p), 0, sorted.count - 1)
        return sorted[index]
    }

    public var renderP50: Double { percentile(renderMs, 0.50) }
    public var renderP95: Double { percentile(renderMs, 0.95) }
    public var renderP99: Double { percentile(renderMs, 0.99) }
    public var geometryP50: Double { percentile(geometryMs, 0.50) }

    /** The frame budget this scene declares for itself. */
    public var budgetMs: Double { 1000.0 / Double(fps) }
    public var lateShare: Double { pacedFrames > 0 ? Double(lateFrames) / Double(pacedFrames) : 0.0 }

    /** The headline: can this scene play at its own rate on this device? */
    public var verdict: String {
        if error != nil { return "ERROR" }
        if lateShare <= 0.01 { return "PASS" }
        if lateShare <= 0.05 { return "MARGINAL" }
        return "FAIL"
    }

    public func toJson() -> String {
        var out = "{"
        out += "\"scene\":\"\(name)\",\"tier\":\(tier),\"frames\":\(frames),\"fps\":\(fps),"
        if let variant = variant { out += "\"variant\":\"\(variant)\"," }
        if let error = error {
            out += "\"error\":\"\(error.replacingOccurrences(of: "\"", with: "'"))\"}"
            return out
        }
        out += JavaFormat.format("\"render_p50_ms\":%.3f,", .double(renderP50))
        out += JavaFormat.format("\"render_p95_ms\":%.3f,", .double(renderP95))
        out += JavaFormat.format("\"render_p99_ms\":%.3f,", .double(renderP99))
        out += JavaFormat.format("\"geometry_p50_ms\":%.3f,", .double(geometryP50))
        out += JavaFormat.format("\"budget_ms\":%.3f,", .double(budgetMs))
        out += "\"paced_frames\":\(pacedFrames),\"late_frames\":\(lateFrames),"
        out += JavaFormat.format("\"late_share\":%.4f,", .double(lateShare))
        out += JavaFormat.format("\"draws_per_frame\":%.1f,", .double(drawsPerFrame))
        out += JavaFormat.format("\"verbs_per_frame\":%.1f,", .double(verbsPerFrame))
        out += "\"max_path_verbs\":\(maxPathVerbs),"
        out += "\"verdict\":\"\(verdict)\"}"
        return out
    }

    public func toLine() -> String {
        let label = variant == nil ? name : "\(name)/\(variant!)"
        if let error = error {
            return JavaFormat.format("%-20s ERROR  %s", .string(label), .string(error))
        }
        return JavaFormat.format(
            "%-20s %-8s p50 %6.2f  p95 %6.2f  p99 %6.2f ms   late %4d/%4d (%5.1f%%)   " +
                "geom %5.2f   draws %6.0f   verbs %7.0f   maxpath %5d",
            .string(label), .string(verdict), .double(renderP50), .double(renderP95), .double(renderP99),
            .int(Int64(lateFrames)), .int(Int64(pacedFrames)), .double(lateShare * 100), .double(geometryP50),
            .double(drawsPerFrame), .double(verbsPerFrame), .int(Int64(maxPathVerbs))
        )
    }
}

/**
 * Where a frame goes.
 *
 * The caller owns the surface lifecycle -- locking a canvas, handing over a
 * sink, posting it -- because acquiring and presenting a buffer is a real part
 * of the per-frame cost and a benchmark that skipped it would measure half the
 * pipeline. It is a protocol so a desktop harness can run the same procedure.
 */
public protocol FrameTarget: AnyObject {
    /** Acquire a surface, pass a sink to [draw], present the result. */
    func render(_ draw: (PathSink) throws -> Void) rethrows
}

/**
 * Runs one scene. Platform-free so a desktop harness can run the identical
 * procedure -- a device number is only meaningful next to one from somewhere
 * else, and they have to be measured the same way to be comparable.
 */
public enum Benchmark {

    /** How many frames to render before timing, so caches settle. */
    private static let WARMUP_FRAMES = 30

    /**
     * The option sets a sweep runs, each turning off exactly one thing.
     *
     * Every entry after the first is a trade that measured well somewhere and
     * had to be taken on trust on a phone. Rasterisers differ enough that trust
     * is not good enough.
     *
     * A row whose option does not apply to the scene -- a 3D-only one on a 2D
     * scene -- is the run's own control: it does identical work to the first
     * row, so the gap between them is the noise floor everything else has to
     * clear.
     */
    public static func variants(_ widthPx: Int) -> [(String, RenderOptions)] {
        let shipping = RenderOptions.forSurface(widthPx)
        func of(
            cull: Bool = shipping.cull,
            lines: Bool = shipping.lines,
            backface: Bool = shipping.backface,
            roundJoins: Bool = shipping.roundJoins,
            mergeTranslucent: Bool = shipping.mergeTranslucent,
            lodTolerance: Float = shipping.lodTolerance,
            mergeVerbs: Int = shipping.mergeVerbs
        ) -> RenderOptions {
            RenderOptions(cull: cull, lines: lines, backface: backface, roundJoins: roundJoins,
                          mergeTranslucent: mergeTranslucent, lodTolerance: lodTolerance, mergeVerbs: mergeVerbs)
        }

        return [
            ("all", shipping),
            ("no-lines", of(lines: false)),
            ("no-cull", of(cull: false)),
            ("no-merge", of(mergeVerbs: 0)),
            ("no-backface", of(backface: false)),
            ("bevel", of(roundJoins: false)),
            ("no-merge-fade", of(mergeTranslucent: false)),
            ("no-lod", of(lodTolerance: 0)),
            ("lod-1px", RenderOptions.forSurface(widthPx, errorPx: 1)),
        ]
    }

    public static func run(
        name: String,
        tier: Int,
        scene: Frames,
        target: FrameTarget,
        nanos: () -> Int64 = systemNanos,
        sleep: (Int64) -> Void = { ms in Thread.sleep(forTimeInterval: Double(ms) / 1000.0) },
        options: RenderOptions = RenderOptions.DEFAULT,
        variant: String? = nil
    ) throws -> SceneResult {
        let counter = CountingSink()
        let total = scene.frameCount
        if total == 0 {
            return SceneResult(name: name, tier: tier, frames: 0, fps: 30, renderMs: [], geometryMs: [], lateFrames: 0,
                               pacedFrames: 0, drawsPerFrame: 0, verbsPerFrame: 0, maxPathVerbs: 0)
        }

        // Warm up. The first frames of a scene are also the cheapest -- nothing
        // is on stage yet -- so warming up on frame 0 would flatter everything
        // after it. Sample across the timeline instead.
        for i in 0..<WARMUP_FRAMES {
            let frame = Int(Int64(i) * Int64(total) / Int64(WARMUP_FRAMES))
            try target.render { sink in try Renderer.drawFrame(scene, frame, sink, options) }
        }
        counter.reset()

        // Pass 1: geometry only. No canvas, no rasterisation -- decode,
        // transform, project, depth sort, shade, and walk the paths.
        var geometry = [Double](repeating: 0, count: total)
        for i in 0..<total {
            let started = nanos()
            try Renderer.drawFrame(scene, i, counter, options)
            geometry[i] = Double(nanos() - started) / 1e6
        }
        let drawsPerFrame = Double(counter.draws) / Double(total)
        let verbsPerFrame = Double(counter.verbs) / Double(total)
        let maxPathVerbs = counter.maxPathVerbs

        // Pass 2: unpaced, full render through the surface. The ceiling.
        var render = [Double](repeating: 0, count: total)
        for i in 0..<total {
            let started = nanos()
            try target.render { sink in try Renderer.drawFrame(scene, i, sink, options) }
            render[i] = Double(nanos() - started) / 1e6
        }

        // Pass 3: paced at the scene's own rate. The verdict.
        //
        // A frame is late if it was not presented by the time the next one was
        // due. Deadlines come from a fixed origin rather than accumulating per
        // frame, so one slow frame cannot silently move every later deadline --
        // which would report permanently-behind playback as perfectly fine.
        let budgetNs = 1_000_000_000 / Int64(scene.fps)
        var late = 0
        let origin = nanos()
        for i in 0..<total {
            let due = origin + Int64(i) * budgetNs
            let now = nanos()
            if now < due {
                let waitMs = (due - now) / 1_000_000
                if waitMs > 0 { sleep(waitMs) }
            }
            try target.render { sink in try Renderer.drawFrame(scene, i, sink, options) }
            if nanos() > due + budgetNs { late += 1 }
        }

        return SceneResult(
            name: name,
            tier: tier,
            frames: total,
            fps: scene.fps,
            renderMs: render.sorted(),
            geometryMs: geometry.sorted(),
            lateFrames: late,
            pacedFrames: total,
            drawsPerFrame: drawsPerFrame,
            verbsPerFrame: verbsPerFrame,
            maxPathVerbs: maxPathVerbs,
            variant: variant
        )
    }

    public static func failed(_ name: String, _ tier: Int, _ reason: String) -> SceneResult {
        SceneResult(name: name, tier: tier, frames: 0, fps: 30, renderMs: [], geometryMs: [], lateFrames: 0,
                    pacedFrames: 0, drawsPerFrame: 0, verbsPerFrame: 0, maxPathVerbs: 0, error: reason)
    }
}
