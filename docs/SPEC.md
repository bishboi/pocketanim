# pocketanim: on-device Manim rendering for Android

Implementation spec. Every decision here was resolved on the wayfinder map
([issue #2](https://github.com/bishboi/pocketanim/issues/2)); each section links the ticket
holding its reasoning. Where a figure is measured, the measurement is cited. Where something
is unresolved, it says so rather than guessing.

## 1. What this replaces

Today: Manim renders scenes server-side to MP4, stored and streamed over a CDN.

Instead: the server exports each scene to a compact **IR**, and a native Android renderer
replays it on device. No Python, Cairo, Pango or LaTeX runs on the phone.

**Drivers, in priority order:** bandwidth/CDN cost, offline playback, instant start.

**Hard constraints:**

- Device floor is **low-end Android at 720p30**.
- Playback is **video-player grade** — arbitrary seek and scrub. Any frame must be renderable
  on demand, not merely reachable by playing forward.
- **Voiceover is core**; audio ships as a real asset.
- **No MP4 fallback exists.** The video pipeline is retired, so the renderer must hold up at
  the floor ([#4](https://github.com/bishboi/pocketanim/issues/4)).

## 2. Architecture

```
Manim Scene (Python)
   │  exporter hooks CairoRenderer.update_frame
   ▼
Scene IR  ──────────┐
   │                │  AAC-LC 64 kbps narration, per segment
   ▼                ▼
Android player: Skia via Canvas, RenderNode display lists, custom SurfaceView
```

Three components: a Python **exporter**, the **IR format**, an Android **player**.

## 3. The IR

### 3.1 Shape

Keyframe-sampled geometry, interpolated linearly on device
([#9](https://github.com/bishboi/pocketanim/issues/9)).

**Manim's interpolation semantics are NOT reimplemented on device.** Every semantic mismatch
would be a silent visual drift, and Manim upstream changes would become our problem. Keyframe
density is the quality dial instead — measurable, tunable, and it cannot drift.

**Keyframes store absolute geometry, never deltas.** This is what makes seeking O(1) in seek
distance: nothing accumulates, nothing is reconstructed by walking the timeline.

Rejected by measurement: a **baked per-frame** dump is 27–85× *larger* than the H.264 it
replaces. This is not an estimate — see §8.

### 3.2 Timeline

- **Snapshots** at animation boundaries: the complete geometry state at that instant.
  These coincide with narration segment boundaries and seek anchors — three independent lines
  of reasoning converged here.
- **Keyframes** between snapshots, carrying only geometry that *morphs*.
- The IR is a **self-sufficient timeline**. Segment durations are resolved at export and
  written in as concrete values. The IR never consults the audio file to know how long
  anything lasts, because scenes must play silently when audio is absent
  ([#15](https://github.com/bishboi/pocketanim/issues/15)).

### 3.3 Static versus morphing

**The IR must mark geometry static or morphing.** Skia caches paths but re-tessellates any path
whose points changed, and Android's docs explicitly warn against editing paths frame to frame
([#8](https://github.com/bishboi/pocketanim/issues/8)).

Measured morphing fractions vary enormously — **0.49% to 45.7%** across the corpus. A single
global keyframe density will be wrong for most scenes: **choose density per mobject from its
measured morph rate.** That is exporter policy, not a format concern.

### 3.4 Coordinates

**16-bit fixed point over the scene bounding box.** At 720p this grid is far finer than a
pixel — visually lossless, and a 4× saving over Manim's float64.

Manim gives `(N, 3)` float64 points. **Keep all three axes**, including for 2D scenes (§3.6).

### 3.5 Glyph atlas

All text in Manim — body text, LaTeX and code alike — is **already outlines** by the time it
reaches the Mobject tree. Everything is `VMobjectFromSVGPath` with no font reference, glyph ID
or character code. Shipping glyph runs is therefore impossible
([#12](https://github.com/bishboi/pocketanim/issues/12)).

Two measured properties make outlines cheap anyway:

- **One submobject per glyph** — per-glyph addressability comes free.
- **Repeated glyphs deduplicate exactly.** After removing translation, outlines are
  byte-identical: `Text("aaabbb")` → 6 instances, **2 unique outlines**.

So the IR carries a **per-bundle glyph atlas**: each distinct outline stored once, each
on-screen glyph an `(atlas index, transform)` reference. An instance costs ~8–14 bytes against
~600 for its outline — roughly **50× on text-heavy content**, which is the dominant 2D payload
term.

This also resolves the performance objection: atlas outlines are **static paths reused across
every instance and frame**, exactly what Skia's path cache handles well.

No fonts ship. No shaping agreement to maintain. LaTeX and body text use one mechanism.

### 3.6 3D

**The IR carries 3D vertices and a camera track. The exporter must never flatten to 2D.**
The client re-projects every frame in painter order
([#13](https://github.com/bishboi/pocketanim/issues/13)).

This is faithful **by construction**: Manim's own Cairo renderer has no z-buffer either — it
projects to 2D Beziers and draws in painter order. The reference implementation has the same
limitation, so matching it is exact rather than approximate.

Measured: a 3D camera orbit morphs **0.49%** of its geometry, because the camera moves and the
model does not. Static-cached IR is **153 KB against a 2.72 MB MP4 — 17.8× smaller**, before
quantization or keyframing. 3D is the cheapest content in the IR and the most expensive in
video; it is the strongest single justification for this project.

**Deferred:** genuinely occluded solids (molecular structures) are the one case painter order
cannot express, and would need a depth-tested GL ES 3.0 layer. Unmeasured — no corpus scene
exercises it yet.

### 3.7 Layers: vector and raster

Two geometry layer types ([#11](https://github.com/bishboi/pocketanim/issues/11)):

- **Vector paths** — the default.
- **Raster with a transform** — the fallback for singular dense assets.

**Selection is automatic by point count.** No author annotation.

Measured: a Natural Earth **50m world coastline is 235,948 points across 1,429 polylines** — one
asset, appearing once. Against corpus scenes running 1,917–6,382 points per frame *in total*,
that is 24–118× an entire scene, and **14.4× over** Skia's `kMaxGPUPathRendererVerbs` (16,384)
into **software** rasterization. So this is a performance guardrail as much as a payload one.

The glyph atlas cannot help here: it rescues text because glyphs *repeat*, and a coastline is
singular. At 16-bit that asset is ~1.42 MB — comparable to a full 3-minute narration track, for
one map.

**Try source resolution first.** The same coastline at Natural Earth 110m is 5,128 points, a
**46× reduction**, and for a map shown small it is visually indistinguishable. Choosing source
resolution by on-screen size is likely more effective than either simplification or
rasterization, and the exporter should attempt it *before* the raster fallback triggers.

**Threshold:** derive from device measurement ([#6](https://github.com/bishboi/pocketanim/issues/6)).
Until that exists, 16,384 verbs is a defensible provisional ceiling — the corpus populations
separate cleanly either side of it.

**Raster resolution:** the exporter inspects the camera track and rasterizes at the tightest
zoom that asset actually reaches. Scenes are fixed at export time, so the export already knows
this. No device-side LOD selection, no pyramid.

**Raster layers animate by transform only** — translate, scale, rotate, opacity. Internals
cannot morph. Content needing internal animation must stay vector.

## 4. The exporter

Hooks `CairoRenderer.update_frame(self, scene, ...)`, called once per frame with the live scene.
**All public API — no fork, no patched internals**
([#3](https://github.com/bishboi/pocketanim/issues/3)).

| Need | API |
|---|---|
| Walk the tree | `Mobject.get_family()` over `scene.mobjects` |
| Geometry | `VMobject.points` → `(N, 3)` float64 |
| Curves | `get_cubic_bezier_tuples()` → `(n_curves, 4, 3)` |
| Style | `fill_color`, `fill_opacity`, `stroke_color`, `stroke_width`, `stroke_opacity` |

`tools/probe_scene_geometry.py` is a working reference for this traversal.

**Arbitrary-`t` evaluation is exact.** `Animation.interpolate(alpha)` is a pure function of
alpha — verified for `Transform`, `Create`, `FadeIn`, `Rotate`, and `ValueTracker` +
`always_redraw`. Evaluating out of order and returning to the same alpha gives byte-identical
geometry.

**But state is cumulative across animations.** `Animation.begin()` snapshots whatever the
previous animation left behind, so `t → (animation index, alpha)` requires the state at that
animation's start. This is precisely why snapshots sit at animation boundaries.

### 4.1 Affine detection is required, not an optimisation

**The exporter must recognise when a mobject's points changed by an affine transform — scale,
translate, rotate — and encode the transform, not the geometry.**

Measured, not projected. The Cartopy scene zooms with `coast.animate.scale(3.0)`, which changes
every one of its 235,948 points on every frame. The probe reports a **93.5% morphing fraction**
— static caching is defeated almost entirely, saving only 1.1×:

| Encoding of the whole 4.7 s scene | Size |
|---|---|
| Naive per-frame geometry | **402.6 MB** |
| Static-cached (no affine detection) | **379.2 MB** |
| With affine detection | ~1.4 MB geometry + a few bytes/frame |
| MP4 baseline | 1.03 MB |

Without affine detection the IR is **~390× larger than the video**. With it, roughly par at
this duration and far ahead at any realistic one. **One exporter feature is worth ~275× here.**

An ordinary pan or zoom over dense content is catastrophic without this. Detection is
straightforward — fit a transform between consecutive point sets and check residual against a
tolerance — but it must exist before the exporter is considered working.

Note that `tools/probe_scene_geometry.py` deliberately does **not** do this. It measures raw
point deltas, so its output is a naive upper bound, not an IR estimate.

**Build environment:** Manim 0.21.0 in a virtualenv. It will *not* install against a Debian
system Python — `srt` fails to build against patched setuptools. LaTeX is required for anything
using `MathTex`, which includes `Axes` coordinate labels, not just explicit formulas.

## 5. The Android player

**Skia via the Android `Canvas` API**, driven from `RenderNode` display lists in a custom
`SurfaceView`. Compose for app chrome only. **`minSdk 29`**
([#8](https://github.com/bishboi/pocketanim/issues/8)).

Not OpenGL ES or Vulkan: requiring Vulkan 1.1 drops ~11% of handhelds concentrated in the floor
segment, and Flutter's Impeller — a funded, dedicated 2D GPU renderer — found hand-rolled path
rendering *"not acceptable for release on Android"*. If that team could not beat Skia at this,
we should not assume we can.

### 5.0 It exists, and most of it has been run

`player/` is three modules, split by what can be verified rather than by
convention:

| Module | What it is | Runs where |
|---|---|---|
| `core/` | Decoder, tier-1 interpreter, renderer, playback clock. No Android, no AWT. | Anywhere a JVM runs |
| `android/` | `SurfaceView` render loop, Skia sink, `AudioTrack` clock | Device only |
| `desktop/` | Verification harness. Not shipped. | Any desktop JVM |

**The whole design turns on one seam.** `core` asks the platform for exactly one
thing — a `PathSink` with `moveTo`/`cubicTo`/`close`/`fill`/`stroke`. Android
backs it with `Canvas`; the desktop harness backs it with Java2D. Everything
that decides *what the picture is* — decode, interpret, transform, project,
depth sort, shade, split subpaths — sits on the `core` side of that line, so
**the code that runs on the phone is the code that gets checked here** against
the §7.1 oracle. Without that seam the Android renderer would be unverifiable
until someone ran it on a device.

Both tiers produce the same type. `Scene.parse(bytes)` yields one from a
`.panm`; `Interpreter.build(Program.parse(text), assets)` yields one from a
`.panim`, expanding the program the way the device must. Past that point nothing
downstream can tell which tier it is playing.

**Verified by running it:**

| Check | Result |
|---|---|
| Three decoders agree field for field (`decode.py`, `PanimDecoder.java`, `player/core`) | 8/8 corpus scenes |
| Two interpreters agree field for field (`dsl/interpret.py`, `player/core`) | 10/10 programs |
| Shipping renderer vs the Cairo oracle, tier 3 | 0.00–0.01% pixels differing |
| Shipping renderer *and* interpreter vs the oracle, tier 1, end to end | **0.00% on all nine** |

The residual is antialiasing: mean absolute error is 0.01–0.21 out of 255 and
sits on edges. Cairo, Java2D and Skia cannot agree pixel-for-pixel and the spec
never asked them to; what is being checked is that the geometry, ordering,
shading and colour are the same.

**Compiled but never executed:** everything in `android/`. `dl.google.com` is
blocked in this environment, so `player/build.sh` compiles the Android layer
against a real framework jar from Maven Central (`org.robolectric:android-all`,
which carries AOSP's `android.jar` contents) rather than against an SDK. That
proves it builds against the real `android.*` API and nothing more. The render
loop, the surface lifecycle and the audio clock have not run. The Gradle build
alongside it is what to use where an SDK is available.

### 5.1 Playback

- **Audio is the master clock** when present. The renderer samples the scene at whatever time
  audio has reached ([#4](https://github.com/bishboi/pocketanim/issues/4)).
- **Silent playback uses the system clock.** A second clock source, not a special case — scenes
  play without audio whenever it has not been downloaded.
- **No live clock handover.** A scene playing silently whose audio arrives mid-playback finishes
  on the system clock; audio takes over on the next play or seek.
- **Under load, drop visual frames.** No adaptive quality ladder, no render-ahead buffer, no
  video fallback.

### 5.2 Seeking

1. Find the nearest snapshot at or before `t`; take static geometry from it.
2. For each morphing mobject, interpolate between the two keyframes bracketing `t`.
3. Render.

**No forward replay at any seek distance.** Cost is bounded by snapshot size, not seek distance.

**During a drag:** snap to the nearest keyframe while the finger is down; settle on the exact
time on release.

**With audio:** the audio decoder leads and visuals snap to where it lands (AAC frame
granularity, ~23 ms). **Silent:** the system clock is exact, with nothing to reposition.

### 5.3 Storage

([#15](https://github.com/bishboi/pocketanim/issues/15))

- **All IR cached eagerly** — the whole library, ~50 MB per thousand scenes. Every scene stays
  browsable and playable offline.
- **Audio on explicit user download only.** Predictable data use; respects metered connections.
- **LRU over audio under a size cap. IR is never evicted.**
- A scene with IR but no audio **plays silently** with an offer to fetch narration.

The two halves differ ~30× in size, so they get opposite policies.

**Scaling bound:** "cache all IR" holds to roughly a thousand scenes. At ten thousand it is
~500 MB and the policy inverts. Carry an explicit library-size assumption.

## 6. Audio

([#4](https://github.com/bishboi/pocketanim/issues/4))

- **AAC-LC 64 kbps**, ~1.44 MB per 3 minutes.
- **Per-segment**, with animation durations derived from clip lengths at export.
- **IR lands instantly; audio streams behind it.**

AAC over Opus costs ~2.5× the bytes but buys **hardware decode**. The renderer is CPU-bound at
the floor (Skia draws large paths on CPU before uploading), so trading bytes for CPU headroom is
correct when the renderer is what is most likely to fail.

**Tuning lever, if payload pressure appears:** mono AAC-LC 48 kbps or HE-AAC v1, both still
hardware-decoded. Neither changes the architecture.

## 7. Fidelity

**Target: perceptually identical.** A viewer comparing side by side sees no difference;
sub-pixel deviation is acceptable. Pixel-exactness is not achievable anyway — Skia and Cairo do
not rasterize identically.

**A golden-image CI harness is required from day one.** We own the format, so we own fidelity;
there is no upstream runtime to be correct on our behalf.

### 7.1 The harness exists

`tools/verify_fidelity.py` exports a scene while capturing Manim's own frames, decodes the IR,
re-renders the same frame indices through `exporter/reference_render.py`, and reports per-pixel
agreement.

**`exporter/reference_render.py` is the oracle.** It proves the format is correct independently
of any Android code, so when the Kotlin renderer disagrees with it, the bug is in the Kotlin.
Build the Android renderer against this, not against Manim directly.

#### The format has a second reader

`exporter/decode.py` was the only thing that read the IR, which meant nothing
distinguished *the format* from *whatever that file happens to do*.
`client/PanimDecoder.java` is an independent implementation written from this
spec — plain Java, no dependencies, no Android APIs, so it runs on any JVM. The
Android renderer will be its logic in Kotlin feeding `android.graphics.Path`,
so a disagreement here is a disagreement on the phone.

`tools/crosscheck_decoders.py` makes both emit the same canonical dump — header,
quantisation bounds, every atlas shape, every record's instance count, the
camera row, every instance of a probed frame — and compares them field by field.
Floats compare by tolerance rather than equality **on purpose**: Java dequantises
the atlas in float32 because that is what the device will do, Python in float64.
Everything that arrives as an integer, a float16 or a float32 must match
exactly, and does.

Verified on the cases where a layout bug would actually bite: a 182-record scene
with a camera track and variable-length instance records (normals present only
under `SHADE_IN_3D`), probed mid-timeline so keyframe replay is exercised rather
than just the opening snapshot; a 1,416-shape baked coastline; a 750-instance
shaded molecule; and a shape-free instances-only text asset.

One thing this exposed: the quantisation box was being recovered from the
extremes of the dequantised points, which only works when some point happens to
land on each extreme. It is now carried on the decoded IR.

### 7.2 What verification caught

Three spec-mandated requirements were **missing from the exporter while every statistic looked
healthy** — atlas hit rates, sizes and affine detection were all fine. Only rendering a frame
revealed them:

| Fix | ThreeDCamera pixels differing |
|---|---|
| (as first written — no camera) | **44.6%** |
| + camera track | 21.0% |
| + per-frame depth sort | 20.9% |
| + normal-based shading | 16.1% |
| + consistent normal orientation | **7.0%** |

The missing camera track is the instructive one: §3.6 says the exporter must never flatten, and
it was silently shipping unprojected world coordinates. No size or hit-rate metric can see that.

The last fix is worth remembering: a plane fit gives an **arbitrary normal sign**, so neighbouring
faces shaded in opposite directions and surfaces came out banded. Orienting every normal into one
hemisphere took 16% to 7%. Winding-order cross products were tried and were *worse* — these are
Bezier control points, not polygon vertices.

### 7.3 Measured agreement

Sampled IR versus Manim's own frames, every 60th frame at 720p:

| Scene | Mean MAE (of 255) | Pixels differing | Previously |
|---|---|---|---|
| LatexDerivation | 0.01 | **0.00%** | 0.00% |
| SurfaceOrbit | 0.31 | **0.00%** | 10.70% |
| CodeWalkthrough | 0.09 | **0.07%** | 0.02% |
| ThreeDCamera | 0.67 | **0.09%** | 7.02% |
| CartopyMap | 0.19 | **0.21%** | 0.25% |
| PlotGeometry | 0.60 | **0.45%** | 0.45% |
| MolecularStructure | 0.41 | **0.46%** | 0.75% |

**Every scene is now under half a percent**, and two are pixel-identical.
CartopyMap remains the striking one: 235,948 points reconstructed through
16-bit quantisation, atlas deduplication and affine transforms, landing within
a fifth of a percent.

The two 3D outliers were not a shading or projection nuance, as the earlier
figures were read to mean. They were **one stale read**: Manim caches the
camera's rotation matrix in a field it only refreshes inside `capture_mobjects`
— that is, during the render — so reading it before the render returned the
*previous* frame's orientation and the camera track lagged its own geometry by
a frame. The error vanished wherever the camera was momentarily still and grew
with camera speed, which is exactly why it looked like a projection problem.
The exporter now regenerates the matrix at capture time.

CodeWalkthrough reads slightly worse than its published 0.02%. That figure
compared reference frames and IR records that were **both** indexed by
`update_frame` call, so they were mistimed identically and the error cancelled.
0.07% is the same data compared against the right frames.

**This is what "perceptually identical" means in practice, and it is a number
rather than an aspiration.**

Suggested CI gate: fail above 1% differing pixels, with no 2D/3D distinction —
the 3D allowance existed only to accommodate the camera bug.

### 7.4 A fourth bug, and why it matters most

After the three 3D fixes above, `CodeWalkthrough` still measured 6.98%. Rendering a frame showed
**a code block containing no code**: the title and nearly every glyph were missing.

Cause: **Text and Code glyphs render fully opaque but report `fill_opacity == 0` on the
attribute.** Manim keeps the authoritative value in `fill_rgbas`. The exporter was reading the
attribute, writing correct colours at zero alpha, and producing thousands of invisible glyphs.

Every statistic was healthy — 2,595 atlas shapes, 90.5% hit rate, plausible file size, instance
counts in range. **No numerical check could distinguish "exported the glyphs" from "exported
2,595 invisible glyphs."** Fix: read style through Manim's getters, never the raw attributes.
6.98% → 0.02%.

This is the strongest argument for the oracle existing at all, and for building the Android
renderer against it rather than against Manim directly.

## 8. Measured baselines

720p30, Manim 0.21.0, from `tools/probe_scene_geometry.py` and `corpus/measurements/`.

All six corpus scenes:

| Scene | Points/frame | Mobjects | Morphing | Naive dump | Static-cached | MP4 | Bitrate |
|---|---|---|---|---|---|---|---|
| LatexDerivation | 2,356 | 55 | 45.7% | 5.43 MB | 2.55 MB | 153 KB | 147 kbps |
| PlotGeometry | 1,917 | 66 | 24.8% | 9.20 MB | 2.29 MB | 345 KB | 195 kbps |
| CodeWalkthrough | 6,382 | 128 | 35.9% | 21.4 MB | 7.73 MB | 251 KB | 187 kbps |
| ThreeDCamera | 7,746 | 657 | **0.49%** | 25.4 MB | **153 KB** | 2.72 MB | **2227 kbps** |
| CartopyMap | 237,928 | 1,450 | **93.5%** | 402.6 MB | 379.2 MB | 1.03 MB | 1413 kbps |
| MolecularStructure | 42,774 | **2,911** | 15.4% | 124.7 MB | 19.8 MB | 259 KB | 235 kbps |

**Read these honestly.** The naive and static-cached columns are an **upper bound on a naive
all-paths IR**, not a prediction of the real one — they model neither the glyph atlas (§3.5),
16-bit quantization (§3.4), nor sub-30fps keyframing (§3.1). The `CodeWalkthrough` row in
particular is almost entirely glyph outlines, which the atlas is designed to collapse.

**What is a genuine result:** 2D Manim content encodes at only **147–195 kbps** because H.264
is excellent at flat-shaded vector graphics on static backgrounds. The codec already exploits
much of the structure our IR intends to. For 2D, **audio outweighs video**, so eliminating video
cannot deliver an order of magnitude — the bandwidth case for 2D is modest. 3D is where it
lands, at 17.8× before optimization.

### 8.1 The organising principle

> **IR cost scales with *change*. Video cost scales with *time*.**

This explains every row above better than "2D versus 3D", which the map used as a proxy for
most of its life:

- **3D camera orbit** — geometry static, camera moves. IR 17.8× smaller.
- **Cartopy map** — geometry static and large, paid once. IR is 1,382 KB against a 1,034 KB
  MP4, so it *loses* at the measured 6 s — but the IR does not grow with duration and the video
  does. **Crossover is ~8 s**; at 30 s the IR wins 3.8×, at 3 min it wins 22×. The measured loss
  is an artefact of a short test clip, not a property of maps.
- **LaTeX derivation** — 45.7% morphing, the worst case, and the weakest IR result.

Content that sits still is nearly free in the IR and expensive in video. Content that changes
constantly is expensive in both. **Use this, not the 2D/3D split, when estimating a scene.**

### 8.2 Refinement: video cost tracks moving *pixel area*, not dimensionality

Both 3D scenes orbit a camera over static geometry, yet their video costs differ 9.5×:

| Scene | Content | Bitrate |
|---|---|---|
| ThreeDCamera | 24×24 checkerboard `Surface` filling the frame | **2227 kbps** |
| MolecularStructure | 15 small spheres on an empty background | **235 kbps** |

So "3D is expensive in video" is the wrong generalisation. **Densely-filled moving content is
expensive in video; sparse moving content is not.** `ThreeDCamera` is expensive because a
textured surface covers most of the frame and every pixel changes under rotation.

The practical consequence for estimating a scene: multiply the two axes.

- **Static geometry + large moving pixel area** → the IR's best case by far. This is where the
  17.8× came from, and it is what to look for when judging whether a scene is worth converting.
- **Static geometry + small moving pixel area** (the molecule) → both formats are cheap; the IR
  still wins on duration-independence, but the absolute saving is small.
- **Morphing geometry** → expensive in the IR regardless of what video does.

Curve counts for the four ordinary scenes run **~620 to ~2,600 per frame**, comfortably under
Skia's 16,384-verb cliff. CartopyMap and MolecularStructure blow past it, which is what the
raster fallback (§3.7) and affine detection (§4.1) exist for.

**Object count is a second, independent bottleneck.** MolecularStructure peaks at **2,911
mobjects** against 55–128 for 2D scenes — `Sphere(resolution=(12,12))` expands into ~144
sub-objects each, so 15 atoms become thousands of small mobjects with low point counts.
**Draw-call batching, not path throughput, is what limits this scene class.**

### 8.3 The measurement that matters most

**Affine detection is worth more than every other optimisation combined**, demonstrated
independently by two unrelated scenes:

| Scene | Affine animation | Reported morphing | Cost if mis-encoded |
|---|---|---|---|
| CartopyMap | `.animate.scale(3.0)` | 93.5% | 379 MB vs a 1.03 MB MP4 (~390×) |
| MolecularStructure | `LaggedStart(GrowFromCenter(...))` | 15.4% | 19.8 MB vs a 259 KB MP4 (~78×) |

In both, the "morphing" geometry is a transform of unchanged points.

Note too that **static caching — worth 162× on ThreeDCamera and 6.3× on MolecularStructure —
collapses to 1.1× on CartopyMap.** The static/morphing distinction is load-bearing everywhere
except where affine animations defeat it, which is exactly where the payload is largest. The
two mechanisms are complements, not alternatives.

### 8.4 Real exporter results — supersede the estimates above

A working exporter exists (`exporter/`). These are measured `.panm` outputs, not models:

| Scene | IR @30fps | Tuned (10fps + quantised) | MP4 | vs MP4 | Naive probe predicted |
|---|---|---|---|---|---|
| LatexDerivation | **143 KB** | — | 153 KB | **0.94× — wins** | 5.43 MB |
| ThreeDCamera | 281 KB | **223 KB** | 2,719 KB | **0.08× — wins 12.2×** | 25.4 MB |
| PlotGeometry | 354 KB | — | 345 KB | 1.03× — par | 9.20 MB |
| CodeWalkthrough | 1,859 KB | **1,436 KB** | 251 KB | 5.7× larger | 21.4 MB |
| MolecularStructure | 6,178 KB | **1,922 KB** | 259 KB | 7.4× larger | 124.7 MB |
| CartopyMap | 11,311 KB | **4,274 KB** | 1,035 KB | 4.1× larger | 402.6 MB |

Every scene beat its naive prediction by **10–37×**. Tuning (10 fps keyframes plus quantised
transforms) bought a further 1.3–3.2×, most on the instance-dominated scenes.

**Three scenes win or draw; three still lose by 4–7×.** The v2 fixes in §10 target exactly
those three, but on today's numbers a mixed library is roughly a wash on bandwidth — which
means **offline playback and instant start, not CDN cost, are what justify this project.**
Those two drivers are unaffected by any of these measurements and apply to every scene.

Atlas performance confirms the unification works:

| Scene | Atlas shapes | Hit rate | Affine reuses |
|---|---|---|---|
| MolecularStructure | **14** | **100%** | 635,572 |
| CartopyMap | 1,443 | 99.3% | 202,969 |
| ThreeDCamera | 612 | 99.6% | 160,175 |
| LatexDerivation | 167 | 97.3% | 5,925 |
| CodeWalkthrough | 2,595 | 90.5% | 24,141 |

Fifteen spheres deduplicate to one shape, reused 635,572 times under different matrices.

**The dominant cost is instance records, not geometry.** Molecular's entire atlas is 240 points,
yet its IR is megabytes because it emits **95,809 instance records** (Cartopy: 153,830) at ~62
bytes each. Everything in §8 above reasoned about *points*; for animation-heavy scenes the real
format is dominated by *per-instance-per-keyframe records*.

This is the predictable price of keyframe sampling over full parametric encoding:
`LaggedStart(GrowFromCenter(...))` over 2,911 atoms is one parametric statement and 95,809
sampled records. The trade was made deliberately — this is its first measurement.

**Two scene classes, two different bottlenecks:**

- **Instance-dominated** (Molecular, Cartopy) — keyframe decimation to 10 fps buys 2.1–2.3×.
- **Atlas-dominated** (CodeWalkthrough) — decimation buys only 1.24×, because the cost is 2,595
  distinct shapes generated by `Transform` interpolating between two code blocks. Each
  intermediate is genuinely new geometry that cannot deduplicate.

### 8.5 A hazard for scene authors

**The morphing fraction measures which Manim API was used, not the visual intent.**
ThreeDCamera (0.49%) and CartopyMap (93.5%) both depict static geometry under a moving
viewpoint. `ThreeDScene` moves a camera and leaves points alone; `.animate.scale()` rewrites
every point. Same intent, opposite IR cost.

Affine detection makes this moot, which is the strongest argument for treating it as mandatory.
Without it, scene authors would need to know which API is cheap — an unreasonable thing to ask.

## 9. Gates before building

**[Measure render throughput on a low-end device](https://github.com/bishboi/pocketanim/issues/6)
is a go/no-go gate, not a sizing exercise.** There is no MP4 fallback, so a negative result has
no mitigation inside this design. It needs a real low-end phone and should measure:

- Static versus morphing path counts **separately** — cached geometry is far cheaper.
- **Many small objects** as a distinct case from few large paths (the 3D scene's 657 mobjects).
- **Frame-drop behaviour under sustained overload**, not just average frame time.
- **Cold snapshot decode plus one frame**, which sets the seek latency budget and hence
  snapshot density.
- The **point count at which a floor device stops holding 30 fps** — this becomes the raster
  fallback threshold (§3.7).

Pull this forward. It needs no final IR, only a synthetic path-heavy workload, and a bad result
invalidates much of the design above.

## 9.5 Tier 1: ship the program, not the samples

Measured after the sampled IR was built, and it changes the economics. The
**source program is itself a 99%+ reduction**, because the IR stores the result
of computation at every keyframe while the program stores the computation once.

Proven end to end (`dsl/`), against Manim's own frames:

| Scene | Program | MP4 | Reduction | Pixels differing |
|---|---|---|---|---|
| VerbTest (`Create` + `Transform`) | **127 B** | 57 KB | **99.78%** | **0.04%** |
| SurfaceOrbit (procedural 3D) | **196 B** | 1,445 KB | **99.986%** | 2.98% |

On SurfaceOrbit the same scene is 162,868 B as sampled IR at 10.70% differing —
so the program is **831× smaller at roughly a quarter of the error**. It dominates
rather than trading, because the device computes at full precision instead of
replaying 16-bit quantised samples. **Shipping the computation is lossless by
construction; shipping its sampled output cannot be.**

### The semantics reproduce exactly

The risk §3.1 cited for rejecting parametric encoding — silent drift from
mismatched semantics — measured as zero:

| Component | Max error vs Manim |
|---|---|
| Circle geometry | **0.0** |
| `Create` / `pointwise_become_partial` | 2.2e-16, correct point count at every alpha |
| `Transform` (align + interpolate) | 2.2e-16 at every alpha |

`Transform` first showed 0.277 error at alpha 0.25/0.75 while exact at 0.5 and
1.0 — symmetric midpoint error with correct endpoints is a **missing rate
function**, not an alignment bug. Manim defaults both verbs to `smooth`.
**The failure mode is forgetting a documented behaviour, not being unable to
reproduce one**, and the harness catches exactly that.

### Coverage and fidelity: 9 of 10, verified

Coverage and fidelity are **separate axes**. Tier 1 means *expressible*; the
harness separately says *correct*. A scene can reach tier 1 and still render
badly, so never report one without the other.

| Scene | Tier | Program | Pixels differing |
|---|---|---|---|
| TextHybrid | **1** | 162 B | **0.03%** |
| VerbTest | **1** | 127 B | **0.04%** |
| TextReuse | **1** | 110 B | **0.05%** |
| ThreeDCamera | **1** | 180 B | **0.06%** |
| CartopyMap | **1** | 140 B | **0.27%** |
| LatexDerivation | **1** | 465 B | **0.36%** |
| CodeWalkthrough | **1** | 263 B | **0.51%** |
| MolecularStructure | **1** | 226 B | 2.44% |
| SurfaceOrbit | **1** | 196 B | 2.98% |
| LongLesson (166 s) | **1** | 2,005 B | 0.37% |
| PlotGeometry | 3 | — | `ValueTracker` / `always_redraw` |

Sampled every 10th frame. **Every tier-1 scene is under 3%, seven of nine
under 1%.** ThreeDCamera used to be the honest exception at 12.79% — *worse*
than its own sampled IR — and is now 0.06%. See "Four frame-timing bugs" below
for why, because the cause was not what the number suggested.

**One scene remains, and it is the one that always will.** `ValueTracker` +
`always_redraw` is **fundamental**: arbitrary Python recomputing geometry every
frame cannot be a verb, ever. This is the hard ceiling on tier 1 and the reason
tier 3 must exist permanently.

#### Four frame-timing bugs, and why 12.79% was misleading

ThreeDCamera's error looked like a camera-model problem: it appeared only once
the camera moved, peaked mid-move and left a persistent plateau. It was not.
Substituting Manim's own camera track into the program's IR dropped the
difference to **0.00% at every frame**, which proved the baked geometry,
normals, shading and depth ordering were already exact and put the whole
residual in the camera track. Recovering Manim's per-frame `phi`/`theta` then
showed the program's track was **bit-exact** — 0 or 2.2e-16 — at a constant
offset of two frames. There was no rate-function bug, no interpolation bug and
no spin-rate bug. Four separate off-by-ones were stacked on top of each other,
three of them in how a frame is *identified* rather than in how it is drawn:

1. **The harness counted the wrong thing.** It indexed Manim's frames by
   `update_frame` call, and calls are not frames: an extra one fires at every
   animation boundary (see 3), so the comparison drifted one frame per
   animation. `renderer.time` is how many frames have actually been written,
   which is the frame the render is about to become, so `round(time × fps)`
   identifies frames rather than counting calls.
2. **The program had no opening frame.** Manim renders the scene's state once at
   t=0 before the first animation's first step. The interpreter started its
   first animation at frame 0, so every later frame was one early and the
   closing frame was missing. It now emits the opening state after any leading
   `show` and before the first frame-producing verb, which is also what puts
   objects added before the first `play` on stage in frame 0.
3. **The static-layer render is not a frame.** Manim caches the static
   mobjects by rendering them through `update_frame` with an explicit mobject
   list, and writes no frame for it. Both call sites pass a mobject list, so
   arguments cannot tell them apart; `save_static_frame_data` is wrapped
   instead. Counting that partial render — whose pixels hold only the static
   layer — as a frame is what produced two renders claiming the same index.
4. **The last frame of an ambient rotation does not advance.** Over a wait of
   *n* frames Manim applies *n−1* increments and repeats the last orientation.
   Measured independently on ThreeDCamera and SurfaceOrbit, both of which spiked
   on exactly that frame.

The fourth one is the instructive one. Its visible cost was a single frame the
harness happened to sample — but the orientation it leaves behind is the one the
*trailing hold* renders, so a whole second of video sat 0.57° out where **the
harness never looks**. A measurement that only samples animated frames cannot
see a static error, and the fix was only found because the frame-count mismatch
was chased instead of explained away.

The first three also applied to the **sampled** exporter, which recorded one
record per call and so shipped an IR shorter than its own scene, with the
trailing hold missing entirely and everything after the first animation playing
early. Both tiers are fixed, and both are re-measured in §7.3 and above.

Correcting these took ThreeDCamera from 12.79% to 0.06%, CartopyMap from 3.39%
to 0.27% and SurfaceOrbit from 4.96% to 2.98% at tier 1, and at tier 3 took
SurfaceOrbit from 10.70% to 0.00% and ThreeDCamera from 7.02% to 0.09%. The
scenes that read slightly worse than their previously published figures are
sampled three times as densely here, or were previously compared against
reference frames that were mistimed in the same direction as the IR so the
error cancelled. The new numbers are the honest ones.

#### What `LaggedStart` actually cost

It was predicted to be mechanical, and the *timing* was — the two-level clock
(group linear, child `smooth`, child *i* starting at `i·lag·span`) is character
for character the arithmetic `Write` already used. Three things were not:

- **The group Manim hands you is empty.** `AnimationGroup` excludes introducer
  animations from the group it builds, and `GrowFromCenter` is an introducer,
  so `anim.mobject` has no submobjects. The group has to be reassembled from
  the sub-animations' own targets, in animation order.
- **A baked group is a flat instance list.** One sphere is 144 faces, so a
  per-child animation needs to know where each child's run starts. The program
  carries the run lengths (`groups=144,144,…`), counted with exactly the same
  `len(points) >= 4` filter the asset baker applies — a disagreement of one
  would misalign every subsequent child.
- **Manim adds each child to the scene on clean-up.** Every atom was therefore
  declared a second time as its own asset and shown, drawing the molecule
  twice. Mobjects covered by a group asset are now marked, and `add` skips them.

The growth itself is exact and needs nothing shipped: `GrowFromCenter`
interpolates from a zero-size copy at the child's centre, which point by point
is `c + α(p − c)` — a uniform scale about `c`, composable onto whatever
transform the instance already carries. `c` is the child's bounding-box centre,
which the runtime measures from geometry it already has.

#### Harness note: the trailing hold is never compared

`verify_dsl` still reports two frame counts that do not match — 241 Manim frames
against 271 for MolecularStructure. Now that both are indexed by playback time
this is not drift: Manim renders a *static* `wait` as a frozen frame written
many times, calling `update_frame` two or three times instead of once per frame,
so no reference image exists for the hold at all.

The program is right to expand the hold — the player has to show it — but the
consequence is that **the trailing hold is never compared**, and a bug confined
to it does not show up here. That is not hypothetical: the ambient-rotation
off-by-one above left the entire final second 0.57° out of true, and the harness
was blind to all of it. Anything that changes the state a hold renders needs
checking by hand, or the harness needs a frozen-frame case.

### Superseded: coverage was 5 of 10

Coverage and fidelity are **separate axes**. Tier 1 means *expressible*; the
harness separately says *correct*. A scene can reach tier 1 and still render
badly, so never report one without the other.

| Scene | Tier | Program | Pixels differing |
|---|---|---|---|
| TextReuse | **1** | 110 B | **0.00%** |
| VerbTest | **1** | 127 B | **0.01%** |
| TextHybrid | **1** | 162 B | **0.04%** |
| CartopyMap | **1** | 140 B | 3.39% |
| SurfaceOrbit | **1** | 196 B | 4.96% |
| LatexDerivation | 3 | — | `TransformMatchingTex` |
| CodeWalkthrough | 3 | — | asset-to-asset `Transform` |
| PlotGeometry | 3 | — | `ValueTracker` / `always_redraw` |
| MolecularStructure | 3 | — | `LaggedStart` |
| ThreeDCamera | 3 | — | surface built via `axes.c2p` |

**One blocker per scene now**, and they sort into three kinds:

- **Glyph-level matching** (LatexDerivation, CodeWalkthrough) — `TransformMatchingTex`
  and asset-to-asset `Transform` are *one capability*. The highest-value thing
  left, and it operates on the glyph atlas §7 already describes.
- **Mechanical** (`LaggedStart`, a declarative surface form) — more vocabulary.
- **Fundamental** (`ValueTracker` + `always_redraw`) — arbitrary Python
  recomputing geometry per frame. **This cannot be program, ever.** It is the
  hard limit of tier 1 and the reason tier 3 must exist.

### The structural guard

Three separate bugs silently dropped an animation by falling through a branch
with no `else` — `FadeIn`, `Transform` operands, and `.animate` on a
`ValueTracker`. Each shipped a program that *claimed tier 1* while rendering the
wrong thing; the `.animate` one lost seven seconds of PlotGeometry.

The exporter now asserts that **every `play()` produces at least one verb**. A
play that emits nothing is always a drop, whatever the cause. Keep this guard as
the vocabulary grows: each new verb is another chance to claim success while
emitting something that does not run.

### Superseded: coverage was 5 of 10 (pre-fidelity)

After adding text assets, groups, `.animate`, `FadeIn`/`FadeOut`, `Write`,
rectangles and rate functions:

| Scene | Tier | Program |
|---|---|---|
| TextReuse | **1** | 96 B |
| VerbTest | **1** | 120 B |
| CartopyMap | **1** | 126 B |
| TextHybrid | **1** | 148 B |
| SurfaceOrbit | **1** | 189 B |
| LatexDerivation, PlotGeometry, ThreeDCamera, MolecularStructure, CodeWalkthrough | 3 | — |

`CartopyMap` is the notable one: 126 bytes plus a cached coastline asset, where
the naive sampled dump was 402 MB.

**Remaining blockers, down from 16 distinct kinds to 8:**

| Blocker | Nature |
|---|---|
| `Axes`, `ThreeDAxes`, `ParametricFunction` | composite/procedural — more vocabulary |
| Surface function using `axes.c2p` | needs a declarative surface form, not source scraping |
| `LaggedStart` | mechanical — offset start times |
| `TransformMatchingTex`, asset-to-asset `Transform` | **one capability: glyph-level matching** |

The text cluster is gone entirely. What is left splits cleanly into vocabulary
(mechanical) and **one genuinely hard capability** — matching glyphs between two
baked text assets, which `TransformMatchingTex` also needs. That capability is
the single highest-value thing left to build, and it operates on exactly the
glyph atlas §7 already describes.

### Superseded: coverage was 2 of 8

`dsl/export_dsl.py` maps a Manim scene onto DSL verbs and records a blocker
rather than guessing when it cannot. Against the corpus — which was built to
span the *hardest* envelope, so this understates a real library:

| Blocker | Scenes | Nature |
|---|---|---|
| `VGroup` / `Group` | 5 | container; mechanical |
| `linear` rate_func | 4 | one parameter |
| `Write`, `Text`, `MathTex`, `Tex`, `Code` | 5 | **one problem: text as assets** |
| `_AnimationBuilder` (`.animate`) | 2 | mechanical |
| `ParametricFunction`, `Axes`, `ThreeDAxes` | 3 | procedural/composite, as `Surface` |
| `TransformMatchingTex` | 1 | genuinely hard — glyph-level matching |
| `LaggedStart` | 1 | mechanical — offset start times |

**Almost nothing here is a fundamental obstacle.** The list is dominated by
missing vocabulary and by text, and text is a tier-2 asset problem that every
tier shares.

### Tier 2 measured: the glyph atlas must be library-wide

Text is the dominant blocker, and it can never be tier 1 — Manim hands us
outlines with no glyph identity (§3.5) and LaTeX cannot run on device. It ships
as a referenced asset.

The first implementation put glyph outlines inside each text asset. Measured,
that costs **682 bytes per glyph**, so a library re-ships the alphabet once per
caption. Deduplicating at the **glyph** level instead:

| | Per-string assets | Library-wide atlas |
|---|---|---|
| Text asset | 6,817 B | **537 B** (12.7× smaller) |
| Shared atlas | — | 6,322 B, once |

**Amortisation is measured, not projected.** Exporting a second scene whose text
("animation") reuses letters from the first ("pocketanim") grew the shared atlas
by **exactly 0 bytes**. That scene's marginal cost is 585 B against a 27,193 B
MP4 — **97.85%** — verified at **0.05%** of pixels differing.

This confirms §3.5's "per-bundle atlas" was the wrong call for bandwidth, as
that section already suspected. Make it library-wide.

Hybrid result, program plus text asset:

| Scene | Program | Asset | MP4 | Pixels differing |
|---|---|---|---|---|
| TextHybrid | 149 B | 537 B | 65,359 B | **0.26%** |
| TextReuse | 97 B | 488 B | 27,193 B | **0.05%** |

### The three tiers

1. **Program** — 99.8–99.99%, fidelity equal or better than sampling.
2. **Assets** — glyph outlines and imported geometry, **library-wide and
   cached**, not per bundle. This is what makes text scenes viable and is a
   change from §3.5.
3. **Sampled IR** — already built, verified 0.00–0.99% on five of six scenes.
   Handles whatever the DSL cannot express.

The exporter attempts tier 1 and falls back, so nothing already built is wasted
and the worst case for any scene is the 9× the sampled IR already delivers.

## 10. Exporter v2 — mostly overtaken by tier 1

**This section was written when six of ten corpus scenes fell back to sampled IR and three of
them lost to MP4 by 4–7×.** Tier 1 now covers **ten of eleven**. Only PlotGeometry still uses
the sampled path, and only because `ValueTracker` + `always_redraw` is the one thing a program
cannot express (§9.5). Three of the four fixes below targeted scenes that no longer use tier 3
at all, so the ordering they were given is obsolete.

Measured on the one scene that still needs it — PlotGeometry, 435 frames:

| | Bytes | Atlas | Instances |
|---|---|---|---|
| 30 fps keyframes | 365,428 | ~157,152 | ~258,850 |
| 10 fps keyframes | **249,690** | ~157,152 | ~92,600 |

The gain is **1.46×**, and the shape of what is left inverts §8.4's conclusion. That section
found instance records dominate; here, after decimation, the IR is **63% atlas**. Those 371
shapes are geometry `always_redraw` genuinely recomputes each frame, so no amount of
deduplication removes them — the same property that keeps the scene out of tier 1 is what makes
its atlas irreducible.

Status of the four, against the corpus as it now stands:

1. ~~**Factor group transforms.**~~ Targeted Cartopy's 1,429 polylines sharing one matrix.
   **Cartopy is tier 1** — 140 B of program. Nothing in tier 3 has this shape any more.
2. ~~**A morph instance type.**~~ Targeted CodeWalkthrough's 2,595 intermediates from
   `Transform`. **CodeWalkthrough is tier 1** — 263 B. PlotGeometry's shapes are not
   interpolations between two known endpoints, so this would not help it either.
3. **Per-mobject keyframe density.** Still pays: 1.46× measured above with a single global
   stride, and §3.3 already asks for per-mobject rates. The only fix here with a live target.
4. **Further transform quantisation.** Now float16 linear plus float32 translation (30 bytes,
   from 48); full 16-bit fixed point over scene bounds would reach 24. Attacks the 37% of
   PlotGeometry that is instances.

**The useful conclusion is not about the fixes.** Making a scene expressible as a program beat
every one of these optimisations by two to three orders of magnitude — Cartopy went from
11,311 KB of tuned IR to 140 B of program. Effort on *tier-1 coverage* dominates effort on
tier-3 encoding, and will keep doing so until something other than `always_redraw` lands in
the fallback.

## 11. Open items

- **Device throughput is ungated, but the load it will place on the rasteriser is now
  measured.** The gate still needs a physical low-end phone. What the player can be asked
  without one is how much work it hands Skia per frame:

  | Scene | Draws / frame | Verbs / frame | Max verbs in one path |
  |---|---|---|---|
  | MolecularStructure | **5,120** | 15,586 | 10 |
  | CartopyMap | 1,426 | **62,054** | **10,298** |
  | SurfaceOrbit | 1,152 | 3,456 | 6 |
  | ThreeDCamera | 996 | 2,992 | 6 |
  | CodeWalkthrough | 90 | 1,882 | 37 |
  | LatexDerivation | 68 | 1,515 | 40 |
  | PlotGeometry (tier 3) | 57 | 587 | 47 |
  | TextHybrid / TextReuse | 11 / 10 | 299 / 277 | 44 |
  | VerbTest | 1 | 9 | 10 |

  **§3.7's 16,384-verb cliff is not being hit.** That limit
  (`kMaxGPUPathRendererVerbs`) is per *path*, and the largest single path in the corpus is
  CartopyMap's 10,298-verb coastline — 63% of it. Close enough to matter: a denser map, or one
  more zoom level of coastline detail, crosses it and falls to CPU rasterisation.
  `tools/build_library.py` now reports any shape past half the limit at packaging time, so
  crossing it is noticed rather than discovered as a device that renders one scene slowly.
  Splitting such a path is *not* implemented, and should not be done blindly: splitting a
  filled path changes what it fills, so only stroke-only geometry can be divided safely.

  **The live risk is draw calls.** MolecularStructure issues 5,120 `drawPath` calls per frame
  — 154,000 per second at 30 fps — because 15 spheres of 144 faces each are 2,160 separate
  quads, fill and stroke apiece. That is the number most likely to miss frame rate on a low-end
  phone.

  **Batching same-style adjacent faces does not fix it, and that was measured rather than
  assumed.** In a mid-timeline frame of MolecularStructure, 2,910 faces in draw order collapse
  to only 2,595 runs of equal colour — an 11% saving, not worth the complexity. The reason is
  the interesting part: those 2,910 faces carry **435 distinct fills derived from 5 base
  colours**. Shading is per face, so depth-adjacent faces share a base colour but almost never a
  final one. Quantising the shade to recover batching does not pay either — 8 levels buys a 33%
  reduction for up to 16/255 of channel error, which is visible banding:

  | Shade levels | Distinct fills | Adjacent runs | Max channel error |
  |---|---|---|---|
  | exact | 435 | 2,595 | 0 |
  | 32 | 72 | 2,329 | 4 |
  | 16 | 40 | 2,196 | 8 |
  | 8 | 24 | 1,958 | 16 |

  So the draw-call count is not a batching problem, it is a **shading-model** problem: one flat
  colour per face means one draw per face, whatever the ordering. The fixes that would actually
  work are the depth-tested layer §3.6 defers, which removes the painter-order constraint, or
  moving to interpolated vertex colours so a whole solid is one draw. Both are larger than they
  look, and neither should be started before the device gate says the problem is real.

  Geometry cost is *not* the worry: 1.7 ms/frame on the worst scene, on a desktop CPU,
  excluding rasterisation. A weak lower bound — a low-end phone is perhaps an order of
  magnitude slower — but it points at the rasteriser rather than at the maths.

  There is still no MP4 fallback, so a bad device result has nowhere to fall back to.
- ~~**The tier-1 interpreter materialises every frame up front.**~~ **Fixed.** It measured at
  **98.8 MB retained** for MolecularStructure, which a phone does not have to spare, so this was
  a defect rather than a note. Each verb is now a resumable `Runner` — its per-frame body was
  already a pure function of (state at the verb's start, frame number) — and verb boundaries are
  checkpointed, so the player holds one frame instead of all of them:

  | Scene | Before | After |
  |---|---|---|
  | MolecularStructure | 98.8 MB | **1.6 MB** |
  | CartopyMap | 31.9 MB | **6.7 MB** |
  | ThreeDCamera | 23.0 MB | **0.7 MB** |
  | CodeWalkthrough | 4.6 MB | **0.8 MB** |

  CartopyMap stays largest because most of its footprint is a 732,852-float coastline — that is
  content, not frames, and no amount of laziness removes it.

  Playing forward costs one verb body per frame; seeking backwards restores the nearest verb
  boundary and replays *inside that verb only*, so cost is bounded by the longest verb rather
  than by how far the seek went — the same property §5.2 relies on for tier 3. **Seeking is
  verified exact**, which matters because a frame rebuilt from a checkpoint could otherwise
  depend on how it was reached: every frame is digested on a forward pass, then re-requested
  in reverse, shuffled, repeated and interleaved with the ends. All 18 corpus files match on
  all four orders (`VerifyKt <scene> seektest`).

  One consequence worth stating: the device no longer keeps transient reveal geometry, so its
  atlas ids differ from the reference interpreter's by design. The interpreter cross-check
  therefore compares the *geometry each instance resolves to* rather than the id — which is
  what is actually drawn, and a better check than the one it replaced.
- **The Android layer has never run.** It compiles against the real framework (§5.0); that is
  all a compiler can tell you. The render thread, surface lifecycle, `AudioTrack` clock,
  `MediaCodec` audio decode and seek-during-drag behaviour are unexercised.
- ~~**Corpus scenes are 6–14.5 s.**~~ **Measured at three minutes.**
  `corpus/scenes/11_long_lesson.py` is a **166-second** explainer, built to be representative
  rather than favourable: roughly half its runtime is spent holding still while a viewer reads,
  which is what a real lesson does. Every 3-minute figure above was extrapolation; this is not.

  | Encoding | Bytes | vs MP4 | Per second of runtime |
  |---|---|---|---|
  | **Tier 1 program** | **2,005** | — | **12 B/s** |
  | Tier 1 playable (program + its 14 text assets) | **13,933** | **133× smaller** | 84 B/s |
  | Tier 3 sampled IR | 1,159,936 | 1.6× smaller | 6,986 B/s |
  | MP4, 720p30 | 1,853,831 | — | 11,165 B/s |

  The per-second column is §8.1's organising principle stated as a measurement: **video costs
  11,165 B for every second that passes; the program costs 12.** The scene's shared glyph
  geometry is not counted in tier 1 above because it lives in the library atlas (51,606 B for
  eleven scenes) and is paid once, which is the whole argument of §3.5.

  Note what the long scene did *not* change: tier 3 still only beats MP4 by 1.6×, consistent
  with §8.4's mixed picture. **The duration argument belongs to tier 1, not to sampled IR** —
  sampling still stores something per frame, so it still scales with time, just more cheaply
  than video does.

  Fidelity against Manim's own frames: **0.37% of pixels differing** across all 4,981 frames.

  The scene also found a real gap. `.animate.scale(...).shift(...)` on a `Circle` is ordinary
  Manim, and the `xform` verb assumed every target was a baked asset — a primitive carries its
  geometry directly rather than as instances under an object transform, so the matrix has to be
  applied to its points. Both interpreters crashed on it. That is what a corpus is for.
- **No real IR exists**, so the exporter should be diffed against
  `tools/probe_scene_geometry.py` (which reports the naive upper bound by design) to prove
  affine detection and the glyph atlas are actually firing. Use the corpus as a regression
  suite, not a one-off.
- **Occluded solids** — depth-tested layer, deferred (§3.6). MolecularStructure now exercises
  this case and can be used to judge how visible the painter-order artefact actually is.
- ~~**Glyph atlas at varying sizes.**~~ **Measured, and it does.** Manim bakes size into glyph
  outlines: the same `A` at six font sizes gives six point arrays that are only *nearly* scaled
  copies, with affine residuals of 4.7e-4 to 1.7e-3. At the 1e-4 tolerance every size became its
  own atlas entry.

  Those residuals are sub-pixel. A scene unit is 90 px at 720p, so 2e-3 is **0.18 px** — below
  what any rasteriser resolves. Measured on the corpus library:

  | Tolerance | Glyphs | Worst error |
  |---|---|---|
  | 1e-4 (before) | 182 | 0.009 px |
  | 1e-3 | 92 | 0.090 px |
  | **2e-3 (now)** | **89** | **0.180 px** |
  | 5e-3 | 87 | 0.450 px |

  `GLYPH_TOLERANCE = 2e-3` is now separate from `AFFINE_TOLERANCE`, which stays at 1e-4 because
  it decides whether a *moving* shape is being transformed or genuinely redrawn — a false match
  there is a wrong animation, not a sub-pixel outline. The shared atlas went **91,802 B → 42,830
  B**, and re-measured against Manim's own frames the text scenes are unchanged or better:
  TextReuse 0.05%, TextHybrid 0.04%, LatexDerivation 0.36%, CodeWalkthrough 0.51% → 0.39%.

  This affects hit rate rather than design, as predicted — but the hit rate was half of what it
  should have been, and the atlas is the one thing every scene in the library shares.
- ~~**Bundle packaging, versioning and library sync**~~ **Done.** `tools/build_library.py`
  packages the corpus into a manifest plus content-addressed files; `player/core`'s `Library`
  reads it, reports what is missing, and opens any scene without knowing where files live. The
  sync algorithm reduces to *fetch the paths I do not have*, because content-addressed files
  never change and so there is no invalidation to get wrong. Measured, for the whole corpus:

  | | Bytes |
  |---|---|
  | 9 programs | **1,869** |
  | 22 shared assets | 1,794,666 |
  | Glyph atlas | 42,830 |
  | **Library total** | **1,839,365** |
  | (tier-3 fallbacks, not shipped where tier 1 exists) | 20,094,987 |

  Two scenes are *pure program* — SurfaceOrbit is 196 B and VerbTest 127 B with no assets at
  all. Everything else is dominated by baked geometry, which is content, not overhead.

  **The manifest exposed a live hazard.** A scene's tier was being inferred from whether a
  `.panim` existed, and `PlotGeometry`'s was stale from before `ValueTracker` was recognised as
  a blocker. Measured against Manim it renders **4.61% of pixels wrong, peaking at 15.65%, and
  is 75 frames (2.5 s) short** — it would have shipped as tier 1. The exporter now writes a
  `<Scene>.tier.json` verdict alongside and deletes a program it cannot certify; the packager
  refuses to ship a program without one. *Presence is not correctness*, and nothing but the
  exporter knows the difference.
- **Export pipeline in CI** — `.github/workflows/verify.yml` runs the cheap half on every push:
  three decoders agree, two interpreters agree, seeking is exact on every file, and the library
  opens every scene through its manifest. About a minute, and no Manim or LaTeX needed. The
  tier-1 artefacts are versioned rather than ignored so CI has something to check — ~1.9 MB,
  which is the point of the project. Fidelity against Manim's own frames still needs a full
  Manim and LaTeX install and tens of minutes per scene; that belongs in a nightly job and is
  run by hand until one exists.
- **Bundle integrity and player UX beyond scrubbing.**
- **Two secondary figures** in the substrate research want re-verifying; several primary sources
  were unreachable behind an egress proxy when it was written.
