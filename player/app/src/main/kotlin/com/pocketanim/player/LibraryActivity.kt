package com.pocketanim.player

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.LruCache
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import com.pocketanim.android.Thumbnails
import com.pocketanim.core.Library
import com.pocketanim.core.LibraryImport
import com.pocketanim.core.SavedLectures
import java.io.File
import java.util.concurrent.Executors

/**
 * The library: what there is to watch, as cards with a still, its length, how far it was watched, and whether it
 * is on the phone or streams. Tap to play; hold for more (play from the start, keep for offline, remove).
 */
class LibraryActivity : Activity() {

    private enum class Tab(val label: String) { SAVED("Saved"), PHONE("On this phone"), SAMPLES("Samples") }

    private var tab = Tab.SAVED
    private lateinit var list: LinearLayout
    private lateinit var status: TextView
    private lateinit var spinner: ProgressBar
    private lateinit var tabs: LinearLayout
    private var refreshing = false

    private val stillMaker = Executors.newSingleThreadExecutor()
    private val stills = LruCache<String, Bitmap>(24)

    /** Lectures being kept for offline right now, with how far they have got. */
    private val keeping = HashMap<String, String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Ui.BG
        window.navigationBarColor = Ui.BG
        setContentView(build())
        tab = if (Lectures.project(this) == null && Lectures.cachedCatalog(this).isEmpty()) {
            if (Lectures.onPhone(this).isNotEmpty()) Tab.PHONE else Tab.SAMPLES
        } else Tab.SAVED
        show()
        if (Lectures.project(this) != null) refresh(quiet = true)
        handle(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handle(intent)
    }

    override fun onResume() {
        super.onResume()
        // Back from the player: progress bars and "on the phone" may have changed.
        show()
    }

    override fun onDestroy() {
        super.onDestroy()
        stillMaker.shutdownNow()
    }

    private fun handle(intent: Intent?) {
        if (intent?.action == Intent.ACTION_VIEW) intent.data?.let(::importFrom)
    }

    // ---- layout -----------------------------------------------------------------------------------------------

    private fun build(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Ui.BG)
            fitsSystemWindows = true
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18f), dp(14f), dp(8f), dp(6f))
        }
        val mark = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(View(context).apply {
                background = Ui.rounded(Ui.ACCENT, dp(6f).toFloat())
                layoutParams = LinearLayout.LayoutParams(dp(22f), dp(22f)).apply { rightMargin = dp(10f) }
            })
            addView(Ui.text(context, 21f, Ui.TEXT, Ui.MEDIUM).apply { text = "pocketanim" })
        }
        header.addView(mark, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        spinner = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = android.content.res.ColorStateList.valueOf(Ui.ACCENT)
            visibility = View.GONE
        }
        header.addView(spinner, LinearLayout.LayoutParams(dp(22f), dp(22f)).apply { rightMargin = dp(8f) })
        header.addView(Ui.iconButton(this, Icon.IMPORT, description = "Import a lecture") { pickZip() })
        header.addView(Ui.iconButton(this, Icon.REFRESH, description = "Refresh") { refresh(quiet = false) })
        header.addView(Ui.iconButton(this, Icon.MORE, description = "Settings") { configure() })
        root.addView(header)

        tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(14f), dp(4f), dp(14f), dp(8f))
        }
        root.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(tabs)
        })

        status = Ui.text(this, 13.5f, Ui.MUTED).apply {
            setPadding(dp(18f), dp(4f), dp(18f), dp(8f))
            visibility = View.GONE
            setLineSpacing(0f, 1.2f)
        }
        root.addView(status)

        list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12f), 0, dp(12f), dp(24f))
        }
        root.addView(ScrollView(this).apply {
            isVerticalScrollBarEnabled = false
            addView(list)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        return root
    }

    private fun drawTabs() {
        tabs.removeAllViews()
        for (t in Tab.values()) {
            val selected = t == tab
            tabs.addView(Ui.text(this, 14f, if (selected) Ui.BG else Ui.TEXT, Ui.MEDIUM).apply {
                text = t.label
                setPadding(dp(16f), dp(8f), dp(16f), dp(8f))
                background = Ui.pressable(if (selected) Ui.ACCENT else Ui.SURFACE_HIGH, dp(18f).toFloat())
                isClickable = true
                setOnClickListener {
                    tab = t
                    show()
                }
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { rightMargin = dp(8f) })
        }
    }

    /** Fill the list for the current tab. */
    private fun show() {
        drawTabs()
        list.removeAllViews()
        status.visibility = View.GONE
        when (tab) {
            Tab.SAVED -> {
                val project = Lectures.project(this)
                val saved = Lectures.saved(this)
                when {
                    project == null -> say("Lectures you save in the web app appear here. Tap ⋮ to say which " +
                        "Supabase project they are saved to.")
                    saved.isEmpty() && !refreshing -> say("No saved lectures yet in " +
                        "${project.url.removePrefix("https://")}. In the web app, Save after a build, then " +
                        "refresh here.")
                }
                var series: String? = null
                for (lecture in saved) {
                    if (lecture.entry.series != series) {
                        series = lecture.entry.series
                        list.addView(Ui.text(this, 13f, Ui.MUTED, Ui.MEDIUM, lines = 1).apply {
                            text = series.uppercase()
                            letterSpacing = 0.06f
                            setPadding(dp(6f), dp(16f), dp(6f), dp(8f))
                        })
                    }
                    list.addView(card(lecture))
                }
            }
            Tab.PHONE -> {
                val here = Lectures.onPhone(this)
                if (here.isEmpty()) say("Nothing kept on the phone yet. A saved lecture is kept once you play " +
                    "it (or hold it and choose Keep for offline); a lecture zip opens with Import.")
                here.forEach { list.addView(card(it)) }
            }
            Tab.SAMPLES -> {
                val samples = Lectures.samples(this)
                if (samples.isEmpty()) say("This build has no sample scenes.")
                samples.forEach { list.addView(card(it)) }
            }
        }
    }

    private fun say(message: String) {
        status.text = message
        status.visibility = View.VISIBLE
    }

    /** One lecture's card: still, length, progress, title, where it comes from. */
    private fun card(lecture: Lecture): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8f), dp(8f), dp(10f), dp(8f))
            background = Ui.pressable(Ui.SURFACE, dp(14f).toFloat())
            isClickable = true
            setOnClickListener { play(lecture, fromStart = false) }
            setOnLongClickListener {
                more(lecture)
                true
            }
        }

        val still = FrameLayout(this).apply {
            background = Ui.rounded(Ui.SURFACE_HIGH, dp(10f).toFloat())
            clipToOutline = true
        }
        val picture = ImageView(this).apply { scaleType = ImageView.ScaleType.CENTER_CROP }
        still.addView(placeholder(lecture), FrameLayout.LayoutParams(MATCH, MATCH))
        still.addView(picture, FrameLayout.LayoutParams(MATCH, MATCH))
        lecture.seconds?.let { seconds ->
            still.addView(Ui.text(this, 11f, Ui.TEXT, Ui.MEDIUM).apply {
                text = Ui.clock(seconds)
                setPadding(dp(5f), dp(2f), dp(5f), dp(2f))
                background = Ui.rounded(0xCC000000.toInt(), dp(4f).toFloat())
            }, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.BOTTOM or Gravity.END).apply {
                setMargins(0, 0, dp(5f), dp(6f))
            })
        }
        Lectures.progress(this, lecture.key)?.let { (at, of) ->
            val fraction = (at / of).toFloat().coerceIn(0f, 1f)
            if (fraction > 0.01f) {
                val bar = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    addView(View(context).apply { setBackgroundColor(Ui.ACCENT) },
                        LinearLayout.LayoutParams(0, MATCH, fraction))
                    addView(View(context).apply { setBackgroundColor(0x66FFFFFF) },
                        LinearLayout.LayoutParams(0, MATCH, 1f - fraction))
                }
                still.addView(bar, FrameLayout.LayoutParams(MATCH, dp(3f), Gravity.BOTTOM))
            }
        }
        val stillWidth = dp(136f)
        card.addView(still, LinearLayout.LayoutParams(stillWidth, stillWidth * 9 / 16))
        loadStill(lecture, picture)

        val words = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14f), 0, 0, 0)
        }
        words.addView(Ui.text(this, 15.5f, Ui.TEXT, Ui.MEDIUM, lines = 2).apply {
            text = lecture.title
            setLineSpacing(0f, 1.1f)
        })
        words.addView(Ui.text(this, 12.5f, Ui.MUTED, lines = 1).apply {
            text = lecture.subtitle
            setPadding(0, dp(5f), 0, 0)
        })
        val chips = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(8f), 0, 0)
        }
        when (lecture) {
            is Lecture.Saved -> {
                val busy = keeping[lecture.key]
                when {
                    busy != null -> chips.addView(Ui.chip(this, busy, Ui.ACCENT, Ui.ACCENT_DARK))
                    lecture.onPhone -> chips.addView(Ui.chip(this, "✓ On phone", Ui.GOOD, 0xFF173325.toInt()))
                    else -> chips.addView(Ui.chip(this, "Streams · ${Ui.bytes(lecture.entry.libraryBytes)}",
                        Ui.MUTED, Ui.SURFACE_HIGH))
                }
                if (!lecture.entry.narrated) chips.addView(space())
                if (!lecture.entry.narrated) chips.addView(Ui.chip(this, "Silent", Ui.MUTED, Ui.SURFACE_HIGH))
            }
            is Lecture.Imported -> chips.addView(Ui.chip(this, "✓ On phone", Ui.GOOD, 0xFF173325.toInt()))
            is Lecture.Sample -> chips.addView(Ui.chip(this, "Sample", Ui.MUTED, Ui.SURFACE_HIGH))
        }
        words.addView(chips)
        card.addView(words, LinearLayout.LayoutParams(0, WRAP, 1f))

        return FrameLayout(this).apply {
            setPadding(0, dp(5f), 0, dp(5f))
            addView(card)
        }
    }

    private fun space() = View(this).apply { layoutParams = LinearLayout.LayoutParams(dp(6f), 1) }

    /** Before a still exists (a lecture not on the phone yet): its series' first letter on a colour of its own. */
    private fun placeholder(lecture: Lecture): View {
        val hue = (lecture.subtitle.hashCode() and 0x7fffffff) % 360
        val a = android.graphics.Color.HSVToColor(floatArrayOf(hue.toFloat(), 0.45f, 0.35f))
        val b = android.graphics.Color.HSVToColor(floatArrayOf(((hue + 40) % 360).toFloat(), 0.55f, 0.18f))
        return FrameLayout(this).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(a, b))
            addView(Ui.text(context, 26f, 0xCCFFFFFF.toInt(), Ui.MEDIUM).apply {
                text = (if (lecture is Lecture.Saved) lecture.entry.series else lecture.title).take(1).uppercase()
            }, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
        }
    }

    /** The lecture's still, drawn once from the lecture itself (off the main thread) and kept. */
    private fun loadStill(lecture: Lecture, into: ImageView) {
        stills.get(lecture.key)?.let {
            into.setImageBitmap(it)
            return
        }
        if (lecture is Lecture.Saved && !lecture.onPhone) return
        val file = File(Lectures.stills(this), "${lecture.key}.png")
        into.tag = lecture.key
        stillMaker.execute {
            val bitmap = Thumbnails.cached(file) {
                val library = Library.load(Lectures.storageOf(this, lecture))
                val entry = library.scenes.first()
                val frames = library.open(entry.name)
                Thumbnails.render(frames, Thumbnails.pick(frames, entry.chapters.map { it.frame }), dp(272f))
            } ?: return@execute
            runOnUiThread {
                stills.put(lecture.key, bitmap)
                if (into.tag == lecture.key) into.setImageBitmap(bitmap)
            }
        }
    }

    // ---- actions ----------------------------------------------------------------------------------------------

    private fun play(lecture: Lecture, fromStart: Boolean) {
        startActivity(PlayerActivity.intent(this, lecture, fromStart))
    }

    private fun more(lecture: Lecture) {
        val actions = ArrayList<Pair<String, () -> Unit>>()
        actions.add("Play" to { play(lecture, fromStart = false) })
        if (Lectures.progress(this, lecture.key) != null) {
            actions.add("Play from the start" to { play(lecture, fromStart = true) })
        }
        if (lecture is Lecture.Saved && !lecture.onPhone && keeping[lecture.key] == null) {
            actions.add("Keep for offline" to { keep(lecture) })
        }
        if (lecture !is Lecture.Sample && Lectures.dirOf(lecture)?.isDirectory == true) {
            actions.add("Remove from phone" to {
                Lectures.remove(this, lecture)
                stills.remove(lecture.key)
                show()
            })
        }
        AlertDialog.Builder(this)
            .setTitle(lecture.title)
            .setItems(actions.map { it.first }.toTypedArray()) { _, which -> actions[which].second() }
            .show()
    }

    /** Download a saved lecture, narration and all, so it plays without the network. */
    private fun keep(lecture: Lecture.Saved) {
        val project = Lectures.project(this) ?: return
        keeping[lecture.key] = "Downloading…"
        show()
        Thread {
            val result = runCatching {
                if (!lecture.onPhone) {
                    SavedLectures.download(project, lecture.entry, lecture.dir) { progress ->
                        keeping[lecture.key] = "Downloading · $progress"
                        runOnUiThread { if (tab == Tab.SAVED) show() }
                    }
                    File(lecture.dir, Lectures.TITLE_FILE).writeText(lecture.title)
                }
                val library = Library.load(LibraryImport.DirStorage(lecture.dir))
                library.scenes.firstOrNull()?.audio?.let { audio ->
                    SavedLectures.fetchNarration(project, lecture.entry, audio, lecture.dir) { progress ->
                        keeping[lecture.key] = "Narration · $progress"
                        runOnUiThread { if (tab == Tab.SAVED) show() }
                    }
                }
            }
            runOnUiThread {
                keeping.remove(lecture.key)
                result.exceptionOrNull()?.let {
                    say("Could not keep ${lecture.title}: ${it.message}")
                    Ui.showError(this, "Could not keep “${lecture.title}”", it)
                }
                show()
            }
        }.start()
    }

    private fun refresh(quiet: Boolean) {
        val project = Lectures.project(this)
        if (project == null) {
            if (!quiet) configure()
            return
        }
        if (refreshing) return
        refreshing = true
        spinner.visibility = View.VISIBLE
        Thread {
            val result = runCatching { Lectures.refreshCatalog(this, project) }
            runOnUiThread {
                refreshing = false
                spinner.visibility = View.GONE
                show()
                result.exceptionOrNull()?.let {
                    if (tab == Tab.SAVED) say("Could not reach the saved lectures (showing what was here last): " +
                        "${it.message}")
                    if (!quiet) Ui.showError(this, "Could not reach the saved lectures", it)
                }
            }
        }.start()
    }

    /** Ask for the project's URL and anon key (Supabase: Project Settings → API). */
    private fun configure() {
        val known = Lectures.project(this)
        val url = EditText(this).apply {
            hint = "https://<project>.supabase.co"
            setText(known?.url ?: "")
            setSingleLine()
        }
        val key = EditText(this).apply {
            hint = "anon / publishable key"
            setText(known?.anonKey ?: "")
            setSingleLine()
        }
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20f), dp(8f), dp(20f), 0)
            addView(url)
            addView(key)
        }
        AlertDialog.Builder(this)
            .setTitle("Where lectures are saved")
            .setMessage("The Supabase project the web app saves to: its URL and anon key (Project Settings → API).")
            .setView(form)
            .setPositiveButton("Save") { _, _ ->
                Lectures.setProject(this, url.text.toString(), key.text.toString())
                tab = Tab.SAVED
                show()
                refresh(quiet = false)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ---- importing a zip ----------------------------------------------------------------------------------------

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
            say("No file picker on this phone: ${e.message}")
        }
    }

    @Deprecated("Activity result API needs AndroidX; this app has no dependencies")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == PICK_ZIP && resultCode == RESULT_OK) data?.data?.let(::importFrom)
    }

    /** Unpack a lecture's zip (checked file by file before it replaces anything), then play it. */
    private fun importFrom(uri: Uri) {
        val name = importName(uri)
        tab = Tab.PHONE
        show()
        say("Importing $name…")
        spinner.visibility = View.VISIBLE
        Thread {
            val dest = File(Lectures.importRoot(this), name)
            val result = runCatching {
                val input = contentResolver.openInputStream(uri) ?: error("cannot read $uri")
                input.use { LibraryImport.unpack(it, dest) }
            }
            runOnUiThread {
                spinner.visibility = View.GONE
                show()
                result.fold(
                    onSuccess = { play(Lecture.Imported(dest, name.replace('-', ' ')), fromStart = false) },
                    onFailure = {
                        say("Could not import $name: ${it.message}")
                        Ui.showError(this, "Could not import $name", it)
                    },
                )
            }
        }.start()
    }

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

    private fun dp(value: Float) = Ui.dp(this, value)

    private companion object {
        const val PICK_ZIP = 7
        const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        const val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
    }
}
