package com.pocketanim.player

import android.content.Context
import com.pocketanim.android.AssetStorage
import com.pocketanim.android.FileStorage
import com.pocketanim.core.Json
import com.pocketanim.core.Library
import com.pocketanim.core.LibraryImport
import com.pocketanim.core.SavedLectures
import com.pocketanim.core.Storage
import java.io.File

/**
 * What there is to watch, as the app shows it: lectures saved from the web app (listed from Supabase, played
 * streaming and kept on the phone once seen), lectures imported from a zip, and the samples inside the app.
 */
sealed class Lecture {
    /** Stable across launches: what progress and stills are kept under. */
    abstract val key: String
    abstract val title: String
    abstract val subtitle: String
    abstract val seconds: Double?

    /** A lecture saved from the web app. [dir] holds it once it has been played (or downloaded). */
    class Saved(val entry: SavedLectures.Entry, val dir: File) : Lecture() {
        override val key get() = "saved-${entry.buildId}"
        override val title get() = entry.shortTitle
        override val subtitle: String
            get() = buildString {
                append(entry.series)
                if (entry.lectures > 1) append("  ·  Lecture ${entry.lecture} of ${entry.lectures}")
            }
        override val seconds get() = entry.seconds
        val onPhone: Boolean get() = File(dir, "library.json").isFile
    }

    /** A lecture imported from the web app's "Download for the phone" zip. */
    class Imported(val dir: File, val name: String) : Lecture() {
        override val key get() = "import-${dir.name}"
        override val title get() = name
        override val subtitle get() = "Imported"
        override var seconds: Double? = null
    }

    /** A sample scene inside the app. */
    class Sample(val scene: String, val frames: Int) : Lecture() {
        override val key get() = "sample-$scene"
        override val title get() = scene.replace(Regex("([a-z])([A-Z])"), "$1 $2")
        override val subtitle get() = "Sample scene"
        override val seconds get() = if (frames > 0) frames / 30.0 else null
    }
}

object Lectures {
    private const val PREFS = "saved_lectures"
    private const val PROGRESS = "progress"
    const val TITLE_FILE = "title.txt"

    fun savedRoot(context: Context) = File(context.filesDir, "saved")
    fun importRoot(context: Context) = File(context.filesDir, "imported")
    fun stills(context: Context) = File(context.filesDir, "stills")

    /** The Supabase project saved lectures come from: set in the app, or shipped in assets/supabase.json. */
    fun project(context: Context): SavedLectures.Project? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        var url = prefs.getString("url", null)
        var key = prefs.getString("anon_key", null)
        if (url.isNullOrBlank() || key.isNullOrBlank()) {
            try {
                val shipped = Json.parse(String(context.assets.open("supabase.json").use { it.readBytes() }))
                url = shipped["url"]?.asString
                key = shipped["anon_key"]?.asString
            } catch (_: Exception) {
            }
        }
        return if (url.isNullOrBlank() || key.isNullOrBlank()) null else SavedLectures.Project(url, key)
    }

    fun setProject(context: Context, url: String, key: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("url", url.trim()).putString("anon_key", key.trim()).apply()
        catalogFile(context).delete()
    }

    // ---- the catalog, kept so the list (and what is on the phone) shows without the network ----------------------

    private fun catalogFile(context: Context) = File(context.filesDir, "catalog.json")

    @Volatile private var catalog: List<SavedLectures.Entry>? = null

    /** The last catalog fetched (kept on disk), without asking the network. */
    fun cachedCatalog(context: Context): List<SavedLectures.Entry> {
        catalog?.let { return it }
        val file = catalogFile(context)
        val loaded = if (file.isFile) runCatching { parseCatalog(file.readText()) }.getOrNull().orEmpty() else emptyList()
        catalog = loaded
        return loaded
    }

    /** The catalog from Supabase, kept for next time. Blocking: call off the main thread. */
    fun refreshCatalog(context: Context, project: SavedLectures.Project): List<SavedLectures.Entry> {
        val entries = SavedLectures.catalog(project)
        catalog = entries
        runCatching { catalogFile(context).writeText(writeCatalog(entries)) }
        return entries
    }

    fun savedEntry(context: Context, buildId: String): SavedLectures.Entry? =
        cachedCatalog(context).firstOrNull { it.buildId == buildId }

    /** The video after [entry] in its series, when there is one. */
    fun nextInSeries(context: Context, entry: SavedLectures.Entry): SavedLectures.Entry? =
        cachedCatalog(context).firstOrNull {
            it.series == entry.series && it.lectures == entry.lectures && it.lecture == entry.lecture + 1
        }

    private fun writeCatalog(entries: List<SavedLectures.Entry>): String = entries.joinToString(",", "[", "]") { e ->
        "{" + listOf(
            "build_id" to q(e.buildId), "series" to q(e.series), "lecture" to "${e.lecture}",
            "lectures" to "${e.lectures}", "title" to q(e.title), "minutes" to (e.minutes?.toString() ?: "null"),
            "library_path" to q(e.libraryPath), "library_bytes" to "${e.libraryBytes}", "narrated" to "${e.narrated}",
            "saved_at" to q(e.savedAt), "frame_count" to "${e.frameCount}", "fps" to "${e.fps}",
            "subject" to q(e.subject),
        ).joinToString(",") { (k, v) -> "\"$k\":$v" } + "}"
    }

    private fun q(text: String): String = buildString {
        append('"')
        for (c in text) when {
            c == '"' -> append("\\\"")
            c == '\\' -> append("\\\\")
            c == '\n' -> append("\\n")
            c < ' ' -> append(String.format("\\u%04x", c.code))
            else -> append(c)
        }
        append('"')
    }

    private fun parseCatalog(text: String): List<SavedLectures.Entry> {
        val rows = Json.parse(text) as? Json.Arr ?: return emptyList()
        return rows.items.mapNotNull { row ->
            SavedLectures.Entry(
                buildId = row["build_id"]?.asString ?: return@mapNotNull null,
                series = row["series"]?.asString ?: "Lecture",
                lecture = row["lecture"]?.asInt ?: 1,
                lectures = row["lectures"]?.asInt ?: 1,
                title = row["title"]?.asString ?: "",
                minutes = (row["minutes"] as? Json.Num)?.value,
                libraryPath = row["library_path"]?.asString ?: return@mapNotNull null,
                libraryBytes = row["library_bytes"]?.asLong ?: 0L,
                narrated = row["narrated"]?.asBool ?: false,
                savedAt = row["saved_at"]?.asString ?: "",
                frameCount = row["frame_count"]?.asInt ?: 0,
                fps = row["fps"]?.asInt ?: 0,
                subject = row["subject"]?.asString ?: "",
            )
        }
    }

    // ---- what is on the phone -------------------------------------------------------------------------------------

    /** Saved lectures, in catalog order (newest series first), each knowing whether it is on the phone. */
    fun saved(context: Context): List<Lecture.Saved> =
        cachedCatalog(context).map { Lecture.Saved(it, File(savedRoot(context), it.buildId)) }

    /** What plays without the network: saved lectures kept on the phone, then imported ones, newest first. */
    fun onPhone(context: Context): List<Lecture> {
        val saved = saved(context).filter { it.onPhone }
        val known = saved.map { it.dir.name }.toSet()
        // Downloaded once but gone from the catalog (unsaved since): still here, still playable.
        val orphans = savedRoot(context).listFiles()?.filter {
            it.isDirectory && !it.name.contains('.') && it.name !in known && File(it, "library.json").isFile
        }.orEmpty().map { dir ->
            Lecture.Imported(dir, File(dir, TITLE_FILE).takeIf { it.isFile }?.readText()?.trim()?.ifEmpty { null }
                ?: dir.name)
        }
        val imported = importRoot(context).listFiles()?.filter {
            it.isDirectory && !it.name.contains('.') && File(it, "library.json").isFile
        }.orEmpty().sortedByDescending { it.lastModified() }.map { Lecture.Imported(it, it.name.replace('-', ' ')) }
        return saved + orphans + imported
    }

    /** The samples packed in the app (or a library pushed beside it with adb, which wins). */
    fun samples(context: Context): List<Lecture.Sample> = runCatching {
        Library.load(sampleStorage(context)).scenes
            .sortedBy { if (it.name == "HelloPocketanim") "" else it.name }
            .map { Lecture.Sample(it.name, it.frames) }
    }.getOrDefault(emptyList())

    fun sampleStorage(context: Context): Storage {
        val pushed = context.getExternalFilesDir(null)?.let { File(it, "library") }
        return if (pushed != null && File(pushed, "library.json").isFile) FileStorage(pushed)
        else AssetStorage(context.assets)
    }

    /** The folder a lecture on the phone is read from. */
    fun dirOf(lecture: Lecture): File? = when (lecture) {
        is Lecture.Saved -> lecture.dir
        is Lecture.Imported -> lecture.dir
        is Lecture.Sample -> null
    }

    fun storageOf(context: Context, lecture: Lecture): Storage =
        dirOf(lecture)?.let { LibraryImport.DirStorage(it) } ?: sampleStorage(context)

    /** Remove a lecture from the phone (a saved one can be streamed again). */
    fun remove(context: Context, lecture: Lecture) {
        dirOf(lecture)?.deleteRecursively()
        File(stills(context), "${lecture.key}.png").delete()
        forget(context, lecture.key)
    }

    // ---- where a viewer got to ------------------------------------------------------------------------------------

    /** Seconds watched of [key] and its length, or null. */
    fun progress(context: Context, key: String): Pair<Double, Double>? {
        val prefs = context.getSharedPreferences(PROGRESS, Context.MODE_PRIVATE)
        val at = prefs.getFloat("$key.at", -1f)
        val of = prefs.getFloat("$key.of", -1f)
        return if (at < 0 || of <= 0) null else at.toDouble() to of.toDouble()
    }

    fun remember(context: Context, key: String, at: Double, of: Double) {
        context.getSharedPreferences(PROGRESS, Context.MODE_PRIVATE).edit()
            .putFloat("$key.at", at.toFloat()).putFloat("$key.of", of.toFloat())
            .putLong("$key.when", System.currentTimeMillis()).apply()
    }

    fun forget(context: Context, key: String) {
        context.getSharedPreferences(PROGRESS, Context.MODE_PRIVATE).edit()
            .remove("$key.at").remove("$key.of").remove("$key.when").apply()
    }
}
