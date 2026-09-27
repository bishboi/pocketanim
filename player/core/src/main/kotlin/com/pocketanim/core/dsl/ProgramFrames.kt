package com.pocketanim.core.dsl

import com.pocketanim.core.Frames
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
}
