// Tests for LibraryImport.swift and SavedLectures.swift: unpacking a phone-library zip, and the saved-lecture
// catalog, download and narration fetch against a local stand-in for Supabase (python3's http.server serving the
// REST and Storage paths SavedLectures asks for). Skipped where python3 is not installed.
import Foundation
import XCTest
@testable import PanimCore

final class SavedLecturesTests: XCTestCase {
    static let fixture = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().appendingPathComponent("player/fixtures/streamed-lecture")

    /** Everything the tests use: zips, the served folder, and where lectures are unpacked. */
    static var work: URL!
    static var server: Process?
    static var port = 0

    // The zips and the served folder, made with python's zipfile (deflate), as the harness makes them.
    static let setup = #"""
import json, os, shutil, sys, zipfile
fixture, work = sys.argv[1], sys.argv[2]
def files(root):
    for d, _, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(d, n)
            yield p, os.path.relpath(p, root).replace(os.sep, "/")
def zipped(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in entries:
            if src is None: z.writestr(name, b"x")
            else: z.write(src, name)
everything = list(files(fixture))
zipped(os.path.join(work, "full.zip"), [("library/" + rel, p) for p, rel in everything])
zipped(os.path.join(work, "flat.zip"), [(rel, p) for p, rel in everything])
zipped(os.path.join(work, "slip.zip"), [("library/library.json", os.path.join(fixture, "library.json")),
                                        ("../evil.txt", None)])
zipped(os.path.join(work, "empty.zip"), [("readme.txt", None)])
serve = os.path.join(work, "serve")
bucket = os.path.join(serve, "storage/v1/object/public/lectures")
# b1: saved as one zip without its narration, which sits beside it.
b1 = os.path.join(bucket, "builds/b1")
os.makedirs(os.path.join(b1, "audio"))
zipped(os.path.join(b1, "library.zip"), [("library/" + rel, p) for p, rel in everything if not rel.startswith("audio/")])
shutil.copy(os.path.join(fixture, "audio/GeneratedScene.ogg"), os.path.join(b1, "audio/GeneratedScene.ogg"))
# "b 2": saved file by file (no zip), assets in the shared folder, its narration never uploaded.
for p, rel in everything:
    if rel.startswith("audio/"): continue
    target = os.path.join(bucket, rel) if rel.startswith("assets/") else os.path.join(bucket, "builds/b 2", rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy(p, target)
rows = [
    {"build_id": "a2", "series": "Forces", "lecture": 2, "lectures": 2, "title": "Lecture 2: Friction",
     "minutes": 24.4, "library_path": "builds/b1", "library_bytes": 123456789012, "narrated": True,
     "saved_at": "2026-01-01T10:00:05Z", "frame_count": 0, "fps": 0, "subject": "physics"},
    {"build_id": "a1", "series": "Forces", "lecture": 1, "lectures": 2, "title": "Lecture 1: Push",
     "minutes": 0.5, "library_path": "builds/b1", "library_bytes": 10, "narrated": False,
     "saved_at": "2026-01-01T10:00:00Z", "frame_count": 900, "fps": 30},
    {"build_id": "c1", "series": "Waves", "lecture": 1, "lectures": 1, "title": "Lecture 1: ",
     "minutes": None, "library_path": "builds/b 2", "saved_at": "2026-02-01T00:00:00Z"},
    {"series": "no build id", "library_path": "x"},
    {"build_id": "no path"},
]
os.makedirs(os.path.join(serve, "rest/v1"))
with open(os.path.join(serve, "rest/v1/phone_lectures"), "w") as f: json.dump(rows, f)
"""#

    override class func setUp() {
        super.setUp()
        let base = ProcessInfo.processInfo.environment["PANIM_SAVED_SCRATCH"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.temporaryDirectory.appendingPathComponent("panim-saved-\(UUID().uuidString)")
        work = base
        try? FileManager.default.removeItem(at: base)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        guard let python = which("python3") else { return }
        let make = Process()
        make.executableURL = python
        make.arguments = ["-I", "-c", setup, fixture.path, base.path]
        guard (try? make.run()) != nil else { return }
        make.waitUntilExit()
        guard make.terminationStatus == 0 else { return }

        let serve = Process()
        serve.executableURL = python
        serve.arguments = ["-I", "-u", "-m", "http.server", "0", "--bind", "127.0.0.1",
                           "--directory", base.appendingPathComponent("serve").path]
        let out = Pipe()
        serve.standardOutput = out
        serve.standardError = FileHandle.nullDevice
        guard (try? serve.run()) != nil else { return }
        server = serve
        // "Serving HTTP on 127.0.0.1 port 41234 (http://127.0.0.1:41234/) ..."
        var text = ""
        let deadline = Date().addingTimeInterval(10)
        while port == 0 && Date() < deadline {
            let data = out.fileHandleForReading.availableData
            if data.isEmpty { break }
            text += String(decoding: data, as: UTF8.self)
            if let range = text.range(of: #"port (\d+)"#, options: .regularExpression) {
                port = Int(text[range].dropFirst(5)) ?? 0
            }
        }
    }

    override class func tearDown() {
        server?.terminate()
        server?.waitUntilExit()
        if ProcessInfo.processInfo.environment["PANIM_SAVED_SCRATCH"] == nil { try? FileManager.default.removeItem(at: work) }
        super.tearDown()
    }

    static func which(_ name: String) -> URL? {
        for dir in (ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin").split(separator: ":") {
            let url = URL(fileURLWithPath: String(dir)).appendingPathComponent(name)
            if FileManager.default.isExecutableFile(atPath: url.path) { return url }
        }
        return nil
    }

    private func zip(_ name: String) throws -> URL {
        let url = Self.work.appendingPathComponent(name)
        try XCTSkipUnless(FileManager.default.fileExists(atPath: url.path), "python3 could not make the zips")
        return url
    }

    private func project() throws -> SavedLectures.Project {
        try XCTSkipUnless(Self.port > 0, "no local http server")
        return SavedLectures.Project(url: "  http://127.0.0.1:\(Self.port)//\n", anonKey: "sb_publishable_test")
    }

    private func fresh(_ name: String) -> URL {
        let dir = Self.work.appendingPathComponent("out-\(name)-\(UUID().uuidString.prefix(8))", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("lecture", isDirectory: true)
    }

    private func leftovers(_ dest: URL) -> [String] {
        let parent = dest.deletingLastPathComponent()
        return ((try? FileManager.default.contentsOfDirectory(atPath: parent.path)) ?? []).filter { $0 != "lecture" }.sorted()
    }

    // ---- LibraryImport ------------------------------------------------------------------------------------------

    func testUnpackChecksAndReplaces() throws {
        let dest = fresh("unpack")
        for name in ["full.zip", "flat.zip", "full.zip"] { // a second import replaces the first
            let input = try XCTUnwrap(InputStream(url: try zip(name)))
            input.open()
            let library = try LibraryImport.unpack(input, dest)
            input.close()
            XCTAssertEqual(library.scenes.map { $0.name }, ["GeneratedScene"])
            XCTAssertEqual(library.missing(), [])
            XCTAssertEqual(try library.checkIntegrity(verifyDigests: true).map { $0.description }, [])
            XCTAssertTrue(FileManager.default.fileExists(atPath: dest.appendingPathComponent("library.json").path))
            XCTAssertEqual(leftovers(dest), [], "staging, spool and .old are cleaned up")
        }
        // An unopened stream is opened for the caller.
        let reopened = try LibraryImport.unpack(try XCTUnwrap(InputStream(url: try zip("full.zip"))), dest)
        XCTAssertNotNil(LibraryImport.DirStorage(dest).file("library.json"))
        let frames = try reopened.open("GeneratedScene")
        XCTAssertGreaterThan(frames.frameCount, 0)
    }

    func testZipSlipIsRefused() throws {
        let dest = fresh("slip")
        XCTAssertThrowsError(try LibraryImport.unpack(try XCTUnwrap(InputStream(url: try zip("slip.zip"))), dest)) {
            XCTAssertEqual(($0 as? LibraryImport.ImportFailed)?.message,
                           "the zip names a file outside the library: ../evil.txt")
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: dest.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: dest.deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("evil.txt").path))
        XCTAssertEqual(leftovers(dest), [])
    }

    func testNotALibrary() throws {
        let dest = fresh("empty")
        XCTAssertThrowsError(try LibraryImport.unpack(try XCTUnwrap(InputStream(url: try zip("empty.zip"))), dest)) {
            XCTAssertEqual("\($0)", "the zip has no library.json: not a phone library")
        }
        XCTAssertThrowsError(try LibraryImport.unpack(InputStream(data: Data("not a zip".utf8)), dest))
        XCTAssertEqual(leftovers(dest), [])
    }

    func testInstallRefusesADamagedLibrary() throws {
        let dest = fresh("damaged")
        let root = dest.deletingLastPathComponent().appendingPathComponent("staged", isDirectory: true)
        try FileManager.default.copyItem(at: Self.fixture, to: root)
        let atlas = root.appendingPathComponent("library.atlas")
        var bytes = try Data(contentsOf: atlas)
        bytes[0] ^= 0xFF
        try bytes.write(to: atlas)
        XCTAssertThrowsError(try LibraryImport.install(root, dest)) {
            XCTAssertTrue("\($0)".hasPrefix("the library is incomplete: library.atlas: digest "), "\($0)")
        }
        try FileManager.default.removeItem(at: root.appendingPathComponent("scenes/GeneratedScene.panim"))
        XCTAssertThrowsError(try LibraryImport.install(root, dest)) {
            XCTAssertEqual("\($0)", "the library is missing 1 file(s), e.g. scenes/GeneratedScene.panim")
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: dest.path))
    }

    // ---- SavedLectures ------------------------------------------------------------------------------------------

    func testEntryAndProgressText() {
        let e = SavedLectures.Entry(buildId: "b", series: "Forces", lecture: 2, lectures: 3, title: "Lecture 2: Friction",
                                    minutes: 23.5, libraryPath: "p", libraryBytes: 1, narrated: true, savedAt: "")
        XCTAssertEqual(e.shortTitle, "Friction")
        XCTAssertEqual(e.label, "Forces · Lecture 2 of 3: Friction (24 min)")
        XCTAssertEqual(e.seconds, 23.5 * 60)
        let one = SavedLectures.Entry(buildId: "b", series: "Waves", lecture: 1, lectures: 1, title: "Lecture 1:  ",
                                      minutes: 0.2, libraryPath: "p", libraryBytes: 1, narrated: false, savedAt: "",
                                      frameCount: 300, fps: 30, subject: "")
        XCTAssertEqual(one.shortTitle, "Waves")
        XCTAssertEqual(one.label, "Waves: " + " (under 1 min)")
        XCTAssertEqual(one.seconds, 10)
        XCTAssertEqual("\(SavedLectures.Progress(1_572_864, 10_485_760, "bytes"))", "1.5 of 10.0 MB")
        XCTAssertEqual("\(SavedLectures.Progress(3, 8, "files"))", "3 of 8 files")
        XCTAssertEqual(SavedLectures.Project(url: " https://x.supabase.co/ ", anonKey: "k").url, "https://x.supabase.co")
    }

    func testUrls() throws {
        let p = SavedLectures.Project(url: "https://x.supabase.co", anonKey: "k")
        let e = SavedLectures.Entry(buildId: "b", series: "s", lecture: 1, lectures: 1, title: "", minutes: nil,
                                    libraryPath: "builds/b 2/", libraryBytes: 0, narrated: false, savedAt: "")
        XCTAssertEqual(SavedLectures.narrationUrl(p, e, "audio/Scène 1+2.ogg"),
                       "https://x.supabase.co/storage/v1/object/public/lectures/builds/b%202/audio/Sc%C3%A8ne%201%2B2.ogg")
        XCTAssertEqual(SavedLectures.RemoteStorage(p, "builds/b").url("assets/ab.panm"),
                       "https://x.supabase.co/storage/v1/object/public/lectures/assets/ab.panm")
    }

    func testCatalog() throws {
        let entries = try SavedLectures.catalog(try project())
        // Newest series first (Waves), each series' videos in order; rows without a build id or path dropped.
        XCTAssertEqual(entries.map { $0.buildId }, ["c1", "a1", "a2"])
        let waves = entries[0]
        XCTAssertEqual(waves.series, "Waves")
        XCTAssertNil(waves.minutes)
        XCTAssertNil(waves.seconds)
        XCTAssertEqual(waves.shortTitle, "Waves")
        XCTAssertEqual(waves.libraryBytes, 0)
        XCTAssertFalse(waves.narrated)
        let a1 = entries[1], a2 = entries[2]
        XCTAssertEqual(a1.seconds, 30)
        XCTAssertEqual(a1.label, "Forces · Lecture 1 of 2: Push (under 1 min)")
        XCTAssertEqual(a2.minutes, 24.4)
        XCTAssertEqual(a2.libraryBytes, 123_456_789_012)
        XCTAssertTrue(a2.narrated)
        XCTAssertEqual(a2.subject, "physics")
        XCTAssertEqual(a2.savedAt, "2026-01-01T10:00:05Z")
        XCTAssertEqual(a2.label, "Forces · Lecture 2 of 2: Friction (24 min)")
    }

    func testCatalogUnreachable() {
        let p = SavedLectures.Project(url: "http://127.0.0.1:1", anonKey: "k")
        XCTAssertThrowsError(try SavedLectures.catalog(p))
    }

    func testDownloadOneZipThenNarration() throws {
        let p = try project()
        let entry = try XCTUnwrap(try SavedLectures.catalog(p).first { $0.buildId == "a2" })
        let dest = fresh("zip")
        var seen: [SavedLectures.Progress] = []
        let library = try SavedLectures.download(p, entry, dest) { seen.append($0) }
        XCTAssertEqual(library.scenes.map { $0.name }, ["GeneratedScene"])
        XCTAssertEqual(try library.checkIntegrity(verifyDigests: true).count, 0)
        XCTAssertEqual(seen.last?.unit, "bytes")
        XCTAssertEqual(seen.last?.done, seen.last?.total)
        XCTAssertGreaterThan(seen.last?.total ?? 0, 0)
        XCTAssertEqual(leftovers(dest), [])

        let audio = try XCTUnwrap(library.scenes[0].audio)
        let target = dest.appendingPathComponent(audio)
        XCTAssertFalse(FileManager.default.fileExists(atPath: target.path), "the zip leaves the narration out")
        // Cancelled before it starts: nothing kept.
        XCTAssertFalse(try SavedLectures.fetchNarration(p, entry, audio, dest, cancelled: { true }))
        XCTAssertFalse(FileManager.default.fileExists(atPath: target.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: target.path + ".part"))

        var told: [SavedLectures.Progress] = []
        XCTAssertTrue(try SavedLectures.fetchNarration(p, entry, audio, dest, progress: { told.append($0) }))
        let original = try Data(contentsOf: Self.fixture.appendingPathComponent(audio))
        XCTAssertEqual(try Data(contentsOf: target), original)
        XCTAssertEqual(told.last?.done, Int64(original.count))
        XCTAssertEqual(told.last?.total, Int64(original.count))
        XCTAssertGreaterThanOrEqual(told.count, 2, "progress every 256 KB and at the end")
        XCTAssertFalse(FileManager.default.fileExists(atPath: target.path + ".part"))
        // Kept: no second fetch.
        XCTAssertTrue(try SavedLectures.fetchNarration(p, entry, audio, dest, cancelled: { true }))
        // Not uploaded: false, not an error.
        XCTAssertFalse(try SavedLectures.fetchNarration(p, entry, "audio/Nothing.ogg", dest))
        // The downloaded library, with its narration, reads through DirStorage as the app does.
        let reread = try Library.load(LibraryImport.DirStorage(dest))
        XCTAssertEqual(try reread.checkIntegrity(verifyDigests: true).count, 0)
    }

    func testDownloadFileByFile() throws {
        let p = try project()
        let entry = try XCTUnwrap(try SavedLectures.catalog(p).first { $0.buildId == "c1" })
        let dest = fresh("files")
        let lock = NSLock()
        var seen: [SavedLectures.Progress] = []
        let library = try SavedLectures.download(p, entry, dest) { progress in
            lock.lock()
            seen.append(progress)
            lock.unlock()
        }
        XCTAssertEqual(library.missing(), [])
        XCTAssertEqual(try library.checkIntegrity(verifyDigests: true).count, 0)
        XCTAssertTrue(seen.allSatisfy { $0.unit == "files" })
        let total = try XCTUnwrap(seen.first?.total)
        XCTAssertEqual(seen.count, Int(total))
        XCTAssertEqual(Set(seen.map { $0.done }), Set(1...total))
        // Its narration was never uploaded: the lecture downloads without it.
        XCTAssertFalse(FileManager.default.fileExists(atPath: dest.appendingPathComponent("audio/GeneratedScene.ogg").path))
        XCTAssertEqual(leftovers(dest), [])
    }

    func testDownloadOfNothingFails() throws {
        let p = try project()
        let entry = SavedLectures.Entry(buildId: "z", series: "s", lecture: 1, lectures: 1, title: "", minutes: nil,
                                        libraryPath: "builds/none", libraryBytes: 0, narrated: false, savedAt: "")
        let dest = fresh("none")
        XCTAssertThrowsError(try SavedLectures.download(p, entry, dest)) {
            XCTAssertTrue("\($0)".hasPrefix("HTTP 404 from http://127.0.0.1:"), "\($0)")
        }
        XCTAssertEqual(leftovers(dest), [])
    }
}
