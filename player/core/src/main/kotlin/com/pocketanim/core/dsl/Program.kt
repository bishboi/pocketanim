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
    /** [lag] is Create's lag_ratio over an asset's children; null means Manim's 1.0. */
    class Create(
        val name: String, val seconds: Double, val rate: String, val removing: Boolean = false,
        val lag: Double? = null,
    ) : Step()
    class Transform(
        val source: String, val target: String, val seconds: Double, val rate: String,
        val arc: Double = 0.0,
    ) : Step()
    class Morph(val source: String, val target: String, val seconds: Double) : Step()
    class Show(val name: String) : Step()
    /** The other half of [Show]: what Manim's Scene.remove took off stage. */
    class Hide(val name: String) : Step()
    class Fade(
        val name: String, val seconds: Double,
        val shift: DoubleArray = doubleArrayOf(0.0, 0.0), val from: Double = 1.0,
    ) : Step()
    class FadeOut(
        val name: String, val seconds: Double,
        val shift: DoubleArray = doubleArrayOf(0.0, 0.0), val from: Double = 1.0,
    ) : Step()
    class Write(val name: String, val seconds: Double) : Step()
    /** Write run backwards, then the object leaves the stage. */
    class Unwrite(val name: String, val seconds: Double) : Step()
    /** Rewritten from Create on an asset; Manim's Create lags a group's children. */
    class RevealSequence(val name: String, val seconds: Double, val lag: Double = 1.0) : Step()
    /** `.animate.set_fill`. Null fields are left as they are. */
    class Fill(val name: String, val color: Int?, val opacity: Double?, val seconds: Double) : Step()
    class Xform(val name: String, val factor: Double, val offsetXy: DoubleArray, val seconds: Double) : Step()
    /** `.animate.set_stroke`. Null fields are left as they are. */
    class Stroke(
        val name: String, val color: Int?, val width: Double?, val opacity: Double?, val seconds: Double,
    ) : Step()
    /** GrowFromCenter on a circle, square or rectangle. Assets use [LaggedGrow]. */
    class Grow(val name: String, val seconds: Double, val at: DoubleArray? = null) : Step()
    class LaggedGrow(
        val name: String, val lag: Double, val groups: IntArray, val seconds: Double,
        val at: DoubleArray? = null,
    ) : Step()
    /** A 2D rotation by [radians] about [at]. */
    class Rotate(
        val name: String, val radians: Double, val at: DoubleArray, val seconds: Double, val rate: String,
    ) : Step()
    /** A there-and-back scale pulse to 1.2. */
    class Indicate(val name: String, val seconds: Double) : Step()
    class Move(val phi: Double?, val theta: Double?, val seconds: Double, val zoom: Double? = null) : Step()
    class Spin(val rate: Double, val seconds: Double, val about: String = "theta") : Step()
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

    /**
     * A staggered group. [runs] is how many following steps belong to each
     * child. The builder folds this into [Lag] before scheduling.
     */
    class LagHeader(val runs: IntArray, val ratio: Double, val seconds: Double) : Step()

    /** Folded [LagHeader]. Children start one after another by [ratio]. */
    class Lag(val ratio: Double, val seconds: Double, val members: List<Step>) : Step()

    /** Several steps played in order, as one child of a [Lag]. */
    class Sequence(val members: List<Step>) : Step()

    /** A folded [Par] group. Never parsed; only ever built. */
    class Parallel(val members: List<Step>) : Step()
}

class Program(
    val fps: Int,
    val mode: String,
    val phi: Double,
    val theta: Double,
    /** Manim's camera zoom. 1.0 unless the scene set one. */
    val zoom: Double,
    val shapes: Map<String, ShapeSpec>,
    /** name -> (kind, assetId), kind being "text" or "geom". */
    val assets: Map<String, Pair<String, String>>,
    val surfaces: List<SurfaceSpec>,
    val timeline: List<Step>,
    /** Declared draw order by name. Absent means 0. */
    val z: Map<String, Double> = emptyMap(),
) {
    val is3d: Boolean get() = mode == "3d"

    companion object {
        fun parse(text: String): Program {
            var fps = 30
            var mode = "3d"
            var phi = 0.0
            var theta = 0.0
            var zoom = 1.0
            val shapes = LinkedHashMap<String, ShapeSpec>()
            val assets = LinkedHashMap<String, Pair<String, String>>()
            val surfaces = ArrayList<SurfaceSpec>()
            val timeline = ArrayList<Step>()
            val z = HashMap<String, Double>()

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

                if (verb in DECLARATIONS) args["z"]?.let { z[positional[0]] = it.toDouble() }

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
                        zoom = (args["zoom"] ?: "1").toDouble()
                    }
                    "create", "uncreate" -> timeline.add(
                        Step.Create(
                            positional[0], t(), rate(), removing = verb == "uncreate",
                            lag = args["lag"]?.toDouble(),
                        )
                    )
                    "transform" -> timeline.add(
                        Step.Transform(
                            positional[0], positional[1], t(), rate(),
                            arc = args["arc"]?.toDouble() ?: 0.0,
                        )
                    )
                    "morph" -> timeline.add(Step.Morph(positional[0], positional[1], t()))
                    "show" -> timeline.add(Step.Show(positional[0]))
                    "hide" -> timeline.add(Step.Hide(positional[0]))
                    "fade" -> timeline.add(Step.Fade(positional[0], t(), shiftOf(args), args["from"]?.toDouble() ?: 1.0))
                    "fadeout" -> timeline.add(Step.FadeOut(positional[0], t(), shiftOf(args), args["from"]?.toDouble() ?: 1.0))
                    "write" -> timeline.add(Step.Write(positional[0], t()))
                    "unwrite" -> timeline.add(Step.Unwrite(positional[0], t()))
                    "fill" -> timeline.add(
                        Step.Fill(
                            positional[0],
                            args["color"]?.let { hexRgb(it) },
                            args["opacity"]?.toDouble(),
                            t(),
                        )
                    )
                    "stroke" -> timeline.add(
                        Step.Stroke(
                            positional[0],
                            args["color"]?.let { hexRgb(it) },
                            args["w"]?.toDouble(),
                            args["opacity"]?.toDouble(),
                            t(),
                        )
                    )
                    "xform" -> {
                        val by = (args["by_xy"] ?: "0,0").split(",")
                        timeline.add(
                            Step.Xform(
                                positional[0], (args["by"] ?: "1.0").toDouble(),
                                doubleArrayOf(by[0].toDouble(), by[1].toDouble()), t(),
                            )
                        )
                    }
                    "grow" -> timeline.add(Step.Grow(positional[0], t(), pointOf(args["at"])))
                    "laggedgrow" -> timeline.add(
                        Step.LaggedGrow(
                            positional[0], args.getValue("lag").toDouble(),
                            args.getValue("groups").split(",").map { it.toInt() }.toIntArray(), t(),
                            pointOf(args["at"]),
                        )
                    )
                    "rotate" -> timeline.add(
                        Step.Rotate(
                            positional[0],
                            Math.toRadians(args.getValue("deg").toDouble()),
                            (args["at"] ?: "0,0").split(",").map { it.toDouble() }.toDoubleArray(),
                            t(), rate(),
                        )
                    )
                    "indicate" -> timeline.add(Step.Indicate(positional[0], t()))
                    "move" -> timeline.add(
                        Step.Move(
                            args["phi"]?.let { Math.toRadians(it.toDouble()) },
                            args["theta"]?.let { Math.toRadians(it.toDouble()) },
                            t(),
                            args["zoom"]?.toDouble(),
                        )
                    )
                    "spin" -> timeline.add(
                        Step.Spin(args.getValue("rate").toDouble(), t(), args["about"] ?: "theta")
                    )
                    "lag" -> timeline.add(
                        Step.LagHeader(
                            args.getValue("runs").split(",").map { it.toInt() }.toIntArray(),
                            args.getValue("ratio").toDouble(),
                            t(),
                        )
                    )
                    "par" -> timeline.add(
                        Step.Par(args.getValue("n").toInt(), t())
                    )
                    "wait" -> timeline.add(Step.Wait(t()))
                    else -> throw IllegalArgumentException("unknown verb '$verb'")
                }
            }

            return Program(fps, mode, phi, theta, zoom, shapes, assets, surfaces, timeline, z)
        }

        private val DECLARATIONS = setOf("circle", "square", "rect", "text", "geom")

        private fun shiftOf(args: Map<String, String>): DoubleArray {
            val parts = (args["shift"] ?: "0,0").split(",")
            return doubleArrayOf(parts[0].toDouble(), parts.getOrElse(1) { "0" }.toDouble())
        }

        private fun pointOf(text: String?): DoubleArray? {
            if (text == null) return null
            val parts = text.split(",").map { it.toDouble() }
            return doubleArrayOf(parts[0], parts[1], parts.getOrElse(2) { 0.0 })
        }

        private fun hexRgb(text: String): Int {
            val hex = text.removePrefix("#")
            return hex.substring(0, 6).toInt(16)
        }
    }
}
