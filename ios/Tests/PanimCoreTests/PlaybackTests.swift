import XCTest
@testable import PanimCore

/** The playback clock: the wall clock's speed, audio as master, holding rather than stepping back, looping. */
final class PlaybackTests: XCTestCase {
    /** A scene of [count] empty frames: Playback only asks for the count and the rate. */
    private final class Blank: Frames {
        let fps: Int
        let frameCount: Int
        init(fps: Int, frames: Int) { self.fps = fps; self.frameCount = frames }
        func shape(_ atlasId: Int) -> [Float] { [] }
        func camera(_ index: Int) throws -> [Float]? { nil }
        func instances(_ index: Int) throws -> [Instance] { [] }
    }

    private final class Audio: TimeSource {
        var at: Double?
        func positionSeconds() -> Double? { at }
    }

    func testSystemClockSpeedAndPause() {
        var now: Int64 = 0
        let clock = SystemTimeSource { now }
        XCTAssertEqual(clock.positionSeconds(), 0)
        clock.start()
        now += 2_000_000_000
        clock.speed = 1.5
        now += 2_000_000_000
        // 2 s at 1x then 2 s at 1.5x, as Verify's stream check has it.
        XCTAssertEqual(clock.positionSeconds(), 5.0, accuracy: 1e-9)
        clock.pause()
        now += 10_000_000_000
        XCTAssertEqual(clock.positionSeconds(), 5.0, accuracy: 1e-9)
        clock.seekTo(1.0)
        XCTAssertEqual(clock.positionSeconds(), 1.0, accuracy: 1e-9)
        clock.start()
        now += 1_000_000_000
        XCTAssertEqual(clock.positionSeconds(), 2.5, accuracy: 1e-9)
    }

    func testFramesFollowTheWallClockAndStopAtTheEnd() {
        var now: Int64 = 0
        let playback = Playback(Blank(fps: 30, frames: 90), SystemTimeSource { now })
        XCTAssertEqual(playback.durationSeconds, 3.0)
        playback.play()
        XCTAssertEqual(playback.frameToDraw(), 0)
        XCTAssertEqual(playback.frameToDraw(), -1) // still frame 0: nothing to draw
        now += 500_000_000
        XCTAssertEqual(playback.frameToDraw(), 15)
        now += 10_000_000_000
        XCTAssertEqual(playback.currentFrame(), 89)
        XCTAssertFalse(playback.playing)
    }

    func testSpeedIsClamped() {
        let playback = Playback(Blank(fps: 30, frames: 90), SystemTimeSource { 0 })
        playback.speed = 10
        XCTAssertEqual(playback.speed, 3.0)
        playback.speed = 0.1
        XCTAssertEqual(playback.speed, 0.25)
    }

    func testAudioIsMasterAndThePictureDoesNotStepBack() {
        var now: Int64 = 0
        let playback = Playback(Blank(fps: 30, frames: 300), SystemTimeSource { now })
        let audio = Audio()
        playback.audio = audio
        playback.play()
        // Audio not started yet: the wall clock answers.
        now += 1_000_000_000
        XCTAssertEqual(playback.currentFrame(), 30)
        // Audio starts a little behind the wall: the picture holds rather than stepping back...
        audio.at = 0.9
        XCTAssertEqual(playback.currentFrame(), 30)
        // ...until the clock passes it.
        audio.at = 1.1
        XCTAssertEqual(playback.currentFrame(), 33)
        // A step back of more than half a second is a real one (a seek elsewhere): it is followed.
        audio.at = 0.2
        XCTAssertEqual(playback.currentFrame(), 6)
    }

    func testPauseRestartsFromThePictureOnScreen() {
        var now: Int64 = 0
        let playback = Playback(Blank(fps: 10, frames: 100), SystemTimeSource { now })
        let audio = Audio()
        playback.audio = audio
        playback.play()
        audio.at = 2.0
        XCTAssertEqual(playback.currentFrame(), 20)
        playback.pause()
        playback.audio = nil
        // The wall clock now stands where the picture was, not where it had counted to.
        XCTAssertEqual(playback.currentFrame(), 20)
    }

    func testLoopingWrapsAndTellsTheNarration() {
        var now: Int64 = 0
        let playback = Playback(Blank(fps: 10, frames: 20), SystemTimeSource { now })
        playback.looping = true
        var wrapped: [Int] = []
        playback.onLoop = { wrapped.append($0) }
        playback.play()
        now += 2_500_000_000 // 25 frames in: 5 past the end
        XCTAssertEqual(playback.currentFrame(), 5)
        XCTAssertEqual(wrapped, [5])
        XCTAssertTrue(playback.playing)
        now += 100_000_000
        XCTAssertEqual(playback.currentFrame(), 6)
    }

    func testSeekResetsTheFrameToDraw() {
        var now: Int64 = 0
        let playback = Playback(Blank(fps: 30, frames: 90), SystemTimeSource { now })
        XCTAssertEqual(playback.frameToDraw(), 0)
        playback.seekToFrame(45)
        XCTAssertEqual(playback.frameToDraw(), 45)
        playback.seekToFrame(500)
        XCTAssertEqual(playback.frameToDraw(), 89)
        now += 1
    }
}
