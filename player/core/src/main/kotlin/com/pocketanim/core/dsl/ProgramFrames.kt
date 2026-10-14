package com.pocketanim.core.dsl

import com.pocketanim.core.Frames
import com.pocketanim.core.ImageDraw
import com.pocketanim.core.Instance

/**
 * A tier-1 program presented as frames.
 *
 * Holds one frame, not all of them. The timeline is a state machine that can be
 * stepped, and verb boundaries are checkpointed, so playing forward costs one
 * verb body per frame and seeking backwards costs a replay bounded by the
 * longest verb rather than by the distance seeked.
 *
 * Not thread-safe, deliberately: producing a frame mutates the machine, so the
 * render thread owns it and nothing else touches it. That is also why
 * [instances] must be called before [shape] for a given frame.
 */
class ProgramFrames internal constructor(private val builder: Builder) : Frames {

    override val fps: Int get() = builder.fps
    override val frameCount: Int get() = builder.frameCount
    override val background: Int get() = builder.background

    private var positioned = -1

    private fun position(index: Int) {
        if (index != positioned) {
            builder.seek(index)
            positioned = index
        }
    }

    override fun shape(atlasId: Int): FloatArray = builder.shape(atlasId)

    override fun camera(index: Int): FloatArray? {
        position(index)
        return builder.frameCamera()
    }

    override fun instances(index: Int): Array<Instance> {
        position(index)
        val frame = builder.frameInstances()
        val drifting = builder.currentDrifting
        if (drifting.isEmpty()) return frame
        // A drifting backdrop or picture moves every frame, from the clock (Drift.at), not from the timeline.
        val out = frame.copyOf()
        val seconds = index.toDouble() / builder.fps
        for ((name, span) in drifting) {
            val outer = builder.drift(name)?.at(seconds) ?: continue
            for (slot in span[0] until span[1]) out[slot] = moved(frame[slot], outer)
        }
        return out
    }

    private fun moved(inst: Instance, outer: DoubleArray): Instance {
        val t = inst.transform
        val out = FloatArray(12)
        for (row in 0 until 3) {
            for (col in 0 until 3) {
                var sum = 0.0
                for (k in 0 until 3) sum += outer[row * 4 + k] * t[k * 4 + col]
                out[row * 4 + col] = sum.toFloat()
            }
            var tr = outer[row * 4 + 3]
            for (k in 0 until 3) tr += outer[row * 4 + k] * t[k * 4 + 3]
            out[row * 4 + 3] = tr.toFloat()
        }
        return Instance(inst.slot, inst.atlasId, inst.flags, out, inst.fill, inst.stroke, inst.strokeWidth, inst.normal)
    }

    /** Lower z first, declaration order between equals: then each goes in no earlier than the one before it. */
    private val byZ by lazy { builder.images.sortedBy { it.z } }
    private val corners = FloatArray(6)

    override fun images(index: Int): List<ImageDraw> {
        val specs = byZ
        if (specs.isEmpty()) return emptyList()
        position(index)
        val out = ArrayList<ImageDraw>(2)
        val frame = index.coerceIn(0, maxOf(frameCount - 1, 0)).toDouble()
        for (spec in specs) {
            val corners = FloatArray(6)
            val alpha = spec.at(frame, corners)
            if (alpha <= 0f) continue
            spec.drift?.move(corners, index.toDouble() / builder.fps)
            out.add(ImageDraw(spec.src, spec.width, spec.height, alpha, corners, builder.instancesAtOrBelow(spec.z)))
        }
        return out
    }

    override fun imageBytes(src: String): ByteArray? = builder.imageBytes(src)

    override fun recover() {
        builder.recover()
        positioned = -1
    }

    /** The frame built for [index] and where each picture stands in it. */
    override fun contentKey(index: Int): Long {
        position(index)
        var key = builder.version
        // A drifting backdrop or picture changes the picture every frame.
        if (builder.currentDrifting.isNotEmpty()) key = key * 31 + index
        val frame = index.coerceIn(0, maxOf(frameCount - 1, 0)).toDouble()
        for (spec in byZ) {
            val alpha = spec.at(frame, corners)
            if (alpha > 0f && spec.drift != null) spec.drift.move(corners, index.toDouble() / builder.fps)
            key = key * 31 + alpha.toRawBits()
            if (alpha > 0f) for (c in corners) key = key * 31 + c.toRawBits()
        }
        return key
    }

    override fun imagesBetween(from: Int, to: Int): List<String> {
        val out = ArrayList<String>()
        for (spec in byZ) {
            var showing = false
            var k = 0
            while (k < spec.keyCount) {
                val at = spec.keys[k * ImageSpec.KEY]
                val alpha = spec.keys[k * ImageSpec.KEY + 1]
                // Showing at some frame of [from, to]: a key in the window, or the key before it still visible.
                if (at > to) break
                if (alpha > 0.004 && (at >= from || k + 1 >= spec.keyCount ||
                        spec.keys[(k + 1) * ImageSpec.KEY] >= from)) showing = true
                k++
            }
            if (showing && spec.src !in out) out.add(spec.src)
        }
        return out
    }
}
