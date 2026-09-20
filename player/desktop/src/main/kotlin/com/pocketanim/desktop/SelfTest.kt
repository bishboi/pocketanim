package com.pocketanim.desktop

import com.pocketanim.core.Frames
import com.pocketanim.core.Instance
import com.pocketanim.core.Json
import com.pocketanim.core.Library
import com.pocketanim.core.Playback
import com.pocketanim.core.Storage
import com.pocketanim.core.SystemTimeSource
import com.pocketanim.core.TimeSource

/**
 * Tests for the parts of the player that decide *what you see* without drawing
 * anything.
 *
 * Rendering is checked against the Cairo oracle, which is a strong test but
 * only of the drawing. The clock chooses which frame reaches that renderer, and
 * a clock that picks the wrong frame produces a picture that is perfectly drawn
 * and wrong. Nothing was checking it.
 *
 * Deliberately not a JUnit suite: pulling a test framework into this module to
 * assert on a few dozen pure functions would cost more than it is worth, and
 * this has to run from the same `build.sh` that has no dependency resolver.
 */
private class Checks {
    var passed = 0
    val failures = ArrayList<String>()

    fun check(name: String, condition: Boolean) {
        if (condition) passed++ else failures.add(name)
    }

    fun <T> equal(name: String, expected: T, actual: T) {
        if (expected == actual) passed++ else failures.add("$name: expected $expected, got $actual")
    }

    fun threw(name: String, body: () -> Unit) {
        try {
            body()
            failures.add("$name: expected an exception, none thrown")
        } catch (_: Exception) {
            passed++
        }
    }
}

/** A clock the test drives by hand, so nothing depends on wall time. */
private class FakeNanos {
    var now = 0L
    fun advance(seconds: Double) {
        now += (seconds * 1e9).toLong()
    }
}

/** Frames with nothing in them: enough for the clock, which never looks. */
private class EmptyFrames(override val fps: Int, override val frameCount: Int) : Frames {
    override fun shape(atlasId: Int) = FloatArray(0)
    override fun camera(index: Int): FloatArray? = null
    override fun instances(index: Int): Array<Instance> = emptyArray()
}

private class MapStorage(private val files: Map<String, ByteArray>) : Storage {
    override fun exists(path: String) = files.containsKey(path)
    override fun read(path: String) = files[path] ?: error("no such file: $path")
    override fun sizeOf(path: String) = (files[path]?.size ?: 0).toLong()
}

private fun jsonChecks(c: Checks) {
    val doc = Json.parse(
        """{"a": 1, "b": [true, false, null], "c": {"d": "x\ny"}, "e": -2.5e2}"""
    )
    c.equal("json int", 1, doc["a"]?.asInt)
    c.equal("json bool", true, doc["b"]?.get(0)?.asBool)
    c.equal("json null", Json.Null, doc["b"]?.get(2))
    c.equal("json nested string", "x\ny", doc["c"]?.get("d")?.asString)
    c.equal("json negative exponent", -250, doc["e"]?.asInt)
    c.equal("json missing key", null, doc["nope"])
    c.equal("json empty object", 0, Json.parse("{}").asList.size)
    c.equal("json unicode escape", "é", Json.parse("""{"k":"é"}""")["k"]?.asString)

    // A manifest is generated, but it arrives over a network. Malformed input
    // should fail loudly at parse rather than silently read as something else.
    c.threw("json rejects trailing input") { Json.parse("""{"a":1} junk""") }
    c.threw("json rejects unterminated string") { Json.parse("""{"a":"x""") }
    c.threw("json rejects bare word") { Json.parse("""{"a": bare}""") }
}

private fun clockChecks(c: Checks) {
    val nanos = FakeNanos()
    val system = SystemTimeSource { nanos.now }
    val playback = Playback(EmptyFrames(fps = 30, frameCount = 90), system)

    c.equal("clock starts at frame 0", 0, playback.currentFrame())
    c.check("clock starts paused", !playback.playing)

    playback.play()
    nanos.advance(1.0)
    c.equal("one second is frame 30", 30, playback.currentFrame())

    // Pausing must stop time, not merely stop drawing.
    playback.pause()
    nanos.advance(5.0)
    c.equal("paused clock does not advance", 30, playback.currentFrame())

    playback.play()
    nanos.advance(0.5)
    c.equal("resuming does not credit the pause", 45, playback.currentFrame())

    // Past the end it pins to the last frame and stops, rather than running off.
    nanos.advance(10.0)
    c.equal("past the end pins to the last frame", 89, playback.currentFrame())
    c.check("past the end stops playing", !playback.playing)

    val looping = Playback(EmptyFrames(30, 90), SystemTimeSource { nanos.now }.also { it.start() })
    looping.looping = true
    looping.play()
    nanos.advance(3.5)
    c.equal("looping wraps", 15, looping.currentFrame())

    // Seeking is by frame, and must survive being asked for the impossible.
    val seeking = Playback(EmptyFrames(30, 90), SystemTimeSource { nanos.now })
    seeking.seekToFrame(45)
    c.equal("seek lands exactly", 45, seeking.currentFrame())
    seeking.seekToFrame(-10)
    c.equal("seek clamps below", 0, seeking.currentFrame())
    seeking.seekToFrame(9999)
    c.equal("seek clamps above", 89, seeking.currentFrame())

    // frameToDraw exists so a still scene costs nothing; it must report a frame
    // once and then stay quiet until the frame actually changes.
    val redraw = Playback(EmptyFrames(30, 90), SystemTimeSource { nanos.now })
    redraw.seekToFrame(10)
    c.equal("first request draws", 10, redraw.frameToDraw())
    c.equal("second request is a no-op", -1, redraw.frameToDraw())
}

private fun audioClockChecks(c: Checks) {
    val nanos = FakeNanos()
    val system = SystemTimeSource { nanos.now }
    val playback = Playback(EmptyFrames(30, 300), system)

    // An AudioTrack reports nothing until it has really started. Treating that
    // as position zero would pin the video on frame 0 until audio caught up,
    // so a source that cannot answer must fall through to the system clock.
    var audioPosition: Double? = null
    playback.audio = TimeSource { audioPosition }

    playback.play()
    nanos.advance(1.0)
    c.equal("silent audio falls back to the system clock", 30, playback.currentFrame())

    audioPosition = 2.0
    c.equal("audio wins once it can answer", 60, playback.currentFrame())

    // And it keeps winning: the video follows audio even when they disagree,
    // because a dropped frame is invisible and drifting narration is not.
    nanos.advance(5.0)
    c.equal("audio keeps the lead", 60, playback.currentFrame())

    audioPosition = null
    c.equal("losing audio returns to the system clock", 180, playback.currentFrame())
}

private fun libraryChecks(c: Checks) {
    val atlas = "glyphs".toByteArray()
    val asset = "some geometry".toByteArray()
    val manifest = """
    {
      "version": 1,
      "glyph_atlas": {"path": "library.atlas", "bytes": ${atlas.size},
                      "sha256_16": "${Library.digestOf(atlas)}"},
      "assets": [{"path": "assets/aa.panm", "bytes": ${asset.size},
                  "sha256_16": "${Library.digestOf(asset)}"}],
      "scenes": [
        {"name": "Present", "tier": 1, "program": "scenes/p.panim",
         "assets": ["assets/aa.panm"], "needs_glyph_atlas": true,
         "frames": 10, "playable_bytes": 99},
        {"name": "Absent", "tier": 3, "container": "scenes/q.panm",
         "assets": [], "needs_glyph_atlas": false,
         "frames": 20, "playable_bytes": 5}
      ]
    }
    """.trimIndent()

    val full = mapOf(
        "library.json" to manifest.toByteArray(),
        "library.atlas" to atlas,
        "assets/aa.panm" to asset,
        "scenes/p.panim" to "scene 2d fps=30".toByteArray(),
        "scenes/q.panm" to ByteArray(4),
    )

    val library = Library.load(MapStorage(full))
    c.equal("reads every scene", 2, library.scenes.size)
    c.equal("reads the tier", 1, library.entry("Present").tier)
    c.equal("nothing missing when all present", 0, library.missing().size)
    c.check("present scene is playable", library.isPlayable(library.entry("Present")))
    c.equal("intact storage has no problems", 0, library.checkIntegrity(verifyDigests = true).size)
    c.threw("unknown scene is an error") { library.entry("Nope") }

    // A scene whose asset has not arrived is reported, not silently broken.
    val partial = Library.load(MapStorage(full - "assets/aa.panm"))
    c.equal("missing asset is reported", 1, partial.missing().size)
    c.check("scene with a missing asset is not playable",
        !partial.isPlayable(partial.entry("Present")))
    c.check("scene needing nothing missing is still playable",
        partial.isPlayable(partial.entry("Absent")))

    // Truncation is the realistic corruption: an interrupted download leaves a
    // file that exists, opens, and decodes into the wrong picture.
    val truncated = Library.load(MapStorage(full + ("assets/aa.panm" to asset.copyOf(3))))
    val bySize = truncated.checkIntegrity()
    c.equal("truncation caught by size alone", 1, bySize.size)
    c.check("problem names the file", bySize.firstOrNull()?.path == "assets/aa.panm")

    // Same length, different bytes: only the digest can see this one.
    val swapped = asset.copyOf().also { it[0] = (it[0] + 1).toByte() }
    val corrupt = Library.load(MapStorage(full + ("assets/aa.panm" to swapped)))
    c.equal("same-size corruption passes a size check", 0, corrupt.checkIntegrity().size)
    c.equal("same-size corruption caught by digest", 1,
        corrupt.checkIntegrity(verifyDigests = true).size)
}

fun runSelfTest(): Boolean {
    val c = Checks()
    jsonChecks(c)
    clockChecks(c)
    audioClockChecks(c)
    libraryChecks(c)

    if (c.failures.isEmpty()) {
        println("selftest: ${c.passed} checks passed")
        return true
    }
    println("selftest: ${c.passed} passed, ${c.failures.size} FAILED")
    c.failures.forEach { println("  $it") }
    return false
}
