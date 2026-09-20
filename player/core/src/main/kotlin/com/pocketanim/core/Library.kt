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
) {
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

            return Library(storage, scenes, root["glyph_atlas"]?.get("path")?.asString)
        }
    }
}
