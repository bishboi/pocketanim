package com.pocketanim.player

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import com.pocketanim.android.AssetStorage
import com.pocketanim.android.FileStorage
import com.pocketanim.android.PanimView
import com.pocketanim.core.Library
import com.pocketanim.core.LibraryImport
import com.pocketanim.core.SceneEntry
import com.pocketanim.core.Storage
import java.io.File
import java.util.Locale

/**
 * The player, as a viewer meets it.
 *
 * Everything before this measured whether frames can be produced fast enough.
 * This is the part that decides whether that is worth anything: a scene opens,
 * plays, pauses, scrubs and loops, driven by a clock rather than by a loop that
 * renders as fast as it can. The benchmark never touched [PanimView], so none
 * of that had run on a phone until this existed.
 *
 * What plays is a *program*. `HelloPocketanim` is 277 bytes of DSL and one text
 * asset; there is no video file anywhere in the APK, and nothing is decoded.
 * The frames are computed on the device as it draws them, which is why seeking
 * is instant and why the whole library is smaller than a single second of H.264.
 */
class PlayerActivity : Activity() {

    private lateinit var view: PanimView
    private lateinit var playButton: Button
    private lateinit var sceneButton: Button
    private lateinit var importButton: Button
    private lateinit var loopButton: Button
    private lateinit var seekBar: SeekBar
    private lateinit var timeLabel: TextView
    private lateinit var titleLabel: TextView

    /**
     * One scene the picker offers, with the library it lives in: a lecture imported from the harness, a library
     * pushed with adb, or the samples inside the APK. [label] is what the viewer sees (an import's file name: every
     * lecture's scene is called GeneratedScene).
     */
    private class Item(val entry: SceneEntry, val library: Library, val storage: Storage, val label: String)

    private var items: List<Item> = emptyList()
    private var current: Item? = null

    /** Where imported lectures live, one folder each, named after the zip they came from. */
    private val importRoot: File by lazy { File(filesDir, "imported") }

    /** True while a finger is on the bar, so the ticker stops fighting it. */
    private var scrubbing = false

    private val ticker = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            syncTransport()
            ticker.postDelayed(this, TICK_MILLIS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // A player that lets the screen sleep mid-scene is not a player.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        setContentView(buildUi())

        reload(select = null)
        // Opened with a lecture's zip (the harness's "Download for the phone", tapped on the phone).
        handle(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handle(intent)
    }

    private fun handle(intent: Intent?) {
        if (intent?.action == Intent.ACTION_VIEW) intent.data?.let(::importFrom)
    }

    /**
     * Every scene there is to play: imported lectures first, newest first; then a library pushed with adb; then
     * the samples in the APK, HelloPocketanim first. Opens [select] (an import's name) when given, else the first.
     */
    private fun reload(select: String?) {
        val found = ArrayList<Item>()
        val problems = ArrayList<String>()
        importRoot.listFiles { f -> f.isDirectory && !f.name.contains('.') }.orEmpty()
            .sortedByDescending { it.lastModified() }
            .forEach { dir ->
                try {
                    val storage = LibraryImport.DirStorage(dir)
                    val library = Library.load(storage)
                    library.scenes.forEach { entry ->
                        val label = if (library.scenes.size == 1) dir.name else "${dir.name} · ${entry.name}"
                        found.add(Item(entry, library, storage, label))
                    }
                } catch (e: Exception) {
                    problems.add("${dir.name}: ${e.message}")
                }
            }
        // A library pushed next to the app wins over the one inside it, so a
        // scene built in the harness plays without rebuilding the APK:
        //   adb push <library> /sdcard/Android/data/com.pocketanim.player/files/library
        val pushed = getExternalFilesDir(null)?.let { File(it, "library") }
        val storage: Storage = if (pushed != null && File(pushed, "library.json").isFile) FileStorage(pushed)
            else AssetStorage(assets)
        try {
            val library = Library.load(storage)
            // The sample first, then everything else alphabetically: the point of
            // the app is that one scene, and a picker that buries it is a worse
            // demonstration than one that does not.
            library.scenes.sortedBy { if (it.name == SAMPLE) "" else it.name }
                .forEach { found.add(Item(it, library, storage, it.name)) }
        } catch (e: Exception) {
            problems.add("the built-in library: ${e.message}")
        }
        items = found
        if (items.isEmpty()) {
            fail("nothing to play" + if (problems.isEmpty()) "" else ": ${problems.first()}")
            return
        }
        setControls(true)
        open(items.firstOrNull { select != null && it.label.startsWith(select) } ?: items.first())
    }

    /** Pick a lecture's zip from the phone's files (Downloads, a chat app, a drive). */
    private fun pickZip() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType("*/*")
            .putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("application/zip", "application/x-zip-compressed",
                "application/octet-stream"))
        try {
            @Suppress("DEPRECATION")
            startActivityForResult(pick, PICK_ZIP)
        } catch (e: Exception) {
            titleLabel.text = "no file picker on this phone: ${e.message}"
        }
    }

    @Deprecated("Activity result API needs AndroidX; this app has no dependencies")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == PICK_ZIP && resultCode == RESULT_OK) data?.data?.let(::importFrom)
    }

    /**
     * Unpack a lecture's zip into app storage, off the main thread (it hashes every file), then play it. A zip
     * that is not a whole library is refused with the reason and nothing already imported is touched.
     */
    private fun importFrom(uri: Uri) {
        val name = importName(uri)
        titleLabel.text = "Importing $name…"
        view.pause()
        Thread {
            val result = runCatching {
                val input = contentResolver.openInputStream(uri) ?: error("cannot read $uri")
                input.use { LibraryImport.unpack(it, File(importRoot, name)) }
            }
            runOnUiThread {
                result.fold(
                    onSuccess = { reload(select = name) },
                    onFailure = { titleLabel.text = "Could not import $name: ${it.message}" },
                )
            }
        }.start()
    }

    /** The import's folder name: the zip's file name, made safe for a folder and without ".zip". */
    private fun importName(uri: Uri): String {
        var shown: String? = null
        try {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) shown = cursor.getString(0)
            }
        } catch (_: Exception) {
        }
        val raw = (shown ?: uri.lastPathSegment ?: "lecture").substringAfterLast('/')
            .removeSuffix(".zip").removeSuffix("-library")
        return raw.replace(Regex("[^A-Za-z0-9_-]+"), "-").trim('-').take(80).ifEmpty { "lecture" }
    }

    private fun buildUi(): View {
        view = PanimView(this)

        titleLabel = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 13f
            setPadding(PAD, PAD, PAD, 0)
        }

        // Centred in a black frame. PanimView measures itself to Manim's 16:9
        // rather than filling, so on a 20:9 phone this is what puts the letterbox
        // either side of it instead of leaving the scene hard against one edge.
        val stage = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(
                view,
                FrameLayout.LayoutParams(MATCH, WRAP, Gravity.CENTER),
            )
        }

        playButton = Button(this).apply {
            text = PLAY
            setOnClickListener { togglePlay() }
        }
        loopButton = Button(this).apply {
            text = "Loop: on"
            setOnClickListener { toggleLoop() }
        }
        sceneButton = Button(this).apply {
            text = "Scene"
            setOnClickListener { chooseScene() }
        }
        importButton = Button(this).apply {
            text = "Import"
            setOnClickListener { pickZip() }
        }
        timeLabel = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 12f
            typeface = android.graphics.Typeface.MONOSPACE
            setPadding(PAD, 0, PAD, 0)
        }

        seekBar = SeekBar(this).apply {
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar, value: Int, fromUser: Boolean) {
                    // Only a drag seeks. Echoing the ticker's own writes back
                    // into the clock would make playback stutter against itself.
                    if (fromUser) {
                        view.seekToFrame(value)
                        showTime(value)
                    }
                }

                override fun onStartTrackingTouch(bar: SeekBar) {
                    scrubbing = true
                }

                override fun onStopTrackingTouch(bar: SeekBar) {
                    scrubbing = false
                }
            })
        }

        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(playButton, LinearLayout.LayoutParams(WRAP, WRAP))
            addView(seekBar, LinearLayout.LayoutParams(0, WRAP, 1f))
            addView(timeLabel, LinearLayout.LayoutParams(WRAP, WRAP))
            addView(loopButton, LinearLayout.LayoutParams(WRAP, WRAP))
            addView(sceneButton, LinearLayout.LayoutParams(WRAP, WRAP))
            addView(importButton, LinearLayout.LayoutParams(WRAP, WRAP))
        }

        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            addView(titleLabel, LinearLayout.LayoutParams(MATCH, WRAP))
            addView(stage, LinearLayout.LayoutParams(MATCH, 0, 1f))
            addView(controls, LinearLayout.LayoutParams(MATCH, WRAP))
        }
    }

    private fun open(item: Item) {
        val entry = item.entry
        val frames = try {
            item.library.open(entry.name)
        } catch (e: Exception) {
            titleLabel.text = "cannot open ${item.label}: ${e.message}"
            return
        }
        current = item
        view.load(frames)
        view.playback?.looping = true

        seekBar.max = (frames.frameCount - 1).coerceAtLeast(0)
        seekBar.progress = 0
        val seconds = frames.frameCount.toDouble() / frames.fps
        titleLabel.text = String.format(
            Locale.ROOT,
            "%s  ·  tier %d  ·  %d frames at %d fps  ·  %.1fs  ·  %s on the wire",
            item.label, entry.tier, frames.frameCount, frames.fps, seconds,
            humanBytes(entry.playableBytes),
        )
        showTime(0)
        entry.audio?.let { attachNarration(item, it) }
        view.play()
        playButton.text = PAUSE
    }

    /**
     * Play the scene's narration against its frames.
     *
     * The player decodes from a file, and an APK asset is not one, so the
     * track is copied out to the cache once. A scene whose narration is
     * missing or unreadable still plays, silently -- audio is optional by
     * design (§5.3), and the picture keeps the system clock.
     */
    private fun attachNarration(item: Item, path: String) {
        try {
            // Keyed by the item's label too: two imported lectures are both GeneratedScene, with different voices.
            val key = "${item.label}-${item.entry.name}".replace(Regex("[^A-Za-z0-9_-]+"), "-")
            val file = File(cacheDir, "narration-$key-${path.substringAfterLast('/')}")
            if (!file.isFile || file.length() != item.storage.sizeOf(path)) file.writeBytes(item.storage.read(path))
            val extractor = MediaExtractor()
            try {
                extractor.setDataSource(file.absolutePath)
                val format = (0 until extractor.trackCount)
                    .map { extractor.getTrackFormat(it) }
                    .firstOrNull { it.getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true }
                    ?: return
                view.attachAudio(
                    file,
                    format.getInteger(MediaFormat.KEY_SAMPLE_RATE),
                    format.getInteger(MediaFormat.KEY_CHANNEL_COUNT),
                )
            } finally {
                extractor.release()
            }
        } catch (e: Exception) {
            titleLabel.text = "${titleLabel.text}  ·  narration unavailable: ${e.message}"
        }
    }

    private fun togglePlay() {
        val playback = view.playback ?: return
        if (playback.playing) {
            view.pause()
            playButton.text = PLAY
        } else {
            // Replay rather than sit on the last frame: reaching the end with
            // looping off stops the clock there, and a play button that does
            // nothing is indistinguishable from a broken one.
            if (playback.currentFrame() >= playback.frameCount - 1) view.seekToFrame(0)
            view.play()
            playButton.text = PAUSE
        }
    }

    private fun toggleLoop() {
        val playback = view.playback ?: return
        playback.looping = !playback.looping
        loopButton.text = if (playback.looping) "Loop: on" else "Loop: off"
    }

    private fun chooseScene() {
        val names = items.map { "${it.label}  (tier ${it.entry.tier})" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Scene")
            .setItems(names) { _, which -> open(items[which]) }
            .show()
    }

    private fun syncTransport() {
        val playback = view.playback ?: return
        if (!scrubbing) {
            val frame = playback.currentFrame()
            seekBar.progress = frame
            showTime(frame)
        }
        val wanted = if (playback.playing) PAUSE else PLAY
        if (playButton.text != wanted) playButton.text = wanted
    }

    private fun showTime(frame: Int) {
        val fps = view.scene?.fps ?: return
        val total = view.playback?.frameCount ?: return
        timeLabel.text = String.format(
            Locale.ROOT, "%s / %s", clock(frame, fps), clock(total - 1, fps),
        )
    }

    private fun clock(frame: Int, fps: Int): String {
        val seconds = frame.toDouble() / fps
        return String.format(Locale.ROOT, "%d:%04.1f", seconds.toInt() / 60, seconds % 60)
    }

    private fun humanBytes(bytes: Long): String = when {
        bytes >= 1_000_000 -> String.format(Locale.ROOT, "%.1f MB", bytes / 1e6)
        bytes >= 1_000 -> String.format(Locale.ROOT, "%.1f kB", bytes / 1e3)
        else -> "$bytes B"
    }

    private fun fail(message: String) {
        titleLabel.text = message
        setControls(false)
    }

    /** Import stays usable when nothing else is: it is how there comes to be something to play. */
    private fun setControls(enabled: Boolean) {
        playButton.isEnabled = enabled
        seekBar.isEnabled = enabled
        sceneButton.isEnabled = enabled
        loopButton.isEnabled = enabled
    }

    override fun onResume() {
        super.onResume()
        ticker.post(tick)
    }

    override fun onPause() {
        super.onPause()
        ticker.removeCallbacks(tick)
        // Pause on leaving: the surface goes away and the clock would otherwise
        // keep running, so coming back would jump to wherever it had reached.
        view.pause()
        playButton.text = PLAY
    }

    override fun onDestroy() {
        super.onDestroy()
        // An AudioTrack outlives the view unless someone says otherwise.
        view.release()
    }

    private companion object {
        const val SAMPLE = "HelloPocketanim"
        const val PICK_ZIP = 7
        const val PLAY = "Play"
        const val PAUSE = "Pause"
        const val TICK_MILLIS = 66L  // ~15 Hz; a scrubber does not need 60
        const val PAD = 24
        const val MATCH = LinearLayout.LayoutParams.MATCH_PARENT
        const val WRAP = LinearLayout.LayoutParams.WRAP_CONTENT
    }
}
