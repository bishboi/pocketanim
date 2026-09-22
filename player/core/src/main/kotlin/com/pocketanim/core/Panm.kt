package com.pocketanim.core

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * The .panm container, decoded.
 *
 * This is the third independent implementation of the format, after
 * exporter/decode.py and client/PanimDecoder.java, and it is the one that ships:
 * everything below runs on the device. It is deliberately free of both Android
 * and JDK-version-specific APIs -- half-float conversion is written out rather
 * than calling Float.float16ToFloat, which needs Java 20 and does not exist on
 * Android at all -- so the same code is exercised by the desktop cross-check
 * and by the phone.
 */
object Panm {
    const val MAGIC = 0x4D4E4150 // "PANM" little-endian
    const val FLAG_CAMERA = 1
    const val SHADE_IN_3D = 1

    /**
     * The face belongs to a closed solid, so one pointing away from the camera
     * is behind one pointing towards it and cannot be seen. Only the exporter
     * can know this -- it saw the class that built the shape, where the device
     * sees an anonymous quad.
     */
    const val CLOSED_SOLID = 2

    /**
     * The stored normal points into that solid rather than out of it. Shading
     * wants the normal Manim derived, sign and all; culling wants to know
     * which way is out. One bit serves both rather than a second normal
     * serving neither.
     */
    const val NORMAL_INWARD = 4
    const val CAMERA_FLOATS = 17
    const val REC_SNAPSHOT = 0
}

/** One drawable: an atlas shape placed by an affine transform and styled. */
class Instance(
    @JvmField val slot: Int,
    @JvmField val atlasId: Int,
    @JvmField val flags: Int,
    /** Row-major 3x4: the linear part in columns 0..2, translation in column 3. */
    @JvmField val transform: FloatArray,
    @JvmField val fill: Int,          // ARGB
    @JvmField val stroke: Int,        // ARGB
    @JvmField val strokeWidth: Float,
    @JvmField val normal: FloatArray?, // null unless SHADE_IN_3D
)

class Record(@JvmField val kind: Int, @JvmField val instances: Array<Instance>)

class Scene(
    override val fps: Int,
    /** Per shape, flat xyz triples, already dequantised. */
    @JvmField val atlas: Array<FloatArray>,
    /** Per record, [Panm.CAMERA_FLOATS] floats; null when the scene is 2D. */
    @JvmField val cameras: Array<FloatArray>?,
    @JvmField val records: Array<Record>,
    @JvmField val lo: FloatArray,
    @JvmField val hi: FloatArray,
) : Frames {
    override val frameCount: Int get() = records.size

    override fun shape(atlasId: Int): FloatArray = atlas[atlasId]

    override fun camera(index: Int): FloatArray? = cameras?.getOrNull(index)

    override fun instances(index: Int): Array<Instance> = frame(index)

    /**
     * Resolve a frame to its ordered instance list.
     *
     * Walk back to the preceding snapshot and replay keyframes forward.
     * Keyframes carry absolute values, so replay is an overwrite and never
     * accumulates -- which is what makes seeking exact rather than approximate,
     * and what lets the player scrub without replaying from frame zero.
     */
    fun frame(index: Int): Array<Instance> {
        var start = index
        while (start > 0 && records[start].kind != Panm.REC_SNAPSHOT) start--

        val order = ArrayList<Int>()
        val state = HashMap<Int, Instance>()
        for (r in start..index) {
            val record = records[r]
            if (record.kind == Panm.REC_SNAPSHOT) {
                order.clear()
                state.clear()
                for (inst in record.instances) {
                    order.add(inst.slot)
                    state[inst.slot] = inst
                }
            } else {
                for (inst in record.instances) {
                    if (!state.containsKey(inst.slot)) order.add(inst.slot)
                    state[inst.slot] = inst
                }
            }
        }

        val out = ArrayList<Instance>(order.size)
        for (slot in order) state[slot]?.let { out.add(it) }
        return out.toTypedArray()
    }

    companion object {
        fun parse(bytes: ByteArray): Scene {
            val buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)

            require(buf.int == Panm.MAGIC) { "not a pocketanim IR" }
            val version = buf.short.toInt() and 0xFFFF
            val flags = buf.short.toInt() and 0xFFFF
            val fps = buf.short.toInt() and 0xFFFF
            val recordCount = buf.int
            val atlasCount = buf.int

            val lo = FloatArray(3) { buf.float }
            val hi = FloatArray(3) { buf.float }
            val span = FloatArray(3) {
                val d = hi[it] - lo[it]
                if (kotlin.math.abs(d) < 1e-9f) 1.0f else d
            }

            var cameras: Array<FloatArray>? = null
            if (flags and Panm.FLAG_CAMERA != 0) {
                cameras = Array(recordCount) { FloatArray(Panm.CAMERA_FLOATS) { buf.float } }
            }

            // Atlas geometry is quantised to uint16 over the scene bounding box.
            val atlas = Array(atlasCount) {
                val pointCount = buf.int
                val points = FloatArray(pointCount * 3)
                for (p in 0 until pointCount) {
                    for (axis in 0 until 3) {
                        val raw = buf.short.toInt() and 0xFFFF
                        points[p * 3 + axis] = lo[axis] + (raw / 65535.0f) * span[axis]
                    }
                }
                points
            }

            val records = Array(recordCount) {
                val kind = buf.get().toInt() and 0xFF
                val instanceCount = buf.int
                val instances = Array(instanceCount) {
                    val slot = buf.int
                    val atlasId = buf.int
                    val instFlags = buf.get().toInt() and 0xFF

                    // The linear part is float16; translation stays float32
                    // because at 720p half precision is visible in position.
                    val transform = FloatArray(12)
                    for (k in 0 until 9) {
                        transform[(k / 3) * 4 + (k % 3)] = halfToFloat(buf.short.toInt() and 0xFFFF)
                    }
                    for (row in 0 until 3) transform[row * 4 + 3] = buf.float

                    val fill = readColor(buf)
                    val stroke = readColor(buf)
                    val strokeWidth = (buf.short.toInt() and 0xFFFF) / 64.0f

                    val normal = if (instFlags and Panm.SHADE_IN_3D != 0) {
                        FloatArray(3) { halfToFloat(buf.short.toInt() and 0xFFFF) }
                    } else null

                    Instance(slot, atlasId, instFlags, transform, fill, stroke, strokeWidth, normal)
                }
                Record(kind, instances)
            }

            if (version != 1) System.err.println("warning: unexpected IR version $version")
            return Scene(fps, atlas, cameras, records, lo, hi)
        }

        /** Four bytes r,g,b,a off the wire into one ARGB int. */
        private fun readColor(buf: ByteBuffer): Int {
            val r = buf.get().toInt() and 0xFF
            val g = buf.get().toInt() and 0xFF
            val b = buf.get().toInt() and 0xFF
            val a = buf.get().toInt() and 0xFF
            return (a shl 24) or (r shl 16) or (g shl 8) or b
        }

        /**
         * IEEE 754 half to single. Written out rather than delegated because
         * Float.float16ToFloat needs Java 20 and Android has no equivalent
         * below API 26; the device and the cross-check must run the same code
         * or the cross-check proves nothing about the device.
         */
        fun halfToFloat(h: Int): Float {
            val sign = (h and 0x8000) shl 16
            val exp = (h and 0x7C00) shr 10
            val man = h and 0x03FF
            return when {
                exp == 0x1F -> Float.fromBits(sign or 0x7F800000 or (man shl 13))
                exp != 0 -> Float.fromBits(sign or ((exp - 15 + 127) shl 23) or (man shl 13))
                man == 0 -> Float.fromBits(sign)
                else -> {
                    // Subnormal: shift the leading one up into place and pay
                    // for each shift out of the exponent.
                    var shifts = 0
                    var m = man
                    while (m and 0x0400 == 0) {
                        m = m shl 1
                        shifts++
                    }
                    Float.fromBits(sign or ((113 - shifts) shl 23) or ((m and 0x03FF) shl 13))
                }
            }
        }
    }
}
