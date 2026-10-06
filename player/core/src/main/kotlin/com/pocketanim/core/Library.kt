package com.pocketanim.core

import com.pocketanim.core.dsl.AssetLoader
import com.pocketanim.core.dsl.Interpreter
import com.pocketanim.core.dsl.Program

/**
 * What the device holds, and what it still needs.
 *
 * §5.3 wants all IR cached eagerly and audio fetched on demand. That only works
 * if the device can enumerate what exists and diff it against local storage,
 * which is what a manifest is for. The sync algorithm deliberately reduces to
 * "fetch the paths I do not have" -- content-addressed files never change, so
 * there is no invalidation to get wrong.
 */

/** Byte storage, wherever it lives. Android reads app storage; the harness, files. */
interface Storage {
    fun exists(path: String): Boolean
    fun read(path: String): ByteArray
    fun sizeOf(path: String): Long

    /**
     * The file as a stream. A lecture's narration was tens to hundreds of MB, and reading it whole (to check its
     * digest, to copy it out for the decoder) ran the phone out of memory: big files are only ever streamed.
     */
    fun open(path: String): java.io.InputStream = read(path).inputStream()

    /** The file itself, when the storage is a folder on this device: the decoder reads it in place. */
    fun file(path: String): java.io.File? = null
}

/** A file the manifest names, with what it should be when it arrives. */
class AssetRecord(val path: String, val bytes: Long, val digest: String?)

/** One thing wrong with local storage, and which file it is wrong about. */
class IntegrityProblem(val path: String, val reason: String) {
    override fun toString() = "$path: $reason"
}

class SceneEntry(
    val name: String,
    val tier: Int,
    /** Present for tier 1; absent means this scene falls back to [container]. */
    val program: String?,
    /** Sampled frames. May be absent once a scene is reliably tier 1. */
    val container: String?,
    val assets: List<String>,
    val needsGlyphAtlas: Boolean,
    val frames: Int,
    /** Everything that must be local before this scene plays offline. */
    val playableBytes: Long,
    val audio: String?,
) {
    /** Paths this scene cannot play without. Audio is deliberately not among them. */
    fun required(): List<String> = buildList {
        program?.let { add(it) } ?: container?.let { add(it) }
        addAll(assets)
    }
}

class Library(
    private val storage: Storage,
    val scenes: List<SceneEntry>,
    val glyphAtlas: String?,
    /** Every content-addressed file the manifest names, including the atlas. */
    val assets: List<AssetRecord> = emptyList(),
) {

    /**
     * Check what is on disk against what the manifest says should be there.
     *
     * Content addressing makes sync trivial but does not make storage
     * trustworthy: a download can truncate, a cache can be evicted mid-write,
     * and the failure then looks like corrupt geometry rather than a bad file.
     * Size is checked always because it is free; the digest only when asked,
     * because hashing two megabytes on every launch is not.
     */
    fun checkIntegrity(verifyDigests: Boolean = false): List<IntegrityProblem> {
        val problems = ArrayList<IntegrityProblem>()
        for (record in assets) {
            if (!storage.exists(record.path)) continue // missing() reports these
            val actual = storage.sizeOf(record.path)
            if (actual != record.bytes) {
                problems.add(IntegrityProblem(record.path, "expected ${record.bytes} B, found $actual B"))
                continue
            }
            val expected = record.digest ?: continue
            if (verifyDigests) {
                val got = storage.open(record.path).use { digestOf(it) }
                if (got != expected) {
                    problems.add(IntegrityProblem(record.path, "digest $got, expected $expected"))
                }
            }
        }
        return problems
    }
    /** Paths named by the manifest that this device does not have yet. */
    fun missing(): List<String> {
        val wanted = LinkedHashSet<String>()
        glyphAtlas?.let { if (scenes.any { s -> s.needsGlyphAtlas }) wanted.add(it) }
        for (scene in scenes) wanted.addAll(scene.required())
        return wanted.filterNot(storage::exists)
    }

    fun isPlayable(scene: SceneEntry): Boolean =
        scene.required().all(storage::exists) &&
            (!scene.needsGlyphAtlas || glyphAtlas?.let(storage::exists) == true)

    fun entry(name: String): SceneEntry =
        scenes.firstOrNull { it.name == name } ?: error("no scene named '$name'")

    /**
     * Open a scene for playback.
     *
     * Prefers the program: it is smaller by three orders of magnitude and, as
     * §9.5 measures, also more accurate, because the device computes at full
     * precision rather than replaying quantised samples. The container is the
     * fallback for scenes the exporter could not express.
     */
    fun open(name: String): Frames {
        val scene = entry(name)
        val program = scene.program
        if (program != null && storage.exists(program)) {
            return Interpreter.open(
                Program.parse(String(storage.read(program), Charsets.UTF_8)),
                ManifestAssets(storage, glyphAtlas),
            )
        }
        val container = scene.container ?: error("scene '$name' has neither program nor container")
        return Scene.parse(storage.read(container))
    }

    private class ManifestAssets(
        private val storage: Storage,
        private val glyphAtlas: String?,
    ) : AssetLoader {
        override fun asset(id: String) = storage.read("assets/$id.panm")
        override fun glyphLibrary() =
            storage.read(glyphAtlas ?: error("scene needs the glyph atlas but the library has none"))
    }

    companion object {
        fun load(storage: Storage, manifestPath: String = "library.json"): Library {
            val root = Json.parse(String(storage.read(manifestPath), Charsets.UTF_8))
            require(root["version"]?.asInt == 1) { "unsupported library version" }

            val scenes = root["scenes"]?.asList.orEmpty().map { entry ->
                SceneEntry(
                    name = entry["name"]?.asString ?: error("scene without a name"),
                    tier = entry["tier"]?.asInt ?: 3,
                    program = entry["program"]?.asString,
                    container = entry["container"]?.asString,
                    assets = entry["assets"]?.asList.orEmpty().mapNotNull { it.asString },
                    needsGlyphAtlas = entry["needs_glyph_atlas"]?.asBool ?: false,
                    frames = entry["frames"]?.asInt ?: 0,
                    playableBytes = entry["playable_bytes"]?.asLong ?: 0L,
                    audio = entry["audio"]?.asString,
                )
            }

            val assets = ArrayList<AssetRecord>()
            root["assets"]?.asList.orEmpty().forEach { entry ->
                val path = entry["path"]?.asString ?: return@forEach
                assets.add(AssetRecord(path, entry["bytes"]?.asLong ?: 0L, entry["sha256_16"]?.asString))
            }
            root["glyph_atlas"]?.let { atlas ->
                atlas["path"]?.asString?.let { path ->
                    assets.add(AssetRecord(path, atlas["bytes"]?.asLong ?: 0L, atlas["sha256_16"]?.asString))
                }
            }

            return Library(storage, scenes, root["glyph_atlas"]?.get("path")?.asString, assets)
        }

        /**
         * The manifest's short digest: the first 16 hex characters of SHA-256.
         *
         * Truncated because this guards against a damaged download rather than
         * a forged one, and 64 bits of it is already far past the point where
         * an accidental collision is conceivable.
         */
        fun digestOf(bytes: ByteArray): String = digestOf(bytes.inputStream())

        /** The same digest, read through a stream in 64 KB pieces, so a file of any size fits in memory. */
        fun digestOf(stream: java.io.InputStream): String {
            val sha = java.security.MessageDigest.getInstance("SHA-256")
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = stream.read(buffer)
                if (read < 0) break
                sha.update(buffer, 0, read)
            }
            val hash = sha.digest()
            val out = StringBuilder(16)
            for (i in 0 until 8) out.append(String.format("%02x", hash[i]))
            return out.toString()
        }
    }
}
