package com.pocketanim.android

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/**
 * Decodes a scene's narration and feeds the clock the video follows.
 *
 * The spec settles on AAC-LC at 64 kbps in per-segment files (§6). AAC is the
 * one codec every Android device decodes in hardware; Opus is smaller at this
 * bitrate and would have been the better choice on size alone, but this player
 * spends its CPU budget tessellating and rasterising vectors, so handing audio
 * decode to a DSP instead of the CPU is worth more than the bytes. That is the
 * whole argument, and it is why this uses MediaCodec rather than a software
 * decoder.
 *
 * Runs on its own thread. Decoding blocks on the codec and writing blocks on
 * the AudioTrack, and neither may happen on the renderer's thread -- a stalled
 * write would show up as dropped frames.
 */
class AudioPlayer(
    private val source: File,
    private val clock: AudioClock,
) {
    private val running = AtomicBoolean(false)
    private val seekTargetUs = AtomicLong(-1L)
    private var thread: Thread? = null

    /** Set when the stream runs out, so the clock can stop being authoritative. */
    @Volatile var finished = false
        private set

    fun start() {
        if (!running.compareAndSet(false, true)) return
        finished = false
        thread = Thread(::pump, "panim-audio").also {
            it.isDaemon = true
            it.start()
        }
    }

    fun stop() {
        running.set(false)
        thread?.join(500)
        thread = null
    }

    /**
     * Reposition the stream.
     *
     * Handled on the audio thread rather than here: flushing a codec from
     * another thread while it is mid-dequeue is a race, and the cost of waiting
     * one buffer is imperceptible next to the seek itself.
     */
    fun seekTo(seconds: Double) {
        seekTargetUs.set((seconds * 1_000_000).toLong())
    }

    private fun pump() {
        val extractor = MediaExtractor()
        var codec: MediaCodec? = null
        try {
            extractor.setDataSource(source.absolutePath)

            val track = (0 until extractor.trackCount).firstOrNull { index ->
                extractor.getTrackFormat(index)
                    .getString(MediaFormat.KEY_MIME)
                    ?.startsWith("audio/") == true
            } ?: return

            extractor.selectTrack(track)
            val format = extractor.getTrackFormat(track)
            val mime = format.getString(MediaFormat.KEY_MIME) ?: return

            codec = MediaCodec.createDecoderByType(mime).apply {
                configure(format, null, null, 0)
                start()
            }

            val info = MediaCodec.BufferInfo()
            var inputDone = false

            while (running.get()) {
                val target = seekTargetUs.getAndSet(-1L)
                if (target >= 0) {
                    // SEEK_TO_PREVIOUS_SYNC, then let the clock's offset carry
                    // the difference: AAC frames are ~23 ms, which is below the
                    // threshold where a listener notices the landing point.
                    extractor.seekTo(target, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
                    codec.flush()
                    // Resume only what was running: a scrub while paused used
                    // to start the narration under a still picture.
                    val resume = clock.playing
                    clock.seekTo(extractor.sampleTime / 1_000_000.0)
                    if (resume) clock.play()
                    inputDone = false
                    finished = false
                }

                if (!inputDone) {
                    val index = codec.dequeueInputBuffer(TIMEOUT_US)
                    if (index >= 0) {
                        val buffer = codec.getInputBuffer(index)!!
                        val size = extractor.readSampleData(buffer, 0)
                        if (size < 0) {
                            codec.queueInputBuffer(
                                index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM,
                            )
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(index, 0, size, extractor.sampleTime, 0)
                            extractor.advance()
                        }
                    }
                }

                when (val index = codec.dequeueOutputBuffer(info, TIMEOUT_US)) {
                    MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                    MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> Unit
                    else -> if (index >= 0) {
                        if (info.size > 0) {
                            val buffer = codec.getOutputBuffer(index)!!
                            val pcm = ByteArray(info.size)
                            buffer.position(info.offset)
                            buffer.get(pcm)
                            // Blocks when the track is full, which is the back
                            // pressure that keeps this thread in step with
                            // playback instead of decoding the whole file.
                            clock.write(pcm, 0, pcm.size)
                        }
                        codec.releaseOutputBuffer(index, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) {
                            finished = true
                            // Stay alive: a seek can bring the stream back.
                            inputDone = true
                        }
                    }
                }

                if (finished && seekTargetUs.get() < 0) Thread.sleep(10)
            }
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        } finally {
            try {
                codec?.stop()
                codec?.release()
            } catch (_: IllegalStateException) {
                // Already torn down; nothing to recover.
            }
            extractor.release()
            running.set(false)
        }
    }

    private companion object {
        const val TIMEOUT_US = 10_000L
    }
}
