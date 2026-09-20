package com.pocketanim.desktop

import com.pocketanim.core.FRAME_HEIGHT
import com.pocketanim.core.FRAME_WIDTH
import com.pocketanim.core.Panm
import com.pocketanim.core.PathSink
import com.pocketanim.core.Renderer
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

    override fun closeSubpath() {
        path.closePath()
    }

    override fun fillPath(argb: Int) {
        g.color = Color(argb, true)
        g.fill(path)
    }

    override fun strokePath(argb: Int, widthInSceneUnits: Float) {
        g.color = Color(argb, true)
        g.stroke = BasicStroke(widthInSceneUnits, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND)
        g.draw(path)
    }
}

private fun render(scene: Scene, index: Int, width: Int, height: Int): BufferedImage {
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

    Renderer.drawFrame(scene, index, Java2DSink(g))
    g.dispose()
    return image
}

/** The canonical dump the Java and Python decoders also emit, field for field. */
private fun dump(scene: Scene, probe: Int) {
    val l = Locale.ROOT
    val out = StringBuilder()
    out.append(String.format(l, "H %d %d %d %d%n",
        scene.fps, scene.records.size, scene.atlas.size, if (scene.cameras != null) 1 else 0))
    // A program carries no quantisation box -- its geometry is computed, not
    // dequantised -- so the bounds line is omitted rather than faked.
    val quantised = scene.lo.any { it != 0f } || scene.hi.any { it != 0f }
    if (quantised) {
        out.append(String.format(l, "B %.6f %.6f %.6f %.6f %.6f %.6f%n",
            scene.lo[0], scene.lo[1], scene.lo[2], scene.hi[0], scene.hi[1], scene.hi[2]))
    }

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

    for (r in scene.records.indices) {
        out.append(String.format(l, "R %d %d %d%n", r, scene.records[r].kind, scene.records[r].instances.size))
    }

    scene.cameras?.let { cameras ->
        out.append("C ").append(probe)
        for (v in cameras[probe]) out.append(String.format(l, " %.6f", v))
        out.append('\n')
    }

    val frame = scene.frame(probe)
    out.append(String.format(l, "F %d %d%n", probe, frame.size))
    for (i in frame.indices) {
        val inst = frame[i]
        out.append(String.format(l, "I %d %d %d %d", i, inst.slot, inst.atlasId, inst.flags))
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
private fun benchmark(scene: Scene, width: Int, height: Int) {
    val sink = object : PathSink {
        var verbs = 0L
        override fun beginPath() {}
        override fun moveTo(x: Float, y: Float) { verbs++ }
        override fun cubicTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float) { verbs++ }
        override fun closeSubpath() { verbs++ }
        override fun fillPath(argb: Int) {}
        override fun strokePath(argb: Int, widthInSceneUnits: Float) {}
    }

    repeat(2) { for (i in 0 until scene.frameCount) Renderer.drawFrame(scene, i, sink) } // warm up
    sink.verbs = 0

    val started = System.nanoTime()
    for (i in 0 until scene.frameCount) Renderer.drawFrame(scene, i, sink)
    val elapsed = (System.nanoTime() - started) / 1e9

    val perFrame = elapsed / scene.frameCount * 1000.0
    println(String.format(Locale.ROOT, "frames          %d", scene.frameCount))
    println(String.format(Locale.ROOT, "geometry ms/fr  %.3f", perFrame))
    println(String.format(Locale.ROOT, "path verbs/fr   %.0f", sink.verbs.toDouble() / scene.frameCount))
    println(String.format(Locale.ROOT, "budget at 30fps %.1f%% (geometry only, desktop)",
        perFrame / (1000.0 / scene.fps) * 100.0))
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
private fun load(path: File): Scene =
    if (path.name.endsWith(".panim")) {
        Interpreter.build(Program.parse(path.readText()), FileAssets(path.parentFile))
    } else {
        Scene.parse(path.readBytes())
    }

fun main(args: Array<String>) {
    if (args.size < 2) {
        println("usage: Verify <scene.panm|scene.panim> <dump|render|bench> [frame] [out.png]")
        return
    }
    val scene = load(File(args[0]))
    val mode = args[1]
    val probe = args.getOrNull(2)?.toInt() ?: (scene.frameCount / 2)

    when (mode) {
        "dump" -> dump(scene, probe)
        "render" -> {
            val out = args.getOrNull(3) ?: "frame.png"
            ImageIO.write(render(scene, probe, 1280, 720), "png", File(out))
            println("wrote $out (frame $probe of ${scene.frameCount})")
        }
        "bench" -> benchmark(scene, 1280, 720)
        else -> println("unknown mode $mode")
    }
}
