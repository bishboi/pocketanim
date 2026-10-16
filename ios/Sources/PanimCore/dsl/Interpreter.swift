// Ported from player/core/src/main/kotlin/com/pocketanim/core/dsl/Interpreter.kt.
import Foundation

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
 * It produces [Frames], as [Panm] does, so the renderer and the player cannot
 * tell which tier they are playing.
 */

/** Where baked assets come from. iOS reads app storage; the harness reads files. */
public protocol AssetLoader: AnyObject {
    /** The content-addressed asset `<id>.panm`. */
    func asset(_ id: String) throws -> [UInt8]
    /** The library-wide glyph atlas that text assets index into. */
    func glyphLibrary() throws -> [UInt8]
    /** A picture an `image` line names (a PNG); nil when it is not here. */
    func image(_ src: String) -> [UInt8]?
}

public extension AssetLoader {
    func image(_ src: String) -> [UInt8]? { nil }
}

let FOCAL_DISTANCE = 20.0
let ZOOM = 1.0
let GAMMA = 0.0
let LIGHT_SOURCE: [Double] = [-7.0, -9.0, 10.0]

/** Mutable instance state during interpretation; rgba kept as Python keeps it. */
final class Inst {
    var atlasId: Int
    var transform: [Double]
    var fill: [Int]
    var stroke: [Int]
    var width: Double

    init(_ atlasId: Int, _ transform: [Double], _ fill: [Int], _ stroke: [Int], _ width: Double) {
        self.atlasId = atlasId
        self.transform = transform
        self.fill = fill
        self.stroke = stroke
        self.width = width
    }
}

final class Obj {
    var kind: String
    var visible: Bool
    var centre: [Double]
    var xform: [Double]
    var instances: [Inst]
    var flags: [Int]?
    var normals: [[Double]?]?
    var glyphIds: [Int]?
    var points: [Double]?
    var alpha: Double
    var strokeRgb: Int
    var width: Double
    /** A primitive's fill, RGBA. Only `fill` changes it; declarations have none. */
    var fill: [Int]
    /** Draw order: emitted in ascending z, stably, as Manim sorts by z_index. */
    var z: Double

    init(
        kind: String, visible: Bool, centre: [Double] = [0, 0, 0], xform: [Double] = identity(),
        instances: [Inst] = [], flags: [Int]? = nil, normals: [[Double]?]? = nil, glyphIds: [Int]? = nil,
        points: [Double]? = nil, alpha: Double = 1.0, strokeRgb: Int = 0xFFFFFF, width: Double = 0.0,
        fill: [Int] = [0, 0, 0, 0], z: Double = 0.0
    ) {
        self.kind = kind
        self.visible = visible
        self.centre = centre
        self.xform = xform
        self.instances = instances
        self.flags = flags
        self.normals = normals
        self.glyphIds = glyphIds
        self.points = points
        self.alpha = alpha
        self.strokeRgb = strokeRgb
        self.width = width
        self.fill = fill
        self.z = z
    }

    /**
     * A checkpoint copy.
     *
     * The instance *list* is copied but the instances are not: verbs replace
     * entries rather than mutating them in place, so sharing is safe and
     * copying 2,900 of them per checkpoint would not be. (Swift arrays copy by
     * value, so every field here is the copy Kotlin makes by hand.)
     */
    func copy() -> Obj {
        Obj(kind: kind, visible: visible, centre: centre, xform: xform, instances: instances, flags: flags,
            normals: normals, glyphIds: glyphIds, points: points, alpha: alpha, strokeRgb: strokeRgb, width: width,
            fill: fill, z: z)
    }
}

func identity() -> [Double] { [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0] }

/** Apply an object-level transform on top of an instance transform. */
func compose(_ outer: [Double], _ inner: [Double]) -> [Double] {
    var out = [Double](repeating: 0, count: 12)
    for row in 0..<3 {
        for col in 0..<3 {
            var sum = 0.0
            for k in 0..<3 { sum += outer[row * 4 + k] * inner[k * 4 + col] }
            out[row * 4 + col] = sum
        }
        var t = outer[row * 4 + 3]
        for k in 0..<3 { t += outer[row * 4 + k] * inner[k * 4 + 3] }
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
func pyRound(_ x: Double) -> Int {
    let f = floor(x)
    let diff = x - f
    if diff > 0.5 { return kToInt(f) + 1 }
    if diff < 0.5 { return kToInt(f) }
    return kToInt(f) % 2 == 0 ? kToInt(f) : kToInt(f) + 1
}

public enum Interpreter {

    /**
     * Open a program for playback.
     *
     * Frames are computed on demand rather than materialised: the eager form
     * measured at 98.8 MB retained for one corpus scene, which a phone does not
     * have to spare. See [ProgramFrames].
     */
    public static func open(_ program: Program, _ loader: AssetLoader) throws -> ProgramFrames {
        let builder = Builder(program, loader)
        try builder.prepare()
        return ProgramFrames(builder)
    }

    /** Manim composes rot_z(gamma) @ rot_x(-phi) @ rot_z(-theta - 90deg). */
    public static func cameraMatrix(_ phi: Double, _ theta: Double, _ gamma: Double = 0.0 /* GAMMA */) -> [Double] {
        func rotZ(_ a: Double) -> [Double] { [cos(a), -sin(a), 0.0, sin(a), cos(a), 0.0, 0.0, 0.0, 1.0] }
        func rotX(_ a: Double) -> [Double] { [1.0, 0.0, 0.0, 0.0, cos(a), -sin(a), 0.0, sin(a), cos(a)] }
        func mul(_ a: [Double], _ b: [Double]) -> [Double] {
            var o = [Double](repeating: 0, count: 9)
            for r in 0..<3 {
                for c in 0..<3 {
                    var s = 0.0
                    for k in 0..<3 { s += a[r * 3 + k] * b[k * 3 + c] }
                    o[r * 3 + c] = s
                }
            }
            return o
        }
        var result = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        for m in [rotZ(-theta - Double.pi / 2), rotX(-phi), rotZ(gamma)] { result = mul(m, result) }
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
    public static func tessellate(_ fn: Expr, _ uRange: [Double], _ vRange: [Double], _ res: [Int]) throws -> [[Double]] {
        let uRes = res[0], vRes = res[1]
        let us = (0...uRes).map { uRange[0] + (uRange[1] - uRange[0]) * Double($0) / Double(uRes) }
        let vs = (0...vRes).map { vRange[0] + (vRange[1] - vRange[0]) * Double($0) / Double(vRes) }

        var faces: [[Double]] = []
        faces.reserveCapacity(uRes * vRes)
        let ts = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
        for i in 0..<uRes {
            for j in 0..<vRes {
                let u1 = us[i], u2 = us[i + 1]
                let v1 = vs[j], v2 = vs[j + 1]
                let corners = [u1, v1, u2, v1, u2, v2, u1, v2, u1, v1]

                var points = [Double](repeating: 0, count: 16 * 3)
                var at = 0
                for edge in 0..<4 {
                    let ua = corners[edge * 2], va = corners[edge * 2 + 1]
                    let ub = corners[edge * 2 + 2], vb = corners[edge * 2 + 3]
                    for t in ts {
                        let u = ua + (ub - ua) * t
                        let v = va + (vb - va) * t
                        points[at] = u
                        points[at + 1] = v
                        points[at + 2] = try fn.eval(u, v)
                        at += 3
                    }
                }
                faces.append(points)
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
    public static func planeNormal(_ points: [Double]) -> [Double] {
        let n = points.count / 3
        var mean = [0.0, 0.0, 0.0]
        for i in 0..<n { for k in 0..<3 { mean[k] += points[i * 3 + k] } }
        for k in 0..<3 { mean[k] /= Double(n) }

        var c = [[Double]](repeating: [0, 0, 0], count: 3)
        for i in 0..<n {
            let dx = points[i * 3] - mean[0]
            let dy = points[i * 3 + 1] - mean[1]
            let dz = points[i * 3 + 2] - mean[2]
            let d = [dx, dy, dz]
            for a in 0..<3 { for b in 0..<3 { c[a][b] += d[a] * d[b] } }
        }

        // Jacobi eigenvalue iteration on a symmetric 3x3.
        var v: [[Double]] = (0..<3).map { r in (0..<3).map { col in r == col ? 1.0 : 0.0 } }
        for _ in 0..<32 {
            var p = 0, q = 1, best = Swift.abs(c[0][1])
            if Swift.abs(c[0][2]) > best { p = 0; q = 2; best = Swift.abs(c[0][2]) }
            if Swift.abs(c[1][2]) > best { p = 1; q = 2; best = Swift.abs(c[1][2]) }
            if best < 1e-14 { continue }

            let theta = 0.5 * atan2(2 * c[p][q], c[q][q] - c[p][p])
            let cs = cos(theta), sn = sin(theta)
            for k in 0..<3 {
                let ckp = c[k][p], ckq = c[k][q]
                c[k][p] = cs * ckp - sn * ckq
                c[k][q] = sn * ckp + cs * ckq
            }
            for k in 0..<3 {
                let cpk = c[p][k], cqk = c[q][k]
                c[p][k] = cs * cpk - sn * cqk
                c[q][k] = sn * cpk + cs * cqk
            }
            for k in 0..<3 {
                let vkp = v[k][p], vkq = v[k][q]
                v[k][p] = cs * vkp - sn * vkq
                v[k][q] = sn * vkp + cs * vkq
            }
        }

        var smallest = 0
        for k in 1..<3 { if c[k][k] < c[smallest][smallest] { smallest = k } }
        let normal = [v[0][smallest], v[1][smallest], v[2][smallest]]
        return normal[2] < 0 ? [-normal[0], -normal[1], -normal[2]] : normal
    }
}
