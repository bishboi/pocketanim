// Ported from player/core/src/main/kotlin/com/pocketanim/core/dsl/Program.kt.
import Foundation

/**
 * The tier-1 artefact: a program, not its samples.
 *
 * A few hundred bytes of text that the device expands into frames. This parses
 * it. The grammar is line-based and whitespace-tokenised -- `verb positional...
 * key=value...` -- which is why the exporter strips spaces out of emitted
 * expressions.
 */

public final class ShapeSpec {
    public let kind: String
    public let size: Double
    public let extent: [Double]?
    public let stroke: Int       // 0xRRGGBB
    public let width: Double
    public let at: [Double]

    public init(kind: String, size: Double, extent: [Double]?, stroke: Int, width: Double, at: [Double]) {
        self.kind = kind
        self.size = size
        self.extent = extent
        self.stroke = stroke
        self.width = width
        self.at = at
    }
}

public final class SurfaceSpec {
    public let name: String
    public let fn: Expr
    public let uRange: [Double]
    public let vRange: [Double]
    public let resolution: [Int]
    public let colors: [Int]
    public let alpha: Double
    public let stroke: Double

    public init(
        name: String, fn: Expr, uRange: [Double], vRange: [Double], resolution: [Int], colors: [Int], alpha: Double,
        stroke: Double
    ) {
        self.name = name
        self.fn = fn
        self.uRange = uRange
        self.vRange = vRange
        self.resolution = resolution
        self.colors = colors
        self.alpha = alpha
        self.stroke = stroke
    }
}

/**
 * A raster picture (`image NAME src=FILE px=W,H keys=... z=Z`): the PNG [src] beside the program (the library's
 * images/ folder), [keys] where it is and how visible through the program's frames, eight numbers a key --
 * frame, alpha, then the upper-left, upper-right and lower-left corners in scene units; [drift], how it drifts.
 */
public final class ImageSpec {
    public let name: String
    public let src: String
    public let width: Int
    public let height: Int
    public let z: Double
    public let keys: [Double]
    /** A picture that drifts slowly while it shows (`drift=...`), its labels with it. */
    public let drift: Drift?

    public init(name: String, src: String, width: Int, height: Int, z: Double, keys: [Double], drift: Drift? = nil) {
        self.name = name
        self.src = src
        self.width = width
        self.height = height
        self.z = z
        self.keys = keys
        self.drift = drift
    }

    public var keyCount: Int { keys.count / ImageSpec.KEY }

    /**
     * Where the picture is at [frame], into [corners] (ulx, uly, urx, ury, dlx, dly); returns its alpha, 0 while it
     * is not showing. Before the first key nothing, between two keys a straight line, after the last key held --
     * the rule exporter/reference_render.py and the browser preview apply.
     */
    public func at(_ frame: Double, _ corners: inout [Float]) -> Float {
        var before = -1
        for k in 0..<keyCount {
            if keys[k * ImageSpec.KEY] <= frame { before = k } else { break }
        }
        if before < 0 { return 0 }
        let a = before * ImageSpec.KEY
        var alpha = keys[a + 1]
        let next = before + 1
        if next < keyCount && keys[next * ImageSpec.KEY] > keys[a] {
            let b = next * ImageSpec.KEY
            let t = coerceIn((frame - keys[a]) / (keys[b] - keys[a]), 0.0, 1.0)
            alpha += (keys[b + 1] - alpha) * t
            for i in 0..<6 { corners[i] = Float(keys[a + 2 + i] + (keys[b + 2 + i] - keys[a + 2 + i]) * t) }
        } else {
            for i in 0..<6 { corners[i] = Float(keys[a + 2 + i]) }
        }
        return alpha > 0.004 ? Float(alpha) : 0
    }

    public static let KEY = 8
}

/** The program's timeline, one verb a step. Kotlin's sealed class: each kind a subclass, told apart with `as?`. */
public class Step {
    fileprivate init() {}

    /** [lag] is Create's lag_ratio over an asset's children; nil means Manim's 1.0. */
    public final class Create: Step {
        public let name: String, seconds: Double, rate: String, removing: Bool, lag: Double?
        public init(_ name: String, _ seconds: Double, _ rate: String, removing: Bool = false, lag: Double? = nil) {
            self.name = name; self.seconds = seconds; self.rate = rate; self.removing = removing; self.lag = lag
            super.init()
        }
    }

    public final class Transform: Step {
        public let source: String, target: String, seconds: Double, rate: String, arc: Double
        public init(_ source: String, _ target: String, _ seconds: Double, _ rate: String, arc: Double = 0.0) {
            self.source = source; self.target = target; self.seconds = seconds; self.rate = rate; self.arc = arc
            super.init()
        }
    }

    /** [keep]: the source stays on stage with the target's shape (Transform, .animate); otherwise the target replaces it. */
    public final class Morph: Step {
        public let source: String, target: String, seconds: Double, keep: Bool
        public init(_ source: String, _ target: String, _ seconds: Double, keep: Bool = false) {
            self.source = source; self.target = target; self.seconds = seconds; self.keep = keep
            super.init()
        }
    }

    public final class Show: Step {
        public let name: String
        public init(_ name: String) { self.name = name; super.init() }
    }

    /** The other half of [Show]: what Manim's Scene.remove took off stage. */
    public final class Hide: Step {
        public let name: String
        public init(_ name: String) { self.name = name; super.init() }
    }

    public final class Fade: Step {
        public let name: String, seconds: Double, shift: [Double], from: Double, rate: String
        public init(_ name: String, _ seconds: Double, _ shift: [Double] = [0.0, 0.0], _ from: Double = 1.0,
                    _ rate: String = "smooth") {
            self.name = name; self.seconds = seconds; self.shift = shift; self.from = from; self.rate = rate
            super.init()
        }
    }

    public final class FadeOut: Step {
        public let name: String, seconds: Double, shift: [Double], from: Double, rate: String
        public init(_ name: String, _ seconds: Double, _ shift: [Double] = [0.0, 0.0], _ from: Double = 1.0,
                    _ rate: String = "smooth") {
            self.name = name; self.seconds = seconds; self.shift = shift; self.from = from; self.rate = rate
            super.init()
        }
    }

    public final class Write: Step {
        public let name: String, seconds: Double
        public init(_ name: String, _ seconds: Double) { self.name = name; self.seconds = seconds; super.init() }
    }

    /** Write run backwards, then the object leaves the stage. */
    public final class Unwrite: Step {
        public let name: String, seconds: Double
        public init(_ name: String, _ seconds: Double) { self.name = name; self.seconds = seconds; super.init() }
    }

    /** Rewritten from Create on an asset; Manim's Create lags a group's children. */
    public final class RevealSequence: Step {
        public let name: String, seconds: Double, lag: Double
        public init(_ name: String, _ seconds: Double, _ lag: Double = 1.0) {
            self.name = name; self.seconds = seconds; self.lag = lag
            super.init()
        }
    }

    /** `.animate.set_fill`. Nil fields are left as they are. */
    public final class Fill: Step {
        public let name: String, color: Int?, opacity: Double?, seconds: Double
        public init(_ name: String, _ color: Int?, _ opacity: Double?, _ seconds: Double) {
            self.name = name; self.color = color; self.opacity = opacity; self.seconds = seconds
            super.init()
        }
    }

    public final class Xform: Step {
        public let name: String, factor: Double, offsetXy: [Double], seconds: Double, rate: String
        public init(_ name: String, _ factor: Double, _ offsetXy: [Double], _ seconds: Double, _ rate: String = "smooth") {
            self.name = name; self.factor = factor; self.offsetXy = offsetXy; self.seconds = seconds; self.rate = rate
            super.init()
        }
    }

    /** `.animate.set_stroke`. Nil fields are left as they are. */
    public final class Stroke: Step {
        public let name: String, color: Int?, width: Double?, opacity: Double?, seconds: Double
        public init(_ name: String, _ color: Int?, _ width: Double?, _ opacity: Double?, _ seconds: Double) {
            self.name = name; self.color = color; self.width = width; self.opacity = opacity; self.seconds = seconds
            super.init()
        }
    }

    /** GrowFromCenter on a circle, square or rectangle. Assets use [LaggedGrow]. */
    public final class Grow: Step {
        public let name: String, seconds: Double, at: [Double]?
        public init(_ name: String, _ seconds: Double, _ at: [Double]? = nil) {
            self.name = name; self.seconds = seconds; self.at = at
            super.init()
        }
    }

    public final class LaggedGrow: Step {
        public let name: String, lag: Double, groups: [Int], seconds: Double, at: [Double]?
        public init(_ name: String, _ lag: Double, _ groups: [Int], _ seconds: Double, _ at: [Double]? = nil) {
            self.name = name; self.lag = lag; self.groups = groups; self.seconds = seconds; self.at = at
            super.init()
        }
    }

    /** A 2D rotation by [radians] about [at]. */
    public final class Rotate: Step {
        public let name: String, radians: Double, at: [Double], seconds: Double, rate: String
        public init(_ name: String, _ radians: Double, _ at: [Double], _ seconds: Double, _ rate: String) {
            self.name = name; self.radians = radians; self.at = at; self.seconds = seconds; self.rate = rate
            super.init()
        }
    }

    /** A there-and-back scale pulse to 1.2. */
    public final class Indicate: Step {
        public let name: String, seconds: Double
        public init(_ name: String, _ seconds: Double) { self.name = name; self.seconds = seconds; super.init() }
    }

    public final class Move: Step {
        public let phi: Double?, theta: Double?, seconds: Double, zoom: Double?
        public init(_ phi: Double?, _ theta: Double?, _ seconds: Double, _ zoom: Double? = nil) {
            self.phi = phi; self.theta = theta; self.seconds = seconds; self.zoom = zoom
            super.init()
        }
    }

    public final class Spin: Step {
        public let rate: Double, seconds: Double, about: String
        public init(_ rate: Double, _ seconds: Double, _ about: String = "theta") {
            self.rate = rate; self.seconds = seconds; self.about = about
            super.init()
        }
    }

    public final class Wait: Step {
        public let seconds: Double
        public init(_ seconds: Double) { self.seconds = seconds; super.init() }
    }

    /**
     * A baked clip played over [seconds]: motion the other verbs cannot say (updaters, a value tracker, a path,
     * any rate function), recorded by the exporter frame by frame into a small sampled asset (`clip` declaration).
     */
    public final class Run: Step {
        public let name: String, seconds: Double
        public init(_ name: String, _ seconds: Double) { self.name = name; self.seconds = seconds; super.init() }
    }

    /**
     * A marker, not a verb: the next [count] steps share one clock.
     *
     * Manim's `play(A(), B())` runs its animations together, and a timeline of
     * consecutive verbs cannot say that -- it played the scene for twice its
     * run_time and showed one thing after the other. The builder folds a run of
     * these into [Parallel] before anything is scheduled.
     */
    public final class Par: Step {
        public let count: Int, seconds: Double
        public init(_ count: Int, _ seconds: Double) { self.count = count; self.seconds = seconds; super.init() }
    }

    /**
     * A staggered group. [runs] is how many following steps belong to each
     * child. The builder folds this into [Lag] before scheduling.
     */
    public final class LagHeader: Step {
        public let runs: [Int], ratio: Double, seconds: Double
        public init(_ runs: [Int], _ ratio: Double, _ seconds: Double) {
            self.runs = runs; self.ratio = ratio; self.seconds = seconds
            super.init()
        }
    }

    /** Folded [LagHeader]. Children start one after another by [ratio]. */
    public final class Lag: Step {
        public let ratio: Double, seconds: Double, members: [Step]
        public init(_ ratio: Double, _ seconds: Double, _ members: [Step]) {
            self.ratio = ratio; self.seconds = seconds; self.members = members
            super.init()
        }
    }

    /** Several steps played in order, as one child of a [Lag]. */
    public final class Sequence: Step {
        public let members: [Step]
        public init(_ members: [Step]) { self.members = members; super.init() }
    }

    /** A folded [Par] group. Never parsed; only ever built. */
    public final class Parallel: Step {
        public let members: [Step]
        public init(_ members: [Step]) { self.members = members; super.init() }
    }
}

public final class Program {
    public let fps: Int
    public let mode: String
    public let phi: Double
    public let theta: Double
    /** Manim's camera zoom. 1.0 unless the scene set one. */
    public let zoom: Double
    public let shapes: OrderedMap<ShapeSpec>
    /** name -> (kind, assetId), kind being "text" or "geom", in declaration order. */
    public let assets: OrderedMap<(String, String)>
    public let surfaces: [SurfaceSpec]
    public let timeline: [Step]
    /** Declared draw order by name. Absent means 0. */
    public let z: [String: Double]
    /** The clear colour, ARGB, from `bg=` on the scene line. */
    public let background: Int32
    /** name -> assetId of each baked clip (`clip K asset=...`). */
    public let clips: OrderedMap<String>
    /** name -> phase of each looping clip (`loop=P`): it holds one period, played round from frame P. */
    public let clipLoops: [String: Int]
    /** The raster pictures, in declaration order. */
    public let images: [ImageSpec]
    /** name -> how a backdrop drifts (`drift NAME period= amp= scale= turn=`): moved every frame by [Drift.at]. */
    public let drifts: [String: Drift]

    public init(
        fps: Int, mode: String, phi: Double, theta: Double, zoom: Double, shapes: OrderedMap<ShapeSpec>,
        assets: OrderedMap<(String, String)>, surfaces: [SurfaceSpec], timeline: [Step], z: [String: Double] = [:],
        background: Int32 = Int32(bitPattern: 0xFF00_0000), clips: OrderedMap<String> = OrderedMap(),
        clipLoops: [String: Int] = [:], images: [ImageSpec] = [], drifts: [String: Drift] = [:]
    ) {
        self.fps = fps
        self.mode = mode
        self.phi = phi
        self.theta = theta
        self.zoom = zoom
        self.shapes = shapes
        self.assets = assets
        self.surfaces = surfaces
        self.timeline = timeline
        self.z = z
        self.background = background
        self.clips = clips
        self.clipLoops = clipLoops
        self.images = images
        self.drifts = drifts
    }

    public var is3d: Bool { mode == "3d" }

    /** Kotlin's `lineSequence()`: lines split at \r\n, \n or \r. */
    private static func lines(_ text: String) -> [String] {
        var out: [String] = []
        var current: [UInt16] = []
        let units = Array(text.utf16)
        var i = 0
        while i < units.count {
            let c = units[i]
            if c == 0x0A || c == 0x0D {
                out.append(String(decoding: current, as: UTF16.self))
                current.removeAll(keepingCapacity: true)
                if c == 0x0D && i + 1 < units.count && units[i + 1] == 0x0A { i += 1 }
            } else {
                current.append(c)
            }
            i += 1
        }
        out.append(String(decoding: current, as: UTF16.self))
        return out
    }

    /** `split(Regex("\\s+"))`: Java's \s is space, tab, newline, vertical tab, form feed, carriage return. */
    private static func tokens(_ line: String) -> [String] {
        var out: [String] = []
        var current = ""
        var inSpace = false
        for ch in line.unicodeScalars {
            if ch == " " || ch == "\t" || ch == "\n" || ch == "\u{0B}" || ch == "\u{0C}" || ch == "\r" {
                if !inSpace { out.append(current); current = "" }
                inSpace = true
            } else {
                inSpace = false
                current.unicodeScalars.append(ch)
            }
        }
        out.append(current)
        return out
    }

    /** Kotlin's `String.split(",")` (or any one delimiter): every piece, empty ones included. */
    static func split(_ text: String, _ by: Character) -> [String] {
        text.split(separator: by, omittingEmptySubsequences: false).map(String.init)
    }

    public static func parse(_ text: String) throws -> Program {
        var fps = 30
        var mode = "3d"
        var phi = 0.0
        var theta = 0.0
        var zoom = 1.0
        var background = Int32(bitPattern: 0xFF00_0000)
        var shapes = OrderedMap<ShapeSpec>()
        var assets = OrderedMap<(String, String)>()
        var surfaces: [SurfaceSpec] = []
        var timeline: [Step] = []
        var z: [String: Double] = [:]
        var clips = OrderedMap<String>()
        var clipLoops: [String: Int] = [:]
        var images: [ImageSpec] = []
        var drifts: [String: Drift] = [:]

        for raw in lines(text) {
            let line = kTrim(raw)
            if line.isEmpty || line.hasPrefix("#") { continue }

            let tokens = tokens(line)
            let verb = tokens[0]
            var positional: [String] = []
            var args: [String: String] = [:]
            for token in tokens.dropFirst() {
                if let eq = token.firstIndex(of: "=") {
                    args[String(token[token.startIndex..<eq])] = String(token[token.index(after: eq)...])
                } else {
                    positional.append(token)
                }
            }

            func t() throws -> Double { try kDouble(try getValue(args, "t")) }
            func rate() -> String { args["rate"] ?? "smooth" }
            func pos(_ i: Int) throws -> String { try element(positional, i) }
            func doubles(_ text: String) throws -> [Double] { try split(text, ",").map { try kDouble($0) } }
            func ints(_ text: String) throws -> [Int] { try split(text, ",").map { try kInt($0) } }

            if DECLARATIONS.contains(verb), let value = args["z"] { z[try pos(0)] = try kDouble(value) }

            switch verb {
            case "scene":
                fps = try args["fps"].map { try kInt($0) } ?? 30
                if !positional.isEmpty { mode = positional[0] }
                if let bg = args["bg"] { background = i32(try hexRgb(bg)) | Int32(bitPattern: 0xFF00_0000) }
            case "circle", "square", "rect":
                shapes[try pos(0)] = ShapeSpec(
                    kind: verb,
                    size: try kDouble(args["r"] ?? args["s"] ?? "0"),
                    extent: try args["wh"].map { try doubles($0) },
                    stroke: try hexRgb(try getValue(args, "stroke")),
                    width: try kDouble(args["w"] ?? "4"),
                    at: try doubles(args["at"] ?? "0,0")
                )
            case "text", "geom":
                assets[try pos(0)] = (verb, try getValue(args, "asset"))
            case "clip":
                clips[try pos(0)] = try getValue(args, "asset")
                if let loop = args["loop"] { clipLoops[try pos(0)] = try kInt(loop) }
            case "image":
                let px = split(try getValue(args, "px"), ",")
                var keys: [Double] = []
                for key in split(args["keys"] ?? "", ";") {
                    if key.isEmpty { continue }
                    let parts = split(key, ":")
                    keys.append(try kDouble(try element(parts, 0)))
                    keys.append(try kDouble(try element(parts, 1)))
                    let corners = split(try element(parts, 2), ",")
                    try require(corners.count == 6, "an image key needs six corner numbers: \(key)")
                    for c in corners { keys.append(try kDouble(c)) }
                }
                images.append(ImageSpec(
                    name: try pos(0), src: try getValue(args, "src"), width: try kInt(try element(px, 0)),
                    height: try kInt(try element(px, 1)), z: try kDouble(args["z"] ?? "0"), keys: keys,
                    drift: try args["drift"].map { try Drift.ofList($0) }
                ))
            case "run":
                timeline.append(Step.Run(try pos(0), try t()))
            case "drift":
                drifts[try pos(0)] = try Drift.parse(args)
            case "surface":
                surfaces.append(SurfaceSpec(
                    name: positional.first ?? "S",
                    fn: try Expr.parse(try getValue(args, "fn")),
                    uRange: try doubles(try getValue(args, "u")),
                    vRange: try doubles(try getValue(args, "v")),
                    resolution: try ints(try getValue(args, "res")),
                    colors: try split(try getValue(args, "fill"), ",").map { try hexRgb($0) },
                    alpha: try kDouble(args["alpha"] ?? "1.0"),
                    stroke: try kDouble(args["stroke"] ?? "0.0")
                ))
            case "camera":
                phi = toRadians(try kDouble(args["phi"] ?? "0"))
                theta = toRadians(try kDouble(args["theta"] ?? "0"))
                zoom = try kDouble(args["zoom"] ?? "1")
            case "create", "uncreate":
                timeline.append(Step.Create(
                    try pos(0), try t(), rate(), removing: verb == "uncreate",
                    lag: try args["lag"].map { try kDouble($0) }
                ))
            case "transform":
                timeline.append(Step.Transform(
                    try pos(0), try pos(1), try t(), rate(),
                    arc: try args["arc"].map { try kDouble($0) } ?? 0.0
                ))
            case "morph":
                timeline.append(Step.Morph(try pos(0), try pos(1), try t(), keep: args["keep"] == "1"))
            case "show":
                timeline.append(Step.Show(try pos(0)))
            case "hide":
                timeline.append(Step.Hide(try pos(0)))
            case "fade":
                timeline.append(Step.Fade(try pos(0), try t(), try shiftOf(args),
                                          try args["from"].map { try kDouble($0) } ?? 1.0, rate()))
            case "fadeout":
                timeline.append(Step.FadeOut(try pos(0), try t(), try shiftOf(args),
                                             try args["from"].map { try kDouble($0) } ?? 1.0, rate()))
            case "write":
                timeline.append(Step.Write(try pos(0), try t()))
            case "unwrite":
                timeline.append(Step.Unwrite(try pos(0), try t()))
            case "fill":
                timeline.append(Step.Fill(
                    try pos(0),
                    try args["color"].map { try hexRgb($0) },
                    try args["opacity"].map { try kDouble($0) },
                    try t()
                ))
            case "stroke":
                timeline.append(Step.Stroke(
                    try pos(0),
                    try args["color"].map { try hexRgb($0) },
                    try args["w"].map { try kDouble($0) },
                    try args["opacity"].map { try kDouble($0) },
                    try t()
                ))
            case "xform":
                let by = split(args["by_xy"] ?? "0,0", ",")
                timeline.append(Step.Xform(
                    try pos(0), try kDouble(args["by"] ?? "1.0"),
                    [try kDouble(try element(by, 0)), try kDouble(try element(by, 1))], try t(), rate()
                ))
            case "grow":
                timeline.append(Step.Grow(try pos(0), try t(), try pointOf(args["at"])))
            case "laggedgrow":
                timeline.append(Step.LaggedGrow(
                    try pos(0), try kDouble(try getValue(args, "lag")),
                    try ints(try getValue(args, "groups")), try t(),
                    try pointOf(args["at"])
                ))
            case "rotate":
                timeline.append(Step.Rotate(
                    try pos(0),
                    toRadians(try kDouble(try getValue(args, "deg"))),
                    try doubles(args["at"] ?? "0,0"),
                    try t(), rate()
                ))
            case "indicate":
                timeline.append(Step.Indicate(try pos(0), try t()))
            case "move":
                timeline.append(Step.Move(
                    try args["phi"].map { toRadians(try kDouble($0)) },
                    try args["theta"].map { toRadians(try kDouble($0)) },
                    try t(),
                    try args["zoom"].map { try kDouble($0) }
                ))
            case "spin":
                timeline.append(Step.Spin(try kDouble(try getValue(args, "rate")), try t(), args["about"] ?? "theta"))
            case "lag":
                timeline.append(Step.LagHeader(
                    try ints(try getValue(args, "runs")),
                    try kDouble(try getValue(args, "ratio")),
                    try t()
                ))
            case "par":
                timeline.append(Step.Par(try kInt(try getValue(args, "n")), try t()))
            case "wait":
                timeline.append(Step.Wait(try t()))
            default:
                throw PanimError.illegalArgument("unknown verb '\(verb)'")
            }
        }

        return Program(fps: fps, mode: mode, phi: phi, theta: theta, zoom: zoom, shapes: shapes, assets: assets,
                       surfaces: surfaces, timeline: timeline, z: z, background: background, clips: clips,
                       clipLoops: clipLoops, images: images, drifts: drifts)
    }

    private static let DECLARATIONS: Set<String> = ["circle", "square", "rect", "text", "geom", "clip"]

    private static func shiftOf(_ args: [String: String]) throws -> [Double] {
        let parts = split(args["shift"] ?? "0,0", ",")
        return [try kDouble(parts[0]), try kDouble(parts.count > 1 ? parts[1] : "0")]
    }

    private static func pointOf(_ text: String?) throws -> [Double]? {
        guard let text = text else { return nil }
        let parts = try split(text, ",").map { try kDouble($0) }
        return [try element(parts, 0), try element(parts, 1), parts.count > 2 ? parts[2] : 0.0]
    }

    private static func hexRgb(_ text: String) throws -> Int {
        let hex = text.hasPrefix("#") ? String(text.dropFirst()) : text
        let units = Array(hex.utf16)
        guard units.count >= 6 else {
            throw PanimError.indexOutOfBounds("begin 0, end 6, length \(units.count)")
        }
        return try kInt(String(decoding: units[0..<6], as: UTF16.self), radix: 16)
    }
}

/**
 * A slow drift: a little across and up, a breath larger and smaller, a hair of a turn, each on its own long period.
 * The same formula as the lecture engine's (harness/lecture/pocket_lecture.py drift_matrix), from the program's
 * clock. A backdrop drifts about the origin from the program's start; a picture (`t0`, `cx`, `cy`) drifts about its
 * centre from where it stood when it came on, so it starts still and its labels move with it.
 */
public final class Drift {
    public let period: Double, amp: Double, scale: Double, turn: Double
    public let t0: Double?, cx: Double, cy: Double

    public init(_ period: Double, _ amp: Double, _ scale: Double, _ turn: Double,
                t0: Double? = nil, cx: Double = 0.0, cy: Double = 0.0) {
        self.period = period
        self.amp = amp
        self.scale = scale
        self.turn = turn
        self.t0 = t0
        self.cx = cx
        self.cy = cy
    }

    private func raw(_ seconds: Double) -> [Double] {
        let w = 2 * Double.pi * seconds / period
        let dx = amp * sin(w)
        let dy = 0.6 * amp * sin(w / 1.3 + 1.1)
        let k = 1 + scale * sin(w / 1.7 + 0.4)
        let a = turn * sin(w / 2.1 + 2.0)
        let c = cos(a) * k
        let s = sin(a) * k
        // x' = A (x - centre) + centre + d
        return [c, -s, cx + dx - (c * cx - s * cy), s, c, cy + dy - (s * cx + c * cy)]
    }

    /** The row-major 3x4 transform at [seconds]. */
    public func at(_ seconds: Double) -> [Double] {
        var m = raw(seconds)
        if let start = t0 {
            // Relative to where it stood at t0: m * inverse(raw(t0)).
            let o = raw(start)
            let det = o[0] * o[4] - o[1] * o[3]
            let i0 = o[4] / det, i1 = -o[1] / det, i3 = -o[3] / det, i4 = o[0] / det
            let i2 = -(i0 * o[2] + i1 * o[5]), i5 = -(i3 * o[2] + i4 * o[5])
            m = [
                m[0] * i0 + m[1] * i3, m[0] * i1 + m[1] * i4, m[0] * i2 + m[1] * i5 + m[2],
                m[3] * i0 + m[4] * i3, m[3] * i1 + m[4] * i4, m[3] * i2 + m[4] * i5 + m[5],
            ]
        }
        return [m[0], m[1], 0.0, m[2], m[3], m[4], 0.0, m[5], 0.0, 0.0, 1.0, 0.0]
    }

    /** Move a picture's three corners (ulx, uly, urx, ury, dlx, dly) to where the drift has them at [seconds]. */
    public func move(_ corners: inout [Float], _ seconds: Double) {
        let m = at(seconds)
        for i in 0..<3 {
            let x = Double(corners[2 * i])
            let y = Double(corners[2 * i + 1])
            corners[2 * i] = Float(m[0] * x + m[1] * y + m[3])
            corners[2 * i + 1] = Float(m[4] * x + m[5] * y + m[7])
        }
    }

    public static func parse(_ args: [String: String]) throws -> Drift {
        Drift(
            try kDouble(args["period"] ?? "26"),
            try kDouble(args["amp"] ?? "0.3"),
            try kDouble(args["scale"] ?? "0.025"),
            try kDouble(args["turn"] ?? "0.012"),
            t0: try args["t0"].map { try kDouble($0) },
            cx: try kDouble(args["cx"] ?? "0"),
            cy: try kDouble(args["cy"] ?? "0")
        )
    }

    /** An image line's `drift=period,amp,scale,turn,t0,cx,cy`. */
    public static func ofList(_ text: String) throws -> Drift {
        let v = try Program.split(text, ",").map { try kDouble($0) }
        try require(v.count == 7, "an image's drift needs seven numbers: \(text)")
        return Drift(v[0], v[1], v[2], v[3], t0: v[4], cx: v[5], cy: v[6])
    }
}
