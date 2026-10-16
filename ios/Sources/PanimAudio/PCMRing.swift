// The decoded narration waiting to be played, and the arithmetic of where the listener is in it.
//
// This is what Android's AudioTrack is in AudioClock.kt: a bounded queue the audio thread writes into without
// blocking ("what the track took, 0 when full") and the device drains. On iOS the device side is an
// AVAudioSourceNode render block (AudioClock.swift); the queue and the position arithmetic live here, free of
// AVFoundation, so they are tested on Linux. Not thread-safe by itself: AudioClock guards it with a lock.

import Foundation

/// A fixed-size ring of mono samples.
public struct PCMRing {
    private var storage: [Float]
    private var readIndex = 0
    public private(set) var count = 0

    public init(capacity: Int) {
        storage = [Float](repeating: 0, count: max(1, capacity))
    }

    public var capacity: Int { storage.count }
    public var space: Int { storage.count - count }

    /// Queue as much of [samples][offset...] as fits; returns how many were taken.
    public mutating func write(_ samples: [Float], from offset: Int = 0) -> Int {
        let n = min(space, samples.count - offset)
        guard n > 0 else { return 0 }
        var w = (readIndex + count) % storage.count
        for i in 0..<n {
            storage[w] = samples[offset + i]
            w += 1
            if w == storage.count { w = 0 }
        }
        count += n
        return n
    }

    /// Move up to [frames] samples into [out], returning how many.
    public mutating func read(into out: UnsafeMutablePointer<Float>, frames: Int) -> Int {
        let n = min(frames, count)
        guard n > 0 else { return 0 }
        storage.withUnsafeBufferPointer { s in
            let first = min(n, s.count - readIndex)
            out.update(from: s.baseAddress! + readIndex, count: first)
            if n > first { (out + first).update(from: s.baseAddress!, count: n - first) }
        }
        readIndex = (readIndex + n) % storage.count
        count -= n
        return n
    }

    public mutating func clear() {
        readIndex = 0
        count = 0
    }
}

/// Where the listener is, from the last time the output pulled samples.
public enum NarrationClockMath {
    /// Media seconds being heard at [now] (seconds on the host clock).
    ///
    /// The render block was last asked for samples at [pulledAt], when the ones it handed over ended at [pulledEnd]
    /// frames past the seek point; [pulled] of them came then. Those reach the ear [latency] seconds later, and
    /// between pulls the narration moves at [speed] times its own rate. The answer never passes [pulledEnd]: when
    /// the queue ran dry (a stream behind) the voice stopped there, and so does the clock -- as an AudioTrack's
    /// head stops when it underruns.
    public static func position(now: Double, pulledAt: Double, pulledEnd: Int64, pulled: Int, latency: Double,
                                speed: Double, sampleRate: Double, startOffset: Double) -> Double {
        let start = Double(pulledEnd - Int64(pulled))
        var frames = start + (now - pulledAt - latency) * speed * sampleRate
        frames = min(frames, Double(pulledEnd))
        frames = max(frames, 0)
        return startOffset + frames / sampleRate
    }
}
