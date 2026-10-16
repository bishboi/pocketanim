// Ported from player/android/src/main/kotlin/com/pocketanim/android/AudioPlayer.kt.
//
// Decodes a scene's narration and feeds the clock the video follows.
//
// Runs on its own thread. Decoding and waiting for a stream's next bytes must not happen on the thread that draws:
// a stalled read would show up as dropped frames. The thread decodes ahead of the play head until the clock's
// queue is full -- the back pressure that keeps it in step with playback instead of decoding the whole file -- and
// handles seeks itself, so a seek never races a decode.
//
// Use, as PanimView.attachAudio does on Android:
//
//     let source = try NarrationSource(contentsOf: file)          // or NarrationSource.stream(url, keepAt: file)
//     let format = try source.format()                            // off the main thread: a stream waits for bytes
//     let clock = AudioClock(sampleRate: format.sampleRate)
//     clock.speed = Float(playback.speed)
//     let player = NarrationPlayer(source: source, format: format, clock: clock)
//     playback.audio = clock                                      // AudioClock answers positionSeconds()
//     if at > 0 { player.seekTo(seconds) }
//     if playing { clock.play(); player.start() }
//
// and the host polls `buffering` (hold the picture, show "Buffering...") and `failed` (play on silent, say why).

#if canImport(AVFoundation)
import AVFoundation
import Foundation

public final class NarrationPlayer {
    public let source: NarrationSource
    public let format: NarrationFormat
    public let clock: AudioClock

    private let lock = NSLock()
    private var running = false
    private var seekTarget: Double?
    private var thread: Thread?
    private var exited: DispatchSemaphore?
    private var _finished = false
    private var _failed: String?
    private var readingSince: UInt64 = 0        // when the decoder started waiting on the source (0: not waiting)

    public init(source: NarrationSource, format: NarrationFormat, clock: AudioClock) {
        self.source = source
        self.format = format
        self.clock = clock
    }

    /// Set when the stream runs out, so the clock can stop being authoritative.
    public var finished: Bool { locked { _finished } }

    /// Set when the narration could not be read at all (no network, the file gone, not a narration).
    public var failed: String? { locked { _failed } }

    /// Whether the narration is waiting on its source -- a stream that has not got the next second yet -- for
    /// longer than a moment. Waiting because the queue is full (paused) is not this: that blocks writing, not
    /// reading.
    public var buffering: Bool {
        let since = locked { readingSince }
        return since != 0 && DispatchTime.now().uptimeNanoseconds - since > Self.bufferingNanos
    }

    public func start() {
        let semaphore = DispatchSemaphore(value: 0)
        let begin: Bool = locked {
            guard !running else { return false }
            running = true
            _finished = false
            exited = semaphore
            return true
        }
        guard begin else { return }
        let thread = Thread { [self] in
            pump()
            semaphore.signal()
        }
        thread.name = "panim-audio"
        thread.qualityOfService = .userInitiated
        self.thread = thread
        thread.start()
    }

    public func stop() {
        let semaphore: DispatchSemaphore? = locked {
            running = false
            return exited
        }
        _ = semaphore?.wait(timeout: .now() + 0.5)
        thread = nil
    }

    /// Reposition the narration. Made on the narration's thread, between two decodes; meanwhile the clock says
    /// nothing, so the picture does not jump back to the old place.
    public func seekTo(_ seconds: Double) {
        clock.seeking = true
        locked { seekTarget = max(0, seconds) }
    }

    private func pump() {
        let reader = NarrationReader(source: source, format: format) { head in
            AudioToolboxOpusDecoder(channels: head.channels)
        }
        var pending: [Float] = []
        var offset = 0
        defer { locked { running = false; readingSince = 0 } }
        while locked({ running }) {
            if let target = locked({ () -> Double? in
                defer { seekTarget = nil }
                return seekTarget
            }) {
                reader.seek(to: target)
                pending = []
                offset = 0
                clock.seekTo(target)
                locked { _finished = false }
            }

            if offset < pending.count {
                // Waits while the queue is full, which is the back pressure. Not a blocking wait: a seek made
                // while paused must be made now, not after the old place has sounded.
                let n = clock.write(pending, from: offset)
                offset += n
                if n == 0 { Thread.sleep(forTimeInterval: Self.writeWait) }
                continue
            }

            let step: NarrationReader.Step
            do {
                step = try reader.next()
            } catch {
                // A stream that cannot be reached or read: the picture plays on, silent, and the screen says why.
                locked {
                    _failed = (error as? NarrationFormatError)?.description ?? (error as? OpusDecodeError)?.description
                        ?? error.localizedDescription
                    _finished = true
                }
                return
            }
            switch step {
            case .pcm(let samples):
                locked { readingSince = 0 }
                pending = samples
                offset = 0
            case .waiting:
                // Over the network this is where a stream waits for its next piece.
                locked { if readingSince == 0 { readingSince = DispatchTime.now().uptimeNanoseconds } }
                source.waitForMore(than: source.count, timeout: Self.writeWait * 10)
            case .ended:
                // Stay alive: a seek can bring the stream back.
                locked {
                    readingSince = 0
                    _finished = true
                }
                Thread.sleep(forTimeInterval: 0.01)
            }
        }
    }

    @inline(__always) private func locked<T>(_ body: () -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return body()
    }

    private static let writeWait = 0.005
    private static let bufferingNanos: UInt64 = 350_000_000
}
#endif
