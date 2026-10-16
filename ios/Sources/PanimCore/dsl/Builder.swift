// Ported from player/core/src/main/kotlin/com/pocketanim/core/dsl/Builder.kt.
import Foundation

/** Manim's DrawBorderThenFill(stroke_width=2). */
private let OUTLINE_STROKE_WIDTH = 2.0

/**
 * One verb, resumable.
 *
 * These replaced loops that materialised every frame of every verb up front
 * and retained them -- 98.8 MB for one corpus scene, which is fatal on a
 * phone. Each verb's per-frame body was already a pure function of (state
 * captured at the verb's start, frame number), so splitting that out costs
 * nothing and lets the player hold one frame instead of all of them.
 *
 * Kotlin writes each verb as an anonymous object; here each is a set of closures over the verb's own captured
 * state, which is the same thing.
 */
private final class Runner {
    let frames: Int
    /**
     * Whether frames must come in order: a group that enters its parts as their turns come cannot be asked for
     * an earlier frame than the last one; it is entered again from its start for that.
     */
    let forwardOnly: Bool
    /** Capture whatever the per-frame body reads; put the object on stage. */
    let enter: () throws -> Void
    /** Put the scene into the state frame [k] of this verb should show. */
    let render: (Int) throws -> Void
    /** Settle the end-of-verb state that the next verb inherits. */
    let exit: () throws -> Void

    init(
        frames: Int, forwardOnly: Bool = false, enter: @escaping () throws -> Void,
        render: @escaping (Int) throws -> Void, exit: @escaping () throws -> Void
    ) {
        self.frames = frames
        self.forwardOnly = forwardOnly
        self.enter = enter
        self.render = render
        self.exit = exit
    }
}

/** Scene state at a verb boundary, so seeking back need not start over. */
private final class Checkpoint {
    let objects: OrderedMap<Obj>
    let shapeCount: Int
    let phi: Double
    let theta: Double

    init(_ objects: OrderedMap<Obj>, _ shapeCount: Int, _ phi: Double, _ theta: Double) {
        self.objects = objects
        self.shapeCount = shapeCount
        self.phi = phi
        self.theta = theta
    }
}

/**
 * The timeline state machine.
 *
 * Split out from [Interpreter] because it is long and it is the part that has
 * to match Manim verb for verb. Each branch below names the Manim behaviour it
 * reproduces; where Manim does something surprising -- a group's children
 * lagging, a wait's last frame not advancing the camera -- the surprise is
 * recorded next to the code that pays for it, because every one of them cost a
 * measured fidelity regression to find.
 */
final class Builder {
    private let program: Program
    private let loader: AssetLoader

    let fps: Int
    let background: Int32
    let is3d: Bool
    private var shapes: [[Double]] = []
    private var objects = OrderedMap<Obj>()

    private var phi: Double
    private var theta: Double
    private var zoom: Double

    /** The frame just produced, held so the renderer can read it. */
    private var current: [Instance] = []
    private var currentCamera: [Float]? = nil

    /**
     * Each atlas entry as floats: a frame asks for every shape it draws, and a copy per shape per frame was most
     * of what a frame allocated. Kotlin keys its cache on the identity of the points it was made from; Swift
     * arrays have no identity, so an entry is dropped whenever its shape is replaced, added or removed instead.
     */
    private var floatShapes: [[Float]?] = []

    init(_ program: Program, _ loader: AssetLoader) {
        self.program = program
        self.loader = loader
        fps = program.fps
        background = program.background
        is3d = program.is3d
        phi = program.phi
        theta = program.theta
        zoom = program.zoom
    }

    func shape(_ atlasId: Int) -> [Float] {
        if let cached = floatShapes[atlasId] { return cached }
        let out = shapes[atlasId].map { Float($0) }
        floatShapes[atlasId] = out
        return out
    }

    private func addShape(_ points: [Double]) {
        shapes.append(points)
        floatShapes.append(nil)
    }

    private func setShape(_ index: Int, _ points: [Double]) {
        shapes[index] = points
        floatShapes[index] = nil
    }

    private func truncateShapes(_ count: Int) {
        while shapes.count > count {
            shapes.removeLast()
            floatShapes.removeLast()
        }
    }

    /** Where each drifting backdrop's instances are in the frame just built: name -> (first, end). */
    private(set) var currentDrifting: [String: [Int]] = [:]

    func frameInstances() -> [Instance] { current }

    func drift(_ name: String) -> Drift? { program.drifts[name] }
    func frameCamera() -> [Float]? { currentCamera }

    /** The frame's objects in draw order as (z, instances drawn once it is done): where a picture goes in. */
    private var currentZ: [Double] = []
    private var currentEnds: [Int] = []

    /** How many of the frame's instances are drawn before a picture at [z]: those of every object at or below it. */
    func instancesAtOrBelow(_ z: Double) -> Int {
        var count = 0
        for i in 0..<currentZ.count {
            if currentZ[i] > z { break }
            count = currentEnds[i]
        }
        return count
    }

    var images: [ImageSpec] { program.images }
    func imageBytes(_ src: String) -> [UInt8]? { loader.image(src) }

    // ---- declarations -----------------------------------------------------

    /** Surfaces declared as program become objects like anything else. */
    private func declareSurfaces() throws {
        for surface in program.surfaces {
            let faces = try Interpreter.tessellate(surface.fn, surface.uRange, surface.vRange, surface.resolution)
            let vRes = surface.resolution[1]
            let alpha = kToInt(surface.alpha * 255)
            var instances: [Inst] = []
            instances.reserveCapacity(faces.count)
            var normals = [[Double]?](repeating: nil, count: faces.count)

            for (index, face) in faces.enumerated() {
                let i = index / vRes
                let j = index % vRes
                let colour = surface.colors[(i + j) % surface.colors.count]
                let centre = meanOf(face)
                var centred = [Double](repeating: 0, count: face.count)
                for k in 0..<face.count { centred[k] = face[k] - centre[k % 3] }
                addShape(centred)

                var transform = identity()
                transform[3] = centre[0]; transform[7] = centre[1]; transform[11] = centre[2]
                let rgba = [(colour >> 16) & 0xFF, (colour >> 8) & 0xFF, colour & 0xFF, alpha]
                instances.append(Inst(shapes.count - 1, transform, rgba, rgba, surface.stroke))
                normals[index] = Interpreter.planeNormal(face)
            }

            objects[surface.name] = Obj(
                kind: "asset", visible: true, instances: instances,
                normals: normals, glyphIds: Array(0..<instances.count)
            )
        }
    }

    private func declareAssets() throws {
        for (name, spec) in program.assets.entries {
            let (kind, assetId) = spec
            let asset = try Scene.parse(try loader.asset(assetId))
            // A text asset carries instances only; its geometry is the shared
            // library, which is what makes a second caption cost zero bytes.
            let geometry = kind == "text" ? try Scene.parse(try loader.glyphLibrary()).atlas : asset.atlas
            let instances = try asset.frame(0)

            let offset = shapes.count
            for shape in geometry { addShape(shape.map { Double($0) }) }

            var minX = Double.greatestFiniteMagnitude, minY = Double.greatestFiniteMagnitude
            var minZ = Double.greatestFiniteMagnitude
            var maxX = -Double.greatestFiniteMagnitude, maxY = -Double.greatestFiniteMagnitude
            var maxZ = -Double.greatestFiniteMagnitude
            var any = false
            for inst in instances {
                let pts = try element(geometry, inst.atlasId)
                let m = inst.transform
                var i = 0
                while i < pts.count {
                    // Float arithmetic, as Kotlin's FloatArray maths is, widened only to compare.
                    let x = m[0] * pts[i] + m[1] * pts[i + 1] + m[2] * pts[i + 2] + m[3]
                    let y = m[4] * pts[i] + m[5] * pts[i + 1] + m[6] * pts[i + 2] + m[7]
                    let z = m[8] * pts[i] + m[9] * pts[i + 1] + m[10] * pts[i + 2] + m[11]
                    if Double(x) < minX { minX = Double(x) }; if Double(x) > maxX { maxX = Double(x) }
                    if Double(y) < minY { minY = Double(y) }; if Double(y) > maxY { maxY = Double(y) }
                    if Double(z) < minZ { minZ = Double(z) }; if Double(z) > maxZ { maxZ = Double(z) }
                    any = true
                    i += 3
                }
            }
            let centre = any ? [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2] : [0.0, 0.0, 0.0]

            objects[name] = Obj(
                kind: "asset",
                // Declaring a thing is not the same as it being on stage; an
                // asset waits for a verb that puts it there.
                visible: false,
                centre: centre,
                instances: instances.map { inst in
                    Inst(
                        inst.atlasId + offset,
                        inst.transform.map { Double($0) },
                        rgbaOf(inst.fill), rgbaOf(inst.stroke), Double(inst.strokeWidth)
                    )
                },
                flags: instances.map { $0.flags },
                normals: instances.map { inst in inst.normal.map { n in n.map { Double($0) } } },
                // Library-relative ids, kept so two assets can be matched glyph
                // for glyph even though each is offset into the shape list.
                glyphIds: instances.map { $0.atlasId },
                z: program.z[name] ?? 0.0
            )
        }
    }

    /** Each baked clip's sampled frames and where its shapes start in [shapes]. */
    private var clips: [String: (Scene, Int)] = [:]

    private func declareClips() throws {
        // A looping period is one asset that many clips play: it is read, and its shapes added, once.
        var loaded: [String: (Scene, Int)] = [:]
        for (name, assetId) in program.clips.entries {
            if let known = loaded[assetId] {
                clips[name] = known
            } else {
                let clip = try Scene.parse(try loader.asset(assetId))
                let offset = shapes.count
                for shape in clip.atlas { addShape(shape.map { Double($0) }) }
                loaded[assetId] = (clip, offset)
                clips[name] = (clip, offset)
            }
            objects[name] = Obj(kind: "asset", visible: false, z: program.z[name] ?? 0.0)
        }
    }

    /**
     * The object a verb acts on. A declared primitive that no verb has put on stage yet enters it here, as
     * dsl/interpret.py's NEEDS_OBJECT does for the same verbs: TransformFromCopy's copy is first seen by the
     * transform that carries it, and looking it up crashed the phone where the reference played on.
     */
    private func need(_ name: String) throws -> Obj {
        if let obj = objects[name] { return obj }
        if program.shapes.contains(name) {
            let obj = try newShape(name)
            objects[name] = obj
            return obj
        }
        return try objects.getValue(name)
    }

    /** A declared primitive entering the stage. */
    private func newShape(_ name: String, alpha: Double = 1.0) throws -> Obj {
        let spec = try program.shapes.getValue(name)
        return Obj(
            kind: "shape", visible: true, points: try geometryFor(spec), alpha: alpha,
            strokeRgb: spec.stroke, width: spec.width, z: program.z[name] ?? 0.0
        )
    }

    // ---- emit -------------------------------------------------------------

    private func cameraRecord() -> [Float] {
        let m = Interpreter.cameraMatrix(phi, theta)
        var out = [Float](repeating: 0, count: Panm.CAMERA_FLOATS)
        out[3] = Builder.FOCAL; out[4] = Float(zoom)
        for k in 0..<9 { out[5 + k] = Float(m[k]) }
        out[14] = -7; out[15] = -9; out[16] = 10
        return out
    }

    /**
     * Where the last emit started appending primitive geometry, and where it
     * stopped. A primitive's points go into the atlas at emit time and only the
     * frame just produced refers to them, so if nothing was appended since,
     * they can be wound back before the next emit appends its own. Without
     * this every visible primitive added a shape per frame for the life of the
     * scene -- unbounded growth over a lecture of holds.
     */
    private var emitStart = -1
    private var emitEnd = -1

    /** Frames built so far: unchanged between two frames, the picture is the same (a hold). */
    private(set) var version: Int64 = 0

    /** Build the frame the stage now shows; false when none is built (a verb played only for its end). */
    @discardableResult
    private func emit() -> Bool {
        if quiet { return false }
        version += 1
        if emitEnd >= 0 && shapes.count == emitEnd && emitStart >= 0 && emitStart <= emitEnd {
            truncateShapes(emitStart)
        }
        emitStart = shapes.count
        var frame: [Instance] = []
        // Stable: equal z keeps declaration order, which is every program
        // written before `z=` existed.
        let staged = objects.entries.filter { $0.value.visible }.stableSortedByDouble { $0.value.z }
        var zs = [Double](repeating: 0, count: staged.count)
        var ends = [Int](repeating: 0, count: staged.count)
        var drifting: [String: [Int]] = [:]
        for (at, entry) in staged.enumerated() {
            let obj = entry.value
            let first = frame.count
            zs[at] = obj.z
            if obj.kind == "asset" {
                let normals = obj.normals
                let flags = obj.flags
                for (index, inst) in obj.instances.enumerated() {
                    let normal: [Double]? = (normals != nil && index < normals!.count) ? normals![index] : nil
                    let flag: Int
                    if let flags = flags, index < flags.count {
                        flag = flags[index]
                    } else {
                        flag = normal != nil ? Panm.SHADE_IN_3D : 0
                    }
                    let composed = compose(obj.xform, inst.transform)
                    frame.append(Instance(
                        slot: frame.count,
                        atlasId: inst.atlasId,
                        flags: flag,
                        transform: composed.map { Float($0) },
                        fill: argbOf(inst.fill),
                        stroke: argbOf(inst.stroke),
                        strokeWidth: Float(inst.width),
                        normal: normal.map { n in n.map { Float($0) } }
                    ))
                }
            } else {
                addShape(obj.points!)
                frame.append(Instance(
                    slot: frame.count,
                    atlasId: shapes.count - 1,
                    flags: 0,
                    transform: identity().map { Float($0) },
                    fill: argbOf([obj.fill[0], obj.fill[1], obj.fill[2], kToInt(Double(obj.fill[3]) * obj.alpha)]),
                    stroke: argbOf([
                        (obj.strokeRgb >> 16) & 0xFF,
                        (obj.strokeRgb >> 8) & 0xFF,
                        obj.strokeRgb & 0xFF,
                        kToInt(255 * obj.alpha),
                    ]),
                    strokeWidth: Float(obj.width),
                    normal: nil
                ))
            }
            ends[at] = frame.count
            if program.drifts[entry.key] != nil { drifting[entry.key] = [first, frame.count] }
        }
        currentDrifting = drifting
        emitEnd = shapes.count
        currentZ = zs
        currentEnds = ends
        current = frame
        currentCamera = is3d ? cameraRecord() : nil
        return true
    }

    // ---- helpers ----------------------------------------------------------

    private func meanOf(_ points: [Double]) -> [Double] {
        let n = points.count / 3
        var out = [0.0, 0.0, 0.0]
        for i in 0..<n { for k in 0..<3 { out[k] += points[i * 3 + k] } }
        for k in 0..<3 { out[k] /= Double(n) }
        return out
    }

    private func rgbaOf(_ argb: Int32) -> [Int] {
        [Int((argb >> 16) & 0xFF), Int((argb >> 8) & 0xFF), Int(argb & 0xFF), Int(ushr(argb, 24) & 0xFF)]
    }

    private func argbOf(_ rgba: [Int]) -> Int32 {
        (i32(rgba[3]) &<< 24) | (i32(rgba[0]) &<< 16) | (i32(rgba[1]) &<< 8) | i32(rgba[2])
    }

    private func geometryFor(_ spec: ShapeSpec) throws -> [Double] {
        var points: [Double]
        switch spec.kind {
        case "circle": points = Verbs.circle(spec.size)
        case "rect":
            guard let extent = spec.extent else { throw PanimError.nullPointer("a rect without wh=") }
            points = Verbs.rectangle(try element(extent, 0), try element(extent, 1))
        default: points = Verbs.square(spec.size)
        }
        var i = 0
        while i < points.count {
            points[i] += try element(spec.at, 0)
            points[i + 1] += try element(spec.at, 1)
            i += 3
        }
        return points
    }

    private func isAsset(_ name: String) -> Bool { objects[name]?.kind == "asset" }

    private static let FOCAL: Float = 20.0

    /** `obj.points!!`. */
    private func pointsOf(_ obj: Obj) throws -> [Double] {
        guard let points = obj.points else { throw PanimError.nullPointer("an asset has no points of its own") }
        return points
    }

    // ---- timeline ---------------------------------------------------------

    private var runners: [Runner] = []
    /** Global frame index at which each verb starts; the last entry is the total. */
    private var starts: [Int] = [0]
    /**
     * The `show` and `hide` verbs attached to each step, in the order the
     * program wrote them. Neither produces a frame, so they ride the verb that
     * follows; order between them matters, so they share one list.
     */
    private var staging: [Int: [Step]] = [:]
    private var checkpoints: [Int: Checkpoint] = [:]

    /** Verb boundaries between kept copies of the stage (see [reach]). */
    private let CHECKPOINT_EVERY = 32

    private var cursorStep = -1
    private var cursorFrame = -1

    var frameCount: Int { starts.last! }

    private func foldComposites(_ steps: [Step]) -> [Step] {
        var folded: [Step] = []
        var cursor = 0
        while cursor < steps.count {
            let step = steps[cursor]
            cursor += 1
            if let par = step as? Step.Par {
                var members: [Step] = []
                var carried: [Step] = []
                while members.count < par.count && cursor < steps.count {
                    let next = steps[cursor]
                    cursor += 1
                    if next is Step.Show || next is Step.Hide { carried.append(next) } else { members.append(next) }
                }
                if !members.isEmpty { folded.append(Step.Parallel(foldComposites(members))) }
                folded.append(contentsOf: carried)
            } else if let header = step as? Step.LagHeader {
                var members: [Step] = []
                for run in header.runs {
                    var slice: [Step] = []
                    var left = run
                    while left > 0 && cursor < steps.count {
                        slice.append(steps[cursor])
                        cursor += 1
                        left -= 1
                    }
                    let inner = foldComposites(slice)
                    if inner.count == 1 {
                        members.append(inner[0])
                    } else if !inner.isEmpty {
                        members.append(Step.Sequence(inner))
                    }
                }
                if !members.isEmpty { folded.append(Step.Lag(header.ratio, header.seconds, members)) }
            } else {
                folded.append(step)
            }
        }
        return folded
    }

    func prepare() throws {
        try declareSurfaces()
        try declareAssets()
        try declareClips()

        // Rewrite create-on-asset to a lagged reveal in a PRE-PASS. Appending
        // the rewrite to the list being iterated pushed every asset reveal to
        // the end, so camera moves ran before the things they were looking at.
        let rewritten: [Step] = program.timeline.map { step in
            if let create = step as? Step.Create, !create.removing, isAsset(create.name) {
                return Step.RevealSequence(create.name, create.seconds, create.lag ?? 1.0)
            }
            return step
        }

        let folded = foldComposites(rewritten)

        // `show` and `hide` produce no frame, so they are attached to the verb
        // that follows rather than being verbs themselves. Manim also renders
        // the scene's opening state once at t=0 before the first animation's
        // first step -- that is the one-frame hold below, and without it every
        // later frame is one early and the closing frame is missing.
        var expanded: [Step] = []
        var pending: [Step] = []
        var opened = false
        for step in folded {
            if step is Step.Show || step is Step.Hide {
                pending.append(step)
                continue
            }
            if !opened {
                opened = true
                // Anything added before the first play is on stage for it.
                staging[expanded.count] = pending
                pending.removeAll()
                expanded.append(Step.Wait(1.0 / Double(fps)))
            }
            staging[expanded.count] = pending
            pending.removeAll()
            expanded.append(step)
        }

        runners = try expanded.map { try runnerFor($0) }
        starts = [Int](repeating: 0, count: runners.count + 1)
        for i in 0..<runners.count { starts[i + 1] = starts[i] + runners[i].frames }
        checkpoint(0)
    }

    private func checkpoint(_ stepIndex: Int) {
        var copy = OrderedMap<Obj>()
        for (name, obj) in objects.entries { copy[name] = obj.copy() }
        checkpoints[stepIndex] = Checkpoint(copy, shapes.count, phi, theta)
    }

    private func restore(_ stepIndex: Int) throws {
        guard let saved = checkpoints[stepIndex] else {
            throw PanimError.noSuchElement("Key \(stepIndex) is missing in the map.")
        }
        objects.removeAll()
        for (name, obj) in saved.objects.entries { objects[name] = obj.copy() }
        // Reveals append partial geometry to the atlas; replaying without
        // truncating would append it again on every seek.
        truncateShapes(saved.shapeCount)
        emitStart = -1
        emitEnd = -1
        phi = saved.phi
        theta = saved.theta
    }

    private func stepContaining(_ frame: Int) -> Int {
        for i in 0..<runners.count { if frame < starts[i + 1] { return i } }
        return runners.count - 1
    }

    /**
     * Produce one frame.
     *
     * A verb's frame is a pure function of the stage at its start and the frame number (see [Runner]), so only the
     * frame asked for is computed: playing on, a frame late or not, and a seek within the verb cost one frame. Into a
     * later verb, close by, the verbs between are played on from here, each as its last frame; further, or back, the
     * stage comes from the nearest kept boundary ([reach]). Before, every frame on the way was built in full, and a
     * late frame at a verb's end sent the player back to a boundary 30 verbs off: playing stuttered and seeking took
     * most of a second on a phone.
     */
    func seek(_ index: Int) throws {
        try require(frameCount - 1 >= 0,
                    "Cannot coerce value to an empty range: maximum \(frameCount - 1) is less than minimum 0.")
        let target = Swift.min(Swift.max(index, 0), frameCount - 1)
        let step = stepContaining(target)
        let local = target - starts[step]

        if step == cursorStep && (local >= cursorFrame || !runners[step].forwardOnly) {
            if local != cursorFrame { try runners[step].render(local) }
            cursorFrame = local
            return
        }

        if step != cursorStep && cursorStep >= 0 && step > cursorStep && step - cursorStep <= CHECKPOINT_EVERY {
            // Playing on: this verb to its end, then the ones between, whole.
            try quietly {
                let runner = runners[cursorStep]
                if runner.frames > 0 && cursorFrame != runner.frames - 1 { try runner.render(runner.frames - 1) }
                try runner.exit()
                var at = cursorStep + 1
                keepBoundary(at)
                while at < step {
                    try playWhole(at)
                    at += 1
                    keepBoundary(at)
                }
            }
            // As restore() leaves it: the next frame's shapes start a new run.
            emitStart = -1
            emitEnd = -1
        } else {
            try reach(step)
        }
        try applyStaging(step)
        try runners[step].enter()
        try runners[step].render(local)
        cursorStep = step
        cursorFrame = local
    }

    /** Back to the start of the timeline, as after [prepare]: the next seek rebuilds from the first boundary. */
    func recover() {
        try? restore(0)
        cursorStep = -1
        cursorFrame = -1
        quiet = false
    }

    private func keepBoundary(_ step: Int) {
        if step % CHECKPOINT_EVERY == 0 && checkpoints[step] == nil { checkpoint(step) }
    }

    /** Verbs played for the stage they leave, not shown: no frame is built for them. */
    private var quiet = false

    private func quietly(_ body: () throws -> Void) rethrows {
        quiet = true
        defer { quiet = false }
        try body()
    }

    /**
     * The stage as it stands at the start of [step]: the nearest kept boundary
     * at or before it, then the verbs between played whole. A copy of the stage
     * was kept at every boundary, and an hour's lecture is thousands of verbs:
     * the copies ran a phone out of memory. One every CHECKPOINT_EVERY verbs
     * keeps a seek to at most that many verbs of replay.
     */
    private func reach(_ step: Int) throws {
        guard var from = checkpoints.keys.filter({ $0 <= step }).max() else {
            throw PanimError.noSuchElement("Collection is empty.")
        }
        try restore(from)
        try quietly {
            while from < step {
                try playWhole(from)
                from += 1
                keepBoundary(from)
            }
        }
        // As restore() leaves it, after the verbs played up to the step.
        emitStart = -1
        emitEnd = -1
    }

    private func applyStaging(_ stepIndex: Int) throws {
        for step in staging[stepIndex] ?? [] {
            if let hide = step as? Step.Hide {
                // A `hide` may name an object this interpreter never put on
                // stage -- a fadeout drops its object outright -- so a hide for
                // an absent name is a no-op rather than an error.
                objects[hide.name]?.visible = false
            } else if let show = step as? Step.Show {
                // A declared shape no verb put on stage yet is put there, as the reference does.
                try need(show.name).visible = true
            }
        }
    }

    /** Run a verb for the stage it leaves: its last frame (each frame stands on its own), then its end. */
    private func playWhole(_ stepIndex: Int) throws {
        try applyStaging(stepIndex)
        let runner = runners[stepIndex]
        try runner.enter()
        if runner.frames > 0 { try runner.render(runner.frames - 1) }
        try runner.exit()
    }

    /**
     * Frames Manim renders for an animation: len(np.arange(0, t, 1/fps)), a
     * ceiling. (t * fps).toInt() agreed only on whole frames, and a narrated
     * beat never is one, so a lecture ran a frame short per play.
     */
    private func frames(_ seconds: Double) -> Int {
        seconds <= 0.0 ? 0 : kToInt((seconds / (1.0 / Double(fps))).rounded(.up))
    }

    /** Frames Manim writes for a static wait: freeze_current_frame's int(d / dt). */
    private func waitFrames(_ seconds: Double) -> Int {
        seconds <= 0.0 ? 0 : kToInt(seconds / (1.0 / Double(fps)))
    }

    private func runnerFor(_ step: Step) throws -> Runner {
        switch step {
        case let s as Step.Create: return createRunner(s)
        case let s as Step.Transform: return transformRunner(s)
        case let s as Step.Xform: return xformRunner(s)
        case let s as Step.Run: return runRunner(s)
        case let s as Step.Stroke: return strokeRunner(s)
        case let s as Step.Grow: return growRunner(s)
        case let s as Step.Write: return revealRunner(s.name, s.seconds, sequential: false)
        case let s as Step.Fill: return fillRunner(s)
        case let s as Step.Unwrite: return unwriteRunner(s)
        case let s as Step.RevealSequence: return revealRunner(s.name, s.seconds, sequential: true, sequenceLag: s.lag)
        case let s as Step.LaggedGrow: return laggedGrowRunner(s)
        case let s as Step.Fade:
            return fadeRunner(s.name, s.seconds, fadingIn: true, s.shift, s.from, s.rate)
        case let s as Step.FadeOut:
            return fadeRunner(s.name, s.seconds, fadingIn: false, s.shift, s.from, s.rate)
        case let s as Step.Rotate: return rotateRunner(s)
        case let s as Step.Indicate: return indicateRunner(s)
        case let s as Step.Morph: return morphRunner(s)
        case let s as Step.Move: return moveRunner(s)
        case let s as Step.Spin: return spinRunner(s)
        case let s as Step.Wait: return holdRunner(waitFrames(s.seconds))
        case let s as Step.Parallel: return parallelRunner(try s.members.map { try runnerFor($0) })
        case let s as Step.Lag: return try lagRunner(s)
        case let s as Step.Sequence: return sequenceRunner(try s.members.map { try runnerFor($0) })
        default: return holdRunner(0) // Par, LagHeader, Show, Hide
        }
    }

    /**
     * Several verbs played in order, as one child of a lag.
     *
     * Children enter in turn. Entering them all at the start let a later
     * child capture the scene before an earlier one had changed it -- a
     * fade-in followed by a fade-out on the same object captured the
     * object before it was on stage.
     */
    private func sequenceRunner(_ children: [Runner]) -> Runner {
        var reached = -1

        func reach(_ index: Int) throws {
            while reached < index {
                if reached >= 0 {
                    let it = children[reached]
                    if it.frames > 0 { try it.render(it.frames - 1) }
                    try it.exit()
                }
                reached += 1
                try children[reached].enter()
            }
        }

        return Runner(
            frames: children.reduce(0) { $0 + $1.frames },
            forwardOnly: true,
            enter: { reached = -1 },
            render: { k in
                var left = k
                for (index, child) in children.enumerated() {
                    if child.frames <= 0 { continue }
                    if left < child.frames || index == children.count - 1 {
                        try reach(index)
                        try child.render(Swift.min(left, child.frames - 1))
                        return
                    }
                    left -= child.frames
                }
            },
            exit: {
                if children.isEmpty { return }
                try reach(children.count - 1)
                try children[children.count - 1].exit()
            }
        )
    }

    private func lagRunner(_ step: Step.Lag) throws -> Runner {
        let children = try step.members.map { try runnerFor($0) }
        let frames = self.frames(step.seconds)
        let fps = self.fps
        /**
         * A child enters when its turn starts, not when the group does.
         * Entering them all up front put every later child on stage at
         * full opacity before its fade began -- all four lines of a
         * chapter card drawn at once, then faded in again one by one.
         * Manim begins each child at its alpha-0 state, which for a fade,
         * a grow or a create draws nothing.
         */
        var entered = [Bool](repeating: false, count: children.count)
        return Runner(
            frames: frames,
            forwardOnly: true,
            enter: { entered = [Bool](repeating: false, count: children.count) },
            render: { [unowned self] k in
                let runTimes = children.map { Double($0.frames) / Double(fps) }
                var starts = [Double](repeating: 0, count: children.count)
                if children.count > 1 {
                    for i in 1..<children.count { starts[i] = starts[i - 1] + runTimes[i - 1] * step.ratio }
                }
                var maxEnd = 1.0
                if !children.isEmpty {
                    maxEnd = starts[0] + runTimes[0]
                    for i in 1..<children.count { maxEnd = kMax(maxEnd, starts[i] + runTimes[i]) }
                }
                let internalT = Double(k + 1) / Double(Swift.max(frames, 1)) * Swift.max(maxEnd, 1e-6)
                for (i, child) in children.enumerated() {
                    if child.frames <= 0 || runTimes[i] <= 0.0 { continue }
                    let local = coerceIn((internalT - starts[i]) / runTimes[i], 0.0, 1.0)
                    if local <= 0.0 { continue }
                    if !entered[i] {
                        entered[i] = true
                        try child.enter()
                    }
                    try child.render(coerceIn(kToInt(local * Double(child.frames)) - 1, 0, child.frames - 1))
                }
                self.emit()
            },
            exit: {
                for (i, child) in children.enumerated() {
                    if !entered[i] {
                        entered[i] = true
                        try child.enter()
                        if child.frames > 0 { try child.render(child.frames - 1) }
                    }
                    try child.exit()
                }
            }
        )
    }

    /**
     * Manim begins every animation in a play() before interpolating any, so
     * all members enter first: two verbs on one object each capture it as it
     * was before either touched it. A member shorter than the group holds its
     * last frame rather than disappearing.
     */
    private func parallelRunner(_ children: [Runner]) -> Runner {
        Runner(
            frames: children.map { $0.frames }.max() ?? 0,
            forwardOnly: children.contains { $0.forwardOnly },
            enter: { for child in children { try child.enter() } },
            render: { k in for child in children { try child.render(Swift.max(Swift.min(k, child.frames - 1), 0)) } },
            exit: { for child in children { try child.exit() } }
        )
    }

    private func holdRunner(_ count: Int) -> Runner {
        /** A hold shows one picture throughout: it is built once, and the frames after it are the same frame. */
        var built = false
        return Runner(
            frames: count,
            enter: { built = false },
            render: { [unowned self] _ in if !built { built = self.emit() } },
            exit: {}
        )
    }

    private func createRunner(_ step: Step.Create) -> Runner {
        let frames = self.frames(step.seconds)
        let rate = Verbs.rate(step.rate)
        var full: [Double] = []
        var obj: Obj! = nil
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.newShape(step.name)
                full = obj.points!
                self.objects[step.name] = obj
            },
            render: { [unowned self] k in
                var alpha = rate(Double(k + 1) / Double(frames))
                if step.removing { alpha = 1.0 - alpha }
                obj.points = Verbs.pointwiseBecomePartial(full, 0.0, alpha)
                self.emit()
            },
            exit: {
                if step.removing {
                    obj.points = [Double](repeating: 0, count: full.count)
                    obj.visible = false
                } else {
                    obj.points = full
                }
            }
        )
    }

    private func transformRunner(_ step: Step.Transform) -> Runner {
        let frames = self.frames(step.seconds)
        let rate = Verbs.rate(step.rate)
        var obj: Obj! = nil
        var startPts: [Double] = []
        var endPts: [Double] = []
        var c0: [Int] = []
        var c1: [Int] = []
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.source)
                let targetSpec = try self.program.shapes.getValue(step.target)
                let aligned = Verbs.align(try self.pointsOf(obj), try self.geometryFor(targetSpec))
                startPts = aligned.0
                endPts = aligned.1
                c0 = [(obj.strokeRgb >> 16) & 0xFF, (obj.strokeRgb >> 8) & 0xFF, obj.strokeRgb & 0xFF]
                c1 = [(targetSpec.stroke >> 16) & 0xFF, (targetSpec.stroke >> 8) & 0xFF, targetSpec.stroke & 0xFF]
            },
            render: { [unowned self] k in
                let alpha = rate(Double(k + 1) / Double(frames))
                let bulge = sin(Double.pi * alpha) * step.arc
                var out = [Double](repeating: 0, count: startPts.count)
                var i = 0
                while i < out.count {
                    let dx = endPts[i] - startPts[i]
                    let dy = endPts[i + 1] - startPts[i + 1]
                    out[i] = startPts[i] + dx * alpha - dy * bulge
                    out[i + 1] = startPts[i + 1] + dy * alpha + dx * bulge
                    out[i + 2] = startPts[i + 2] + (endPts[i + 2] - startPts[i + 2]) * alpha
                    i += 3
                }
                obj.points = out
                var rgb = 0
                for i in 0..<3 {
                    rgb = (rgb << 8) | coerceIn(pyRound(Double(c0[i]) + Double(c1[i] - c0[i]) * alpha), 0, 255)
                }
                obj.strokeRgb = Int(i32(rgb))
                self.emit()
            },
            exit: {}
        )
    }

    /**
     * GrowFromCenter: points scale up from a centre. A primitive scales its
     * points; an asset scales its instances. The asset branch mirrors the
     * reference -- programs from before `laggedgrow` covered groups carry
     * `grow` on an asset, and this threw on the missing points.
     */
    private func growRunner(_ step: Step.Grow) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var base: [Double]? = nil
        var baseInstances: [Inst]? = nil
        var centre: [Double] = []
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                if !self.objects.contains(step.name) { self.objects[step.name] = try self.newShape(step.name) }
                obj = try self.need(step.name)
                obj.visible = true
                let forced = step.at
                if obj.kind == "asset" {
                    let held = obj.instances
                    baseInstances = held
                    if let forced = forced {
                        centre = [forced[0], forced[1], forced.count > 2 ? forced[2] : 0.0]
                    } else if held.isEmpty {
                        centre = [0.0, 0.0, 0.0]
                    } else {
                        centre = try self.boundsCentre(held, 0, held.count)
                    }
                    return
                }
                let points = try self.pointsOf(obj)
                base = points
                if let forced = forced {
                    centre = [forced[0], forced[1], forced.count > 2 ? forced[2] : 0.0]
                } else {
                    centre = self.boundsOfPoints(points)
                }
            },
            render: { [unowned self] k in
                let scale = Verbs.smooth(Double(k + 1) / Double(Swift.max(frames, 1)))
                if let held = baseInstances {
                    var grow = [Double](repeating: 0, count: 12)
                    grow[0] = scale; grow[5] = scale; grow[10] = scale
                    grow[3] = (1 - scale) * centre[0]
                    grow[7] = (1 - scale) * centre[1]
                    grow[11] = (1 - scale) * centre[2]
                    obj.instances = held.map { Inst($0.atlasId, compose(grow, $0.transform), $0.fill, $0.stroke, $0.width) }
                    self.emit()
                    return
                }
                let points = base!
                var out = points
                var i = 0
                while i < out.count {
                    out[i] = centre[0] + (points[i] - centre[0]) * scale
                    out[i + 1] = centre[1] + (points[i + 1] - centre[1]) * scale
                    out[i + 2] = centre[2] + (points[i + 2] - centre[2]) * scale
                    i += 3
                }
                obj.points = out
                self.emit()
            },
            exit: {
                if let held = baseInstances { obj.instances = held }
                if let points = base { obj.points = points }
            }
        )
    }

    private func strokeRunner(_ step: Step.Stroke) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var startRgb = [0, 0, 0]
        var startWidth = 0.0
        var startAlpha = 1.0
        var base: [Inst]? = nil
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                if obj.kind == "shape" {
                    startRgb = [(obj.strokeRgb >> 16) & 0xFF, (obj.strokeRgb >> 8) & 0xFF, obj.strokeRgb & 0xFF]
                    startWidth = obj.width
                    startAlpha = obj.alpha
                } else {
                    base = obj.instances
                }
            },
            render: { [unowned self] k in
                let alpha = Verbs.smooth(Double(k + 1) / Double(frames))
                if obj.kind == "shape" {
                    let end = step.color
                    var rgb = [0, 0, 0]
                    for i in 0..<3 {
                        let target = end == nil ? startRgb[i] : (end! >> (16 - 8 * i)) & 0xFF
                        rgb[i] = pyRound(Double(startRgb[i]) + Double(target - startRgb[i]) * alpha)
                    }
                    obj.strokeRgb = Int(i32((rgb[0] << 16) | (rgb[1] << 8) | rgb[2]))
                    let width = step.width ?? startWidth
                    obj.width = startWidth + (width - startWidth) * alpha
                    let opacity = step.opacity ?? startAlpha
                    obj.alpha = startAlpha + (opacity - startAlpha) * alpha
                } else {
                    // The stroke only: a fill running beside it in the same par (set_color is both) changes the fill of
                    // the same instances, and writing them back from this runner's own start undid it.
                    let held = base!
                    let now = obj.instances.count == held.count ? obj.instances : held
                    obj.instances = held.indices.map { n in
                        let inst = held[n]
                        let current = now[n]
                        var rgb = [0, 0, 0]
                        for i in 0..<3 {
                            let target = step.color.map { ($0 >> (16 - 8 * i)) & 0xFF } ?? inst.stroke[i]
                            rgb[i] = pyRound(Double(inst.stroke[i]) + Double(target - inst.stroke[i]) * alpha)
                        }
                        let channel = step.opacity == nil ? inst.stroke[3]
                            : pyRound(Double(inst.stroke[3]) + (step.opacity! * 255 - Double(inst.stroke[3])) * alpha)
                        let width = step.width == nil ? inst.width : inst.width + (step.width! - inst.width) * alpha
                        return Inst(current.atlasId, current.transform, current.fill, [rgb[0], rgb[1], rgb[2], channel], width)
                    }
                }
                self.emit()
            },
            exit: {}
        )
    }

    /** A baked clip: frame k of the verb shows the clip's frame at the same moment (dsl/interpret.py does the same). */
    private func runRunner(_ step: Step.Run) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var clip: Scene! = nil
        var offset = 0
        unowned let me = self

        func put(_ j: Int) throws {
            let drawn = try clip.frame(j)
            obj.instances = drawn.map { inst in
                Inst(
                    inst.atlasId + offset,
                    inst.transform.map { Double($0) },
                    me.rgbaOf(inst.fill), me.rgbaOf(inst.stroke), Double(inst.strokeWidth)
                )
            }
            obj.flags = [Int](repeating: 0, count: drawn.count)
            obj.normals = [[Double]?](repeating: nil, count: drawn.count)
            obj.glyphIds = drawn.map { $0.atlasId }
        }

        /** Program frame k of the run in the clip: round the period from its phase, or spread over the run. */
        func at(_ k: Int) throws -> Int {
            let count = clip.frameCount
            if let loop = me.program.clipLoops[step.name] {
                guard count != 0 else { throw PanimError.illegalArgument("/ by zero") }
                return floorMod(loop + k, count)
            }
            guard frames != 0 else { throw PanimError.illegalArgument("/ by zero") }
            try require(count - 1 >= 0,
                        "Cannot coerce value to an empty range: maximum \(count - 1) is less than minimum 0.")
            return coerceIn(((k + 1) * count + frames - 1) / frames - 1, 0, count - 1)
        }

        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                obj.visible = true
                guard let found = self.clips[step.name] else {
                    throw PanimError.noSuchElement("Key \(step.name) is missing in the map.")
                }
                clip = found.0
                offset = found.1
            },
            render: { [unowned self] k in
                try put(try at(k))
                self.emit()
            },
            exit: { [unowned self] in
                // Its last frame stays: the frame the run ended on (a loop's phase, if it had no frames).
                if clip.frameCount > 0 {
                    try put(self.program.clipLoops[step.name] != nil ? try at(Swift.max(frames - 1, 0)) : clip.frameCount - 1)
                }
            }
        )
    }

    /** Manim scales about the object's centre, then translates. */
    private func xformRunner(_ step: Step.Xform) -> Runner {
        let frames = self.frames(step.seconds)
        let rate = Verbs.rate(step.rate)
        var obj: Obj! = nil
        var base: [Double] = []
        var centre: [Double] = []
        var isShape = false
        var basePoints: [Double]? = nil
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                // A primitive carries its geometry directly rather than as
                // instances under an object transform, so the matrix has to be
                // applied to its points. `.animate.scale(...).shift(...)` on a
                // Circle is ordinary Manim; this used to assume an asset.
                isShape = obj.kind == "shape"
                if isShape {
                    let points = try self.pointsOf(obj)
                    basePoints = points
                    centre = self.boundsOfPoints(points)
                    base = identity()
                } else {
                    base = obj.xform
                    centre = obj.centre
                }
            },
            render: { [unowned self] k in
                // there_and_back ends where it began: a part shown moving, then back in its place.
                let alpha = rate(Double(k + 1) / Double(frames))
                let scale = 1.0 + (step.factor - 1.0) * alpha
                var m = [Double](repeating: 0, count: 12)
                m[0] = scale; m[5] = scale; m[10] = scale
                m[3] = (1 - scale) * centre[0] + step.offsetXy[0] * alpha
                m[7] = (1 - scale) * centre[1] + step.offsetXy[1] * alpha
                m[11] = (1 - scale) * centre[2]

                if isShape, let points = basePoints {
                    var out = [Double](repeating: 0, count: points.count)
                    var i = 0
                    while i < points.count {
                        out[i] = m[0] * points[i] + m[1] * points[i + 1] + m[2] * points[i + 2] + m[3]
                        out[i + 1] = m[4] * points[i] + m[5] * points[i + 1] + m[6] * points[i + 2] + m[7]
                        out[i + 2] = m[8] * points[i] + m[9] * points[i + 1] + m[10] * points[i + 2] + m[11]
                        i += 3
                    }
                    obj.points = out
                } else {
                    obj.xform = compose(m, base)
                }
                self.emit()
            },
            exit: {}
        )
    }

    /**
     * Manim lags each submobject. Write uses lag_ratio min(4/n, 0.2); Create on
     * a group uses 1.0, i.e. strictly one child at a time.
     */
    private func revealRunner(_ name: String, _ seconds: Double, sequential: Bool, sequenceLag: Double = 1.0) -> Runner {
        let frames = self.frames(seconds)
        var obj: Obj! = nil
        var base: [Inst] = []
        var lag = 0.0
        var window = 0.0
        /**
         * The atlas slots this reveal draws its partial paths into, reused every frame. Partial paths are per
         * frame and never outlive it, so the atlas does not grow for the whole reveal. It used to be wound back
         * to where the reveal began instead -- and when two reveals ran at once (a lag of writes, a diagram's
         * drawings written in turn) each one's wind-back deleted the paths the other had just drawn, so the
         * phone drew the wrong outline for one of them.
         */
        var slots: [Int] = []
        var used = 0
        unowned let me = self

        /** A partial path into this reveal's next slot: its atlas id. */
        func scratch(_ points: [Double]) -> Int {
            if used < slots.count {
                me.setShape(slots[used], points)
            } else {
                me.addShape(points)
                slots.append(me.shapes.count - 1)
            }
            let id = slots[used]
            used += 1
            return id
        }

        /**
         * One child of a Write, at [local] along its own clock.
         *
         * Manim's Write is DrawBorderThenFill on a linear clock, and the two
         * phases are what the name says. The first half draws the child's
         * *outline* -- a copy with the fill switched off and a width-2 stroke
         * in the child's own colour -- as a partial path, twice as fast as the
         * clock. The second half puts the whole outline down and interpolates
         * it into the finished child, so the fill fades in as the outline
         * stroke thins away.
         *
         * Modelling it as one eased partial reveal, which is what Create does,
         * put the pen a long way behind Manim's: at the start of the sample
         * scene, where a few strokes are all there is to disagree about, Manim
         * had 36% of a glyph down where we had 3%.
         */
        func drawBorderThenFill(_ inst: Inst, _ local: Double) -> Inst {
            // Manim's get_stroke_color: the stroke colour where there is a
            // stroke, the mobject's own colour otherwise. Text carries no
            // stroke, so its outline is drawn in the fill colour.
            let source = inst.width > 0.0 ? inst.stroke : inst.fill
            let outline = [source[0], source[1], source[2], 255]

            if local < 0.5 {
                let partial = Verbs.pointwiseBecomePartial(me.shapes[inst.atlasId], 0.0, 2.0 * local)
                return Inst(
                    scratch(partial),
                    inst.transform,
                    [inst.fill[0], inst.fill[1], inst.fill[2], 0],
                    outline,
                    OUTLINE_STROKE_WIDTH
                )
            }

            // integerInterpolate(0, 2, local) lands in the upper half: the
            // shape is whole and only the style is still moving.
            let t = 2.0 * local - 1.0
            // floor(x + 0.5), not Math.round: Python rounds halves to even
            // and Java rounds them up, and the two interpreters have to agree
            // on every byte. Every value here is a non-negative channel.
            let stroke = (0..<4).map { kToInt(Double(outline[$0]) + Double(inst.stroke[$0] - outline[$0]) * t + 0.5) }
            return Inst(
                inst.atlasId,
                inst.transform,
                [inst.fill[0], inst.fill[1], inst.fill[2], kToInt(Double(inst.fill[3]) * t + 0.5)],
                stroke,
                OUTLINE_STROKE_WIDTH + (inst.width - OUTLINE_STROKE_WIDTH) * t
            )
        }

        return Runner(
            frames: frames,
            enter: { [unowned self] in
                guard let found = self.objects[name] else {
                    throw PanimError.illegalState("reveal target '\(name)' was never declared")
                }
                obj = found
                // Revealing a thing puts it on stage. Without this the object
                // stayed hidden for the whole reveal and appeared only at its
                // trailing show.
                obj.visible = true
                base = obj.instances
                let count = Swift.max(base.count, 1)
                lag = sequential ? sequenceLag : Swift.min(4.0 / Double(count), 0.2)
                window = 1.0 / (1.0 + lag * Double(count - 1))
                slots.removeAll()
            },
            render: { [unowned self] k in
                used = 0
                let alpha = Double(k + 1) / Double(frames)
                var revealed: [Inst] = []
                revealed.reserveCapacity(base.count)
                for (index, inst) in base.enumerated() {
                    let start = Double(index) * lag * window
                    let local = coerceIn((alpha - start) / window, 0.0, 1.0)
                    if local <= 0.0 { continue }
                    if local >= 1.0 {
                        revealed.append(inst)
                        continue
                    }
                    if sequential {
                        // Create on a group: a plain partial reveal, eased.
                        let partial = Verbs.pointwiseBecomePartial(self.shapes[inst.atlasId], 0.0, Verbs.smooth(local))
                        revealed.append(Inst(scratch(partial), inst.transform, inst.fill, inst.stroke, inst.width))
                    } else {
                        revealed.append(drawBorderThenFill(inst, local))
                    }
                }
                obj.instances = revealed
                self.emit()
            },
            exit: { [unowned self] in
                // The slots go back only when they are the atlas's last entries (nothing after them still in use).
                if let top = slots.max(), top == self.shapes.count - 1, slots.count == Set(slots).count,
                   slots.min() == self.shapes.count - slots.count {
                    self.truncateShapes(slots.min()!)
                }
                slots.removeAll()
                obj.instances = base
            }
        )
    }

    /**
     * Manim's LaggedStart(*[GrowFromCenter(child) ...], lag_ratio=r).
     *
     * GrowFromCenter interpolates from a zero-size copy at the child's centre,
     * which point by point is c + alpha*(p - c) -- a uniform scale about c,
     * composable onto whatever transform the instance already carries, so
     * nothing extra is shipped. The run lengths do have to be: a baked group is
     * a flat instance list with no notion of which faces are which sphere.
     */
    private func laggedGrowRunner(_ step: Step.LaggedGrow) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var base: [Inst] = []
        var flags: [Int]? = nil
        var normals: [[Double]?]? = nil
        var spans: [[Int]] = []
        var centres: [[Double]] = []
        var window = 0.0
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                obj.visible = true
                base = obj.instances
                flags = obj.flags
                normals = obj.normals

                var built: [[Int]] = []
                var cursor = 0
                for size in step.groups {
                    built.append([cursor, cursor + size])
                    cursor += size
                }
                try require(cursor == base.count,
                            "laggedgrow \(step.name): groups cover \(cursor) instances, asset has \(base.count)")
                spans = built

                if let forced = step.at {
                    let point = [forced[0], forced[1], forced.count > 2 ? forced[2] : 0.0]
                    centres = spans.map { _ in point }
                } else {
                    centres = try spans.map { span in try self.boundsCentre(base, span[0], span[1]) }
                }
                window = 1.0 / (1.0 + step.lag * Double(Swift.max(spans.count, 1) - 1))
            },
            render: { [unowned self] k in
                let alpha = Double(k + 1) / Double(frames)
                var grown: [Inst] = []
                var kept: [Int] = []
                for (groupIndex, span) in spans.enumerated() {
                    let start = Double(groupIndex) * step.lag * window
                    let local = coerceIn((alpha - start) / window, 0.0, 1.0)
                    if local <= 0.0 { continue }
                    let scale = Verbs.smooth(local)
                    let centre = centres[groupIndex]
                    var grow = [Double](repeating: 0, count: 12)
                    grow[0] = scale; grow[5] = scale; grow[10] = scale
                    grow[3] = (1 - scale) * centre[0]
                    grow[7] = (1 - scale) * centre[1]
                    grow[11] = (1 - scale) * centre[2]
                    if span[0] < span[1] {
                        for index in span[0]..<span[1] {
                            let inst = base[index]
                            grown.append(Inst(inst.atlasId, compose(grow, inst.transform), inst.fill, inst.stroke, inst.width))
                            kept.append(index)
                        }
                    }
                }
                // Flags and normals are indexed by position, so dropping the
                // not-yet-grown children would shade each sphere with another's.
                obj.instances = grown
                if let f = flags { obj.flags = try kept.map { try element(f, $0) } }
                if let n = normals { obj.normals = try kept.map { try element(n, $0) } }
                self.emit()
            },
            exit: {
                obj.instances = base
                obj.flags = flags
                obj.normals = normals
            }
        )
    }

    private func fadeRunner(
        _ name: String, _ seconds: Double, fadingIn: Bool, _ shift: [Double], _ from: Double, _ rateName: String = "smooth"
    ) -> Runner {
        let rate = Verbs.rate(rateName)
        let frames = self.frames(seconds)
        var obj: Obj! = nil
        var base: [Inst]? = nil
        var rest: [Double]? = nil
        var centre = [0.0, 0.0, 0.0]
        var baseXform = identity()
        var moves = false
        // Manim's _Fade starts FadeIn from a copy shifted by -shift and ends
        // FadeOut at +shift. FadeIn used to travel +shift here, so things rose
        // into place from above instead of from below.
        let sign = fadingIn ? -1.0 : 1.0
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                self.objects[name]?.visible = true
                // A declared shape only enters the scene when something animates it
                // in; fade is one of those entry points, not just create.
                // A fade out of a declared shape never put on stage (a stage card faded with a group the exporter
                // took apart) starts from nothing, as dsl/interpret.py does, instead of stopping the lecture.
                if !self.objects.contains(name) && self.program.shapes.contains(name) {
                    self.objects[name] = try self.newShape(name, alpha: 0.0)
                }
                obj = try self.objects.getValue(name)
                base = obj.kind == "asset" ? obj.instances : nil
                moves = shift[0] != 0.0 || shift[1] != 0.0 || from != 1.0
                if obj.kind == "shape" {
                    rest = try self.pointsOf(obj)
                    centre = self.boundsOfPoints(rest!)
                } else {
                    baseXform = obj.xform
                    if moves {
                        let world = base!.map { Inst($0.atlasId, compose(baseXform, $0.transform), $0.fill, $0.stroke, $0.width) }
                        centre = try self.boundsCentre(world, 0, world.count)
                    }
                }
            },
            render: { [unowned self] k in
                // An easing that overshoots (ease_out_back) carries the size and the travel past the end and back, as
                // Manim's does; the opacity stops at full.
                let progress = rate(Double(k + 1) / Double(frames))
                let shown = fadingIn ? progress : 1.0 - progress
                let alpha = coerceIn(shown, 0.0, 1.0)
                let scale = from + (1.0 - from) * shown
                let travel = sign * (1.0 - shown)
                if let held = base {
                    if moves {
                        var m = [Double](repeating: 0, count: 12)
                        m[0] = scale; m[5] = scale; m[10] = scale
                        m[3] = (1 - scale) * centre[0] + shift[0] * travel
                        m[7] = (1 - scale) * centre[1] + shift[1] * travel
                        m[11] = (1 - scale) * centre[2]
                        obj.xform = compose(m, baseXform)
                    }
                    obj.instances = held.map { inst in
                        Inst(
                            inst.atlasId, inst.transform,
                            [inst.fill[0], inst.fill[1], inst.fill[2], kToInt(Double(inst.fill[3]) * alpha)],
                            [inst.stroke[0], inst.stroke[1], inst.stroke[2], kToInt(Double(inst.stroke[3]) * alpha)],
                            inst.width
                        )
                    }
                } else {
                    obj.alpha = alpha
                    if let points = rest {
                        var out = points
                        var i = 0
                        while i < out.count {
                            out[i] = centre[0] + (points[i] - centre[0]) * scale + shift[0] * travel
                            out[i + 1] = centre[1] + (points[i + 1] - centre[1]) * scale + shift[1] * travel
                            out[i + 2] = centre[2] + (points[i + 2] - centre[2]) * scale
                            i += 3
                        }
                        obj.points = out
                    }
                }
                self.emit()
            },
            exit: { [unowned self] in
                if let held = base {
                    obj.xform = baseXform
                    // Faded out, an asset keeps its parts, hidden, as dsl/interpret.py does: faded in again (a veil
                    // that comes and goes), it shows them; emptied, it came back as nothing.
                    obj.instances = held
                    if !fadingIn { obj.visible = false }
                } else {
                    if fadingIn {
                        obj.alpha = 1.0
                        if let points = rest { obj.points = points }
                    } else {
                        self.objects.remove(name)
                    }
                }
            }
        )
    }

    /**
     * `.animate.set_fill`. set_fill reaches the whole family, members with no
     * fill included, so every instance moves to the given colour and opacity.
     */
    private func fillRunner(_ step: Step.Fill) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var base: [Inst]? = nil
        var start = [0, 0, 0, 0]
        var end = [0.0, 0.0, 0.0, 0.0]
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                if obj.kind == "shape" {
                    start = obj.fill
                    end = start.map { Double($0) }
                    if let c = step.color { for i in 0..<3 { end[i] = Double((c >> (16 - 8 * i)) & 0xFF) } }
                    if let opacity = step.opacity { end[3] = opacity * 255 }
                } else {
                    base = obj.instances
                }
            },
            render: { [unowned self] k in
                let alpha = Verbs.smooth(Double(k + 1) / Double(Swift.max(frames, 1)))
                if let held = base {
                    // The fill only: a stroke beside it in the same par changes the same instances' strokes.
                    let now = obj.instances.count == held.count ? obj.instances : held
                    obj.instances = held.indices.map { n in
                        let inst = held[n]
                        let current = now[n]
                        var rgb = [0, 0, 0]
                        for i in 0..<3 {
                            if let color = step.color {
                                let target = (color >> (16 - 8 * i)) & 0xFF
                                rgb[i] = kToInt(Double(inst.fill[i]) + Double(target - inst.fill[i]) * alpha + 0.5)
                            } else {
                                rgb[i] = inst.fill[i]
                            }
                        }
                        let channel = step.opacity == nil ? inst.fill[3]
                            : kToInt(Double(inst.fill[3]) + (step.opacity! * 255 - Double(inst.fill[3])) * alpha + 0.5)
                        return Inst(current.atlasId, current.transform, [rgb[0], rgb[1], rgb[2], channel], current.stroke,
                                    current.width)
                    }
                } else {
                    obj.fill = (0..<4).map { kToInt(Double(start[$0]) + (end[$0] - Double(start[$0])) * alpha + 0.5) }
                }
                self.emit()
            },
            exit: {}
        )
    }

    /**
     * Glyph-level matching. Instances sharing a library glyph id pair up in
     * order; anything left over on either side fades rather than morphing into
     * an unrelated shape -- the correspondence TransformMatchingTex computes
     * from TeX structure, recovered here from the shared atlas.
     */
    private func morphRunner(_ step: Step.Morph) -> Runner {
        let frames = self.frames(step.seconds)
        var src: Obj! = nil
        var dst: Obj! = nil
        var pairs: [(Int, Int)] = []
        var orphans: [Int] = []
        var arrivals: [Int] = []
        var srcBase: [Inst] = []
        var dstBase: [Inst] = []
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                src = try self.need(step.source)
                dst = try self.need(step.target)
                src.visible = true
                dst.visible = false

                guard let dstGlyphs = dst.glyphIds, let srcGlyphs = src.glyphIds else {
                    throw PanimError.nullPointer("morph between objects without glyphs")
                }
                // LinkedHashMap<glyph, queue>: insertion order is the order arrivals are listed in.
                var pendingOrder: [Int] = []
                var pending: [Int: [Int]] = [:]
                var heads: [Int: Int] = [:]
                for (index, glyph) in dstGlyphs.enumerated() {
                    if pending[glyph] == nil {
                        pending[glyph] = []
                        heads[glyph] = 0
                        pendingOrder.append(glyph)
                    }
                    pending[glyph]!.append(index)
                }
                var matched: [(Int, Int)] = []
                var unmatched: [Int] = []
                for (index, glyph) in srcGlyphs.enumerated() {
                    if let queue = pending[glyph], let head = heads[glyph], head < queue.count {
                        matched.append((index, queue[head]))
                        heads[glyph] = head + 1
                    } else {
                        unmatched.append(index)
                    }
                }
                pairs = matched
                orphans = unmatched
                arrivals = pendingOrder.flatMap { glyph in Array(pending[glyph]![heads[glyph]!...]) }
                srcBase = src.instances
                dstBase = dst.instances
            },
            render: { [unowned self] k in
                let alpha = Verbs.smooth(Double(k + 1) / Double(frames))
                let fadeOut = 1.0 - alpha
                var built: [Inst] = []
                for pair in pairs {
                    let a = srcBase[pair.0]
                    let b = dstBase[pair.1]
                    built.append(Inst(
                        a.atlasId,
                        (0..<12).map { a.transform[$0] + (b.transform[$0] - a.transform[$0]) * alpha },
                        (0..<4).map { pyRound(Double(a.fill[$0]) + Double(b.fill[$0] - a.fill[$0]) * alpha) },
                        (0..<4).map { pyRound(Double(a.stroke[$0]) + Double(b.stroke[$0] - a.stroke[$0]) * alpha) },
                        a.width + (b.width - a.width) * alpha
                    ))
                }
                for index in orphans {
                    let a = srcBase[index]
                    built.append(Inst(
                        a.atlasId, a.transform,
                        [a.fill[0], a.fill[1], a.fill[2], kToInt(Double(a.fill[3]) * fadeOut)],
                        [a.stroke[0], a.stroke[1], a.stroke[2], kToInt(Double(a.stroke[3]) * fadeOut)],
                        a.width
                    ))
                }
                for index in arrivals {
                    let b = dstBase[index]
                    built.append(Inst(
                        b.atlasId, b.transform,
                        [b.fill[0], b.fill[1], b.fill[2], kToInt(Double(b.fill[3]) * alpha)],
                        [b.stroke[0], b.stroke[1], b.stroke[2], kToInt(Double(b.stroke[3]) * alpha)],
                        b.width
                    ))
                }
                src.instances = built
                self.emit()
            },
            exit: {
                src.instances = dstBase
                guard let glyphs = dst.glyphIds else { throw PanimError.nullPointer("morph target without glyphs") }
                src.glyphIds = glyphs

                // Manim's TransformMatchingTex leaves the *target* on stage and
                // takes the source off it. The blend is carried by the source
                // object, so without this the source stayed visible holding the
                // target's content while the target's own trailing `show` drew the
                // same thing again -- harmless for one morph, and cumulative for a
                // chain of them. Three morphs left three stale equations
                // superimposed on the fourth.
                // A moved source (Transform, .animate: keep) is still the thing on
                // stage, which a later fadeout or hide takes away.
                src.visible = step.keep
                dst.visible = !step.keep
            }
        )
    }

    private func moveRunner(_ step: Step.Move) -> Runner {
        let frames = self.frames(step.seconds)
        var startPhi = 0.0
        var startTheta = 0.0
        var startZoom = 1.0
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                startPhi = self.phi
                startTheta = self.theta
                startZoom = self.zoom
            },
            render: { [unowned self] k in
                let alpha = Verbs.smooth(Double(k + 1) / Double(frames))
                if let it = step.phi { self.phi = startPhi + (it - startPhi) * alpha }
                if let it = step.theta { self.theta = startTheta + (it - startTheta) * alpha }
                if let it = step.zoom { self.zoom = startZoom + (it - startZoom) * alpha }
                self.emit()
            },
            exit: {}
        )
    }

    /**
     * Manim's ambient rotation advances once per frame except on the wait's
     * last frame, which repeats the previous orientation. Measured on two
     * scenes. Without it the trailing hold sits 0.57 deg out for a whole
     * second -- where the fidelity harness never looks.
     *
     * Resumable form: theta at frame k is a closed form off the verb's start,
     * so a seek inside a spin does not have to replay it.
     */
    private func spinRunner(_ step: Step.Spin) -> Runner {
        let frames = self.frames(step.seconds)
        let fps = self.fps
        var startTheta = 0.0
        var startPhi = 0.0
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                startTheta = self.theta
                startPhi = self.phi
            },
            render: { [unowned self] k in
                let advances = Swift.min(k + 1, Swift.max(frames - 1, 0))
                let turned = Double(advances) * step.rate / Double(fps)
                if step.about == "phi" { self.phi = startPhi + turned } else { self.theta = startTheta + turned }
                self.emit()
            },
            exit: { [unowned self] in
                let turned = Double(Swift.max(frames - 1, 0)) * step.rate / Double(fps)
                if step.about == "phi" { self.phi = startPhi + turned } else { self.theta = startTheta + turned }
            }
        )
    }

    private func boundsOfPoints(_ points: [Double]) -> [Double] {
        var minX = points[0], minY = points[1], minZ = points[2]
        var maxX = minX, maxY = minY, maxZ = minZ
        var i = 3
        while i < points.count {
            if points[i] < minX { minX = points[i] }
            if points[i] > maxX { maxX = points[i] }
            if points[i + 1] < minY { minY = points[i + 1] }
            if points[i + 1] > maxY { maxY = points[i + 1] }
            if points[i + 2] < minZ { minZ = points[i + 2] }
            if points[i + 2] > maxZ { maxZ = points[i + 2] }
            i += 3
        }
        return [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2]
    }

    private func rotateRunner(_ step: Step.Rotate) -> Runner {
        let frames = self.frames(step.seconds)
        let rate = Verbs.rate(step.rate)
        var obj: Obj! = nil
        var basePoints: [Double]? = nil
        var baseInst: [Inst]? = nil
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                if obj.kind == "shape" { basePoints = try self.pointsOf(obj) } else { baseInst = obj.instances }
            },
            render: { [unowned self] k in
                let ang = step.radians * rate(Double(k + 1) / Double(frames))
                let c = cos(ang)
                let s = sin(ang)
                let ox = step.at[0]
                let oy = step.at.count > 1 ? step.at[1] : 0.0
                if let points = basePoints {
                    var out = points
                    var i = 0
                    while i < out.count {
                        let x = points[i] - ox
                        let y = points[i + 1] - oy
                        out[i] = c * x - s * y + ox
                        out[i + 1] = s * x + c * y + oy
                        i += 3
                    }
                    obj.points = out
                } else {
                    let rot = [
                        c, -s, 0.0, ox * (1 - c) + oy * s,
                        s, c, 0.0, oy * (1 - c) - ox * s,
                        0.0, 0.0, 1.0, 0.0,
                    ]
                    obj.instances = baseInst!.map { Inst($0.atlasId, compose(rot, $0.transform), $0.fill, $0.stroke, $0.width) }
                }
                self.emit()
            },
            // It stays turned, as Manim leaves a Rotate's object: put back at its start, a ray turned to graze the
            // surface sprang back the moment the turn ended.
            exit: {}
        )
    }

    private func indicateRunner(_ step: Step.Indicate) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var basePoints: [Double]? = nil
        var baseInst: [Inst]? = nil
        var centre = [0.0, 0.0, 0.0]
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                if obj.kind == "shape" {
                    basePoints = try self.pointsOf(obj)
                    centre = self.boundsOfPoints(basePoints!)
                } else {
                    baseInst = obj.instances
                    centre = try self.boundsCentre(baseInst!, 0, baseInst!.count)
                }
            },
            render: { [unowned self] k in
                let pulse = Verbs.thereAndBack(Double(k + 1) / Double(frames))
                let scale = 1.0 + 0.2 * pulse
                if let points = basePoints {
                    var out = points
                    var i = 0
                    while i < out.count {
                        out[i] = centre[0] + (points[i] - centre[0]) * scale
                        out[i + 1] = centre[1] + (points[i + 1] - centre[1]) * scale
                        out[i + 2] = centre[2] + (points[i + 2] - centre[2]) * scale
                        i += 3
                    }
                    obj.points = out
                } else {
                    let grow = [
                        scale, 0.0, 0.0, (1 - scale) * centre[0],
                        0.0, scale, 0.0, (1 - scale) * centre[1],
                        0.0, 0.0, scale, (1 - scale) * centre[2],
                    ]
                    obj.instances = baseInst!.map { Inst($0.atlasId, compose(grow, $0.transform), $0.fill, $0.stroke, $0.width) }
                }
                self.emit()
            },
            exit: {
                if let points = basePoints { obj.points = points }
                if let held = baseInst { obj.instances = held }
            }
        )
    }

    private func unwriteRunner(_ step: Step.Unwrite) -> Runner {
        let frames = self.frames(step.seconds)
        var obj: Obj! = nil
        var base: [Inst] = []
        return Runner(
            frames: frames,
            enter: { [unowned self] in
                obj = try self.need(step.name)
                obj.visible = true
                base = obj.instances
            },
            render: { [unowned self] k in
                let count = Swift.max(base.count, 1)
                let lag = Swift.min(4.0 / Double(count), 0.2)
                let span = 1.0 / (1.0 + lag * Double(count - 1))
                let alpha = 1.0 - Double(k + 1) / Double(frames)
                var revealed: [Inst] = []
                for (i, inst) in base.enumerated() {
                    let start = Double(i) * lag * span
                    let local = coerceIn((alpha - start) / span, 0.0, 1.0)
                    if local > 0.0 { revealed.append(inst) }
                }
                obj.instances = revealed
                self.emit()
            },
            exit: {
                obj.instances = []
                obj.visible = false
            }
        )
    }

    private func boundsCentre(_ instances: [Inst], _ from: Int, _ until: Int) throws -> [Double] {
        var minX = Double.greatestFiniteMagnitude, minY = Double.greatestFiniteMagnitude
        var minZ = Double.greatestFiniteMagnitude
        var maxX = -Double.greatestFiniteMagnitude, maxY = -Double.greatestFiniteMagnitude
        var maxZ = -Double.greatestFiniteMagnitude
        if from < until {
            for index in from..<until {
                let inst = try element(instances, index)
                let pts = shapes[inst.atlasId]
                let m = inst.transform
                var i = 0
                while i < pts.count {
                    let x = m[0] * pts[i] + m[1] * pts[i + 1] + m[2] * pts[i + 2] + m[3]
                    let y = m[4] * pts[i] + m[5] * pts[i + 1] + m[6] * pts[i + 2] + m[7]
                    let z = m[8] * pts[i] + m[9] * pts[i + 1] + m[10] * pts[i + 2] + m[11]
                    if x < minX { minX = x }; if x > maxX { maxX = x }
                    if y < minY { minY = y }; if y > maxY { maxY = y }
                    if z < minZ { minZ = z }; if z > maxZ { maxZ = z }
                    i += 3
                }
            }
        }
        return [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2]
    }
}

/** Kotlin's `maxOf` on Doubles (Math.max): NaN wins, and 0.0 is above -0.0. */
@inline(__always)
func kMax(_ a: Double, _ b: Double) -> Double {
    if a.isNaN || b.isNaN { return Double.nan }
    if a == 0 && b == 0 { return a.sign == .minus ? b : a }
    return a > b ? a : b
}
