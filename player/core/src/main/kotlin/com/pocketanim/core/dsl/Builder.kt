package com.pocketanim.core.dsl

import com.pocketanim.core.Instance
import com.pocketanim.core.Panm
import com.pocketanim.core.Record
import com.pocketanim.core.Scene

/** Manim's DrawBorderThenFill(stroke_width=2). */
private const val OUTLINE_STROKE_WIDTH = 2.0

/**
 * The timeline state machine.
 *
 * Split out from [Interpreter] because it is long and it is the part that has
 * to match Manim verb for verb. Each branch below names the Manim behaviour it
 * reproduces; where Manim does something surprising -- a group's children
 * lagging, a wait's last frame not advancing the camera -- the surprise is
 * recorded next to the code that pays for it, because every one of them cost a
 * measured fidelity regression to find.
 */
internal class Builder(private val program: Program, private val loader: AssetLoader) {

    val fps = program.fps
    val is3d = program.is3d
    private val shapes = ArrayList<DoubleArray>()
    private val objects = LinkedHashMap<String, Obj>()

    private var phi = program.phi
    private var theta = program.theta

    /** The frame just produced, held so the renderer can read it. */
    private var current: Array<Instance> = emptyArray()
    private var currentCamera: FloatArray? = null

    fun shape(atlasId: Int): FloatArray {
        val s = shapes[atlasId]
        return FloatArray(s.size) { s[it].toFloat() }
    }

    fun frameInstances(): Array<Instance> = current
    fun frameCamera(): FloatArray? = currentCamera

    // ---- declarations -----------------------------------------------------

    /** Surfaces declared as program become objects like anything else. */
    private fun declareSurfaces() {
        for (surface in program.surfaces) {
            val faces = Interpreter.tessellate(surface.fn, surface.uRange, surface.vRange, surface.resolution)
            val vRes = surface.resolution[1]
            val alpha = (surface.alpha * 255).toInt()
            val instances = ArrayList<Inst>(faces.size)
            val normals = arrayOfNulls<DoubleArray>(faces.size)

            for ((index, face) in faces.withIndex()) {
                val i = index / vRes
                val j = index % vRes
                val colour = surface.colors[(i + j) % surface.colors.size]
                val centre = meanOf(face)
                val centred = DoubleArray(face.size)
                for (k in face.indices) centred[k] = face[k] - centre[k % 3]
                shapes.add(centred)

                val transform = identity()
                transform[3] = centre[0]; transform[7] = centre[1]; transform[11] = centre[2]
                val rgba = intArrayOf((colour shr 16) and 0xFF, (colour shr 8) and 0xFF, colour and 0xFF, alpha)
                instances.add(Inst(shapes.size - 1, transform, rgba, rgba.copyOf(), surface.stroke))
                normals[index] = Interpreter.planeNormal(face)
            }

            objects[surface.name] = Obj(
                kind = "asset", visible = true, instances = instances,
                glyphIds = IntArray(instances.size) { it },
                normals = normals,
            )
        }
    }

    private fun declareAssets() {
        for ((name, spec) in program.assets) {
            val (kind, assetId) = spec
            val asset = Panm.let { Scene.parse(loader.asset(assetId)) }
            // A text asset carries instances only; its geometry is the shared
            // library, which is what makes a second caption cost zero bytes.
            val geometry = if (kind == "text") Scene.parse(loader.glyphLibrary()).atlas else asset.atlas
            val instances = asset.frame(0)

            val offset = shapes.size
            for (shape in geometry) shapes.add(DoubleArray(shape.size) { shape[it].toDouble() })

            var minX = Double.MAX_VALUE; var minY = Double.MAX_VALUE; var minZ = Double.MAX_VALUE
            var maxX = -Double.MAX_VALUE; var maxY = -Double.MAX_VALUE; var maxZ = -Double.MAX_VALUE
            var any = false
            for (inst in instances) {
                val pts = geometry[inst.atlasId]
                var i = 0
                while (i < pts.size) {
                    val x = inst.transform[0] * pts[i] + inst.transform[1] * pts[i + 1] + inst.transform[2] * pts[i + 2] + inst.transform[3]
                    val y = inst.transform[4] * pts[i] + inst.transform[5] * pts[i + 1] + inst.transform[6] * pts[i + 2] + inst.transform[7]
                    val z = inst.transform[8] * pts[i] + inst.transform[9] * pts[i + 1] + inst.transform[10] * pts[i + 2] + inst.transform[11]
                    if (x < minX) minX = x.toDouble(); if (x > maxX) maxX = x.toDouble()
                    if (y < minY) minY = y.toDouble(); if (y > maxY) maxY = y.toDouble()
                    if (z < minZ) minZ = z.toDouble(); if (z > maxZ) maxZ = z.toDouble()
                    any = true
                    i += 3
                }
            }
            val centre = if (any) doubleArrayOf((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
                         else DoubleArray(3)

            objects[name] = Obj(
                kind = "asset",
                // Declaring a thing is not the same as it being on stage; an
                // asset waits for a verb that puts it there.
                visible = false,
                centre = centre,
                instances = instances.mapTo(ArrayList()) { inst ->
                    Inst(
                        inst.atlasId + offset,
                        DoubleArray(12) { inst.transform[it].toDouble() },
                        rgbaOf(inst.fill), rgbaOf(inst.stroke), inst.strokeWidth.toDouble(),
                    )
                },
                flags = IntArray(instances.size) { instances[it].flags },
                normals = Array(instances.size) { i ->
                    instances[i].normal?.let { n -> DoubleArray(3) { n[it].toDouble() } }
                },
                // Library-relative ids, kept so two assets can be matched glyph
                // for glyph even though each is offset into the shape list.
                glyphIds = IntArray(instances.size) { instances[it].atlasId },
            )
        }
    }

    // ---- emit -------------------------------------------------------------

    private fun cameraRecord(): FloatArray {
        val m = Interpreter.cameraMatrix(phi, theta)
        val out = FloatArray(Panm.CAMERA_FLOATS)
        out[3] = FOCAL; out[4] = ZOOM_F
        for (k in 0 until 9) out[5 + k] = m[k].toFloat()
        out[14] = -7f; out[15] = -9f; out[16] = 10f
        return out
    }

    private fun emit() {
        val frame = ArrayList<Instance>()
        for (obj in objects.values) {
            if (!obj.visible) continue
            if (obj.kind == "asset") {
                val normals = obj.normals
                val flags = obj.flags
                for ((index, inst) in obj.instances.withIndex()) {
                    val normal = normals?.getOrNull(index)
                    val flag = if (flags != null && index < flags.size) flags[index]
                               else if (normal != null) Panm.SHADE_IN_3D else 0
                    val composed = compose(obj.xform, inst.transform)
                    frame.add(
                        Instance(
                            slot = frame.size,
                            atlasId = inst.atlasId,
                            flags = flag,
                            transform = FloatArray(12) { composed[it].toFloat() },
                            fill = argbOf(inst.fill),
                            stroke = argbOf(inst.stroke),
                            strokeWidth = inst.width.toFloat(),
                            normal = normal?.let { n -> FloatArray(3) { n[it].toFloat() } },
                        )
                    )
                }
            } else {
                shapes.add(obj.points!!)
                frame.add(
                    Instance(
                        slot = frame.size,
                        atlasId = shapes.size - 1,
                        flags = 0,
                        transform = FloatArray(12) { identity()[it].toFloat() },
                        fill = 0,
                        stroke = argbOf(
                            intArrayOf(
                                (obj.strokeRgb shr 16) and 0xFF,
                                (obj.strokeRgb shr 8) and 0xFF,
                                obj.strokeRgb and 0xFF,
                                (255 * obj.alpha).toInt(),
                            )
                        ),
                        strokeWidth = obj.width.toFloat(),
                        normal = null,
                    )
                )
            }
        }
        current = frame.toTypedArray()
        currentCamera = if (is3d) cameraRecord() else null
    }

    // ---- helpers ----------------------------------------------------------

    private fun meanOf(points: DoubleArray): DoubleArray {
        val n = points.size / 3
        val out = DoubleArray(3)
        for (i in 0 until n) for (k in 0 until 3) out[k] += points[i * 3 + k]
        for (k in 0 until 3) out[k] /= n
        return out
    }

    private fun rgbaOf(argb: Int) = intArrayOf(
        (argb shr 16) and 0xFF, (argb shr 8) and 0xFF, argb and 0xFF, (argb ushr 24) and 0xFF,
    )

    private fun argbOf(rgba: IntArray) =
        (rgba[3] shl 24) or (rgba[0] shl 16) or (rgba[1] shl 8) or rgba[2]

    private fun geometryFor(spec: ShapeSpec): DoubleArray {
        val points = when (spec.kind) {
            "circle" -> Verbs.circle(spec.size)
            "rect" -> Verbs.rectangle(spec.extent!![0], spec.extent[1])
            else -> Verbs.square(spec.size)
        }
        var i = 0
        while (i < points.size) {
            points[i] += spec.at[0]
            points[i + 1] += spec.at[1]
            i += 3
        }
        return points
    }

    private fun isAsset(name: String) = objects[name]?.kind == "asset"

    private companion object {
        const val FOCAL = 20.0f
        const val ZOOM_F = 1.0f
    }


    // ---- timeline ---------------------------------------------------------

    /**
     * One verb, resumable.
     *
     * These replaced loops that materialised every frame of every verb up front
     * and retained them -- 98.8 MB for one corpus scene, which is fatal on a
     * phone. Each verb's per-frame body was already a pure function of (state
     * captured at the verb's start, frame number), so splitting that out costs
     * nothing and lets the player hold one frame instead of all of them.
     */
    private interface Runner {
        val frames: Int
        /** Capture whatever the per-frame body reads; put the object on stage. */
        fun enter()
        /** Put the scene into the state frame [k] of this verb should show. */
        fun render(k: Int)
        /** Settle the end-of-verb state that the next verb inherits. */
        fun exit()
    }

    /** Scene state at a verb boundary, so seeking back need not start over. */
    private class Checkpoint(
        val objects: LinkedHashMap<String, Obj>,
        val shapeCount: Int,
        val phi: Double,
        val theta: Double,
    )

    private lateinit var runners: List<Runner>
    /** Global frame index at which each verb starts; the last entry is the total. */
    private lateinit var starts: IntArray
    /** Names made visible immediately before the verb at this index. */
    /**
     * The `show` and `hide` verbs attached to each step, in the order the
     * program wrote them. Neither produces a frame, so they ride the verb that
     * follows; order between them matters, so they share one list.
     */
    private val staging = HashMap<Int, List<Step>>()
    private val checkpoints = HashMap<Int, Checkpoint>()

    private var cursorStep = -1
    private var cursorFrame = -1

    val frameCount: Int get() = starts.last()

    fun prepare() {
        declareSurfaces()
        declareAssets()

        // Rewrite create-on-asset to a lagged reveal in a PRE-PASS. Appending
        // the rewrite to the list being iterated pushed every asset reveal to
        // the end, so camera moves ran before the things they were looking at.
        val rewritten = program.timeline.map { step ->
            if (step is Step.Create && isAsset(step.name)) Step.RevealSequence(step.name, step.seconds)
            else step
        }

        // Fold `par` groups before anything is scheduled, so a group is one
        // step from here on and the show-attachment below keeps its indices.
        val folded = ArrayList<Step>()
        var cursor = 0
        while (cursor < rewritten.size) {
            val step = rewritten[cursor]
            cursor++
            if (step !is Step.Par) {
                folded.add(step)
                continue
            }
            // Take the next `count` verbs. A `show` produces no frame and is
            // not a member, so it is carried past the group rather than into
            // it -- the exporter does not interleave them, and relying on that
            // silently would be the kind of assumption this file keeps paying
            // for.
            val members = ArrayList<Step>()
            val carried = ArrayList<Step>()
            while (members.size < step.count && cursor < rewritten.size) {
                val next = rewritten[cursor]
                cursor++
                if (next is Step.Show || next is Step.Hide) carried.add(next) else members.add(next)
            }
            if (members.isNotEmpty()) folded.add(Step.Parallel(members))
            folded.addAll(carried)
        }

        // `show` and `hide` produce no frame, so they are attached to the verb
        // that follows rather than being verbs themselves. Manim also renders
        // the scene's opening state once at t=0 before the first animation's
        // first step -- that is the one-frame hold below, and without it every
        // later frame is one early and the closing frame is missing.
        val expanded = ArrayList<Step>()
        val pending = ArrayList<Step>()
        var opened = false
        for (step in folded) {
            if (step is Step.Show || step is Step.Hide) {
                pending.add(step)
                continue
            }
            if (!opened) {
                opened = true
                // Anything added before the first play is on stage for it.
                staging[expanded.size] = ArrayList(pending)
                pending.clear()
                expanded.add(Step.Wait(1.0 / fps))
            }
            staging[expanded.size] = ArrayList(pending)
            pending.clear()
            expanded.add(step)
        }

        runners = expanded.map { runnerFor(it) }
        starts = IntArray(runners.size + 1)
        for (i in runners.indices) starts[i + 1] = starts[i] + runners[i].frames
        checkpoint(0)
    }

    private fun checkpoint(stepIndex: Int) {
        val copy = LinkedHashMap<String, Obj>()
        for ((name, obj) in objects) copy[name] = obj.copy()
        checkpoints[stepIndex] = Checkpoint(copy, shapes.size, phi, theta)
    }

    private fun restore(stepIndex: Int) {
        val saved = checkpoints.getValue(stepIndex)
        objects.clear()
        for ((name, obj) in saved.objects) objects[name] = obj.copy()
        // Reveals append partial geometry to the atlas; replaying without
        // truncating would append it again on every seek.
        while (shapes.size > saved.shapeCount) shapes.removeAt(shapes.size - 1)
        phi = saved.phi
        theta = saved.theta
    }

    private fun stepContaining(frame: Int): Int {
        for (i in runners.indices) if (frame < starts[i + 1]) return i
        return runners.size - 1
    }

    /**
     * Produce one frame.
     *
     * Playing forward advances within the current verb. Seeking backwards
     * restores the nearest verb boundary and replays inside that verb only, so
     * the cost is bounded by the longest verb rather than by how far the seek
     * went -- the same property that makes tier-3 snapshots cheap to seek in.
     */
    fun seek(index: Int) {
        val target = index.coerceIn(0, frameCount - 1)
        val step = stepContaining(target)
        val local = target - starts[step]

        if (step == cursorStep && local >= cursorFrame) {
            for (k in (cursorFrame + 1)..local) runners[step].render(k)
            cursorFrame = local
            return
        }

        // Finishing the current verb is the cheap way into the next one; it
        // avoids replaying a verb we have just finished playing.
        if (cursorStep >= 0 && step == cursorStep + 1 &&
            cursorFrame == runners[cursorStep].frames - 1 &&
            !checkpoints.containsKey(step)
        ) {
            runners[cursorStep].exit()
            checkpoint(step)
        }

        ensureCheckpoint(step)
        restore(step)
        applyStaging(step)
        runners[step].enter()
        for (k in 0..local) runners[step].render(k)
        cursorStep = step
        cursorFrame = local
    }

    private fun ensureCheckpoint(step: Int) {
        if (checkpoints.containsKey(step)) return
        var from = checkpoints.keys.filter { it < step }.max()
        restore(from)
        while (from < step) {
            playWhole(from)
            from++
            checkpoint(from)
        }
    }

    private fun applyStaging(stepIndex: Int) {
        staging[stepIndex]?.forEach { step ->
            when (step) {
                // A `hide` may name an object this interpreter never put on
                // stage -- a fadeout drops its object outright -- so a hide for
                // an absent name is a no-op rather than an error.
                is Step.Hide -> objects[step.name]?.visible = false
                is Step.Show -> objects.getValue(step.name).visible = true
                else -> Unit
            }
        }
    }

    /** Run a verb start to finish for its side effects, discarding its frames. */
    private fun playWhole(stepIndex: Int) {
        applyStaging(stepIndex)
        val runner = runners[stepIndex]
        runner.enter()
        for (k in 0 until runner.frames) runner.render(k)
        runner.exit()
    }

    private fun frames(seconds: Double) = (seconds * fps).toInt()

    private fun runnerFor(step: Step): Runner = when (step) {
        is Step.Create -> createRunner(step)
        is Step.Transform -> transformRunner(step)
        is Step.Xform -> xformRunner(step)
        is Step.Write -> revealRunner(step.name, step.seconds, sequential = false)
        is Step.RevealSequence -> revealRunner(step.name, step.seconds, sequential = true)
        is Step.LaggedGrow -> laggedGrowRunner(step)
        is Step.Fade -> fadeRunner(step.name, step.seconds, fadingIn = true)
        is Step.FadeOut -> fadeRunner(step.name, step.seconds, fadingIn = false)
        is Step.Morph -> morphRunner(step)
        is Step.Move -> moveRunner(step)
        is Step.Spin -> spinRunner(step)
        is Step.Wait -> holdRunner(step.seconds)
        is Step.Parallel -> parallelRunner(step.members.map { runnerFor(it) })
        is Step.Par -> holdRunner(0.0)  // folded away in prepare; never reached
        is Step.Show, is Step.Hide -> holdRunner(0.0)
    }

    /**
     * Several verbs over one clock.
     *
     * The Runner contract composes without help: enter them all, render frame
     * k of each, exit them all. A member shorter than the group holds its last
     * frame rather than disappearing, which is what Manim does when one
     * animation in a `play()` finishes before another.
     */
    private fun parallelRunner(children: List<Runner>) = object : Runner {
        override val frames = children.maxOfOrNull { it.frames } ?: 0
        override fun enter() = children.forEach { it.enter() }
        override fun render(k: Int) =
            children.forEach { it.render(minOf(k, it.frames - 1).coerceAtLeast(0)) }
        override fun exit() = children.forEach { it.exit() }
    }

    private fun holdRunner(seconds: Double) = object : Runner {
        override val frames = frames(seconds)
        override fun enter() {}
        override fun render(k: Int) = emit()
        override fun exit() {}
    }

    private fun createRunner(step: Step.Create) = object : Runner {
        override val frames = frames(step.seconds)
        private val rate = Verbs.rate(step.rate)
        private val spec = program.shapes.getValue(step.name)
        private val full = geometryFor(spec)
        private lateinit var obj: Obj

        override fun enter() {
            obj = Obj(
                kind = "shape", visible = true, points = full, alpha = 1.0,
                strokeRgb = spec.stroke, width = spec.width,
            )
            objects[step.name] = obj
        }

        override fun render(k: Int) {
            obj.points = Verbs.pointwiseBecomePartial(full, 0.0, rate((k + 1).toDouble() / frames))
            emit()
        }

        override fun exit() {
            obj.points = full
        }
    }

    private fun transformRunner(step: Step.Transform) = object : Runner {
        override val frames = frames(step.seconds)
        private val rate = Verbs.rate(step.rate)
        private lateinit var obj: Obj
        private lateinit var startPts: DoubleArray
        private lateinit var endPts: DoubleArray
        private lateinit var c0: IntArray
        private lateinit var c1: IntArray

        override fun enter() {
            obj = objects.getValue(step.source)
            val targetSpec = program.shapes.getValue(step.target)
            val aligned = Verbs.align(obj.points!!, geometryFor(targetSpec))
            startPts = aligned.first
            endPts = aligned.second
            c0 = intArrayOf((obj.strokeRgb shr 16) and 0xFF, (obj.strokeRgb shr 8) and 0xFF, obj.strokeRgb and 0xFF)
            c1 = intArrayOf((targetSpec.stroke shr 16) and 0xFF, (targetSpec.stroke shr 8) and 0xFF, targetSpec.stroke and 0xFF)
        }

        override fun render(k: Int) {
            val alpha = rate((k + 1).toDouble() / frames)
            obj.points = DoubleArray(startPts.size) { startPts[it] + (endPts[it] - startPts[it]) * alpha }
            obj.strokeRgb = (0 until 3).fold(0) { acc, i ->
                (acc shl 8) or pyRound(c0[i] + (c1[i] - c0[i]) * alpha).coerceIn(0, 255)
            }
            emit()
        }

        override fun exit() {}
    }

    /** Manim scales about the object's centre, then translates. */
    private fun xformRunner(step: Step.Xform) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private lateinit var base: DoubleArray
        private lateinit var centre: DoubleArray
        private var isShape = false
        private var basePoints: DoubleArray? = null

        override fun enter() {
            obj = objects.getValue(step.name)
            // A primitive carries its geometry directly rather than as
            // instances under an object transform, so the matrix has to be
            // applied to its points. `.animate.scale(...).shift(...)` on a
            // Circle is ordinary Manim; this used to assume an asset.
            isShape = obj.kind == "shape"
            if (isShape) {
                val points = obj.points!!.copyOf()
                basePoints = points
                var minX = points[0]; var minY = points[1]; var minZ = points[2]
                var maxX = minX; var maxY = minY; var maxZ = minZ
                var i = 3
                while (i < points.size) {
                    if (points[i] < minX) minX = points[i]
                    if (points[i] > maxX) maxX = points[i]
                    if (points[i + 1] < minY) minY = points[i + 1]
                    if (points[i + 1] > maxY) maxY = points[i + 1]
                    if (points[i + 2] < minZ) minZ = points[i + 2]
                    if (points[i + 2] > maxZ) maxZ = points[i + 2]
                    i += 3
                }
                centre = doubleArrayOf((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
                base = identity()
            } else {
                base = obj.xform.copyOf()
                centre = obj.centre
            }
        }

        override fun render(k: Int) {
            val alpha = Verbs.smooth((k + 1).toDouble() / frames)
            val scale = 1.0 + (step.factor - 1.0) * alpha
            val m = DoubleArray(12)
            m[0] = scale; m[5] = scale; m[10] = scale
            m[3] = (1 - scale) * centre[0] + step.offsetXy[0] * alpha
            m[7] = (1 - scale) * centre[1] + step.offsetXy[1] * alpha
            m[11] = (1 - scale) * centre[2]

            val points = basePoints
            if (isShape && points != null) {
                val out = DoubleArray(points.size)
                var i = 0
                while (i < points.size) {
                    out[i] = m[0] * points[i] + m[1] * points[i + 1] + m[2] * points[i + 2] + m[3]
                    out[i + 1] = m[4] * points[i] + m[5] * points[i + 1] + m[6] * points[i + 2] + m[7]
                    out[i + 2] = m[8] * points[i] + m[9] * points[i + 1] + m[10] * points[i + 2] + m[11]
                    i += 3
                }
                obj.points = out
            } else {
                obj.xform = compose(m, base)
            }
            emit()
        }

        override fun exit() {}
    }

    /**
     * Manim lags each submobject. Write uses lag_ratio min(4/n, 0.2); Create on
     * a group uses 1.0, i.e. strictly one child at a time.
     */
    private fun revealRunner(name: String, seconds: Double, sequential: Boolean) = object : Runner {
        override val frames = frames(seconds)
        private lateinit var obj: Obj
        private lateinit var base: List<Inst>
        private var lag = 0.0
        private var window = 0.0
        private var shapeFloor = 0

        override fun enter() {
            obj = objects[name] ?: throw IllegalStateException("reveal target '$name' was never declared")
            // Revealing a thing puts it on stage. Without this the object
            // stayed hidden for the whole reveal and appeared only at its
            // trailing show.
            obj.visible = true
            base = obj.instances.toList()
            val count = maxOf(base.size, 1)
            lag = if (sequential) 1.0 else minOf(4.0 / count, 0.2)
            window = 1.0 / (1.0 + lag * (count - 1))
            shapeFloor = shapes.size
        }

        override fun render(k: Int) {
            // Partial paths are per frame and never outlive it, so the atlas is
            // wound back rather than allowed to grow for the whole reveal.
            while (shapes.size > shapeFloor) shapes.removeAt(shapes.size - 1)

            val alpha = (k + 1).toDouble() / frames
            val revealed = ArrayList<Inst>(base.size)
            for ((index, inst) in base.withIndex()) {
                val start = index * lag * window
                val local = ((alpha - start) / window).coerceIn(0.0, 1.0)
                if (local <= 0.0) continue
                if (local >= 1.0) {
                    revealed.add(inst)
                    continue
                }
                if (sequential) {
                    // Create on a group: a plain partial reveal, eased.
                    val partial = Verbs.pointwiseBecomePartial(shapes[inst.atlasId], 0.0, Verbs.smooth(local))
                    shapes.add(partial)
                    revealed.add(Inst(shapes.size - 1, inst.transform, inst.fill, inst.stroke, inst.width))
                } else {
                    revealed.add(drawBorderThenFill(inst, local))
                }
            }
            obj.instances = revealed
            emit()
        }

        override fun exit() {
            while (shapes.size > shapeFloor) shapes.removeAt(shapes.size - 1)
            obj.instances = base.toMutableList()
        }

        /**
         * One child of a Write, at [local] along its own clock.
         *
         * Manim's Write is DrawBorderThenFill on a linear clock, and the two
         * phases are what the name says. The first half draws the child's
         * *outline* -- a copy with the fill switched off and a width-2 stroke
         * in the child's own colour -- as a partial path, twice as fast as the
         * clock. The second half puts the whole outline down and interpolates
         * it into the finished child, so the fill fades in as the outline
         * stroke thins away.
         *
         * Modelling it as one eased partial reveal, which is what Create does,
         * put the pen a long way behind Manim's: at the start of the sample
         * scene, where a few strokes are all there is to disagree about, Manim
         * had 36% of a glyph down where we had 3%.
         */
        private fun drawBorderThenFill(inst: Inst, local: Double): Inst {
            // Manim's get_stroke_color: the stroke colour where there is a
            // stroke, the mobject's own colour otherwise. Text carries no
            // stroke, so its outline is drawn in the fill colour.
            val source = if (inst.width > 0.0) inst.stroke else inst.fill
            val outline = intArrayOf(source[0], source[1], source[2], 255)

            if (local < 0.5) {
                val partial = Verbs.pointwiseBecomePartial(shapes[inst.atlasId], 0.0, 2.0 * local)
                shapes.add(partial)
                return Inst(
                    shapes.size - 1,
                    inst.transform,
                    intArrayOf(inst.fill[0], inst.fill[1], inst.fill[2], 0),
                    outline,
                    OUTLINE_STROKE_WIDTH,
                )
            }

            // integerInterpolate(0, 2, local) lands in the upper half: the
            // shape is whole and only the style is still moving.
            val t = 2.0 * local - 1.0
            // floor(x + 0.5), not Math.round: Python rounds halves to even
            // and Java rounds them up, and the two interpreters have to agree
            // on every byte. Every value here is a non-negative channel.
            val stroke = IntArray(4) {
                (outline[it] + (inst.stroke[it] - outline[it]) * t + 0.5).toInt()
            }
            return Inst(
                inst.atlasId,
                inst.transform,
                intArrayOf(
                    inst.fill[0], inst.fill[1], inst.fill[2],
                    (inst.fill[3] * t + 0.5).toInt(),
                ),
                stroke,
                OUTLINE_STROKE_WIDTH + (inst.width - OUTLINE_STROKE_WIDTH) * t,
            )
        }
    }

    /**
     * Manim's LaggedStart(*[GrowFromCenter(child) ...], lag_ratio=r).
     *
     * GrowFromCenter interpolates from a zero-size copy at the child's centre,
     * which point by point is c + alpha*(p - c) -- a uniform scale about c,
     * composable onto whatever transform the instance already carries, so
     * nothing extra is shipped. The run lengths do have to be: a baked group is
     * a flat instance list with no notion of which faces are which sphere.
     */
    private fun laggedGrowRunner(step: Step.LaggedGrow) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private lateinit var base: List<Inst>
        private var flags: IntArray? = null
        private var normals: Array<DoubleArray?>? = null
        private lateinit var spans: List<IntArray>
        private lateinit var centres: List<DoubleArray>
        private var window = 0.0

        override fun enter() {
            obj = objects.getValue(step.name)
            obj.visible = true
            base = obj.instances.toList()
            flags = obj.flags
            normals = obj.normals

            val built = ArrayList<IntArray>()
            var cursor = 0
            for (size in step.groups) {
                built.add(intArrayOf(cursor, cursor + size))
                cursor += size
            }
            require(cursor == base.size) {
                "laggedgrow ${step.name}: groups cover $cursor instances, asset has ${base.size}"
            }
            spans = built

            // Centres are measured, not shipped: the geometry already knows them.
            centres = spans.map { span -> boundsCentre(base, span[0], span[1]) }
            window = 1.0 / (1.0 + step.lag * (maxOf(spans.size, 1) - 1))
        }

        override fun render(k: Int) {
            val alpha = (k + 1).toDouble() / frames
            val grown = ArrayList<Inst>()
            val kept = ArrayList<Int>()
            for ((groupIndex, span) in spans.withIndex()) {
                val start = groupIndex * step.lag * window
                val local = ((alpha - start) / window).coerceIn(0.0, 1.0)
                if (local <= 0.0) continue
                val scale = Verbs.smooth(local)
                val centre = centres[groupIndex]
                val grow = DoubleArray(12)
                grow[0] = scale; grow[5] = scale; grow[10] = scale
                grow[3] = (1 - scale) * centre[0]
                grow[7] = (1 - scale) * centre[1]
                grow[11] = (1 - scale) * centre[2]
                for (index in span[0] until span[1]) {
                    val inst = base[index]
                    grown.add(Inst(inst.atlasId, compose(grow, inst.transform), inst.fill, inst.stroke, inst.width))
                    kept.add(index)
                }
            }
            // Flags and normals are indexed by position, so dropping the
            // not-yet-grown children would shade each sphere with another's.
            obj.instances = grown
            flags?.let { f -> obj.flags = IntArray(kept.size) { f[kept[it]] } }
            normals?.let { n -> obj.normals = Array(kept.size) { n[kept[it]] } }
            emit()
        }

        override fun exit() {
            obj.instances = base.toMutableList()
            obj.flags = flags
            obj.normals = normals
        }
    }

    private fun fadeRunner(name: String, seconds: Double, fadingIn: Boolean) = object : Runner {
        override val frames = frames(seconds)
        private lateinit var obj: Obj
        private var base: List<Inst>? = null

        override fun enter() {
            objects[name]?.visible = true
            // A declared shape only enters the scene when something animates it
            // in; fade is one of those entry points, not just create.
            if (fadingIn && name !in objects) {
                val spec = program.shapes.getValue(name)
                objects[name] = Obj(
                    kind = "shape", visible = true, points = geometryFor(spec), alpha = 0.0,
                    strokeRgb = spec.stroke, width = spec.width,
                )
            }
            obj = objects.getValue(name)
            base = if (obj.kind == "asset") obj.instances.toList() else null
        }

        override fun render(k: Int) {
            val progress = Verbs.smooth((k + 1).toDouble() / frames)
            val alpha = if (fadingIn) progress else 1.0 - progress
            val held = base
            if (held == null) {
                obj.alpha = alpha
            } else {
                obj.instances = held.mapTo(ArrayList()) { inst ->
                    Inst(
                        inst.atlasId, inst.transform,
                        intArrayOf(inst.fill[0], inst.fill[1], inst.fill[2], (inst.fill[3] * alpha).toInt()),
                        intArrayOf(inst.stroke[0], inst.stroke[1], inst.stroke[2], (inst.stroke[3] * alpha).toInt()),
                        inst.width,
                    )
                }
            }
            emit()
        }

        override fun exit() {
            val held = base
            if (held == null) {
                if (fadingIn) obj.alpha = 1.0 else objects.remove(name)
            } else {
                obj.instances = if (fadingIn) held.toMutableList() else ArrayList()
            }
        }
    }

    /**
     * Glyph-level matching. Instances sharing a library glyph id pair up in
     * order; anything left over on either side fades rather than morphing into
     * an unrelated shape -- the correspondence TransformMatchingTex computes
     * from TeX structure, recovered here from the shared atlas.
     */
    private fun morphRunner(step: Step.Morph) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var src: Obj
        private lateinit var dst: Obj
        private lateinit var pairs: List<IntArray>
        private lateinit var orphans: List<Int>
        private lateinit var arrivals: List<Int>
        private lateinit var srcBase: List<Inst>
        private lateinit var dstBase: List<Inst>

        override fun enter() {
            src = objects.getValue(step.source)
            dst = objects.getValue(step.target)
            src.visible = true
            dst.visible = false

            val pending = LinkedHashMap<Int, ArrayDeque<Int>>()
            dst.glyphIds!!.forEachIndexed { index, glyph ->
                pending.getOrPut(glyph) { ArrayDeque() }.addLast(index)
            }
            val matched = ArrayList<IntArray>()
            val unmatched = ArrayList<Int>()
            src.glyphIds!!.forEachIndexed { index, glyph ->
                val queue = pending[glyph]
                if (queue != null && queue.isNotEmpty()) matched.add(intArrayOf(index, queue.removeFirst()))
                else unmatched.add(index)
            }
            pairs = matched
            orphans = unmatched
            arrivals = pending.values.flatten()
            srcBase = src.instances.toList()
            dstBase = dst.instances.toList()
        }

        override fun render(k: Int) {
            val alpha = Verbs.smooth((k + 1).toDouble() / frames)
            val fadeOut = 1.0 - alpha
            val built = ArrayList<Inst>()
            for (pair in pairs) {
                val a = srcBase[pair[0]]
                val b = dstBase[pair[1]]
                built.add(
                    Inst(
                        a.atlasId,
                        DoubleArray(12) { a.transform[it] + (b.transform[it] - a.transform[it]) * alpha },
                        IntArray(4) { pyRound(a.fill[it] + (b.fill[it] - a.fill[it]) * alpha) },
                        IntArray(4) { pyRound(a.stroke[it] + (b.stroke[it] - a.stroke[it]) * alpha) },
                        a.width + (b.width - a.width) * alpha,
                    )
                )
            }
            for (index in orphans) {
                val a = srcBase[index]
                built.add(
                    Inst(
                        a.atlasId, a.transform,
                        intArrayOf(a.fill[0], a.fill[1], a.fill[2], (a.fill[3] * fadeOut).toInt()),
                        intArrayOf(a.stroke[0], a.stroke[1], a.stroke[2], (a.stroke[3] * fadeOut).toInt()),
                        a.width,
                    )
                )
            }
            for (index in arrivals) {
                val b = dstBase[index]
                built.add(
                    Inst(
                        b.atlasId, b.transform,
                        intArrayOf(b.fill[0], b.fill[1], b.fill[2], (b.fill[3] * alpha).toInt()),
                        intArrayOf(b.stroke[0], b.stroke[1], b.stroke[2], (b.stroke[3] * alpha).toInt()),
                        b.width,
                    )
                )
            }
            src.instances = built
            emit()
        }

        override fun exit() {
            src.instances = dstBase.toMutableList()
            src.glyphIds = dst.glyphIds!!.copyOf()

            // Manim's TransformMatchingTex leaves the *target* on stage and
            // takes the source off it. The blend is carried by the source
            // object, so without this the source stayed visible holding the
            // target's content while the target's own trailing `show` drew the
            // same thing again -- harmless for one morph, and cumulative for a
            // chain of them. Three morphs left three stale equations
            // superimposed on the fourth.
            src.visible = false
            dst.visible = true
        }
    }

    private fun moveRunner(step: Step.Move) = object : Runner {
        override val frames = frames(step.seconds)
        private var startPhi = 0.0
        private var startTheta = 0.0

        override fun enter() {
            startPhi = phi
            startTheta = theta
        }

        override fun render(k: Int) {
            val alpha = Verbs.smooth((k + 1).toDouble() / frames)
            phi = startPhi + (step.phi - startPhi) * alpha
            theta = startTheta + (step.theta - startTheta) * alpha
            emit()
        }

        override fun exit() {}
    }

    /**
     * Manim's ambient rotation advances once per frame except on the wait's
     * last frame, which repeats the previous orientation. Measured on two
     * scenes. Without it the trailing hold sits 0.57 deg out for a whole
     * second -- where the fidelity harness never looks.
     *
     * Resumable form: theta at frame k is a closed form off the verb's start,
     * so a seek inside a spin does not have to replay it.
     */
    private fun spinRunner(step: Step.Spin) = object : Runner {
        override val frames = frames(step.seconds)
        private var startTheta = 0.0

        override fun enter() {
            startTheta = theta
        }

        override fun render(k: Int) {
            val advances = minOf(k + 1, maxOf(frames - 1, 0))
            theta = startTheta + advances * step.rate / fps
            emit()
        }

        override fun exit() {
            theta = startTheta + maxOf(frames - 1, 0) * step.rate / fps
        }
    }

    private fun boundsCentre(instances: List<Inst>, from: Int, until: Int): DoubleArray {
        var minX = Double.MAX_VALUE; var minY = Double.MAX_VALUE; var minZ = Double.MAX_VALUE
        var maxX = -Double.MAX_VALUE; var maxY = -Double.MAX_VALUE; var maxZ = -Double.MAX_VALUE
        for (index in from until until) {
            val inst = instances[index]
            val pts = shapes[inst.atlasId]
            var i = 0
            while (i < pts.size) {
                val x = inst.transform[0] * pts[i] + inst.transform[1] * pts[i + 1] + inst.transform[2] * pts[i + 2] + inst.transform[3]
                val y = inst.transform[4] * pts[i] + inst.transform[5] * pts[i + 1] + inst.transform[6] * pts[i + 2] + inst.transform[7]
                val z = inst.transform[8] * pts[i] + inst.transform[9] * pts[i + 1] + inst.transform[10] * pts[i + 2] + inst.transform[11]
                if (x < minX) minX = x; if (x > maxX) maxX = x
                if (y < minY) minY = y; if (y > maxY) maxY = y
                if (z < minZ) minZ = z; if (z > maxZ) maxZ = z
                i += 3
            }
        }
        return doubleArrayOf((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
    }
}
