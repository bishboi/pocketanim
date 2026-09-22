package com.pocketanim.core

import java.util.Locale

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
 * through a sink that counts and draws nothing. On a desktop that split put 1.7
 * ms/frame of geometry against everything else; on a phone the ratio is the
 * whole answer, because it says whether to attack the maths or the draw calls.
 */
class SceneResult(
    val name: String,
    val tier: Int,
    val frames: Int,
    val fps: Int,
    /** Sorted frame times in milliseconds, full render including rasterisation. */
    val renderMs: DoubleArray,
    /** Sorted frame times for geometry alone, no rasterisation. */
    val geometryMs: DoubleArray,
    val lateFrames: Int,
    val pacedFrames: Int,
    val drawsPerFrame: Double,
    val verbsPerFrame: Double,
    val maxPathVerbs: Int,
    val error: String? = null,
    /** Which option set produced this row, when the run was a sweep. */
    val variant: String? = null,
) {
    private fun percentile(sorted: DoubleArray, p: Double): Double {
        if (sorted.isEmpty()) return 0.0
        val index = ((sorted.size - 1) * p).toInt().coerceIn(0, sorted.size - 1)
        return sorted[index]
    }

    val renderP50 get() = percentile(renderMs, 0.50)
    val renderP95 get() = percentile(renderMs, 0.95)
    val renderP99 get() = percentile(renderMs, 0.99)
    val geometryP50 get() = percentile(geometryMs, 0.50)

    /** The frame budget this scene declares for itself. */
    val budgetMs get() = 1000.0 / fps
    val lateShare get() = if (pacedFrames > 0) lateFrames.toDouble() / pacedFrames else 0.0

    /** The headline: can this scene play at its own rate on this device? */
    val verdict: String
        get() = when {
            error != null -> "ERROR"
            lateShare <= 0.01 -> "PASS"
            lateShare <= 0.05 -> "MARGINAL"
            else -> "FAIL"
        }

    fun toJson(): String = buildString {
        val l = Locale.ROOT
        append("{")
        append("\"scene\":\"$name\",\"tier\":$tier,\"frames\":$frames,\"fps\":$fps,")
        if (variant != null) append("\"variant\":\"$variant\",")
        if (error != null) {
            append("\"error\":\"${error.replace("\"", "'")}\"}")
            return@buildString
        }
        append(String.format(l, "\"render_p50_ms\":%.3f,", renderP50))
        append(String.format(l, "\"render_p95_ms\":%.3f,", renderP95))
        append(String.format(l, "\"render_p99_ms\":%.3f,", renderP99))
        append(String.format(l, "\"geometry_p50_ms\":%.3f,", geometryP50))
        append(String.format(l, "\"budget_ms\":%.3f,", budgetMs))
        append("\"paced_frames\":$pacedFrames,\"late_frames\":$lateFrames,")
        append(String.format(l, "\"late_share\":%.4f,", lateShare))
        append(String.format(l, "\"draws_per_frame\":%.1f,", drawsPerFrame))
        append(String.format(l, "\"verbs_per_frame\":%.1f,", verbsPerFrame))
        append("\"max_path_verbs\":$maxPathVerbs,")
        append("\"verdict\":\"$verdict\"}")
    }

    fun toLine(): String {
        val label = if (variant == null) name else "$name/$variant"
        return if (error != null) {
            String.format(Locale.ROOT, "%-20s ERROR  %s", label, error)
        } else {
            String.format(
                Locale.ROOT,
                "%-20s %-8s p50 %6.2f  p95 %6.2f  p99 %6.2f ms   late %4d/%4d (%5.1f%%)   " +
                    "geom %5.2f   draws %6.0f   verbs %7.0f   maxpath %5d",
                label, verdict, renderP50, renderP95, renderP99,
                lateFrames, pacedFrames, lateShare * 100, geometryP50,
                drawsPerFrame, verbsPerFrame, maxPathVerbs,
            )
        }
    }
}

/**
 * Runs one scene. Platform-free so the desktop harness can run the identical
 * procedure -- a device number is only meaningful next to one from somewhere
 * else, and they have to be measured the same way to be comparable.
 */
/**
 * Where a frame goes.
 *
 * The caller owns the surface lifecycle -- locking a canvas, handing over a
 * sink, posting it -- because acquiring and presenting a buffer is a real part
 * of the per-frame cost and a benchmark that skipped it would measure half the
 * pipeline. It is an interface so the desktop harness can run the same
 * procedure against Java2D.
 */
fun interface FrameTarget {
    /** Acquire a surface, pass a sink to [draw], present the result. */
    fun render(draw: (PathSink) -> Unit)
}

object Benchmark {

    /** How many frames to render before timing, so JIT and caches settle. */
    private const val WARMUP_FRAMES = 30

    /**
     * The option sets a sweep runs, each turning off exactly one thing.
     *
     * Every entry after the first was a change that measured well on a desktop
     * and had to be taken on trust on a phone. Rasterisers differ enough that
     * trust is not good enough -- merging strokes, for one, replaces many small
     * paths with a few that span the screen, and which of those Skia prefers is
     * not something this repository can reason its way to.
     */
    @JvmField
    val VARIANTS: Array<Pair<String, RenderOptions>> = arrayOf(
        "all" to RenderOptions(),
        "no-lines" to RenderOptions(lines = false),
        "no-cull" to RenderOptions(cull = false),
        "no-merge" to RenderOptions(mergeVerbs = 0),
        "no-backface" to RenderOptions(backface = false),
        "opaque-merge" to RenderOptions(mergeTranslucent = false),
        "bevel" to RenderOptions(roundJoins = false),
    )

    @JvmOverloads
    fun run(
        name: String,
        tier: Int,
        scene: Frames,
        target: FrameTarget,
        nanos: () -> Long = System::nanoTime,
        sleep: (Long) -> Unit = { ms -> Thread.sleep(ms) },
        options: RenderOptions = RenderOptions.DEFAULT,
        variant: String? = null,
    ): SceneResult {
        val counter = CountingSink()
        val total = scene.frameCount
        if (total == 0) {
            return SceneResult(name, tier, 0, 30, DoubleArray(0), DoubleArray(0), 0, 0, 0.0, 0.0, 0)
        }

        // Warm up. The first frames of a scene are also the cheapest -- nothing
        // is on stage yet -- so warming up on frame 0 would flatter everything
        // after it. Sample across the timeline instead.
        for (i in 0 until WARMUP_FRAMES) {
            val frame = (i.toLong() * total / WARMUP_FRAMES).toInt()
            target.render { sink -> Renderer.drawFrame(scene, frame, sink, options) }
        }
        counter.reset()

        // Pass 1: geometry only. No canvas, no rasterisation -- decode,
        // transform, project, depth sort, shade, and walk the paths.
        val geometry = DoubleArray(total)
        for (i in 0 until total) {
            val started = nanos()
            Renderer.drawFrame(scene, i, counter, options)
            geometry[i] = (nanos() - started) / 1e6
        }
        val drawsPerFrame = counter.draws.toDouble() / total
        val verbsPerFrame = counter.verbs.toDouble() / total
        val maxPathVerbs = counter.maxPathVerbs

        // Pass 2: unpaced, full render through the surface. The ceiling.
        val render = DoubleArray(total)
        for (i in 0 until total) {
            val started = nanos()
            target.render { sink -> Renderer.drawFrame(scene, i, sink, options) }
            render[i] = (nanos() - started) / 1e6
        }

        // Pass 3: paced at the scene's own rate. The verdict.
        //
        // A frame is late if it was not presented by the time the next one was
        // due. Deadlines come from a fixed origin rather than accumulating per
        // frame, so one slow frame cannot silently move every later deadline --
        // which would report permanently-behind playback as perfectly fine.
        val budgetNs = 1_000_000_000L / scene.fps
        var late = 0
        val origin = nanos()
        for (i in 0 until total) {
            val due = origin + i * budgetNs
            val now = nanos()
            if (now < due) {
                val waitMs = (due - now) / 1_000_000
                if (waitMs > 0) sleep(waitMs)
            }
            target.render { sink -> Renderer.drawFrame(scene, i, sink, options) }
            if (nanos() > due + budgetNs) late++
        }

        return SceneResult(
            name = name,
            tier = tier,
            frames = total,
            fps = scene.fps,
            renderMs = render.sortedArray(),
            geometryMs = geometry.sortedArray(),
            lateFrames = late,
            pacedFrames = total,
            drawsPerFrame = drawsPerFrame,
            verbsPerFrame = verbsPerFrame,
            maxPathVerbs = maxPathVerbs,
            variant = variant,
        )
    }

    fun failed(name: String, tier: Int, reason: String) =
        SceneResult(name, tier, 0, 30, DoubleArray(0), DoubleArray(0), 0, 0, 0.0, 0.0, 0, reason)
}
