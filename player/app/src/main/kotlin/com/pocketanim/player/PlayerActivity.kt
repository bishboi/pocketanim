package com.pocketanim.player

import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaExtractor
import android.media.MediaFormat
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import com.pocketanim.android.PanimView
import com.pocketanim.core.Chapter
import com.pocketanim.core.Frames
import com.pocketanim.core.Library
import com.pocketanim.core.LibraryImport
import com.pocketanim.core.SavedLectures
import com.pocketanim.core.SceneEntry
import com.pocketanim.core.Storage
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The player, as a viewer meets it: like a video, though nothing here is a video. The lecture is a program the
 * phone draws frame by frame as it plays, which is why it starts after a few megabytes, seeks instantly and looks
 * sharp at any size.
 *
 * A saved lecture streams: its program and pictures (a few MB) come first and it starts; its narration plays from
 * the network while it is kept on the phone for next time. The picture follows the narration, and holds -- with a
 * spinner, as a video buffers -- when the network falls behind.
 *
 * Tap the picture for the controls (they hide themselves while it plays); double-tap its left or right side to go
 * back or on ten seconds. Turn the phone, or press the corner button, for the whole screen.
 */
class PlayerActivity : Activity() {

    companion object {
        private const val EXTRA_KIND = "kind"
        private const val EXTRA_ID = "id"
        private const val EXTRA_TITLE = "title"
        private const val EXTRA_FROM_START = "from_start"
        private const val TICK_MILLIS = 66L
        private const val HIDE_AFTER_MILLIS = 3200L
        private const val SKIP_SECONDS = 10.0
        private val SPEEDS = doubleArrayOf(0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)

        fun intent(context: Context, lecture: Lecture, fromStart: Boolean): Intent =
            Intent(context, PlayerActivity::class.java)
                .putExtra(EXTRA_FROM_START, fromStart)
                .putExtra(EXTRA_TITLE, lecture.title)
                .also { intent ->
                    when (lecture) {
                        is Lecture.Saved -> intent.putExtra(EXTRA_KIND, "saved").putExtra(EXTRA_ID, lecture.entry.buildId)
                        is Lecture.Imported -> intent.putExtra(EXTRA_KIND, "dir").putExtra(EXTRA_ID, lecture.dir.path)
                        is Lecture.Sample -> intent.putExtra(EXTRA_KIND, "sample").putExtra(EXTRA_ID, lecture.scene)
                    }
                }
    }

    private lateinit var lecture: Lecture
    private lateinit var root: LinearLayout
    private lateinit var stage: FrameLayout
    private lateinit var view: PanimView
    private lateinit var overlay: FrameLayout
    private lateinit var controls: FrameLayout
    private lateinit var playButton: ImageView
    private lateinit var timeline: TimelineView
    private lateinit var timeLabel: TextView
    private lateinit var chapterLabel: TextView
    private lateinit var titleLabel: TextView
    private lateinit var speedButton: TextView
    private lateinit var fullscreenButton: ImageView
    private lateinit var spinner: ProgressBar
    private lateinit var loadingLabel: TextView
    private lateinit var hint: TextView
    private lateinit var notice: TextView
    private lateinit var endCard: LinearLayout
    private lateinit var details: ScrollView
    private lateinit var chapterList: LinearLayout
    private lateinit var infoLabel: TextView

    private var frames: Frames? = null
    private var scene: SceneEntry? = null
    private var chapters: List<Chapter> = emptyList()
    private var fps = 30
    private var frameCount = 1

    /** What the viewer asked for: playing or not. Buffering holds the picture without changing this. */
    private var wantPlaying = false
    private var heldForNetwork = false
    private var controlsShown = true
    private var scrubbing = false
    private var endShown = false
    private var speed = 1.0
    private var lastSaved = 0L
    private var shownChapter = -1
    private var loadedFraction = 1f

    private val narrationFetch = AtomicBoolean(false)
    private val main = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            sync()
            main.postDelayed(this, TICK_MILLIS)
        }
    }
    private val hideControls = Runnable { if (wantPlaying && !scrubbing) setControls(false) }

    private var focus: AudioFocusRequest? = null
    private val noisy = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            // Headphones pulled out: stop, as a video app does, rather than speak to the room.
            if (wantPlaying) togglePlay()
        }
    }

    // ---- life ---------------------------------------------------------------------------------------------------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        lecture = lectureFrom(intent) ?: run {
            finish()
            return
        }
        setContentView(build())
        layoutFor(resources.configuration.orientation)
        registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
        prepare()
    }

    override fun onResume() {
        super.onResume()
        main.post(tick)
    }

    override fun onPause() {
        super.onPause()
        main.removeCallbacks(tick)
        if (wantPlaying) togglePlay()
        remember()
    }

    override fun onDestroy() {
        super.onDestroy()
        narrationFetch.set(true)
        runCatching { unregisterReceiver(noisy) }
        abandonFocus()
        if (::view.isInitialized) view.release()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        layoutFor(newConfig.orientation)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE &&
            requestedOrientation == ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE) {
            // Out of the whole screen first, as a video app does; back again leaves.
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
            main.postDelayed({ requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED }, 1500)
            return
        }
        @Suppress("DEPRECATION")
        super.onBackPressed()
    }

    private fun lectureFrom(intent: Intent): Lecture? {
        val id = intent.getStringExtra(EXTRA_ID) ?: return null
        return when (intent.getStringExtra(EXTRA_KIND)) {
            "saved" -> Lectures.savedEntry(this, id)?.let { Lecture.Saved(it, File(Lectures.savedRoot(this), it.buildId)) }
            "dir" -> Lecture.Imported(File(id), intent.getStringExtra(EXTRA_TITLE) ?: File(id).name)
            "sample" -> Lecture.Sample(id, 0)
            else -> null
        }
    }

    // ---- getting it ready -----------------------------------------------------------------------------------------

    /**
     * Get the lecture onto the phone if it is not (a saved one: its program and pictures, a few MB, in one
     * request), open it, and start. Off the main thread; the stage says how far it has got.
     */
    private fun prepare() {
        loading(true, "Getting ready…")
        Thread {
            val result = runCatching {
                val current = lecture
                if (current is Lecture.Saved && !current.onPhone) {
                    val project = Lectures.project(this) ?: error("no Supabase project is set (Library → ⋮)")
                    SavedLectures.download(project, current.entry, current.dir) { progress ->
                        if (progress.unit == "bytes" && progress.total > 0) {
                            val share = progress.done.toFloat() / progress.total
                            runOnUiThread { loading(true, "Loading the lecture · $progress", share) }
                        } else runOnUiThread { loading(true, "Loading the lecture · $progress") }
                    }
                    File(current.dir, Lectures.TITLE_FILE).writeText(current.title)
                }
                runOnUiThread { loading(true, "Opening…") }
                val storage = Lectures.storageOf(this, lecture)
                val library = Library.load(storage)
                val entry = if (lecture is Lecture.Sample) library.entry((lecture as Lecture.Sample).scene)
                else library.scenes.first()
                Triple(storage, entry, library.open(entry.name))
            }
            runOnUiThread {
                result.fold(
                    onSuccess = { (storage, entry, opened) -> start(storage, entry, opened) },
                    onFailure = { error ->
                        // OutOfMemoryError included: a message, not the app closing.
                        loading(false)
                        showNotice("Could not play this lecture: ${error.message ?: error.javaClass.simpleName}",
                            action = "Back") { finish() }
                    },
                )
            }
        }.start()
    }

    private fun start(storage: Storage, entry: SceneEntry, opened: Frames) {
        frames = opened
        scene = entry
        fps = opened.fps
        frameCount = opened.frameCount.coerceAtLeast(1)
        chapters = entry.chapters
        view.load(opened)
        view.playback?.looping = false
        view.setSpeed(speed)
        timeline.durationSeconds = frameCount.toDouble() / fps
        timeline.chapters = chapters.map { it.frame.toFloat() / frameCount to it.title }
        fillDetails()
        loading(false)

        val saved = Lectures.progress(this, lecture.key)
        val from = intent.getBooleanExtra(EXTRA_FROM_START, false)
        val total = frameCount.toDouble() / fps
        if (!from && saved != null && saved.first > 5 && saved.first < total - 10) {
            view.seekToFrame((saved.first * fps).toInt())
            showNotice("Resumed at ${Ui.clock(saved.first)}", action = "Start over") { seekSeconds(0.0) }
        }
        play()
        narrate(storage, entry)
    }

    /**
     * The narration: from the phone when it is here; else, for a saved lecture, streamed from where Save put it,
     * and kept on the phone as it plays. The picture plays at once; the voice joins at the picture's place.
     */
    private fun narrate(storage: Storage, entry: SceneEntry) {
        val path = entry.audio ?: return
        val current = lecture
        Thread {
            var source: String? = storage.file(path)?.takeIf { it.isFile && it.length() > 0 }?.absolutePath
            if (source == null && current is Lecture.Sample) {
                // Inside the app: copied out once, where the decoder can read it.
                source = runCatching {
                    val copy = File(cacheDir, "narration-${current.scene}-${path.substringAfterLast('/')}")
                    if (!copy.isFile || copy.length() != storage.sizeOf(path)) {
                        storage.open(path).use { input -> copy.outputStream().use { input.copyTo(it, 64 * 1024) } }
                    }
                    copy.absolutePath
                }.getOrNull()
            }
            if (source == null && current is Lecture.Saved) {
                val project = Lectures.project(this)
                if (project != null) {
                    source = SavedLectures.narrationUrl(project, current.entry, path)
                    runOnUiThread { loadedFraction = 0f }
                    keepNarration(project, current, path)
                }
            }
            val found = source ?: return@Thread
            val format = runCatching {
                val extractor = MediaExtractor()
                try {
                    extractor.setDataSource(found)
                    (0 until extractor.trackCount).map { extractor.getTrackFormat(it) }
                        .firstOrNull { it.getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true }
                        ?.let { it.getInteger(MediaFormat.KEY_SAMPLE_RATE) to it.getInteger(MediaFormat.KEY_CHANNEL_COUNT) }
                } finally {
                    extractor.release()
                }
            }
            runOnUiThread {
                val (rate, channels) = format.getOrNull() ?: run {
                    showNotice("Playing without narration: " +
                        (format.exceptionOrNull()?.message ?: "it could not be read"))
                    return@runOnUiThread
                }
                if (!isFinishing) view.attachAudio(found, rate, channels)
            }
        }.start()
    }

    /** Download a streamed narration into the lecture's folder, so it plays offline next time. */
    private fun keepNarration(project: SavedLectures.Project, current: Lecture.Saved, path: String) {
        Thread {
            runCatching {
                SavedLectures.fetchNarration(project, current.entry, path, current.dir, { narrationFetch.get() }) { p ->
                    if (p.total > 0) runOnUiThread { loadedFraction = p.done.toFloat() / p.total }
                }
            }
            runOnUiThread { loadedFraction = 1f }
        }.start()
    }

    // ---- layout -------------------------------------------------------------------------------------------------

    private fun build(): View {
        view = PanimView(this)

        stage = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        stage.addView(view, FrameLayout.LayoutParams(MATCH, WRAP, Gravity.CENTER))

        overlay = FrameLayout(this)
        stage.addView(overlay, FrameLayout.LayoutParams(MATCH, MATCH))
        val gestures = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent) = true
            override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                setControls(!controlsShown)
                return true
            }

            override fun onDoubleTap(e: MotionEvent): Boolean {
                val third = overlay.width / 3f
                when {
                    e.x < third -> skip(-SKIP_SECONDS)
                    e.x > 2 * third -> skip(SKIP_SECONDS)
                    else -> togglePlay()
                }
                return true
            }
        })
        overlay.setOnTouchListener { _, event -> gestures.onTouchEvent(event) }

        controls = FrameLayout(this)
        overlay.addView(controls, FrameLayout.LayoutParams(MATCH, MATCH))

        // Top: back, the title and the chapter, chapters, speed.
        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(4f), dp(6f), dp(8f), dp(24f))
            background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(0xB3000000.toInt(), 0))
        }
        top.addView(Ui.iconButton(this, Icon.BACK, description = "Back") { onBackPressedCompat() })
        val names = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        titleLabel = Ui.text(this, 15f, Ui.TEXT, Ui.MEDIUM, lines = 1).apply { text = lecture.title }
        chapterLabel = Ui.text(this, 12f, 0xCCFFFFFF.toInt(), lines = 1).apply { setPadding(0, dp(3f), 0, 0) }
        names.addView(titleLabel)
        names.addView(chapterLabel)
        top.addView(names, LinearLayout.LayoutParams(0, WRAP, 1f).apply { leftMargin = dp(4f) })
        speedButton = Ui.text(this, 13f, Ui.TEXT, Ui.MEDIUM).apply {
            text = "1×"
            gravity = Gravity.CENTER
            setPadding(dp(10f), dp(6f), dp(10f), dp(6f))
            background = Ui.pressable(0x33FFFFFF, dp(14f).toFloat())
            contentDescription = "Playback speed"
            setOnClickListener { chooseSpeed() }
        }
        top.addView(speedButton, LinearLayout.LayoutParams(WRAP, WRAP).apply { rightMargin = dp(4f) })
        top.addView(Ui.iconButton(this, Icon.CHAPTERS, description = "Chapters") { chooseChapter() })
        controls.addView(top, FrameLayout.LayoutParams(MATCH, WRAP, Gravity.TOP))

        // Middle: back ten seconds, play or pause, on ten seconds.
        val middle = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        middle.addView(Ui.iconButton(this, Icon.BACK10, size = 52f, fill = 0x40000000, description = "Back 10 seconds") {
            skip(-SKIP_SECONDS)
        })
        playButton = Ui.iconButton(this, Icon.PLAY, size = 68f, fill = 0x66000000, description = "Play") { togglePlay() }
        middle.addView(playButton, LinearLayout.LayoutParams(dp(68f), dp(68f)).apply {
            leftMargin = dp(28f)
            rightMargin = dp(28f)
        })
        middle.addView(Ui.iconButton(this, Icon.FORWARD10, size = 52f, fill = 0x40000000,
            description = "Forward 10 seconds") { skip(SKIP_SECONDS) })
        controls.addView(middle, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))

        // Bottom: the time, the timeline, the whole screen.
        val bottom = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8f), dp(28f), dp(8f), dp(2f))
            background = GradientDrawable(GradientDrawable.Orientation.BOTTOM_TOP, intArrayOf(0xB3000000.toInt(), 0))
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10f), 0, 0, 0)
        }
        timeLabel = Ui.text(this, 13f, Ui.TEXT, Ui.MEDIUM).apply { text = "0:00 / 0:00" }
        row.addView(timeLabel, LinearLayout.LayoutParams(0, WRAP, 1f))
        fullscreenButton = Ui.iconButton(this, Icon.FULLSCREEN, size = 40f, description = "Whole screen") {
            toggleFullscreen()
        }
        row.addView(fullscreenButton)
        bottom.addView(row)
        timeline = TimelineView(this)
        timeline.listener = object : TimelineView.Listener {
            private var wasPlaying = false
            override fun onScrubStart() {
                scrubbing = true
                wasPlaying = wantPlaying
                main.removeCallbacks(hideControls)
            }

            override fun onScrub(fraction: Float) {
                view.seekToFrame((fraction * (frameCount - 1)).toInt())
                showTime(fraction * (frameCount - 1))
            }

            override fun onScrubEnd(fraction: Float) {
                scrubbing = false
                view.seekToFrame((fraction * (frameCount - 1)).toInt())
                endShown = false
                endCard.visibility = View.GONE
                if (wasPlaying) scheduleHide()
            }
        }
        bottom.addView(timeline, LinearLayout.LayoutParams(MATCH, WRAP))
        controls.addView(bottom, FrameLayout.LayoutParams(MATCH, WRAP, Gravity.BOTTOM))

        // While getting ready or waiting on the network.
        val loadingBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        spinner = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = android.content.res.ColorStateList.valueOf(Ui.ACCENT)
        }
        loadingBox.addView(spinner, LinearLayout.LayoutParams(dp(48f), dp(48f)))
        loadingLabel = Ui.text(this, 13f, Ui.TEXT).apply {
            gravity = Gravity.CENTER
            setPadding(dp(16f), dp(12f), dp(16f), 0)
        }
        loadingBox.addView(loadingLabel)
        overlay.addView(loadingBox, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))

        // "−10 s" / "+10 s" where a double tap landed.
        hint = Ui.text(this, 15f, Ui.TEXT, Ui.MEDIUM).apply {
            setPadding(dp(16f), dp(10f), dp(16f), dp(10f))
            background = Ui.rounded(0x99000000.toInt(), dp(22f).toFloat())
            visibility = View.GONE
        }
        overlay.addView(hint, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))

        // A line with an action: "Resumed at 4:12 · Start over", a problem.
        notice = Ui.text(this, 13f, Ui.TEXT).apply {
            setPadding(dp(14f), dp(10f), dp(14f), dp(10f))
            background = Ui.rounded(0xE6202329.toInt(), dp(10f).toFloat())
            visibility = View.GONE
        }
        overlay.addView(notice, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
            .apply { bottomMargin = dp(84f) })

        // At the end: watch again, or the next lecture of the series.
        endCard = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            visibility = View.GONE
            setBackgroundColor(0xB3000000.toInt())
            isClickable = true
        }
        overlay.addView(endCard, FrameLayout.LayoutParams(MATCH, MATCH))

        // Below the picture when the phone is upright: the lecture, and its chapters to jump to.
        details = ScrollView(this).apply { setBackgroundColor(Ui.BG) }
        val words = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18f), dp(16f), dp(18f), dp(28f))
        }
        words.addView(Ui.text(this, 19f, Ui.TEXT, Ui.MEDIUM).apply {
            text = lecture.title
            setLineSpacing(0f, 1.15f)
        })
        infoLabel = Ui.text(this, 13f, Ui.MUTED).apply {
            text = lecture.subtitle
            setPadding(0, dp(6f), 0, dp(14f))
            setLineSpacing(0f, 1.2f)
        }
        words.addView(infoLabel)
        chapterList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        words.addView(chapterList)
        details.addView(words)

        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            addView(stage)
            addView(details)
        }
        return root
    }

    /** Upright: the picture across the top, the lecture's details under it. Sideways: the picture, whole screen. */
    private fun layoutFor(orientation: Int) {
        val landscape = orientation == Configuration.ORIENTATION_LANDSCAPE
        val width = resources.displayMetrics.widthPixels
        stage.layoutParams = if (landscape) LinearLayout.LayoutParams(MATCH, 0, 1f)
        else LinearLayout.LayoutParams(MATCH, width * 9 / 16)
        details.visibility = if (landscape) View.GONE else View.VISIBLE
        details.layoutParams = LinearLayout.LayoutParams(MATCH, 0, 1f)
        root.fitsSystemWindows = !landscape
        immersive(landscape)
        fullscreenButton.setImageDrawable(IconDrawable(if (landscape) Icon.EXIT_FULLSCREEN else Icon.FULLSCREEN, Ui.TEXT))
        root.requestLayout()
    }

    @Suppress("DEPRECATION")
    private fun immersive(on: Boolean) {
        window.decorView.systemUiVisibility = if (on) {
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        } else 0
    }

    private fun toggleFullscreen() {
        val landscape = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
        requestedOrientation = if (landscape) ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
        else ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        if (landscape) main.postDelayed({ requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED }, 1500)
        scheduleHide()
    }

    private fun onBackPressedCompat() {
        @Suppress("DEPRECATION")
        onBackPressed()
    }

    // ---- the details panel ----------------------------------------------------------------------------------------

    private fun fillDetails() {
        val seconds = frameCount.toDouble() / fps
        val bits = ArrayList<String>()
        bits.add(lecture.subtitle)
        bits.add(Ui.length(seconds))
        if (chapters.isNotEmpty()) bits.add("${chapters.size} chapters")
        infoLabel.text = bits.filter { it.isNotBlank() }.joinToString("  ·  ")
        chapterList.removeAllViews()
        if (chapters.isEmpty()) return
        chapterList.addView(Ui.text(this, 12.5f, Ui.MUTED, Ui.MEDIUM).apply {
            text = "CHAPTERS"
            letterSpacing = 0.08f
            setPadding(0, dp(4f), 0, dp(8f))
        })
        chapters.forEachIndexed { index, chapter ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12f), dp(12f), dp(12f), dp(12f))
                background = Ui.pressable(0, dp(10f).toFloat())
                isClickable = true
                setOnClickListener { jumpTo(chapter) }
                tag = index
            }
            row.addView(Ui.text(this, 13f, Ui.ACCENT, Ui.MEDIUM).apply {
                text = Ui.clock(chapter.frame.toDouble() / fps)
                minWidth = dp(56f)
            })
            row.addView(Ui.text(this, 14.5f, Ui.TEXT, lines = 2).apply { text = chapter.title },
                LinearLayout.LayoutParams(0, WRAP, 1f))
            chapterList.addView(row, LinearLayout.LayoutParams(MATCH, WRAP))
        }
    }

    private fun currentChapter(frame: Int): Int = chapters.indexOfLast { it.frame <= frame }

    // ---- playing --------------------------------------------------------------------------------------------------

    private fun play() {
        if (frames == null) return
        val playback = view.playback ?: return
        if (playback.currentFrame() >= frameCount - 1) view.seekToFrame(0)
        endShown = false
        endCard.visibility = View.GONE
        requestFocus()
        wantPlaying = true
        heldForNetwork = false
        view.play()
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        playButton.setImageDrawable(IconDrawable(Icon.PAUSE, Ui.TEXT))
        playButton.contentDescription = "Pause"
        scheduleHide()
    }

    private fun pause() {
        wantPlaying = false
        heldForNetwork = false
        view.pause()
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        playButton.setImageDrawable(IconDrawable(Icon.PLAY, Ui.TEXT))
        playButton.contentDescription = "Play"
        main.removeCallbacks(hideControls)
        setControls(true)
        remember()
    }

    private fun togglePlay() {
        if (wantPlaying) pause() else play()
    }

    private fun seekSeconds(seconds: Double) {
        val frame = (seconds * fps).toInt().coerceIn(0, frameCount - 1)
        view.seekToFrame(frame)
        endShown = false
        endCard.visibility = View.GONE
        showTime(frame.toFloat())
    }

    private fun skip(seconds: Double) {
        val playback = view.playback ?: return
        seekSeconds(playback.currentFrame().toDouble() / fps + seconds)
        hint.text = if (seconds < 0) "« ${(-seconds).toInt()} s" else "${seconds.toInt()} s »"
        (hint.layoutParams as FrameLayout.LayoutParams).gravity =
            Gravity.CENTER_VERTICAL or if (seconds < 0) Gravity.START else Gravity.END
        (hint.layoutParams as FrameLayout.LayoutParams).leftMargin = dp(40f)
        (hint.layoutParams as FrameLayout.LayoutParams).rightMargin = dp(40f)
        hint.requestLayout()
        hint.visibility = View.VISIBLE
        hint.alpha = 1f
        hint.animate().alpha(0f).setStartDelay(500).setDuration(300).withEndAction { hint.visibility = View.GONE }
        if (controlsShown) scheduleHide()
    }

    private fun jumpTo(chapter: Chapter) {
        seekSeconds(chapter.frame.toDouble() / fps)
        if (!wantPlaying) play()
    }

    private fun chooseChapter() {
        if (chapters.isEmpty()) {
            showNotice("This lecture has no chapters.")
            return
        }
        val now = currentChapter(view.playback?.currentFrame() ?: 0)
        val names = chapters.mapIndexed { i, c ->
            "${if (i == now) "▶ " else ""}${Ui.clock(c.frame.toDouble() / fps)}   ${c.title}"
        }.toTypedArray()
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Chapters")
            .setItems(names) { _, which -> jumpTo(chapters[which]) }
            .show()
    }

    private fun chooseSpeed() {
        val names = SPEEDS.map { if (it == speed) "✓  ${label(it)}" else "     ${label(it)}" }.toTypedArray()
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Playback speed")
            .setItems(names) { _, which ->
                speed = SPEEDS[which]
                view.setSpeed(speed)
                speedButton.text = label(speed)
            }
            .show()
    }

    private fun label(value: Double): String =
        (if (value == value.toInt().toDouble()) value.toInt().toString() else value.toString()) + "×"

    // ---- controls -------------------------------------------------------------------------------------------------

    private fun setControls(show: Boolean) {
        controlsShown = show
        controls.animate().cancel()
        if (show) {
            controls.visibility = View.VISIBLE
            controls.animate().alpha(1f).setDuration(150)
            if (wantPlaying) scheduleHide()
        } else {
            controls.animate().alpha(0f).setDuration(220).withEndAction {
                if (!controlsShown) controls.visibility = View.INVISIBLE
            }
        }
    }

    private fun scheduleHide() {
        main.removeCallbacks(hideControls)
        if (wantPlaying) main.postDelayed(hideControls, HIDE_AFTER_MILLIS)
    }

    private fun loading(on: Boolean, text: String = "", share: Float = -1f) {
        spinner.visibility = if (on) View.VISIBLE else View.GONE
        loadingLabel.visibility = if (on && text.isNotEmpty()) View.VISIBLE else View.GONE
        loadingLabel.text = text
        if (on) {
            if (share >= 0f) {
                spinner.isIndeterminate = false
                spinner.max = 1000
                spinner.progress = (share * 1000).toInt()
            } else spinner.isIndeterminate = true
        }
    }

    private fun showNotice(text: String, action: String? = null, onAction: (() -> Unit)? = null) {
        notice.text = if (action != null) "$text    $action" else text
        notice.setTextColor(Ui.TEXT)
        if (action != null) {
            val span = android.text.SpannableString(notice.text)
            span.setSpan(android.text.style.ForegroundColorSpan(Ui.ACCENT), text.length, span.length, 0)
            span.setSpan(android.text.style.StyleSpan(android.graphics.Typeface.BOLD), text.length, span.length, 0)
            notice.text = span
        }
        notice.setOnClickListener {
            notice.visibility = View.GONE
            onAction?.invoke()
        }
        notice.isClickable = onAction != null
        notice.visibility = View.VISIBLE
        notice.alpha = 1f
        notice.animate().cancel()
        notice.animate().alpha(0f).setStartDelay(5000).setDuration(400).withEndAction { notice.visibility = View.GONE }
    }

    private fun showEnd() {
        endShown = true
        endCard.removeAllViews()
        fun choice(icon: Icon, label: String, action: () -> Unit) = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(18f), dp(10f), dp(18f), dp(10f))
            background = Ui.pressable(0, dp(14f).toFloat())
            isClickable = true
            setOnClickListener { action() }
            addView(ImageView(context).apply {
                setImageDrawable(IconDrawable(icon, Ui.TEXT))
                val pad = dp(14f)
                setPadding(pad, pad, pad, pad)
                background = Ui.rounded(0x33FFFFFF, dp(30f).toFloat())
            }, LinearLayout.LayoutParams(dp(60f), dp(60f)))
            addView(Ui.text(context, 13f, Ui.TEXT, Ui.MEDIUM, lines = 2).apply {
                text = label
                gravity = Gravity.CENTER
                maxWidth = dp(180f)
                setPadding(0, dp(8f), 0, 0)
            })
        }
        endCard.addView(choice(Icon.REPLAY, "Watch again") {
            seekSeconds(0.0)
            play()
        })
        val current = lecture
        val next = (current as? Lecture.Saved)?.let { Lectures.nextInSeries(this, it.entry) }
        if (next != null) {
            endCard.addView(choice(Icon.NEXT, "Up next: ${next.shortTitle}") {
                Lectures.forget(this, lecture.key)
                startActivity(intent(this, Lecture.Saved(next, File(Lectures.savedRoot(this), next.buildId)), false))
                finish()
            })
        }
        endCard.visibility = View.VISIBLE
        setControls(false)
    }

    // ---- the clock ---------------------------------------------------------------------------------------------

    /** Fifteen times a second: the timeline, the time, the chapter, buffering, the end. */
    private fun sync() {
        val playback = view.playback ?: return
        // The network fell behind the narration: hold the picture with it, as a video buffers.
        if (wantPlaying && !heldForNetwork && view.audioBuffering) {
            heldForNetwork = true
            view.pause()
            loading(true, "Buffering…")
        } else if (heldForNetwork && !view.audioBuffering) {
            heldForNetwork = false
            loading(false)
            if (wantPlaying) view.play()
        }

        val frame = playback.currentFrame()
        if (!scrubbing) {
            timeline.played = frame.toFloat() / (frameCount - 1).coerceAtLeast(1)
            showTime(frame.toFloat())
        }
        timeline.loaded = loadedFraction.coerceAtLeast(timeline.played)

        val chapter = currentChapter(frame)
        if (chapter != shownChapter) {
            shownChapter = chapter
            chapterLabel.text = chapters.getOrNull(chapter)?.let { "Chapter ${chapter + 1} · ${it.title}" }
                ?: lecture.subtitle
            for (i in 0 until chapterList.childCount) {
                val row = chapterList.getChildAt(i)
                row.background = if (row.tag == chapter) Ui.rounded(Ui.SURFACE_HIGH, dp(10f).toFloat())
                else Ui.pressable(0, dp(10f).toFloat())
            }
        }

        if (wantPlaying && !playback.playing && frame >= frameCount - 1 && !endShown) {
            wantPlaying = false
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            playButton.setImageDrawable(IconDrawable(Icon.REPLAY, Ui.TEXT))
            Lectures.forget(this, lecture.key)
            showEnd()
        }

        val now = System.currentTimeMillis()
        if (wantPlaying && now - lastSaved > 5000) remember()
    }

    private fun showTime(frame: Float) {
        val total = frameCount.toDouble() / fps
        timeLabel.text = "${Ui.clock(frame / fps.toDouble())} / ${Ui.clock(total)}"
    }

    /** Where the viewer got to, for the library's progress bar and for resuming. */
    private fun remember() {
        val playback = view.playback ?: return
        if (frames == null || endShown) return
        lastSaved = System.currentTimeMillis()
        Lectures.remember(this, lecture.key, playback.currentFrame().toDouble() / fps, frameCount.toDouble() / fps)
    }

    // ---- audio focus ----------------------------------------------------------------------------------------------

    private fun requestFocus() {
        val manager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val request = focus ?: AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setOnAudioFocusChangeListener { change ->
                // A call, another app's sound: stop, and let the viewer start again.
                if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
                    main.post { if (wantPlaying) pause() }
                }
            }
            .build().also { focus = it }
        manager.requestAudioFocus(request)
    }

    private fun abandonFocus() {
        val request = focus ?: return
        (getSystemService(Context.AUDIO_SERVICE) as AudioManager).abandonAudioFocusRequest(request)
    }

    private fun dp(value: Float) = Ui.dp(this, value)

    private val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    private val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
}
