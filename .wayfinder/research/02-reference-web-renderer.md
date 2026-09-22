---
ticket: 2
title: What the reference project does for web rendering
labels: [wayfinder:research]
state: answered
---

# `yu314-coder/manim_app` as a web-rendering reference

## Headline

**The repo was reached and read in full. It is not a web renderer, and there is
no web in it.** It is a Windows **desktop application** — a PyWebView native
window pointed at a local `index.html` — that shells out to the `manim` CLI and
plays the resulting MP4 from the local filesystem. There is no HTTP server, no
browser, no client/server split, no streaming, and no queue.

For the decision this ticket unblocks — *how our preview reaches the browser* —
the reference **offers no transport to copy**. Its transport is "copy the file
into the web root so the local page can `<video src>` it", which only exists
because a webview's CSP blocks `file:///`. That has no analogue in a Next.js app
talking to a remote worker.

Confidence: **high** on everything in the "Established" section — it is read
directly from source at a pinned commit. The "Inferred" section is marked
separately. One thing I could not establish is flagged at the end.

**Provenance.** Cloned from `https://github.com/yu314-coder/manim_app.git`,
branch `main`, commit `ca73becc4f6b5a0d8da13ffbe2d2a5aa4258d8e8`
("Merge branch 'man'", 2026-07-30). Line numbers below are that commit's.
Repo shape: ~370 KB `app.py`, ~200 KB `ai_edit.py`, and a `web/` directory that
is mostly a vendored Monaco editor and xterm.js.

---

## The five questions

### 1. How does Manim output get into a browser?

**Server-rendered video — except there is no server.** A file on disk, copied to
where the local page can read it. Established from source; high confidence.

The chain, end to end:

1. `manim` is invoked as a **subprocess** with a temp `.py` file, the scene name,
   a quality flag and `--media_dir` (`app.py:3040-3080`, `_build_manim_cmd`).
   Output is an MP4 written to disk by Manim itself.
2. The backend copies that MP4 into `~/.manim_studio/assets/`, then again to
   `~/.manim_studio/preview/latest_preview.mp4` (`app.py:3900-3935`).
3. The backend pushes the **path** to the frontend by injecting JavaScript into
   the webview: `window.evaluate_js('window.previewCompleted("<path>")')`
   (`app.py:3946-3957`).
4. The frontend calls back into Python over the PyWebView bridge —
   `pywebview.api.get_asset_as_data_url(filePath)` (`web/renderer_desktop.js:1596`).
   Despite the name, **this returns no data URL.** It copies the MP4 a third time
   into `web/temp_assets/` and returns the relative string `temp_assets/<name>.mp4`
   (`app.py:5529-5630`). The function is docstring'd `DEPRECATED` yet is the live
   preview path.
5. The frontend sets `previewVideo.src = 'temp_assets/X.mp4?_=<timestamp>'` and
   calls `.load()` (`web/renderer_desktop.js:1683-1694`). The cache-buster is
   needed because the filename is reused across renders.

**Why the copy exists**, stated outright in a source comment at `app.py:4437-4441`:

> `file://` URLs are blocked by the webview's CSP, so we copy the rendered MP4
> into `web/temp_assets/` and return an HTTP-served relative path (same pattern
> the main preview pipeline uses).

Note the comment says "HTTP-served", but the window is created with
`url=html_path` — a **local file path**, not a URL (`app.py:7892-7905`). There is
no `http_server=True` and no Flask/FastAPI anywhere; `app.py`'s imports are
`webview`, `os`, `subprocess`, `threading`, `socket` and friends (`app.py:6-52`).
The relative path resolves against the local HTML document. The comment is
inaccurate about its own mechanism.

Two other minor transports, for completeness:
- **Still images** take a different route: `get_asset_as_bytes` → base64 → `atob`
  → `Uint8Array` → `Blob` → `URL.createObjectURL` (`renderer_desktop.js:1608-1638`).
  Only images; explicitly avoided for video, commented as "no size limits".
- The **asset browser modal** does use raw `file:///` (`renderer_desktop.js:2276-2285`),
  which per the CSP comment above presumably does not work.

**Not** WASM, **not** streamed frames, **not** a re-implementation. No TypeScript
renderer, no canvas drawing of scene content, no frame protocol.

### 2. Where does Manim run, and what does it need installed?

Locally, in a managed virtualenv, on the user's own machine. Established; high confidence.

- Venv at `~/.manim_studio/venvs/manim_studio_default` (`app.py:70`), populated by
  an in-app setup wizard running `pip install manim manim-fonts basedpyright`
  (`app.py:1008`).
- Invoked as `<venv>/Scripts/manim.exe` (or `bin/manim`), falling back to
  `python -m manim` (`app.py:3048-3058`).
- **LaTeX is a system dependency, not pip-installed.** The README tells users to
  install MiKTeX or TeX Live themselves and restart the app (README:465-473);
  the app only *detects* it and shows a status indicator.
- ffmpeg is required for the multi-scene concat and render-farm paths.
- Quality presets map to Manim's own flags: `-ql` (480p/15fps) through `-qk` (4K/8K)
  (`app.py:1226-1234`).
- Platform badge in the README is **Windows** only, and the code is full of
  `os.name == 'nt'` branches, though most paths have POSIX fallbacks.

This is the same "real Manim, real Python, real LaTeX" constraint our map already
records for `dsl/export_dsl.py`. The reference does not dodge it — it installs
into a venv on the user's desktop and reminds them to install LaTeX.

### 3. What does it do about the wait?

**It does not block the UI, but it has no queue and no real progress.**
Established; high confidence.

- **Fire-and-forget + callback.** The API call starts a `threading.Thread` and
  returns `{'status': 'started'}` immediately (`app.py:3976-3982`). Completion
  arrives later as an injected JS call: `window.previewCompleted(path)` /
  `window.renderCompleted(...)` / `window.previewFailed(msg)`
  (`app.py:3946-3965`). The JS comment at `renderer_desktop.js:1171-1173`
  confirms this contract.
- **Progress is log tailing, not a percentage.** Manim's stdout is read
  line-by-line and pushed to a console pane, coalesced into roughly one
  `evaluate_js` per 100 ms (~10 Hz) to avoid flooding the bridge
  (`app.py:1258-1310`, `app.py:2852`). I searched for percentage/ETA parsing of
  Manim's progress bars and **found none** — no `renderProgress`, no percent
  regex. The user reads Manim's own log lines and a spinner.
- **No job queue. One job at a time.** Concurrency control is two booleans,
  `app_state['is_rendering']` and `is_previewing`, with a stuck-flag recovery
  hack (`app.py:1173-1174`, `2448-2467`). A second render is refused, not queued.
  `render_farm.py`'s own docstring says "one active farm job at a time".
- **Cancellation exists**: `stop_render()` kills the whole process tree
  (`kill_process_tree`), so ffmpeg and LaTeX children die too (`app.py:3995-4020`).
  Worth stealing conceptually — a half-killed Manim leaves ffmpeg orphans.
- A defensive **20-minute timeout** wraps the completion promise in the batch
  loop so it cannot deadlock (`renderer_desktop.js:1174`).

Three genuine latency techniques, all reducing *render* time rather than hiding it:

1. **Low-quality preview preset** — `-ql` at 480p/15fps for iteration, separate
   from the export quality (`app.py:1226-1234`). The obvious move, and it is the
   main one.
2. **Manim's own caching left on by default**, with a user setting to disable
   (`app.py:3073-3080`).
3. **`render_farm.py` — the one architecturally interesting file.** It AST-parses
   `construct()`, splits the scene at `self.wait()` boundaries, synthesises a
   separate scene file per fragment, renders them in parallel subprocesses
   (`workers = cpu_count // 2`, gated by a `threading.Semaphore`), and stitches
   with the ffmpeg concat demuxer (`render_farm.py:1-30, 412-480`). It bails out
   to single-process rendering when parallelism would be unsafe or pointless —
   `ValueTracker` present, cross-fragment attribute references, `narrate()` in
   use, no `wait()` boundaries, single fragment, or GPU renderer
   (`render_farm.py:63-75`). Progress is a module-level `STATE` dict polled by
   the frontend via `farm_status()`.

### 4. Is any of it reusable for a preview that must not persist an MP4?

**The transport itself: no. It is the exact inverse of our constraint.**
Established; high confidence.

A single preview writes the MP4 to disk **four times**:

| # | Location | Source |
|---|---|---|
| 1 | Manim's own `--media_dir` output | `app.py:3040-3080` |
| 2 | `~/.manim_studio/assets/<name>.mp4` | `app.py:3900-3912` |
| 3 | `~/.manim_studio/preview/latest_preview.mp4` | `app.py:3915-3922` |
| 4 | `web/temp_assets/<name>.mp4` | `app.py:5529-5560` |

Copies 1-3 are deleted in `cleanup_on_exit()` **when the app closes cleanly** —
preview files tracked in `preview_files_to_cleanup` are removed, `temp_` folders
under `MEDIA_DIR` are pruned, and `PREVIEW_DIR` is emptied wholesale. So the
intent is "preview files are temporary". But they persist for the entire session,
and the durability is only as good as a clean shutdown.

Two notes on that, both from source:
- The console message printed right after the copies says
  `"Files will persist after app closes"` (`app.py:3931`), which **contradicts**
  the cleanup code. One of the two is stale. Not a claim about behaviour so much
  as a warning that this code's comments are not reliable.
- **I found no cleanup of `web/temp_assets/` anywhere** — every reference to it
  is a write (`app.py:4446, 4465, 5529-5560`), none in `cleanup_on_exit`. It is
  in `.gitignore`, which suggests it is known to accumulate. Copy #4, the one the
  player actually reads, appears to be the one that is never swept.

**What *is* transferable**, as patterns rather than code:

- **The async job contract.** Start returns immediately with a job handle;
  completion is pushed, not polled; failure is a separate channel. This maps
  cleanly onto our worker → harness relationship, with the caveat that their
  push channel is `evaluate_js` into a local webview, which for us becomes SSE,
  a websocket, or Supabase Realtime.
- **Log streaming as the progress surface**, coalesced to ~10 Hz. Cheap, honest,
  and it gives the user something to read during a minutes-long wait. Worth
  considering precisely *because* Manim does not expose a usable completion
  percentage — the reference tried and settled for the log.
- **Process-tree kill on cancel.** A correctness detail we would otherwise
  discover the hard way.
- **The render-farm split.** If our preview latency becomes the binding
  constraint, AST-splitting at `wait()` boundaries and rendering fragments in
  parallel is a real idea with a worked implementation — including its list of
  conditions under which it is unsafe, which is the expensive part to rediscover.
  Note it produces MP4 fragments to concat, so adopting it for a
  no-MP4-at-rest preview would mean re-targeting its output.
- **A negative lesson.** Their whole `temp_assets` dance exists to satisfy a
  webview CSP. A real browser hitting a real origin does not have this problem —
  we can stream bytes from a route and never name a file. The reference's
  contortion is an artefact of being a desktop app, and copying it would be
  cargo-culting.

Against the map's settled position ("preview is server-rendered frames for now"):
the reference does **not** validate it, because the reference does not render
frames. It renders whole MP4s at low quality and plays them. The only place it
touches individual frames is `web/renderer_desktop.js:5046-5084`, which
screenshots the **already-rendered video element** onto a `<canvas>` via
`drawImage` and ships the PNG back to Python — that is how AI Agent Mode's
"visual QA" gets its frames. Frames are derived from the video, never a
substitute for it. So our frames-based preview is something we would be
inventing, not borrowing.

### 5. What is its licence?

**MIT.** `LICENSE` at the repo root is the standard MIT text, and the README
carries an MIT badge.

One wrinkle worth knowing before any code is lifted: the copyright line reads
`Copyright (c) 2025` — **the holder's name is blank**. The grant is intact and
MIT is permissive, so attribution-with-the-repo-URL would be the practical
course, but the notice is malformed.

---

## Could not establish

- **Whether the project has ever run as a hosted/browser application.** I read
  the pinned commit only; I did not review release history, branches or issues.
  Everything at this commit is desktop-only. If someone cited it as a *web*
  renderer, I found no basis for that in the code, but I cannot rule out a claim
  made about some other branch or an earlier version.
- **Why it was cited for web rendering.** Possible that "Monaco + HTML UI +
  `<video>` tag" read as web from the README's screenshots. That is a guess, not
  a finding.
- **Whether `web/temp_assets/` is cleaned up by anything.** I found no such code,
  but `app.py` is 370 KB and I searched by string rather than reading it entire.
  Stated as "found no cleanup", not "there is none".

## Bottom line for the map

The reference does not beat what we would have invented, because it is not
solving our problem. It is a single-user desktop tool whose "web" is a local
HTML shell; its preview transport is a filesystem copy that our no-MP4 constraint
forbids outright.

What it does supply is a sanity check on **cost**: even a purpose-built desktop
Manim IDE, with a local venv and no network hop, treats a render as a
fire-and-forget background job with a log tail and no progress bar, and its main
latency answer is "render at 480p/15fps instead". If our preview budget assumes
better than that from a remote worker, the assumption needs an argument.

The one piece worth a second look is `render_farm.py`, and it belongs to a later
conversation about latency, not to the transport decision this ticket unblocks.
