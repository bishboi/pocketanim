// Ported from player/core/src/main/kotlin/com/pocketanim/core/LibraryImport.kt.
import Foundation
import PanimZip

/**
 * A library zip, as the harness's "Phone library" download makes it, unpacked into app storage.
 *
 * Until this existed a lecture reached the phone only by `adb push`, which no viewer does. The zip holds one
 * folder, `library/` (library.json, the atlas, the programs, the assets, the narration); it is unpacked into a
 * staging folder beside [dest], checked the way the player will read it -- the manifest parses, every file it
 * names is there at the size and digest it says -- and only then moved into place, so a broken or half-copied
 * download never replaces a library that played.
 *
 * Foundation and PanimZip only (the Kotlin uses java.util.zip), so it builds and is tested on Linux. PanimZip reads
 * a zip through its central directory, so a stream is first written to a file beside [dest].
 */
public enum LibraryImport {

    /** The most a zip may unpack to: a two-hour lecture is a few MB; this only stops a zip bomb. */
    public static let MAX_BYTES: Int64 = 512 * 1024 * 1024

    public struct ImportFailed: Error, LocalizedError, CustomStringConvertible {
        public let message: String
        public init(_ message: String) { self.message = message }
        public var description: String { message }
        public var errorDescription: String? { message }
    }

    /**
     * Unpack [input] into [dest] (replaced when the new library checks out). Returns the library, opened.
     * A leading `library/` folder in the zip is dropped; an entry that would land outside [dest] is refused.
     */
    public static func unpack(_ input: InputStream, _ dest: URL) throws -> Library {
        let parent = try parentOf(dest, "no folder to unpack into")
        let spool = parent.appendingPathComponent("\(dest.lastPathComponent).import.zip")
        defer { try? FileManager.default.removeItem(at: spool) }
        try copy(input, to: spool)
        return try unpack(zipFile: spool, dest)
    }

    /** [unpack] of a zip already in a file (a saved lecture's download), without copying it first. */
    static func unpack(zipFile: URL, _ dest: URL) throws -> Library {
        let parent = try parentOf(dest, "no folder to unpack into")
        let staging = parent.appendingPathComponent("\(dest.lastPathComponent).importing", isDirectory: true)
        try? FileManager.default.removeItem(at: staging)
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: staging) }
        try extract(zipFile, staging)
        guard let root = findRoot(staging) else {
            throw ImportFailed("the zip has no library.json: not a phone library")
        }
        return try install(root, dest)
    }

    /**
     * A library unpacked or downloaded into [root], checked the way the player will read it -- the manifest
     * parses, every file it names is there at the size and digest it says, it has a scene -- and only then moved
     * to [dest], replacing what was there. Shared by a zip's import and a saved lecture's download (SavedLectures).
     */
    public static func install(_ root: URL, _ dest: URL) throws -> Library {
        let parent = try parentOf(dest, "no folder to install into")
        let library = try Library.load(DirStorage(root))
        let absent = library.missing()
        if !absent.isEmpty {
            throw ImportFailed("the library is missing \(absent.count) file(s), e.g. \(absent[0])")
        }
        let problems = try library.checkIntegrity(verifyDigests: true)
        if !problems.isEmpty {
            throw ImportFailed("the library is incomplete: " + problems.prefix(3).map { $0.description }.joined(separator: "; "))
        }
        if library.scenes.isEmpty { throw ImportFailed("the library has no scenes") }
        let manager = FileManager.default
        let old = parent.appendingPathComponent("\(dest.lastPathComponent).old", isDirectory: true)
        try? manager.removeItem(at: old)
        if manager.fileExists(atPath: dest.path) {
            do { try manager.moveItem(at: dest, to: old) } catch {
                throw ImportFailed("cannot replace \(dest.lastPathComponent)")
            }
        }
        do { try manager.moveItem(at: root, to: dest) } catch {
            try? manager.moveItem(at: old, to: dest)
            throw ImportFailed("cannot move the library into place")
        }
        try? manager.removeItem(at: old)
        return try Library.load(DirStorage(dest))
    }

    private static func parentOf(_ dest: URL, _ why: String) throws -> URL {
        let absolute = dest.standardizedFileURL
        let parent = absolute.deletingLastPathComponent()
        if absolute.path == "/" || parent.path.isEmpty { throw ImportFailed(why) }
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        return parent
    }

    /** [input] written to [file] in pieces (opened here if the caller has not). */
    private static func copy(_ input: InputStream, to file: URL) throws {
        let manager = FileManager.default
        guard manager.createFile(atPath: file.path, contents: nil) else {
            throw ImportFailed("cannot write \(file.lastPathComponent)")
        }
        let out = try FileHandle(forWritingTo: file)
        defer { try? out.close() }
        if input.streamStatus == .notOpen { input.open() }
        let size = 64 * 1024
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: size)
        defer { buffer.deallocate() }
        while true {
            let read = input.read(buffer, maxLength: size)
            if read < 0 { throw ImportFailed("cannot read the zip: \(input.streamError?.localizedDescription ?? "read failed")") }
            if read == 0 { break }
            try out.write(contentsOf: Data(bytes: buffer, count: read))
        }
    }

    private static func extract(_ zipFile: URL, _ into: URL) throws {
        do {
            let zip = try ZipArchive(url: zipFile)
            // Names first, every one checked before anything is written.
            var chosen: [(ZipEntry, String)] = []
            for entry in zip.entries {
                var name = entry.path.replacingOccurrences(of: "\\", with: "/")
                while name.hasPrefix("/") { name.removeFirst() }
                if name.isEmpty || name.hasPrefix("__MACOSX/") { continue }
                // Zip slip: "../../shared_prefs/x" would otherwise write outside the library.
                let relative: String
                do { relative = try ZipArchive.safeRelativePath(name) } catch {
                    throw ImportFailed("the zip names a file outside the library: \(entry.path)")
                }
                chosen.append((entry, relative))
            }
            var total: Int64 = 0
            for (entry, relative) in chosen {
                let target = relative.isEmpty ? into : into.appendingPathComponent(relative)
                if entry.isDirectory || relative.isEmpty {
                    try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
                    continue
                }
                try zip.extract(entry, to: target, limit: UInt64(MAX_BYTES - total))
                total += Int64(entry.uncompressedSize)
            }
        } catch let error as ZipError {
            if case .tooLarge = error {
                throw ImportFailed("the zip unpacks to more than \(MAX_BYTES / 1_048_576) MB")
            }
            throw ImportFailed(error.description)
        }
    }

    /** The folder holding library.json: the top, or the one folder the zip wraps it in. */
    private static func findRoot(_ dir: URL) -> URL? {
        if isFile(dir.appendingPathComponent("library.json")) { return dir }
        let listed = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? []
        let folders = listed.filter { isDirectory($0) && $0.lastPathComponent != "__MACOSX" }
        guard folders.count == 1, isFile(folders[0].appendingPathComponent("library.json")) else { return nil }
        return folders[0]
    }

    static func isFile(_ url: URL) -> Bool {
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &directory) && !directory.boolValue
    }

    static func isDirectory(_ url: URL) -> Bool {
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &directory) && directory.boolValue
    }

    /** [Storage] over a folder: what an imported library is read through, on the phone as here. */
    public final class DirStorage: Storage {
        private let root: URL

        public init(_ root: URL) { self.root = root }

        private func at(_ path: String) -> URL { root.appendingPathComponent(path) }

        public func exists(_ path: String) -> Bool { FileManager.default.fileExists(atPath: at(path).path) }

        public func read(_ path: String) throws -> [UInt8] {
            do {
                return [UInt8](try Data(contentsOf: at(path)))
            } catch {
                throw PanimError.io("\(at(path).path) (No such file or directory)")
            }
        }

        /** The file's length; 0 when it is not there (File.length). */
        public func sizeOf(_ path: String) -> Int64 {
            let attributes = try? FileManager.default.attributesOfItem(atPath: at(path).path)
            return (attributes?[.size] as? NSNumber)?.int64Value ?? 0
        }

        public func open(_ path: String) throws -> InputStream {
            guard LibraryImport.isFile(at(path)), let stream = InputStream(url: at(path)) else {
                throw PanimError.io("\(at(path).path) (No such file or directory)")
            }
            return stream
        }

        public func file(_ path: String) -> URL? { at(path) }
    }
}
