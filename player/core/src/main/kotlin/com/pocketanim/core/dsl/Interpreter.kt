package com.pocketanim.core.dsl

import com.pocketanim.core.Instance
import com.pocketanim.core.Panm
import com.pocketanim.core.Record
import com.pocketanim.core.Scene
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sin

/**
 * Expand a tier-1 program into frames, on the device.
 *
 * This is the half of the project that makes the size claim real: the artefact
 * is a few hundred bytes of program plus cached assets, and *this* is the cost
 * of that -- the arithmetic the exporter would otherwise have baked into
 * megabytes of sampled keyframes runs here instead. Because the device computes
 * at full precision rather than replaying quantised samples, the result is also
 * more accurate than the sampled IR, not less.
 *
 * It produces a [Scene], the same type [Panm] produces, so the renderer and the
 * player cannot tell which tier they are playing.
 *
 * Known cost, and it is real: frames are materialised up front. A long
 * instance-heavy scene will hold tens of megabytes. The structure to fix it is
 * already here -- the timeline is a state machine stepped one frame at a time --
 * so the change is to stop retaining, not to redesign. See docs/SPEC.md §11.
 */

/** Where baked assets come from. Android reads app storage; the harness reads files. */
interface AssetLoader {
    /** The content-addressed asset `<id>.panm`. */
    fun asset(id: String): ByteArray
    /** The library-wide glyph atlas that text assets index into. */
    fun glyphLibrary(): ByteArray
}

private const val FOCAL_DISTANCE = 20.0
private const val ZOOM = 1.0
private const val GAMMA = 0.0
private val LIGHT_SOURCE = doubleArrayOf(-7.0, -9.0, 10.0)

/** Mutable instance state during interpretation; rgba kept as Python keeps it. */
internal class Inst(
    var atlasId: Int,
    var transform: DoubleArray,
    var fill: IntArray,
    var stroke: IntArray,
    var width: Double,
)

internal class Obj(
    var kind: String,
    var visible: Boolean,
    var centre: DoubleArray = DoubleArray(3),
    var xform: DoubleArray = identity(),
    var instances: MutableList<Inst> = ArrayList(),
    var flags: IntArray? = null,
    var normals: Array<DoubleArray?>? = null,
    var glyphIds: IntArray? = null,
    var points: DoubleArray? = null,
    var alpha: Double = 1.0,
    var strokeRgb: Int = 0xFFFFFF,
    var width: Double = 0.0,
) {
    /**
     * A checkpoint copy.
     *
     * The instance *list* is copied but the instances are not: verbs replace
     * entries rather than mutating them in place, so sharing is safe and
     * copying 2,900 of them per checkpoint would not be. `points` is copied
     * because create and transform do write it.
     */
    fun copy() = Obj(
        kind, visible, centre.copyOf(), xform.copyOf(), ArrayList(instances),
        flags?.copyOf(), normals?.copyOf(), glyphIds?.copyOf(),
        points?.copyOf(), alpha, strokeRgb, width,
    )
}

internal fun identity() = doubleArrayOf(1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)

/** Apply an object-level transform on top of an instance transform. */
internal fun compose(outer: DoubleArray, inner: DoubleArray): DoubleArray {
    val out = DoubleArray(12)
    for (row in 0 until 3) {
        for (col in 0 until 3) {
            var sum = 0.0
            for (k in 0 until 3) sum += outer[row * 4 + k] * inner[k * 4 + col]
            out[row * 4 + col] = sum
        }
        var t = outer[row * 4 + 3]
        for (k in 0 until 3) t += outer[row * 4 + k] * inner[k * 4 + 3]
        out[row * 4 + 3] = t
    }
    return out
}

/**
 * Python's round(), which is half-to-even rather than half-up.
 *
 * Only colour interpolation depends on it, and only on exact .5 boundaries --
 * but those land often when interpolating 8-bit channels, and the desktop
 * cross-check compares field for field.
 */
internal fun pyRound(x: Double): Int {
    val f = floor(x)
    val diff = x - f
    return when {
        diff > 0.5 -> f.toInt() + 1
        diff < 0.5 -> f.toInt()
        else -> if (f.toInt() % 2 == 0) f.toInt() else f.toInt() + 1
    }
}

object Interpreter {

    /**
     * Open a program for playback.
     *
     * Frames are computed on demand rather than materialised: the eager form
     * measured at 98.8 MB retained for one corpus scene, which a phone does not
     * have to spare. See [ProgramFrames].
     */
    fun open(program: Program, loader: AssetLoader): ProgramFrames =
        ProgramFrames(Builder(program, loader).also { it.prepare() })

    /** Manim composes rot_z(gamma) @ rot_x(-phi) @ rot_z(-theta - 90deg). */
    fun cameraMatrix(phi: Double, theta: Double, gamma: Double = GAMMA): DoubleArray {
        fun rotZ(a: Double) = doubleArrayOf(cos(a), -sin(a), 0.0, sin(a), cos(a), 0.0, 0.0, 0.0, 1.0)
        fun rotX(a: Double) = doubleArrayOf(1.0, 0.0, 0.0, 0.0, cos(a), -sin(a), 0.0, sin(a), cos(a))
        fun mul(a: DoubleArray, b: DoubleArray): DoubleArray {
            val o = DoubleArray(9)
            for (r in 0 until 3) for (c in 0 until 3) {
                var s = 0.0
                for (k in 0 until 3) s += a[r * 3 + k] * b[k * 3 + c]
                o[r * 3 + c] = s
            }
            return o
        }
        var result = doubleArrayOf(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        for (m in listOf(rotZ(-theta - Math.PI / 2), rotX(-phi), rotZ(gamma))) result = mul(m, result)
        return result
    }

    /**
     * Build surface faces exactly as Manim's Surface does.
     *
     * Manim lays each face out as a flat quad in UV space via
     * set_points_as_corners -- cubic control points at 0, 1/3, 2/3, 1 along
     * each straight edge -- then maps every control point through the surface
     * function. Four edges of four points is the 16 points per face Manim
     * produces, and reproducing that exactly is what lets a surface ship as an
     * expression rather than a mesh.
     */
    fun tessellate(fn: Expr, uRange: DoubleArray, vRange: DoubleArray, res: IntArray): List<DoubleArray> {
        val (uRes, vRes) = Pair(res[0], res[1])
        val us = DoubleArray(uRes + 1) { uRange[0] + (uRange[1] - uRange[0]) * it / uRes }
        val vs = DoubleArray(vRes + 1) { vRange[0] + (vRange[1] - vRange[0]) * it / vRes }

        val faces = ArrayList<DoubleArray>(uRes * vRes)
        for (i in 0 until uRes) {
            for (j in 0 until vRes) {
                val u1 = us[i]; val u2 = us[i + 1]
                val v1 = vs[j]; val v2 = vs[j + 1]
                val corners = doubleArrayOf(u1, v1, u2, v1, u2, v2, u1, v2, u1, v1)

                val points = DoubleArray(16 * 3)
                var at = 0
                for (edge in 0 until 4) {
                    val ua = corners[edge * 2]; val va = corners[edge * 2 + 1]
                    val ub = corners[edge * 2 + 2]; val vb = corners[edge * 2 + 3]
                    for (t in doubleArrayOf(0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)) {
                        val u = ua + (ub - ua) * t
                        val v = va + (vb - va) * t
                        points[at] = u
                        points[at + 1] = v
                        points[at + 2] = fn.eval(u, v)
                        at += 3
                    }
                }
                faces.add(points)
            }
        }
        return faces
    }

    /**
     * Best-fit plane normal, oriented into the +z hemisphere.
     *
     * The orientation is not cosmetic. Manim's shading uses the normal's sign,
     * and taking whatever sign the fit happens to produce banded adjacent faces
     * light and dark -- it cost 9 points of fidelity before the hemisphere rule
     * was added. Computed from the covariance matrix's smallest eigenvector via
     * Jacobi rotations, which is the SVD the exporter uses without needing one.
     */
    fun planeNormal(points: DoubleArray): DoubleArray {
        val n = points.size / 3
        val mean = DoubleArray(3)
        for (i in 0 until n) for (k in 0 until 3) mean[k] += points[i * 3 + k]
        for (k in 0 until 3) mean[k] /= n

        val c = Array(3) { DoubleArray(3) }
        for (i in 0 until n) {
            val dx = points[i * 3] - mean[0]
            val dy = points[i * 3 + 1] - mean[1]
            val dz = points[i * 3 + 2] - mean[2]
            val d = doubleArrayOf(dx, dy, dz)
            for (a in 0 until 3) for (b in 0 until 3) c[a][b] += d[a] * d[b]
        }

        // Jacobi eigenvalue iteration on a symmetric 3x3.
        val v = Array(3) { r -> DoubleArray(3) { col -> if (r == col) 1.0 else 0.0 } }
        repeat(32) {
            var p = 0; var q = 1; var best = abs(c[0][1])
            if (abs(c[0][2]) > best) { p = 0; q = 2; best = abs(c[0][2]) }
            if (abs(c[1][2]) > best) { p = 1; q = 2; best = abs(c[1][2]) }
            if (best < 1e-14) return@repeat

            val theta = 0.5 * Math.atan2(2 * c[p][q], c[q][q] - c[p][p])
            val cs = cos(theta); val sn = sin(theta)
            for (k in 0 until 3) {
                val ckp = c[k][p]; val ckq = c[k][q]
                c[k][p] = cs * ckp - sn * ckq
                c[k][q] = sn * ckp + cs * ckq
            }
            for (k in 0 until 3) {
                val cpk = c[p][k]; val cqk = c[q][k]
                c[p][k] = cs * cpk - sn * cqk
                c[q][k] = sn * cpk + cs * cqk
            }
            for (k in 0 until 3) {
                val vkp = v[k][p]; val vkq = v[k][q]
                v[k][p] = cs * vkp - sn * vkq
                v[k][q] = sn * vkp + cs * vkq
            }
        }

        var smallest = 0
        for (k in 1 until 3) if (c[k][k] < c[smallest][smallest]) smallest = k
        val normal = doubleArrayOf(v[0][smallest], v[1][smallest], v[2][smallest])
        return if (normal[2] < 0) doubleArrayOf(-normal[0], -normal[1], -normal[2]) else normal
    }
}
