// Ported from player/core/src/main/kotlin/com/pocketanim/core/Render.kt.
import Foundation

/**
 * Turning a decoded frame into drawing commands.
 *
 * Everything that decides *what the picture is* lives here, and nothing in this
 * file knows about a platform. The platform supplies only [PathSink]. That
 * boundary is the point: the same code that runs on the phone is run on the
 * desktop against the Cairo oracle in exporter/reference_render.py, so a
 * disagreement is a disagreement about the format rather than about Skia
 * (or, here, CoreGraphics).
 */

/** Manim's defaults at 16:9. */
public let FRAME_WIDTH: Float = 14.222222222222221
public let FRAME_HEIGHT: Float = 8.0

/**
 * Manim's cairo_line_width_multiple: stroke_width is in hundredths of a scene
 * unit. The canvas is set up in scene coordinates so the rasteriser scales
 * stroke widths for us, exactly as Cairo does for the oracle.
 */
public let STROKE_SCALE: Float = 0.01

/**
 * Where the renderer meets the platform. A sink receives paths already in scene
 * coordinates; the transform from scene to pixels belongs to the platform, so
 * stroke widths scale the same way they do in Manim.
 *
 * [lineTo], [fillAndStrokePath], [strokeStyle] and [drawImage] have defaults (in the extension below), as the
 * Kotlin interface's default methods; a sink that declares its own is called instead.
 */
public protocol PathSink: AnyObject {
    func beginPath()
    func moveTo(_ x: Float, _ y: Float)
    func cubicTo(_ x1: Float, _ y1: Float, _ x2: Float, _ y2: Float, _ x3: Float, _ y3: Float)
    func closeSubpath()
    /** Fill the current path with a premultiplied-by-nothing ARGB colour. */
    func fillPath(_ argb: Int32)
    func strokePath(_ argb: Int32, _ widthInSceneUnits: Float)

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
    func lineTo(_ x: Float, _ y: Float)

    /**
     * Fill and stroke the current path in one operation.
     *
     * Only ever called when the two colours are identical and opaque, which is
     * the common case for shaded 3D faces: Manim gives a face the same colour
     * for both, so two draws produce one appearance. The default splits it back
     * into the two calls, so this stays an optimisation rather than a format
     * change.
     */
    func fillAndStrokePath(_ argb: Int32, _ widthInSceneUnits: Float)

    /**
     * How strokes join and cap, set once a frame.
     *
     * Manim strokes with round joins and round caps, and a rasteriser has to
     * build the round join at every vertex -- 30,000 of them on a coastline.
     * A bevel is one flat cut instead, and at a stroke a pixel or two wide the
     * difference is sub-pixel. A mitre is not the alternative: measured on the
     * coastline it changes 0.88% of the pixels, because a polyline that doubles
     * back produces a mitre spike up to ten stroke widths long.
     *
     * Caps stay round either way. There are two per subpath against a join per
     * vertex, so they are not where the time goes.
     */
    func strokeStyle(round: Bool)

    /**
     * A raster picture, its pixel (u, v) at UL + u/width (UR - UL) + v/height (DL - UL) in scene coordinates, at
     * [ImageDraw.alpha]; [bytes] reads its PNG. A sink that cannot draw pictures leaves them out.
     */
    func drawImage(_ image: ImageDraw, _ bytes: (String) -> [UInt8]?)
}

public extension PathSink {
    func lineTo(_ x: Float, _ y: Float) {
        // Without the original handles, thirds reproduce the same curve.
        cubicTo(x, y, x, y, x, y)
    }

    func fillAndStrokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        fillPath(argb)
        strokePath(argb, widthInSceneUnits)
    }

    func strokeStyle(round: Bool) {}

    func drawImage(_ image: ImageDraw, _ bytes: (String) -> [UInt8]?) {}
}

/**
 * The parts of drawing that trade one cost for another.
 *
 * Each of these was measured to help on one device and could plausibly hurt on
 * another, or on another scene, so they are parameters rather than decisions
 * baked into the renderer -- and the benchmark can sweep them on the hardware
 * that matters instead of anyone arguing about it.
 *
 * - cull: drop 2D instances whose transformed bounds miss the frame.
 * - lines: emit a cubic whose handles lie on its chord as a line.
 * - backface: honour [Panm.CLOSED_SOLID] and drop faces that point away
 *   from the camera, which for a closed solid are behind faces that do not.
 *   Measured on the device: 1.46x fewer verbs and draws on MolecularStructure,
 *   which took it from 32.6 ms a frame to 22.9 and from 194 late frames to
 *   none. It is not quite free -- Manim's back faces show through the
 *   antialiased seams between the front faces and dapple them, so culling them
 *   changes about 1% of the pixels of a frame that is 3.5% ink -- and the
 *   exporter decides which shapes may be treated this way, not this flag.
 * - roundJoins: join strokes with an arc, as Manim does, rather than with
 *   a bevel. One join per vertex, so what it costs depends entirely on how many
 *   there are. At 22,719 verbs round joins were worth 119 of CartopyMap's 181
 *   late frames and a bevel shipped; at 17,625, after [lodTolerance] took the
 *   count down, they cost 4.3 ms at p50 and 2 late frames of 181, so they are
 *   back, because matching Manim is the default worth having whenever it is
 *   affordable. [RenderOptions] is why the bevel is one field away for whoever
 *   meets a slower phone.
 * - mergeTranslucent: merge a run of strokes that share a colour even when
 *   that colour is not opaque. Merging opaque strokes is exact; merging
 *   translucent ones is exact only where they do not overlap, since two
 *   overlapping translucent strokes blend twice when drawn apart and once when
 *   drawn together. It costs 0.117% of a frame's pixels.
 * - lodTolerance: drop points closer together than this, in scene units,
 *   when the segments either side of them are straight. The exporter already
 *   decimates artwork, but it has to decimate for the tightest zoom the program
 *   reaches. This spends the error budget where the frame actually is. Every
 *   dropped point lies within the tolerance of the segment that replaces it.
 *   Zero disables it.
 * - mergeVerbs: verb ceiling for a merged run of identical opaque strokes;
 *   zero draws every shape on its own. Skia rasterises a path on the GPU only
 *   below kMaxGPUPathRendererVerbs (16,384) and on the CPU above it, so merging
 *   is a saving only while the merged path stays under that. The default leaves
 *   half the limit as room for the shape that tips a run over it.
 */
public final class RenderOptions {
    public let cull: Bool
    public let lines: Bool
    public let backface: Bool
    public let roundJoins: Bool
    public let mergeTranslucent: Bool
    public let lodTolerance: Float
    public let mergeVerbs: Int

    public init(
        cull: Bool = true,
        lines: Bool = true,
        backface: Bool = true,
        roundJoins: Bool = true,
        mergeTranslucent: Bool = true,
        lodTolerance: Float = 0,
        mergeVerbs: Int = 8192
    ) {
        self.cull = cull
        self.lines = lines
        self.backface = backface
        self.roundJoins = roundJoins
        self.mergeTranslucent = mergeTranslucent
        self.lodTolerance = lodTolerance
        self.mergeVerbs = mergeVerbs
    }

    public static let DEFAULT = RenderOptions()

    /**
     * Options for drawing into a surface this many pixels wide.
     *
     * The level-of-detail tolerance is the only thing here that depends on
     * the target, and it has to: half a pixel is a promise about what a
     * viewer can see, which is a statement about pixels and not about scene
     * units. A caller that does not know its resolution gets [DEFAULT],
     * which does no dropping at all, because guessing wrong here would
     * silently coarsen someone's artwork.
     */
    public static func forSurface(_ widthPx: Int, errorPx: Float = 0.5) -> RenderOptions {
        RenderOptions(lodTolerance: errorPx / (Float(widthPx) / FRAME_WIDTH))
    }
}

public enum Renderer {

    /**
     * Project world points through a captured camera.
     *
     * Replicates ThreeDCamera.project_points. The device does this per frame,
     * which is why the IR carries 3D vertices and a camera track instead of
     * flattened output: a camera move costs 17 floats, not new geometry.
     */
    public static func project(_ points: [Float], _ camera: [Float], _ out: inout [Float]) {
        project(points, 0, points.count, camera, &out)
    }

    /**
     * [project], reading a slice of a shared buffer and writing from zero.
     *
     * The slice is how one frame's world points live in a single array rather
     * than one array per instance.
     */
    public static func project(_ points: [Float], _ at: Int, _ length: Int, _ camera: [Float], _ out: inout [Float]) {
        let cx = camera[0], cy = camera[1], cz = camera[2]
        let focal = camera[3], zoom = camera[4]

        var i = 0
        while i < length {
            let dx = points[at + i] - cx
            let dy = points[at + i + 1] - cy
            let dz = points[at + i + 2] - cz

            // rotation is row-major 3x3 at camera[5..13]; this is (p - c) @ R^T.
            let rx = camera[5] * dx + camera[6] * dy + camera[7] * dz
            let ry = camera[8] * dx + camera[9] * dy + camera[10] * dz
            let rz = camera[11] * dx + camera[12] * dy + camera[13] * dz

            let denominator = focal - rz
            let factor: Float
            if denominator < 0 {
                factor = 1e6
            } else if denominator == 0 {
                factor = focal / 1e-9
            } else {
                factor = focal / denominator
            }

            out[i] = rx * factor * zoom
            out[i + 1] = ry * factor * zoom
            out[i + 2] = rz
            i += 3
        }
    }

    /** Apply an instance's 3x4 transform to the canonical atlas points. */
    public static func transform(_ canonical: [Float], _ m: [Float], _ out: inout [Float]) {
        transformInto(canonical, m, &out)
    }

    /** Bounding-box centre, which is what Manim means by a mobject's centre. */
    private static func centre(_ points: [Float], _ at: Int, _ length: Int) -> (Float, Float, Float) {
        var minX = points[at], minY = points[at + 1], minZ = points[at + 2]
        var maxX = minX, maxY = minY, maxZ = minZ
        var i = at + 3
        let end = at + length
        while i < end {
            let x = points[i], y = points[i + 1], z = points[i + 2]
            if x < minX { minX = x }; if x > maxX { maxX = x }
            if y < minY { minY = y }; if y > maxY { maxY = y }
            if z < minZ { minZ = z }; if z > maxZ { maxZ = z }
            i += 3
        }
        return ((minX + maxX) * 0.5, (minY + maxY) * 0.5, (minZ + maxZ) * 0.5)
    }

    /**
     * Manim's get_shaded_rgb: light = 0.5 * dot(normal, to_sun)^3, halved again
     * when the face points away. The normal and the light position travel in
     * the IR, so this is derived on the device rather than baked into colours --
     * which is what lets one atlas entry serve every orientation of a solid.
     */
    private static func shadeOf(
        _ worldPoints: [Float], _ at: Int, _ length: Int, _ normal: [Float], _ camera: [Float]
    ) -> Float {
        let c = centre(worldPoints, at, length)
        let sx = camera[14] - c.0
        let sy = camera[15] - c.1
        let sz = camera[16] - c.2
        let norm = (sx * sx + sy * sy + sz * sz).squareRoot()
        if norm <= 1e-9 { return 0 }
        let dot = (normal[0] * sx + normal[1] * sy + normal[2] * sz) / norm
        var shade = 0.5 * dot * dot * dot
        if shade < 0 { shade *= 0.5 }
        return shade
    }

    /**
     * Sort key for painter order: the bounding-box centre rotated into camera
     * space, z component. Manim re-sorts every frame, so draw order changes as
     * the camera moves and cannot be baked in. Anything not flagged
     * shade_in_3d sorts last, matching Manim's np.inf.
     */
    private static func depthOf(
        _ worldPoints: [Float], _ at: Int, _ length: Int, _ flags: Int, _ camera: [Float]
    ) -> Float {
        if flags & Panm.SHADE_IN_3D == 0 { return Float.infinity }
        let c = centre(worldPoints, at, length)
        // rotation^T column 2 is rotation row 2.
        return camera[11] * c.0 + camera[12] * c.1 + camera[13] * c.2
    }

    private static func shift(_ argb: Int32, _ shade: Float) -> Int32 {
        if shade == 0 { return argb }
        let a = ushr(argb, 24) & 0xFF
        let r = Swift.min(Swift.max(Float((argb >> 16) & 0xFF) / 255 + shade, 0), 1)
        let g = Swift.min(Swift.max(Float((argb >> 8) & 0xFF) / 255 + shade, 0), 1)
        let b = Swift.min(Swift.max(Float(argb & 0xFF) / 255 + shade, 0), 1)
        return (a &<< 24) |
            (i32(kToInt(r * 255 + 0.5)) &<< 16) |
            (i32(kToInt(g * 255 + 0.5)) &<< 8) |
            i32(kToInt(b * 255 + 0.5))
    }

    /**
     * How far a cubic's handles may stray from the chord before it stops
     * counting as a line, in scene units. At the benchmark's 2148-pixel surface
     * a scene unit is 151 pixels, so this is a sixth of a pixel -- below what
     * antialiasing can express, and comfortably above the atlas's quantisation
     * step.
     */
    private static let LINE_TOLERANCE: Float = 1e-3

    /**
     * Transform an instance's points and say whether the result can be seen.
     *
     * The bounds come out of the same pass that writes the points, because the
     * separate pass they used to come from cost more than the culling saved:
     * on the device CartopyMap's geometry went from 7.9 ms a frame to 22.1 ms,
     * half its whole budget, for a scan whose only output is four floats.
     *
     * Culling is still worth doing -- 62% of that scene's verbs are off-screen
     * at its tightest zoom -- it just has to be free. A transform we were going
     * to do anyway can carry it.
     *
     * Only the 2D path uses this. Under a projecting camera the mapping is not
     * affine and a box does not survive it.
     */
    private static func transformVisible(_ canonical: [Float], _ m: [Float], _ out: inout [Float]) -> Bool {
        let m0 = m[0], m1 = m[1], m2 = m[2], m3 = m[3]
        let m4 = m[4], m5 = m[5], m6 = m[6], m7 = m[7]
        let m8 = m[8], m9 = m[9], m10 = m[10], m11 = m[11]

        var minX = Float.greatestFiniteMagnitude, maxX = -Float.greatestFiniteMagnitude
        var minY = Float.greatestFiniteMagnitude, maxY = -Float.greatestFiniteMagnitude

        var i = 0
        let end = canonical.count
        while i < end {
            let x = canonical[i], y = canonical[i + 1], z = canonical[i + 2]
            let tx = m0 * x + m1 * y + m2 * z + m3
            let ty = m4 * x + m5 * y + m6 * z + m7
            out[i] = tx
            out[i + 1] = ty
            out[i + 2] = m8 * x + m9 * y + m10 * z + m11
            if tx < minX { minX = tx }
            if tx > maxX { maxX = tx }
            if ty < minY { minY = ty }
            if ty > maxY { maxY = ty }
            i += 3
        }

        return maxX >= -FRAME_WIDTH * 0.5 && minX <= FRAME_WIDTH * 0.5 &&
            maxY >= -FRAME_HEIGHT * 0.5 && minY <= FRAME_HEIGHT * 0.5
    }

    /**
     * Emit one frame into [sink].
     *
     * Scratch buffers are grown, never reallocated per instance: the throughput
     * question on a low-end phone is decided by allocation and draw-call count
     * long before it is decided by arithmetic.
     */
    public static func drawFrame(
        _ scene: Frames,
        _ index: Int,
        _ sink: PathSink,
        _ options: RenderOptions = RenderOptions.DEFAULT
    ) throws {
        // instances() first: a computing source populates its atlas as a side
        // effect of producing the frame, so shape() is only valid afterwards.
        let instances = try scene.instances(index)
        let camera = try scene.camera(index)
        let images = try scene.images(index)
        if let camera = camera {
            draw3D(scene, instances, camera, sink, options)
            // A 3D frame is depth-sorted; a picture (only ever flat on a 2D stage) goes over it.
            for image in images { sink.drawImage(image, { scene.imageBytes($0) }) }
        } else {
            draw2D(scene, instances, sink, options, images)
        }
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
    private static func draw2D(
        _ scene: Frames,
        _ instances: [Instance],
        _ sink: PathSink,
        _ options: RenderOptions,
        _ images: [ImageDraw] = []
    ) {
        sink.strokeStyle(round: options.roundJoins)
        var world: [Float] = []
        let bytes: (String) -> [UInt8]? = { scene.imageBytes($0) }

        var runOpen = false
        var runColour: Int32 = 0
        var runWidth: Float = 0
        var runVerbs = 0
        var nextImage = 0

        for (position, inst) in instances.enumerated() {
            // The pictures that go in before this instance: an open run is stroked first, so what is under a
            // picture stays under it.
            while nextImage < images.count && images[nextImage].before <= position {
                if runOpen {
                    sink.strokePath(runColour, runWidth)
                    runOpen = false
                }
                sink.drawImage(images[nextImage], bytes)
                nextImage += 1
            }
            let canonical = scene.shape(inst.atlasId)
            if canonical.count < 12 { continue }

            let fill = inst.fill
            let stroke = inst.stroke
            let filled = ushr(fill, 24) & 0xFF > 0
            let stroked = ushr(stroke, 24) & 0xFF > 0 && inst.strokeWidth > 0
            if !filled && !stroked { continue }

            if world.count < canonical.count { world = [Float](repeating: 0, count: canonical.count) }
            let visible = transformVisible(canonical, inst.transform, &world)
            // An invisible instance contributes nothing, so it does not break
            // an open run either -- the shapes either side of it still share a
            // paint and still merge.
            if options.cull && !visible { continue }

            let width = inst.strokeWidth * STROKE_SCALE

            // Verbs this shape will contribute: one per curve, plus a move and
            // a close for each subpath. One subpath is the usual case and the
            // budget has slack, so the estimate need not be exact.
            let verbs = canonical.count / 12 + 2
            let mergeable = options.mergeVerbs > 0 && !filled && stroked &&
                (options.mergeTranslucent || ushr(stroke, 24) & 0xFF == 0xFF)

            let continues = runOpen && mergeable && stroke == runColour &&
                width == runWidth && runVerbs + verbs <= options.mergeVerbs
            if runOpen && !continues {
                sink.strokePath(runColour, runWidth)
                runOpen = false
            }

            if mergeable {
                if !runOpen {
                    sink.beginPath()
                    runOpen = true
                    runColour = stroke
                    runWidth = width
                    runVerbs = 0
                }
                appendPath(world, canonical.count, sink, options)
                runVerbs += verbs
                continue
            }

            sink.beginPath()
            appendPath(world, canonical.count, sink, options)
            if filled && stroked && fill == stroke && ushr(fill, 24) & 0xFF == 0xFF {
                sink.fillAndStrokePath(fill, width)
            } else {
                if filled { sink.fillPath(fill) }
                if stroked { sink.strokePath(stroke, width) }
            }
        }

        if runOpen { sink.strokePath(runColour, runWidth) }
        while nextImage < images.count {
            sink.drawImage(images[nextImage], bytes)
            nextImage += 1
        }
    }

    /**
     * The 3D case: depth sort, project, shade.
     *
     * The sort keeps the world points it computed rather than computing them
     * again in the draw pass, and orders an index permutation packed into longs
     * rather than an array of boxed pairs. On the molecule scene that is 2,910
     * fewer transforms and 2,910 fewer allocations per frame.
     */
    private static func draw3D(
        _ scene: Frames,
        _ instances: [Instance],
        _ camera: [Float],
        _ sink: PathSink,
        _ options: RenderOptions
    ) {
        let n = instances.count
        if n == 0 { return }
        sink.strokeStyle(round: options.roundJoins)

        // One buffer for every instance's world points, indexed by offset.
        // The molecule scene has 2,910 instances per frame; a FloatArray each
        // is 2,910 allocations a frame, which is what its 7.4 ms of geometry
        // time on the device was mostly made of.
        var offset = [Int](repeating: 0, count: n + 1)
        for i in 0..<n { offset[i + 1] = offset[i] + scene.shape(instances[i].atlasId).count }
        var world = [Float](repeating: 0, count: offset[n])

        var order = [Int64](repeating: 0, count: n)
        for i in 0..<n {
            let inst = instances[i]
            let canonical = scene.shape(inst.atlasId)
            transformInto(canonical, inst.transform, &world, offset[i])
            let depth = depthOf(world, offset[i], canonical.count, inst.flags, camera)
            order[i] = (Int64(sortable(depth)) << 32) | (Int64(i) & 0xFFFF_FFFF)
        }
        order.sort()

        var screen: [Float] = []
        for k in 0..<n {
            let i = Int(order[k] & 0xFFFF_FFFF)
            let inst = instances[i]
            let at = offset[i]
            let length = offset[i + 1] - at
            if length < 12 { continue }

            let fill = inst.fill
            let stroke = inst.stroke
            let filled = ushr(fill, 24) & 0xFF > 0
            let stroked = ushr(stroke, 24) & 0xFF > 0 && inst.strokeWidth > 0
            if !filled && !stroked { continue }

            // A back face of a closed solid is covered by a front face of the
            // same solid. Rotation row 2 is the camera's forward axis, and
            // project() makes a larger value mean nearer, so a face with a
            // positive component along it turns towards the viewer.
            let normal = inst.normal
            if options.backface && inst.flags & Panm.CLOSED_SOLID != 0, let normal = normal {
                let out: Float = inst.flags & Panm.NORMAL_INWARD != 0 ? -1 : 1
                let facing = out *
                    (camera[11] * normal[0] + camera[12] * normal[1] + camera[13] * normal[2])
                if facing <= 0 { continue }
            }

            if screen.count < length { screen = [Float](repeating: 0, count: length) }
            project(world, at, length, camera, &screen)
            var shade: Float = 0
            if inst.flags & Panm.SHADE_IN_3D != 0, let normal = inst.normal {
                shade = shadeOf(world, at, length, normal, camera)
            }

            sink.beginPath()
            appendPath(screen, length, sink, options)

            let width = inst.strokeWidth * STROKE_SCALE
            if filled && stroked && fill == stroke && ushr(fill, 24) & 0xFF == 0xFF {
                // Both shift by the same amount, so equal colours stay equal.
                sink.fillAndStrokePath(shift(fill, shade), width)
            } else {
                if filled { sink.fillPath(shift(fill, shade)) }
                if stroked { sink.strokePath(shift(stroke, shade), width) }
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
    private static func sortable(_ f: Float) -> Int32 {
        let bits = rawBits(f)
        return bits < 0 ? Int32.min &- bits : bits
    }

    /** [transform], writing only the first [canonical].count floats of [out]. */
    private static func transformInto(_ canonical: [Float], _ m: [Float], _ out: inout [Float], _ at: Int = 0) {
        var i = 0
        let end = canonical.count
        while i < end {
            let x = canonical[i], y = canonical[i + 1], z = canonical[i + 2]
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
    private static func appendPath(_ points: [Float], _ length: Int, _ sink: PathSink, _ options: RenderOptions) {
        let curves = length / 12 // 4 points x 3 floats
        let lod = options.lodTolerance
        let lodSquared = lod * lod
        var open = false
        let third: Float = 1 / 3
        let twoThirds: Float = 2 / 3

        // A run of points dropped by [RenderOptions.lodTolerance] is remembered
        // rather than discarded: whatever ends the run draws a straight segment
        // to the last of them, so a subpath never loses its end.
        var held = false
        var heldX: Float = 0
        var heldY: Float = 0
        var anchorX: Float = 0
        var anchorY: Float = 0

        // The subpath's first point, and the end of its last curve. A subpath
        // is closed only when those two meet -- see [closes].
        var startX: Float = 0
        var startY: Float = 0
        var endX: Float = 0
        var endY: Float = 0

        for i in 0..<curves {
            let o = i * 12
            if open {
                // Compare against the previous curve's end point.
                let p = o - 12 + 9
                let joined = Swift.abs(points[p] - points[o]) <= 1e-6 &&
                    Swift.abs(points[p + 1] - points[o + 1]) <= 1e-6 &&
                    Swift.abs(points[p + 2] - points[o + 2]) <= 1e-6
                if !joined {
                    if held { sink.lineTo(heldX, heldY); held = false }
                    if closes(startX, startY, endX, endY) { sink.closeSubpath() }
                    open = false
                }
            }
            if !open {
                sink.moveTo(points[o], points[o + 1])
                anchorX = points[o]; anchorY = points[o + 1]
                startX = points[o]; startY = points[o + 1]
                open = true
            }

            let ax = points[o], ay = points[o + 1]
            let ex = points[o + 9], ey = points[o + 10]
            endX = ex; endY = ey
            let dx = ex - ax, dy = ey - ay
            let straight = options.lines &&
                Swift.abs(points[o + 3] - (ax + dx * third)) <= LINE_TOLERANCE &&
                Swift.abs(points[o + 4] - (ay + dy * third)) <= LINE_TOLERANCE &&
                Swift.abs(points[o + 6] - (ax + dx * twoThirds)) <= LINE_TOLERANCE &&
                Swift.abs(points[o + 7] - (ay + dy * twoThirds)) <= LINE_TOLERANCE

            if straight {
                if lod > 0 {
                    let gx = ex - anchorX, gy = ey - anchorY
                    if gx * gx + gy * gy < lodSquared {
                        // Still within the tolerance of where the pen is: hold
                        // this point in case it turns out to be the last one.
                        held = true; heldX = ex; heldY = ey
                        continue
                    }
                }
                sink.lineTo(ex, ey)
            } else {
                // A curve must start where it was drawn from, so catch up first.
                if held { sink.lineTo(heldX, heldY); held = false }
                sink.cubicTo(points[o + 3], points[o + 4], points[o + 6], points[o + 7], ex, ey)
            }
            held = false
            anchorX = ex; anchorY = ey
        }

        if held { sink.lineTo(heldX, heldY) }
        if open && closes(startX, startY, endX, endY) { sink.closeSubpath() }
    }

    /**
     * Whether a subpath that started at (sx, sy) and ended at (ex, ey) is a
     * closed one. Manim's Camera asks the same question of every subpath it
     * draws, and a partial reveal is why it matters: Create hands the renderer
     * an open arc, and closing that arc draws a chord across its two ends that
     * Manim never draws. A shape that is closed brings its ends together
     * exactly, so the test needs no more tolerance than float noise.
     */
    private static func closes(_ sx: Float, _ sy: Float, _ ex: Float, _ ey: Float) -> Bool {
        Swift.abs(ex - sx) <= 1e-6 && Swift.abs(ey - sy) <= 1e-6
    }
}
