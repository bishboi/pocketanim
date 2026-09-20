package com.pocketanim.android

import android.content.res.AssetManager
import com.pocketanim.core.Storage
import java.io.File

/**
 * [Storage] over the APK's assets.
 *
 * For the benchmark, and for a first run before anything has been synced: the
 * library ships inside the app so there is something to play without a network.
 * A shipping app would back this with app storage instead, which is what §5.3's
 * cache policy is about — the interface is the same either way, which is the
 * reason it exists.
 *
 * Assets are compressed inside the APK, so `sizeOf` has to read the entry to
 * find out how big it is. That is fine for an integrity check run once, and
 * would not be fine per frame.
 */
class AssetStorage(
    private val assets: AssetManager,
    private val root: String = "library",
) : Storage {

    private fun full(path: String) = if (root.isEmpty()) path else "$root/$path"

    override fun exists(path: String): Boolean = try {
        assets.open(full(path)).close()
        true
    } catch (_: java.io.IOException) {
        false
    }

    override fun read(path: String): ByteArray =
        assets.open(full(path)).use { it.readBytes() }

    override fun sizeOf(path: String): Long =
        assets.open(full(path)).use { stream ->
            var total = 0L
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = stream.read(buffer)
                if (read < 0) break
                total += read
            }
            total
        }
}

/** [Storage] over a directory, for a library pushed with `adb push`. */
class FileStorage(private val root: File) : Storage {
    override fun exists(path: String) = File(root, path).exists()
    override fun read(path: String) = File(root, path).readBytes()
    override fun sizeOf(path: String) = File(root, path).length()
}
