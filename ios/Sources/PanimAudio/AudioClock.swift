// Ported from player/android/src/main/kotlin/com/pocketanim/android/AudioClock.kt.
//
// Audio playback, and the clock the video follows.
//
// The narration is the master clock whenever it plays: this player spends its CPU budget tessellating and
// rasterising vectors, so frames *will* be late on a slow phone. A late frame nobody notices; narration drifting
// away from the drawing they are watching, they do.
//
// Android writes PCM into an AudioTrack and asks it for timestamps. Here the PCM goes into a PCMRing that an
// AVAudioSourceNode drains (source -> AVAudioUnitTimePitch -> main mixer). A source node rather than an
// AVAudioPlayerNode because its clock is the samples actually handed to the output: when a stream falls behind
// and the ring runs dry the voice stops and so does the clock, as an AudioTrack's head stops on underrun --
// a player node's timeline runs on through the silence, and the picture would run ahead of the voice.
//
// [positionSeconds] returns nil rather than zero until the output has taken samples since the last play or seek,
// so Playback falls back to the system clock for exactly that window (see the Kotlin note on getTimestamp).
//
// Threads: play/pause/speed/release from the main thread; write and seekTo from the narration's own thread
// (NarrationPlayer); positionSeconds from any thread. The render block only ever try-locks.

#if canImport(AVFoundation)
import AVFoundation
import Foundation
import os

public final class AudioClock {
    public let sampleRate: Double

    private let engine = AVAudioEngine()
    private let timePitch = AVAudioUnitTimePitch()
    private let sourceNode: AVAudioSourceNode
    private let state: RenderState
    /// Serialises calls into the engine, which come from the main thread and the narration's.
    private let engineLock = NSRecursiveLock()
    private var observers: [NSObjectProtocol] = []

    /// Called on the main queue when the system stopped the narration: a call or another app's audio took over,
    /// or the headphones were pulled out -- stop, as a video app does, rather than speak to the room. The host
    /// pauses its picture here (Android's PlayerActivity does it in its BECOMING_NOISY receiver and focus listener).
    public var onSystemPause: (() -> Void)?

    /// Why the audio engine would not start, when it would not.
    public private(set) var problem: String?

    /// [sampleRate] is the PCM's: 48000 for Opus, the file's own for a WAV. Mono.
    public init(sampleRate: Int) {
        self.sampleRate = Double(sampleRate)
        let state = RenderState(capacity: sampleRate)        // a second of narration queued at most
        self.state = state
        let format = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1)!
        sourceNode = AVAudioSourceNode(format: format) { isSilence, _, frameCount, buffers -> OSStatus in
            state.render(isSilence: isSilence, frames: Int(frameCount), buffers: buffers)
        }
        engine.attach(sourceNode)
        engine.attach(timePitch)
        engine.connect(sourceNode, to: timePitch, format: format)
        engine.connect(timePitch, to: engine.mainMixerNode, format: format)
        engine.prepare()
        observe()
    }

    deinit { release() }

    /// The narration app's session: plays with the ringer switched to silent, as spoken audio.
    public static func activateSession() throws {
        #if os(iOS)
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .spokenAudio, options: [])
        try session.setActive(true)
        #endif
    }

    public func play() {
        engineLock.lock()
        defer { engineLock.unlock() }
        if !engine.isRunning {
            do {
                try engine.start()
                problem = nil
            } catch {
                problem = error.localizedDescription
                return
            }
        }
        state.setLatency(outputLatency())
        state.setRunning(true)
    }

    public func pause() {
        state.setRunning(false)
        engineLock.lock()
        engine.pause()
        engineLock.unlock()
    }

    /// Play the narration faster or slower, its pitch kept (the time-pitch unit's rate). Positions stay in media
    /// seconds: the clock counts the narration's own frames, and the time since the last pull runs at [speed].
    public var speed: Float = 1 {
        didSet {
            let rate = min(max(speed, 1.0 / 32), 32)
            engineLock.lock()
            timePitch.rate = rate
            timePitch.pitch = 0
            engineLock.unlock()
            state.setSpeed(Double(rate))
        }
    }

    /// Whether it is playing, as opposed to paused or stopped by the system.
    public var playing: Bool { state.isRunning && engine.isRunning }

    /// Feed decoded PCM: how many samples were taken (0 when the queue is full). Call from the narration's thread.
    public func write(_ samples: [Float], from offset: Int) -> Int {
        state.write(samples, from: offset)
    }

    /// Samples queued and not yet played.
    public var queued: Int { state.queued }

    /// Drop everything queued and restart the clock at [seconds]. Unlike the Kotlin (where flush needs a paused
    /// track) the engine keeps running: an empty queue is silence, and the clock says nothing until new samples
    /// are taken.
    public func seekTo(_ seconds: Double) {
        state.seek(to: seconds)
        engineLock.lock()
        timePitch.reset()           // what the time stretch still held belongs to the old place
        engineLock.unlock()
    }

    /// A seek has been asked for and the narration's thread has not made it yet: until it has, the queue still
    /// holds the old place, and the picture -- following it -- would jump back to the old place for a moment.
    /// The clock says nothing meanwhile (the picture keeps its own time from the place sought).
    public var seeking: Bool {
        get { state.isSeeking }
        set { state.setSeeking(newValue) }
    }

    public func release() {
        for o in observers { NotificationCenter.default.removeObserver(o) }
        observers.removeAll()
        state.setRunning(false)
        engineLock.lock()
        engine.stop()
        engineLock.unlock()
    }

    /// Seconds of media heard, or nil when this clock cannot say (paused, seeking, nothing played since).
    public func positionSeconds() -> Double? {
        guard engine.isRunning else { return nil }
        return state.position(now: hostSeconds(mach_absolute_time()), sampleRate: sampleRate)
    }

    /// How long from a sample's render to its reaching the ear.
    private func outputLatency() -> Double {
        var latency = engine.outputNode.presentationLatency + timePitch.latency
        #if os(iOS)
        latency += AVAudioSession.sharedInstance().ioBufferDuration
        #endif
        return max(0, latency)
    }

    private func observe() {
        let center = NotificationCenter.default
        // The engine stops itself when the hardware's configuration changes (a route change, a rate change).
        observers.append(center.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine,
                                            queue: .main) { [weak self] _ in
            guard let self, self.state.isRunning else { return }
            self.play()
        })
        #if os(iOS)
        observers.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil,
                                            queue: .main) { [weak self] note in
            guard let self,
                  let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  AVAudioSession.InterruptionType(rawValue: raw) == .began,
                  self.state.isRunning else { return }
            // Resuming after the call is the viewer's to ask for, as on Android after a transient focus loss.
            self.pause()
            self.onSystemPause?()
        })
        observers.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil,
                                            queue: .main) { [weak self] note in
            guard let self else { return }
            self.state.setLatency(self.outputLatency())
            guard let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
                  AVAudioSession.RouteChangeReason(rawValue: raw) == .oldDeviceUnavailable,
                  self.state.isRunning else { return }
            self.pause()
            self.onSystemPause?()
        })
        #endif
    }
}

private let hostTicksToSeconds: Double = {
    var info = mach_timebase_info_data_t()
    mach_timebase_info(&info)
    return Double(info.numer) / Double(info.denom) / 1e9
}()

@inline(__always) private func hostSeconds(_ ticks: UInt64) -> Double { Double(ticks) * hostTicksToSeconds }

/// What the render block shares with the rest: the queue and the last pull, behind an unfair lock.
private final class RenderState {
    private let lock: UnsafeMutablePointer<os_unfair_lock>
    private var ring: PCMRing
    private var running = false
    private var seeking = false
    private var startOffset = 0.0
    private var played: Int64 = 0           // frames handed to the output since the last seek
    private var pulledAt = 0.0              // host seconds of the last pull that took samples; 0: none yet
    private var pulled = 0
    private var latency = 0.0
    private var speed = 1.0

    init(capacity: Int) {
        ring = PCMRing(capacity: capacity)
        lock = .allocate(capacity: 1)
        lock.initialize(to: os_unfair_lock())
    }

    deinit {
        lock.deinitialize(count: 1)
        lock.deallocate()
    }

    @inline(__always) private func locked<T>(_ body: () -> T) -> T {
        os_unfair_lock_lock(lock)
        defer { os_unfair_lock_unlock(lock) }
        return body()
    }

    /// On the audio render thread: never blocks; a contended lock is a buffer of silence.
    func render(isSilence: UnsafeMutablePointer<ObjCBool>, frames: Int,
                buffers: UnsafeMutablePointer<AudioBufferList>) -> OSStatus {
        let list = UnsafeMutableAudioBufferListPointer(buffers)
        var copied = 0
        if let out = list[0].mData?.assumingMemoryBound(to: Float.self) {
            if os_unfair_lock_trylock(lock) {
                if running {
                    copied = ring.read(into: out, frames: frames)
                    if copied > 0 {
                        played += Int64(copied)
                        pulled = copied
                        pulledAt = hostSeconds(mach_absolute_time())
                    }
                }
                os_unfair_lock_unlock(lock)
            }
            if copied < frames { (out + copied).update(repeating: 0, count: frames - copied) }
        }
        for i in 1..<max(1, list.count) {
            if let data = list[i].mData { memset(data, 0, Int(list[i].mDataByteSize)) }
        }
        if copied == 0 { isSilence.pointee = true }
        return noErr
    }

    func write(_ samples: [Float], from offset: Int) -> Int { locked { ring.write(samples, from: offset) } }
    var queued: Int { locked { ring.count } }
    var isRunning: Bool { locked { running } }
    var isSeeking: Bool { locked { seeking } }
    func setSeeking(_ value: Bool) { locked { seeking = value } }
    func setLatency(_ value: Double) { locked { latency = value } }
    func setSpeed(_ value: Double) { locked { speed = value } }

    func setRunning(_ value: Bool) {
        locked {
            running = value
            pulledAt = 0        // a pull from before the pause says nothing about after it
        }
    }

    func seek(to seconds: Double) {
        locked {
            ring.clear()
            startOffset = seconds
            played = 0
            pulledAt = 0
            seeking = false
        }
    }

    func position(now: Double, sampleRate: Double) -> Double? {
        locked {
            guard running, !seeking, pulledAt > 0 else { return nil }
            return NarrationClockMath.position(now: now, pulledAt: pulledAt, pulledEnd: played, pulled: pulled,
                                               latency: latency, speed: speed, sampleRate: sampleRate,
                                               startOffset: startOffset)
        }
    }
}
#endif
