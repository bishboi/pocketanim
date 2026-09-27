package com.pocketanim.core

/**
 * A source of frames, however they come to exist.
 *
 * Tier 3 decodes them; tier 1 computes them. The renderer is handed this and
 * cannot tell which, which is what lets one renderer serve both tiers.
 *
 * Geometry is fetched through [shape] rather than exposed as an array because a
 * computing source grows and truncates its atlas as it seeks -- a caller
 * holding the array across frames would be holding a stale one.
 */
interface Frames {
    val fps: Int
    val frameCount: Int

    /** The clear colour, ARGB. A sampled container has none and means black. */
    val background: Int get() = 0xFF000000.toInt()

    fun shape(atlasId: Int): FloatArray

    /** The camera for this frame, or null for a 2D scene. */
    fun camera(index: Int): FloatArray?

    /**
     * The ordered instance list for this frame.
     *
     * Draw order is painter order, so the order is part of the answer, not an
     * implementation detail.
     */
    fun instances(index: Int): Array<Instance>
}
