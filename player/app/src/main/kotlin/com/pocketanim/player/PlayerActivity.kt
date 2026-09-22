package com.pocketanim.player

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import com.pocketanim.android.AssetStorage
import com.pocketanim.android.PanimView
import com.pocketanim.core.Library
import com.pocketanim.core.SceneEntry
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
    private lateinit var loopButton: Button
    private lateinit var seekBar: SeekBar
    private lateinit var timeLabel: TextView
    private lateinit var titleLabel: TextView

    private lateinit var library: Library
    private var entries: List<SceneEntry> = emptyList()
    private var current: SceneEntry? = null

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

        library = try {
            Library.load(AssetStorage(assets))
        } catch (e: Exception) {
            fail("cannot open the library: ${e.message}")
            return
        }

        // The sample first, then everything else alphabetically: the point of
        // the app is that one scene, and a picker that buries it is a worse
        // demonstration than one that does not.
        entries = library.scenes.sortedBy { if (it.name == SAMPLE) "" else it.name }
        if (entries.isEmpty()) {
            fail("the library has no scenes")
            return
        }
        open(entries.first())
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
        }

        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            addView(titleLabel, LinearLayout.LayoutParams(MATCH, WRAP))
            addView(stage, LinearLayout.LayoutParams(MATCH, 0, 1f))
            addView(controls, LinearLayout.LayoutParams(MATCH, WRAP))
        }
    }

    private fun open(entry: SceneEntry) {
        val frames = try {
            library.open(entry.name)
        } catch (e: Exception) {
            fail("cannot open ${entry.name}: ${e.message}")
            return
        }
        current = entry
        view.load(frames)
        view.playback?.looping = true

        seekBar.max = (frames.frameCount - 1).coerceAtLeast(0)
        seekBar.progress = 0
        val seconds = frames.frameCount.toDouble() / frames.fps
        titleLabel.text = String.format(
            Locale.ROOT,
            "%s  ·  tier %d  ·  %d frames at %d fps  ·  %.1fs  ·  %s on the wire",
            entry.name, entry.tier, frames.frameCount, frames.fps, seconds,
            humanBytes(entry.playableBytes),
        )
        showTime(0)
        view.play()
        playButton.text = PAUSE
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
        val names = entries.map { "${it.name}  (tier ${it.tier})" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Scene")
            .setItems(names) { _, which -> open(entries[which]) }
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
        playButton.isEnabled = false
        seekBar.isEnabled = false
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
        const val PLAY = "Play"
        const val PAUSE = "Pause"
        const val TICK_MILLIS = 66L  // ~15 Hz; a scrubber does not need 60
        const val PAD = 24
        const val MATCH = LinearLayout.LayoutParams.MATCH_PARENT
        const val WRAP = LinearLayout.LayoutParams.WRAP_CONTENT
    }
}
