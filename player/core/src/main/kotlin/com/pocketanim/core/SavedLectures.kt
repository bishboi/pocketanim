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

        override fun read(path: String): ByteArray = cache.getOrPut(path) {
            val key = objectPath(path).split('/').joinToString("/") { URLEncoder.encode(it, "UTF-8").replace("+", "%20") }
            get(project, "${project.url}/storage/v1/object/public/$BUCKET/$key", rest = false)
        }

        override fun sizeOf(path: String): Long = read(path).size.toLong()
    }

    /**
     * Download a saved lecture into [dest] (replacing an earlier download of it) and open it: the manifest, the
     * glyph atlas, every scene's program and assets, and its narration, checked before it replaces anything.
     */
    fun download(project: Project, entry: Entry, dest: File, progress: (done: Int, total: Int) -> Unit = { _, _ -> }): Library {
        val remote = RemoteStorage(project, entry.libraryPath)
        val manifest = Library.load(remote)
        val wanted = LinkedHashSet<String>()
        wanted.add("library.json")
        manifest.glyphAtlas?.let { wanted.add(it) }
        for (scene in manifest.scenes) {
            wanted.addAll(scene.required())
            scene.audio?.let { wanted.add(it) }
        }
        val parent = dest.absoluteFile.parentFile ?: throw Unavailable("no folder to download into")
        parent.mkdirs()
        val staging = File(parent, "${dest.name}.downloading")
        staging.deleteRecursively()
        staging.mkdirs()
        try {
            wanted.forEachIndexed { i, path ->
                val bytes = try {
                    remote.read(path)
                } catch (e: IOException) {
                    // Narration is optional (the picture plays silently without it); everything else is not.
                    if (manifest.scenes.any { it.audio == path }) return@forEachIndexed
                    throw e
                }
                val file = File(staging, path)
                file.parentFile?.mkdirs()
                file.writeBytes(bytes)
                progress(i + 1, wanted.size)
            }
            return LibraryImport.install(staging, dest)
        } finally {
            staging.deleteRecursively()
        }
    }

    private fun get(project: Project, url: String, rest: Boolean): ByteArray {
        val connection = URI(url).toURL().openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15_000
            connection.readTimeout = 60_000
            if (rest) {
                connection.setRequestProperty("apikey", project.anonKey)
                connection.setRequestProperty("Authorization", "Bearer ${project.anonKey}")
                connection.setRequestProperty("Accept", "application/json")
            }
            val code = connection.responseCode
            if (code !in 200..299) {
                val said = connection.errorStream?.use { String(it.readBytes(), Charsets.UTF_8) }.orEmpty()
                throw Unavailable("HTTP $code from ${url.substringBefore('?')}: ${said.take(300)}")
            }
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }
}
