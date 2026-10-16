# Porting the player to iOS

The iOS player is a Swift port of the Android player (`player/`), file for file, so both play a lecture the same
way. This note is the contract every part of the port follows.

## Layout

| Here | Ported from | Builds on |
|---|---|---|
| `Sources/PanimCore/` | `player/core` (decoder, DSL interpreter, renderer, playback clock, library, saved lectures, import) | Linux and Apple |
| `Sources/PanimAudio/` | `player/android/.../AudioPlayer.kt`, `AudioClock.kt` (Ogg Opus demuxer pure Swift; decoding and output behind `#if canImport(AVFoundation)`) | demuxer on Linux, the rest Apple |
| `Sources/PanimVerify/` | `player/desktop/.../Verify.kt` (the modes that need no rasteriser: `dump`, `trace`, `library`) | Linux and Apple |
| `App/` | `player/app` and the rest of `player/android` (CoreGraphics `PathSink`, display-link view, screens) | Apple only (Xcode, via XcodeGen `project.yml`) |

## Rules

- One Swift file per Kotlin file, same base name (`Panm.kt` -> `Panm.swift`), its doc comment saying where it came
  from. Same type, function and property names (Swift casing is the same as Kotlin's). Keep the Kotlin comments that
  explain *why*.
- Types: Kotlin `Float` stays `Float` and `Double` stays `Double` (the maths must round alike; never widen a Float
  computation to Double or the reverse). `FloatArray` -> `[Float]`, `IntArray` -> `[Int32]` where the values are
  colours or bit patterns, `[Int]` otherwise. `ByteArray` -> `[UInt8]` (or `Data` at I/O edges). `Long` -> `Int64`.
  `Int` -> `Int`, except colours (ARGB) and anything relying on 32-bit overflow or `ushr`/`shl`: `Int32` with the
  wrapping operators (`&+`, `&*`, `&<<`) and `UInt32(bitPattern:)` for `ushr`.
- Little-endian reads go through one helper (a `ByteReader` in `Panm.swift`), never `withUnsafeBytes` casts of
  unaligned memory.
- PanimCore imports Foundation only (FoundationNetworking under `#if canImport(FoundationNetworking)` for
  URLSession on Linux). No UIKit/CoreGraphics/Compression in PanimCore.
- Kotlin `interface` -> Swift `protocol`; default methods go in a protocol extension. `object` -> `enum` with
  static members. `class` stays `class` (final unless subclassed).
- Errors: Kotlin exceptions -> Swift `throws` with a `PanimError` enum carrying the same message text the Kotlin
  code builds (the app shows it to the user).
- Floats in text output are formatted exactly as the Kotlin `String.format(Locale.ROOT, ...)` does, so dumps diff
  clean.

## Checking

    source ios/scripts/linux-swift.sh
    cd ios && swift build && swift test
    bash player/build.sh          # the Kotlin side
    ios/scripts/crosscheck.sh     # Swift and Kotlin dumps/traces of the same scenes, diffed

Each worker builds with its own `--scratch-path .build-<name>` so parallel builds do not collide.
