# Pocketanim for iOS

The iOS player: a Swift port of the Android player in `player/`, file for file, so both play a lecture the same
way. `PORTING.md` is the contract the port follows.

## Building on a Mac

Needs Xcode 15 or later (iOS 15 is the deployment target) and [XcodeGen](https://github.com/yonaskolb/XcodeGen),
which writes the Xcode project from `project.yml` (the project itself is not versioned).

    brew install xcodegen
    cd ios
    cp App/Secrets.example.xcconfig App/Secrets.xcconfig     # optional: fill in your Supabase project
    xcodegen generate
    open PanimPlayer.xcodeproj

Then pick the **PanimPlayer** scheme, choose your team under *Signing & Capabilities* (or set `DEVELOPMENT_TEAM`
in `App/Secrets.xcconfig`, which survives regenerating the project), pick your phone and Run.

- **Supabase.** `App/Secrets.xcconfig` (gitignored) sets `PANIM_SUPABASE_URL` and `PANIM_SUPABASE_ANON_KEY`;
  they reach the app through Info.plist. Write the URL's `//` as `/$()/` -- xcconfig reads `//` as a comment.
  Without them the app asks for the project (Library → ⋮), as the Android app does.
- **Samples.** The Samples tab plays the scene library bundled into the app. It is build output, as it is for the
  APK; make it with `python -m tools.build_library --out ios/App/Resources/library` from the repository root
  (needs numpy), then run `xcodegen generate` again. Without it the app builds and plays saved and imported
  lectures; Samples says it has none. A library copied into the app's Documents folder as `library/` (Finder or
  Files) replaces the bundled one -- the iOS form of `adb push`.
- **Release** builds are the ones to judge playback by: every frame is rasterised on the CPU, and a Debug build
  of the renderer is several times slower.

Re-run `xcodegen generate` after adding or removing a file under `App/`.

## How CI builds it

`.github/workflows/ios.yml` runs on a macOS runner on every push that touches `ios/` (or by hand):

1. packs the scene library into `ios/App/Resources/library`, exactly as `apk.yml` packs it into the APK;
2. writes `App/Secrets.xcconfig` from the repository secrets `PANIM_SUPABASE_URL` / `PANIM_SUPABASE_ANON_KEY`,
   when they are set;
3. `xcodegen generate`, then `xcodebuild` twice with signing off: for the Simulator and for a device;
4. uploads `PanimPlayer-<sha>-unsigned.ipa` (`Payload/PanimPlayer.app`, zipped) and
   `PanimPlayer-<sha>-simulator.app.zip`;
5. runs `swift test` on the package.

The .ipa is unsigned: it installs only once re-signed with a team (or build from Xcode as above). The Simulator
app installs with `xcrun simctl install booted PanimPlayer.app`.

## Architecture

    ios/
      Package.swift            PanimCore, PanimAudio, PanimVerify (builds on Linux too)
      Sources/PanimCore/       player/core: decoder, DSL interpreter, renderer, playback clock, library, saved lectures, import
      Sources/PanimAudio/      the narration: Ogg Opus demuxer, AudioToolbox decode, AVAudioEngine output with speed and pitch
      project.yml              -> PanimPlayer.xcodeproj (XcodeGen)
      App/                     the app (Apple only)
        Config.xcconfig        build settings; includes Secrets.xcconfig if present
        Sources/
        Resources/library/     the packed scene library (generated)

What maps to what in the Android player:

| iOS (`App/Sources/`) | Android | What it is |
|---|---|---|
| `CGSink.swift` | `android/CanvasSink.kt` | The renderer's `PathSink` on CoreGraphics: the context in scene units (y up, centred) so stroke widths scale as Manim's do; fills, strokes with round or bevel joins, ARGB colours; pictures (WebP/PNG through ImageIO, decoded no larger than 2048 px, cached up to 48 MB, prefetched on a queue of their own). |
| `SurfaceCanvas.swift` | `android/SurfaceCanvas.kt` | The buffer a frame is drawn into: a reused bitmap context, handed to the view's layer as a picture. |
| `PanimView.swift` | `android/PanimView.kt` | The player view: a `CADisplayLink` paces it, frames are made and drawn on a serial queue (never the main thread), the picture is fitted 16:9 and letterboxed, frames that show what is on screen are skipped, a frame that fails is dropped and reported (`onFrameError`) with its full error. Owns the narration and makes it the clock (`Playback.audio`). |
| `AssetStorage.swift` | `android/AssetStorage.kt` | The library inside the app. A bundle is a folder, so it is read through the same folder `Storage` an imported library is. |
| `Thumbnails.swift` | `android/Thumbnails.kt` | A card's still: a frame chosen past the first chapter's title, drawn off screen, kept as a PNG. |
| PanimAudio `NarrationPlayer` | `android/AudioPlayer.kt`, `AudioClock.kt` | Decoding and output, time-stretched with the pitch kept; its position is the master clock. |
| `LibraryViewController.swift` | `app/LibraryActivity.kt` | Tabs Saved / On this phone / Samples; cards with still, length, progress, on-phone or streams; hold for Play from the start, Keep for offline, Remove; import a zip (document picker, or opened from Files/Safari/AirDrop); the Supabase project. |
| `PlayerViewController.swift` | `app/PlayerActivity.kt` | Picture on top with details and chapters below when upright, whole screen sideways or with the corner button; tap for controls, ±10 s, double-tap the sides; timeline; speed 0.5–2×; chapters; resume; buffering; the end card with the next lecture; pauses for calls and unplugged headphones; lock-screen play/pause. |
| `TimelineView.swift` | `app/TimelineView.kt` | The seek bar: played, loaded, chapters as gaps, the scrub bubble. |
| `Lectures.swift` | `app/Lectures.kt` | What there is to watch and where it is kept (Application Support), the cached catalog, progress (UserDefaults). |
| `Ui.swift` | `app/Ui.kt` | Colours, labels, chips, the icons drawn as paths, and the error sheet with the full error text and Copy. |
| `App.swift` | `AndroidManifest.xml` | Entry points: the library launches; a zip opened from elsewhere is imported. |

Differences forced by the platform:

- **Rasterising.** Android draws through Skia on the GPU; CoreGraphics rasterises on the CPU. The view caps the
  picture at 2 pixels per point to keep a frame's cost bounded on large screens (`PanimView.maxScale`).
- **Whole screen.** iOS 15 cannot be asked to turn the screen; there the corner button gives the picture the whole
  upright screen, and turning the phone does the rest. iOS 16 and later turn it, as Android does.
- **In the background.** With narration the lecture plays on with the screen locked (the narration is the clock,
  and the picture catches up on return); a silent lecture pauses, as Android pauses when it leaves the screen.
- **Errors.** Swift has no stack trace for a thrown error; the error sheet shows the type, the message, every
  underlying error and the error's own description. A trap (an index out of range in the core) ends the app
  rather than dropping the frame as a Kotlin exception would.
