package com.pocketanim.core

import java.io.File
import java.io.IOException
import java.io.InputStream
import java.util.zip.ZipInputStream

/**
 * A library zip, as the harness's "Phone library" download makes it, unpacked into app storage.
 *
 * Until this existed a lecture reached the phone only by `adb push`, which no viewer does. The zip holds one
 * folder, `library/` (library.json, the atlas, the programs, the assets, the narration); it is unpacked into a
 * staging folder beside [dest], checked the way the player will read it -- the manifest parses, every file it
 * names is there at the size and digest it says -- and only then moved into place, so a broken or half-copied
 * download never replaces a library that played.
 *
 * Pure JVM on purpose (java.util.zip only), so the desktop self-test runs the same code the phone does.
 */
object LibraryImport {

    /** The most a zip may unpack to: a two-hour lecture is a few MB; this only stops a zip bomb. */
    const val MAX_BYTES = 512L * 1024 * 1024

    class ImportFailed(message: String) : IOException(message)

    /**
     * Unpack [input] into [dest] (replaced when the new library checks out). Returns the library, opened.
     * A leading `library/` folder in the zip is dropped; an entry that would land outside [dest] is refused.
     */
    fun unpack(input: InputStream, dest: File): Library {
        val parent = dest.absoluteFile.parentFile ?: throw ImportFailed("no folder to unpack into")
        parent.mkdirs()
        val staging = File(parent, "${dest.name}.importing")
        staging.deleteRecursively()
        staging.mkdirs()
        try {
            extract(input, staging)
            val root = findRoot(staging) ?: throw ImportFailed("the zip has no library.json: not a phone library")
            val library = Library.load(DirStorage(root))
            val absent = library.missing()
            if (absent.isNotEmpty()) {
                throw ImportFailed("the library is missing ${absent.size} file(s), e.g. ${absent.first()}")
            }
            val problems = library.checkIntegrity(verifyDigests = true)
            if (problems.isNotEmpty()) {
                throw ImportFailed("the library is incomplete: " + problems.take(3).joinToString("; "))
            }
            if (library.scenes.isEmpty()) throw ImportFailed("the library has no scenes")
            val old = File(parent, "${dest.name}.old")
            old.deleteRecursively()
            if (dest.exists() && !dest.renameTo(old)) throw ImportFailed("cannot replace ${dest.name}")
            if (!root.renameTo(dest)) {
                old.renameTo(dest)
                throw ImportFailed("cannot move the library into place")
            }
            old.deleteRecursively()
            return Library.load(DirStorage(dest))
        } finally {
            staging.deleteRecursively()
        }
    }

    private fun extract(input: InputStream, into: File) {
        val base = into.canonicalFile
        var total = 0L
        ZipInputStream(input.buffered()).use { zip ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val entry = zip.nextEntry ?: break
                val name = entry.name.replace('\\', '/').trimStart('/')
                if (name.isEmpty() || name.startsWith("__MACOSX/")) continue
                val target = File(base, name).canonicalFile
                // Zip slip: "../../shared_prefs/x" would otherwise write outside the library.
                if (target != base && !target.path.startsWith(base.path + File.separator)) {
                    throw ImportFailed("the zip names a file outside the library: ${entry.name}")
                }
                if (entry.isDirectory) {
                    target.mkdirs()
                    continue
                }
                target.parentFile?.mkdirs()
                target.outputStream().use { out ->
                    while (true) {
                        val read = zip.read(buffer)
                        if (read < 0) break
                        total += read
                        if (total > MAX_BYTES) throw ImportFailed("the zip unpacks to more than ${MAX_BYTES / 1_048_576} MB")
                        out.write(buffer, 0, read)
                    }
                }
            }
        }
    }

    /** The folder holding library.json: the top, or the one folder the zip wraps it in. */
    private fun findRoot(dir: File): File? {
        if (File(dir, "library.json").isFile) return dir
        val folders = dir.listFiles { f -> f.isDirectory && f.name != "__MACOSX" }.orEmpty()
        return folders.singleOrNull()?.takeIf { File(it, "library.json").isFile }
    }

    /** [Storage] over a folder: what an imported library is read through, on the phone as here. */
    class DirStorage(private val root: File) : Storage {
        override fun exists(path: String) = File(root, path).exists()
        override fun read(path: String) = File(root, path).readBytes()
        override fun sizeOf(path: String) = File(root, path).length()
    }
}
