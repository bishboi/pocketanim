# Running the harness locally

This guide covers everything a lecture needs on your own machine: the Python environment, the downloaded
libraries (place names, voice, maps, fonts), the online picture sources and the optional keys.

## 1. Tools to install first

| Tool | Why | macOS | Ubuntu / Debian |
|---|---|---|---|
| Python 3.11+ | Manim and the lecture engine | `brew install python@3.13` | `sudo apt install python3.12 python3.12-venv` |
| Node.js 20+ | the web app | `brew install node` | from nodejs.org, or `nvm install 20` |
| ffmpeg | the video, the audio mix | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Cairo and Pango | Manim draws text and shapes with them | `brew install cairo pango pkg-config` | `sudo apt install libcairo2-dev libpango1.0-dev pkg-config` |
| LaTeX (recommended) | typeset equations (`MathTex`, `Tex`, axis numbers); without it they are drawn as plain Unicode text. `fetch_latex.py` (section 2) installs TinyTeX for you | `.venv/bin/python harness/scripts/fetch_latex.py`, or `brew install --cask mactex-no-gui` | the same script, or `sudo apt install texlive texlive-latex-extra texlive-xetex dvisvgm` |

On Windows, use WSL (Ubuntu) and follow the Ubuntu column.

## 2. Python environment and every library, in one step

From the repository root:

```sh
harness/scripts/setup-python.sh
```

The script:
- creates `.venv`;
- installs `harness/requirements.txt` (Manim, Cartopy, RDKit and the rest);
- runs `fetch_all.py`, which downloads the libraries below.

It takes a few minutes and about 400 MB the first time. Run it again whenever you like: anything already
downloaded is skipped.

To fetch the libraries again, or only some of them:

```sh
.venv/bin/python harness/scripts/fetch_all.py                 # all of them; ends with a ready/FAILED table
.venv/bin/python harness/scripts/fetch_all.py --skip maps     # leave one out
.venv/bin/python harness/scripts/fetch_gazetteer.py
```

| Library | What it gives a lecture | Where it goes | Size |
|---|---|---|---|
| Gazetteer | GeoNames, about 150,000 towns, so markers find small places (Lakhimpur Kheri, Prayagraj). | `harness/lecture/data/geonames/` | 10 MB |
| Maps | Natural Earth borders, states, rivers and towns. | Cartopy's data folder (`~/.local/share/cartopy`) | 40 MB |
| Fonts | The styles' Google Fonts: Playfair, Poppins, EB Garamond, Cinzel and others, and Hind for Hindi in equations. | `~/.fonts` (Linux), `~/Library/Fonts` (macOS) | 10 MB |
| LaTeX | TinyTeX (a small TeX Live) with the packages Manim uses, for typeset equations; XeLaTeX in it typesets formulas with Hindi words. Skipped when LaTeX is already installed (MacTeX, TeX Live); then only missing packages are added. | `~/Library/TinyTeX` (macOS), `~/.TinyTeX` (Linux) | 250 MB |

These folders are not in git, so each machine downloads them once.

LaTeX on its own, and a check that it typesets (a plain formula, and one with Hindi):

```sh
.venv/bin/python harness/scripts/fetch_latex.py            # install TinyTeX if LaTeX is missing, then check
.venv/bin/python harness/scripts/fetch_latex.py --check
```

The harness finds TinyTeX, MacTeX and TeX Live even when they are not on the app's PATH. Maths a model writes
with Unicode (μ, θ, ², →) is turned into TeX first; a formula with Hindi in it (`\text{फिसलन होगी}`) goes to
XeLaTeX with a Devanagari font (Noto Sans Devanagari, Hind, Poppins, or macOS's Kohinoor); a formula that
will not compile is drawn as text rather than stopping the lecture (`harness/lecture/nolatex.py`).

Pictures are not downloaded from anywhere. Each one is made in one of three ways, chosen by the lecture writer:
built in Manim, drawn as an SVG, or made by an image model (`OPENROUTER_API_KEY`; `PANIM_IMAGE_MODEL`, default
`google/gemini-2.5-flash-image`) as a borderless cutout traced into vector shapes. See
`harness/lecture/README.md`. Made pictures are cached in `harness/lecture/.cache/images`.
- **Molecules** not in the built-in table are looked up on PubChem. They are cached in `harness/lecture/.cache/molecules.json`.
- **PDF figures** come from your uploaded PDF.

## 3. The narration voice: Gemini 3.8 Flash-Lite TTS

Every lecture is spoken by **Gemini 3.8 Flash-Lite TTS**, Google's speech model on the Gemini API. It reads a
Hinglish line in one go, Hindi and English together, like one teacher talking. It needs one key:

1. Create a Gemini API key in Google AI Studio: aistudio.google.com/apikey.
2. Put it in `harness/app/.env.local`:
   ```sh
   GEMINI_API_KEY=your-key
   ```
3. Restart the app.

To check the key and speak one test line: `.venv/bin/python harness/lecture/gemini_tts.py --check`. To try the
voice on its own: `.venv/bin/python harness/lecture/gemini_tts.py "नमस्ते, आज हम गति के नियम समझेंगे।" hello.wav`

Settings (all optional, in `.env.local`):

| Variable | What it does |
|---|---|
| `PANIM_TTS_MODEL` | `gemini-3.8-flash-lite-tts` (default): fast and cheap, for the hundreds of lines a lecture has. Or `gemini-3.8-flash-tts`: a little more expressive, slower and dearer. |
| `PANIM_TTS_VOICE` | The speaker. `Achird` by default, for every style; any other Gemini prebuilt voice (`Charon`, `Kore`, `Aoede`, `Puck`...) instead. |
| `PANIM_TTS_PRICE` | The voice's price in US dollars per million tokens, `in,out` (text in, audio out), for the cost shown in the agent log. Default: Google's list price, Flash-Lite TTS $0.50 / $6.00 and Flash TTS $0.50 / $9.00 until 31 December 2026, double from 1 January 2027. Set it for the batch tier (half) or priority (1.8×). |
| `PANIM_TTS_THREADS` | How many lines are spoken at once before Manim draws the lecture (default 8). Lower it if Google answers "429: Resource exhausted" often; raise it on a paid tier. |
| `PANIM_TRANSCRIPT_PARALLEL` | How many transcript sections are written at once (default 6, at most 8; lower it if the provider answers 429, too many requests). One after another, a book chapter's transcript took most of an hour. |
| `PANIM_STALL_SECONDS` | A reply (transcript or video) that streams nothing for this long after it started (default 180) has stalled: it is stopped and asked again. One that sends nothing at all is stopped after `PANIM_MODEL_WAIT_MINUTES` (15). A section that fails every try is left out, with a note, rather than stopping the lecture (unless more than about one in seven fail). |
| `PANIM_CHAPTERS_PARALLEL` | How many transcript sections have their video chapters written at once (default: `PANIM_TRANSCRIPT_PARALLEL`, else 6; at most 8). Each section's chapters are a request of their own, checked on their own, then put together and checked as a whole; a section the whole check still faults (transcript not all said, a chapter that does not compile, nothing written) is written again, in parallel, with the reasons; only what belongs to no section (the count of problems or questions, the length) is fixed with `add_chapters`, at most 3 chapters a call. After 4 refusals of the finished lecture, its chapters are built as they are. A turn that goes silent or stalls is asked again (twice), and if the model still does not answer, the chapters already written are built rather than lost. |
| `PANIM_NARRATION_KBPS` | The narration's bitrate in the phone's files (Save, Download for the phone): Opus, mono, 24 kbit/s by default, about 11 MB an hour where the WAV was 300 MB (and over the 50 MB per-file upload limit of a free Supabase project). Needs ffmpeg with an Opus encoder; without one the WAV is shipped. The browser preview keeps the WAV. |
| `PANIM_MANIM_CACHE` | Where every build keeps Manim's LaTeX and text renders (default `harness/.cache/manim`). They used to go in each build's own folder, so every build ran LaTeX again for every formula. The server fills it as it starts (`scripts/warm_caches.py`, from `app/instrumentation.ts`: Manim and the engine imported, the common formulas and each style's fonts drawn), so the first build does not pay for that; `PANIM_WARM=0` turns the warm-up off. |
| `PANIM_MANIM_CHECK` | `off` skips running a lecture's free-form Manim blocks (the `manim` op) before they are accepted; the sandbox's rules still apply. By default each block is run once in a probe scene and its verdict cached by its code. |
| `PANIM_MANIM_CHECK_SECONDS` | How long that probe may run (default 240). |
| `PANIM_MICRO_MINUTES` | The length a micro-lecture aims for (default 25, so 20-30 min). A lecture longer than the top of that range is planned, before its transcript is written, as a series of micro-lectures, one per topic (`lib/topics.ts`): its sections grouped, cutting at the book's headings where it can, a book's questions kept with their teaching. Each lecture's first section opens it (what it covers, what came before, what the student will be able to do), its last closes it (key points, self-check questions, what comes next), and the video is cut there, each part with its own title card and recap. The editor shows them as Lecture 1, Lecture 2... of one version. |
| `PANIM_MAX_VIDEO_MINUTES` | For a lecture without a topic plan (no transcript): the longest single video (default: the top of the micro-lecture range, 30). A longer one is cut between chapters into the fewest parts under it. |
| `PANIM_TTS_LANGUAGE` | The accent. `auto` (default) speaks every line with an Indian language code: a line with Hindi in it as `hi-IN`, an all-English line as `en-IN` (Indian English), so no line comes out in an American accent. Or one code for every line (`hi-IN`, `en-IN`), or `none` to let the model guess from the words. Changing it speaks the lines again. |
| `PANIM_TTS_STYLE` | How to read, as an instruction to the speech model (`teacher` for a warm, patient teacher). Off by default: the Gemini 3.8 TTS models refuse instructions ("Developer instruction is not enabled for this model"), and the harness then stops sending it. |

**The older voice, Chirp 3 HD.** `PANIM_TTS=chirp` goes back to Google Cloud's Chirp 3 HD voices, through the
Cloud Text-to-Speech API. It needs that API enabled in a Google Cloud project and one of: your gcloud login
(`gcloud auth application-default login`, then `gcloud auth application-default set-quota-project
YOUR_PROJECT_ID`), a service account (`GOOGLE_APPLICATION_CREDENTIALS=/path/key.json`), or an API key
(`GOOGLE_TTS_API_KEY`) where the project allows keys. `.venv/bin/python harness/lecture/chirp.py --check` checks it.

## 4. Pictures: Manim, SVG drawings, or the image model

There are no picture libraries, icons or emoji to download, and nothing is searched for on the web. A lecture's
pictures are built in Manim (diagrams, graphs, sketches, the map), drawn as SVGs by the SVG model
(`OPENROUTER_SVG_MODEL`), or made by the image model (`PANIM_IMAGE_MODEL`) as cutouts: the subject alone, no
border or background, traced into vector shapes so the phone plays them at tier 1. A book's photograph is made
again the same way. `.venv/bin/python harness/lecture/genimage.py "a steam locomotive, side view"` makes one and
prints where it went. `PANIM_IMAGES=0` turns the image model off.

## 5. The web app

```sh
cd harness/app
npm install
cp .env.example .env.local
npm run dev                       # http://localhost:3000
```

Put your keys in `.env.local`. All of them are optional.

| Key | What it does |
|---|---|
| `GOOGLE_TTS_API_KEY` | An API key for the narration voice, where the project allows keys; a gcloud login or `GOOGLE_APPLICATION_CREDENTIALS` is used first (section 3). |
| `GOOGLE_CLOUD_QUOTA_PROJECT` | The project a gcloud login's voice calls are billed to, if `set-quota-project` was not run. |
| `PANIM_CHIRP_VOICE` | One Chirp 3 HD voice for every style (`Charon`, `Kore`, `Aoede`, `Puck`, `Orus`, `Leda`, `Fenrir`...); each style has its own otherwise. |
| `PANIM_CHIRP_LANG` | The accent English lines are spoken in: `en-US` (default), `en-IN`, `en-GB`. A line with Hindi in it is split into language runs, each sent with its own language code: Devanagari as `hi-IN`, English words in it as `en-IN`, by the same speaker (`harness/lecture/chirp.py`, `runs`). Units in a Hindi line are said in Hindi (प्रतिशत, मीटर प्रति सेकंड). |
| `OPENROUTER_API_KEY` | Lectures are written by a model. Without it, the app uses an offline test script. |
| `OPENROUTER_MODEL` | Which model writes the video: the beat script, its diagrams and the Manim scene. |
| `OPENROUTER_TRANSCRIPT_MODEL` | Which model writes a lecture's spoken transcript first (what the teacher says, section by section). Defaults to `OPENROUTER_MODEL`. The page's **Transcript model** field overrides it for your browser. |
| `PANIM_MODEL_WAIT_MINUTES` | How long a model may send nothing at all before the request is stopped (default 15). Reasoning models think silently first; a "pro" model can take many minutes, so pick a non-pro model for lectures. |
| `PANIM_REASONING_EFFORT` | How hard the model thinks before writing: `low` (the default: quicker and cheaper), `minimal`, `medium` or `high`; `off` leaves it to the model. Used by the editor and by Forge. |
| `DATALAB_API_KEY` | Clean PDF conversion, with figures cut out properly. Without it, pypdf is used. |
| `PANIM_IMAGES=0` | Turn off internet photos and illustrations. |
| `SMITHSONIAN_API_KEY` | A free api.data.gov key for Smithsonian pictures (history). Without it the rate-limited `DEMO_KEY` is used. |
| `PANIM_ALLOW_NC=1` | Also use non-commercial collections (most OpenStax books). Only for non-commercial lectures. |
| `PANIM_PACE` | The teaching pace. The voice speaks at its own (1×) speed in every pace; the pace is the pauses. `slow` (the default): 1.4 s after each line, 2.8 s between paragraphs, 7 s to think about a question. `relaxed`: shorter pauses. `brisk`: short pauses. |
| `PANIM_AI_ILLUSTRATIONS=0` | No AI illustrations. With `OPENROUTER_API_KEY` set, an image model draws one when no library has a picture; `PANIM_IMAGE_MODEL` picks the model and `PANIM_AI_MAX` (6) caps them per lecture. |

### How a long lecture is made quickly

- **Cut by time before a word is written.** The sections are sized from the time estimate and grouped into
  micro-lectures of 20-30 min (`lib/topics.ts`) first; the transcript is written in that order, so the first
  micro-lecture's transcript is done first.
- **Each micro-lecture is finished on its own.** Each section's scenes (video chapters) are asked for as soon as
  its transcript is written. When every section of a micro-lecture has its scenes, that micro-lecture is put
  together, checked as a lecture of its own (its transcript all said, its ops compiling, its book questions asked,
  its figures built), its faulty sections written again in parallel, and sent to the page, which builds it while
  the next micro-lectures are still being written. A series is never checked or fixed as one long lecture and cut
  afterwards: those fix-up turns carried the whole lecture each time and were the slowest part.
- **Beats name the transcript's lines.** The video's model sees each section as numbered lines (`12| ...`) and
  writes `{"lines": [12, 13], "do": [...]}` instead of copying the sentences out (`lib/lines.ts`). A line no beat
  names is said on a beat of its own; a chapter too thin to stand is merged into its neighbour.
- **Each request carries only its own part.** The transcript's system prompt is an outline of the sections, the same
  for every section's request (cached by the provider; marked for caching on Anthropic and Google models); each
  request adds its own slice of the book or reference. A section's video request carries its numbered lines, its own
  book questions and the figures its text marks.
- **Mended, not rewritten.** A transcript section refused for being short, or for a missing question or example, is
  sent back with "add only the new paragraphs"; headings, bullet marks and [stage directions] are taken out rather
  than refused. A section's chapters refused once for ops that will not compile have those beats' ops left out on
  the next try instead (the beat is said over the picture before it).
- **Three builds at once.** The page builds a series' micro-lectures three at a time.

## 6. Check that everything is in place

The bar at the top of every page shows the version and the commit, for example `v0.6.0 · 264831d · <branch>`. It also
lists anything still missing, each with a **download** button:

- **Voice: Gemini 3.8 Flash-Lite TTS** means narration is ready. Without `GEMINI_API_KEY` (section 3) it says so, and lectures do not build.
- **Pictures** says whether the image model can make pictures (`OPENROUTER_API_KEY`, and `PANIM_IMAGES` not 0).
- **Towns** means small places may not be found.
- **LaTeX** says whether equations are typeset; **download** installs TinyTeX (a few minutes). What is ready shows
  as a green tick (hover **LaTeX ✓** to see where it was found). When LaTeX is found but a part is missing (usually
  `dvisvgm`, which TinyTeX does not include), the bar names it, and **download** adds it.

The app also downloads the voice by itself before the first lecture that needs it.

## Troubleshooting

| You see | Cause | Fix |
|---|---|---|
| Words where a picture should be | No `OPENROUTER_API_KEY`, `PANIM_IMAGES=0`, or the image model refused | check `.venv/bin/python harness/lecture/genimage.py "water cycle"` |
| `Narration is spoken by Gemini 3.8 Flash-Lite TTS, and no Gemini API key is set` | No key | section 3, then restart the app |
| `403: ... requires a quota project, which is not set by default` | Your login has no quota project (a new login drops it) | `gcloud auth application-default set-quota-project YOUR_PROJECT_ID`, or `GOOGLE_CLOUD_QUOTA_PROJECT=YOUR_PROJECT_ID` in `.env.local`; `chirp.py --check` shows what is used |
| `401: API keys are not supported by this API` | The project refuses API keys for Text-to-Speech | sign in with `gcloud auth application-default login` and `set-quota-project` (section 3); the key can stay, a login is used first |
| `Gemini 3.8 Flash-Lite TTS could not speak ...` | Google refused the request: the key is wrong, or its quota ran out | the page shows Google's message; try `.venv/bin/python harness/lecture/gemini_tts.py --check` |
| `KeyError: no place named 'X'` | The gazetteer is missing, or the name is spelt differently | `fetch_gazetteer.py` |
| `ModuleNotFoundError: manim` | The app is not using `.venv` | rerun `setup-python.sh` |
| An equation looks plain, or reads `mathbf F rm ext` | No LaTeX, or the app cannot find it | `.venv/bin/python harness/scripts/fetch_latex.py`, then restart the app; the bar at the top says **LaTeX** when it is found |
| Pictures, labels or text on top of each other in a lecture | a layout bug | `.venv/bin/python harness/scripts/lecture_audit.py <build>/scene.py GeneratedScene audit/ --frames` lists every overlap, beat by beat, with a picture of each beat's end (`audit/sheet00.png`...) |
| `FileNotFoundError: [Errno 2] No such file or directory: 'latex'` | A scene uses `MathTex`, `Tex` or axis numbers, LaTeX is not installed, and the scene was run without the harness's fallback (plain `manim render`, or an older checkout) | update to this version: the app and Forge draw these as plain text without LaTeX; for your own runs use `.venv/bin/python harness/scripts/manim_render.py render ...` instead of `manim render ...`. Or install LaTeX (above) for real typesetting |
| A download fails with 403 or a timeout | A firewall or proxy blocks the host | allow `download.geonames.org` (towns), `github.com` (voice, fonts), `naturalearth.s3.amazonaws.com` (maps), `commons.wikimedia.org`, `upload.wikimedia.org`, `en.wikipedia.org`, `hi.wikipedia.org` and `api.openverse.org`, `images-api.nasa.gov`, `images-assets.nasa.gov`, `collectionapi.metmuseum.org`, `images.metmuseum.org`, `api.si.edu`, `ids.si.edu`, `raw.githubusercontent.com` (photos and illustrations), `generativelanguage.googleapis.com` (the Gemini voice; `texttospeech.googleapis.com` for Chirp), `yihui.org`, `tlnet.yihui.org` and `mirror.ctan.org` (TinyTeX and its packages) |
