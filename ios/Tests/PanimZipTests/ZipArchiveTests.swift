import Foundation
import XCTest
@testable import PanimZip

final class InflateTests: XCTestCase {
    func testCRC32() {
        XCTAssertEqual(CRC32.checksum(Array("123456789".utf8)), 0xCBF4_3926)
        XCTAssertEqual(CRC32.checksum([]), 0)
    }

    // Hand-made streams: a stored block, and the fixed-Huffman "a" * 3 with a back-reference (zlib -15 output).
    func testSmallStreams() throws {
        XCTAssertEqual(try Inflater.inflate([0x01, 0x03, 0x00, 0xFC, 0xFF, 0x61, 0x62, 0x63]), Array("abc".utf8))
        // python: zlib.compressobj(9, zlib.DEFLATED, -15) of b"abcabcabcabcabc"
        XCTAssertEqual(try Inflater.inflate([0x4B, 0x4C, 0x4A, 0x4E, 0x44, 0x42, 0x00]), Array("abcabcabcabcabc".utf8))
        XCTAssertEqual(try Inflater.inflate([0x03, 0x00]), [])
        XCTAssertThrowsError(try Inflater.inflate([0x4B, 0x4C, 0x4A])) { XCTAssertEqual($0 as? InflateError, .truncated) }
        XCTAssertThrowsError(try Inflater.inflate([0x07]))           // block type 3
        XCTAssertThrowsError(try Inflater.inflate([0x01, 0x03, 0x00, 0x00, 0x00, 0x61]))   // bad NLEN
    }

    func testSafePaths() throws {
        XCTAssertEqual(try ZipArchive.safeRelativePath("library/scenes/a.panm"), "library/scenes/a.panm")
        XCTAssertEqual(try ZipArchive.safeRelativePath("a/./b//c"), "a/b/c")
        XCTAssertEqual(try ZipArchive.safeRelativePath("a/../b"), "b")
        XCTAssertEqual(try ZipArchive.safeRelativePath("a\\b"), "a/b")
        for bad in ["../x", "a/../../x", "/etc/passwd", "\\x", "C:/x", "c:x", "..", "a/b/../../.."] {
            XCTAssertThrowsError(try ZipArchive.safeRelativePath(bad), bad) {
                XCTAssertEqual($0 as? ZipError, .unsafePath(bad))
            }
        }
    }
}

#if os(macOS) || os(Linux)
/// Zips made by Python's zipfile, unpacked here and compared byte for byte with what went in.
final class ZipArchiveTests: XCTestCase {
    private var dir: URL!

    override func setUpWithError() throws {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent("panimzip-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let script = dir.appendingPathComponent("make.py")
        try Self.script.write(to: script, atomically: true, encoding: .utf8)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "-I", script.path, dir.path]
        do { try process.run() } catch { throw XCTSkip("python3 is not available: \(error)") }
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw XCTSkip("python3 could not make the zips") }
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dir)
    }

    private func checkUnpacks(_ name: String, method: UInt16? = nil) throws {
        let zip = try ZipArchive(url: dir.appendingPathComponent(name))
        let source = dir.appendingPathComponent("src")
        let out = dir.appendingPathComponent("out-\(name)")
        let files = try zip.extractAll(to: out)
        let expected = ["library/random.bin", "library/text.txt", "library/empty.txt", "library/scenes/Ünïcode.json",
                        "library/small.txt"]
        XCTAssertEqual(Set(files.map { String($0.path.dropFirst(out.path.count + 1)) }), Set(expected))
        for path in expected {
            let a = try Data(contentsOf: source.appendingPathComponent(path))
            let b = try Data(contentsOf: out.appendingPathComponent(path))
            XCTAssertEqual(a.count, b.count, path)
            XCTAssertTrue(a == b, "\(path) differs")
        }
        if let method {
            XCTAssertTrue(zip.entries.filter { !$0.isDirectory && $0.uncompressedSize > 0 }.allSatisfy { $0.method == method })
        }
        XCTAssertTrue(zip.entries.contains { $0.isDirectory })
        let manifest = try XCTUnwrap(zip.entry("library/small.txt"))
        XCTAssertEqual(String(decoding: try zip.data(manifest), as: UTF8.self), "library manifest\n")
    }

    func testDeflated() throws { try checkUnpacks("deflated.zip", method: 8) }
    func testDeflatedFast() throws { try checkUnpacks("fast.zip", method: 8) }
    func testStored() throws { try checkUnpacks("stored.zip", method: 0) }
    func testZip64() throws { try checkUnpacks("zip64.zip") }
    func testDataDescriptors() throws {
        try checkUnpacks("streamed.zip", method: 8)
        let zip = try ZipArchive(url: dir.appendingPathComponent("streamed.zip"))
        XCTAssertTrue(zip.entries.contains { $0.flags & 8 != 0 })
    }

    func testCommentedAndPrefixed() throws {
        let zip = try ZipArchive(url: dir.appendingPathComponent("commented.zip"))
        XCTAssertEqual(zip.entries.count, 1)
        XCTAssertEqual(try zip.data(zip.entries[0]), Data("hello\n".utf8))
    }

    func testRefusesTraversalBeforeWriting() throws {
        let zip = try ZipArchive(url: dir.appendingPathComponent("evil.zip"))
        let out = dir.appendingPathComponent("evil-out")
        XCTAssertThrowsError(try zip.extractAll(to: out)) { XCTAssertEqual($0 as? ZipError, .unsafePath("../evil.txt")) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: out.appendingPathComponent("ok.txt").path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: dir.appendingPathComponent("evil.txt").path))
    }

    func testLimitAndCorruption() throws {
        let zip = try ZipArchive(url: dir.appendingPathComponent("deflated.zip"))
        XCTAssertThrowsError(try zip.extractAll(to: dir.appendingPathComponent("capped"), maxTotalBytes: 1_000_000)) {
            XCTAssertEqual($0 as? ZipError, .tooLarge(1_000_000))
        }
        // Flip a byte inside the text entry's compressed data: the inflater or the CRC must catch it.
        let url = dir.appendingPathComponent("deflated.zip")
        var bytes = try Data(contentsOf: url)
        let text = try XCTUnwrap(zip.entry("library/text.txt"))
        let middle = Int(text.localHeaderOffset) + 30 + text.path.utf8.count + Int(text.compressedSize / 2)
        bytes[middle] ^= 0x55
        let broken = dir.appendingPathComponent("broken.zip")
        try bytes.write(to: broken)
        let damaged = try ZipArchive(url: broken)
        let target = dir.appendingPathComponent("broken-out.txt")
        XCTAssertThrowsError(try damaged.extract(try XCTUnwrap(damaged.entry("library/text.txt")), to: target))
        XCTAssertFalse(FileManager.default.fileExists(atPath: target.path))
        XCTAssertThrowsError(try ZipArchive(url: dir.appendingPathComponent("make.py")))
    }

    private static let script = #"""
import io, os, random, sys, zipfile
root = sys.argv[1]
src = os.path.join(root, "src")
rng = random.Random(1234)
files = {
    "library/random.bin": bytes(rng.getrandbits(8) for _ in range(3 * 1024 * 1024 + 17)),
    "library/text.txt": "".join(
        rng.choice(["frame ", "scene ", "the ", "narration ", "keyframe\n", "0.25 ", "path M 1 2 L 3 4\n"])
        for _ in range(900_000)).encode(),
    "library/empty.txt": b"",
    "library/scenes/Ünïcode.json": ('{"name": "Ünïcode", "n": [%s]}' % ",".join(str(i) for i in range(5000))).encode(),
    "library/small.txt": b"library manifest\n",
}
for name, data in files.items():
    path = os.path.join(src, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)

def make(name, method, level=None, force64=False):
    with zipfile.ZipFile(os.path.join(root, name), "w", method, compresslevel=level) as z:
        z.writestr("library/", b"")
        for n, d in files.items():
            if force64:
                with z.open(zipfile.ZipInfo(n), "w", force_zip64=True) as f:
                    f.write(d)
            else:
                info = zipfile.ZipInfo(n)
                info.compress_type = method
                z.writestr(info, d, compress_type=method, compresslevel=level)

make("deflated.zip", zipfile.ZIP_DEFLATED, 9)
make("fast.zip", zipfile.ZIP_DEFLATED, 1)
make("stored.zip", zipfile.ZIP_STORED)
make("zip64.zip", zipfile.ZIP_DEFLATED, 6, force64=True)

class Unseekable(io.RawIOBase):
    def __init__(self, f): self.f = f
    def writable(self): return True
    def write(self, b): return self.f.write(b)
with open(os.path.join(root, "streamed.zip"), "wb") as raw:
    with zipfile.ZipFile(Unseekable(raw), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("library/", b"")
        for n, d in files.items():
            with z.open(n, "w") as f:
                f.write(d)

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("hello.txt", b"hello\n")
    z.comment = b"a comment " * 50
open(os.path.join(root, "commented.zip"), "wb").write(b"#!prefix\n" + buf.getvalue())

with zipfile.ZipFile(os.path.join(root, "evil.zip"), "w") as z:
    z.writestr("ok.txt", b"fine")
    z.writestr("../evil.txt", b"escaped")
"""#
}
#endif
