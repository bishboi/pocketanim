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
| Diagram drawings | SVG drawings (a tree, a deer, a factory) that diagram nodes, definitions and comparisons draw things with. They are never a lecture's picture. | `harness/lecture/data/icons/` | 75 MB |
| Textbook figures | An index of the figures in OpenStax's CC BY textbooks (add `--non-commercial` to `fetch_openstax.py` for the CC BY-NC-SA ones, and set `PANIM_ALLOW_NC=1` to use them). | `harness/lecture/data/illustrations/` | <1 MB |
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

Other pictures are fetched per lecture, as needed, and cached:
- **Illustrations and diagrams** come from the sources that suit the subject. These are OpenStax textbook figures, NASA, The Met, the Smithsonian, Wikimedia Commons and Openverse, and, last, an AI illustration. See `harness/lecture/README.md`. To add NIH BioArt or Servier Medical Art, download their images into a folder under `harness/lecture/data/illustrations/`.
- **Photos** come from Wikimedia Commons, reusable licences only. For a named person, movement, event, monument or place, the picture its Wikipedia article leads with is used. They are cached in `harness/lecture/.cache/images`.
- **Molecules** not in the built-in table are looked up on PubChem. They are cached in `harness/lecture/.cache/molecules.json`.
- **PDF figures** come from your uploaded PDF.

## 3. The narration voice: Gemini 3.8 Flash TTS

Every lecture is spoken by **Gemini 3.8 Flash TTS**, Google's speech model on the Gemini API. It reads a
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
| `PANIM_TTS_MODEL` | `gemini-3.8-flash-tts` (default), or `gemini-3.8-flash-lite-tts`: cheaper and faster, a little less expressive. |
| `PANIM_TTS_VOICE` | The speaker. `Achird` by default, for every style; any other Gemini prebuilt voice (`Charon`, `Kore`, `Aoede`, `Puck`...) instead. |
| `PANIM_TTS_THREADS` | How many lines are spoken at once before Manim draws the lecture (default 8). Lower it if Google answers "429: Resource exhausted" often; raise it on a paid tier. |
| `PANIM_TTS_STYLE` | How to read, as an instruction to the speech model (`teacher` for a warm, patient teacher). Off by default: `gemini-3.8-flash-tts` refuses instructions ("Developer instruction is not enabled for this model"), and the harness then stops sending it. |

**The older voice, Chirp 3 HD.** `PANIM_TTS=chirp` goes back to Google Cloud's Chirp 3 HD voices, through the
Cloud Text-to-Speech API. It needs that API enabled in a Google Cloud project and one of: your gcloud login
(`gcloud auth application-default login`, then `gcloud auth application-default set-quota-project
YOUR_PROJECT_ID`), a service account (`GOOGLE_APPLICATION_CREDENTIALS=/path/key.json`), or an API key
(`GOOGLE_TTS_API_KEY`) where the project allows keys. `.venv/bin/python harness/lecture/chirp.py --check` checks it.

## 4. The web app

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
| `OPENROUTER_MODEL` | Which model writes them. |
| `PANIM_MODEL_WAIT_MINUTES` | How long a model may send nothing at all before the request is stopped (default 15). Reasoning models think silently first; a "pro" model can take many minutes, so pick a non-pro model for lectures. |
| `PANIM_REASONING_EFFORT` | How hard the model thinks before writing: `low` (the default: quicker and cheaper), `minimal`, `medium` or `high`; `off` leaves it to the model. Used by the editor and by Forge. |
| `DATALAB_API_KEY` | Clean PDF conversion, with figures cut out properly. Without it, pypdf is used. |
| `PANIM_IMAGES=0` | Turn off internet photos and illustrations. |
| `SMITHSONIAN_API_KEY` | A free api.data.gov key for Smithsonian pictures (history). Without it the rate-limited `DEMO_KEY` is used. |
| `PANIM_ALLOW_NC=1` | Also use non-commercial collections (most OpenStax books). Only for non-commercial lectures. |
| `PANIM_PACE` | The teaching pace. `slow` (the default): voice at 0.85, 1.4 s after each line, 2.8 s between paragraphs, 7 s to think about a question. `relaxed`: a little quicker. `brisk`: normal voice speed and short pauses. |
| `PANIM_AI_ILLUSTRATIONS=0` | No AI illustrations. With `OPENROUTER_API_KEY` set, an image model draws one when no library has a picture; `PANIM_IMAGE_MODEL` picks the model and `PANIM_AI_MAX` (6) caps them per lecture. |

## 5. Check that everything is in place

The bar at the top of every page shows the version and the commit, for example `v0.6.0 · 264831d · <branch>`. It also
lists anything still missing, each with a **download** button:

- **Voice: Gemini 3.8 Flash TTS** means narration is ready. Without `GEMINI_API_KEY` (section 3) it says so, and lectures do not build.
- **Illustrations** says whether internet pictures are on (Wikimedia Commons and Openverse).
- **Towns** means small places may not be found.
- **LaTeX** says whether equations are typeset; **download** installs TinyTeX (a few minutes). What is ready shows
  as a green tick (hover **LaTeX ✓** to see where it was found). When LaTeX is found but a part is missing (usually
  `dvisvgm`, which TinyTeX does not include), the bar names it, and **download** adds it.

The app also downloads the voice by itself before the first lecture that needs it.

## Troubleshooting

| You see | Cause | Fix |
|---|---|---|
| Text boxes where illustrations should be | No internet access to Wikimedia Commons or Openverse, or `PANIM_IMAGES=0` | allow the hosts below; check `images.py --illustrations "water cycle"` |
| `Narration is spoken by Gemini 3.8 Flash TTS, and no Gemini API key is set` | No key | section 3, then restart the app |
| `403: ... requires a quota project, which is not set by default` | Your login has no quota project (a new login drops it) | `gcloud auth application-default set-quota-project YOUR_PROJECT_ID`, or `GOOGLE_CLOUD_QUOTA_PROJECT=YOUR_PROJECT_ID` in `.env.local`; `chirp.py --check` shows what is used |
| `401: API keys are not supported by this API` | The project refuses API keys for Text-to-Speech | sign in with `gcloud auth application-default login` and `set-quota-project` (section 3); the key can stay, a login is used first |
| `Gemini 3.8 Flash TTS could not speak ...` | Google refused the request: the key is wrong, or its quota ran out | the page shows Google's message; try `.venv/bin/python harness/lecture/gemini_tts.py --check` |
| `KeyError: no place named 'X'` | The gazetteer is missing, or the name is spelt differently | `fetch_gazetteer.py` |
| `ModuleNotFoundError: manim` | The app is not using `.venv` | rerun `setup-python.sh` |
| An equation looks plain, or reads `mathbf F rm ext` | No LaTeX, or the app cannot find it | `.venv/bin/python harness/scripts/fetch_latex.py`, then restart the app; the bar at the top says **LaTeX** when it is found |
| Pictures, labels or text on top of each other in a lecture | a layout bug | `.venv/bin/python harness/scripts/lecture_audit.py <build>/scene.py GeneratedScene audit/ --frames` lists every overlap, beat by beat, with a picture of each beat's end (`audit/sheet00.png`...) |
| `FileNotFoundError: [Errno 2] No such file or directory: 'latex'` | A scene uses `MathTex`, `Tex` or axis numbers, LaTeX is not installed, and the scene was run without the harness's fallback (plain `manim render`, or an older checkout) | update to this version: the app and Forge draw these as plain text without LaTeX; for your own runs use `.venv/bin/python harness/scripts/manim_render.py render ...` instead of `manim render ...`. Or install LaTeX (above) for real typesetting |
| A download fails with 403 or a timeout | A firewall or proxy blocks the host | allow `download.geonames.org` (towns), `github.com` (voice, fonts), `naturalearth.s3.amazonaws.com` (maps), `commons.wikimedia.org`, `upload.wikimedia.org`, `en.wikipedia.org`, `hi.wikipedia.org` and `api.openverse.org`, `images-api.nasa.gov`, `images-assets.nasa.gov`, `collectionapi.metmuseum.org`, `images.metmuseum.org`, `api.si.edu`, `ids.si.edu`, `raw.githubusercontent.com` (photos and illustrations), `generativelanguage.googleapis.com` (the Gemini voice; `texttospeech.googleapis.com` for Chirp), `yihui.org`, `tlnet.yihui.org` and `mirror.ctan.org` (TinyTeX and its packages) |
