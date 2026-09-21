package com.pocketanim.benchmark

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.pocketanim.android.AssetStorage
import com.pocketanim.android.CanvasSink
import com.pocketanim.android.FileStorage
import com.pocketanim.android.SurfaceCanvas
import com.pocketanim.core.Benchmark
import com.pocketanim.core.FrameTarget
import com.pocketanim.core.Library
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
    private val lines = StringBuilder()
    private var started = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // A benchmark that lets the screen sleep halfway through measures the
        // screen going to sleep.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        surface = SurfaceView(this)
        output = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.BLACK)
            textSize = 9f
            typeface = android.graphics.Typeface.MONOSPACE
            text = "warming up..."
        }

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        // The surface gets most of the window: rasterisation cost scales with
        // the pixels actually touched, so measuring in a thumbnail would
        // understate it.
        root.addView(surface, LinearLayout.LayoutParams(MATCH, 0, 3f))
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
        report("surface ${width}x$height, canvas ${surfaceCanvas.description}")
        report("${scenes.size} scene(s)")
        report("")

        val results = ArrayList<SceneResult>()

        for (entry in scenes) {
            val result = try {
                val frames = library.open(entry.name)
                Benchmark.run(entry.name, entry.tier, frames, target)
            } catch (e: Throwable) {
                Benchmark.failed(entry.name, entry.tier, "${e::class.java.simpleName}: ${e.message}")
            }
            results.add(result)
            report(result.toLine())
        }

        report("")
        val pass = results.count { it.verdict == "PASS" }
        val marginal = results.count { it.verdict == "MARGINAL" }
        val fail = results.count { it.verdict == "FAIL" || it.verdict == "ERROR" }
        report("PASS $pass   MARGINAL $marginal   FAIL $fail   of ${results.size}")

        val json = buildString {
            append("{\"device\":\"${android.os.Build.MODEL}\",")
            append("\"soc\":\"${android.os.Build.HARDWARE}\",")
            append("\"android\":${android.os.Build.VERSION.SDK_INT},")
            append("\"surface\":\"${width}x$height\",")
            append("\"canvas\":\"${if (surfaceCanvas.usingHardware) "hardware" else "software"}\",")
            append("\"scenes\":[")
            append(results.joinToString(",") { it.toJson() })
            append("]}")
        }
        val file = File(filesDir, "benchmark.json")
        file.writeText(json)
        report("")
        report("wrote ${file.absolutePath}")
        report("adb shell run-as $packageName cat files/benchmark.json")
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
        const val MATCH = LinearLayout.LayoutParams.MATCH_PARENT
    }
}
