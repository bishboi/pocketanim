package com.pocketanim.core

import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder

/**
 * The lectures saved from the harness (its Save button), as the player finds and fetches them.
 *
 * Saving puts each video's phone library in Supabase Storage, in the public bucket `lectures` --
 * builds/<build id>/library.json and the rest, the assets content-addressed once at assets/<digest>.panm -- and
 * lists it in the view `phone_lectures` (harness/supabase/migrations/0002_saved_lectures.sql). The player reads
 * that list through the project's REST API with its anon key, and downloads a lecture's files into app storage,
 * where it plays offline like an imported one (LibraryImport.install checks every file first).
 *
 * Plain JVM (java.net), so the desktop harness runs the same code as the phone.
 */
object SavedLectures {

    /** The Supabase project: its URL (https://<ref>.supabase.co) and its anon (public) key. */
    class Project(url: String, val anonKey: String) {
        val url: String = url.trim().trimEnd('/')
    }

    /** One saved video, as the catalog lists it. */
    class Entry(
        val buildId: String,
        val series: String,
        val lecture: Int,
        val lectures: Int,
        val title: String,
        val minutes: Double?,
        val libraryPath: String,
        val libraryBytes: Long,
        val narrated: Boolean,
        val savedAt: String,
    ) {
        /** What the picker shows: "Forces · Lecture 2 of 3: Friction (24 min)". */
        val label: String
            get() = buildString {
                append(series)
                val name = title.replace(Regex("^Lecture \\d+:\\s*"), "")
                if (lectures > 1) append(" · Lecture $lecture of $lectures: $name") else if (name != series) append(": $name")
                minutes?.let { append(if (it < 1) " (under 1 min)" else " (${Math.round(it)} min)") }
            }
    }

    class Unavailable(message: String) : IOException(message)

    const val BUCKET = "lectures"

    /** Every saved video, newest series first and each series' videos in order. */
    fun catalog(project: Project): List<Entry> {
        val query = "select=*&order=saved_at.desc,lecture.asc"
        val body = String(get(project, "${project.url}/rest/v1/phone_lectures?$query", rest = true), Charsets.UTF_8)
        val rows = Json.parse(body)
        if (rows !is Json.Arr) throw Unavailable("the catalog is not a list: ${body.take(200)}")
        // Newest series first, its videos together in order (a series' videos are saved within seconds).
        val entries = rows.items.mapNotNull { row ->
            Entry(
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
            )
        }
        val newest = entries.groupBy { it.series + "|" + it.lectures }.values
            .sortedByDescending { group -> group.maxOf { it.savedAt } }
        return newest.flatMap { group -> group.sortedBy { it.lecture } }
    }

    /**
     * A saved lecture's library, read file by file from the bucket: its own files under its folder, its assets
     * from the shared content-addressed folder.
     */
    class RemoteStorage(private val project: Project, private val libraryPath: String) : Storage {
        private val cache = HashMap<String, ByteArray>()

        private fun objectPath(path: String) =
            if (path.startsWith("assets/")) path else "${libraryPath.trimEnd('/')}/$path"

        override fun exists(path: String): Boolean = try {
            read(path)
            true
        } catch (_: IOException) {
            false
        }

        fun url(path: String): String {
            val key = objectPath(path).split('/').joinToString("/") { URLEncoder.encode(it, "UTF-8").replace("+", "%20") }
            return "${project.url}/storage/v1/object/public/$BUCKET/$key"
        }

        override fun read(path: String): ByteArray = cache.getOrPut(path) { get(project, url(path), rest = false) }

        override fun sizeOf(path: String): Long = read(path).size.toLong()
    }

    /** How far a download has got: bytes for a lecture's single file, files for one saved file by file. */
    class Progress(val done: Long, val total: Long, val unit: String) {
        override fun toString(): String =
            if (unit == "bytes") "%.1f of %.1f MB".format(java.util.Locale.ROOT, done / 1048576.0, total / 1048576.0)
            else "$done of $total files"
    }

    /** The one file a lecture is saved as (store.ts): its whole phone library, zipped. */
    const val BUNDLE = "library.zip"

    /** Files downloaded at once for a lecture saved file by file (before the bundle existed). */
    private const val DOWNLOADS_AT_ONCE = 8

    /**
     * Download a saved lecture into [dest] (replacing an earlier download of it) and open it, checked before it
     * replaces anything.
     *
     * A lecture is saved as one zip, downloaded in one request and unpacked as an import is (LibraryImport). It was
     * hundreds of files, one request each, one after another: the round trips, not the bytes, made a download take
     * minutes. One saved before the zip existed is still fetched file by file, [DOWNLOADS_AT_ONCE] at a time.
     */
    fun download(project: Project, entry: Entry, dest: File, progress: (Progress) -> Unit = {}): Library {
        val remote = RemoteStorage(project, entry.libraryPath)
        val parent = dest.absoluteFile.parentFile ?: throw Unavailable("no folder to download into")
        parent.mkdirs()
        val zip = File(parent, "${dest.name}.zip.part")
        try {
            val fetched = try {
                fetchTo(project, remote.url(BUNDLE), zip) { done, total -> progress(Progress(done, total, "bytes")) }
                true
            } catch (e: Missing) {
                false
            }
            if (fetched) return zip.inputStream().use { LibraryImport.unpack(it, dest) }
        } finally {
            zip.delete()
        }
        return downloadFiles(project, remote, dest, parent, progress)
    }

    private fun downloadFiles(project: Project, remote: RemoteStorage, dest: File, parent: File,
                              progress: (Progress) -> Unit): Library {
        val manifest = Library.load(remote)
        val wanted = LinkedHashSet<String>()
        wanted.add("library.json")
        manifest.glyphAtlas?.let { wanted.add(it) }
        for (scene in manifest.scenes) {
            wanted.addAll(scene.required())
            scene.audio?.let { wanted.add(it) }
        }
        val staging = File(parent, "${dest.name}.downloading")
        staging.deleteRecursively()
        staging.mkdirs()
        val pool = java.util.concurrent.Executors.newFixedThreadPool(DOWNLOADS_AT_ONCE)
        try {
            val done = java.util.concurrent.atomic.AtomicInteger()
            val jobs = wanted.map { path ->
                pool.submit {
                    val file = File(staging, path)
                    file.parentFile?.mkdirs()
                    try {
                        // Straight to the file: held in memory whole, a long narration could run the phone out.
                        fetchTo(project, remote.url(path), file)
                    } catch (e: IOException) {
                        file.delete()
                        // Narration is optional (the picture plays silently without it); everything else is not.
                        if (manifest.scenes.none { it.audio == path }) throw e
                    }
                    progress(Progress(done.incrementAndGet().toLong(), wanted.size.toLong(), "files"))
                }
            }
            for (job in jobs) {
                try {
                    job.get()
                } catch (e: java.util.concurrent.ExecutionException) {
                    throw (e.cause ?: e)
                }
            }
            return LibraryImport.install(staging, dest)
        } finally {
            pool.shutdownNow()
            staging.deleteRecursively()
        }
    }

    /** A Storage object that is not there (HTTP 400/404 from Supabase Storage). */
    class Missing(message: String) : IOException(message)

    /** A public Storage object downloaded into [file], in pieces. */
    private fun fetchTo(project: Project, url: String, file: File, progress: (Long, Long) -> Unit = { _, _ -> }) {
        val connection = URI(url).toURL().openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15_000
            connection.readTimeout = 60_000
            val code = connection.responseCode
            if (code !in 200..299) {
                val said = connection.errorStream?.use { String(it.readBytes(), Charsets.UTF_8) }.orEmpty()
                // Storage answers a missing object with 400 {"statusCode":"404","error":"not_found"} or a 404.
                if (code == 404 || "not_found" in said || "\"404\"" in said) throw Missing("not found: ${url.substringBefore('?')}")
                throw Unavailable("HTTP $code from ${url.substringBefore('?')}: ${said.take(300)}")
            }
            val total = connection.contentLengthLong
            connection.inputStream.use { input ->
                file.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    var done = 0L
                    var told = 0L
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        output.write(buffer, 0, read)
                        done += read
                        if (done - told >= 256 * 1024) {
                            progress(done, total)
                            told = done
                        }
                    }
                    progress(done, if (total > 0) total else done)
                }
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun get(project: Project, url: String, rest: Boolean): ByteArray {
        val connection = URI(url).toURL().openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15_000
            connection.readTimeout = 60_000
            if (rest) {
                connection.setRequestProperty("apikey", project.anonKey)
                // A legacy anon key is a JWT and goes in Authorization too; a publishable key (sb_publishable_...)
                // is not a JWT and belongs in apikey alone.
                if (project.anonKey.startsWith("eyJ")) {
                    connection.setRequestProperty("Authorization", "Bearer ${project.anonKey}")
                }
                connection.setRequestProperty("Accept", "application/json")
            }
            val code = connection.responseCode
            if (code !in 200..299) {
                val said = connection.errorStream?.use { String(it.readBytes(), Charsets.UTF_8) }.orEmpty()
                // PGRST205: the project has no phone_lectures view -- its schema was never applied.
                if ("PGRST205" in said || "phone_lectures" in said && code == 404) {
                    throw Unavailable("The Supabase project has no saved-lectures tables yet. In its dashboard, open " +
                        "SQL Editor, paste harness/supabase/setup.sql and run it; then save a lecture from the web app.")
                }
                throw Unavailable("HTTP $code from ${url.substringBefore('?')}: ${said.take(300)}")
            }
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }
}
