// Reading a zip file, for importing a phone library (player/core LibraryImport.kt, which uses ZipInputStream).
//
// Read through the central directory, the zip's own index, rather than front to back: the import has the file on
// the phone, and the directory gives every entry's sizes even where the local header defers them to a data
// descriptor (bit 3). Zip64 sizes and offsets are understood. Entries are stored (0) or deflated (8; Inflater).
// Each entry is streamed to its file in pieces and checked against its CRC-32 and size. Paths that would land
// outside the destination ("../", absolute) are refused, and the total unpacked can be capped against a zip bomb.
// Foundation only, so it builds and is tested on Linux.

import Foundation

public enum ZipError: Error, Equatable, CustomStringConvertible {
    case notZip(String)
    case corrupt(String)
    case unsupported(String)
    /// A name that would land outside the folder unpacked into.
    case unsafePath(String)
    /// The zip unpacks to more than the limit given.
    case tooLarge(UInt64)
    case io(String)

    public var description: String {
        switch self {
        case .notZip(let why): return "not a zip file: \(why)"
        case .corrupt(let why): return "the zip is damaged: \(why)"
        case .unsupported(let why): return "the zip uses \(why), which cannot be read"
        case .unsafePath(let name): return "the zip names a file outside the library: \(name)"
        case .tooLarge(let limit): return "the zip unpacks to more than \(limit / 1_048_576) MB"
        case .io(let why): return why
        }
    }
}

/// One file or folder in the zip, from the central directory.
public struct ZipEntry: Equatable {
    /// The name as stored (`/`-separated; may be unsafe -- see ZipArchive.safeRelativePath).
    public let path: String
    public let method: UInt16
    public let flags: UInt16
    public let crc32: UInt32
    public let compressedSize: UInt64
    public let uncompressedSize: UInt64
    public let localHeaderOffset: UInt64

    public var isDirectory: Bool { path.hasSuffix("/") || path.hasSuffix("\\") }
}

public final class ZipArchive {
    public let url: URL
    public let entries: [ZipEntry]
    private let handle: FileHandle
    private let fileSize: UInt64

    /// Pieces read from the file at a time.
    private static let chunk = 64 * 1024

    public init(url: URL) throws {
        self.url = url
        do {
            handle = try FileHandle(forReadingFrom: url)
            fileSize = try handle.seekToEnd()
        } catch {
            throw ZipError.io("cannot open \(url.lastPathComponent): \(error.localizedDescription)")
        }
        entries = try Self.readDirectory(handle, fileSize: fileSize)
    }

    deinit { try? handle.close() }

    // MARK: paths

    /// [name] as a path relative to the folder unpacked into, `.` and empty parts dropped and `..` resolved; throws
    /// when it is absolute (`/x`, `\x`, `C:`) or climbs out of the folder. Backslashes count as separators, as
    /// LibraryImport.kt treats them.
    public static func safeRelativePath(_ name: String) throws -> String {
        let unified = name.replacingOccurrences(of: "\\", with: "/")
        if unified.hasPrefix("/") || unified.contains("\0") { throw ZipError.unsafePath(name) }
        if let first = unified.split(separator: "/").first, first.contains(":") { throw ZipError.unsafePath(name) }
        var parts: [Substring] = []
        for part in unified.split(separator: "/", omittingEmptySubsequences: true) {
            switch part {
            case ".": continue
            case "..":
                guard !parts.isEmpty else { throw ZipError.unsafePath(name) }
                parts.removeLast()
            default: parts.append(part)
            }
        }
        return parts.joined(separator: "/")
    }

    // MARK: extraction

    /// Stream [entry]'s contents to [sink] in pieces, checked against its size and CRC-32. Throws tooLarge when it
    /// would pass [limit] bytes (the sizes in the zip are not trusted for that).
    public func extract(_ entry: ZipEntry, limit: UInt64 = .max, to sink: ([UInt8]) throws -> Void) throws {
        if entry.flags & 1 != 0 { throw ZipError.unsupported("encryption (\(entry.path))") }
        let start = try dataOffset(entry)
        guard start + entry.compressedSize <= fileSize else { throw ZipError.corrupt("\(entry.path) runs past the end") }
        var crc = CRC32()
        var total: UInt64 = 0
        func deliver(_ piece: [UInt8]) throws {
            total += UInt64(piece.count)
            if total > limit { throw ZipError.tooLarge(limit) }
            if total > entry.uncompressedSize { throw ZipError.corrupt("\(entry.path) is longer than it says") }
            crc.update(piece)
            try sink(piece)
        }
        var at = start
        let end = start + entry.compressedSize
        let read: () throws -> [UInt8]? = { [handle] in
            guard at < end else { return nil }
            let n = Int(min(UInt64(Self.chunk), end - at))
            let piece = try Self.read(handle, at: at, count: n)
            guard piece.count == n else { throw ZipError.corrupt("\(entry.path) is cut short") }
            at += UInt64(n)
            return piece
        }
        switch entry.method {
        case 0:
            while let piece = try read() { try deliver(piece) }
        case 8:
            do {
                try Inflater(pull: read).run(deliver)
            } catch let error as InflateError {
                throw ZipError.corrupt("\(entry.path): \(error.description)")
            }
        default:
            throw ZipError.unsupported("compression method \(entry.method) (\(entry.path))")
        }
        guard total == entry.uncompressedSize else { throw ZipError.corrupt("\(entry.path) is shorter than it says") }
        guard crc.value == entry.crc32 else { throw ZipError.corrupt("\(entry.path) fails its CRC check") }
    }

    /// [entry] written to [file] (parent folders made), streamed. A file that fails its check is removed.
    public func extract(_ entry: ZipEntry, to file: URL, limit: UInt64 = .max) throws {
        let manager = FileManager.default
        try manager.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        guard manager.createFile(atPath: file.path, contents: nil) else {
            throw ZipError.io("cannot create \(file.lastPathComponent)")
        }
        let out = try FileHandle(forWritingTo: file)
        do {
            try extract(entry, limit: limit) { try out.write(contentsOf: Data($0)) }
            try out.close()
        } catch {
            try? out.close()
            try? manager.removeItem(at: file)
            throw error
        }
    }

    /// [entry]'s contents in memory (small entries: a manifest).
    public func data(_ entry: ZipEntry, limit: UInt64 = .max) throws -> Data {
        var data = Data()
        try extract(entry, limit: limit) { data.append(contentsOf: $0) }
        return data
    }

    /// The entry named [path] (exactly as stored), if there is one.
    public func entry(_ path: String) -> ZipEntry? { entries.first { $0.path == path } }

    /// Every entry unpacked under [directory], folders made, as LibraryImport.extract does. Entries [skip] says
    /// yes to are left out (LibraryImport drops `__MACOSX/`). Throws unsafePath for a name outside [directory],
    /// before anything is written, and tooLarge when the whole would pass [maxTotalBytes]. Returns the files written.
    @discardableResult
    public func extractAll(to directory: URL, maxTotalBytes: UInt64 = .max,
                           skip: (ZipEntry) -> Bool = { _ in false }) throws -> [URL] {
        let chosen = try entries.filter { !skip($0) }.map { ($0, try Self.safeRelativePath($0.path)) }
        var written: [URL] = []
        var total: UInt64 = 0
        for (entry, relative) in chosen where !relative.isEmpty {
            let target = directory.appendingPathComponent(relative)
            if entry.isDirectory {
                try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
                continue
            }
            try extract(entry, to: target, limit: maxTotalBytes - total)
            total += entry.uncompressedSize
            written.append(target)
        }
        return written
    }

    // MARK: reading the directory

    private func dataOffset(_ entry: ZipEntry) throws -> UInt64 {
        let header = try Self.read(handle, at: entry.localHeaderOffset, count: 30)
        guard header.count == 30, le32(header, 0) == 0x0403_4B50 else {
            throw ZipError.corrupt("no local header for \(entry.path)")
        }
        return entry.localHeaderOffset + 30 + UInt64(le16(header, 26)) + UInt64(le16(header, 28))
    }

    private static func read(_ handle: FileHandle, at offset: UInt64, count: Int) throws -> [UInt8] {
        do {
            try handle.seek(toOffset: offset)
            return [UInt8](try handle.read(upToCount: count) ?? Data())
        } catch {
            throw ZipError.io("cannot read the zip: \(error.localizedDescription)")
        }
    }

    private static func readDirectory(_ handle: FileHandle, fileSize: UInt64) throws -> [ZipEntry] {
        guard fileSize >= 22 else { throw ZipError.notZip("too short") }
        // The end record is the last thing in the file but for a comment of up to 65535 bytes.
        let tailSize = Int(min(fileSize, 22 + 65535))
        let tailStart = fileSize - UInt64(tailSize)
        let tail = try read(handle, at: tailStart, count: tailSize)
        var eocd = -1
        var i = tail.count - 22
        while i >= 0 {
            if tail[i] == 0x50 && le32(tail, i) == 0x0605_4B50 && i + 22 + Int(le16(tail, i + 20)) <= tail.count {
                eocd = i
                break
            }
            i -= 1
        }
        guard eocd >= 0 else { throw ZipError.notZip("no end of central directory") }
        var count = UInt64(le16(tail, eocd + 10))
        var size = UInt64(le32(tail, eocd + 12))
        var offset = UInt64(le32(tail, eocd + 16))
        if le16(tail, eocd + 4) != 0 || le16(tail, eocd + 6) != 0 { throw ZipError.unsupported("multiple disks") }

        // Zip64: a locator just before the end record points at a larger one.
        // Data before the zip (a self-extractor's stub, a prefix) shifts every offset by the same amount: where
        // the directory really ends -- at the end record -- against where it says it starts.
        var shift: UInt64 = 0
        let eocdAt = tailStart + UInt64(eocd)
        if eocdAt >= size, eocdAt - size > offset { shift = eocdAt - size - offset }
        if count == 0xFFFF || size == 0xFFFF_FFFF || offset == 0xFFFF_FFFF, eocd >= 20,
           le32(tail, eocd - 20) == 0x0706_4B50 {
            let at = le64(tail, eocd - 20 + 8)
            let record = try read(handle, at: at, count: 56)
            guard record.count == 56, le32(record, 0) == 0x0606_4B50 else {
                throw ZipError.corrupt("no zip64 end record")
            }
            count = le64(record, 32)
            size = le64(record, 40)
            offset = le64(record, 48)
            shift = 0
        }
        offset += shift
        guard offset + size <= fileSize, size < UInt64(Int32.max) else {
            throw ZipError.corrupt("the central directory is outside the file")
        }
        let directory = try read(handle, at: offset, count: Int(size))
        var entries: [ZipEntry] = []
        var p = 0
        for _ in 0..<count {
            guard p + 46 <= directory.count, le32(directory, p) == 0x0201_4B50 else {
                throw ZipError.corrupt("central directory entry \(entries.count)")
            }
            let flags = le16(directory, p + 8)
            let method = le16(directory, p + 10)
            let crc = le32(directory, p + 16)
            var compressed = UInt64(le32(directory, p + 20))
            var uncompressed = UInt64(le32(directory, p + 24))
            let nameLength = Int(le16(directory, p + 28))
            let extraLength = Int(le16(directory, p + 30))
            let commentLength = Int(le16(directory, p + 32))
            var local = UInt64(le32(directory, p + 42))
            let nameStart = p + 46
            let extraStart = nameStart + nameLength
            let next = extraStart + extraLength + commentLength
            guard next <= directory.count else { throw ZipError.corrupt("central directory entry \(entries.count)") }
            let nameBytes = Array(directory[nameStart..<extraStart])
            // Bit 11 says UTF-8; otherwise CP437, which for the ASCII names a library has is the same.
            let name = String(bytes: nameBytes, encoding: .utf8) ?? String(decoding: nameBytes, as: UTF8.self)

            var e = extraStart
            while e + 4 <= extraStart + extraLength {
                let id = le16(directory, e)
                let len = Int(le16(directory, e + 2))
                var f = e + 4
                let fieldEnd = min(f + len, extraStart + extraLength)
                if id == 0x0001 {
                    if uncompressed == 0xFFFF_FFFF, f + 8 <= fieldEnd { uncompressed = le64(directory, f); f += 8 }
                    if compressed == 0xFFFF_FFFF, f + 8 <= fieldEnd { compressed = le64(directory, f); f += 8 }
                    if local == 0xFFFF_FFFF, f + 8 <= fieldEnd { local = le64(directory, f); f += 8 }
                }
                e += 4 + len
            }
            entries.append(ZipEntry(path: name, method: method, flags: flags, crc32: crc,
                                    compressedSize: compressed, uncompressedSize: uncompressed,
                                    localHeaderOffset: local + shift))
            p = next
        }
        return entries
    }
}

@inline(__always) private func le16(_ b: [UInt8], _ i: Int) -> UInt16 { UInt16(b[i]) | UInt16(b[i + 1]) << 8 }
@inline(__always) private func le32(_ b: [UInt8], _ i: Int) -> UInt32 {
    UInt32(b[i]) | UInt32(b[i + 1]) << 8 | UInt32(b[i + 2]) << 16 | UInt32(b[i + 3]) << 24
}
@inline(__always) private func le64(_ b: [UInt8], _ i: Int) -> UInt64 { UInt64(le32(b, i)) | UInt64(le32(b, i + 4)) << 32 }
