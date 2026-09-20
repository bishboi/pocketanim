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
}

object Renderer {

    /**
     * Project world points through a captured camera.
     *
     * Replicates ThreeDCamera.project_points. The device does this per frame,
     * which is why the IR carries 3D vertices and a camera track instead of
     * flattened output: a camera move costs 17 floats, not new geometry.
     */
    fun project(points: FloatArray, camera: FloatArray, out: FloatArray) {
        val cx = camera[0]; val cy = camera[1]; val cz = camera[2]
        val focal = camera[3]; val zoom = camera[4]

        var i = 0
        while (i < points.size) {
            val dx = points[i] - cx
            val dy = points[i + 1] - cy
            val dz = points[i + 2] - cz

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
    fun transform(canonical: FloatArray, m: FloatArray, out: FloatArray) {
        var i = 0
        while (i < canonical.size) {
            val x = canonical[i]; val y = canonical[i + 1]; val z = canonical[i + 2]
            out[i] = m[0] * x + m[1] * y + m[2] * z + m[3]
            out[i + 1] = m[4] * x + m[5] * y + m[6] * z + m[7]
            out[i + 2] = m[8] * x + m[9] * y + m[10] * z + m[11]
            i += 3
        }
    }

    /** Bounding-box centre, which is what Manim means by a mobject's centre. */
    private fun centre(points: FloatArray, out: FloatArray) {
        var minX = points[0]; var minY = points[1]; var minZ = points[2]
        var maxX = minX; var maxY = minY; var maxZ = minZ
        var i = 3
        while (i < points.size) {
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
    private fun shadeOf(worldPoints: FloatArray, normal: FloatArray, camera: FloatArray): Float {
        val c = FloatArray(3)
        centre(worldPoints, c)
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
    private fun depthOf(worldPoints: FloatArray, flags: Int, camera: FloatArray): Float {
        if (flags and Panm.SHADE_IN_3D == 0) return Float.POSITIVE_INFINITY
        val c = FloatArray(3)
        centre(worldPoints, c)
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
     * Emit one frame into [sink].
     *
     * Allocation is kept to two scratch buffers per instance rather than per
     * point, because the throughput question on a low-end phone is decided by
     * allocation and draw-call count long before it is decided by arithmetic.
     */
    fun drawFrame(scene: Scene, index: Int, sink: PathSink) {
        val camera = scene.cameras?.getOrNull(index)
        var instances = scene.frame(index)

        if (camera != null) {
            val keyed = Array(instances.size) { i ->
                val inst = instances[i]
                val canonical = scene.atlas[inst.atlasId]
                val world = FloatArray(canonical.size)
                transform(canonical, inst.transform, world)
                Pair(depthOf(world, inst.flags, camera), inst)
            }
            keyed.sortBy { it.first }
            instances = Array(keyed.size) { keyed[it].second }
        }

        for (inst in instances) {
            val canonical = scene.atlas[inst.atlasId]
            val world = FloatArray(canonical.size)
            transform(canonical, inst.transform, world)

            val screen: FloatArray
            var shade = 0f
            if (camera != null) {
                screen = FloatArray(world.size)
                project(world, camera, screen)
                if (inst.flags and Panm.SHADE_IN_3D != 0 && inst.normal != null) {
                    shade = shadeOf(world, inst.normal, camera)
                }
            } else {
                screen = world
            }

            emitPath(screen, sink)

            val fill = inst.fill
            if ((fill ushr 24) and 0xFF > 0) sink.fillPath(shift(fill, shade))

            val stroke = inst.stroke
            if ((stroke ushr 24) and 0xFF > 0 && inst.strokeWidth > 0f) {
                sink.strokePath(shift(stroke, shade), inst.strokeWidth * STROKE_SCALE)
            }
        }
    }

    /**
     * Manim stores four points per cubic. A subpath continues while each curve
     * starts where the previous one ended; a break starts a new one. Splitting
     * is done on the projected points, as the oracle does, so a projection that
     * separates two curves separates the subpaths too.
     */
    private fun emitPath(points: FloatArray, sink: PathSink) {
        sink.beginPath()
        val curves = points.size / 12 // 4 points x 3 floats
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
            sink.cubicTo(
                points[o + 3], points[o + 4],
                points[o + 6], points[o + 7],
                points[o + 9], points[o + 10],
            )
        }
        if (open) sink.closeSubpath()
    }
}
