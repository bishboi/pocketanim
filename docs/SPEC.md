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
there is no upstream runtime to be correct on our behalf. It should compare device output
against reference Manim renders with a tolerance threshold, and be used to find the lowest
keyframe density that still reads as identical, per scene class.

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

## 10. Exporter v2 — the fixes measurement identified

Ordered by expected value. None reopens a design decision; all are refinements to how instances
serialise.

1. **Factor group transforms.** Cartopy's zoom scales a single `VGroup`, so all 1,429 polylines
   share one matrix change — currently written out 1,429 times per keyframe. Manim's hierarchy
   already expresses this and the exporter flattens it away. Structurally the right fix and
   almost certainly the largest: it targets the worst scene directly.
2. **A morph instance type.** `Transform(before, after)` between two known shapes currently
   generates a new atlas entry per intermediate frame — the whole of CodeWalkthrough's 2,595
   shapes. Storing `(atlas_a, atlas_b, t, transform, style)` instead costs a few bytes over a
   normal instance and eliminates the intermediates entirely. This is a narrowly-scoped
   parametric element, and worth the exception: it is the only fix that helps atlas-dominated
   scenes.
3. **Per-mobject keyframe density.** Currently one global stride. §3.3 already calls for choosing
   density from each mobject's measured morph rate; a slow-moving background object does not
   need the rate a fast one does.
4. **Further transform quantisation.** Now float16 linear part plus float32 translation (30 bytes,
   from 48). Full 16-bit fixed point over scene bounds would reach 24.

## 11. Open items

- **Corpus scenes are 6–14.5 s.** Any 3-minute figure here is extrapolation, and the IR/video
  crossover is duration-sensitive — CartopyMap's sits around 8 s. Add a long scene before any
  production sizing decision.
- **No real IR exists**, so the exporter should be diffed against
  `tools/probe_scene_geometry.py` (which reports the naive upper bound by design) to prove
  affine detection and the glyph atlas are actually firing. Use the corpus as a regression
  suite, not a one-off.
- **Occluded solids** — depth-tested layer, deferred (§3.6). MolecularStructure now exercises
  this case and can be used to judge how visible the painter-order artefact actually is.
- **Glyph atlas at varying sizes.** Deduplication was verified at identical scale; Manim may
  bake size into outlines, in which case the atlas must normalise by scale before deduplicating.
  Affects hit rate, not design.
- **Bundle packaging, versioning and library sync** — caching all IR means the device must learn
  what exists: a manifest and incremental sync.
- **Export pipeline in CI**, bundle integrity, and player UX beyond scrubbing.
- **Two secondary figures** in the substrate research want re-verifying; several primary sources
  were unreachable behind an egress proxy when it was written.
