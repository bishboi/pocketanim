package com.pocketanim.core.dsl

import com.pocketanim.core.Instance
import com.pocketanim.core.Panm
import com.pocketanim.core.Record
import com.pocketanim.core.Scene

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

    private val fps = program.fps
    private val is3d = program.is3d
    private val shapes = ArrayList<DoubleArray>()
    private val records = ArrayList<Record>()
    private val cameras = ArrayList<FloatArray>()
    private val objects = LinkedHashMap<String, Obj>()

    private var phi = program.phi
    private var theta = program.theta

    fun build(): Scene {
        declareSurfaces()
        declareAssets()
        runTimeline()

        val atlas = Array(shapes.size) { i -> FloatArray(shapes[i].size) { shapes[i][it].toFloat() } }
        return Scene(
            fps = fps,
            atlas = atlas,
            cameras = if (is3d) cameras.toTypedArray() else null,
            records = records.toTypedArray(),
            lo = FloatArray(3),
            hi = FloatArray(3),
        )
    }

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
        records.add(Record(Panm.REC_SNAPSHOT, frame.toTypedArray()))
        if (is3d) cameras.add(cameraRecord())
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

    private fun runTimeline() {
        // Rewrite create-on-asset to a lagged reveal in a PRE-PASS. Appending
        // the rewrite to the list being iterated pushed every asset reveal to
        // the end, so camera moves ran before the things they were looking at.
        val steps = program.timeline.map { step ->
            if (step is Step.Create && isAsset(step.name)) Step.RevealSequence(step.name, step.seconds)
            else step
        }

        // Manim renders the scene's opening state once at t=0, before the first
        // animation's first step. Without it every later frame is one early and
        // the closing frame is missing.
        var opened = false

        for (step in steps) {
            if (step is Step.Show) {
                objects.getValue(step.name).visible = true
                continue
            }
            if (!opened) {
                opened = true
                emit()
            }
            runStep(step)
        }
    }

    private fun frames(seconds: Double) = (seconds * fps).toInt()

    private fun runStep(step: Step) {
        when (step) {
            is Step.Create -> doCreate(step)
            is Step.Transform -> doTransform(step)
            is Step.Xform -> doXform(step)
            is Step.Write -> doReveal(step.name, step.seconds, sequential = false)
            is Step.RevealSequence -> doReveal(step.name, step.seconds, sequential = true)
            is Step.LaggedGrow -> doLaggedGrow(step)
            is Step.Fade -> doFade(step.name, step.seconds, fadingIn = true)
            is Step.FadeOut -> doFade(step.name, step.seconds, fadingIn = false)
            is Step.Morph -> doMorph(step)
            is Step.Move -> doMove(step)
            is Step.Spin -> doSpin(step)
            is Step.Wait -> repeat(frames(step.seconds)) { emit() }
            is Step.Show -> Unit
        }
    }

    private fun doCreate(step: Step.Create) {
        val rate = Verbs.rate(step.rate)
        val spec = program.shapes.getValue(step.name)
        val full = geometryFor(spec)
        val obj = Obj(
            kind = "shape", visible = true, points = full, alpha = 1.0,
            strokeRgb = spec.stroke, width = spec.width,
        )
        objects[step.name] = obj
        val total = frames(step.seconds)
        for (i in 0 until total) {
            obj.points = Verbs.pointwiseBecomePartial(full, 0.0, rate((i + 1).toDouble() / total))
            emit()
        }
        obj.points = full
    }

    private fun doTransform(step: Step.Transform) {
        val rate = Verbs.rate(step.rate)
        val obj = objects.getValue(step.source)
        val targetSpec = program.shapes.getValue(step.target)
        val (startPts, endPts) = Verbs.align(obj.points!!, geometryFor(targetSpec))
        val c0 = intArrayOf((obj.strokeRgb shr 16) and 0xFF, (obj.strokeRgb shr 8) and 0xFF, obj.strokeRgb and 0xFF)
        val c1 = intArrayOf((targetSpec.stroke shr 16) and 0xFF, (targetSpec.stroke shr 8) and 0xFF, targetSpec.stroke and 0xFF)

        val total = frames(step.seconds)
        for (i in 0 until total) {
            val alpha = rate((i + 1).toDouble() / total)
            val pts = DoubleArray(startPts.size) { startPts[it] + (endPts[it] - startPts[it]) * alpha }
            obj.points = pts
            obj.strokeRgb = (0 until 3).fold(0) { acc, k ->
                (acc shl 8) or pyRound(c0[k] + (c1[k] - c0[k]) * alpha).coerceIn(0, 255)
            }
            emit()
        }
    }

    /** Manim scales about the object's centre, then translates. */
    private fun doXform(step: Step.Xform) {
        val obj = objects.getValue(step.name)
        val base = obj.xform.copyOf()
        val centre = obj.centre
        val total = frames(step.seconds)
        for (i in 0 until total) {
            val alpha = Verbs.smooth((i + 1).toDouble() / total)
            val scale = 1.0 + (step.factor - 1.0) * alpha
            val m = DoubleArray(12)
            m[0] = scale; m[5] = scale; m[10] = scale
            m[3] = (1 - scale) * centre[0] + step.offsetXy[0] * alpha
            m[7] = (1 - scale) * centre[1] + step.offsetXy[1] * alpha
            m[11] = (1 - scale) * centre[2]
            obj.xform = compose(m, base)
            emit()
        }
    }

    /**
     * Manim lags each submobject. Write uses lag_ratio min(4/n, 0.2); Create on
     * a group uses 1.0, i.e. strictly one child at a time.
     */
    private fun doReveal(name: String, seconds: Double, sequential: Boolean) {
        val obj = objects[name] ?: throw IllegalStateException("reveal target '$name' was never declared")
        // Revealing a thing puts it on stage. Without this the object stayed
        // hidden for the whole reveal and appeared only at its trailing show.
        obj.visible = true
        val base = obj.instances.toList()
        val count = maxOf(base.size, 1)
        val lag = if (sequential) 1.0 else minOf(4.0 / count, 0.2)
        val window = 1.0 / (1.0 + lag * (count - 1))
        val total = frames(seconds)

        for (i in 0 until total) {
            val alpha = (i + 1).toDouble() / total
            val revealed = ArrayList<Inst>(base.size)
            for ((index, inst) in base.withIndex()) {
                val start = index * lag * window
                val local = ((alpha - start) / window).coerceIn(0.0, 1.0)
                if (local <= 0.0) continue
                if (local >= 1.0) {
                    revealed.add(inst)
                    continue
                }
                val partial = Verbs.pointwiseBecomePartial(shapes[inst.atlasId], 0.0, Verbs.smooth(local))
                shapes.add(partial)
                revealed.add(Inst(shapes.size - 1, inst.transform, inst.fill, inst.stroke, inst.width))
            }
            obj.instances = revealed
            emit()
        }
        obj.instances = base.toMutableList()
    }

    /**
     * Manim's LaggedStart(*[GrowFromCenter(child) ...], lag_ratio=r).
     *
     * GrowFromCenter interpolates from a zero-size copy at the child's centre,
     * which point by point is c + alpha*(p - c) -- a uniform scale about c,
     * composable onto whatever transform the instance already carries, so
     * nothing extra has to be shipped. The run lengths do have to be: a baked
     * group is a flat instance list with no notion of which faces are which
     * sphere.
     */
    private fun doLaggedGrow(step: Step.LaggedGrow) {
        val obj = objects.getValue(step.name)
        obj.visible = true
        val base = obj.instances.toList()
        val flags = obj.flags
        val normals = obj.normals

        val spans = ArrayList<IntArray>()
        var cursor = 0
        for (size in step.groups) {
            spans.add(intArrayOf(cursor, cursor + size))
            cursor += size
        }
        require(cursor == base.size) {
            "laggedgrow ${step.name}: groups cover $cursor instances, asset has ${base.size}"
        }

        // Centres are measured, not shipped: the geometry already knows them.
        val centres = spans.map { (lo, hi) ->
            var minX = Double.MAX_VALUE; var minY = Double.MAX_VALUE; var minZ = Double.MAX_VALUE
            var maxX = -Double.MAX_VALUE; var maxY = -Double.MAX_VALUE; var maxZ = -Double.MAX_VALUE
            for (index in lo until hi) {
                val inst = base[index]
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
            doubleArrayOf((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
        }

        val count = maxOf(spans.size, 1)
        val window = 1.0 / (1.0 + step.lag * (count - 1))
        val total = frames(step.seconds)

        for (i in 0 until total) {
            val alpha = (i + 1).toDouble() / total
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
            if (flags != null) obj.flags = IntArray(kept.size) { flags[kept[it]] }
            if (normals != null) obj.normals = Array(kept.size) { normals[kept[it]] }
            emit()
        }
        obj.instances = base.toMutableList()
        obj.flags = flags
        obj.normals = normals
    }

    private fun doFade(name: String, seconds: Double, fadingIn: Boolean) {
        objects[name]?.visible = true
        // A declared shape only enters the scene when something animates it in;
        // fade is one of those entry points, not just create.
        if (fadingIn && name !in objects) {
            val spec = program.shapes.getValue(name)
            objects[name] = Obj(
                kind = "shape", visible = true, points = geometryFor(spec), alpha = 0.0,
                strokeRgb = spec.stroke, width = spec.width,
            )
        }
        val obj = objects.getValue(name)
        val base = if (obj.kind == "asset") obj.instances.toList() else null
        val total = frames(seconds)

        for (i in 0 until total) {
            val progress = Verbs.smooth((i + 1).toDouble() / total)
            val alpha = if (fadingIn) progress else 1.0 - progress
            if (base == null) {
                obj.alpha = alpha
            } else {
                obj.instances = base.mapTo(ArrayList()) { inst ->
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

        if (base == null) {
            if (fadingIn) obj.alpha = 1.0 else objects.remove(name)
        } else {
            obj.instances = if (fadingIn) base.toMutableList() else ArrayList()
        }
    }

    /**
     * Glyph-level matching. Instances sharing a library glyph id pair up in
     * order; anything left over on either side fades rather than morphing into
     * an unrelated shape -- which is the correspondence TransformMatchingTex
     * computes from TeX structure, recovered here from the shared atlas.
     */
    private fun doMorph(step: Step.Morph) {
        val src = objects.getValue(step.source)
        val dst = objects.getValue(step.target)
        src.visible = true
        dst.visible = false

        val pending = LinkedHashMap<Int, ArrayDeque<Int>>()
        dst.glyphIds!!.forEachIndexed { index, glyph ->
            pending.getOrPut(glyph) { ArrayDeque() }.addLast(index)
        }

        val pairs = ArrayList<IntArray>()
        val orphans = ArrayList<Int>()
        src.glyphIds!!.forEachIndexed { index, glyph ->
            val queue = pending[glyph]
            if (queue != null && queue.isNotEmpty()) pairs.add(intArrayOf(index, queue.removeFirst()))
            else orphans.add(index)
        }
        val arrivals = pending.values.flatten()

        val srcBase = src.instances.toList()
        val dstBase = dst.instances.toList()
        val total = frames(step.seconds)

        for (i in 0 until total) {
            val alpha = Verbs.smooth((i + 1).toDouble() / total)
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
            val fadeOut = 1.0 - alpha
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
        src.instances = dstBase.toMutableList()
        src.glyphIds = dst.glyphIds!!.copyOf()
    }

    private fun doMove(step: Step.Move) {
        val startPhi = phi
        val startTheta = theta
        val total = frames(step.seconds)
        for (i in 0 until total) {
            val alpha = Verbs.smooth((i + 1).toDouble() / total)
            phi = startPhi + (step.phi - startPhi) * alpha
            theta = startTheta + (step.theta - startTheta) * alpha
            emit()
        }
    }

    /**
     * Manim's ambient rotation advances once per frame except on the wait's
     * last frame, which repeats the previous orientation. Measured on two
     * scenes. Without it the trailing hold sits 0.57 deg out for a whole
     * second -- where the fidelity harness never looks.
     */
    private fun doSpin(step: Step.Spin) {
        val total = frames(step.seconds)
        for (i in 0 until total) {
            if (i < total - 1) theta += step.rate / fps
            emit()
        }
    }
}
