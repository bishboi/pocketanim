# The Android player

Five modules, split by what can be verified rather than by convention.

| Module | What it is | Runs where |
|---|---|---|
| `core/` | Decoder, tier-1 interpreter, renderer, playback clock. No Android, no AWT. | Anywhere a JVM runs |
| `android/` | `SurfaceView` render loop, Skia `PathSink`, `AudioTrack` clock | Device only |
| `app/` | The player someone watches a scene in. Transport, scrubbing, scene picker. | Device only |
| `benchmark/` | The device gate. Renders every scene as fast as it can and counts late frames. | Device only |
| `desktop/` | Verification harness. Not shipped. | This machine |

## Watching something

`app/` is the demonstration, and the thing it demonstrates is what is *not*
in the APK. It opens on `HelloPocketanim` — an ordinary Manim scene in
`samples/hello_pocketanim.py`, eight seconds of title, circle, transform and
move:

```python
class HelloPocketanim(Scene):
    def construct(self):
        title = Text("pocketanim", font_size=56)
        self.play(Write(title), run_time=1.5)
        ...
```

| That scene, as | Bytes |
|---|---|
| 720p30 MP4 from `manim -qm` | 128,851 |
| tier-1 program | 277 |
| program **and** its text asset — everything needed to play it | **814** |

158x smaller, and not because it is compressed: there is no video in the APK
and nothing is decoded. The program is interpreted and its frames are drawn
as they are needed, which is why scrubbing lands instantly and why the whole
twelve-scene library is 1.2 MB.

Against Manim's own frames the sample measures **0.05% of pixels differing**.

```
adb install -r app-release.apk
adb shell am start -n com.pocketanim.player/.PlayerActivity
```

Both APKs are built by `.github/workflows/apk.yml` and attached to the run.

## The one seam

`core` asks the platform for exactly one thing:

```kotlin
interface PathSink {
    fun beginPath()
    fun moveTo(x: Float, y: Float)
    fun cubicTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float)
    fun closeSubpath()
    fun fillPath(argb: Int)
    fun strokePath(argb: Int, widthInSceneUnits: Float)
}
```

Android backs it with `Canvas`/`Path`/`Paint`; `desktop` backs it with Java2D.
Everything that decides *what the picture is* — decode, interpret, transform,
project, depth sort, shade, split subpaths — is on the `core` side of that line,
so **the code that runs on the phone is the code that gets checked here**
against `exporter/reference_render.py`.

The sink receives points in *scene* coordinates. The platform sets up the
scene-to-pixel transform, which is what makes stroke widths — expressed by
Manim in hundredths of a scene unit — scale the same way they do in Cairo.

## Both tiers, one type

`Scene` is what the renderer draws. It comes from either:

- `Scene.parse(bytes)` — a `.panm`, sampled frames (tier 3)
- `Interpreter.build(Program.parse(text), assets)` — a `.panim`, a program the
  device expands (tier 1)

Past that point nothing can tell which tier it is playing, which is the whole
reason the interpreter returns a `Scene` rather than its own type.

## Building

With an Android SDK, use the Gradle build (`settings.gradle.kts` and the
per-module `build.gradle.kts`).

Without one — `dl.google.com` is blocked in some sandboxes — use `build.sh`.
Maven Central carries both the Kotlin compiler and a real Android framework jar
(`org.robolectric:android-all`, which is AOSP's `android.jar` contents), which
is enough to *compile* the Android layer against the real `android.*` API:

```
./player/build.sh --fetch   # toolchain, ~200 MB, once
./player/build.sh           # core + desktop + android
```

## Verifying

```
python -m tools.crosscheck_decoders corpus/ir/*.panm      # 3 decoders agree
python -m tools.crosscheck_interpreter dsl/generated/*.panim  # 2 interpreters agree
python -m tools.verify_player <scene.panm|.panim>         # renderer vs the oracle
java -cp ... com.pocketanim.desktop.VerifyKt <scene> bench    # geometry cost
```

## What is proven, and what is not

**Proven, by running it:** the decoder agrees field for field with
`exporter/decode.py` and `client/PanimDecoder.java` on every corpus scene; the
tier-1 interpreter agrees with `dsl/interpret.py` on all ten programs, cameras
and normals included; the renderer matches the Cairo oracle at 0.00–0.01% of
pixels differing, which is antialiasing noise.

**Compiled but never executed:** everything in `android/`. It builds against the
real framework, and that is all a compiler can tell you. The render loop, the
surface lifecycle and the audio clock have not run.

**Not addressed at all:** whether a low-end phone can keep up. `bench` reports
draws, verbs and the largest single path per frame; `docs/SPEC.md` §11 has the
corpus numbers. The headline is 5,120 `drawPath` calls per frame on
MolecularStructure — 154,000 per second at 30 fps. That is a real risk this
repository cannot retire without a device.
