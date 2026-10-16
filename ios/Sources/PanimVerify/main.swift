// Ported from player/desktop/src/main/kotlin/com/pocketanim/desktop/Verify.kt: the modes that need no rasteriser.
//
// Desktop harness. Not shipped -- this exists so the code that *is* shipped can be run and checked here, on Linux
// as on a Mac, and diffed against the Kotlin core's own Verify (ios/scripts/crosscheck.sh):
//
//   PanimVerify <scene.panim|scene.panm|libraryDir[#scene]> dump [probe]
//   PanimVerify <scene.panim|scene.panm|libraryDir[#scene]> trace [all|every:N|i,j,k] [default|shipping|<variant>]
//   PanimVerify <libraryDir> library
//
// `dump` and `library` print what the Kotlin Verify prints, byte for byte; `trace` prints every PathSink call the
// renderer makes, which the Kotlin Verify's `trace` mode prints too.
import Foundation
import PanimCore

// MARK: - Output

final class Output {
    private var buffer = ""

    func append(_ text: String) {
        buffer += text
        if buffer.utf8.count > 1 << 20 { flush() }
    }

    func flush() {
        FileHandle.standardOutput.write(buffer.data(using: .utf8)!)
        buffer = ""
    }
}

let stdout = Output()

func println(_ text: String = "") { stdout.append(text + "\n") }

/** Straight to standard output, after anything println() has gathered. */
func printRaw(_ text: String) {
    stdout.append(text)
    stdout.flush()
}

func f6(_ v: Float) -> String { JavaFormat.fixed(v, 6) }
func f6(_ v: Double) -> String { JavaFormat.fixed(v, 6) }
func f4(_ v: Float) -> String { JavaFormat.fixed(v, 4) }

/** `Integer.toHexString(argb).padStart(8, '0')`. */
func hex(_ argb: Int32) -> String {
    let text = String(UInt32(bitPattern: argb), radix: 16)
    return String(repeating: "0", count: max(0, 8 - text.count)) + text
}

// MARK: - Files

/**
 * Assets off the filesystem, laid out as the exporter writes them.
 *
 * On iOS this is backed by app storage and a content-addressed cache; the
 * shape of the interface is the same because the interpreter must not care.
 */
final class FileAssets: AssetLoader {
    private let root: URL

    init(_ root: URL) { self.root = root }

    func asset(_ id: String) throws -> [UInt8] { try readFile(root.appendingPathComponent("assets/\(id).panm")) }
    func glyphLibrary() throws -> [UInt8] { try readFile(root.appendingPathComponent("library.atlas")) }
    // images/ beside the program (dsl/generated), or one up (a library's scenes/).
    func image(_ src: String) -> [UInt8]? {
        for candidate in [root.appendingPathComponent("images/\(src)"),
                          root.standardizedFileURL.deletingLastPathComponent().appendingPathComponent("images/\(src)")] {
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: candidate.path, isDirectory: &isDir), !isDir.boolValue {
                return try? readFile(candidate)
            }
        }
        return nil
    }
}

func readFile(_ url: URL) throws -> [UInt8] {
    guard let data = FileManager.default.contents(atPath: url.path) else {
        throw PanimError.io("\(url.path) (No such file or directory)")
    }
    return [UInt8](data)
}

/** [Storage] over a directory, which is what app storage will look like. */
final class DirStorage: Storage {
    private let root: URL

    init(_ root: URL) { self.root = root }

    private func url(_ path: String) -> URL { root.appendingPathComponent(path) }

    func exists(_ path: String) -> Bool { FileManager.default.fileExists(atPath: url(path).path) }
    func read(_ path: String) throws -> [UInt8] { try readFile(url(path)) }
    func sizeOf(_ path: String) -> Int64 {
        let attributes = try? FileManager.default.attributesOfItem(atPath: url(path).path)
        return (attributes?[.size] as? NSNumber)?.int64Value ?? 0
    }
    func open(_ path: String) throws -> InputStream {
        guard let stream = InputStream(url: url(path)) else { throw PanimError.io("\(url(path).path) cannot be read") }
        return stream
    }
    func file(_ path: String) -> URL? { url(path) }
}

func isDirectory(_ path: String) -> Bool {
    var isDir: ObjCBool = false
    return FileManager.default.fileExists(atPath: path, isDirectory: &isDir) && isDir.boolValue
}

func isFile(_ path: String) -> Bool {
    var isDir: ObjCBool = false
    return FileManager.default.fileExists(atPath: path, isDirectory: &isDir) && !isDir.boolValue
}

/**
 * Load either tier. A `.panim` is a program and is expanded here, exactly as
 * the device would; a `.panm` is already sampled frames; a library directory
 * (or `<dir>#<scene>`) is opened through its manifest, as the phone opens it.
 */
func load(_ spec: String) throws -> Frames {
    let hash = spec.lastIndex(of: "#")
    let dir = hash.map { String(spec[spec.startIndex..<$0]) } ?? spec
    if isDirectory(dir) && isFile(URL(fileURLWithPath: dir).appendingPathComponent("library.json").path) {
        let library = try Library.load(DirStorage(URL(fileURLWithPath: dir)))
        guard let first = library.scenes.first else { throw PanimError.noSuchElement("List is empty.") }
        return try library.open(hash.map { String(spec[spec.index(after: $0)...]) } ?? first.name)
    }
    let url = URL(fileURLWithPath: spec)
    if url.lastPathComponent.hasSuffix(".panim") {
        let text = String(decoding: try readFile(url), as: UTF8.self)
        return try Interpreter.open(try Program.parse(text), FileAssets(url.deletingLastPathComponent()))
    }
    return try Scene.parse(try readFile(url))
}

// MARK: - dump

/** The canonical dump the Java and Python decoders also emit, field for field. */
func highestAtlasId(_ scene: Frames, _ index: Int) throws -> Int {
    var highest = -1
    for inst in try scene.instances(index) where inst.atlasId > highest { highest = inst.atlasId }
    return highest
}

func pointsLine(_ tag: String, _ id: Int, _ pts: [Float]) -> String {
    let n = pts.count / 3
    var mean = [0.0, 0.0, 0.0]
    for i in 0..<n { for k in 0..<3 { mean[k] += Double(pts[i * 3 + k]) } }
    for k in 0..<3 { mean[k] = n > 0 ? mean[k] / Double(n) : 0.0 }
    var line = "\(tag) \(id) \(n)"
    let firstLast: [Float] = n > 0
        ? [pts[0], pts[1], pts[2], pts[(n - 1) * 3], pts[(n - 1) * 3 + 1], pts[(n - 1) * 3 + 2]]
        : [0, 0, 0, 0, 0, 0]
    for v in firstLast { line += " " + f6(v) }
    for v in mean { line += " " + f6(v) }
    return line + "\n"
}

func dump(_ scene: Frames, _ probe: Int) throws {
    var out = ""
    let decoded = scene as? Scene

    // A computing source has no records array and grows its atlas as it plays,
    // so the header and the per-record lines are gathered by walking frames.
    var perFrame = [Int](repeating: 0, count: scene.frameCount)
    var atlasSize = 0
    for i in 0..<scene.frameCount {
        perFrame[i] = try scene.instances(i).count
        atlasSize = max(atlasSize, try highestAtlasId(scene, i) + 1)
    }
    // A decoded container always carries a quantisation box in its header, even
    // when it is all zeros -- a text asset has an empty atlas because its
    // glyphs live in the shared library.
    let shapeCount = decoded?.atlas.count ?? atlasSize

    let hasCamera = try scene.camera(0) != nil ? 1 : 0
    if let decoded = decoded {
        out += "H \(decoded.fps) \(decoded.frameCount) \(shapeCount) \(hasCamera)\n"
        out += "B \(f6(decoded.lo[0])) \(f6(decoded.lo[1])) \(f6(decoded.lo[2])) " +
            "\(f6(decoded.hi[0])) \(f6(decoded.hi[1])) \(f6(decoded.hi[2]))\n"
        for s in 0..<decoded.atlas.count { out += pointsLine("A", s, decoded.atlas[s]) }
    } else {
        // Shape count is bookkeeping for a computing source, not content.
        out += "H \(scene.fps) \(scene.frameCount) \(hasCamera)\n"
    }

    // A decoded container has real record kinds; a computing source has no
    // records at all, so every frame reports as a snapshot.
    for r in 0..<scene.frameCount {
        if let decoded = decoded {
            out += "R \(r) \(decoded.records[r].kind) \(decoded.records[r].instances.count)\n"
        } else {
            out += "R \(r) 0 \(perFrame[r])\n"
        }
    }

    if let camera = try scene.camera(probe) {
        out += "C \(probe)"
        for v in camera { out += " " + f6(v) }
        out += "\n"
    }

    let frame = try scene.instances(probe)
    out += "F \(probe) \(frame.count)\n"
    for (i, inst) in frame.enumerated() {
        // A computing source allocates atlas ids as it goes and reuses them
        // once transient reveal geometry is wound back, so the id itself is
        // bookkeeping rather than meaning: what must agree is the geometry.
        if decoded == nil {
            let pts = scene.shape(inst.atlasId)
            out += pointsLine("G", i, pts)
            out += "I \(i) \(inst.slot) \(pts.count / 3) \(inst.flags)"
        } else {
            out += "I \(i) \(inst.slot) \(inst.atlasId) \(inst.flags)"
        }
        for v in inst.transform { out += " " + f6(v) }
        for c in [inst.fill, inst.stroke] {
            out += " \((c >> 16) & 0xFF) \((c >> 8) & 0xFF) \(c & 0xFF) \(Int32(bitPattern: UInt32(bitPattern: c) >> 24) & 0xFF)"
        }
        out += " " + f6(inst.strokeWidth)
        if let normal = inst.normal { for k in 0..<3 { out += " " + f6(normal[k]) } }
        out += "\n"
    }
    for image in try scene.images(probe) {
        out += "P \(image.src) \(image.before) \(f4(image.alpha))"
        for v in image.corners { out += " " + f4(v) }
        out += "\n"
    }
    // Printed whole at the end, as Kotlin's dump prints its StringBuilder: a scene that fails part way prints nothing.
    printRaw(out)
}

// MARK: - trace

/**
 * A [PathSink] that writes down every call it is handed, one line each, floats to four places: the drawing itself,
 * as text, to diff against the Kotlin Verify's `trace` call for call.
 */
final class TraceSink: PathSink {
    var out = ""

    func beginPath() { out += "beginPath\n" }
    func moveTo(_ x: Float, _ y: Float) { out += ("moveTo \(f4(x)) \(f4(y))\n") }
    func lineTo(_ x: Float, _ y: Float) { out += ("lineTo \(f4(x)) \(f4(y))\n") }
    func cubicTo(_ x1: Float, _ y1: Float, _ x2: Float, _ y2: Float, _ x3: Float, _ y3: Float) {
        out += ("cubicTo \(f4(x1)) \(f4(y1)) \(f4(x2)) \(f4(y2)) \(f4(x3)) \(f4(y3))\n")
    }
    func closeSubpath() { out += ("closeSubpath\n") }
    func fillPath(_ argb: Int32) { out += ("fill \(hex(argb))\n") }
    func strokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        out += ("stroke \(hex(argb)) \(f4(widthInSceneUnits))\n")
    }
    func fillAndStrokePath(_ argb: Int32, _ widthInSceneUnits: Float) {
        out += ("fillAndStroke \(hex(argb)) \(f4(widthInSceneUnits))\n")
    }
    func strokeStyle(round: Bool) { out += ("strokeStyle \(round ? "round" : "bevel")\n") }
    func drawImage(_ image: ImageDraw, _ bytes: (String) -> [UInt8]?) {
        var line = "drawImage \(image.src) \(image.width) \(image.height) \(f4(image.alpha))"
        for c in image.corners { line += " " + f4(c) }
        line += " before \(image.before) bytes \(bytes(image.src)?.count ?? -1)\n"
        out += line
    }
}

func trace(_ scene: Frames, _ framesArg: String?, _ optionsArg: String?) throws {
    let n = scene.frameCount
    let spec = framesArg ?? "every:30"
    var frames: [Int]
    if spec == "all" {
        frames = Array(0..<n)
    } else if spec.hasPrefix("every:") {
        let by = try kInt(String(spec.dropFirst("every:".count)))
        frames = Array(stride(from: 0, to: n, by: by))
        if n > 0 && frames.last != n - 1 { frames.append(n - 1) }
    } else {
        frames = try spec.split(separator: ",", omittingEmptySubsequences: false).map {
            try kInt($0.trimmingCharacters(in: .whitespaces))
        }
    }
    let name = optionsArg ?? "shipping"
    let options: RenderOptions
    switch name {
    case "default": options = RenderOptions.DEFAULT
    case "shipping": options = RenderOptions.forSurface(1280)
    default:
        guard let found = Benchmark.variants(1280).first(where: { $0.0 == name }) else {
            throw PanimError.illegalState("unknown options \(name)")
        }
        options = found.1
    }
    let sink = TraceSink()
    sink.out += "trace fps \(scene.fps) frames \(n) background \(hex(scene.background))\n"
    for i in frames {
        let key = try scene.contentKey(i)
        sink.out += "frame \(i) key \(key == FramesConstants.UNKNOWN ? "unknown" : String(key))\n"
        try Renderer.drawFrame(scene, i, sink, options)
        // Printed in the pieces Kotlin's trace prints, so a scene that fails part way prints the same part.
        if sink.out.utf8.count > 1 << 20 { // ASCII: the same count as Kotlin's UTF-16 length
            printRaw(sink.out)
            sink.out = ""
        }
    }
    printRaw(sink.out)
}

// MARK: - library

/** What the JVM's ImageIO would open: the formats it reads, by their signatures. */
func decodable(_ bytes: [UInt8]) -> Bool {
    if bytes.starts(with: [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) { return true } // PNG
    if bytes.starts(with: [0xFF, 0xD8, 0xFF]) { return true } // JPEG
    if bytes.starts(with: Array("GIF8".utf8)) { return true }
    if bytes.starts(with: Array("BM".utf8)) { return true }
    return false
}

/**
 * Open every scene the way the device will: through the manifest, not by
 * knowing where files live. This is the check that the library is actually
 * self-describing rather than a directory the harness happens to understand.
 */
func libraryReport(_ root: URL) throws -> Bool {
    let library = try Library.load(DirStorage(root))
    let missing = library.missing()
    if !missing.isEmpty {
        println("missing \(missing.count) path(s): [\(missing.prefix(5).joined(separator: ", "))]")
        return false
    }

    // Digests as well as sizes: a download that truncates is caught by size,
    // but one that corrupts a block in place is not, and the symptom of the
    // second is geometry that decodes and draws the wrong picture.
    let problems = try library.checkIntegrity(verifyDigests: true)
    if !problems.isEmpty {
        println("integrity: \(problems.count) problem(s)")
        for problem in problems.prefix(5) { println("  \(problem)") }
        return false
    }
    println("integrity: \(library.assets.count) files match the manifest")

    println(JavaFormat.format("%-22s %5s %7s %8s %9s  %s", .string("scene"), .string("tier"), .string("frames"),
                              .string("bytes"), .string("instances"), .string("status")))
    var failures = 0
    for entry in library.scenes {
        if !library.isPlayable(entry) {
            println(JavaFormat.format("%-22s %5d %7d %8d %9s  NOT PLAYABLE", .string(entry.name), .int(Int64(entry.tier)),
                                      .int(Int64(entry.frames)), .int(entry.playableBytes), .string("-")))
            failures += 1
            continue
        }
        var status: String? = nil
        do {
            let frames = try library.open(entry.name)
            // Touch both ends and the middle: enough to prove assets resolved
            // and the timeline runs, without rendering the whole scene.
            var seen: Int64 = 0
            for i in [0, frames.frameCount / 2, frames.frameCount - 1] {
                seen += Int64(try frames.instances(i).count)
                // A picture the program draws must be one the library holds and an image reader can open.
                for image in try frames.images(i) {
                    guard let bytes = frames.imageBytes(image.src) else {
                        throw PanimError.illegalState("picture \(image.src) is not in the library")
                    }
                    // WebP (the library's pictures) has its header checked; the platform decodes it.
                    let webp = bytes.count > 12 && bytes[0..<4].elementsEqual("RIFF".utf8) &&
                        bytes[8..<12].elementsEqual("WEBP".utf8)
                    if !webp && !decodable(bytes) {
                        throw PanimError.illegalState("picture \(image.src) does not decode")
                    }
                }
            }
            println(JavaFormat.format("%-22s %5d %7d %8d %9d  ok", .string(entry.name), .int(Int64(entry.tier)),
                                      .int(Int64(frames.frameCount)), .int(entry.playableBytes), .int(seen)))
        } catch let error as PanimError {
            failures += 1
            status = "\(error.kotlinName): \(error.message ?? "null")"
        } catch {
            failures += 1
            status = "\(type(of: error)): \(error)"
        }
        if let status = status {
            println(JavaFormat.format("%-22s %5d %7d %8d %9s  FAIL %s", .string(entry.name), .int(Int64(entry.tier)),
                                      .int(Int64(entry.frames)), .int(entry.playableBytes), .string("-"), .string(status)))
        }
    }
    return failures == 0
}

// MARK: - main

func run(_ args: [String]) throws -> Int32 {
    if args.count < 2 {
        println("usage: PanimVerify <scene|libraryDir[#scene]> <dump|trace|library> [args]")
        return 0
    }
    if args[1] == "library" {
        return try libraryReport(URL(fileURLWithPath: args[0])) ? 0 : 1
    }

    let scene = try load(args[0])
    let mode = args[1]
    switch mode {
    case "dump":
        let probe = try args.count > 2 ? kInt(args[2]) : scene.frameCount / 2
        try dump(scene, probe)
    case "trace":
        try trace(scene, args.count > 2 ? args[2] : nil, args.count > 3 ? args[3] : nil)
    default:
        println("unknown mode \(mode)")
    }
    return 0
}

let status: Int32
do {
    status = try run(Array(CommandLine.arguments.dropFirst()))
} catch let error as PanimError {
    stdout.flush()
    FileHandle.standardError.write("Exception in thread \"main\" \(error.kotlinName): \(error.message ?? "")\n".data(using: .utf8)!)
    exit(1)
} catch {
    stdout.flush()
    FileHandle.standardError.write("error: \(error)\n".data(using: .utf8)!)
    exit(1)
}
stdout.flush()
exit(status)
