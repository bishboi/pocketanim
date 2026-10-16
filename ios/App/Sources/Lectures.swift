// Ported from player/app/src/main/kotlin/com/pocketanim/player/Lectures.kt.
import Foundation
import PanimCore

/**
 * What there is to watch, as the app shows it: lectures saved from the web app (listed from Supabase, played
 * streaming and kept on the phone once seen), lectures imported from a zip, and the samples inside the app.
 */
enum Lecture {
    /** A lecture saved from the web app. [dir] holds it once it has been played (or downloaded). */
    case saved(SavedLectures.Entry, dir: URL)
    /** A lecture imported from the web app's "Download for the phone" zip. */
    case imported(dir: URL, name: String)
    /** A sample scene inside the app. */
    case sample(scene: String, frames: Int)

    /** Stable across launches: what progress and stills are kept under. */
    var key: String {
        switch self {
        case .saved(let entry, _): return "saved-\(entry.buildId)"
        case .imported(let dir, _): return "import-\(dir.lastPathComponent)"
        case .sample(let scene, _): return "sample-\(scene)"
        }
    }

    var title: String {
        switch self {
        case .saved(let entry, _): return entry.shortTitle
        case .imported(_, let name): return name
        case .sample(let scene, _):
            return scene.replacingOccurrences(of: "([a-z])([A-Z])", with: "$1 $2", options: .regularExpression)
        }
    }

    var subtitle: String {
        switch self {
        case .saved(let entry, _):
            var text = entry.series
            if entry.lectures > 1 { text += "  ·  Lecture \(entry.lecture) of \(entry.lectures)" }
            return text
        case .imported: return "Imported"
        case .sample: return "Sample scene"
        }
    }

    var seconds: Double? {
        switch self {
        case .saved(let entry, _): return entry.seconds
        case .imported: return nil
        case .sample(_, let frames): return frames > 0 ? Double(frames) / 30.0 : nil
        }
    }

    /** A saved lecture is on the phone once its library is in its folder; the others always are. */
    var onPhone: Bool {
        switch self {
        case .saved(_, let dir): return Lectures.isFile(dir.appendingPathComponent("library.json"))
        case .imported, .sample: return true
        }
    }

    var isSample: Bool {
        if case .sample = self { return true }
        return false
    }
}

enum Lectures {
    private static let PREFS_URL = "saved_lectures.url"
    private static let PREFS_KEY = "saved_lectures.anon_key"
    private static let PROGRESS = "progress."
    static let TITLE_FILE = "title.txt"

    private static var files: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }

    static var savedRoot: URL { files.appendingPathComponent("saved", isDirectory: true) }
    static var importRoot: URL { files.appendingPathComponent("imported", isDirectory: true) }
    static var stills: URL { files.appendingPathComponent("stills", isDirectory: true) }

    static func isFile(_ url: URL) -> Bool {
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &directory) && !directory.boolValue
    }

    static func isDirectory(_ url: URL) -> Bool {
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &directory) && directory.boolValue
    }

    /**
     * The Supabase project saved lectures come from: set in the app, or built in (PANIM_SUPABASE_URL and
     * PANIM_SUPABASE_ANON_KEY from Secrets.xcconfig, through Info.plist) -- the Android app's assets/supabase.json.
     */
    static func project() -> SavedLectures.Project? {
        let defaults = UserDefaults.standard
        var url = defaults.string(forKey: PREFS_URL)
        var key = defaults.string(forKey: PREFS_KEY)
        if url?.isEmpty != false || key?.isEmpty != false {
            url = built("PanimSupabaseURL")
            key = built("PanimSupabaseAnonKey")
        }
        guard let u = url, !u.isEmpty, let k = key, !k.isEmpty else { return nil }
        return SavedLectures.Project(url: u, anonKey: k)
    }

    /** An Info.plist value set at build time; nil when the build left it empty (or unexpanded). */
    private static func built(_ name: String) -> String? {
        guard let value = (Bundle.main.object(forInfoDictionaryKey: name) as? String)?
            .trimmingCharacters(in: .whitespaces), !value.isEmpty, !value.hasPrefix("$(") else { return nil }
        return value
    }

    static func setProject(url: String, key: String) {
        let defaults = UserDefaults.standard
        defaults.set(url.trimmingCharacters(in: .whitespacesAndNewlines), forKey: PREFS_URL)
        defaults.set(key.trimmingCharacters(in: .whitespacesAndNewlines), forKey: PREFS_KEY)
        try? FileManager.default.removeItem(at: catalogFile)
        catalog = nil
    }

    // ---- the catalog, kept so the list (and what is on the phone) shows without the network ----------------------

    private static var catalogFile: URL { files.appendingPathComponent("catalog.json") }

    private static let catalogLock = NSLock()
    private static var catalog: [SavedLectures.Entry]?

    /** The last catalog fetched (kept on disk), without asking the network. */
    static func cachedCatalog() -> [SavedLectures.Entry] {
        catalogLock.lock()
        defer { catalogLock.unlock() }
        if let known = catalog { return known }
        let loaded = (try? Data(contentsOf: catalogFile)).flatMap(parseCatalog) ?? []
        catalog = loaded
        return loaded
    }

    /** The catalog from Supabase, kept for next time. Blocking: call off the main thread. */
    static func refreshCatalog(_ project: SavedLectures.Project) throws -> [SavedLectures.Entry] {
        let entries = try SavedLectures.catalog(project)
        catalogLock.lock()
        catalog = entries
        catalogLock.unlock()
        if let data = writeCatalog(entries) { try? data.write(to: catalogFile, options: .atomic) }
        return entries
    }

    static func savedEntry(_ buildId: String) -> SavedLectures.Entry? {
        cachedCatalog().first { $0.buildId == buildId }
    }

    /** The video after [entry] in its series, when there is one. */
    static func nextInSeries(_ entry: SavedLectures.Entry) -> SavedLectures.Entry? {
        cachedCatalog().first {
            $0.series == entry.series && $0.lectures == entry.lectures && $0.lecture == entry.lecture + 1
        }
    }

    // Foundation's JSON here, not the core's: the Kotlin app had no library to use, this one has the platform's.
    private static func writeCatalog(_ entries: [SavedLectures.Entry]) -> Data? {
        let rows: [[String: Any]] = entries.map { e in
            [
                "build_id": e.buildId, "series": e.series, "lecture": e.lecture, "lectures": e.lectures,
                "title": e.title, "minutes": e.minutes.map { $0 as Any } ?? NSNull(),
                "library_path": e.libraryPath, "library_bytes": e.libraryBytes, "narrated": e.narrated,
                "saved_at": e.savedAt, "frame_count": e.frameCount, "fps": e.fps, "subject": e.subject,
            ]
        }
        return try? JSONSerialization.data(withJSONObject: rows)
    }

    private static func parseCatalog(_ data: Data) -> [SavedLectures.Entry]? {
        guard let rows = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { return nil }
        return rows.compactMap { row in
            guard let buildId = row["build_id"] as? String, let libraryPath = row["library_path"] as? String else {
                return nil
            }
            return SavedLectures.Entry(
                buildId: buildId,
                series: row["series"] as? String ?? "Lecture",
                lecture: (row["lecture"] as? NSNumber)?.intValue ?? 1,
                lectures: (row["lectures"] as? NSNumber)?.intValue ?? 1,
                title: row["title"] as? String ?? "",
                minutes: (row["minutes"] as? NSNumber)?.doubleValue,
                libraryPath: libraryPath,
                libraryBytes: (row["library_bytes"] as? NSNumber)?.int64Value ?? 0,
                narrated: (row["narrated"] as? NSNumber)?.boolValue ?? false,
                savedAt: row["saved_at"] as? String ?? "",
                frameCount: (row["frame_count"] as? NSNumber)?.intValue ?? 0,
                fps: (row["fps"] as? NSNumber)?.intValue ?? 0,
                subject: row["subject"] as? String ?? ""
            )
        }
    }

    // ---- what is on the phone -------------------------------------------------------------------------------------

    /** Saved lectures, in catalog order (newest series first), each knowing whether it is on the phone. */
    static func saved() -> [Lecture] {
        cachedCatalog().map { .saved($0, dir: savedRoot.appendingPathComponent($0.buildId, isDirectory: true)) }
    }

    private static func folders(_ root: URL) -> [URL] {
        let found = (try? FileManager.default.contentsOfDirectory(
            at: root, includingPropertiesForKeys: [.contentModificationDateKey], options: [.skipsHiddenFiles])) ?? []
        return found.filter {
            isDirectory($0) && !$0.lastPathComponent.contains(".") && isFile($0.appendingPathComponent("library.json"))
        }
    }

    /** What plays without the network: saved lectures kept on the phone, then imported ones, newest first. */
    static func onPhone() -> [Lecture] {
        let saved = saved().filter { $0.onPhone }
        var known = Set<String>()
        for case .saved(_, let dir) in saved { known.insert(dir.lastPathComponent) }
        // Downloaded once but gone from the catalog (unsaved since): still here, still playable.
        let orphans: [Lecture] = folders(savedRoot).filter { !known.contains($0.lastPathComponent) }.map { dir in
            let title = (try? String(contentsOf: dir.appendingPathComponent(TITLE_FILE), encoding: .utf8))?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return .imported(dir: dir, name: (title?.isEmpty == false ? title : nil) ?? dir.lastPathComponent)
        }
        func modified(_ url: URL) -> Date {
            (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
        }
        let imported: [Lecture] = folders(importRoot).sorted { modified($0) > modified($1) }.map {
            .imported(dir: $0, name: $0.lastPathComponent.replacingOccurrences(of: "-", with: " "))
        }
        return saved + orphans + imported
    }

    /** The samples packed in the app (or a library copied into Documents with Finder or Files, which wins). */
    static func samples() -> [Lecture] {
        guard let storage = sampleStorage(), let library = try? Library.load(storage) else { return [] }
        return library.scenes
            .sorted { ($0.name == "HelloPocketanim" ? "" : $0.name) < ($1.name == "HelloPocketanim" ? "" : $1.name) }
            .map { .sample(scene: $0.name, frames: $0.frames) }
    }

    static func sampleStorage() -> Storage? {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let pushed = documents.appendingPathComponent("library", isDirectory: true)
        if isFile(pushed.appendingPathComponent("library.json")) { return LibraryImport.DirStorage(pushed) }
        return AssetStorage.storage()
    }

    /** The folder a lecture on the phone is read from. */
    static func dirOf(_ lecture: Lecture) -> URL? {
        switch lecture {
        case .saved(_, let dir): return dir
        case .imported(let dir, _): return dir
        case .sample: return nil
        }
    }

    static func storageOf(_ lecture: Lecture) -> Storage? {
        if let dir = dirOf(lecture) { return LibraryImport.DirStorage(dir) }
        return sampleStorage()
    }

    /** Remove a lecture from the phone (a saved one can be streamed again). */
    static func remove(_ lecture: Lecture) {
        if let dir = dirOf(lecture) { try? FileManager.default.removeItem(at: dir) }
        try? FileManager.default.removeItem(at: stills.appendingPathComponent("\(lecture.key).png"))
        forget(lecture.key)
    }

    // ---- where a viewer got to ------------------------------------------------------------------------------------

    /** Seconds watched of [key] and its length, or nil. */
    static func progress(_ key: String) -> (at: Double, of: Double)? {
        let defaults = UserDefaults.standard
        guard let at = defaults.object(forKey: "\(PROGRESS)\(key).at") as? Double,
              let of = defaults.object(forKey: "\(PROGRESS)\(key).of") as? Double, at >= 0, of > 0 else { return nil }
        return (at, of)
    }

    static func remember(_ key: String, at: Double, of: Double) {
        let defaults = UserDefaults.standard
        defaults.set(at, forKey: "\(PROGRESS)\(key).at")
        defaults.set(of, forKey: "\(PROGRESS)\(key).of")
        defaults.set(Date().timeIntervalSince1970, forKey: "\(PROGRESS)\(key).when")
    }

    static func forget(_ key: String) {
        let defaults = UserDefaults.standard
        for suffix in ["at", "of", "when"] { defaults.removeObject(forKey: "\(PROGRESS)\(key).\(suffix)") }
    }
}
