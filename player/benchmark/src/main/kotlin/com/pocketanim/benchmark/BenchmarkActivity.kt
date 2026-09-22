package com.pocketanim.benchmark

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.pocketanim.android.AssetStorage
import com.pocketanim.android.CanvasSink
import com.pocketanim.android.FileStorage
import com.pocketanim.android.SurfaceCanvas
import com.pocketanim.core.Benchmark
import com.pocketanim.core.FrameTarget
import com.pocketanim.core.Library
import com.pocketanim.core.RenderOptions
import com.pocketanim.core.SceneResult
import com.pocketanim.core.Storage
import java.io.File
import java.util.Locale

/**
 * The device gate, as an app you can install and run.
 *
 * Draws to a real `SurfaceView` through the real `CanvasSink` — the same code
 * path playback uses — because a benchmark that renders to an off-screen bitmap
 * would skip the part most likely to be slow. Results go to logcat under the
 * tag `panim` and to a file, so a run can be collected without reading the
 * screen.
 *
 *   adb shell am start -n com.pocketanim.benchmark/.BenchmarkActivity
 *   adb logcat -s panim:I
 *   adb shell run-as com.pocketanim.benchmark cat files/benchmark.json
 *
 * Optional extras:
 *   --es scenes "ThreeDCamera CartopyMap"   one or more, default all
 *   --es library /sdcard/panim-library      a pushed library instead of assets
 */
class BenchmarkActivity : Activity(), SurfaceHolder.Callback {

    private lateinit var surface: SurfaceView
    private lateinit var output: TextView
    private lateinit var shareButton: Button
    private lateinit var copyButton: Button
    private val lines = StringBuilder()
    private var started = false

    /** The finished report. Null until the run completes. */
    @Volatile private var resultJson: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // A benchmark that lets the screen sleep halfway through measures the
        // screen going to sleep.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        surface = SurfaceView(this)
        // Render into a fixed 16:9 buffer rather than whatever the layout
        // happens to give. The first device run measured a 2148x411 surface --
        // a fifth of the pixels a full frame has, at an aspect ratio that
        // stretched every scene -- so its rasterisation numbers were neither
        // right for that phone nor comparable with any other. The buffer is
        // scaled to the view for display, which is why the preview can look
        // squashed while the measurement does not.
        surface.holder.setFixedSize(BUFFER_WIDTH, BUFFER_HEIGHT)
        output = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.BLACK)
            textSize = 9f
            typeface = android.graphics.Typeface.MONOSPACE
            text = "warming up..."
        }

        // Getting the results off the phone should not require a cable.
        // `run-as` needs adb, which is a lot of setup for someone who just ran
        // a benchmark and wants to send the numbers on.
        shareButton = Button(this).apply {
            text = "Share results"
            isEnabled = false
            setOnClickListener { shareResults() }
        }
        copyButton = Button(this).apply {
            text = "Copy JSON"
            isEnabled = false
            setOnClickListener { copyResults() }
        }
        val buttons = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(shareButton, LinearLayout.LayoutParams(0, WRAP, 1f))
            addView(copyButton, LinearLayout.LayoutParams(0, WRAP, 1f))
        }

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        // The surface gets most of the window: rasterisation cost scales with
        // the pixels actually touched, so measuring in a thumbnail would
        // understate it.
        root.addView(surface, LinearLayout.LayoutParams(MATCH, 0, 3f))
        root.addView(buttons, LinearLayout.LayoutParams(MATCH, WRAP))
        root.addView(
            ScrollView(this).apply { addView(output) },
            LinearLayout.LayoutParams(MATCH, 0, 2f),
        )
        setContentView(root)

        surface.holder.addCallback(this)
    }

    override fun surfaceCreated(holder: SurfaceHolder) = Unit

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        if (started) return
        started = true
        Thread({ runAll(holder, width, height) }, "panim-benchmark").start()
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) = Unit

    private fun report(line: String) {
        Log.i(TAG, line)
        lines.append(line).append('\n')
        runOnUiThread { output.text = lines.toString() }
    }

    private fun runAll(holder: SurfaceHolder, width: Int, height: Int) {
        val storage: Storage = intent.getStringExtra("library")
            ?.let { FileStorage(File(it)) }
            ?: AssetStorage(assets)

        val library = try {
            Library.load(storage)
        } catch (e: Exception) {
            report("cannot load the library: ${e.message}")
            return
        }

        val missing = library.missing()
        if (missing.isNotEmpty()) {
            report("library incomplete, ${missing.size} path(s) missing: ${missing.take(3)}")
            return
        }

        val wanted = intent.getStringExtra("scenes")?.split(" ")?.filter { it.isNotBlank() }
        val scenes = library.scenes.filter { wanted == null || it.name in wanted }

        val sink = CanvasSink()

        // Locking a canvas and posting it is part of what a frame costs, so the
        // target does it per frame rather than the benchmark drawing into
        // something off-screen.
        val surfaceCanvas = SurfaceCanvas(holder)
        val target = FrameTarget { draw ->
            val canvas = surfaceCanvas.acquire()
            if (canvas != null) {
                try {
                    val depth = sink.begin(canvas, width, height, Color.BLACK)
                    try {
                        draw(sink)
                    } finally {
                        sink.end(depth)
                    }
                } finally {
                    surfaceCanvas.release(canvas)
                }
            }
        }

        // Acquire one frame before reporting, so the canvas kind printed below
        // is what was actually obtained rather than what was hoped for. A run
        // that silently fell back to software raster would otherwise look
        // exactly like one that did not, which is how the first round of
        // numbers came to be misread.
        target.render { }

        report(deviceLine())
        report("buffer ${width}x$height, canvas ${surfaceCanvas.description}")
        report("${scenes.size} scene(s)")
        report("")

        val results = ArrayList<SceneResult>()

        for (entry in scenes) {
            val result = try {
                val frames = library.open(entry.name)
                Benchmark.run(entry.name, entry.tier, frames, target,
                    options = RenderOptions.forSurface(width))
            } catch (e: Throwable) {
                Benchmark.failed(entry.name, entry.tier, "${e::class.java.simpleName}: ${e.message}")
            }
            results.add(result)
            report(result.toLine())
        }

        // Anything that missed its budget gets swept: the same scene again with
        // one of the renderer's trades turned off each time. A change that
        // measured well on a desktop rasteriser is a guess on a phone until the
        // phone says so, and this is cheap -- it only runs for scenes that
        // failed, and only until the list is exhausted.
        val struggling = results.filter { it.verdict == "FAIL" || it.verdict == "MARGINAL" }
        if (struggling.isNotEmpty()) {
            report("")
            report("sweeping ${struggling.size} scene(s) that missed the budget")
            for (result in struggling) {
                for ((label, options) in Benchmark.variants(width)) {
                    if (label == "all") continue  // the run above already is it
                    val swept = try {
                        val frames = library.open(result.name)
                        Benchmark.run(
                            result.name, result.tier, frames, target,
                            options = options, variant = label,
                        )
                    } catch (e: Throwable) {
                        Benchmark.failed(result.name, result.tier, "${e::class.java.simpleName}: ${e.message}")
                    }
                    results.add(swept)
                    report(swept.toLine())
                }
            }
        }

        report("")
        // The tally is about the shipping configuration, so sweep rows -- which
        // exist to be worse -- are left out of it.
        val primary = results.filter { it.variant == null }
        val pass = primary.count { it.verdict == "PASS" }
        val marginal = primary.count { it.verdict == "MARGINAL" }
        val fail = primary.count { it.verdict == "FAIL" || it.verdict == "ERROR" }
        report("PASS $pass   MARGINAL $marginal   FAIL $fail   of ${primary.size}")

        val json = buildString {
            append("{\"device\":\"${android.os.Build.MODEL}\",")
            append("\"soc\":\"${android.os.Build.HARDWARE}\",")
            append("\"android\":${android.os.Build.VERSION.SDK_INT},")
            append("\"surface\":\"${width}x$height\",")
            append("\"view\":\"${surface.width}x${surface.height}\",")
            append("\"canvas\":\"${if (surfaceCanvas.usingHardware) "hardware" else "software"}\",")
            append("\"scenes\":[")
            append(results.joinToString(",") { it.toJson() })
            append("]}")
        }
        resultJson = json
        File(filesDir, "benchmark.json").writeText(json)

        // Also somewhere a file manager can reach. getExternalFilesDir needs no
        // permission and is browsable on most devices, unlike filesDir.
        val shared = runCatching {
            File(getExternalFilesDir(null), "benchmark.json").also { it.writeText(json) }
        }.getOrNull()

        report("")
        report("Use the buttons above to send these numbers on.")
        if (shared != null) report("also written to ${shared.absolutePath}")
        report("or with adb: adb shell run-as $packageName cat files/benchmark.json")

        runOnUiThread {
            shareButton.isEnabled = true
            copyButton.isEnabled = true
        }
    }

    /**
     * Sends the report as text rather than as a file attachment.
     *
     * A file share would need a FileProvider and an androidx dependency for
     * what is a few kilobytes of JSON; text goes through any mail, chat or
     * notes app and can be pasted straight back. The human-readable table
     * rides along above it, because a table someone can read is more useful in
     * a message than JSON alone.
     */
    private fun shareResults() {
        val json = resultJson ?: return
        val body = buildString {
            append(lines)
            append("\n--- machine readable ---\n")
            append(json)
        }
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, "pocketanim benchmark: ${android.os.Build.MODEL}")
            putExtra(Intent.EXTRA_TEXT, body)
        }
        startActivity(Intent.createChooser(intent, "Send benchmark results"))
    }

    /** Clipboard, for when the fastest route is pasting into a chat. */
    private fun copyResults() {
        val json = resultJson ?: return
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("pocketanim benchmark", json))
        Toast.makeText(this, "JSON copied to clipboard", Toast.LENGTH_SHORT).show()
    }

    /**
     * Records what was measured. A frame time without a device next to it is
     * not a result, and "a low-end phone" is not a device.
     */
    private fun deviceLine(): String = String.format(
        Locale.ROOT,
        "%s %s / %s / Android %s (API %d) / %d cores",
        android.os.Build.MANUFACTURER,
        android.os.Build.MODEL,
        android.os.Build.HARDWARE,
        android.os.Build.VERSION.RELEASE,
        android.os.Build.VERSION.SDK_INT,
        Runtime.getRuntime().availableProcessors(),
    )

    private companion object {
        const val TAG = "panim"
        /** The frame every device is measured at, so numbers compare. */
        const val BUFFER_WIDTH = 1920
        const val BUFFER_HEIGHT = 1080
        const val MATCH = LinearLayout.LayoutParams.MATCH_PARENT
        const val WRAP = LinearLayout.LayoutParams.WRAP_CONTENT
    }
}
