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

**Not executed here:** everything in `android/`. `dl.google.com` is blocked in
this environment, so `player/build.sh` compiles the Android layer against a
real framework jar from Maven Central (`org.robolectric:android-all`, which
carries AOSP's `android.jar` contents) rather than against an SDK. That proves
it builds against the real `android.*` API and nothing more. The Gradle build
alongside it is what to use where an SDK is available, and CI builds the
benchmark APK with it.

It *has* run on a phone — the render loop, the surface lifecycle and the Skia
sink — twice, through that APK. §11 carries both runs, including the one whose
numbers turned out to be measuring a software canvas.

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

**One deliberate loss.** The exporter decimates imported artwork to the detail
a screen can resolve, which is a fidelity decision and so it is measured rather
than assumed. On CartopyMap's tier-1 program against Manim's own frames:

| CartopyMap, tier 1 | Mean MAE | Pixels differing |
|---|---|---|
| Full coastline, 58,987 curves | 0.25 | 0.30% |
| Decimated at export, 30,756 curves | 0.42 | 0.60% |
| …and half a pixel of playback detail | **0.48** | **0.75%** |

Two deliberate losses, each measured before it was taken, and together they are what makes the
scene playable on a phone (§11): 104 ms a frame became 23. **0.75% against a 1% gate is the
tightest margin in the corpus.**

A third row lived here for two runs and has been taken back out. Bevelling stroke joins bought
119 of CartopyMap's 181 late frames when the scene carried 22,719 verbs, and cost 0.17 points
of this margin. Once playback detail took the count to 17,625 it bought **one** late frame, so
the join that matches Manim is the one that ships and the margin is 0.75% rather than 0.92%.
The bevel is still in the sweep for a device that needs it.

Neither loss costs anything where it is not needed: playback detail is invisible on text, where
CodeWalkthrough measures **0.19% against Manim either way**, because a glyph outline has no
sub-pixel straight runs to drop.

The budget is one pixel at 2400 px wide **at the tightest zoom the program
reaches** — a third of a pixel anywhere else in that animation — and the cost
of it is those two rows. It stays inside the 1% gate below with room, and it is
the only place in this table where the exporter is choosing to be wrong.

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

  **A desktop reference now exists, measured by the identical procedure.** `player/benchmark`
  is an installable app that runs every corpus scene three times — warm-up, unpaced, then paced
  at the scene's own rate — and the same `Benchmark` code runs here against Java2D, so a phone
  number lands next to a comparable one. 1280×720:

  | Scene | Verdict | p50 ms | Geometry ms | Draws | Max path verbs |
  |---|---|---|---|---|---|
  | CartopyMap | **FAIL** (98% late) | 67.35 | 2.19 | 1,426 | **10,298** |
  | MolecularStructure | **FAIL** (51% late) | 30.72 | 2.32 | **5,120** | 10 |
  | ThreeDCamera | PASS (0.3% late) | 20.71 | 0.32 | 996 | 6 |
  | SurfaceOrbit | PASS | 11.44 | 0.33 | 1,152 | 6 |
  | LongLesson | PASS | 1.00 | 0.04 | 47 | 44 |
  | the other six | PASS | ≤1.5 | ≤0.08 | ≤90 | ≤47 |

  Three things fall out of this, and the first is the important one.

  **Geometry is 0.3–3% of a frame. Rasterisation is the rest.** Everything measured so far —
  interpreter laziness, atlas deduplication, affine detection, camera projection — lives in a
  column that never exceeds 2.32 ms. §11's earlier note that "the bottleneck is the rasteriser"
  was an inference from verb counts; this measures it.

  **The two failures fail differently.** CartopyMap has *few* draws and an enormous path;
  MolecularStructure has *many* draws and trivial ones. 1,426 draws costing 67 ms against 5,120
  costing 31 ms is not a draw-count story — it is path complexity in one case and per-draw
  overhead in the other, and they want different fixes. §11's draw-call analysis covers the
  second; the first is what the `maxpath` guard in `build_library.py` was added for.

  **This is a shape, not a prediction.** Java2D software-rasterises antialiased paths and is
  generally slower at it than Skia, which on Android is GPU-backed through HWUI. A phone may
  well beat these numbers on the rasterisation-dominated scenes. What transfers is which scenes
  are expensive and where their cost sits — and ThreeDCamera at 62% of a 33.3 ms budget on a
  desktop is a warning worth taking to the device.

  `player/BENCHMARK.md` has the build-and-run instructions; results land in logcat and in a
  JSON file.

  **First device run, and a bug it exposed in the benchmark itself.** On a low-end phone,
  **8 of 11 scenes passed** and rendered correctly. Three did not: CartopyMap 178/181 frames
  late, MolecularStructure 235/271, ThreeDCamera 45/301.

  Those numbers came through `SurfaceHolder.lockCanvas()`, which returns a **software**
  canvas — Skia rasterising into a CPU buffer, with the GPU only compositing the result.
  `lockHardwareCanvas()` is the HWUI-backed one. **§5's substrate decision is "Skia via the
  Canvas API, GPU-backed", and the benchmark bypassed exactly that**, so the first run
  measured CPU rasterisation on a phone: the one thing the architecture exists to avoid.

  It matters most for the scenes that failed. ThreeDCamera is **fill-bound, not draw-bound**
  — 996 draws against SurfaceOrbit's 1,152, but 63% screen coverage against 23% — and filling
  pixels is nearly free on a GPU and expensive on a CPU. CartopyMap scored identically on
  desktop Java2D and on the phone (178/181 both), which is what two software rasterisers far
  over budget look like.

  `SurfaceCanvas` now takes a hardware canvas where the device offers one and falls back
  rather than dropping a frame; `PanimView` uses it too, so the player is not
  software-rendering either. The benchmark **reports which path it got**, in the log line and
  the JSON, and acquires a frame before reporting so the answer is observed rather than
  assumed. A silent fallback is how the first numbers came to be misread.

  **Second device run, on a hardware canvas.** RMX3242, mt6833, Android 33. **8 of 10
  scenes pass**, and ThreeDCamera went from 45/301 frames late to **0/301** — the fill-rate
  reading was right, and nothing else was wrong with it. CartopyMap and MolecularStructure
  still fail, for different reasons:

  | Scene | p50 | geometry | draws/frame | verbs/frame | late |
  |---|---|---|---|---|---|
  | CartopyMap | 104.3 ms | 7.9 ms | 1,426 | 62,054 | 180/181 |
  | MolecularStructure | 41.5 ms | 7.4 ms | 5,120 | 15,586 | 222/271 |
  | *VerbTest (1 draw, 9 verbs)* | *16.47 ms* | *0.04 ms* | *1* | *9* | *0/151* |

  VerbTest is the important row: a scene that draws one path takes 16.47 ms, because
  `unlockCanvasAndPost` blocks on the next buffer. **Every passing scene's p50 sits on that
  vsync floor**, so p50 is an upper bound on their cost and not a measurement of it. Only
  the two failures are above it and therefore actually measured.

  Two failures and two passes give four equations for two unknowns, and they fit:
  **rasterisation costs about 1.5 µs per verb and 2.1 µs per draw** on this device. That is
  the model the work below is aimed at, and each change attacks one term.

  | | draws/frame | verbs/frame | max path |
  |---|---|---|---|
  | CartopyMap, first run | 1,426 | 62,054 | 10,298 |
  | CartopyMap, now | **355** | **22,719** | **8,192** |
  | MolecularStructure, first run | 5,120 | 15,586 | 10 |
  | MolecularStructure, now | **2,649** | 15,569 | 10 |

  Where that came from: lines instead of cubics where Manim's polylines are straight (98% of
  CartopyMap's curves); frame culling of 2D instances, which an affine transform makes exact;
  merging adjacent opaque strokes that share a paint, which is exact for the same reason;
  one `drawPath` where a face's fill and stroke are the same opaque colour, which is 2,880 of
  MolecularStructure's 2,910; and export-time decimation of over-detailed artwork. Agreement
  with the Cairo oracle is unchanged to three digits, which is the property all of it had to
  preserve — the decimation is the one deliberate loss, and §7.3 carries its cost.

  **Third device run, at 1920x1080 — 2.35x the pixels of the run above.** Same phone. The two
  scenes are still the only failures, and the answer to the open question is emphatic:

  | | p50 | p95 | geometry | rasterisation | late |
  |---|---|---|---|---|---|
  | CartopyMap, before | 104.3 ms | 135.6 ms | 7.9 ms | 96.3 ms | 180/181 |
  | CartopyMap, after | **44.1 ms** | 201.3 ms | 22.1 ms | **22.0 ms** | 134/181 |
  | MolecularStructure, before | 41.5 ms | 51.9 ms | 7.4 ms | 34.1 ms | 222/271 |
  | MolecularStructure, after | **30.9 ms** | **39.9 ms** | 5.9 ms | **25.0 ms** | 190/271 |

  **Rasterising a coastline got 4.4x cheaper while the frame got 2.35x bigger.** Lines are
  much cheaper than cubics on Skia — that was the term the cost model could not supply, and it
  is the difference between a vector coastline being hopeless on this phone and being close.
  Every passing scene is unchanged and still sitting on the vsync floor.

  Two things the run exposed, both now addressed or instrumented:

  **Geometry became CartopyMap's bottleneck**, 7.9 ms to 22.1 ms — half the remaining budget.
  That was culling scanning each instance's points for a bounding box *before* transforming
  them, so every visible shape was walked twice to produce four floats. The bounds now fall out
  of the transform. The same regression is invisible on a desktop JVM, which is its own lesson.

  **CartopyMap's p95 got worse as its p50 halved**, 135.6 ms to 201.3 ms. That is the signature
  of a trade winning on average and losing badly somewhere, and the most likely suspect is
  stroke merging: it replaces 1,429 small paths with a handful spanning the whole screen, and
  which of those Skia prefers is not something this repository can reason its way to. So it no
  longer tries. Each trade is a field on `RenderOptions`, and the benchmark now **sweeps any
  scene that missed its budget** with one of them turned off at a time — lines, culling,
  merging, and back-face culling — and reports a row for each. The phone decides.

  **Fourth device run, the first sweep.** Same phone, same 1920x1080. The geometry fix landed:
  CartopyMap's geometry went 22.1 ms → **4.3 ms** and its p95 201.3 → **57.1 ms**, so the tail
  was that regression and *not* stroke merging. What each trade is worth, measured rather than
  argued:

  | turned off | CartopyMap p50 | CartopyMap p95 | MolecularStructure p50 |
  |---|---|---|---|
  | nothing | 34.4 ms | 57.1 ms | 32.6 ms |
  | lines | +19.6 | +33.1 | +2.8 |
  | stroke merging | +16.8 | +24.6 | ±0 (2D only) |
  | frame culling | ±0 | +13.5 | ±0 (2D only) |
  | *back-face culling, then ON* | *±0 (2D only)* | — | **−9.6** |

  The noise floor is ±1.6 ms at p50, read off the row where a 2D scene was swept with a 3D-only
  option and should have been identical. Two conclusions. **Lines and merging are both worth
  about half a budget each** and neither is optional. And **back-face culling took
  MolecularStructure to 22.9 ms and 0 late frames of 271** — a pass — so it now ships, driven by
  a `CLOSED_SOLID` flag the exporter sets for Manim's nine closed types and never for `Surface`.
  Against Manim it costs nothing measurable: 2.36% of pixels differing becomes 2.35%.

  That flag needed a second one, and finding out why corrected a mistake. **The normals in the
  IR do not point outwards.** Manim 0.21's `VMobject` has no `get_unit_normal` at all, so every
  normal comes from the exporter's SVD plane fit, whose sign is arbitrary and which then forces
  all of them into one hemisphere — right for shading a sheet evenly, inward for half of any
  sphere. The device's 1.46x was measured through that, culling the wrong faces and looking
  plausible because a sphere is symmetric. `NORMAL_INWARD` records which way is out, settled
  against the solid's own centre; shading still uses the normal exactly as Manim derived it.
  Corrected, it is **2.0x**: 15,569 verbs → 7,785, 2,649 draws → 1,325.

  CartopyMap's remaining problem is now visible. Its first 44 frames are a `FadeIn`, and they
  were drawing 1,429 separate paths each because merging demanded an opaque colour — which is
  exactly why they were the scene's worst frames. Merging a translucent run is exact except
  where two strokes overlap, and that measures at 0.117% of a frame's pixels, a fifth of what
  decimation already costs. Draws per frame: **355 → 25**.

  **Fifth device run: 9 of 10 pass, and the last one is marginal.** MolecularStructure came in
  at **18.1 ms p50 and 0 of 271 late**, so closed-solid back-face culling did what the sweep
  said it would. The sweep then overturned two more of my expectations at once.

  | CartopyMap, turned off | p50 | p95 | late of 181 |
  |---|---|---|---|
  | nothing | 36.0 ms | 53.5 ms | 126 |
  | lines | 53.4 | 62.0 | 177 |
  | stroke merging | 46.5 | 72.4 | 178 |
  | frame culling | 33.4 | 39.5 | 155 |
  | *back-face culling (3D only: a control)* | *32.3* | *39.1* | *120* |
  | translucent merging | 32.7 | 58.8 | 132 |
  | **round joins** | **25.5** | **30.6** | **7** |

  The control row matters as much as the rest: a 3D-only option swept on a 2D scene does
  identical work to the first row, and it came back 3.7 ms and 14.4 ms and 6 frames away from
  it. **That is the noise floor**, and it is far wider than a desktop's — three of these rows
  never cleared it.

  **Round joins cost 119 of 181 late frames**, more than lines and more than merging. Manim
  joins strokes with an arc and a rasteriser has to build one at every vertex; a coastline has
  22,719 of them. A bevel is one flat cut, and against Manim's own frames the whole scene goes
  from 0.60% of pixels differing to **0.75%** — inside the 1% gate. On a scene whose strokes are
  sub-pixel it is not a difference at all: SurfaceOrbit measures 2.98% either way. So the
  renderer bevels, and the Cairo oracle bevels with it.

  **Merging a translucent run buys nothing.** It takes the fade from 355 draws a frame to 25 and
  moves the frame time by less than the noise floor, while costing 0.117% of a frame's pixels.
  A cost for no measured gain is not a trade, so it is off — and still swept, because once round
  joins are gone the arithmetic may change.

  **Sixth device run: it did change, and the sweep caught it.** With bevel joins shipping,
  CartopyMap measures 25.7 ms p50 and 30 late frames — and the `merge-fade` row, the thing
  turned off one run earlier for buying nothing, measures **9 late frames and 5.7 ms less at
  p99**. A trade is worth only what is left once the larger costs are paid; with round joins
  still in, merging was hidden behind them. It is back on.

  | CartopyMap | p50 | p95 | p99 | late of 181 |
  |---|---|---|---|---|
  | shipping | 25.7 | 37.5 | 44.0 | 30 |
  | without lines | 47.2 | 91.7 | 94.4 | 177 |
  | without merging | 32.7 | 41.9 | 46.9 | 177 |
  | without frame culling | 26.8 | 55.1 | 57.6 | 121 |
  | with round joins | 32.8 | 71.9 | 78.6 | 144 |
  | *3D-only option: a control* | *25.2* | *34.9* | *46.1* | *78* |
  | **with translucent merging** | **25.5** | **34.9** | **38.3** | **9** |

  **And the control row says something about the harness.** It does work identical to the first
  row and lands within 0.5, 2.6 and 2.1 ms of it — but 48 late frames away. Once p50 sits near
  the budget, small jitter flips many frames at once, so **`late_frames` is the unstable number
  there and the percentiles are not.** The verdict still keys off late share, which is the right
  question to ask; it just has to be read next to a control.

  That leaves CartopyMap marginal at about 5% of frames late, and every lever that got it there
  is exhausted or exercised. The last one is level of detail *at playback*: the exporter has to
  decimate for the tightest zoom a program reaches, so a coastline carries three times the
  detail it needs in exactly the frames where all of it is on screen.

  **Seventh device run — it works, and it is the last of them.** Dropping points that lie within
  a tolerance of the segment replacing them:

  | CartopyMap | p50 | p95 | late of 181 | verbs |
  |---|---|---|---|---|
  | shipping, no level of detail | 26.0 ms | 38.2 ms | 12 | 22,719 |
  | *3D-only option: a control* | *25.9* | *31.0* | *7* | *22,719* |
  | **half a pixel** | **22.0** | **28.0** | **3** | **17,625** |
  | one pixel | 19.2 | 34.3 | 0 | 14,033 |

  Half a pixel ships. One pixel reaches zero late frames, but the two are a control row apart on
  the only axis that matters and one pixel costs four times as much: against Manim's own frames
  the scene measures 0.77% of pixels differing at half a pixel of tolerance and 0.85% at one,
  with one pixel's worst frame at 1.32%. More detail for no measured gain is the same bad trade
  as its opposite.

  It is free everywhere else. CodeWalkthrough measures **0.19% against Manim either way**, to
  two digits, because a glyph outline has no sub-pixel straight runs to drop. The cost lands
  only where the detail is.

  **Eighth run, and the last: 9 of 10 pass, CartopyMap is marginal at 23.5 ms and 5 late frames
  of 181.** Every number above reproduced.

  It also showed that these trades interact, in the direction that gives something back. **Round
  joins, which cost 119 late frames at 22,719 verbs, cost a handful at 17,625** — playback detail
  took the vertex count down and took the cost of an arc at every vertex with it. Two samples put
  that handful at 1 and 4 late frames, and about 3.5 ms at p50, with the scene marginal either
  way. So Manim's own join is back: the fidelity margin returns from 0.92% to **0.75%** and the
  bevel stays in the sweep for a device that needs it. That last step is a judgement rather than
  a measurement — 0.17 points of fidelity against 3.5 ms — and `RenderOptions` exists so it is
  one field to reverse. The same shape as the translucent-merge reversal two runs earlier, read
  the right way round this time: a trade is worth only what is left once the others are paid,
  which cuts both ways.

  **A ninth run, of the same build, is what the harness needed.** The benchmark sweeps any scene
  that misses its budget, so a marginal MolecularStructure brought seven near-identical rows with
  it — and the primary row reported **10 late frames of 271 where all six comparable rows
  reported 0**, on the same code, in the same run, minutes apart. Its p50 never moved: 16.56 ms
  then 16.63 ms across the two runs.

  That is the clearest statement yet of something §11 already suspected: **once a scene's p50
  sits near the vsync floor or near its budget, `late_frames` measures the machine's mood as much
  as the renderer.** It is still the right question — a viewer sees late frames, not percentiles
  — but a single run of it decides nothing. The sweep's controls are what make it readable, and
  they are only there because a scene missed its budget. A scene that passes has none.

  The same run did confirm the one thing that was load-bearing: **MolecularStructure without
  back-face culling is 30.0 ms and 33 late frames — a clear fail** — against 16.6 ms with it.

  **Tenth run, verifying the revert, and the end of the sequence.** CartopyMap marginal at 28.2
  ms and 9 late frames of 181; everything else passes, MolecularStructure among them at 0 late,
  which settles the previous run's 10 as the noise its own controls said it was.

  Three samples of each join style now exist, so the cost of matching Manim is no longer a guess:

  | CartopyMap, with playback detail | p50 samples | mean | late samples | mean |
  |---|---|---|---|---|
  | round joins (ships) | 26.9, 26.3, 28.2 | 27.1 ms | 6, 8, 9 | 7.7 |
  | bevel | 23.5, 22.6, 22.3 | 22.8 ms | 5, 4, 8 | 5.7 |

  The p50 ranges do not overlap, so **4.3 ms is real**; two late frames is not much more than the
  noise. Marginal either way, in all six samples. **That makes the shipping choice a judgement
  rather than a measurement**: 0.17 points of fidelity margin, which is measured, against 4.3 ms
  of headroom for a slower phone than the one that exists, which is not. It ships matching Manim,
  and `RenderOptions.roundJoins` is one field for whoever meets that phone.

  One last note on the metric, from inside this run: `lod-1px` draws **fewer** verbs than the
  shipping configuration (14,033 against 17,625) at a better p50 (21.0 against 28.2), and reports
  **more** late frames (15 against 9). Percentiles and late counts disagree even within a single
  run at this end of the scale. The verdict column is still the right question, and it still
  needs more than one run to answer.

  **What the whole sequence cost and bought:**

  | | first run | now |
  |---|---|---|
  | CartopyMap | 104.3 ms, 180/181 late | **23.5 ms, 5/181 late** |
  | MolecularStructure | 41.5 ms, 222/271 late | **16.6 ms, 0/271 late** |
  | verdicts | 8 pass, 2 fail | **9 pass, 1 marginal** |
  | surface | 2148x411 (stretched) | 1920x1080, 2.35x the pixels |

  The stopping point is fidelity rather than ideas. CartopyMap sits at 0.75% of pixels differing
  against a 1% gate, and it is the scene the corpus chose as the worst case for a vector format.
  Anything further has to be spent out of that margin.

  There is still no MP4 fallback, so a bad device result has nowhere to fall back
  to — but render-to-cache on first open, which #6 names, needs no format change.
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
- ~~**The Android layer has never run.**~~ **Partly run.** Two device runs have exercised the
  render thread, the surface lifecycle and the Skia sink through the benchmark APK; the results
  and what the first of them got wrong are above. The `AudioTrack` clock, `MediaCodec` audio
  decode and seek-during-drag behaviour are still unexercised, because the benchmark drives
  frames itself and plays no audio.
- **A scene can export at tier 1 and be wrong.** Three verified defects, found by
  probing the exporter with 34 single-construct scenes while charting a separate
  effort. Each exports cleanly, reports tier 1, and lists no blockers.

  | What the scene says | What the program does |
  |---|---|
  | `Circle().shift(RIGHT*4 + UP*2)` | drawn at the origin |
  | `self.play(Create(a), Create(b), run_time=2)` | plays for 4.03 s, not 2 s |
  | `Write(Circle())` | crashes the player: `KeyError "write target 'A' was never declared"` |

  The first is the plainest: the `circle` and `square` emitters carry radius,
  colour and stroke width and **no position**. Only `rect` emits `at=`, and the
  interpreter's parser reads `at=` for all three — so the reader was built for a
  field the writer never sends. The second is that concurrent animations inside
  one `play()` become sequential verbs. The third is that `write` assumes a text
  asset and nothing checks.

  What makes these worse than a blocker is that **nothing reports them**. §9.5's
  tier machinery exists to catch scenes the exporter cannot express, and these
  are scenes it believes it *can*. The corpus does not catch them either,
  because every corpus scene was written by hand against what the exporter
  supports; the fidelity harness compares programs to Manim for scenes that were
  authored to work.

  **`LongLesson` was shipping wrong.** Its circles and squares sit at
  `(0, -1.4)` and were drawn at the origin, through every device run in this
  section and every nightly fidelity run — including while someone watched it
  play.

  **Two of the three verification layers cannot see this class of defect at
  all**, and that is structural rather than an oversight:

  | Check | What it compares | Can it see a lost position? |
  |---|---|---|
  | `crosscheck_interpreter` | Python interpreter vs Kotlin | **No** — both read the same program and agree, wrongly |
  | `verify_player` | Kotlin renderer vs Cairo oracle | **No** — same program, same omission, perfect agreement |
  | `verify_dsl` | program vs **Manim's own frames** | Yes, and only this one |

  Everything except the last is an agreement test between implementations of the
  format. They are worth having and they caught real drift, but no number of
  them can notice that the format was handed the wrong thing in the first place.
  Only the comparison against Manim can, which makes it load-bearing rather than
  one of three, and makes its threshold the thing to get right.

  Also established while probing: the `unsupported mobject:` blocker at
  `export_dsl.py:217` is **unreachable**. Line 120 returns early on exactly the
  negation of line 206's condition, so no mobject ever reaches it. Geometry
  never blocks; the tier-3 cliff is narrower than §9.5 implies and is about
  animations alone.

  **Two of the three are fixed, and the third is not.**

  *Position.* `circle` and `square` now emit `at=`, as `rect` always did. Two
  lines, because both readers had parsed the field all along.
  `corpus/scenes/12_positioned_primitives.py` is the scene that would have
  caught it: three primitives, three positions, drawn one at a time so that a
  failure means the position was lost and nothing else. Against Manim it went
  from 0.57% of pixels differing to **0.04%**.

  *`Write` on a primitive* is now a blocker, so the scene falls to tier 3 and
  draws correctly rather than reaching tier 1 and crashing. Write reveals an
  asset one submobject at a time; a primitive has none to lag. Tier 3 producing
  a correct large scene is what the tiers are for.

  *Concurrent animations* are fixed, and it took a format change. The timeline
  had no way to say "these run together", so `par n=N t=T` was added: a marker
  that claims the next N verbs and gives them one clock.
  `corpus/scenes/13_concurrent_play.py` is the scene that would have caught it,
  and it now plays 151 frames where Manim plays 151.

  The two runtimes absorbed it differently, which is worth recording because it
  says something about both designs. Kotlin's `Runner` — `frames`, `enter`,
  `render(k)`, `exit` — **composes without being asked to**: a parallel runner
  enters them all, renders frame k of each, and exits them all, in four lines. A
  member shorter than the group holds its last frame, as Manim does. Python's
  interpreter had each verb's per-frame loop calling `emit()` directly, which
  cannot interleave; each verb is now a **generator that yields once per frame**
  and the driver either drains one or advances a group in lockstep. That was a
  mechanical change — `emit()` became `yield` — but only because the branches
  already had a clean per-frame body to extract.

- **A 1% pixel gate cannot see a positioning bug.** The scene above, with every
  primitive drawn in the wrong place, measured **0.57% of pixels differing** and
  would have passed §7.3's suggested gate with room to spare. Thin outlines on
  black are under 1% ink, so moving all of them moves well under 1% of the
  frame.

  `verify_dsl` now also reports **differing pixels as a share of inked pixels**.
  The same broken frame reads **114%** by that measure — more than the entire
  drawing moved — against 0.4% once fixed. A denominator of "the whole frame"
  flatters sparse line art, and most of this corpus is sparse line art.

  Not yet done: §7.3's gate is still phrased against the frame. Whether the
  ink-relative number becomes the gate, or a second one beside it, wants the
  nightly numbers for the whole corpus first — a dense scene and a sparse one
  should probably not be held to the same threshold on either measure.

- **Mid-animation frames disagree with Manim far more than the headline says.**
  The first thing the ink-relative number found, and it was already there.
  `HelloPocketanim` ships at 0.05% of pixels differing; measured against its own
  ink it reads **139% at frame 8**, 83% at 16, 60% at 24. By frame 64 — once the
  animation has settled — it is 0.4%. The corpus's fidelity numbers are averages
  dominated by held frames, and the held frames are the ones that agree.

  **It is not a timing offset.** Scoring our frame *N* against Manim's *N±1* and
  *N±2* produces no minimum — 163%, 151%, 139%, 125%, 124% across the window, a
  monotone slide with no dip at any shift. So this is not the off-by-one family
  §11 already closed; the *partial geometry* differs. `Create` on a circle draws
  a visibly longer arc than Manim's at the same instant, which points at
  `pointwise_become_partial` or the rate applied to it rather than at the clock.

  Whether it matters is a judgement nobody has made yet: a growing stroke that is
  slightly further along is a different animation, not a wrong picture, and every
  device run and every visual check passed it. Recorded rather than chased,
  because it is a self-contained investigation and this section already has two.

- **Exporting the same scene twice gives different asset files.** Confirmed, and it is Python's
  string-hash randomisation: `TransformMatchingTex` matches by tex-string keys through sets, so
  the order of the groups it builds varies per process, and a group's order is part of its
  content digest. Two runs under `PYTHONHASHSEED=0` produce identical digests; two runs without
  it do not. LatexDerivation's five matched groups churn their asset files on every export and
  orphan the previous ones.

  Nothing ships wrong — the program and the assets it points at are written together, and the
  fidelity harness checks the pair. But a content-addressed store whose addresses move is not
  content-addressed, so the export path should either pin the seed or make the digest
  independent of a group's internal order. Left open because the fix belongs with whatever
  cleans up orphaned assets, which nothing does yet.
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
- ~~**No real IR exists**, so the exporter should be diffed against the naive upper bound.~~
  **Superseded.** The IR exists and the corpus *is* the regression suite. Both mechanisms are
  now asserted nightly rather than inspected: `fidelity.yml` fails if atlas hit rate drops
  below 0.95 or affine reuses fall under a thousand on the 3D scenes. That guard exists
  because breaking either is **invisible** — every frame still renders correctly and the file
  just quietly balloons, which no pixel comparison can see.
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
- ~~**Export pipeline in CI**~~ **Done, in two halves.**

  `verify.yml` runs on every push in about 80 seconds, with no Manim or LaTeX: the player
  self-test, three decoders agreeing, two interpreters agreeing, seeking exact on every file,
  and the library opening every scene through its manifest. The tier-1 artefacts are versioned
  rather than ignored so it has something to check — ~1.9 MB, which is the point of the
  project.

  `fidelity.yml` runs nightly and on demand, and is the expensive half: a full Manim and LaTeX
  install, comparing the program against Manim's own frames and failing above §7.3's 1% gate.
  **Validated by running it** — TextReuse and VerbTest both came back 0.00% differing. It also
  guards the two mechanisms that make the IR small, because breaking either is *invisible*:
  every frame still renders correctly and the file quietly balloons. Thresholds are atlas hit
  rate ≥ 0.95 and affine reuses ≥ 1,000; measured now at 0.9962 / 158,865 for ThreeDCamera and
  1.0000 / 629,752 for MolecularStructure.
- ~~**Bundle integrity.**~~ **Done.** `Library.checkIntegrity` compares local storage against
  the manifest: size always, because it is free and catches a truncated download; digests on
  request, because hashing two megabytes per launch is not free and only same-length
  corruption needs them. Both paths are tested against deliberately damaged storage, including
  the case a size check cannot see.
- **Player UX beyond scrubbing.**
- ~~**Two secondary figures** in the substrate research want re-verifying.~~ **Done, and one was
  wrong.** The Graphite MotionMark number is confirmed as written (~15% on MotionMark 1.3,
  Apple Silicon, not Android). The Snapdragon 680 Impeller-vs-Skia entry had **merged two
  different benchmarks**: the ~22% frame-time and ~60% variance figures belong to that device,
  the "4.05 ms vs 2.81 ms GPU raster" numbers belong to another with no Snapdragon attribution.
  Corrected in `docs/research/android-rendering-substrate.md`.

  Re-verification also turned up a primary source the draft did not have, and it is a better
  one: [flutter/flutter#192147](https://github.com/flutter/flutter/issues/192147) measures
  Impeller's GLES backend at **2–3× slower than Skia GL on an Adreno 610** — 12.0 ms/frame
  against 6.7 ms — with the cause being per-draw CPU overhead, 25–35 redundant GL calls per
  draw, not anything on the GPU. That sharpens §5's substrate choice and says plainly what
  §11's draw-call measurement implies: **on a floor-segment device the number of draws costs
  you, not their complexity.**
