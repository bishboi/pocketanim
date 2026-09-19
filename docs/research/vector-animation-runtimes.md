# Vector-animation IRs and Android runtimes: adopt or invent?

**Ticket:** should pocketanim adopt an existing vector-animation IR + Android runtime instead of
inventing its own?

**Date:** 2026-09-19

**Verdict up front: INVENT the IR. ADOPT the rasterizer.** Do not adopt Lottie, dotLottie, Rive,
AnimatedVectorDrawable or PAG as the wire format. Build a purpose-built, random-access binary IR for
Manim semantics and replay it onto Skia — which is already in the OS as `android.graphics.Canvas`,
at zero binary-size cost. Rationale and risks are in the final section.

---

## 1. What we are actually grading

Three requirements do almost all the disqualifying work:

1. **Arbitrary-time evaluation.** Any frame at time *t* must be renderable on demand, without
   replaying [0, t). This is a property of *both* the format (is state at *t* a pure function of *t*?)
   and the runtime (does the API expose `seek(t); render()` as separable operations?).
2. **Expressiveness under Manim semantics** — thousands of filled/stroked cubic Beziers per frame,
   arbitrary per-frame geometry, clipping/masking, gradients, baked LaTeX glyph outlines, 3D camera.
3. **Low-end Android at 720p30.** ~33.3 ms/frame budget on a mid-2010s-class SoC, CPU rasterisation
   or a GL ES 3.0-class GPU at best.

### 1.1 The Manim impedance mismatch, stated precisely

Every candidate here descends from After Effects. AE's model is *a small, fixed layer tree whose
scalar properties are keyframed over time*. Manim's model is *a scene graph of `VMobject`s whose
cubic-Bezier point arrays are recomputed from scratch every frame by arbitrary Python*.

Concretely, these Manim behaviours have no native AE-model equivalent:

- `Transform(a, b)` where `a` and `b` have different anchor counts. Manim null-pads to align point
  counts internally, so a per-frame export is well defined — but the *format* must tolerate a shape
  whose vertex count changes at a boundary.
- `Create` / `Write` / `ShowPartial`, implemented via `pointwise_become_partial` — a genuine
  path-length reparameterisation, not an opacity fade.
- `ValueTracker` + `always_redraw` / `updater` functions: geometry that is an arbitrary function of
  scene state, with no closed form the exporter can keyframe.
- `ThreeDScene` camera moves with real perspective and per-frame depth sorting.

This matters for the *size* claim, not just fidelity. The Lottie specification is explicit:

> "For interpolation to work correctly all bezier values in a property's keyframe must have the same
> number of points."
> — [Lottie Specs, Properties](https://lottiefiles.github.io/lottie-docs/properties/)

So any Manim animation that is not a pure affine transform of a fixed point set must be exported as
**one Bezier keyframe per frame per shape**. That is a full geometry dump at 30 fps wearing a Lottie
costume — strictly *larger* than a purpose-built binary IR (JSON floats, `"i"/"o"/"v"` triples,
no delta coding), while inheriting every runtime limitation below. The megabytes-to-kilobytes goal
dies on this sentence alone for any AE-derived format.

There is no existing Manim→Lottie/Rive/PAG exporter. The one piece of prior art,
[`manim-svg-animations`](https://github.com/MathItYT/manim-svg-animations) (21 stars, ~52 commits),
sidesteps the problem by emitting per-frame SVG snapshots into a browser — i.e. it independently
arrived at "dump geometry per frame", which confirms the shape of the problem but is not a runtime
we can ship.

---

## 2. Lottie (and dotLottie)

**Format:** JSON layer tree with keyframed properties; dotLottie is *only* a ZIP container around
one or more Lottie JSONs plus assets and a manifest — it changes packaging, not the animation model,
so everything below applies identically.

### 2.1 Expressiveness

Per the [official Android support matrix](https://github.com/airbnb/lottie/blob/master/supported-features.md):

- **Supported:** arbitrary Bezier shapes, fills (incl. linear/radial gradients, fill rule), strokes
  (width, caps, joins, miter, dashes, gradient strokes), full 2D transforms with parenting, all
  interpolation types incl. spatial Bezier, **masks** (add/subtract, path, opacity), **alpha and
  alpha-inverted track mattes**, merge paths (API 19+), precomps, time stretch, time remap, markers,
  text as glyphs/fonts with fill/stroke/tracking, Gaussian blur and drop shadow.
- **Unsupported on Android:** auto-orient, expressions, **luma matte** variants, **mask intersect
  mode**, layer effects (fill/stroke/tint/tritone), text-on-path, per-character 3D, range and
  expression selectors.
- **3D: effectively absent.** `ddd` is a flag in the schema and `CameraLayer` is layer type 13, but
  3D layers are not supported by lottie-android at all, and even lottie-web flattens them —
  "layers are displayed as if they were 2D and are flattened with no perspective"
  ([lottie-web #2572](https://github.com/airbnb/lottie-web/issues/2572),
  [lottie-web 3D wiki](https://github.com/airbnb/lottie-web/wiki/3D)). Camera options are not
  exportable. **Our 3D scenes would have to be flattened to 2D on the server**, which forfeits the
  camera-move use case entirely.

**Where it hits the wall:** no hard node/path-count limit exists in the schema — but see §2.2; and
the equal-vertex-count interpolation rule (§1.1) makes non-affine geometry change pathologically
expensive to encode.

**Glyph/stroke-on story:** the right primitive exists — **Trim Paths** maps well onto Manim's
`Create`/`Write`. But text must be pre-converted to outlines (Lottie's text-layer support is a
different, weaker code path), and lottie-android has an *open* rendering bug where
`Trim multiple shapes: individually` is ignored and all paths animate simultaneously
([lottie-android #2262](https://github.com/airbnb/lottie-android/issues/2262), open, labelled
"Rendering bug", reproduced on 5.2.0 and 6.0.0). Writing a formula glyph-by-glyph is exactly the
case that bug breaks. See also
[#2402 "Lottie Animation Tracing All at Once Instead of Step by Step"](https://github.com/airbnb/lottie-android/issues/2402).

### 2.2 Performance (lottie-android)

From the [official performance guide](https://github.com/airbnb/lottie/blob/master/android.md) —
these are the maintainers' own warnings, not third-party complaints:

- "Masks and mattes on android have the **largest performance hit**." Cost is proportional to the
  intersection bounds of the masked layer and the mask. Hardware acceleration gives "several X"
  improvement *specifically* for masks/mattes.
- **Merge paths are disabled by default** because the underlying `Path.Op` is slow and would "ship
  broken experiences on older devices."
- **Hardware acceleration is off by default**: it does not support anti-aliasing, does not support
  stroke caps pre-API-18, and "may actually perform worse depending on the animation." So the
  default configuration is *software* rasterisation on the UI thread — which is where we would land
  at thousands of paths.
- The recommended remedy is "eliminate masks, mattes, and merge paths where possible" — i.e. remove
  three of the features we specifically need.

The most useful real-world datapoint is **Telegram's TGS** (gzipped Lottie), the largest production
deployment of Lottie on low-end Android. Telegram's
[sticker requirements](https://core.telegram.org/stickers) cap animations at 512×512, ≤3 s, and
**≤64 KB**, and forbid: *masks, layer effects, images, solids, texts, 3D layers, merge paths, star
shapes, gradient strokes, repeaters, time stretching, time remapping, auto-oriented layers,
expressions, auto-bezier keys.* When a company with Telegram's resources ships Lottie at scale on
cheap hardware, it bans essentially every feature on our requirements list. That is the clearest
available statement of where Lottie's practical complexity ceiling sits.

Also relevant: Lottie has no single renderer. lottie-web, lottie-android, lottie-ios, Skottie and
ThorVG are separate implementations with separate feature subsets, and cross-renderer mismatch is a
chronic, well-documented class of bug (e.g.
[lottie-android #2671](https://github.com/airbnb/lottie-android/issues/2671),
[#2667](https://github.com/airbnb/lottie-android/issues/2667),
[thorvg #4162 "fill effect mismatch between lottie-web/skottie/thorvg"](https://github.com/thorvg/thorvg/issues/4162),
[thorvg #3896](https://github.com/thorvg/thorvg/issues/3896)). Adopting Lottie means adopting
"our server's output looks right in one renderer" as a permanent QA problem.

### 2.3 Arbitrary-time evaluation — **this one passes, and cleanly**

This is Lottie's genuine strength and the reason it deserves serious consideration despite
everything above. Reading `LottieDrawable.java`, rendering is a pure function of progress:

```java
public void setProgress(@FloatRange(from = 0f, to = 1f) final float progress) {
  ...
  animator.setFrame(composition.getFrameForProgress(progress));
}
```

`draw()` then dispatches to `drawDirectlyToCanvas()` or `renderAndDrawAsBitmap()` from that frame
value. There is **no incremental playback state**: set progress to any value, draw, get the correct
frame. A semaphore guards concurrent `setProgress`/`draw`. Scrubbing is a first-class operation, and
the docs explicitly support "manually set progress to hook up an animation to a gesture."
(Historical `setFrame` off-by-one and RecyclerView glitches — e.g.
[#591](https://github.com/airbnb/lottie-android/issues/591),
[#1157](https://github.com/airbnb/lottie-android/issues/1157) — have been addressed via an animator
overhaul, and are integration bugs, not model limitations.)

**Conclusion on Lottie:** passes the seek test, fails on 3D, fails on encoding efficiency for
non-affine geometry, and the feature set we need is precisely the feature set its own maintainers
and largest production user tell you to avoid on low-end Android.

### 2.4 Lottie runtime variants

| Runtime | Status | Seek | Notes |
|---|---|---|---|
| **lottie-android** (airbnb) | Mature, actively maintained | ✅ true `setProgress` | Java/Kotlin, `android.graphics.Canvas`, software by default. The reference Android implementation. |
| **rlottie** (Samsung) | ❌ **ARCHIVED** | ✅ `renderSync(frameNo, surface)` | README: "This project has been archived and is no longer maintained. We does not provide security support, vulnerability review, patches, releases, or CVE assignment/coordination." Feature table marks **text/glyphs/fonts, merge paths, layer effects, skew, and most mask modes as unsupported**. Doubly disqualified: dead, and cannot draw text. LVGL now marks it deprecated. |
| **ThorVG** | ✅ Actively maintained, v1.1 (Jul 2026) | ✅ `Result frame(float no)` — "Specifies the current frame in the animation", arbitrary index | The healthiest Lottie engine. C++, SW + GL/WebGL/WebGPU backends. Powers all official dotLottie players (web/iOS/Android). But its Lottie conformance is still actively churning — the issue tracker carries a steady stream of Lottie correctness bugs. |
| **dotlottie-android** (LottieFiles) | ⚠️ **v0.5.0**, ~89 commits, ~153 stars | ⚠️ exposes `setSegment(start,end)` + `currentFrame`; no documented direct `seekToFrame` | Rust (`dotlottie-rs`) over ThorVG, via UniFFI. API 21+, four ABIs. Too immature to bet a product on today, and the playback API is play/pause/segment-shaped rather than scrub-shaped. |
| **Skottie** (Skia) | ✅ Mature, Google-maintained, in Chrome | ✅ **best-in-class** | See §5. |

---

## 3. Rive

### 3.1 Expressiveness

Rive is a genuinely modern vector format with a clean binary encoding (`.riv`: little-endian,
`RIVE` fingerprint, varuint-keyed object/property stream driven by "core defs" JSON). It supports
arbitrary Beziers, clipping, gradients, meshes, bones, N-slicing, runtime text, vector feathering,
and data binding. The runtime is **MIT-licensed**, which is a real advantage.

**Where it hits the wall — two hard blockers:**

1. **No supported programmatic authoring path.** `.riv` is defined as "the binary runtime format
   **exported from the Rive Editor**." The format is documented, but the authoring toolchain is a
   commercial GUI editor. Community/experimental writers exist —
   [`rive-rs-cli`](https://github.com/George-RD/rive-rs-cli) (third-party) and
   [`rive-code-generator-wip`](https://github.com/rive-app/rive-code-generator-wip) (Rive's own,
   explicitly "wip", and a *reader* that extracts names, not a writer). Building our server exporter
   on a reverse-engineered writer for a vendor-controlled binary format that changes with the editor
   is an unacceptable dependency for a pipeline component.
2. **3D is not there.** Rive content "is essentially orthographic by design"; view matrices are
   supported "only in 2D space." Rive's newer **GPU Canvas** announcement adds 3D-ish capability but
   is a new, advanced, renderer-gated layer — not a substrate for `ThreeDScene` camera moves today.

Rive's authoring model is also *designer*-shaped (artboards, state machines, inputs, interactivity),
which is the opposite of what we need: we have a deterministic, non-interactive, machine-generated
timeline.

### 3.2 Performance

The Rive Renderer is a serious piece of engineering — GPU-first, with layered fallbacks: pixel local
storage (Apple/modern mobile), fragment shader interlock (NVIDIA/Intel), R/W texture and
`EXT_shader_pixel_local_storage`, and an **MSAA path on minimal drivers**. Backends: Metal, Vulkan,
D3D11/12, OpenGL/WebGL. On paper this is the best path-throughput story of any candidate.

**But on Android specifically, the CPU escape hatch has been removed.** In `rive-android`,
`RendererType` now contains only:

```kotlin
enum class RendererType(val value: Int) {
    Rive(0),
    @Deprecated("The Canvas renderer is deprecated. Use the Rive renderer instead.")
    Canvas(1),
}
```

Rive on Android is now **GPU-only**. That is a bet that every device in our floor has a driver that
behaves on one of those fallback paths. Rive's own engineers note they "see fewer problems with
OpenGL/ES 3.0 [on iOS] than with OpenGL/ES 3.1 on Android" — driver variance on cheap Android GPUs
is exactly the risk the MSAA fallback exists to absorb, and it is the path with the worst
fill-rate cost. min SDK 21, four ABIs, `libc++_shared.so` conflicts are a documented integration
hazard. I found no independent low-end Android benchmark with path counts near ours; the widely
circulated "Rive vs Lottie" comparisons are vendor or SEO content and should not be relied on.

### 3.3 Arbitrary-time evaluation — **partial pass, with a trap**

`LinearAnimationInstance` does expose true seeking:

```cpp
void time(float value);            // "Sets the animation's point in time."
float time() const;
bool advance(float seconds, ...);  // forward integration
void apply(float mix = 1.0f) const;
```

So `instance.time(t); instance.apply(); artboard.draw()` is a genuine arbitrary-time evaluation for
a *linear timeline*. Header comments confirm the design is seek-aware ("Time-seeking via
`time(float)` and `reset()` intentionally does NOT clear the cache").

**The trap:** Rive's idiomatic model is the **state machine**, which is strictly forward-integrating
— `StateMachineInstance::advance(elapsed)`. Rive's own docs are blunt: `scrub()` "will not do
anything if you are playing through a state machine." Adopting Rive means confining ourselves to the
linear-timeline subset and forgoing the machinery that makes Rive worth adopting. At that point we
are using an expensive, editor-gated format as a dumb timeline container.

---

## 4. Android `AnimatedVectorDrawable` — **disqualified outright**

1. **It cannot seek. At all.** AVD exposes `start()`, `stop()`, `reset()`, and registration for
   `Animatable2` callbacks. There is no `setCurrentPlayTime`, no progress, no frame. It does not
   expose its internal `AnimatorSet`. It is a fire-and-forget forward-playing timeline. This alone
   ends the discussion for a video-player-like scrubbing UX.
2. **Expressiveness is far below our floor.** Path morphing requires the two paths to have identical
   command structure and point counts (hence tools like VectAlign existing at all). Geometry lives
   in XML `pathData` strings. Gradients are API 24+. Masking beyond `clip-path` is absent. 3D:
   nonexistent. Per-glyph text animation: nonexistent.
3. **Performance is explicitly not designed for this.** Google's own guidance is that
   VectorDrawables suit icons and images **up to ~200×200 dp**, and that "very complex images should
   consider using WebP." Animated vectors *cannot cache to a bitmap* because their properties change
   each frame, so every frame re-parses and re-draws. Clipping is called out as particularly
   expensive. (API 25+ moves AVD to RenderThread, which helps jank but not throughput.)

This is the wrong tool by two orders of magnitude.

---

## 5. Skia directly — SkSVG, Skottie, and `android.graphics.Canvas`

Skia deserves to be split into three distinct propositions, because they have very different
answers.

### 5.1 SkSVG — not a candidate

`SkSVG` is a static SVG DOM renderer. It has no SMIL/`<animate>` timeline engine; Skia's answer to
"animated vector content" is Skottie, not SkSVG. There is no timeline to seek. Rejected.

### 5.2 Skottie — the best *runtime* on this list, attached to the wrong *format*

Skottie is Skia's Lottie player, Google-maintained, shipping in Chrome and available via SkiaSharp,
React Native Skia, etc. Its API is the cleanest expression of exactly the property we need —
seeking and rendering are **separate operations**, and seeking is total:

```
seek(t)            // "Updates the animation state for |t|. @param t normalized [0..1]
                   //  frame selector (0 -> first frame, 1 -> final frame)"
seekFrame(t)       // "Update the animation state to match |t|, specified as a frame index"
seekFrameTime(t)   // "Update the animation state to match t, specified in frame time"
render(canvas, r)  // "Draws the current animation frame."
```

with the documented note that calling `render()` before any `seek()` is undefined behaviour — i.e.
the model has *no implicit current time*, which is precisely the stateless design we want. Skottie
also generally has better Lottie conformance than lottie-android and is the renderer other
implementations are diffed against.

Its limitation is inherited, not intrinsic: it plays **Lottie**, so §2.1's ceiling (no 3D, equal
-vertex-count interpolation, per-frame geometry blowup) applies unchanged. Skottie is the right
*engine architecture* married to the wrong *container*.

Cost of shipping Skia yourself: React Native Skia reports `librnskia.so` at ~3.8 MB and ~4 MB added
download per ABI via App Bundles (~41 MB if you ship a fat APK). That is acceptable but not free.

### 5.3 `android.graphics.Canvas` — the part people forget

**Android's 2D canvas *is* Skia.** Every device in our floor already ships a tuned, vendor-tested
Skia. `Canvas` gives us `drawPath`, `clipPath`, `saveLayer` (for alpha masking / mattes),
`LinearGradient`/`RadialGradient`/`SweepGradient` shaders, `PorterDuff` blend modes, `PathMeasure`
(for trim-path / stroke-on), `Matrix`, and anti-aliased fills and strokes — the complete primitive
set our content needs, callable from Kotlin, at **zero additional binary size**. This is what
lottie-android itself draws onto.

The honest caveat, which shapes the design: **hardware-accelerated path rendering on Android is not
free for dynamic geometry.** HWUI/Skia rasterise complex paths into a texture mask and upload it;
"animating or editing paths is costly because it requires re-tessellating the entire path," and very
large paths can exceed GPU texture-size limits (a real, reported failure mode — see
[mapcompose #85](https://github.com/p-lr/mapcompose/issues/85)). At our path counts, per-frame
re-tessellation of thousands of changing paths is *the* performance question regardless of which
option we choose — and note that it is a cost Lottie, Skottie and PAG all pay too, just hidden.
Rive's GPU renderer is the only candidate that structurally attacks it, and it pays for that with
GPU-only + driver risk. Practical mitigations belong to us either way: dirty-region redraw, caching
static sub-trees to layers, bucketing paths by whether their geometry actually changed at *t*, and
aggressive culling.

**Arbitrary-time evaluation:** trivially yes — there is no timeline at all. We evaluate our own IR at
*t* and issue draw calls. Seeking is whatever we design it to be.

---

## 6. Candidates not on the original list

### 6.1 PAG / libpag (Tencent) — the strongest omission, still a no

[`Tencent/libpag`](https://github.com/Tencent/libpag), Apache-2.0, Android 5.0+, is the most
credible Lottie alternative in production (WeChat/Tencent scale). Binary format, not JSON.

- **Expressiveness:** deliberately hybrid — "combines vector-based and raster-based exporting
  techniques to support **all** AE animations in a single file," including third-party plugin
  effects, by falling back to raster where vector export can't express something. That fallback is
  fatal for us: raster fallback is exactly the megabytes we are trying to escape.
- **Performance:** decodes "10 times faster than JSON" and files are "about 50% smaller"; vendor
  benchmarks claim 1.5–2.5× Lottie's real-time rendering throughput; recent releases cite large tgfx
  gains (10× basic shapes, 20× text). These are vendor numbers, but PAG's production pedigree makes
  them more credible than most marketing.
- **Arbitrary-time evaluation: ✅ full pass.** `PAGPlayer` exposes
  `void setProgress(double percent)` ("Sets the progress of play position, the value ranges from 0.0
  to 1.0") and `double getProgress()`, with `bool flush()` to "apply all pending changes to the
  target surface immediately." Set any progress, flush, get that frame.
- **Blocker: authoring.** PAG files are produced by the **PAGExporter After Effects plugin** on
  macOS/Windows. The runtime can *edit* existing files (swap text/images) but there is no supported
  programmatic path to author arbitrary vector content. Our server is Python + Manim in a container;
  it cannot drive After Effects. Same class of failure as Rive, and decisive.
- 3D: no. Glyph-by-glyph stroke-on: no native primitive.

### 6.2 SVGA — no

[`svga/SVGAPlayer-Android`](https://github.com/svga/SVGAPlayer-Android) draws via Android Canvas and
is maintained, but SVGA's model is Flash/sprite-derived: shapes plus **bitmap sprites with per-frame
transforms**. It is built for streaming-gift animations, not thousands of analytic Beziers, and it
leans on raster assets. Wrong shape of content.

### 6.3 Vello + Velato (Rust/linebender) — technically the most interesting, not shippable

Vello is a GPU-**compute**-centric 2D renderer; Velato is its Lottie front end. Vello "can currently
be considered in an **alpha** state" and "needs a GPU with support for compute shaders to run."
Velato "is working towards correctness, but there are missing features." Compute-shader dependency
is directly incompatible with a low-end Android floor, and alpha status is incompatible with
shipping. Revisit in two years.

### 6.4 SVG + SMIL via AndroidSVG — no

AndroidSVG is effectively unmaintained, SMIL support in the Android ecosystem is negligible, and
SMIL's declarative timeline does not cover our transform/geometry needs. Per-frame SVG dumps (the
`manim-svg-animations` approach) are a debugging aid, not a payload format.

### 6.5 WebView + our own JS/WASM renderer — viable fallback, not a recommendation

Shipping the IR plus a canvas/WebGL renderer in a WebView would give us one renderer across web and
Android. But it costs us the low-end performance floor (WebView startup, JS GC pauses, no
predictable frame budget) and control over scrubbing latency. Worth keeping as a *web* target for
the same IR; not the Android path.

---

## 7. Cross-cutting questions

### 7.1 Does anything handle 3D?

**No. Not one of them.**

| Candidate | 3D |
|---|---|
| Lottie / dotLottie | `ddd` flag and `CameraLayer` exist in schema; **not supported on Android**, flattened without perspective even on web |
| Rive | "essentially orthographic by design", view matrices 2D-only; GPU Canvas is new and renderer-gated |
| AnimatedVectorDrawable | none |
| Skottie | inherits Lottie's non-support |
| PAG | none (raster-bakes AE 3D at export) |
| SVGA | none |

Our 3D scenes with camera moves therefore require either (a) server-side flattening to 2D per frame
— which destroys the compression story, since a camera move changes every projected point every
frame — or (b) **an IR that carries 3D geometry plus a camera and projects on-device**. Only (b)
preserves the size win, and only a custom IR can do (b). **This requirement alone forces invention.**

### 7.2 Text / writing a formula stroke by stroke

The correct technique is format-independent: bake LaTeX to **glyph outlines** server-side (we are
already committed to no LaTeX on device), then animate a **path-length trim** per glyph, staggered.

- **Lottie/Skottie/ThorVG:** the primitive exists (Trim Paths), but lottie-android has an open bug
  where per-shape ("individually") trimming animates all shapes at once
  ([#2262](https://github.com/airbnb/lottie-android/issues/2262)) — the exact failure mode for
  writing a formula. Workaround is one shape group per glyph, which multiplies layer count and
  therefore per-frame cost.
- **rlottie:** text/glyphs/fonts marked unsupported; merge paths unsupported.
- **Rive:** runtime text exists but is layout-oriented; no per-glyph outline trim primitive.
- **PAG / SVGA / AVD:** no.
- **Custom IR + Canvas:** `PathMeasure.getSegment()` gives us exactly this, per glyph, with full
  control over stagger and per-stroke ordering. Straightforward.

---

## 8. Summary table

| | Arbitrary-time seek | Arbitrary Bezier geometry | Masks/clip | Gradients | High path counts on low-end | 3D | Per-glyph write-on | Programmatic authoring | Maintained |
|---|---|---|---|---|---|---|---|---|---|
| **Lottie / lottie-android** | ✅ true `setProgress` | ⚠️ equal-vertex-count rule | ✅ (slowest feature) | ✅ | ⚠️ SW by default; maintainers say avoid masks/mattes/merge | ❌ | ⚠️ trim-path bug | ✅ (JSON) | ✅ |
| **dotLottie / ThorVG** | ✅ `frame(float)` | same as Lottie | ✅ | ✅ | ⚠️ unknown at our scale | ❌ | ⚠️ | ✅ | ✅ (Android binding v0.5.0 ⚠️) |
| **rlottie** | ✅ `renderSync(frameNo)` | same | ⚠️ partial modes | ✅ | ⚠️ | ❌ | ❌ no text | ✅ | ❌ **archived** |
| **Skottie** | ✅✅ best API | same as Lottie | ✅ | ✅ | ⚠️ +4 MB binary | ❌ | ⚠️ | ✅ | ✅ |
| **Rive** | ⚠️ linear only; state machines forward-only | ✅ | ✅ | ✅ | ⚠️ GPU-only on Android now | ❌ | ❌ | ❌ editor-gated | ✅ |
| **AnimatedVectorDrawable** | ❌ **cannot seek** | ❌ | ⚠️ clip-path only | ⚠️ API 24+ | ❌ ~200×200dp guidance | ❌ | ❌ | ✅ (XML) | ✅ |
| **PAG / libpag** | ✅ `setProgress`+`flush` | ✅ | ✅ | ✅ | ✅ best vendor numbers | ❌ | ❌ | ❌ AE-plugin only | ✅ |
| **SkSVG** | ❌ no timeline | ✅ static | ✅ | ✅ | n/a | ❌ | n/a | ✅ | ✅ |
| **Vello / Velato** | ✅ | ✅ | ✅ | ✅ | ❌ needs compute shaders | ❌ | ⚠️ | ✅ | ⚠️ alpha |
| **Custom IR + `android.graphics.Canvas`** | ✅ by construction | ✅ | ✅ `saveLayer`/`clipPath` | ✅ | ⚠️ our problem to solve | ✅ if we design it | ✅ `PathMeasure` | ✅ | us |

---

## 9. Recommendation

### INVENT the IR. ADOPT the rasterizer (Skia, via `android.graphics.Canvas`).

**Why not adopt a format.** The candidates split into two groups and both fail:

- **Group A (Lottie, dotLottie, Skottie, ThorVG)** — seekable, open, authorable from Python, and
  therefore the only real temptation. They fail on *three* independent grounds: no 3D at all; the
  equal-vertex-count interpolation rule that forces a full geometry dump per frame for Manim's
  non-affine animations, destroying the kilobyte goal; and a feature set (masks, mattes, merge
  paths, per-glyph trim) that the maintainers' own docs and Telegram's production constraints
  identify as the stuff you must strip to survive on low-end Android.
- **Group B (Rive, PAG)** — better renderers, better binary formats, real seeking. Both are
  **editor-gated**: `.riv` is "exported from the Rive Editor" and `.pag` from an After Effects
  plugin. Neither offers a supported programmatic authoring API. Our exporter is a headless Python
  service; building it on a reverse-engineered writer for a vendor-controlled binary is a standing
  liability, and it is the single failure mode the ticket names — "impedance mismatch that only
  surfaces late, after we're committed."

The saving from adopting was supposed to be the *runtime*. We can capture most of that saving
without adopting the *format*, because **Skia is already on the device**. `android.graphics.Canvas`
gives us anti-aliased filled/stroked paths, `clipPath`, `saveLayer` masking, all three gradient
shaders, blend modes and `PathMeasure` — everything the content needs — at zero binary cost, on a
vendor-tested code path, with no GPU-driver bet.

### The design this implies

1. **Binary IR with random access as a first-class property.** Chunked timeline with periodic
   self-contained keyframes ("I-frames") plus deltas, and an index mapping *t* → nearest preceding
   I-frame. Seek cost is then bounded by chunk length, not by *t*. Bake this in from day one; it is
   the requirement that cannot be retrofitted.
2. **Two-tier encoding.** Affine-only motion (the common case: `shift`, `rotate`, `scale`,
   `FadeIn`) encodes as sparse transform keyframes — this is where the kilobytes come from. Genuine
   geometry change (`Transform` with re-pointed paths, updaters) encodes as delta-coded,
   quantised point arrays. Do not force everything into one representation; that is the mistake
   Lottie's model would impose on us.
3. **Carry 3D.** Ship 3D geometry plus camera keyframes and project on-device. Nothing else on this
   list can do this, and flattening server-side forfeits the compression win precisely when the
   camera moves.
4. **Steal, don't adopt.** Take Lottie's property/keyframe/interpolator model and Trim Paths
   concept; take Skottie's API shape (`seek(t)` strictly separated from `render()`, with no implicit
   current time). Implement `Write` via `PathMeasure.getSegment()`.
5. **Keep a Lottie export as a debug/interchange target**, not the wire format — useful for
   eyeballing scenes in standard tooling and for a future web player.

### Specific risks of choosing "invent"

| Risk | Severity | Mitigation |
|---|---|---|
| **Path throughput on low-end hardware.** Thousands of re-tessellated paths per frame may not fit 33 ms. This risk is *not avoided* by any candidate — Lottie/Skottie/PAG pay it too — but we now own it. | **High** | Prototype the worst real scene first, on the actual floor device, before IR design freezes. Dirty-region redraw; cache unchanged sub-trees to `Bitmap`/hardware layers; bucket by geometry-changed-at-*t*; cull off-screen; consider decimating Bezier detail by on-screen size. |
| **Fidelity drift vs Manim's Cairo/OpenGL output.** Two renderers, one reference. | **High** | Golden-image harness from day one: render N frames server-side and on-device, compare with a perceptual diff in CI. This is non-negotiable and is the main tax of inventing. |
| **Scope: we now own an exporter, a format, a spec, a renderer and its tooling.** | **High** | Version the IR from v1 with a capability/feature-flag header so the app can refuse or degrade unknown scenes. Keep the v1 feature set deliberately small; MP4 fallback for scenes the renderer declines. |
| **Android `clipPath` is aliased under hardware acceleration**; true anti-aliased masking needs `saveLayer`, which is expensive — the same cost that makes Lottie masks slow. | Medium | Prefer geometric clipping resolved at export (path intersection server-side, where CPU is cheap) over runtime masking wherever the mask is static. |
| **Very large single paths can exceed GPU texture-mask size limits.** | Medium | Split oversized paths at export; test explicitly with Cartopy coastline data, which is the likely trigger. |
| **No ecosystem tooling** — no LottieFiles preview, no designer handoff, no third-party debuggers. | Low | Build a small web player against the same IR (doubles as the web target) and a per-frame SVG dump for inspection. |
| **Scrub latency on cold seek** if chunking is too coarse. | Low | Tune I-frame interval empirically; target worst-case seek reconstruct well under one frame. |

**The one thing that would change this recommendation:** if 3D scenes were dropped from scope *and*
profiling showed that Manim's real content is overwhelmingly affine motion over stable point sets,
then Lottie-as-IR with **Skottie** as the runtime becomes genuinely defensible — it is the only
combination here with a mature, correct, properly stateless `seek`. That is worth measuring on our
actual scene corpus before committing, because it is the cheapest possible outcome. But the ticket
lists 3D camera moves as in scope, and that closes the door.

---

## Sources

- [Lottie Android performance guide (airbnb/lottie)](https://github.com/airbnb/lottie/blob/master/android.md)
- [Lottie supported features matrix](https://github.com/airbnb/lottie/blob/master/supported-features.md)
- [Lottie Specs — Properties (equal-point-count rule)](https://lottiefiles.github.io/lottie-docs/properties/)
- [lottie-android `LottieDrawable.java`](https://github.com/airbnb/lottie-android/blob/master/lottie/src/main/java/com/airbnb/lottie/LottieDrawable.java)
- [lottie-android #2262 — Trim Path individually broken](https://github.com/airbnb/lottie-android/issues/2262)
- [lottie-android #2402 — tracing all at once](https://github.com/airbnb/lottie-android/issues/2402)
- [lottie-android #591](https://github.com/airbnb/lottie-android/issues/591), [#1157](https://github.com/airbnb/lottie-android/issues/1157)
- [lottie-web 3D wiki](https://github.com/airbnb/lottie-web/wiki/3D), [lottie-web #2572](https://github.com/airbnb/lottie-web/issues/2572)
- [Telegram sticker requirements (TGS constraints)](https://core.telegram.org/stickers)
- [Samsung/rlottie — archived notice + feature table](https://github.com/Samsung/rlottie)
- [ThorVG `thorvg.h` — `Animation::frame(float)`](https://github.com/thorvg/thorvg/blob/main/inc/thorvg.h)
- [thorvg #4162 — fill effect mismatch lottie-web/skottie/thorvg](https://github.com/thorvg/thorvg/issues/4162)
- [LottieFiles/dotlottie-android](https://github.com/LottieFiles/dotlottie-android)
- [Skia `Skottie.h` — seek/seekFrame/seekFrameTime/render](https://github.com/google/skia/blob/main/modules/skottie/include/Skottie.h)
- [Skottie docs](https://skia.org/docs/user/modules/skottie/)
- [React Native Skia bundle size](https://shopify.github.io/react-native-skia/docs/getting-started/bundle-size/)
- [rive-app/rive-runtime](https://github.com/rive-app/rive-runtime) and `linear_animation_instance.hpp`
- [rive-android `RendererType.kt` — Canvas renderer deprecated](https://github.com/rive-app/rive-android/blob/master/kotlin/src/main/java/app/rive/runtime/kotlin/core/RendererType.kt)
- [rive-app/rive-code-generator-wip](https://github.com/rive-app/rive-code-generator-wip), [George-RD/rive-rs-cli](https://github.com/George-RD/rive-rs-cli)
- [Tencent/libpag](https://github.com/Tencent/libpag) and `include/pag/pag.h` (`PAGPlayer::setProgress`/`flush`)
- [Android `AnimatedVectorDrawable` reference](https://developer.android.com/reference/android/graphics/drawable/AnimatedVectorDrawable)
- [Understanding Android's VectorDrawable (Nick Butcher)](https://medium.com/androiddevelopers/understanding-androids-vector-image-format-vectordrawable-ab09e41d5c68)
- [Android hardware acceleration docs](https://developer.android.com/topic/performance/hardware-accel)
- [mapcompose #85 — large path exceeds texture size limit](https://github.com/p-lr/mapcompose/issues/85)
- [svga/SVGAPlayer-Android](https://github.com/svga/SVGAPlayer-Android)
- [Vello](https://lib.rs/crates/vello), [Velato](https://lib.rs/crates/velato)
- [MathItYT/manim-svg-animations](https://github.com/MathItYT/manim-svg-animations)
