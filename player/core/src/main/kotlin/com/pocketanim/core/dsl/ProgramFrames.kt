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
        return builder.frameInstances()
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
        val frame = index.coerceIn(0, maxOf(frameCount - 1, 0)).toDouble()
        for (spec in byZ) {
            val alpha = spec.at(frame, corners)
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
