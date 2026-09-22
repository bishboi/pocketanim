package com.pocketanim.core.dsl

/**
 * The tier-1 artefact: a program, not its samples.
 *
 * A few hundred bytes of text that the device expands into frames. This parses
 * it. The grammar is line-based and whitespace-tokenised -- `verb positional...
 * key=value...` -- which is why the exporter strips spaces out of emitted
 * expressions.
 */

class ShapeSpec(
    val kind: String,
    val size: Double,
    val extent: DoubleArray?,
    val stroke: Int,       // 0xRRGGBB
    val width: Double,
    val at: DoubleArray,
)

class SurfaceSpec(
    val name: String,
    val fn: Expr,
    val uRange: DoubleArray,
    val vRange: DoubleArray,
    val resolution: IntArray,
    val colors: IntArray,
    val alpha: Double,
    val stroke: Double,
)

sealed class Step {
    class Create(val name: String, val seconds: Double, val rate: String) : Step()
    class Transform(val source: String, val target: String, val seconds: Double, val rate: String) : Step()
    class Morph(val source: String, val target: String, val seconds: Double) : Step()
    class Show(val name: String) : Step()
    class Fade(val name: String, val seconds: Double) : Step()
    class FadeOut(val name: String, val seconds: Double) : Step()
    class Write(val name: String, val seconds: Double) : Step()
    /** Rewritten from Create on an asset; Manim's Create lags a group's children. */
    class RevealSequence(val name: String, val seconds: Double) : Step()
    class Xform(val name: String, val factor: Double, val offsetXy: DoubleArray, val seconds: Double) : Step()
    class LaggedGrow(val name: String, val lag: Double, val groups: IntArray, val seconds: Double) : Step()
    class Move(val phi: Double, val theta: Double, val seconds: Double) : Step()
    class Spin(val rate: Double, val seconds: Double) : Step()
    class Wait(val seconds: Double) : Step()

    /**
     * A marker, not a verb: the next [count] steps share one clock.
     *
     * Manim's `play(A(), B())` runs its animations together, and a timeline of
     * consecutive verbs cannot say that -- it played the scene for twice its
     * run_time and showed one thing after the other. The builder folds a run of
     * these into [Parallel] before anything is scheduled.
     */
    class Par(val count: Int, val seconds: Double) : Step()

    /** A folded [Par] group. Never parsed; only ever built. */
    class Parallel(val members: List<Step>) : Step()
}

class Program(
    val fps: Int,
    val mode: String,
    val phi: Double,
    val theta: Double,
    val shapes: Map<String, ShapeSpec>,
    /** name -> (kind, assetId), kind being "text" or "geom". */
    val assets: Map<String, Pair<String, String>>,
    val surfaces: List<SurfaceSpec>,
    val timeline: List<Step>,
) {
    val is3d: Boolean get() = mode == "3d"

    companion object {
        fun parse(text: String): Program {
            var fps = 30
            var mode = "3d"
            var phi = 0.0
            var theta = 0.0
            val shapes = LinkedHashMap<String, ShapeSpec>()
            val assets = LinkedHashMap<String, Pair<String, String>>()
            val surfaces = ArrayList<SurfaceSpec>()
            val timeline = ArrayList<Step>()

            for (raw in text.lineSequence()) {
                val line = raw.trim()
                if (line.isEmpty() || line.startsWith("#")) continue

                val tokens = line.split(Regex("\\s+"))
                val verb = tokens[0]
                val positional = ArrayList<String>()
                val args = HashMap<String, String>()
                for (token in tokens.drop(1)) {
                    val eq = token.indexOf('=')
                    if (eq >= 0) args[token.substring(0, eq)] = token.substring(eq + 1)
                    else positional.add(token)
                }

                fun t() = args.getValue("t").toDouble()
                fun rate() = args["rate"] ?: "smooth"

                when (verb) {
                    "scene" -> {
                        fps = args["fps"]?.toInt() ?: 30
                        if (positional.isNotEmpty()) mode = positional[0]
                    }
                    "circle", "square", "rect" -> shapes[positional[0]] = ShapeSpec(
                        kind = verb,
                        size = (args["r"] ?: args["s"] ?: "0").toDouble(),
                        extent = args["wh"]?.split(",")?.map { it.toDouble() }?.toDoubleArray(),
                        stroke = hexRgb(args.getValue("stroke")),
                        width = (args["w"] ?: "4").toDouble(),
                        at = (args["at"] ?: "0,0").split(",").map { it.toDouble() }.toDoubleArray(),
                    )
                    "text", "geom" -> assets[positional[0]] = Pair(verb, args.getValue("asset"))
                    "surface" -> surfaces.add(
                        SurfaceSpec(
                            name = positional.firstOrNull() ?: "S",
                            fn = Expr.parse(args.getValue("fn")),
                            uRange = args.getValue("u").split(",").map { it.toDouble() }.toDoubleArray(),
                            vRange = args.getValue("v").split(",").map { it.toDouble() }.toDoubleArray(),
                            resolution = args.getValue("res").split(",").map { it.toInt() }.toIntArray(),
                            colors = args.getValue("fill").split(",").map { hexRgb(it) }.toIntArray(),
                            alpha = (args["alpha"] ?: "1.0").toDouble(),
                            stroke = (args["stroke"] ?: "0.0").toDouble(),
                        )
                    )
                    "camera" -> {
                        phi = Math.toRadians((args["phi"] ?: "0").toDouble())
                        theta = Math.toRadians((args["theta"] ?: "0").toDouble())
                    }
                    "create" -> timeline.add(Step.Create(positional[0], t(), rate()))
                    "transform" -> timeline.add(Step.Transform(positional[0], positional[1], t(), rate()))
                    "morph" -> timeline.add(Step.Morph(positional[0], positional[1], t()))
                    "show" -> timeline.add(Step.Show(positional[0]))
                    "fade" -> timeline.add(Step.Fade(positional[0], t()))
                    "fadeout" -> timeline.add(Step.FadeOut(positional[0], t()))
                    "write" -> timeline.add(Step.Write(positional[0], t()))
                    "xform" -> {
                        val by = (args["by_xy"] ?: "0,0").split(",")
                        timeline.add(
                            Step.Xform(
                                positional[0], (args["by"] ?: "1.0").toDouble(),
                                doubleArrayOf(by[0].toDouble(), by[1].toDouble()), t(),
                            )
                        )
                    }
                    "laggedgrow" -> timeline.add(
                        Step.LaggedGrow(
                            positional[0], args.getValue("lag").toDouble(),
                            args.getValue("groups").split(",").map { it.toInt() }.toIntArray(), t(),
                        )
                    )
                    "move" -> timeline.add(
                        Step.Move(
                            Math.toRadians(args.getValue("phi").toDouble()),
                            Math.toRadians(args.getValue("theta").toDouble()),
                            t(),
                        )
                    )
                    "spin" -> timeline.add(Step.Spin(args.getValue("rate").toDouble(), t()))
                    "par" -> timeline.add(
                        Step.Par(args.getValue("n").toInt(), t())
                    )
                    "wait" -> timeline.add(Step.Wait(t()))
                    else -> throw IllegalArgumentException("unknown verb '$verb'")
                }
            }

            return Program(fps, mode, phi, theta, shapes, assets, surfaces, timeline)
        }

        private fun hexRgb(text: String): Int {
            val hex = text.removePrefix("#")
            return hex.substring(0, 6).toInt(16)
        }
    }
}
