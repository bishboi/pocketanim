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

    /**
     * The raster pictures showing in this frame, each with the instance it is drawn before. Called after
     * [instances] for the same frame. A sampled container has none.
     */
    fun images(index: Int): List<ImageDraw> = emptyList()

    /** A picture's file (PNG), by the name an [ImageDraw] carries; null when the source has none. */
    fun imageBytes(src: String): ByteArray? = null
}

/**
 * One picture in one frame: its pixel (u, v) lands at UL + u/[width] (UR - UL) + v/[height] (DL - UL), [corners]
 * being ulx, uly, urx, ury, dlx, dly in scene units; drawn at [alpha] just before instance [before] of the frame
 * (after every object at or below its z).
 */
class ImageDraw(
    @JvmField val src: String,
    @JvmField val width: Int,
    @JvmField val height: Int,
    @JvmField val alpha: Float,
    @JvmField val corners: FloatArray,
    @JvmField val before: Int,
)
