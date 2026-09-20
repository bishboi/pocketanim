package com.pocketanim.android

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.media.AudioTimestamp
import com.pocketanim.core.TimeSource

/**
 * Audio playback, and the clock the video follows.
 *
 * The spec calls for AAC-LC at 64 kbps in per-segment files, with audio as the
 * master clock. The reason for that choice is contention: this player is
 * spending its CPU budget tessellating and rasterising vectors, so frames
 * *will* be late on a low-end phone. A late frame nobody notices; narration
 * drifting away from the drawing they are watching, they do.
 *
 * [positionSeconds] returns null rather than zero before the device reports a
 * timestamp. An AudioTrack that has been written to but not yet started reports
 * position 0 for a while, and treating that as authoritative pins the video on
 * frame 0 until audio catches up. Null makes [com.pocketanim.core.Playback]
 * fall back to the system clock, which is right for exactly that window.
 */
class AudioClock(
    sampleRate: Int,
    channelCount: Int,
) : TimeSource {

    private val channelMask =
        if (channelCount == 1) AudioFormat.CHANNEL_OUT_MONO else AudioFormat.CHANNEL_OUT_STEREO

    private val format = AudioFormat.Builder()
        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
        .setSampleRate(sampleRate)
        .setChannelMask(channelMask)
        .build()

    private val bufferBytes = AudioTrack.getMinBufferSize(
        sampleRate, channelMask, AudioFormat.ENCODING_PCM_16BIT,
    ).coerceAtLeast(sampleRate * channelCount * 2 / 4) // at least ~250 ms

    private val track = AudioTrack.Builder()
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE)
                .build()
        )
        .setAudioFormat(format)
        .setBufferSizeInBytes(bufferBytes)
        .setTransferMode(AudioTrack.MODE_STREAM)
        .build()

    private val timestamp = AudioTimestamp()
    private val rate = sampleRate.toDouble()

    /** Seconds of media before the first sample this track was fed. */
    var startOffsetSeconds: Double = 0.0

    fun play() = track.play()
    fun pause() = track.pause()

    /** Feed decoded PCM. Blocking; call from the audio thread, not the renderer. */
    fun write(pcm: ByteArray, offset: Int, size: Int): Int =
        track.write(pcm, offset, size)

    /**
     * Drop everything queued and restart the clock at [seconds].
     *
     * flush() requires a stopped or paused track, and the position counters
     * reset with it -- which is why the seek target is kept as an offset rather
     * than assumed to be zero.
     */
    fun seekTo(seconds: Double) {
        track.pause()
        track.flush()
        startOffsetSeconds = seconds
    }

    fun release() = track.release()

    override fun positionSeconds(): Double? {
        if (track.playState != AudioTrack.PLAYSTATE_PLAYING) return null
        // getTimestamp is the one that accounts for buffering and device
        // latency; getPlaybackHeadPosition does not, and on a device with a
        // deep buffer that difference is tens of milliseconds of lip-sync.
        if (track.getTimestamp(timestamp)) {
            val elapsed = (System.nanoTime() - timestamp.nanoTime) / 1e9
            return startOffsetSeconds + timestamp.framePosition / rate + elapsed
        }
        val head = track.playbackHeadPosition
        if (head <= 0) return null
        return startOffsetSeconds + head / rate
    }
}
