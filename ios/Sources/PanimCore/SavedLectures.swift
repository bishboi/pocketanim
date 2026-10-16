// Ported from player/core/src/main/kotlin/com/pocketanim/core/SavedLectures.kt.
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/**
 * The lectures saved from the harness (its Save button), as the player finds and fetches them.
 *
 * Saving puts each video's phone library in Supabase Storage, in the public bucket `lectures` --
 * builds/<build id>/library.json and the rest, the assets content-addressed once at assets/<digest>.panm -- and
 * lists it in the view `phone_lectures` (harness/supabase/migrations/0002_saved_lectures.sql). The player reads
 * that list through the project's REST API with its anon key, and downloads a lecture's files into app storage,
 * where it plays offline like an imported one (LibraryImport.install checks every file first).
 *
 * Blocking, as the Kotlin is (java.net): URLSession underneath, waited on, so call it off the main thread.
 */
public enum SavedLectures {

    /** The Supabase project: its URL (https://<ref>.supabase.co) and its anon (public) key. */
    public final class Project {
        public let url: String
        public let anonKey: String

        public init(url: String, anonKey: String) {
            var trimmed = kTrim(url)
            while trimmed.hasSuffix("/") { trimmed.removeLast() }
            self.url = trimmed
            self.anonKey = anonKey
        }
    }

    /** One saved video, as the catalog lists it. */
    public final class Entry {
        public let buildId: String
        public let series: String
        public let lecture: Int
        public let lectures: Int
        public let title: String
        public let minutes: Double?
        public let libraryPath: String
        public let libraryBytes: Int64
        public let narrated: Bool
        public let savedAt: String
        /** The video's length, when the catalog has it: frames at [fps]. */
        public let frameCount: Int
        public let fps: Int
        public let subject: String

        public init(
            buildId: String, series: String, lecture: Int, lectures: Int, title: String, minutes: Double?,
            libraryPath: String, libraryBytes: Int64, narrated: Bool, savedAt: String, frameCount: Int = 0,
            fps: Int = 0, subject: String = ""
        ) {
            self.buildId = buildId
            self.series = series
            self.lecture = lecture
            self.lectures = lectures
            self.title = title
            self.minutes = minutes
            self.libraryPath = libraryPath
            self.libraryBytes = libraryBytes
            self.narrated = narrated
            self.savedAt = savedAt
            self.frameCount = frameCount
            self.fps = fps
            self.subject = subject
        }

        /** Its length in seconds: from the frames when known, else the minutes the harness estimated. */
        public var seconds: Double? {
            if frameCount > 0 && fps > 0 { return Double(frameCount) / Double(fps) }
            return minutes.map { $0 * 60 }
        }

        /** The lecture's own title, without the series or "Lecture n:". */
        public var shortTitle: String {
            let name = Entry.withoutNumber(title)
            return kTrim(name).isEmpty ? series : name
        }

        /** What the picker shows: "Forces · Lecture 2 of 3: Friction (24 min)". */
        public var label: String {
            var out = series
            let name = Entry.withoutNumber(title)
            if lectures > 1 { out += " · Lecture \(lecture) of \(lectures): \(name)" } else if name != series { out += ": \(name)" }
            if let m = minutes { out += m < 1 ? " (under 1 min)" : " (\(javaRound(m)) min)" }
            return out
        }

        /** `title.replace(Regex("^Lecture \\d+:\\s*"), "")`, with Java's ASCII \d and \s. */
        static func withoutNumber(_ title: String) -> String {
            guard let range = title.range(of: "^Lecture [0-9]+:[ \\t\\n\\x0B\\f\\r]*", options: .regularExpression)
            else { return title }
            return String(title[range.upperBound...])
        }
    }

    /** Java's Math.round(double): the closest Long, ties up. */
    static func javaRound(_ value: Double) -> Int64 {
        if value.isNaN { return 0 }
        let rounded = value >= 0 ? value.rounded(.toNearestOrAwayFromZero) : (value + 0.5).rounded(.down)
        return kToLong(rounded)
    }

    /** The catalog or Storage could not be reached, or said no (Kotlin's Unavailable, an IOException). */
    public struct Unavailable: Error, LocalizedError, CustomStringConvertible {
        public let message: String
        public init(_ message: String) { self.message = message }
        public var description: String { message }
        public var errorDescription: String? { message }
    }

    /** A Storage object that is not there (HTTP 400/404 from Supabase Storage). */
    public struct Missing: Error, LocalizedError, CustomStringConvertible {
        public let message: String
        public init(_ message: String) { self.message = message }
        public var description: String { message }
        public var errorDescription: String? { message }
    }

    public static let BUCKET = "lectures"

    /** Every saved video, newest series first and each series' videos in order. */
    public static func catalog(_ project: Project) throws -> [Entry] {
        let query = "select=*&order=saved_at.desc,lecture.asc"
        let body = String(decoding: try get(project, "\(project.url)/rest/v1/phone_lectures?\(query)", rest: true),
                          as: UTF8.self)
        let rows = try Json.parse(body)
        guard case .arr(let items) = rows else {
            throw Unavailable("the catalog is not a list: \(String(body.prefix(200)))")
        }
        let entries: [Entry] = items.compactMap { row in
            guard let buildId = row["build_id"]?.asString, let libraryPath = row["library_path"]?.asString else {
                return nil
            }
            var minutes: Double? = nil
            if case .num(let value)? = row["minutes"] { minutes = value }
            return Entry(
                buildId: buildId,
                series: row["series"]?.asString ?? "Lecture",
                lecture: row["lecture"]?.asInt ?? 1,
                lectures: row["lectures"]?.asInt ?? 1,
                title: row["title"]?.asString ?? "",
                minutes: minutes,
                libraryPath: libraryPath,
                libraryBytes: row["library_bytes"]?.asLong ?? 0,
                narrated: row["narrated"]?.asBool ?? false,
                savedAt: row["saved_at"]?.asString ?? "",
                frameCount: row["frame_count"]?.asInt ?? 0,
                fps: row["fps"]?.asInt ?? 0,
                subject: row["subject"]?.asString ?? ""
            )
        }
        // Newest series first, its videos together in order (a series' videos are saved within seconds).
        var keys: [String] = []
        var groups: [String: [Entry]] = [:]
        for entry in entries {
            let key = entry.series + "|" + String(entry.lectures)
            if groups[key] == nil { keys.append(key) }
            groups[key, default: []].append(entry)
        }
        // Kotlin's String.compareTo: UTF-16 units in order.
        func before(_ a: String, _ b: String) -> Bool { a.utf16.lexicographicallyPrecedes(b.utf16) }
        let newest = keys.map { key -> (String, [Entry]) in
            let group = groups[key]!
            return (group.map { $0.savedAt }.reduce(group[0].savedAt) { before($0, $1) ? $1 : $0 }, group)
        }
        // sortedByDescending, stable: equal keys keep their order.
        let ordered = newest.enumerated().sorted { a, b in
            before(b.element.0, a.element.0) || (!before(a.element.0, b.element.0) && a.offset < b.offset)
        }
        return ordered.flatMap { $0.element.1.stableSorted { $0.lecture } }
    }

    /**
     * A saved lecture's library, read file by file from the bucket: its own files under its folder, its assets
     * from the shared content-addressed folder.
     */
    public final class RemoteStorage: Storage {
        private let project: Project
        private let libraryPath: String
        private var cache: [String: [UInt8]] = [:]
        private let lock = NSLock()

        public init(_ project: Project, _ libraryPath: String) {
            self.project = project
            self.libraryPath = libraryPath
        }

        private func objectPath(_ path: String) -> String {
            if path.hasPrefix("assets/") { return path }
            var folder = libraryPath
            while folder.hasSuffix("/") { folder.removeLast() }
            return "\(folder)/\(path)"
        }

        public func exists(_ path: String) -> Bool {
            do {
                _ = try read(path)
                return true
            } catch {
                return false
            }
        }

        public func url(_ path: String) -> String {
            let key = objectPath(path).split(separator: "/", omittingEmptySubsequences: false)
                .map { SavedLectures.urlEncode(String($0)) }.joined(separator: "/")
            return "\(project.url)/storage/v1/object/public/\(BUCKET)/\(key)"
        }

        public func read(_ path: String) throws -> [UInt8] {
            lock.lock()
            let known = cache[path]
            lock.unlock()
            if let known = known { return known }
            let bytes = try get(project, url(path), rest: false)
            lock.lock()
            cache[path] = bytes
            lock.unlock()
            return bytes
        }

        public func sizeOf(_ path: String) -> Int64 { Int64((try? read(path))?.count ?? 0) }
    }

    /** Java's URLEncoder.encode(s, "UTF-8") with "+" then made "%20": a-z A-Z 0-9 . - * _ kept, the rest %XX. */
    static func urlEncode(_ s: String) -> String {
        var out = ""
        for byte in s.utf8 {
            switch byte {
            case 0x30...0x39, 0x41...0x5A, 0x61...0x7A, 0x2E, 0x2D, 0x2A, 0x5F:
                out.unicodeScalars.append(Unicode.Scalar(byte))
            default:
                out += "%" + String(format: "%02X", byte)
            }
        }
        return out
    }

    /** How far a download has got: bytes for a lecture's single file, files for one saved file by file. */
    public final class Progress: CustomStringConvertible {
        public let done: Int64
        public let total: Int64
        public let unit: String

        public init(_ done: Int64, _ total: Int64, _ unit: String) {
            self.done = done
            self.total = total
            self.unit = unit
        }

        public var description: String {
            if unit == "bytes" {
                return JavaFormat.format("%.1f of %.1f MB", .double(Double(done) / 1048576.0),
                                         .double(Double(total) / 1048576.0))
            }
            return "\(done) of \(total) files"
        }
    }

    /** The one file a lecture is saved as (store.ts): its whole phone library, zipped. */
    public static let BUNDLE = "library.zip"

    /** Files downloaded at once for a lecture saved file by file (before the bundle existed). */
    private static let DOWNLOADS_AT_ONCE = 8

    /**
     * Download a saved lecture into [dest] (replacing an earlier download of it) and open it, checked before it
     * replaces anything.
     *
     * A lecture is saved as one zip, downloaded in one request and unpacked as an import is (LibraryImport). It was
     * hundreds of files, one request each, one after another: the round trips, not the bytes, made a download take
     * minutes. One saved before the zip existed is still fetched file by file, [DOWNLOADS_AT_ONCE] at a time.
     */
    public static func download(_ project: Project, _ entry: Entry, _ dest: URL,
                                progress: @escaping (Progress) -> Void = { _ in }) throws -> Library {
        let remote = RemoteStorage(project, entry.libraryPath)
        let absolute = dest.standardizedFileURL
        let parent = absolute.deletingLastPathComponent()
        if absolute.path == "/" { throw Unavailable("no folder to download into") }
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        let zip = parent.appendingPathComponent("\(absolute.lastPathComponent).zip.part")
        do {
            defer { try? FileManager.default.removeItem(at: zip) }
            var fetched = true
            do {
                try fetchTo(project, remote.url(BUNDLE), zip, progress: { done, total in progress(Progress(done, total, "bytes")) })
            } catch is Missing {
                fetched = false
            }
            if fetched { return try LibraryImport.unpack(zipFile: zip, absolute) }
        }
        return try downloadFiles(project, remote, absolute, parent, progress)
    }

    private static func downloadFiles(_ project: Project, _ remote: RemoteStorage, _ dest: URL, _ parent: URL,
                                      _ progress: @escaping (Progress) -> Void) throws -> Library {
        let manifest = try Library.load(remote)
        var wanted: [String] = []
        var seen = Set<String>()
        func want(_ path: String) { if seen.insert(path).inserted { wanted.append(path) } }
        want("library.json")
        if let atlas = manifest.glyphAtlas { want(atlas) }
        for scene in manifest.scenes {
            scene.required().forEach(want)
            if let audio = scene.audio { want(audio) }
        }
        let audio = Set(manifest.scenes.compactMap { $0.audio })
        let manager = FileManager.default
        let staging = parent.appendingPathComponent("\(dest.lastPathComponent).downloading", isDirectory: true)
        try? manager.removeItem(at: staging)
        try manager.createDirectory(at: staging, withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: staging) }

        // A pool of threads, as the Kotlin's is: each one blocks on its download, and blocked GCD workers could
        // starve the queues URLSession itself runs on.
        let lock = NSLock()
        var errors = [Error?](repeating: nil, count: wanted.count)
        var next = 0
        var done: Int64 = 0
        var failed = false
        let finished = DispatchGroup()
        for _ in 0..<min(DOWNLOADS_AT_ONCE, wanted.count) {
            finished.enter()
            let worker = Thread {
                defer { finished.leave() }
                while true {
                    lock.lock()
                    // shutdownNow: the rest are not started once one has failed.
                    if failed || next >= wanted.count {
                        lock.unlock()
                        return
                    }
                    let index = next
                    next += 1
                    lock.unlock()
                    let path = wanted[index]
                    let file = staging.appendingPathComponent(path)
                    do {
                        try manager.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
                        do {
                            // Straight to the file: held in memory whole, a long narration could run the phone out.
                            try fetchTo(project, remote.url(path), file)
                        } catch {
                            try? manager.removeItem(at: file)
                            // Narration is optional (the picture plays silently without it); everything else is not.
                            if !audio.contains(path) { throw error }
                        }
                        lock.lock()
                        done += 1
                        let now = done
                        lock.unlock()
                        progress(Progress(now, Int64(wanted.count), "files"))
                    } catch {
                        lock.lock()
                        errors[index] = error
                        failed = true
                        lock.unlock()
                    }
                }
            }
            worker.start()
        }
        finished.wait()
        if let first = errors.lazy.compactMap({ $0 }).first { throw first }
        return try LibraryImport.install(staging, dest)
    }

    /**
     * Where a saved lecture's narration can be streamed from: [path] is the scene's audio as its manifest names it
     * (audio/<scene>.ogg). Save uploads it beside the lecture's zip, which leaves it out, so the picture starts as
     * soon as the zip is down and the narration plays from here while [fetchNarration] keeps it for offline.
     */
    public static func narrationUrl(_ project: Project, _ entry: Entry, _ path: String) -> String {
        RemoteStorage(project, entry.libraryPath).url(path)
    }

    /**
     * Download a saved lecture's narration into its folder ([dest]/[path]), for play without the network next time.
     * Written beside it and renamed when whole, so a half download is never taken for the narration. False when it
     * is not there to fetch (a lecture saved with its narration inside the zip has it already) or [cancelled] said
     * stop.
     */
    public static func fetchNarration(_ project: Project, _ entry: Entry, _ path: String, _ dest: URL,
                                      cancelled: () -> Bool = { false },
                                      progress: (Progress) -> Void = { _ in }) throws -> Bool {
        let manager = FileManager.default
        let target = dest.appendingPathComponent(path)
        if LibraryImport.isFile(target),
           let size = (try? manager.attributesOfItem(atPath: target.path))?[.size] as? NSNumber, size.int64Value > 0 {
            return true
        }
        try manager.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
        let part = URL(fileURLWithPath: target.path + ".part")
        defer { try? manager.removeItem(at: part) }
        do {
            try fetchTo(project, narrationUrl(project, entry, path), part, cancelled: cancelled) { done, total in
                progress(Progress(done, total, "bytes"))
            }
            if cancelled() { return false }
            do {
                if manager.fileExists(atPath: target.path) { try manager.removeItem(at: target) }
                try manager.moveItem(at: part, to: target)
            } catch {
                throw Unavailable("cannot keep the narration")
            }
            return true
        } catch is Missing {
            return false
        }
    }

    private static func beforeQuery(_ url: String) -> String {
        url.firstIndex(of: "?").map { String(url[..<$0]) } ?? url
    }

    /** A request to [url], timed out as the Kotlin's connection is (15 s to connect, 60 s between reads). */
    private static func request(_ url: String) throws -> URLRequest {
        guard let target = URL(string: url) else { throw Unavailable("not a URL: \(beforeQuery(url))") }
        var request = URLRequest(url: target)
        request.timeoutInterval = 60
        return request
    }

    /**
     * One session for every request, its delegate handing each task's events to that task's [Fetch]. (A session
     * per request is what the Kotlin's connection per request suggests, but on Linux several at once stall until
     * they time out.)
     */
    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 60
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.httpMaximumConnectionsPerHost = DOWNLOADS_AT_ONCE
        return URLSession(configuration: configuration, delegate: router, delegateQueue: nil)
    }()

    private static let router = Router()

    private final class Router: NSObject, URLSessionDataDelegate {
        private let lock = NSLock()
        private var fetches: [Int: Fetch] = [:]

        func start(_ request: URLRequest, _ fetch: Fetch) -> URLSessionDataTask {
            let task = SavedLectures.session.dataTask(with: request)
            lock.lock()
            fetches[task.taskIdentifier] = fetch
            lock.unlock()
            task.resume()
            return task
        }

        private func of(_ task: URLSessionTask) -> Fetch? {
            lock.lock()
            defer { lock.unlock() }
            return fetches[task.taskIdentifier]
        }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
            guard let fetch = of(dataTask) else { return completionHandler(.allow) }
            fetch.urlSession(session, dataTask: dataTask, didReceive: response, completionHandler: completionHandler)
        }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
            of(dataTask)?.urlSession(session, dataTask: dataTask, didReceive: data)
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            lock.lock()
            let fetch = fetches.removeValue(forKey: task.taskIdentifier)
            lock.unlock()
            fetch?.urlSession(session, task: task, didCompleteWithError: error)
        }
    }

    /**
     * Streams a response to a file. URLSession hands the bytes to this delegate on its own queue; the caller's
     * thread waits, and calls [cancelled] and the progress callback itself, so neither has to escape. Each 256 KB
     * written is noted as it happens, for the caller to pass on, as the Kotlin's read loop reports it.
     */
    private final class Fetch {
        let condition = NSCondition()
        private let file: URL
        private var out: FileHandle?
        // Guarded by [condition].
        var status = 0
        var total: Int64 = -1
        var done: Int64 = 0
        var told: Int64 = 0
        var steps: [(Int64, Int64)] = []
        var finished = false
        // Read by the caller once finished.
        private(set) var said = Data()
        private(set) var failure: Error?

        init(_ file: URL) { self.file = file }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            condition.lock()
            status = code
            total = response.expectedContentLength
            condition.unlock()
            if (200...299).contains(code) {
                if FileManager.default.createFile(atPath: file.path, contents: nil) {
                    out = try? FileHandle(forWritingTo: file)
                }
                if out == nil {
                    failure = Unavailable("cannot write \(file.lastPathComponent)")
                    completionHandler(.cancel)
                    return
                }
            }
            completionHandler(.allow)
        }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
            guard let out = out else {
                if said.count < 4096 { said.append(data) }
                return
            }
            do {
                try out.write(contentsOf: data)
            } catch {
                failure = error
                dataTask.cancel()
                return
            }
            condition.lock()
            done += Int64(data.count)
            if done - told >= 256 * 1024 {
                steps.append((done, total))
                told = done
                condition.signal()
            }
            condition.unlock()
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            try? out?.close()
            out = nil
            if failure == nil { failure = error }
            condition.lock()
            finished = true
            condition.signal()
            condition.unlock()
        }
    }

    /** A public Storage object downloaded into [file], in pieces. */
    private static func fetchTo(_ project: Project, _ url: String, _ file: URL, cancelled: () -> Bool = { false },
                                progress: (Int64, Int64) -> Void = { _, _ in }) throws {
        let fetch = Fetch(file)
        let task = router.start(try request(url), fetch)
        var stopped = false
        let condition = fetch.condition
        condition.lock()
        while true {
            let steps = fetch.steps
            fetch.steps.removeAll()
            let finished = fetch.finished
            condition.unlock()
            for (done, total) in steps where !stopped { progress(done, total) }
            if finished { break }
            if !stopped && cancelled() {
                stopped = true
                task.cancel()
            }
            condition.lock()
            if fetch.steps.isEmpty && !fetch.finished { _ = condition.wait(until: Date().addingTimeInterval(0.1)) }
        }
        condition.lock()
        let code = fetch.status
        let done = fetch.done
        let total = fetch.total
        condition.unlock()
        if stopped || ((200...299).contains(code) && cancelled()) {
            // Cancelled: the loop stops, and the caller checks cancelled() and drops what arrived.
            progress(done, total > 0 ? total : done)
            return
        }
        if let error = fetch.failure, code == 0 || (200...299).contains(code) { throw error }
        if !(200...299).contains(code) {
            let said = String(decoding: fetch.said, as: UTF8.self)
            // Storage answers a missing object with 400 {"statusCode":"404","error":"not_found"} or a 404.
            if code == 404 || said.contains("not_found") || said.contains("\"404\"") {
                throw Missing("not found: \(beforeQuery(url))")
            }
            throw Unavailable("HTTP \(code) from \(beforeQuery(url)): \(String(said.prefix(300)))")
        }
        if total > 0 && done < total { throw Unavailable("the download of \(beforeQuery(url)) was cut short") }
        progress(done, total > 0 ? total : done)
    }

    private static func get(_ project: Project, _ url: String, rest: Bool) throws -> [UInt8] {
        var request = try request(url)
        if rest {
            request.setValue(project.anonKey, forHTTPHeaderField: "apikey")
            // A legacy anon key is a JWT and goes in Authorization too; a publishable key (sb_publishable_...)
            // is not a JWT and belongs in apikey alone.
            if project.anonKey.hasPrefix("eyJ") {
                request.setValue("Bearer \(project.anonKey)", forHTTPHeaderField: "Authorization")
            }
            request.setValue("application/json", forHTTPHeaderField: "Accept")
        }
        let finished = DispatchSemaphore(value: 0)
        var body: Data?
        var answer: URLResponse?
        var failure: Error?
        session.dataTask(with: request) { data, response, error in
            body = data
            answer = response
            failure = error
            finished.signal()
        }.resume()
        finished.wait()
        if let error = failure { throw error }
        let code = (answer as? HTTPURLResponse)?.statusCode ?? 0
        let data = body ?? Data()
        if !(200...299).contains(code) {
            let said = String(decoding: data, as: UTF8.self)
            // PGRST205: the project has no phone_lectures view -- its schema was never applied.
            if said.contains("PGRST205") || said.contains("phone_lectures") && code == 404 {
                throw Unavailable("The Supabase project has no saved-lectures tables yet. In its dashboard, open " +
                    "SQL Editor, paste harness/supabase/setup.sql and run it; then save a lecture from the web app.")
            }
            throw Unavailable("HTTP \(code) from \(beforeQuery(url)): \(String(said.prefix(300)))")
        }
        return [UInt8](data)
    }
}
