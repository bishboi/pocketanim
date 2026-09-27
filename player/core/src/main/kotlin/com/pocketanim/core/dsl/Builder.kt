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
    val background = program.background
    val is3d = program.is3d
    private val shapes = ArrayList<DoubleArray>()
    private val objects = LinkedHashMap<String, Obj>()

    private var phi = program.phi
    private var theta = program.theta
    private var zoom = program.zoom

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
                z = program.z[name] ?: 0.0,
            )
        }
    }

    /** A declared primitive entering the stage. */
    private fun newShape(name: String, alpha: Double = 1.0): Obj {
        val spec = program.shapes.getValue(name)
        return Obj(
            kind = "shape", visible = true, points = geometryFor(spec), alpha = alpha,
            strokeRgb = spec.stroke, width = spec.width, z = program.z[name] ?: 0.0,
        )
    }

    // ---- emit -------------------------------------------------------------

    private fun cameraRecord(): FloatArray {
        val m = Interpreter.cameraMatrix(phi, theta)
        val out = FloatArray(Panm.CAMERA_FLOATS)
        out[3] = FOCAL; out[4] = zoom.toFloat()
        for (k in 0 until 9) out[5 + k] = m[k].toFloat()
        out[14] = -7f; out[15] = -9f; out[16] = 10f
        return out
    }

    /**
     * Where the last emit started appending primitive geometry, and where it
     * stopped. A primitive's points go into the atlas at emit time and only the
     * frame just produced refers to them, so if nothing was appended since,
     * they can be wound back before the next emit appends its own. Without
     * this every visible primitive added a shape per frame for the life of the
     * scene -- unbounded growth over a lecture of holds.
     */
    private var emitStart = -1
    private var emitEnd = -1

    private fun emit() {
        if (emitEnd >= 0 && shapes.size == emitEnd && emitStart in 0..emitEnd) {
            while (shapes.size > emitStart) shapes.removeAt(shapes.size - 1)
        }
        emitStart = shapes.size
        val frame = ArrayList<Instance>()
        // Stable: equal z keeps declaration order, which is every program
        // written before `z=` existed.
        for (obj in objects.values.filter { it.visible }.sortedBy { it.z }) {
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
                        fill = argbOf(
                            intArrayOf(obj.fill[0], obj.fill[1], obj.fill[2], (obj.fill[3] * obj.alpha).toInt())
                        ),
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
        emitEnd = shapes.size
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

    private fun foldComposites(steps: List<Step>): List<Step> {
        val folded = ArrayList<Step>()
        var cursor = 0
        while (cursor < steps.size) {
            val step = steps[cursor]
            cursor++
            when (step) {
                is Step.Par -> {
                    val members = ArrayList<Step>()
                    val carried = ArrayList<Step>()
                    while (members.size < step.count && cursor < steps.size) {
                        val next = steps[cursor]
                        cursor++
                        if (next is Step.Show || next is Step.Hide) carried.add(next) else members.add(next)
                    }
                    if (members.isNotEmpty()) folded.add(Step.Parallel(foldComposites(members)))
                    folded.addAll(carried)
                }
                is Step.LagHeader -> {
                    val members = ArrayList<Step>()
                    for (run in step.runs) {
                        val slice = ArrayList<Step>()
                        var left = run
                        while (left > 0 && cursor < steps.size) {
                            slice.add(steps[cursor])
                            cursor++
                            left--
                        }
                        val inner = foldComposites(slice)
                        if (inner.size == 1) members.add(inner[0])
                        else if (inner.isNotEmpty()) members.add(Step.Sequence(inner))
                    }
                    if (members.isNotEmpty()) folded.add(Step.Lag(step.ratio, step.seconds, members))
                }
                else -> folded.add(step)
            }
        }
        return folded
    }

    fun prepare() {
        declareSurfaces()
        declareAssets()

        // Rewrite create-on-asset to a lagged reveal in a PRE-PASS. Appending
        // the rewrite to the list being iterated pushed every asset reveal to
        // the end, so camera moves ran before the things they were looking at.
        val rewritten = program.timeline.map { step ->
            if (step is Step.Create && !step.removing && isAsset(step.name)) {
                Step.RevealSequence(step.name, step.seconds, step.lag ?: 1.0)
            }
            else step
        }

        val folded = foldComposites(rewritten)

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
        emitStart = -1
        emitEnd = -1
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

    /**
     * Frames Manim renders for an animation: len(np.arange(0, t, 1/fps)), a
     * ceiling. (t * fps).toInt() agreed only on whole frames, and a narrated
     * beat never is one, so a lecture ran a frame short per play.
     */
    private fun frames(seconds: Double) =
        if (seconds <= 0.0) 0 else kotlin.math.ceil(seconds / (1.0 / fps)).toInt()

    /** Frames Manim writes for a static wait: freeze_current_frame's int(d / dt). */
    private fun waitFrames(seconds: Double) =
        if (seconds <= 0.0) 0 else (seconds / (1.0 / fps)).toInt()

    private fun runnerFor(step: Step): Runner = when (step) {
        is Step.Create -> createRunner(step)
        is Step.Transform -> transformRunner(step)
        is Step.Xform -> xformRunner(step)
        is Step.Stroke -> strokeRunner(step)
        is Step.Grow -> growRunner(step)
        is Step.Write -> revealRunner(step.name, step.seconds, sequential = false)
        is Step.Fill -> fillRunner(step)
        is Step.Unwrite -> unwriteRunner(step)
        is Step.RevealSequence -> revealRunner(step.name, step.seconds, sequential = true, sequenceLag = step.lag)
        is Step.LaggedGrow -> laggedGrowRunner(step)
        is Step.Fade -> fadeRunner(step.name, step.seconds, fadingIn = true, step.shift, step.from)
        is Step.FadeOut -> fadeRunner(step.name, step.seconds, fadingIn = false, step.shift, step.from)
        is Step.Rotate -> rotateRunner(step)
        is Step.Indicate -> indicateRunner(step)
        is Step.Morph -> morphRunner(step)
        is Step.Move -> moveRunner(step)
        is Step.Spin -> spinRunner(step)
        is Step.Wait -> holdRunner(waitFrames(step.seconds))
        is Step.Parallel -> parallelRunner(step.members.map { runnerFor(it) })
        is Step.Lag -> lagRunner(step)
        is Step.Sequence -> sequenceRunner(step.members.map { runnerFor(it) })
        is Step.Par, is Step.LagHeader -> holdRunner(0)
        is Step.Show, is Step.Hide -> holdRunner(0)
    }

    /**
     * Several verbs over one clock.
     *
     * The Runner contract composes without help: enter them all, render frame
     * k of each, exit them all. A member shorter than the group holds its last
     * frame rather than disappearing, which is what Manim does when one
     * animation in a `play()` finishes before another.
     */
    private fun sequenceRunner(children: List<Runner>) = object : Runner {
        override val frames = children.sumOf { it.frames }
        /**
         * Children enter in turn. Entering them all at the start let a later
         * child capture the scene before an earlier one had changed it -- a
         * fade-in followed by a fade-out on the same object captured the
         * object before it was on stage.
         */
        private var reached = -1

        override fun enter() {
            reached = -1
        }

        private fun reach(index: Int) {
            while (reached < index) {
                if (reached >= 0) children[reached].let { if (it.frames > 0) it.render(it.frames - 1); it.exit() }
                reached++
                children[reached].enter()
            }
        }

        override fun render(k: Int) {
            var left = k
            for ((index, child) in children.withIndex()) {
                if (child.frames <= 0) continue
                if (left < child.frames || index == children.lastIndex) {
                    reach(index)
                    child.render(minOf(left, child.frames - 1))
                    return
                }
                left -= child.frames
            }
        }

        override fun exit() {
            if (children.isEmpty()) return
            reach(children.lastIndex)
            children.last().exit()
        }
    }

    private fun lagRunner(step: Step.Lag): Runner {
        val children = step.members.map { runnerFor(it) }
        return object : Runner {
            override val frames = frames(step.seconds)
            /**
             * A child enters when its turn starts, not when the group does.
             * Entering them all up front put every later child on stage at
             * full opacity before its fade began -- all four lines of a
             * chapter card drawn at once, then faded in again one by one.
             * Manim begins each child at its alpha-0 state, which for a fade,
             * a grow or a create draws nothing.
             */
            private val entered = BooleanArray(children.size)

            override fun enter() = entered.fill(false)

            override fun render(k: Int) {
                val runTimes = children.map { it.frames.toDouble() / fps }
                val starts = DoubleArray(children.size)
                for (i in 1 until children.size) {
                    starts[i] = starts[i - 1] + runTimes[i - 1] * step.ratio
                }
                val maxEnd = children.indices.maxOfOrNull { starts[it] + runTimes[it] } ?: 1.0
                val internal = (k + 1).toDouble() / frames.coerceAtLeast(1) * maxEnd.coerceAtLeast(1e-6)
                children.forEachIndexed { i, child ->
                    if (child.frames <= 0 || runTimes[i] <= 0.0) return@forEachIndexed
                    val local = ((internal - starts[i]) / runTimes[i]).coerceIn(0.0, 1.0)
                    if (local <= 0.0) return@forEachIndexed
                    if (!entered[i]) {
                        entered[i] = true
                        child.enter()
                    }
                    child.render(((local * child.frames).toInt() - 1).coerceIn(0, child.frames - 1))
                }
                emit()
            }

            override fun exit() {
                children.forEachIndexed { i, child ->
                    if (!entered[i]) {
                        entered[i] = true
                        child.enter()
                        if (child.frames > 0) child.render(child.frames - 1)
                    }
                    child.exit()
                }
            }
        }
    }

    /**
     * Manim begins every animation in a play() before interpolating any, so
     * all members enter first: two verbs on one object each capture it as it
     * was before either touched it. A member shorter than the group holds its
     * last frame rather than disappearing.
     */
    private fun parallelRunner(children: List<Runner>) = object : Runner {
        override val frames = children.maxOfOrNull { it.frames } ?: 0
        override fun enter() = children.forEach { it.enter() }
        override fun render(k: Int) =
            children.forEach { it.render(minOf(k, it.frames - 1).coerceAtLeast(0)) }
        override fun exit() = children.forEach { it.exit() }
    }

    private fun holdRunner(count: Int) = object : Runner {
        override val frames = count
        override fun enter() {}
        override fun render(k: Int) = emit()
        override fun exit() {}
    }

    private fun createRunner(step: Step.Create) = object : Runner {
        override val frames = frames(step.seconds)
        private val rate = Verbs.rate(step.rate)
        private lateinit var full: DoubleArray
        private lateinit var obj: Obj

        override fun enter() {
            obj = newShape(step.name)
            full = obj.points!!
            objects[step.name] = obj
        }

        override fun render(k: Int) {
            var alpha = rate((k + 1).toDouble() / frames)
            if (step.removing) alpha = 1.0 - alpha
            obj.points = Verbs.pointwiseBecomePartial(full, 0.0, alpha)
            emit()
        }

        override fun exit() {
            if (step.removing) {
                obj.points = DoubleArray(full.size)
                obj.visible = false
            } else {
                obj.points = full
            }
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
            val bulge = kotlin.math.sin(Math.PI * alpha) * step.arc
            val out = DoubleArray(startPts.size)
            var i = 0
            while (i < out.size) {
                val dx = endPts[i] - startPts[i]
                val dy = endPts[i + 1] - startPts[i + 1]
                out[i] = startPts[i] + dx * alpha - dy * bulge
                out[i + 1] = startPts[i + 1] + dy * alpha + dx * bulge
                out[i + 2] = startPts[i + 2] + (endPts[i + 2] - startPts[i + 2]) * alpha
                i += 3
            }
            obj.points = out
            obj.strokeRgb = (0 until 3).fold(0) { acc, i ->
                (acc shl 8) or pyRound(c0[i] + (c1[i] - c0[i]) * alpha).coerceIn(0, 255)
            }
            emit()
        }

        override fun exit() {}
    }

    /**
     * GrowFromCenter: points scale up from a centre. A primitive scales its
     * points; an asset scales its instances. The asset branch mirrors the
     * reference -- programs from before `laggedgrow` covered groups carry
     * `grow` on an asset, and this threw on the missing points.
     */
    private fun growRunner(step: Step.Grow) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private var base: DoubleArray? = null
        private var baseInstances: List<Inst>? = null
        private lateinit var centre: DoubleArray

        override fun enter() {
            if (step.name !in objects) objects[step.name] = newShape(step.name)
            obj = objects.getValue(step.name)
            obj.visible = true
            val forced = step.at
            if (obj.kind == "asset") {
                val held = obj.instances.toList()
                baseInstances = held
                centre = if (forced != null) {
                    doubleArrayOf(forced[0], forced[1], if (forced.size > 2) forced[2] else 0.0)
                } else if (held.isEmpty()) DoubleArray(3) else boundsCentre(held, 0, held.size)
                return
            }
            val points = obj.points!!.copyOf()
            base = points
            centre = if (forced != null) {
                doubleArrayOf(forced[0], forced[1], if (forced.size > 2) forced[2] else 0.0)
            } else boundsOfPoints(points)
        }

        override fun render(k: Int) {
            val scale = Verbs.smooth((k + 1).toDouble() / frames.coerceAtLeast(1))
            val held = baseInstances
            if (held != null) {
                val grow = DoubleArray(12)
                grow[0] = scale; grow[5] = scale; grow[10] = scale
                grow[3] = (1 - scale) * centre[0]
                grow[7] = (1 - scale) * centre[1]
                grow[11] = (1 - scale) * centre[2]
                obj.instances = held.mapTo(ArrayList()) {
                    Inst(it.atlasId, compose(grow, it.transform), it.fill, it.stroke, it.width)
                }
                emit()
                return
            }
            val points = base!!
            val out = points.copyOf()
            var i = 0
            while (i < out.size) {
                out[i] = centre[0] + (points[i] - centre[0]) * scale
                out[i + 1] = centre[1] + (points[i + 1] - centre[1]) * scale
                out[i + 2] = centre[2] + (points[i + 2] - centre[2]) * scale
                i += 3
            }
            obj.points = out
            emit()
        }

        override fun exit() {
            baseInstances?.let { obj.instances = it.toMutableList() }
            base?.let { obj.points = it }
        }
    }

    private fun strokeRunner(step: Step.Stroke) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private var startRgb = IntArray(3)
        private var startWidth = 0.0
        private var startAlpha = 1.0
        private var base: List<Inst>? = null

        override fun enter() {
            obj = objects.getValue(step.name)
            if (obj.kind == "shape") {
                startRgb = intArrayOf(
                    (obj.strokeRgb shr 16) and 0xFF,
                    (obj.strokeRgb shr 8) and 0xFF,
                    obj.strokeRgb and 0xFF,
                )
                startWidth = obj.width
                startAlpha = obj.alpha
            } else {
                base = obj.instances.toList()
            }
        }

        override fun render(k: Int) {
            val alpha = Verbs.smooth((k + 1).toDouble() / frames)
            if (obj.kind == "shape") {
                val end = step.color
                val rgb = IntArray(3) { i ->
                    val target = if (end == null) startRgb[i] else (end shr (16 - 8 * i)) and 0xFF
                    pyRound(startRgb[i] + (target - startRgb[i]) * alpha)
                }
                obj.strokeRgb = (rgb[0] shl 16) or (rgb[1] shl 8) or rgb[2]
                val width = step.width ?: startWidth
                obj.width = startWidth + (width - startWidth) * alpha
                val opacity = step.opacity ?: startAlpha
                obj.alpha = startAlpha + (opacity - startAlpha) * alpha
            } else {
                obj.instances = base!!.mapTo(ArrayList()) { inst ->
                    val rgb = IntArray(3) { i ->
                        val target = step.color?.let { (it shr (16 - 8 * i)) and 0xFF } ?: inst.stroke[i]
                        pyRound(inst.stroke[i] + (target - inst.stroke[i]) * alpha)
                    }
                    val channel = if (step.opacity == null) inst.stroke[3]
                    else pyRound(inst.stroke[3] + (step.opacity * 255 - inst.stroke[3]) * alpha)
                    val width = if (step.width == null) inst.width
                    else inst.width + (step.width - inst.width) * alpha
                    Inst(
                        inst.atlasId, inst.transform, inst.fill,
                        intArrayOf(rgb[0], rgb[1], rgb[2], channel), width,
                    )
                }
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
    private fun revealRunner(
        name: String, seconds: Double, sequential: Boolean, sequenceLag: Double = 1.0,
    ) = object : Runner {
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
            lag = if (sequential) sequenceLag else minOf(4.0 / count, 0.2)
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

            val forced = step.at
            centres = if (forced != null) {
                val point = doubleArrayOf(forced[0], forced[1], if (forced.size > 2) forced[2] else 0.0)
                spans.map { point }
            } else {
                spans.map { span -> boundsCentre(base, span[0], span[1]) }
            }
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

    private fun fadeRunner(
        name: String, seconds: Double, fadingIn: Boolean,
        shift: DoubleArray, from: Double,
    ) = object : Runner {
        override val frames = frames(seconds)
        private lateinit var obj: Obj
        private var base: List<Inst>? = null
        private var rest: DoubleArray? = null
        private var centre = doubleArrayOf(0.0, 0.0, 0.0)
        private var baseXform = identity()
        private var moves = false
        // Manim's _Fade starts FadeIn from a copy shifted by -shift and ends
        // FadeOut at +shift. FadeIn used to travel +shift here, so things rose
        // into place from above instead of from below.
        private val sign = if (fadingIn) -1.0 else 1.0

        override fun enter() {
            objects[name]?.visible = true
            // A declared shape only enters the scene when something animates it
            // in; fade is one of those entry points, not just create.
            if (fadingIn && name !in objects) objects[name] = newShape(name, alpha = 0.0)
            obj = objects.getValue(name)
            base = if (obj.kind == "asset") obj.instances.toList() else null
            moves = shift[0] != 0.0 || shift[1] != 0.0 || from != 1.0
            if (obj.kind == "shape") {
                rest = obj.points!!.copyOf()
                centre = boundsOfPoints(rest!!)
            } else {
                baseXform = obj.xform.copyOf()
                if (moves) {
                    val world = base!!.map { Inst(it.atlasId, compose(baseXform, it.transform), it.fill, it.stroke, it.width) }
                    centre = boundsCentre(world, 0, world.size)
                }
            }
        }

        override fun render(k: Int) {
            val progress = Verbs.smooth((k + 1).toDouble() / frames)
            val alpha = if (fadingIn) progress else 1.0 - progress
            val scale = from + (1.0 - from) * alpha
            val travel = sign * (1.0 - alpha)
            val held = base
            if (held == null) {
                obj.alpha = alpha
                val points = rest
                if (points != null) {
                    val out = points.copyOf()
                    var i = 0
                    while (i < out.size) {
                        out[i] = centre[0] + (points[i] - centre[0]) * scale + shift[0] * travel
                        out[i + 1] = centre[1] + (points[i + 1] - centre[1]) * scale + shift[1] * travel
                        out[i + 2] = centre[2] + (points[i + 2] - centre[2]) * scale
                        i += 3
                    }
                    obj.points = out
                }
            } else {
                if (moves) {
                    val m = DoubleArray(12)
                    m[0] = scale; m[5] = scale; m[10] = scale
                    m[3] = (1 - scale) * centre[0] + shift[0] * travel
                    m[7] = (1 - scale) * centre[1] + shift[1] * travel
                    m[11] = (1 - scale) * centre[2]
                    obj.xform = compose(m, baseXform)
                }
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
                if (fadingIn) {
                    obj.alpha = 1.0
                    rest?.let { obj.points = it }
                } else objects.remove(name)
            } else {
                obj.xform = baseXform
                obj.instances = if (fadingIn) held.toMutableList() else ArrayList()
            }
        }
    }

    /**
     * `.animate.set_fill`. set_fill reaches the whole family, members with no
     * fill included, so every instance moves to the given colour and opacity.
     */
    private fun fillRunner(step: Step.Fill) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private var base: List<Inst>? = null
        private var start = IntArray(4)
        private var end = DoubleArray(4)

        override fun enter() {
            obj = objects.getValue(step.name)
            if (obj.kind == "shape") {
                start = obj.fill.copyOf()
                end = DoubleArray(4) { start[it].toDouble() }
                step.color?.let { c -> for (i in 0 until 3) end[i] = ((c shr (16 - 8 * i)) and 0xFF).toDouble() }
                step.opacity?.let { end[3] = it * 255 }
            } else {
                base = obj.instances.toList()
            }
        }

        override fun render(k: Int) {
            val alpha = Verbs.smooth((k + 1).toDouble() / frames.coerceAtLeast(1))
            val held = base
            if (held == null) {
                obj.fill = IntArray(4) { (start[it] + (end[it] - start[it]) * alpha + 0.5).toInt() }
            } else {
                obj.instances = held.mapTo(ArrayList()) { inst ->
                    val rgb = IntArray(3) { i ->
                        val target = step.color?.let { (it shr (16 - 8 * i)) and 0xFF } ?: return@IntArray inst.fill[i]
                        (inst.fill[i] + (target - inst.fill[i]) * alpha + 0.5).toInt()
                    }
                    val channel = if (step.opacity == null) inst.fill[3]
                    else (inst.fill[3] + (step.opacity * 255 - inst.fill[3]) * alpha + 0.5).toInt()
                    Inst(inst.atlasId, inst.transform, intArrayOf(rgb[0], rgb[1], rgb[2], channel), inst.stroke, inst.width)
                }
            }
            emit()
        }

        override fun exit() {}
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
        private var startZoom = 1.0

        override fun enter() {
            startPhi = phi
            startTheta = theta
            startZoom = zoom
        }

        override fun render(k: Int) {
            val alpha = Verbs.smooth((k + 1).toDouble() / frames)
            step.phi?.let { phi = startPhi + (it - startPhi) * alpha }
            step.theta?.let { theta = startTheta + (it - startTheta) * alpha }
            step.zoom?.let { zoom = startZoom + (it - startZoom) * alpha }
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
        private var startPhi = 0.0

        override fun enter() {
            startTheta = theta
            startPhi = phi
        }

        override fun render(k: Int) {
            val advances = minOf(k + 1, maxOf(frames - 1, 0))
            val turned = advances * step.rate / fps
            if (step.about == "phi") phi = startPhi + turned else theta = startTheta + turned
            emit()
        }

        override fun exit() {
            val turned = maxOf(frames - 1, 0) * step.rate / fps
            if (step.about == "phi") phi = startPhi + turned else theta = startTheta + turned
        }
    }

    private fun boundsOfPoints(points: DoubleArray): DoubleArray {
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
        return doubleArrayOf((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
    }

    private fun rotateRunner(step: Step.Rotate) = object : Runner {
        override val frames = frames(step.seconds)
        private val rate = Verbs.rate(step.rate)
        private lateinit var obj: Obj
        private var basePoints: DoubleArray? = null
        private var baseInst: List<Inst>? = null

        override fun enter() {
            obj = objects.getValue(step.name)
            if (obj.kind == "shape") basePoints = obj.points!!.copyOf()
            else baseInst = obj.instances.toList()
        }

        override fun render(k: Int) {
            val ang = step.radians * rate((k + 1).toDouble() / frames)
            val c = kotlin.math.cos(ang)
            val s = kotlin.math.sin(ang)
            val ox = step.at[0]
            val oy = if (step.at.size > 1) step.at[1] else 0.0
            val points = basePoints
            if (points != null) {
                val out = points.copyOf()
                var i = 0
                while (i < out.size) {
                    val x = points[i] - ox
                    val y = points[i + 1] - oy
                    out[i] = c * x - s * y + ox
                    out[i + 1] = s * x + c * y + oy
                    i += 3
                }
                obj.points = out
            } else {
                val rot = doubleArrayOf(
                    c, -s, 0.0, ox * (1 - c) + oy * s,
                    s, c, 0.0, oy * (1 - c) - ox * s,
                    0.0, 0.0, 1.0, 0.0,
                )
                obj.instances = baseInst!!.mapTo(ArrayList()) { inst ->
                    Inst(inst.atlasId, compose(rot, inst.transform), inst.fill, inst.stroke, inst.width)
                }
            }
            emit()
        }

        override fun exit() {
            basePoints?.let { obj.points = it }
            baseInst?.let { obj.instances = it.toMutableList() }
        }
    }

    private fun indicateRunner(step: Step.Indicate) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private var basePoints: DoubleArray? = null
        private var baseInst: List<Inst>? = null
        private var centre = doubleArrayOf(0.0, 0.0, 0.0)

        override fun enter() {
            obj = objects.getValue(step.name)
            if (obj.kind == "shape") {
                basePoints = obj.points!!.copyOf()
                centre = boundsOfPoints(basePoints!!)
            } else {
                baseInst = obj.instances.toList()
                centre = boundsCentre(baseInst!!, 0, baseInst!!.size)
            }
        }

        override fun render(k: Int) {
            val pulse = Verbs.thereAndBack((k + 1).toDouble() / frames)
            val scale = 1.0 + 0.2 * pulse
            val points = basePoints
            if (points != null) {
                val out = points.copyOf()
                var i = 0
                while (i < out.size) {
                    out[i] = centre[0] + (points[i] - centre[0]) * scale
                    out[i + 1] = centre[1] + (points[i + 1] - centre[1]) * scale
                    out[i + 2] = centre[2] + (points[i + 2] - centre[2]) * scale
                    i += 3
                }
                obj.points = out
            } else {
                val grow = doubleArrayOf(
                    scale, 0.0, 0.0, (1 - scale) * centre[0],
                    0.0, scale, 0.0, (1 - scale) * centre[1],
                    0.0, 0.0, scale, (1 - scale) * centre[2],
                )
                obj.instances = baseInst!!.mapTo(ArrayList()) { inst ->
                    Inst(inst.atlasId, compose(grow, inst.transform), inst.fill, inst.stroke, inst.width)
                }
            }
            emit()
        }

        override fun exit() {
            basePoints?.let { obj.points = it }
            baseInst?.let { obj.instances = it.toMutableList() }
        }
    }

    private fun unwriteRunner(step: Step.Unwrite) = object : Runner {
        override val frames = frames(step.seconds)
        private lateinit var obj: Obj
        private lateinit var base: List<Inst>

        override fun enter() {
            obj = objects.getValue(step.name)
            obj.visible = true
            base = obj.instances.toList()
        }

        override fun render(k: Int) {
            val count = maxOf(base.size, 1)
            val lag = minOf(4.0 / count, 0.2)
            val span = 1.0 / (1.0 + lag * (count - 1))
            val alpha = 1.0 - (k + 1).toDouble() / frames
            val revealed = ArrayList<Inst>()
            for ((i, inst) in base.withIndex()) {
                val start = i * lag * span
                val local = ((alpha - start) / span).coerceIn(0.0, 1.0)
                if (local > 0.0) revealed.add(inst)
            }
            obj.instances = revealed
            emit()
        }

        override fun exit() {
            obj.instances = ArrayList()
            obj.visible = false
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
