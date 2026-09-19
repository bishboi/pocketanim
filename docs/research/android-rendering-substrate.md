# Android rendering substrate for on-device replay of Manim scenes

**Ticket question:** given a floor of low-end Android at 720p30, what should the native
renderer actually draw with?

**Candidates evaluated:** Skia via the Android `Canvas` API (HWUI), Jetpack Compose's
graphics layer, OpenGL ES directly, Vulkan directly, plus four alternatives not in the
original list: an **embedded vector GPU renderer** (Rive Renderer), **Skia bundled in-app
via the NDK**, **Vello / vello_hybrid**, and **ThorVG**. Filament is discussed as a 3D
companion rather than a 2D substrate.

Date of research: 2026-09-19. Distribution figures are Google's, collected Nov 2025.

---

## 0. Framing: what "low-end at 720p30" actually buys us

- 30 fps is a **33.3 ms** frame budget, not 16.7 ms. Android's own Slow Rendering guidance
  is written against 16 ms for 60 fps and notes that overrunning the window by even 1 ms
  causes `Choreographer` to **drop the frame entirely** rather than show it late
  ([Slow rendering](https://developer.android.com/topic/performance/vitals/render)).
  Targeting 30 fps doubles the headroom, which is the single biggest thing working in our
  favour. It is also the reason a Canvas-based design is plausible at all.
- 720p = 921,600 px. Fill rate is not the constraint on any Vulkan-capable phone; **path
  setup / tessellation / mask generation on the CPU is**. Every source below points the
  same way.
- The realistic floor device is something like a Mali-G52/G57 or Adreno 5xx–6xx class GPU,
  4 GB RAM, Android 10–13. That class reports Vulkan 1.1 and OpenGL ES 3.2, and is where
  Flutter's Impeller regressions and MapLibre's Vulkan reports cluster.

---

## 1. Path-heavy 2D throughput

### 1.1 The load-bearing finding: Skia caches paths, Manim invalidates the cache

Android's own documentation is unusually blunt about this, twice, in two different places.

From [Hardware acceleration (Views)](https://developer.android.com/topic/performance/views/hardware-accel-views),
verbatim:

> "Complex shapes, paths, and circles for example, are rendered using texture masks. Every
> time you create or modify a path, the hardware pipeline creates a new mask, which can be
> expensive."

and the accompanying rule: **"Don't modify shapes too often."**

From [Slow rendering](https://developer.android.com/topic/performance/vitals/render), on
what makes `Record View#draw` overrun:

> "**Canvas.drawPath()** — Large paths are drawn on CPU then uploaded to GPU. Avoid editing
> paths frame-to-frame."
> "**Canvas.clipPath()** — Very expensive; use shape drawing instead."

Jetpack Compose's [Graphics modifiers](https://developer.android.com/develop/ui/compose/graphics/draw/modifiers)
page repeats it: *"If you have large paths, avoid editing them from frame to frame."*

This is exactly the shape of a Manim workload. Manim animations are dominated by
**interpolating Bezier control points** — `Transform`, `Create`, `ReplacementTransform`,
value trackers driving geometry. The path data genuinely changes every frame, so the
generation-ID keyed cache in Skia misses every frame, and we pay full path setup cost
every frame for every animating mobject. **Static, merely transformed paths are cheap;
morphing paths are not.** Any capacity estimate must be made in terms of *animating* paths
per frame, not total paths per frame.

Practical consequence for the IR: it is worth encoding "this path is static, only its
transform/colour animates" distinctly from "this path's geometry animates", because the
two have completely different costs on every substrate here, and on Canvas specifically
the first is nearly free (the transform goes on a `RenderNode` property, no re-record).

### 1.2 Where Skia's GPU path rendering falls over

Skia's Ganesh backend selects from a chain of path renderers
([`PathRendererChain.cpp`](https://github.com/google/skia/blob/main/src/gpu/ganesh/PathRendererChain.cpp)):
`DashLinePathRenderer`, `AAConvexPathRenderer`, `AAHairLinePathRenderer`,
`AALinearizingConvexPathRenderer`, `AtlasPathRenderer`, `SmallPathRenderer`,
`TriangulatingPathRenderer`, `TessellationPathRenderer` (only if GPU caps allow), and
`DefaultPathRenderer` as the always-present fallback. Each answers `canDrawPath()` with
`kNo` / `kAsBackup` / `kYes`, where `kAsBackup` is documented as *"This renderer is better
than SW fallback if no others can draw the path"*
([`PathRenderer.h`](https://github.com/google/skia/blob/main/src/gpu/ganesh/PathRenderer.h)).

Three concrete failure modes follow:

1. **Verb-count cliff.** `PathRenderer.h` carries
   `static constexpr int kMaxGPUPathRendererVerbs = 1 << 14` (16,384 verbs), described as a
   guard against path complexity that may *"cause OOM or other stalls."* Paths above that
   go to the software fallback. Manim scenes that merge many submobjects into one path
   (a dense graph, a filled surface, a long `VMobject` group) can cross this. **Emit many
   moderate paths rather than a few enormous ones.**
2. **Software fallback = CPU raster + texture upload.** When no GPU renderer accepts the
   path, Skia rasterises a coverage mask on the CPU and uploads it as a texture. This is
   the mechanism behind Android's "texture masks" wording, and it is the worst case:
   CPU time *and* a per-frame upload on the RenderThread.
3. **Anti-aliasing quality/speed trade.** The tessellating/MSAA path renderers are
   markedly faster but need MSAA and their quality is bounded by sample count; the analytic
   convex renderer is only for convex paths. Manim's typical stroked, self-intersecting,
   non-convex Beziers land in the expensive middle.

### 1.3 Negative result: rolling your own tessellator on GL ES is harder than it looks

The strongest available evidence against "just write it on OpenGL ES" is Flutter's
Impeller, a well-funded, dedicated 2D GPU renderer written by people who previously
shipped Skia integration.

- [flutter/flutter#143077](https://github.com/flutter/flutter/issues/143077) — *"[Impeller]
  Path drawing performance needs significant improvement"* — states path handling
  performance was **"not acceptable for release on Android"** relative to Skia. Profiling
  quoted in the issue: `67% FillPathGeometry::GetPositionBuffer -> 45%
  Tessellator::Tessellate + 20% Path::CreatePolyline`. Two thirds of frame CPU inside
  tessellation and polyline generation.
- [flutter/flutter#108499](https://github.com/flutter/flutter/issues/108499) — Impeller
  "tessellates every path synchronously on the CPU and transfers decompressed geometry to
  the GPU via vertex buffers."
- [flutter/flutter#126212](https://github.com/flutter/flutter/issues/126212) — a path with
  roughly 8,000 arc segments renders fine under Skia and **fails to render / corrupts under
  Impeller**, maintainer hypothesis being tessellation time or index-buffer overflow.
- [flutter/flutter#134432](https://github.com/flutter/flutter/issues/134432) —
  "Tessellation overhead causes regression on some animations."
- [flutter/flutter#183510](https://github.com/flutter/flutter/issues/183510) — Impeller
  "extremely slow and janky" on a Mali-T860 device while smooth with Impeller disabled.

The pattern: a from-scratch GPU path renderer beat Skia on *simple* content and lost badly
on *complex path* content, on exactly the low-end Android hardware we care about. Skia is
not fast because Skia is magic; it is fast because it has a dozen specialised path
renderers and a decade of fallback tuning.

### 1.4 Draw-call and batching cost

Ganesh is single-threaded and immediate-mode; it batches opportunistically but its design
is GL-centric. Skia's replacement backend, **Graphite**, records, sorts and batches draws
before submission, and was motivated precisely by Ganesh's inability to exploit
multithreading and GPU compute
([Chromium blog, Jul 2025 — Introducing Skia Graphite](https://blog.google/chromium/introducing-skia-graphite-chromes/);
Chrome reported up to ~15% Motionmark 1.3 improvement, measured on Apple Silicon, not
Android). **Android's HWUI still uses Ganesh, not Graphite**, so we inherit Ganesh's
batching behaviour and cannot choose otherwise via `Canvas`.

Practical implication: state changes matter. Every distinct paint (colour, shader,
blend mode, stroke width) can break a batch. Grouping the IR's draw stream by paint state
— all fills of colour X, then all strokes of width W — is a free win on any substrate and
a large one on Canvas.

### 1.5 What a cheap phone can actually sustain

No source gives "N Manim paths per frame on a Snapdragon 680". The honest answer is that
the number is workload-shaped, and the credible anchors are:

- **Impeller vs Skia on a Snapdragon 680 / 4 GB device**: GPU raster averaged 4.05 ms/frame
  (Skia) vs 2.81 ms (Impeller), with Impeller improving average frame render time ~22% and
  frame-time variance ~60% *for Flutter UI workloads* (widely republished benchmark; treat
  as order-of-magnitude, secondary source). The useful reading is that **GPU raster on a
  budget phone for a full-screen UI is single-digit milliseconds** — the GPU is not our
  problem, the CPU-side path work is.
- Skia's own text throughput ceiling in one reported case was ~10,000 `DrawText` calls/sec
  ([SkiaSharp#2771](https://github.com/mono/SkiaSharp/issues/2771)) — i.e. roughly
  300 calls per frame at 30 fps before text alone eats the budget, on desktop-class
  hardware. Per-draw-call overhead in Skia is on the order of tens of microseconds, not
  microseconds.
- Budget-device guidance from the React Native Skia ecosystem is consistent: "issuing
  hundreds to thousands of separate GPU commands every frame is where performance problems
  occur."

**Working assumption to carry into the spike, not a measured fact:** on the floor device
at 33 ms, expect a budget on the order of **a few hundred to low thousands of moderate
draw calls per frame**, with **animating (geometry-changing) paths costing several times a
static one**. "Thousands of filled and stroked Beziers per frame, all morphing" is above
that line on any substrate in this list and will require server-side reduction — path
simplification, culling of off-screen and fully-occluded mobjects, flattening static
subtrees into a single pre-recorded display list, and possibly dropping sub-pixel detail
at 720p. This is an IR-design constraint, not just a renderer constraint.

### 1.6 Masking, clipping, gradients

- **`clipPath()` is called out by name as "very expensive"** by Android. Skia implements
  non-rectangular clips via stencil or a clip mask texture; nested non-rect clips compound.
  Manim's masking (e.g. `add_to_back` reveal effects, `Succession` wipes) should be
  expressed as **a shader/alpha mask or a drawn shape with `BitmapShader`**, which is
  literally the workaround Android's docs recommend, rather than as `clipPath`.
- **`saveLayer` / offscreen compositing** is the other silent killer: Compose's
  `CompositingStrategy.Offscreen`, or any `alpha < 1` on a `graphicsLayer`, allocates an
  offscreen buffer. Group opacity animations — extremely common in Manim (`FadeIn` on a
  `VGroup`) — must be applied per-primitive where the primitives don't overlap, not as a
  group layer. Compose exposes exactly this via `CompositingStrategy.ModulateAlpha`.
- **Gradients** are cheap on all GPU substrates (they are shaders). Skia's `LinearGradient`
  / `RadialGradient` / `SweepGradient` map straight onto Manim's gradient fills, and
  `RuntimeShader` (AGSL, API 33+) covers anything exotic.
- Hardware-acceleration coverage for the operations we need settles at **API 28**:
  `drawPath()` scaling, `setPathEffect()` for lines, `setShadowLayer()`, `ComposeShader`
  inside `ComposeShader`, and the `DARKEN`/`LIGHTEN`/`OVERLAY` framebuffer blend modes all
  list "first supported API level 28"
  ([support table](https://developer.android.com/topic/performance/views/hardware-accel-views)).
  `setMaskFilter()` and `setLinearText()` are **never** hardware accelerated — avoid blur
  effects via `MaskFilter`; use `RenderEffect` (API 31) instead.

### 1.7 The alternatives, on this criterion

| Substrate | Path throughput assessment |
|---|---|
| **Canvas / Skia (HWUI)** | Best-in-class fallback chain; caches well for static paths, poorly for morphing ones. Everything above applies. Ganesh, not Graphite. |
| **Compose graphics layer** | Identical Skia underneath (`DrawScope` → `android.graphics.Canvas`, `Modifier.graphicsLayer` is **backed by `RenderNode`**). Adds Compose recomposition/measure overhead we do not need for a full-bleed animation surface. No throughput advantage, some overhead. |
| **OpenGL ES directly** | You must write the vector rasteriser. Impeller's evidence says that is a multi-year project that loses to Skia on complex paths. Only sane if paired with an existing vector renderer. |
| **Vulkan directly** | Same as GL ES plus driver risk (§4). Buys better batching/multithreading — the thing Graphite exploits — but we would be hand-building it. |
| **Rive Renderer** (added) | Purpose-built real-time vector GPU renderer, open source, C++, backends for Vulkan, Metal, D3D11/12, OpenGL/WebGL. Explicitly designed for "an unprecedented amount of vector graphics" with pristine AA. The closest thing to a drop-in answer to our exact problem. Risk: no glyph/text stack for us to reuse, integration is a native build, and its fastest modes depend on GPU features (fragment-shader interlock / pixel local storage class extensions) whose availability on low-end Mali is the open question. |
| **Skia bundled via NDK** (added) | Our own `GrDirectContext` on our own GL ES 3.0 context. Same rasteriser quality as HWUI, but **we pick the Skia version** (including Graphite later) and we can interleave our own GL draws. Costs single-digit MB per ABI and a non-trivial build. Strong hedge; see §5. |
| **Vello / vello_hybrid** (added) | GPU-compute-centric 2D renderer (Rust). The compute renderer is explicitly **"an experimental implementation"**; `vello_cpu` is described as *"currently overall more mature"*. `vello_hybrid`/Vello GPU works without compute shaders. No Android performance data published. Too early for a product floor of low-end Android. |
| **ThorVG** (added) | Small C++ vector engine (software + GL ES), used in the Lottie ecosystem. Lighter than Skia, but its GL backend is far less battle-tested and it has no path-caching story better than Skia's. |

---

## 2. Text and glyph rendering

### 2.1 Ship shaped glyph runs, not outlines — the measurement says so

The single most useful primary datum: converting text to outlines and drawing them as
paths is **slower** than drawing text. From
[SkiaSharp#2771](https://github.com/mono/SkiaSharp/issues/2771), where the reporter tried
exactly our proposed optimisation:

> Converting text to glyph outlines via `Paint.GetTextPath()` and rendering with
> `Canvas.DrawPath()` proved **"even slower"** than direct `DrawText` calls.

The reason is structural: Skia rasterises glyphs once into a **GPU glyph atlas**
(`GrAtlasGlyphCache`, populated via `glTexSubImage2D`) and thereafter every glyph is a
textured quad — effectively free, and batchable across a whole text run. An outline drawn
as a path re-enters the path renderer chain (§1.2) on every frame it changes, or at best
gets a cached texture mask per (path, matrix) pair.

**Recommendation for the IR: baked LaTeX should arrive as shaped glyph runs — font id +
glyph ids + positions — with the math fonts bundled in the APK.** Outlines should be the
exception, emitted only for glyphs that are stroke-on animated (§2.3).

### 2.2 Android gives us a first-class API for exactly that

- `Canvas.drawGlyphs(int[] glyphIds, int glyphIdOffset, float[] positions, int
  positionOffset, int glyphCount, Font font, Paint paint)` — **API 31**. This is a literal
  "replay a shaped glyph run" primitive.
- `android.graphics.text.TextRunShaper.shapeTextRun()` → `PositionedGlyphs` (glyph ids +
  positions + per-glyph `Font`) — **API 31**. Useful if we ever want to shape on-device.
- `android.graphics.fonts.Font.Builder` — **API 29** — loads a font from an asset/buffer,
  which is how we get Computer Modern / STIX / Latin Modern into a `drawGlyphs` call.
- Below API 31, the fallback is `Typeface.createFromAsset` + `Canvas.drawText` /
  `drawTextRun`, available since forever. This works but means we must address glyphs by
  *character*, not glyph id, so the exporter has to emit a character sequence plus
  positions rather than raw glyph ids. For a LaTeX pipeline with a known font set this is
  doable but adds an encoding wrinkle. **This is a real argument for minSdk 31**, or for
  emitting both encodings.
- Text scaling under hardware acceleration is supported from **API 18** (`drawText()`);
  `drawPosText()` and `drawTextOnPath()` only from **API 28**.

### 2.3 Known failure modes for a lot of animated glyphs

1. **Atlas thrash under continuous scale.** Skia rasterises per (glyph, size, matrix)
   bucket. A Manim `ScaleInPlace` on a formula, or a continuous camera zoom over text,
   generates a new rasterisation per distinct scale, evicting the atlas. Skia also **falls
   back to drawing glyphs as paths above a maximum atlas dimension** (very large text),
   which puts us straight back into §1.2. Mitigations: quantise animated text scale into
   buckets, or — better — draw text once at a canonical size into a `RenderNode` /
   `graphicsLayer` and animate the *layer's* `scaleX/scaleY`. The layer route is
   resolution-limited (visible softening past ~2× up-scale) but costs nothing per frame.
   This trade-off should be an explicit knob in the IR.
2. **Per-glyph draw calls.** `drawGlyphs` takes a whole run; one call per run, not per
   glyph. The exporter should group by (font, paint) so runs stay long. Naive per-glyph
   emission would multiply draw calls by ~20× for a typical equation.
3. **Cache clearing is expensive**, so avoid patterns that force it (e.g. cycling through
   very many distinct fonts/sizes in one scene).

### 2.4 Stroke-by-stroke ("write-on") animation

This is the one place outlines are unavoidable — you cannot partially draw an atlas quad.
Options on Canvas:

- `PathMeasure.getSegment(start, stop, dst, startWithMoveTo)` — copies a sub-range into a
  new `Path` each frame. Correct, and **the exact anti-pattern Android warns about**: a new
  path object every frame means a new texture mask every frame. Acceptable for a handful of
  concurrently-writing glyphs; not for a whole paragraph at once.
- `DashPathEffect` with an animated `phase` (or a dash array sized to the contour length)
  — draws only a prefix of the path without reallocating it, and is the technique Romain
  Guy documented. Caveat: `setPathEffect()` under hardware acceleration is listed as
  supported **for lines from API 28**, and dash effects apply to *strokes*, so this covers
  Manim's `Write`/`Create` (stroked outline first) but not a progressive *fill*.
- `AnimatedVectorDrawable` `trimPathStart` / `trimPathEnd` — the platform's own version of
  the same idea; useful as a reference implementation, too rigid as our runtime.

**Design rule:** cap the number of simultaneously stroke-animating glyphs in the exporter,
and let already-written glyphs snap back to the atlas path (`drawGlyphs`) the moment their
write-on completes. That keeps outline work proportional to the *writing frontier*, not to
the amount of text on screen.

### 2.5 Text on the raw GL ES / Vulkan options

On raw GL ES or Vulkan, **none of this exists**. We would own: font loading, glyph
rasterisation (or a pre-baked SDF/MSDF atlas shipped in the APK), atlas packing and
eviction, hinting decisions, and sub-pixel positioning. For a LaTeX-only corpus a
pre-baked MSDF atlas is actually tractable — the glyph set is closed and known at build
time — and gives free arbitrary scaling, which neatly solves §2.3(1). But it is weeks of
work that Canvas hands us for free, and MSDF degrades on sharp corners and thin serifs,
which is precisely what Computer Modern is made of. Rive likewise has no text stack we
could reuse directly.

**Criterion 2 verdict: Canvas/Skia wins decisively. Compose ties (same engine). GL ES and
Vulkan lose badly.**

---

## 3. 3D reachability

### 3.1 Canvas and Compose are 2D-only, and not partially so

- `android.graphics.Canvas` has **no depth buffer and no depth test**. It is a 2D
  painter's-algorithm surface.
- `Canvas.drawVertices()` (hardware-accelerated from **API 29**) and `Canvas.drawMesh()`
  with `MeshSpecification` (**API 34**) let you submit arbitrary triangles with custom
  AGSL shaders. This is genuinely more than "2D", but there is still **no depth buffer**,
  so triangles composite in submission order. It gives you textured/warped 2.5D, not 3D.
- `Modifier.graphicsLayer` exposes `rotationX`, `rotationY`, `rotationZ` and
  `cameraDistance` ([Graphics modifiers](https://developer.android.com/develop/ui/compose/graphics/draw/modifiers)),
  and the View system exposes the same via `View.setRotationX/Y` and `android.graphics.Camera`.
  This is per-layer perspective projection — a card flip — not a scene graph. Two layers
  cannot interpenetrate.

**So: yes, choosing Canvas or Compose is a 2D-only choice, and it does quietly pre-decide
the 3D question.** It should be made with eyes open.

### 3.2 But the reference implementation is also 2D-only, which changes the stakes

Manim's own **Cairo renderer has no z-buffer**: it transforms world coordinates through the
camera, projects to 2D screen space (`points_to_pixel_coords`), and emits cubic Bezier
paths that composite in scene order. Correct occlusion in Manim comes only from the
**OpenGL renderer**, where `depth_test = True` enables real Z-buffering
([ManimCommunity/manim](https://github.com/ManimCommunity/manim);
[three_d_scene docs](https://docs.manim.community/en/stable/_modules/manim/scene/three_d_scene.html)).

That is a big deal for this ticket. It means:

- For any 3D scene authored against the **Cairo** model — `ThreeDScene` with
  `set_camera_orientation`, rotating axes, parametric surfaces drawn as sorted polygon
  fans — a 2D substrate reproduces the reference **exactly**, provided the IR carries 3D
  vertex data plus the camera and the client re-projects per frame. Camera moves are then
  just a per-frame matrix applied to control points before emitting paths. Cheap, and
  entirely within Canvas's abilities.
- For **molecular structures** — overlapping spheres and bonds that must occlude each
  other correctly from every angle — painter's-algorithm sorting is not enough. Per-object
  depth sorting fails on interpenetrating geometry (a bond cylinder passing through an
  atom sphere is the canonical failure), and per-triangle sorting at interactive rates is
  a CPU cost we cannot pay on the floor device. **These scenes need a real depth buffer.**

So the split is not 2D-vs-3D, it is *projected-vector 3D* (fine on Canvas) vs
*occluded-solid 3D* (needs GL).

### 3.3 The seam is real and has a well-trodden implementation

Adding a GL ES 3D layer later does **not** require rewriting the 2D renderer, because
Android gives several supported ways to compose a GL surface with a Canvas surface:

- **`SurfaceView` / `GLSurfaceView`** — a separate compositor layer, often a hardware
  overlay, z-ordered above or below the window. Cheapest, but z-order is all-or-nothing:
  you cannot interleave 2D content above *and* below the 3D content in one pass.
- **`TextureView`** — GL content as a regular view in the hierarchy, fully interleavable,
  at the cost of an extra copy and no overlay promotion.
- **GL → Canvas**: render 3D into a `SurfaceTexture` / `HardwareBuffer` and draw the result
  as a bitmap/shader inside the Canvas scene. Gives correct interleaving with one buffer
  round-trip per frame.
- **Canvas → GL**: `HardwareRenderer` + `RenderNode` (**both API 29, both public**) let an
  app drive the HWUI/Skia pipeline into an arbitrary `Surface` — including an
  `ImageReader`-backed one — so 2D content can be composited *inside* a GL scene.

For the eventual 3D layer, **Filament** (Google, OpenGL ES 3.0 and Vulkan backends,
Android-first, actively maintained) is the obvious candidate and avoids writing a PBR
renderer for molecules. A hand-rolled GL ES 3.0 renderer is also viable given how simple
ball-and-stick geometry is.

### 3.4 The one option that serves both from one substrate

If "never ship a second renderer" is a hard requirement, the only credible route is
**bundling Skia via the NDK on our own OpenGL ES 3.0 context**: Skia's `GrDirectContext`
can share a GL context with our own draw calls, so 2D vector content and a depth-tested 3D
pass live in the same surface with correct interleaving, one swap, one frame pacing
source. Rive Renderer on a shared GL context is the same idea with a different vector
engine. Both cost a native build and single-digit MB per ABI, and both give up "the OS
maintains our rasteriser for us".

**Criterion 3 verdict:** Canvas/Compose are 2D-only and force a second path for
occluded-solid 3D. GL ES and Vulkan serve both but lose criteria 1 and 2. Bundled-Skia-on-GL
is the only single-substrate answer, at meaningful cost.

---

## 4. Reach and minimum API level

### 4.1 Google's own distribution numbers (collected to 24 Nov 2025)

From the [Distribution dashboard](https://developer.android.com/about/dashboards):

**OpenGL ES, handheld devices**

| Version | Share |
|---|---|
| GL ES 2.0 | 0.49% |
| GL ES 3.0 | 0.86% |
| GL ES 3.1 | 0.39% |
| **GL ES 3.2** | **98.24%** |

**Vulkan, handheld devices**

| Version | Share |
|---|---|
| **None** | **7.37%** |
| 1.0.3 | 3.86% |
| 1.1 | 62.09% |
| 1.3 | 26.01% |
| 1.4 | 0.67% |

**Android Vulkan Profiles** (share of Vulkan-capable devices, Oct 2025): AVP 2021 **95.5%**,
AVP 2022 **86.5%**, AVP 2025 **80.1%**.

Read directly: **requiring Vulkan 1.1 excludes ~11.2% of handhelds** (no Vulkan + 1.0.3),
and those excluded devices are disproportionately the cheap ones we said were the floor.
OpenGL ES 3.2 is effectively universal.

### 4.2 Vulkan driver quality on low-end Android — Google's own warnings

From [Native and proprietary engines](https://developer.android.com/games/develop/vulkan/native-engine-support),
verbatim:

> "Older Android devices could be using out-of-date Vulkan drivers. These driver versions
> might include bugs that can affect the stability of your game. **Working around driver
> bugs can involve significant amounts of testing and engineering time.**"

> "Many older devices are limited to version 1.0.3 of the Vulkan API and are often missing
> widely used Vulkan extensions available on more modern hardware."

> "When targeting older devices, **include OpenGL ES rendering support as a fallback**, as
> some devices in your target device list may have Vulkan implementations that can't run
> your game reliably."

Google telling you to keep a GL ES fallback is about as clear a signal as this criterion
gets. Corroborating field evidence from a real vector-rendering product: MapLibre Native
made Vulkan the Android default in 13.0.0 and immediately collected reports of
[lag and jitter on Vulkan that were absent on OpenGL ES](https://github.com/maplibre/maplibre-native/issues/4130)
(the issue is thin on measurements, so treat it as a smell, not a proof). Flutter's
Android Vulkan issue list shows the same texture: driver-specific corruption on Mali-G72
([#192798](https://github.com/flutter/flutter/issues/192798)) and Mali-G52
([#187505](https://github.com/flutter/flutter/issues/187505)).

There is also a **hidden tax unique to raw Vulkan**: surface pre-rotation. If you don't
implement `preTransform` matching `surfaceCapabilities.currentTransform`, SurfaceFlinger
does the rotation and you eat **1–3 ms of frame time** from compositor preemption plus a
**~40% higher GPU clock** than necessary
([Vulkan pre-rotation](https://developer.android.com/games/optimize/vulkan-prerotation)).
On a 33 ms budget, 1–3 ms is 3–9% of the frame, spent on nothing.

### 4.3 API-level floors for each option

| Capability | Min API |
|---|---|
| `Canvas` 2D drawing | 1 |
| Hardware-accelerated `drawPath()` scaling, `setPathEffect()`, `ComposeShader`-in-`ComposeShader`, `DARKEN/LIGHTEN/OVERLAY` | **28** |
| `RenderNode`, `HardwareRenderer` (public) | **29** |
| `Canvas.drawVertices()` hardware-accelerated | **29** |
| `Font.Builder` (app-bundled fonts as `Font`) | **29** |
| `Canvas.drawGlyphs()`, `TextRunShaper`, `PositionedGlyphs` | **31** |
| `RenderEffect` (blur etc.) | **31** |
| `RuntimeShader` (AGSL) | **33** |
| `Canvas.drawMesh()` / `android.graphics.Mesh` | **34** |
| OpenGL ES 2.0 | 8 |
| OpenGL ES 3.0 / 3.1 / 3.2 | 18 / 21 / 24 |
| Vulkan | 24 |

Cumulative reach (StatCounter-derived, Apr 2026 data): **API 30 ≈ 86.9%**, API 33 ≈ 68.9%,
API 34 ≈ 54.5% ([apilevels.com](https://apilevels.com/)). API 28 and 29 are comfortably
above 90%.

**Suggested floor: minSdk 29**, which gets `RenderNode`/`HardwareRenderer`, hardware
`drawVertices`, `Font.Builder`, and all the API-28 path/paint fixes, at ~90%+ reach.
Gate `drawGlyphs` (31) behind a runtime check with a `drawTextRun` fallback, and treat
`RuntimeShader` (33) and `drawMesh` (34) as progressive enhancement only.

### 4.4 Direction of travel

Google now calls Vulkan *"the primary low-level graphics API on Android, replacing OpenGL
ES"*, and says OpenGL ES *"is still supported on Android, but is no longer under active
feature development"*
([Use Vulkan for graphics](https://developer.android.com/games/develop/vulkan/overview)).
From Android 15, **ANGLE** ships as an optional GL ES-on-Vulkan driver, and Google intends
to ship ANGLE as the GL system driver on more new devices, with GL ES eventually available
*only* through ANGLE.

Two things follow, and they cut in opposite directions:
- Writing to GL ES is **not** a dead end: it keeps working, increasingly via ANGLE's
  well-tested Vulkan translation, which is often *more* reliable than a vendor GL driver.
- But GL ES will not get new features, and on ANGLE devices you pay a thin translation
  layer.

Neither is a reason to pick raw Vulkan today. Notably, **`Canvas` sidesteps the whole
question**: HWUI picks its own backend (`skiagl` or `skiavk`) per device and OS version,
so the platform absorbs this migration on our behalf.

---

## 5. Recommendation

### Pick: Skia via the Android `Canvas` API, driven from `RenderNode` display lists in a custom `SurfaceView`.

Concretely:

- A custom `SurfaceView` (not a Compose `Canvas`) owns the animation surface, so playback
  runs on its own thread with its own frame pacing and is not coupled to Compose
  recomposition or the app's UI thread.
- The IR replayer records into **`RenderNode`s**, one per logical mobject subtree, and
  re-records only the nodes whose geometry actually changed this frame. Static subtrees are
  recorded once and re-drawn by reference; their transforms and alpha are set as
  `RenderNode` *properties*, which costs nothing per frame.
- Text goes through `Canvas.drawGlyphs` with app-bundled math fonts (API 31+), falling back
  to `drawTextRun` with `Typeface.createFromAsset` below that.
- Use Compose for app chrome — controls, navigation, scrubber — and embed the
  `SurfaceView` via `AndroidView`. Compose is the right tool for the app, the wrong tool
  for the frame loop.

### Why

1. **It is the only option that already solves the hard parts.** Filled and stroked
   Beziers with correct anti-aliasing, non-zero and even-odd fills, joins and caps,
   gradients, blend modes, clipping, *and* a production glyph atlas — all present, all
   tuned, all maintained by Google, all shipped in the OS at zero APK cost.
2. **The negative results point away from the alternatives.** Flutter's Impeller — a
   dedicated, well-resourced 2D GPU renderer — found its own path performance *"not
   acceptable for release on Android"*, with two thirds of frame CPU in tessellation, and
   still corrupts on paths Skia draws fine. We would be re-running that experiment with
   less budget.
3. **Reach is strictly better.** GL ES 3.2 is on 98.24% of handhelds and `Canvas` is on all
   of them; Vulkan 1.1 leaves out ~11%, concentrated exactly in our floor segment, and
   Google's own docs tell you to keep a GL ES fallback and warn that driver-bug workarounds
   cost "significant amounts of testing and engineering time."
4. **Compose's graphics layer offers nothing extra here.** `DrawScope` bottoms out in
   `android.graphics.Canvas` and `Modifier.graphicsLayer` is backed by `RenderNode` — the
   same machinery, plus Compose overhead we do not want in a 30 fps frame loop.
5. **It is reversible at the seam we care about.** The IR, the scene-graph diffing, the
   timing model and the text pipeline are all substrate-independent. If measurement shows
   Canvas cannot hold 33 ms, the replayer's back end can be swapped for **Rive Renderer**
   or **bundled Skia on our own GL ES 3.0 context** without touching the IR.

### Conditions on this recommendation

This is a bet that the *exporter* can keep per-frame animating-path counts inside budget.
Before committing, spike this, on the actual floor device:

- **Measure the cliff.** Render N morphing cubic Beziers (stroked, AA, ~20 verbs each) at
  720p and find N where `Record View#draw` + `DrawFrame` exceeds 33 ms. Repeat with the
  paths static-but-transformed. The ratio between those two numbers is the most important
  number in this project.
- **Verify the `drawGlyphs` path** with a bundled Computer Modern and a real formula,
  including a continuous scale animation, and measure atlas thrash.
- **Verify a write-on animation** using `DashPathEffect` phase rather than
  `PathMeasure.getSegment`, and confirm it stays hardware-accelerated.

Hard rules to encode in the exporter and the replayer regardless of outcome:
never `clipPath` where a shader mask will do; never `saveLayer`/offscreen for group alpha
on non-overlapping content; keep single paths well under 16,384 verbs; group the draw
stream by paint state; mark static vs. morphing geometry in the IR.

### What this choice implies for 3D — stated explicitly

**Choosing `Canvas` is choosing a 2D-only primary substrate. It commits us to a second
rendering path for any scene that needs true depth occlusion.** That is a deliberate,
accepted cost, not an oversight, and it is bounded for three reasons:

1. **Most Manim 3D is already 2D.** Manim's Cairo renderer has no z-buffer; it projects 3D
   geometry to 2D Bezier paths in painter order. Any scene authored against that model —
   rotating axes, parametric surfaces, camera moves over projected curves — replays
   *exactly* on Canvas, provided **the IR carries 3D vertex data and the camera matrix and
   the client re-projects per frame**. This is a requirement on the IR that must be
   designed in now: do not let the exporter flatten 3D scenes to fixed 2D paths, or camera
   moves become un-replayable and the payload stops being compact.
2. **Only occluded-solid content needs the second path.** Molecular structures with
   interpenetrating spheres and bonds cannot be served by per-object depth sorting. Those
   scenes — and only those — get a depth-tested **OpenGL ES 3.0** renderer (Filament, or a
   small custom one) in a `SurfaceView`.
3. **The composition seam is supported and cheap.** `SurfaceView` z-ordering for the simple
   case; `SurfaceTexture`/`HardwareBuffer` for GL-inside-Canvas; `HardwareRenderer` +
   `RenderNode` (both public since API 29) for Canvas-inside-GL. Nothing here requires
   private APIs.

If a single substrate for both 2D and 3D is judged a hard requirement — the seam is
genuinely a maintenance cost, two renderers means two sets of frame-pacing and colour bugs
— then the answer is **not** raw OpenGL ES or Vulkan. It is **bundling Skia (or Rive
Renderer) via the NDK onto our own OpenGL ES 3.0 context**, which keeps a production vector
rasteriser and gains a depth buffer in the same surface. That is the documented fallback
position, and it should be revisited if and when the first molecular scene ships.

---

## Sources

Primary (Android / Google):
- [Hardware acceleration](https://developer.android.com/topic/performance/hardware-accel)
- [Hardware acceleration (Views) — support tables, layers, display lists, texture masks](https://developer.android.com/topic/performance/views/hardware-accel-views)
- [Slow rendering — frame budget, drawPath/clipPath guidance](https://developer.android.com/topic/performance/vitals/render)
- [Graphics modifiers (Compose) — graphicsLayer/RenderNode, CompositingStrategy, path guidance](https://developer.android.com/develop/ui/compose/graphics/draw/modifiers)
- [Graphics in Compose](https://developer.android.com/develop/ui/compose/graphics/draw/overview)
- [Distribution dashboard — OpenGL ES / Vulkan / AVP shares](https://developer.android.com/about/dashboards)
- [Use Vulkan for graphics](https://developer.android.com/games/develop/vulkan/overview)
- [Native and proprietary engines — driver quality warnings](https://developer.android.com/games/develop/vulkan/native-engine-support)
- [Android Vulkan Profiles (AVP)](https://developer.android.com/ndk/guides/graphics/android-vulkan-profile)
- [Vulkan pre-rotation — 1–3 ms / 40% GPU clock](https://developer.android.com/games/optimize/vulkan-prerotation)
- [Canvas API reference](https://developer.android.com/reference/android/graphics/Canvas), [PositionedGlyphs](https://developer.android.com/reference/android/graphics/text/PositionedGlyphs), [HardwareRenderer](https://developer.android.com/reference/android/graphics/HardwareRenderer)

Primary (Skia / engines / issue threads):
- [skia — PathRenderer.h](https://github.com/google/skia/blob/main/src/gpu/ganesh/PathRenderer.h), [PathRendererChain.cpp](https://github.com/google/skia/blob/main/src/gpu/ganesh/PathRendererChain.cpp)
- [Introducing Skia Graphite](https://blog.google/chromium/introducing-skia-graphite-chromes/)
- [flutter#143077 — Impeller path drawing performance](https://github.com/flutter/flutter/issues/143077)
- [flutter#126212 — complex paths cause errors/freezes](https://github.com/flutter/flutter/issues/126212)
- [flutter#108499 — GPU path tessellation](https://github.com/flutter/flutter/issues/108499)
- [flutter#134432 — tessellation overhead regression](https://github.com/flutter/flutter/issues/134432)
- [flutter#183510 — Mali-T860 jank with Impeller](https://github.com/flutter/flutter/issues/183510)
- [SkiaSharp#2771 — DrawText throughput; outlines slower than DrawText](https://github.com/mono/SkiaSharp/issues/2771)
- [maplibre-native#4130 — Vulkan lag/jitter vs OpenGL](https://github.com/maplibre/maplibre-native/issues/4130), [#4114 — Vulkan by default](https://github.com/maplibre/maplibre-native/issues/4114)
- [rive-app/rive-runtime](https://github.com/rive-app/rive-runtime), [linebender/vello](https://github.com/linebender/vello), [google/filament](https://github.com/google/filament)
- [ManimCommunity/manim — three_d_scene](https://docs.manim.community/en/stable/_modules/manim/scene/three_d_scene.html)

Secondary (used only for order-of-magnitude, flagged inline): republished Impeller-vs-Skia
Snapdragon 680 benchmarks; React Native Skia batching write-ups; [apilevels.com](https://apilevels.com/)
cumulative reach figures.

### Sources that could not be retrieved

The research network blocked `skia.org`, `skia.googlesource.com`, `source.android.com`,
`blog.chromium.org`, `blog.google`, `groups.google.com` (skia-discuss), `rive.app`,
`news.ycombinator.com`, `vulkan.org` (Ian Elliott's *Vulkan on Android* Vulkanised 2025/2026
decks) and `arxiv.org`. Claims that would normally be sourced there were either obtained
from the GitHub mirror of the Skia repo, from `developer.android.com`, or from search-engine
summaries and are flagged as secondary above. **Two figures worth re-verifying against the
original when those domains are reachable:** the Graphite Motionmark number, and the
Snapdragon 680 Impeller-vs-Skia frame times.
