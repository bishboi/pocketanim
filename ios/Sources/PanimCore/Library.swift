// Ported from player/core/src/main/kotlin/com/pocketanim/core/Library.kt.
import Foundation

/**
 * What the device holds, and what it still needs.
 *
 * §5.3 wants all IR cached eagerly and audio fetched on demand. That only works
 * if the device can enumerate what exists and diff it against local storage,
 * which is what a manifest is for. The sync algorithm deliberately reduces to
 * "fetch the paths I do not have" -- content-addressed files never change, so
 * there is no invalidation to get wrong.
 */

/** Byte storage, wherever it lives. iOS reads app storage; the harness, files. */
public protocol Storage: AnyObject {
    func exists(_ path: String) -> Bool
    func read(_ path: String) throws -> [UInt8]
    func sizeOf(_ path: String) -> Int64

    /**
     * The file as a stream. A lecture's narration was tens to hundreds of MB, and reading it whole (to check its
     * digest, to copy it out for the decoder) ran the phone out of memory: big files are only ever streamed.
     */
    func open(_ path: String) throws -> InputStream

    /** The file itself, when the storage is a folder on this device: the decoder reads it in place. */
    func file(_ path: String) -> URL?
}

public extension Storage {
    func open(_ path: String) throws -> InputStream { InputStream(data: Data(try read(path))) }
    func file(_ path: String) -> URL? { nil }
}

/** One chapter of a lecture: its number, its title, and the frame it begins on. */
public final class Chapter {
    public let number: Int
    public let title: String
    public let frame: Int

    public init(number: Int, title: String, frame: Int) {
        self.number = number
        self.title = title
        self.frame = frame
    }
}

/** A file the manifest names, with what it should be when it arrives. */
public final class AssetRecord {
    public let path: String
    public let bytes: Int64
    public let digest: String?

    public init(path: String, bytes: Int64, digest: String?) {
        self.path = path
        self.bytes = bytes
        self.digest = digest
    }
}

/** One thing wrong with local storage, and which file it is wrong about. */
public final class IntegrityProblem: CustomStringConvertible {
    public let path: String
    public let reason: String

    public init(path: String, reason: String) {
        self.path = path
        self.reason = reason
    }

    public var description: String { "\(path): \(reason)" }
}

public final class SceneEntry {
    public let name: String
    public let tier: Int
    /** Present for tier 1; absent means this scene falls back to [container]. */
    public let program: String?
    /** Sampled frames. May be absent once a scene is reliably tier 1. */
    public let container: String?
    public let assets: [String]
    public let needsGlyphAtlas: Bool
    public let frames: Int
    /** Everything that must be local before this scene plays offline. */
    public let playableBytes: Int64
    public let audio: String?
    /** Where each chapter begins, in order: the player's chapter list and the marks on its seek bar. */
    public let chapters: [Chapter]

    public init(
        name: String, tier: Int, program: String?, container: String?, assets: [String], needsGlyphAtlas: Bool,
        frames: Int, playableBytes: Int64, audio: String?, chapters: [Chapter] = []
    ) {
        self.name = name
        self.tier = tier
        self.program = program
        self.container = container
        self.assets = assets
        self.needsGlyphAtlas = needsGlyphAtlas
        self.frames = frames
        self.playableBytes = playableBytes
        self.audio = audio
        self.chapters = chapters
    }

    /** Paths this scene cannot play without. Audio is deliberately not among them. */
    public func required() -> [String] {
        var out: [String] = []
        if let program = program { out.append(program) } else if let container = container { out.append(container) }
        out.append(contentsOf: assets)
        return out
    }
}

/** Every shape of a library in one file (assets.pack), each at an offset: [index] is id to (offset, length). */
public final class AssetPack {
    public let path: String
    public let index: [String: (Int, Int)]

    public init(path: String, index: [String: (Int, Int)]) {
        self.path = path
        self.index = index
    }
}

public final class Library {
    private let storage: Storage
    public let scenes: [SceneEntry]
    public let glyphAtlas: String?
    /** Every content-addressed file the manifest names, including the atlas. */
    public let assets: [AssetRecord]
    /** The shapes' pack, when the library keeps them in one file (tools/build_library.py); else one file each. */
    public let pack: AssetPack?

    public init(
        _ storage: Storage, scenes: [SceneEntry], glyphAtlas: String?, assets: [AssetRecord] = [],
        pack: AssetPack? = nil
    ) {
        self.storage = storage
        self.scenes = scenes
        self.glyphAtlas = glyphAtlas
        self.assets = assets
        self.pack = pack
    }

    /**
     * Check what is on disk against what the manifest says should be there.
     *
     * Content addressing makes sync trivial but does not make storage
     * trustworthy: a download can truncate, a cache can be evicted mid-write,
     * and the failure then looks like corrupt geometry rather than a bad file.
     * Size is checked always because it is free; the digest only when asked,
     * because hashing two megabytes on every launch is not.
     */
    public func checkIntegrity(verifyDigests: Bool = false) throws -> [IntegrityProblem] {
        var problems: [IntegrityProblem] = []
        for record in assets {
            if !storage.exists(record.path) { continue } // missing() reports these
            let actual = storage.sizeOf(record.path)
            if actual != record.bytes {
                problems.append(IntegrityProblem(path: record.path, reason: "expected \(record.bytes) B, found \(actual) B"))
                continue
            }
            guard let expected = record.digest else { continue }
            if verifyDigests {
                let stream = try storage.open(record.path)
                let got = Library.digestOf(stream)
                if got != expected {
                    problems.append(IntegrityProblem(path: record.path, reason: "digest \(got), expected \(expected)"))
                }
            }
        }
        return problems
    }

    /** Paths named by the manifest that this device does not have yet. */
    public func missing() -> [String] {
        var wanted: [String] = []
        var seen = Set<String>()
        func want(_ path: String) { if seen.insert(path).inserted { wanted.append(path) } }
        if let atlas = glyphAtlas, scenes.contains(where: { $0.needsGlyphAtlas }) { want(atlas) }
        for scene in scenes { scene.required().forEach(want) }
        return wanted.filter { !storage.exists($0) }
    }

    public func isPlayable(_ scene: SceneEntry) -> Bool {
        scene.required().allSatisfy { storage.exists($0) } &&
            (!scene.needsGlyphAtlas || (glyphAtlas.map { storage.exists($0) } ?? false))
    }

    public func entry(_ name: String) throws -> SceneEntry {
        guard let found = scenes.first(where: { $0.name == name }) else {
            throw PanimError.illegalState("no scene named '\(name)'")
        }
        return found
    }

    /**
     * Open a scene for playback.
     *
     * Prefers the program: it is smaller by three orders of magnitude and, as
     * §9.5 measures, also more accurate, because the device computes at full
     * precision rather than replaying quantised samples. The container is the
     * fallback for scenes the exporter could not express.
     */
    public func open(_ name: String) throws -> Frames {
        let scene = try entry(name)
        if let program = scene.program, storage.exists(program) {
            return try Interpreter.open(
                try Program.parse(String(decoding: try storage.read(program), as: UTF8.self)),
                ManifestAssets(storage, glyphAtlas, pack)
            )
        }
        guard let container = scene.container else {
            throw PanimError.illegalState("scene '\(name)' has neither program nor container")
        }
        return try Scene.parse(try storage.read(container))
    }

    private final class ManifestAssets: AssetLoader {
        private let storage: Storage
        private let glyphAtlas: String?
        private let pack: AssetPack?
        // The pack, read once when the first shape is asked for.
        private var packed: [UInt8]? = nil

        init(_ storage: Storage, _ glyphAtlas: String?, _ pack: AssetPack?) {
            self.storage = storage
            self.glyphAtlas = glyphAtlas
            self.pack = pack
        }

        func asset(_ id: String) throws -> [UInt8] {
            guard let pack = pack, let at = pack.index[id] else { return try storage.read("assets/\(id).panm") }
            if packed == nil { packed = try storage.read(pack.path) }
            let bytes = packed!
            try require(at.0 >= 0 && at.0 + at.1 <= bytes.count,
                        "shape \(id) lies outside \(pack.path) (\(at.0)+\(at.1) of \(bytes.count) bytes)")
            return Array(bytes[at.0..<(at.0 + at.1)])
        }

        func glyphLibrary() throws -> [UInt8] {
            guard let atlas = glyphAtlas else {
                throw PanimError.illegalState("scene needs the glyph atlas but the library has none")
            }
            return try storage.read(atlas)
        }

        func image(_ src: String) -> [UInt8]? {
            let path = "images/\(src)"
            return storage.exists(path) ? try? storage.read(path) : nil
        }
    }

    public static func load(_ storage: Storage, _ manifestPath: String = "library.json") throws -> Library {
        let root = try Json.parse(String(decoding: try storage.read(manifestPath), as: UTF8.self))
        try require(root["version"]?.asInt == 1, "unsupported library version")

        var scenes: [SceneEntry] = []
        for entry in root["scenes"]?.asList ?? [] {
            guard let name = entry["name"]?.asString else { throw PanimError.illegalState("scene without a name") }
            var chapters: [Chapter] = []
            for c in entry["chapters"]?.asList ?? [] {
                guard let number = c["number"]?.asInt, let frame = c["frame"]?.asInt else { continue }
                chapters.append(Chapter(number: number, title: c["title"]?.asString ?? "", frame: frame))
            }
            scenes.append(SceneEntry(
                name: name,
                tier: entry["tier"]?.asInt ?? 3,
                program: entry["program"]?.asString,
                container: entry["container"]?.asString,
                assets: (entry["assets"]?.asList ?? []).compactMap { $0.asString },
                needsGlyphAtlas: entry["needs_glyph_atlas"]?.asBool ?? false,
                frames: entry["frames"]?.asInt ?? 0,
                playableBytes: entry["playable_bytes"]?.asLong ?? 0,
                audio: entry["audio"]?.asString,
                chapters: chapters.stableSorted { $0.frame }
            ))
        }

        var assets: [AssetRecord] = []
        for entry in root["assets"]?.asList ?? [] {
            guard let path = entry["path"]?.asString else { continue }
            assets.append(AssetRecord(path: path, bytes: entry["bytes"]?.asLong ?? 0, digest: entry["sha256_16"]?.asString))
        }
        if let atlas = root["glyph_atlas"], let path = atlas["path"]?.asString {
            assets.append(AssetRecord(path: path, bytes: atlas["bytes"]?.asLong ?? 0, digest: atlas["sha256_16"]?.asString))
        }

        var pack: AssetPack? = nil
        if let node = root["asset_pack"], let path = node["path"]?.asString {
            var index: [String: (Int, Int)] = [:]
            for (id, at) in node["index"]?.fields?.entries ?? [] {
                let pair = at.asList
                if pair.count == 2 { index[id] = (pair[0].asInt ?? 0, pair[1].asInt ?? 0) }
            }
            pack = AssetPack(path: path, index: index)
        }

        return Library(storage, scenes: scenes, glyphAtlas: root["glyph_atlas"]?["path"]?.asString,
                       assets: assets, pack: pack)
    }

    /**
     * The manifest's short digest: the first 16 hex characters of SHA-256.
     *
     * Truncated because this guards against a damaged download rather than
     * a forged one, and 64 bits of it is already far past the point where
     * an accidental collision is conceivable.
     */
    public static func digestOf(_ bytes: [UInt8]) -> String {
        var sha = SHA256()
        sha.update(bytes)
        return hex16(sha.finish())
    }

    /** The same digest, read through a stream in 64 KB pieces, so a file of any size fits in memory. */
    public static func digestOf(_ stream: InputStream) -> String {
        var sha = SHA256()
        let size = 64 * 1024
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: size)
        defer { buffer.deallocate() }
        stream.open()
        defer { stream.close() }
        while true {
            let read = stream.read(buffer, maxLength: size)
            if read <= 0 { break }
            sha.update(UnsafeBufferPointer(start: buffer, count: read))
        }
        return hex16(sha.finish())
    }

    private static func hex16(_ hash: [UInt8]) -> String {
        var out = ""
        for i in 0..<8 {
            let byte = hash[i]
            out += String(byte >> 4, radix: 16) + String(byte & 0xF, radix: 16)
        }
        return out
    }
}
