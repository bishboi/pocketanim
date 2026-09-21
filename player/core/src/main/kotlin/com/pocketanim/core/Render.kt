package com.pocketanim.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Turning a decoded frame into drawing commands.
 *
 * Everything that decides *what the picture is* lives here, and nothing in this
 * file knows about a platform. The platform supplies only [PathSink]. That
 * boundary is the point: the same code that runs on the phone is run on the
 * desktop against the Cairo oracle in exporter/reference_render.py, so a
 * disagreement is a disagreement about the format rather than about Skia.
 */

/** Manim's defaults at 16:9. */
const val FRAME_WIDTH = 14.222222222222221f
const val FRAME_HEIGHT = 8.0f

/**
 * Manim's cairo_line_width_multiple: stroke_width is in hundredths of a scene
 * unit. The canvas is set up in scene coordinates so the rasteriser scales
 * stroke widths for us, exactly as Cairo does for the oracle.
 */
const val STROKE_SCALE = 0.01f

/**
 * Where the renderer meets the platform. A sink receives paths already in scene
 * coordinates; the transform from scene to pixels belongs to the platform, so
 * stroke widths scale the same way they do in Manim.
 */
interface PathSink {
    fun beginPath()
    fun moveTo(x: Float, y: Float)
    fun cubicTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float)
    fun closeSubpath()
    /** Fill the current path with a premultiplied-by-nothing ARGB colour. */
    fun fillPath(argb: Int)
    fun strokePath(argb: Int, widthInSceneUnits: Float)

    /**
     * A straight segment.
     *
     * Manim has no line primitive -- `set_points_as_corners` stores a polyline
     * as cubics whose handles sit exactly at a third and two thirds of the
     * chord -- so the renderer recovers the lines it was given. Measured on the
     * coastline scene: every one of its 58,987 curves is straight to 1e-15, and
     * a rasteriser must otherwise subdivide each of them before it can find
     * that out.
     *
     * The default keeps the seam small: a sink that has no line primitive gets
     * the cubic it would have got anyway.
     */
    fun lineTo(x: Float, y: Float) {
        // Without the original handles, thirds reproduce the same curve.
        cubicTo(x, y, x, y, x, y)
    }

    /**
     * Fill and stroke the current path in one operation.
     *
     * Only ever called when the two colours are identical and opaque, which is
     * the common case for shaded 3D faces: Manim gives a face the same colour
     * for both, so two draws produce one appearance. The default splits it back
     * into the two calls, so this stays an optimisation rather than a format
     * change.
     */
    fun fillAndStrokePath(argb: Int, widthInSceneUnits: Float) {
        fillPath(argb)
        strokePath(argb, widthInSceneUnits)
    }
}

object Renderer {

    /**
     * Project world points through a captured camera.
     *
     * Replicates ThreeDCamera.project_points. The device does this per frame,
     * which is why the IR carries 3D vertices and a camera track instead of
     * flattened output: a camera move costs 17 floats, not new geometry.
     */
    fun project(points: FloatArray, camera: FloatArray, out: FloatArray) =
        project(points, 0, points.size, camera, out)

    /**
     * [project], reading a slice of a shared buffer and writing from zero.
     *
     * The slice is how one frame's world points live in a single array rather
     * than one array per instance.
     */
    fun project(points: FloatArray, at: Int, length: Int, camera: FloatArray, out: FloatArray) {
        val cx = camera[0]; val cy = camera[1]; val cz = camera[2]
        val focal = camera[3]; val zoom = camera[4]

        var i = 0
        while (i < length) {
            val dx = points[at + i] - cx
            val dy = points[at + i + 1] - cy
            val dz = points[at + i + 2] - cz

            // rotation is row-major 3x3 at camera[5..13]; this is (p - c) @ R^T.
            val rx = camera[5] * dx + camera[6] * dy + camera[7] * dz
            val ry = camera[8] * dx + camera[9] * dy + camera[10] * dz
            val rz = camera[11] * dx + camera[12] * dy + camera[13] * dz

            val denominator = focal - rz
            val factor = when {
                denominator < 0f -> 1e6f
                denominator == 0f -> focal / 1e-9f
                else -> focal / denominator
            }

            out[i] = rx * factor * zoom
            out[i + 1] = ry * factor * zoom
            out[i + 2] = rz
            i += 3
        }
    }

    /** Apply an instance's 3x4 transform to the canonical atlas points. */
    fun transform(canonical: FloatArray, m: FloatArray, out: FloatArray) =
        transformInto(canonical, m, out)

    /** Bounding-box centre, which is what Manim means by a mobject's centre. */
    private fun centre(points: FloatArray, at: Int, length: Int, out: FloatArray) {
        var minX = points[at]; var minY = points[at + 1]; var minZ = points[at + 2]
        var maxX = minX; var maxY = minY; var maxZ = minZ
        var i = at + 3
        val end = at + length
        while (i < end) {
            val x = points[i]; val y = points[i + 1]; val z = points[i + 2]
            if (x < minX) minX = x; if (x > maxX) maxX = x
            if (y < minY) minY = y; if (y > maxY) maxY = y
            if (z < minZ) minZ = z; if (z > maxZ) maxZ = z
            i += 3
        }
        out[0] = (minX + maxX) * 0.5f
        out[1] = (minY + maxY) * 0.5f
        out[2] = (minZ + maxZ) * 0.5f
    }

    /**
     * Manim's get_shaded_rgb: light = 0.5 * dot(normal, to_sun)^3, halved again
     * when the face points away. The normal and the light position travel in
     * the IR, so this is derived on the device rather than baked into colours --
     * which is what lets one atlas entry serve every orientation of a solid.
     */
    private fun shadeOf(
        worldPoints: FloatArray,
        at: Int,
        length: Int,
        normal: FloatArray,
        camera: FloatArray,
    ): Float {
        val c = FloatArray(3)
        centre(worldPoints, at, length, c)
        val sx = camera[14] - c[0]
        val sy = camera[15] - c[1]
        val sz = camera[16] - c[2]
        val norm = sqrt(sx * sx + sy * sy + sz * sz)
        if (norm <= 1e-9f) return 0f
        val dot = (normal[0] * sx + normal[1] * sy + normal[2] * sz) / norm
        var shade = 0.5f * dot * dot * dot
        if (shade < 0f) shade *= 0.5f
        return shade
    }

    /**
     * Sort key for painter order: the bounding-box centre rotated into camera
     * space, z component. Manim re-sorts every frame, so draw order changes as
     * the camera moves and cannot be baked in. Anything not flagged
     * shade_in_3d sorts last, matching Manim's np.inf.
     */
    private fun depthOf(
        worldPoints: FloatArray,
        at: Int,
        length: Int,
        flags: Int,
        camera: FloatArray,
    ): Float {
        if (flags and Panm.SHADE_IN_3D == 0) return Float.POSITIVE_INFINITY
        val c = FloatArray(3)
        centre(worldPoints, at, length, c)
        // rotation^T column 2 is rotation row 2.
        return camera[11] * c[0] + camera[12] * c[1] + camera[13] * c[2]
    }

    private fun shift(argb: Int, shade: Float): Int {
        if (shade == 0f) return argb
        val a = (argb ushr 24) and 0xFF
        val r = min(max(((argb shr 16) and 0xFF) / 255f + shade, 0f), 1f)
        val g = min(max(((argb shr 8) and 0xFF) / 255f + shade, 0f), 1f)
        val b = min(max((argb and 0xFF) / 255f + shade, 0f), 1f)
        return (a shl 24) or
            ((r * 255f + 0.5f).toInt() shl 16) or
            ((g * 255f + 0.5f).toInt() shl 8) or
            (b * 255f + 0.5f).toInt()
    }

    /**
     * How far a cubic's handles may stray from the chord before it stops
     * counting as a line, in scene units. At the benchmark's 2148-pixel surface
     * a scene unit is 151 pixels, so this is a sixth of a pixel -- below what
     * antialiasing can express, and comfortably above the atlas's quantisation
     * step.
     */
    private const val LINE_TOLERANCE = 1e-3f

    /**
     * Verb ceiling for a merged run of strokes.
     *
     * Skia rasterises a path on the GPU only below kMaxGPUPathRendererVerbs
     * (16,384) and on the CPU above it, so merging draws is only a saving while
     * the merged path stays under that. Half the limit leaves room for the
     * shape that tips a run over it.
     */
    private const val MERGE_VERB_BUDGET = 8192

    /**
     * Whether an instance can touch the frame at all.
     *
     * The canonical bounding box through the instance's affine transform is a
     * bounding box of the result, so a miss is a certain miss. Measured on the
     * coastline scene at its tightest zoom: 62% of its verbs are off-screen,
     * and this drops them before they are transformed, walked or drawn.
     *
     * Only the 2D path uses it. Under a projecting camera the mapping is not
     * affine and a box does not survive it.
     */
    private fun offFrame(canonical: FloatArray, m: FloatArray): Boolean {
        var minX = canonical[0]; var maxX = minX
        var minY = canonical[1]; var maxY = minY
        var minZ = canonical[2]; var maxZ = minZ
        var i = 3
        while (i < canonical.size) {
            val x = canonical[i]; val y = canonical[i + 1]; val z = canonical[i + 2]
            if (x < minX) minX = x else if (x > maxX) maxX = x
            if (y < minY) minY = y else if (y > maxY) maxY = y
            if (z < minZ) minZ = z else if (z > maxZ) maxZ = z
            i += 3
        }

        // |a| * halfExtent bounds the linear part's contribution on each axis.
        val cx = (minX + maxX) * 0.5f; val ex = (maxX - minX) * 0.5f
        val cy = (minY + maxY) * 0.5f; val ey = (maxY - minY) * 0.5f
        val cz = (minZ + maxZ) * 0.5f; val ez = (maxZ - minZ) * 0.5f

        val centreX = m[0] * cx + m[1] * cy + m[2] * cz + m[3]
        val spanX = abs(m[0]) * ex + abs(m[1]) * ey + abs(m[2]) * ez
        if (centreX - spanX > FRAME_WIDTH * 0.5f || centreX + spanX < -FRAME_WIDTH * 0.5f) return true

        val centreY = m[4] * cx + m[5] * cy + m[6] * cz + m[7]
        val spanY = abs(m[4]) * ex + abs(m[5]) * ey + abs(m[6]) * ez
        return centreY - spanY > FRAME_HEIGHT * 0.5f || centreY + spanY < -FRAME_HEIGHT * 0.5f
    }

    /**
     * Emit one frame into [sink].
     *
     * Scratch buffers are grown, never reallocated per instance: the throughput
     * question on a low-end phone is decided by allocation and draw-call count
     * long before it is decided by arithmetic.
     */
    fun drawFrame(scene: Frames, index: Int, sink: PathSink) {
        // instances() first: a computing source populates its atlas as a side
        // effect of producing the frame, so shape() is only valid afterwards.
        val instances = scene.instances(index)
        val camera = scene.camera(index)
        if (camera == null) draw2D(scene, instances, sink) else draw3D(scene, instances, camera, sink)
    }

    /**
     * The 2D case: no projection, no depth sort, no shading.
     *
     * Two things it does that the 3D case cannot. It culls against the frame,
     * because an affine transform carries a bounding box. And it merges a run
     * of adjacent opaque strokes that share a colour and a width into one path,
     * which is exact -- stroking A then B in the same opaque colour paints the
     * same pixels as stroking A and B together -- and turns the coastline's
     * 1,429 draws into a handful.
     */
    private fun draw2D(scene: Frames, instances: Array<Instance>, sink: PathSink) {
        var world = FloatArray(0)

        var runOpen = false
        var runColour = 0
        var runWidth = 0f
        var runVerbs = 0

        for (inst in instances) {
            val canonical = scene.shape(inst.atlasId)
            if (canonical.size < 12) continue
            if (offFrame(canonical, inst.transform)) continue

            val fill = inst.fill
            val stroke = inst.stroke
            val filled = (fill ushr 24) and 0xFF > 0
            val stroked = (stroke ushr 24) and 0xFF > 0 && inst.strokeWidth > 0f
            if (!filled && !stroked) continue
            val width = inst.strokeWidth * STROKE_SCALE

            // Verbs this shape will contribute: one per curve, plus a move and
            // a close for each subpath. One subpath is the usual case and the
            // budget has slack, so the estimate need not be exact.
            val verbs = canonical.size / 12 + 2
            val mergeable = !filled && stroked && (stroke ushr 24) and 0xFF == 0xFF

            val continues = runOpen && mergeable && stroke == runColour &&
                width == runWidth && runVerbs + verbs <= MERGE_VERB_BUDGET
            if (runOpen && !continues) {
                sink.strokePath(runColour, runWidth)
                runOpen = false
            }

            if (world.size < canonical.size) world = FloatArray(canonical.size)
            transformInto(canonical, inst.transform, world)

            if (mergeable) {
                if (!runOpen) {
                    sink.beginPath()
                    runOpen = true
                    runColour = stroke
                    runWidth = width
                    runVerbs = 0
                }
                appendPath(world, canonical.size, sink)
                runVerbs += verbs
                continue
            }

            sink.beginPath()
            appendPath(world, canonical.size, sink)
            if (filled && stroked && fill == stroke && (fill ushr 24) and 0xFF == 0xFF) {
                sink.fillAndStrokePath(fill, width)
            } else {
                if (filled) sink.fillPath(fill)
                if (stroked) sink.strokePath(stroke, width)
            }
        }

        if (runOpen) sink.strokePath(runColour, runWidth)
    }

    /**
     * The 3D case: depth sort, project, shade.
     *
     * The sort keeps the world points it computed rather than computing them
     * again in the draw pass, and orders an index permutation packed into longs
     * rather than an array of boxed pairs. On the molecule scene that is 2,910
     * fewer transforms and 2,910 fewer allocations per frame.
     */
    private fun draw3D(
        scene: Frames,
        instances: Array<Instance>,
        camera: FloatArray,
        sink: PathSink,
    ) {
        val n = instances.size
        if (n == 0) return

        // One buffer for every instance's world points, indexed by offset.
        // The molecule scene has 2,910 instances per frame; a FloatArray each
        // is 2,910 allocations a frame, which is what its 7.4 ms of geometry
        // time on the device was mostly made of.
        val offset = IntArray(n + 1)
        for (i in 0 until n) offset[i + 1] = offset[i] + scene.shape(instances[i].atlasId).size
        val world = FloatArray(offset[n])

        val order = LongArray(n)
        for (i in 0 until n) {
            val inst = instances[i]
            val canonical = scene.shape(inst.atlasId)
            transformInto(canonical, inst.transform, world, offset[i])
            val depth = depthOf(world, offset[i], canonical.size, inst.flags, camera)
            order[i] = (sortable(depth).toLong() shl 32) or (i.toLong() and 0xFFFFFFFFL)
        }
        order.sort()

        var screen = FloatArray(0)
        for (k in 0 until n) {
            val i = (order[k] and 0xFFFFFFFFL).toInt()
            val inst = instances[i]
            val at = offset[i]
            val length = offset[i + 1] - at
            if (length < 12) continue

            val fill = inst.fill
            val stroke = inst.stroke
            val filled = (fill ushr 24) and 0xFF > 0
            val stroked = (stroke ushr 24) and 0xFF > 0 && inst.strokeWidth > 0f
            if (!filled && !stroked) continue

            if (screen.size < length) screen = FloatArray(length)
            project(world, at, length, camera, screen)
            var shade = 0f
            if (inst.flags and Panm.SHADE_IN_3D != 0 && inst.normal != null) {
                shade = shadeOf(world, at, length, inst.normal, camera)
            }

            sink.beginPath()
            appendPath(screen, length, sink)

            val width = inst.strokeWidth * STROKE_SCALE
            if (filled && stroked && fill == stroke && (fill ushr 24) and 0xFF == 0xFF) {
                // Both shift by the same amount, so equal colours stay equal.
                sink.fillAndStrokePath(shift(fill, shade), width)
            } else {
                if (filled) sink.fillPath(shift(fill, shade))
                if (stroked) sink.strokePath(shift(stroke, shade), width)
            }
        }
    }

    /**
     * Order floats as signed integers.
     *
     * Float bit patterns already increase with the value for positives, but run
     * backwards for negatives; reflecting them about the sign bit fixes that,
     * and lets a depth key and an instance index share one long that sorts
     * correctly without boxing anything.
     */
    private fun sortable(f: Float): Int {
        val bits = f.toRawBits()
        return if (bits < 0) Int.MIN_VALUE - bits else bits
    }

    /** [transform], writing only the first [canonical].size floats of [out]. */
    private fun transformInto(canonical: FloatArray, m: FloatArray, out: FloatArray, at: Int = 0) {
        var i = 0
        val end = canonical.size
        while (i < end) {
            val x = canonical[i]; val y = canonical[i + 1]; val z = canonical[i + 2]
            out[at + i] = m[0] * x + m[1] * y + m[2] * z + m[3]
            out[at + i + 1] = m[4] * x + m[5] * y + m[6] * z + m[7]
            out[at + i + 2] = m[8] * x + m[9] * y + m[10] * z + m[11]
            i += 3
        }
    }

    /**
     * Manim stores four points per cubic. A subpath continues while each curve
     * starts where the previous one ended; a break starts a new one. Splitting
     * is done on the projected points, as the oracle does, so a projection that
     * separates two curves separates the subpaths too.
     *
     * A curve whose handles lie on the chord is emitted as a line. Manim has no
     * line primitive, so a polyline arrives here as cubics with handles at a
     * third and two thirds, and telling the rasteriser that saves it
     * subdividing every one of them to discover it.
     *
     * Does not open the path: a caller may be accumulating several shapes into
     * one.
     */
    private fun appendPath(points: FloatArray, length: Int, sink: PathSink) {
        val curves = length / 12 // 4 points x 3 floats
        var open = false
        for (i in 0 until curves) {
            val o = i * 12
            if (open) {
                // Compare against the previous curve's end point.
                val p = o - 12 + 9
                val joined = abs(points[p] - points[o]) <= 1e-6f &&
                    abs(points[p + 1] - points[o + 1]) <= 1e-6f &&
                    abs(points[p + 2] - points[o + 2]) <= 1e-6f
                if (!joined) {
                    sink.closeSubpath()
                    open = false
                }
            }
            if (!open) {
                sink.moveTo(points[o], points[o + 1])
                open = true
            }

            val ax = points[o]; val ay = points[o + 1]
            val dx = points[o + 9] - ax; val dy = points[o + 10] - ay
            val straight =
                abs(points[o + 3] - (ax + dx * (1f / 3f))) <= LINE_TOLERANCE &&
                abs(points[o + 4] - (ay + dy * (1f / 3f))) <= LINE_TOLERANCE &&
                abs(points[o + 6] - (ax + dx * (2f / 3f))) <= LINE_TOLERANCE &&
                abs(points[o + 7] - (ay + dy * (2f / 3f))) <= LINE_TOLERANCE
            if (straight) {
                sink.lineTo(points[o + 9], points[o + 10])
            } else {
                sink.cubicTo(
                    points[o + 3], points[o + 4],
                    points[o + 6], points[o + 7],
                    points[o + 9], points[o + 10],
                )
            }
        }
        if (open) sink.closeSubpath()
    }
}
