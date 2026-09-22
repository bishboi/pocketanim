package com.pocketanim.desktop

import com.pocketanim.core.FRAME_HEIGHT
import com.pocketanim.core.FRAME_WIDTH
import com.pocketanim.core.Panm
import com.pocketanim.core.PathSink
import com.pocketanim.core.RenderOptions
import com.pocketanim.core.Renderer
import com.pocketanim.core.CountingSink
import com.pocketanim.core.Benchmark
import com.pocketanim.core.FrameTarget
import com.pocketanim.core.Frames
import com.pocketanim.core.Library
import com.pocketanim.core.Storage
import com.pocketanim.core.Scene
import com.pocketanim.core.dsl.AssetLoader
import com.pocketanim.core.dsl.Interpreter
import com.pocketanim.core.dsl.Program
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Graphics2D
import java.awt.RenderingHints
import java.awt.geom.Path2D
import java.awt.image.BufferedImage
import java.io.File
import java.util.Locale
import javax.imageio.ImageIO

/**
 * Desktop harness. Not shipped -- this exists so the code that *is* shipped can
 * be run and checked here.
 *
 * The player's core is platform-neutral by construction: the only thing it asks
 * of a platform is [PathSink]. Android supplies one backed by Skia; this one is
 * backed by Java2D. That means the exact renderer that runs on the phone can be
 * executed against exporter/reference_render.py, and any disagreement is about
 * the format or the maths rather than about a rasteriser we cannot run here.
 *
 * What this does *not* prove: that Skia rasterises like Cairo. It cannot, and
 * neither can Java2D -- antialiasing differs between all three. Structural
 * errors (wrong transform, wrong draw order, wrong shade, wrong subpath split)
 * move thousands of pixels and are exactly what this catches.
 */
class Java2DSink(private val g: Graphics2D) : PathSink {
    private val path = Path2D.Float()
    private var join = BasicStroke.JOIN_ROUND

    override fun strokeStyle(round: Boolean) {
        join = if (round) BasicStroke.JOIN_ROUND else BasicStroke.JOIN_BEVEL
    }

    override fun beginPath() {
        path.reset()
    }

    override fun moveTo(x: Float, y: Float) {
        path.moveTo(x.toDouble(), y.toDouble())
    }

    override fun cubicTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float) {
        path.curveTo(
            x1.toDouble(), y1.toDouble(),
            x2.toDouble(), y2.toDouble(),
            x3.toDouble(), y3.toDouble(),
        )
    }

    override fun lineTo(x: Float, y: Float) {
        path.lineTo(x.toDouble(), y.toDouble())
    }

    override fun closeSubpath() {
        path.closePath()
    }

    override fun fillPath(argb: Int) {
        g.color = Color(argb, true)
        g.fill(path)
    }

    override fun strokePath(argb: Int, widthInSceneUnits: Float) {
        g.color = Color(argb, true)
        g.stroke = BasicStroke(widthInSceneUnits, BasicStroke.CAP_ROUND, join)
        g.draw(path)
    }

    override fun fillAndStrokePath(argb: Int, widthInSceneUnits: Float) {
        // Java2D has no combined style, so the oracle side keeps two calls.
        // That is the point of the default: only the sink that gains from one
        // call has to know about it.
        fillPath(argb)
        strokePath(argb, widthInSceneUnits)
    }
}

private fun render(
    scene: Frames,
    index: Int,
    width: Int,
    height: Int,
    options: RenderOptions = RenderOptions.DEFAULT,
): BufferedImage {
    val image = BufferedImage(width, height, BufferedImage.TYPE_INT_RGB)
    val g = image.createGraphics()
    g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
    g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE)
    g.color = Color.BLACK
    g.fillRect(0, 0, width, height)

    // Scene coordinates: y up, origin centred, stroke widths in scene units --
    // the same setup reference_render.py gives Cairo.
    g.translate(width / 2.0, height / 2.0)
    g.scale(width / FRAME_WIDTH.toDouble(), -height / FRAME_HEIGHT.toDouble())

    Renderer.drawFrame(scene, index, Java2DSink(g), options)
    g.dispose()
    return image
}

/** The canonical dump the Java and Python decoders also emit, field for field. */
private fun highestAtlasId(scene: Frames, index: Int): Int {
    var highest = -1
    for (inst in scene.instances(index)) if (inst.atlasId > highest) highest = inst.atlasId
    return highest
}

private fun dump(scene: Frames, probe: Int) {
    val l = Locale.ROOT
    val out = StringBuilder()

    // A computing source has no records array and grows its atlas as it plays,
    // so the header and the per-record lines are gathered by walking frames.
    val perFrame = IntArray(scene.frameCount)
    var atlasSize = 0
    for (i in 0 until scene.frameCount) {
        perFrame[i] = scene.instances(i).size
        atlasSize = maxOf(atlasSize, highestAtlasId(scene, i) + 1)
    }
    // A decoded container always carries a quantisation box in its header, even
    // when it is all zeros -- a text asset has an empty atlas because its
    // glyphs live in the shared library. Testing the values rather than the
    // kind skipped the line for exactly those assets.
    val shapeCount = if (scene is Scene) scene.atlas.size else atlasSize

    if (scene is Scene) {
        out.append(String.format(l, "H %d %d %d %d%n",
            scene.fps, scene.frameCount, shapeCount,
            if (scene.camera(0) != null) 1 else 0))
    } else {
        // Shape count is bookkeeping for a computing source, not content.
        out.append(String.format(l, "H %d %d %d%n",
            scene.fps, scene.frameCount, if (scene.camera(0) != null) 1 else 0))
    }
    if (scene is Scene) {
        out.append(String.format(l, "B %.6f %.6f %.6f %.6f %.6f %.6f%n",
            scene.lo[0], scene.lo[1], scene.lo[2], scene.hi[0], scene.hi[1], scene.hi[2]))
    }

    if (scene is Scene) {
        for (s in scene.atlas.indices) {
            val pts = scene.atlas[s]
            val n = pts.size / 3
            val mean = DoubleArray(3)
            for (i in 0 until n) for (k in 0 until 3) mean[k] += pts[i * 3 + k].toDouble()
            for (k in 0 until 3) mean[k] = if (n > 0) mean[k] / n else 0.0
            out.append(String.format(l, "A %d %d %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f%n",
                s, n,
                if (n > 0) pts[0] else 0f, if (n > 0) pts[1] else 0f, if (n > 0) pts[2] else 0f,
                if (n > 0) pts[(n - 1) * 3] else 0f,
                if (n > 0) pts[(n - 1) * 3 + 1] else 0f,
                if (n > 0) pts[(n - 1) * 3 + 2] else 0f,
                mean[0], mean[1], mean[2]))
        }
    }

    // A decoded container has real record kinds -- snapshot versus keyframe is
    // part of what the decoder cross-check is checking. A computing source has
    // no records at all, so every frame reports as a snapshot.
    for (r in 0 until scene.frameCount) {
        if (scene is Scene) {
            // The record's own payload, not the resolved frame: a keyframe
            // carrying no changes is exactly what the delta encoding is for,
            // and reporting the replayed count would hide it.
            out.append(String.format(l, "R %d %d %d%n",
                r, scene.records[r].kind, scene.records[r].instances.size))
        } else {
            out.append(String.format(l, "R %d %d %d%n", r, 0, perFrame[r]))
        }
    }

    scene.camera(probe)?.let { camera ->
        out.append("C ").append(probe)
        for (v in camera) out.append(String.format(l, " %.6f", v))
        out.append('\n')
    }

    val frame = scene.instances(probe)
    out.append(String.format(l, "F %d %d%n", probe, frame.size))
    for (i in frame.indices) {
        val inst = frame[i]
        // A computing source allocates atlas ids as it goes and reuses them
        // once transient reveal geometry is wound back, so the id itself is
        // bookkeeping rather than meaning. What must agree across
        // implementations is the geometry the id resolves to.
        // Only a computing source is asked for geometry here. A decoded text
        // asset carries an empty atlas on purpose -- its glyphs live in the
        // shared library -- so resolving the id would fail and mean nothing.
        if (scene !is Scene) {
            val pts = scene.shape(inst.atlasId)
            val n = pts.size / 3
            // Only for a computing source: it allocates atlas ids as it goes and
            // reuses them once transient reveal geometry is wound back, so the id
            // is bookkeeping. What must agree is the geometry it resolves to.
            val mean = DoubleArray(3)
            for (q in 0 until n) for (k in 0 until 3) mean[k] += pts[q * 3 + k].toDouble()
            for (k in 0 until 3) mean[k] = if (n > 0) mean[k] / n else 0.0
            out.append(String.format(l, "G %d %d %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f%n",
                i, n,
                if (n > 0) pts[0] else 0f, if (n > 0) pts[1] else 0f, if (n > 0) pts[2] else 0f,
                if (n > 0) pts[(n - 1) * 3] else 0f,
                if (n > 0) pts[(n - 1) * 3 + 1] else 0f,
                if (n > 0) pts[(n - 1) * 3 + 2] else 0f,
                mean[0], mean[1], mean[2]))
            out.append(String.format(l, "I %d %d %d %d", i, inst.slot, n, inst.flags))
        } else {
            out.append(String.format(l, "I %d %d %d %d", i, inst.slot, inst.atlasId, inst.flags))
        }
        for (row in 0 until 3) for (col in 0 until 4) {
            out.append(String.format(l, " %.6f", inst.transform[row * 4 + col]))
        }
        for (c in intArrayOf(inst.fill, inst.stroke)) {
            out.append(" ").append((c shr 16) and 0xFF)
            out.append(" ").append((c shr 8) and 0xFF)
            out.append(" ").append(c and 0xFF)
            out.append(" ").append((c ushr 24) and 0xFF)
        }
        out.append(String.format(l, " %.6f", inst.strokeWidth))
        inst.normal?.let { for (k in 0 until 3) out.append(String.format(l, " %.6f", it[k])) }
        out.append('\n')
    }
    print(out)
}

/**
 * Time a straight run through every frame, with no clock and no display.
 *
 * This is not the device gate -- a desktop CPU says nothing about a low-end
 * phone, and Java2D is not Skia. It measures the part that is the same on both:
 * decode, transform, project, depth sort, shade, and walk the paths.
 */
private fun benchmark(scene: Frames, width: Int, height: Int) {
    // Two different numbers, and they answer different questions.
    //
    // Skia's kMaxGPUPathRendererVerbs cliff is per *path*: a single path over
    // 16,384 verbs falls back to CPU rasterisation. So maxPathVerbs is the one
    // that decides whether that fallback fires.
    //
    // Verbs and draws per frame are throughput, not a cliff: they say how much
    // work the rasteriser is handed and how many draw calls it costs.
    // CountingSink rather than a copy of it: a second implementation drifted
    // from the first the moment the sink grew a combined fill-and-stroke, and
    // this harness went on reporting two draws where the device now issues one.
    val sink = CountingSink()

    repeat(2) { for (i in 0 until scene.frameCount) Renderer.drawFrame(scene, i, sink) } // warm up
    sink.reset()

    val started = System.nanoTime()
    for (i in 0 until scene.frameCount) Renderer.drawFrame(scene, i, sink)
    val elapsed = (System.nanoTime() - started) / 1e9

    val perFrame = elapsed / scene.frameCount * 1000.0
    println(String.format(Locale.ROOT, "frames          %d", scene.frameCount))
    println(String.format(Locale.ROOT, "geometry ms/fr  %.3f", perFrame))
    println(String.format(Locale.ROOT, "verbs/frame     %.0f", sink.verbs.toDouble() / scene.frameCount))
    println(String.format(Locale.ROOT, "draws/frame     %.0f", sink.draws.toDouble() / scene.frameCount))
    println(String.format(Locale.ROOT, "max verbs/path  %d", sink.maxPathVerbs))
    println(String.format(Locale.ROOT, "budget at 30fps %.1f%% (geometry only, desktop)",
        perFrame / (1000.0 / scene.fps) * 100.0))

    // What each of the renderer's trades is worth, in the two numbers that
    // travel between rasterisers. The milliseconds do not travel; the counts
    // do, and on the device the sweep is run against a real surface.
    println()
    println(String.format(Locale.ROOT, "%-10s %10s %10s %10s", "variant", "verbs/fr", "draws/fr", "maxpath"))
    for ((label, options) in Benchmark.variants(width / FRAME_WIDTH)) {
        val counter = CountingSink()
        for (i in 0 until scene.frameCount) Renderer.drawFrame(scene, i, counter, options)
        println(String.format(
            Locale.ROOT, "%-10s %10.0f %10.0f %10d",
            label,
            counter.verbs.toDouble() / scene.frameCount,
            counter.draws.toDouble() / scene.frameCount,
            counter.maxPathVerbs,
        ))
    }
}

/**
 * Assets off the filesystem, laid out as the exporter writes them.
 *
 * On Android this is backed by app storage and a content-addressed cache; the
 * shape of the interface is the same because the interpreter must not care.
 */
private class FileAssets(private val root: File) : AssetLoader {
    override fun asset(id: String) = File(root, "assets/$id.panm").readBytes()
    override fun glyphLibrary() = File(root, "library.atlas").readBytes()
}

/**
 * Load either tier. A `.panim` is a program and is expanded here, exactly as
 * the device would; a `.panm` is already sampled frames. Past this point
 * nothing downstream can tell which tier it is looking at, which is the whole
 * point of the interpreter producing a [Scene].
 */
private fun load(path: File): Frames =
    if (path.name.endsWith(".panim")) {
        Interpreter.open(Program.parse(path.readText()), FileAssets(path.parentFile))
    } else {
        Scene.parse(path.readBytes())
    }

/**
 * Seeking must be exact, not approximate.
 *
 * A computing source rebuilds a frame from a checkpoint and replays forward, so
 * "the frame you get" could depend on how you arrived at it. That would show up
 * as a scrub that renders subtly differently from playback -- the kind of bug
 * that survives a fidelity harness, because a harness plays forward.
 *
 * Every frame is digested during a forward pass, then re-requested backwards,
 * shuffled, and with repeats. Any disagreement is a state leak between frames.
 */
private fun seekTest(scene: Frames): Boolean {
    val shapeCount = if (scene is Scene) scene.atlas.size else Int.MAX_VALUE

    fun digest(index: Int): Long {
        var h = 1125899906842597L
        for (inst in scene.instances(index)) {
            h = h * 31 + inst.slot
            h = h * 31 + inst.flags
            h = h * 31 + inst.fill
            h = h * 31 + inst.stroke
            h = h * 31 + inst.strokeWidth.toRawBits()
            for (v in inst.transform) h = h * 31 + v.toRawBits()
            inst.normal?.forEach { h = h * 31 + it.toRawBits() }
            // Geometry too: the atlas is rebuilt on seek, so an id alone would
            // not notice if it came back pointing at different points.
            //
            // Absent for a text asset decoded on its own: its instances index
            // the shared glyph library, so it carries an empty atlas and the id
            // resolves to nothing. That is a fragment rather than a scene, and
            // the ids are still worth checking even when the geometry is not.
            val pts = if (inst.atlasId < shapeCount) scene.shape(inst.atlasId) else FloatArray(0)
            h = h * 31 + pts.size
            if (pts.isNotEmpty()) {
                h = h * 31 + pts[0].toRawBits()
                h = h * 31 + pts[pts.size - 1].toRawBits()
            }
        }
        scene.camera(index)?.forEach { h = h * 31 + it.toRawBits() }
        return h
    }

    val forward = LongArray(scene.frameCount) { digest(it) }

    val orders = listOf(
        "reverse" to (scene.frameCount - 1 downTo 0).toList(),
        "shuffled" to (0 until scene.frameCount).shuffled(java.util.Random(7).let { r ->
            kotlin.random.Random(7)
        }),
        "repeated" to (0 until scene.frameCount).flatMap { listOf(it, it) },
        "ends" to (0 until scene.frameCount).flatMap { listOf(it, 0, scene.frameCount - 1) },
    )

    var failures = 0
    for ((name, order) in orders) {
        var bad = 0
        var firstBad = -1
        for (index in order) {
            if (digest(index) != forward[index]) {
                bad++
                if (firstBad < 0) firstBad = index
            }
        }
        if (bad > 0) {
            failures++
            println("  FAIL $name: $bad/${order.size} frames differ, first at $firstBad")
        } else {
            println("  ok   $name: ${order.size} requests match the forward pass")
        }
    }
    return failures == 0
}

/** [Storage] over a directory, which is what app storage will look like. */
private class DirStorage(private val root: File) : Storage {
    override fun exists(path: String) = File(root, path).exists()
    override fun read(path: String) = File(root, path).readBytes()
    override fun sizeOf(path: String) = File(root, path).length()
}

/**
 * Open every scene the way the device will: through the manifest, not by
 * knowing where files live. This is the check that the library is actually
 * self-describing rather than a directory the harness happens to understand.
 */
private fun libraryReport(root: File): Boolean {
    val library = Library.load(DirStorage(root))
    val missing = library.missing()
    if (missing.isNotEmpty()) {
        println("missing ${missing.size} path(s): ${missing.take(5)}")
        return false
    }

    // Digests as well as sizes: a download that truncates is caught by size,
    // but one that corrupts a block in place is not, and the symptom of the
    // second is geometry that decodes and draws the wrong picture.
    val problems = library.checkIntegrity(verifyDigests = true)
    if (problems.isNotEmpty()) {
        println("integrity: ${problems.size} problem(s)")
        problems.take(5).forEach { println("  $it") }
        return false
    }
    println("integrity: ${library.assets.size} files match the manifest")

    println(String.format("%-22s %5s %7s %8s %9s  %s", "scene", "tier", "frames", "bytes", "instances", "status"))
    var failures = 0
    for (entry in library.scenes) {
        if (!library.isPlayable(entry)) {
            println(String.format("%-22s %5d %7d %8d %9s  NOT PLAYABLE", entry.name, entry.tier, entry.frames, entry.playableBytes, "-"))
            failures++
            continue
        }
        val status = try {
            val frames = library.open(entry.name)
            // Touch both ends and the middle: enough to prove assets resolved
            // and the timeline runs, without rendering the whole scene.
            var seen = 0L
            for (i in intArrayOf(0, frames.frameCount / 2, frames.frameCount - 1)) {
                seen += frames.instances(i).size
            }
            println(String.format("%-22s %5d %7d %8d %9d  ok", entry.name, entry.tier,
                frames.frameCount, entry.playableBytes, seen))
            null
        } catch (e: Exception) {
            failures++
            "${e::class.simpleName}: ${e.message}"
        }
        if (status != null) println(String.format("%-22s %5d %7d %8d %9s  FAIL %s",
            entry.name, entry.tier, entry.frames, entry.playableBytes, "-", status))
    }
    return failures == 0
}

/**
 * The device benchmark, run here.
 *
 * Identical procedure to the one the phone runs -- same warm-up, same three
 * passes, same percentiles -- against Java2D instead of Skia. That is the point:
 * a frame time from a phone means little alone, and means a lot next to one
 * measured the same way on hardware you understand.
 *
 * It is a reference, not a prediction. Java2D is not Skia and a desktop CPU is
 * not a phone SoC; what transfers is the *shape* -- which scenes are expensive,
 * and how much of their cost is geometry rather than rasterisation.
 */
private fun deviceBenchmark(root: File, only: List<String>?) {
    val library = Library.load(DirStorage(root))
    val missing = library.missing()
    if (missing.isNotEmpty()) {
        println("library incomplete, ${missing.size} path(s) missing")
        return
    }

    val width = 1280
    val height = 720
    val image = BufferedImage(width, height, BufferedImage.TYPE_INT_RGB)

    val target = FrameTarget { draw ->
        val g = image.createGraphics()
        try {
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE)
            g.color = Color.BLACK
            g.fillRect(0, 0, width, height)
            g.translate(width / 2.0, height / 2.0)
            g.scale(width / FRAME_WIDTH.toDouble(), -height / FRAME_HEIGHT.toDouble())
            draw(Java2DSink(g))
        } finally {
            g.dispose()
        }
    }

    println("desktop reference, ${width}x$height, Java2D")
    val scenes = library.scenes.filter { only == null || it.name in only }
    for (entry in scenes) {
        val result = try {
            Benchmark.run(entry.name, entry.tier, library.open(entry.name), target)
        } catch (e: Throwable) {
            Benchmark.failed(entry.name, entry.tier, "${e::class.simpleName}: ${e.message}")
        }
        println(result.toLine())
    }
}

fun main(args: Array<String>) {
    if (args.size < 2 && args.firstOrNull() != "selftest") {
        println("usage: Verify <scene|libraryDir> <dump|render|bench|seektest|library|devicebench> [args]")
        println("       Verify selftest")
        return
    }
    if (args[0] == "selftest") {
        if (!runSelfTest()) kotlin.system.exitProcess(1)
        return
    }

    if (args[1] == "devicebench") {
        deviceBenchmark(File(args[0]), args.drop(2).takeIf { it.isNotEmpty() })
        return
    }

    if (args[1] == "library") {
        if (!libraryReport(File(args[0]))) kotlin.system.exitProcess(1)
        return
    }

    val scene = load(File(args[0]))
    val mode = args[1]
    val probe = args.getOrNull(2)?.toInt() ?: (scene.frameCount / 2)

    when (mode) {
        "perframe" -> {
            val counter = CountingSink()
            println("frame verbs draws maxpath")
            for (i in 0 until scene.frameCount) {
                counter.reset()
                Renderer.drawFrame(scene, i, counter)
                println("$i ${counter.verbs} ${counter.draws} ${counter.maxPathVerbs}")
            }
        }
        "dump" -> dump(scene, probe)
        "render" -> {
            val out = args.getOrNull(3) ?: "frame.png"
            // An optional variant name renders through one of the sweep's
            // option sets, so a trade can be looked at rather than only timed.
            val variant = args.getOrNull(4)
            val options = Benchmark.variants(1280f / FRAME_WIDTH).firstOrNull { it.first == variant }?.second
                ?: RenderOptions.DEFAULT
            ImageIO.write(render(scene, probe, 1280, 720, options), "png", File(out))
            println("wrote $out (frame $probe of ${scene.frameCount})")
        }
        "bench" -> benchmark(scene, 1280, 720)
        "seektest" -> {
            println("seek exactness, ${scene.frameCount} frames")
            if (!seekTest(scene)) kotlin.system.exitProcess(1)
        }
        else -> println("unknown mode $mode")
    }
}
