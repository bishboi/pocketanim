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
| LaTeX (optional) | typeset maths (`MathTex`, `Tex`, axis numbers); without it they are drawn as plain Unicode text | `brew install --cask mactex-no-gui` | `sudo apt install texlive texlive-latex-extra dvisvgm` |

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
| Fonts | The styles' Google Fonts: Playfair, Poppins, EB Garamond, Cinzel and others. | `~/.fonts` (Linux), `~/Library/Fonts` (macOS) | 10 MB |

These folders are not in git, so each machine downloads them once.

Other pictures are fetched per lecture, as needed, and cached:
- **Illustrations and diagrams** come from the sources that suit the subject. These are OpenStax textbook figures, NASA, The Met, the Smithsonian, Wikimedia Commons and Openverse, and, last, an AI illustration. See `harness/lecture/README.md`. To add NIH BioArt or Servier Medical Art, download their images into a folder under `harness/lecture/data/illustrations/`.
- **Photos** come from Wikimedia Commons, reusable licences only. For a named person, movement, event, monument or place, the picture its Wikipedia article leads with is used. They are cached in `harness/lecture/.cache/images`.
- **Molecules** not in the built-in table are looked up on PubChem. They are cached in `harness/lecture/.cache/molecules.json`.
- **PDF figures** come from your uploaded PDF.

## 3. The web app

```sh
cd harness/app
npm install
cp .env.example .env.local
npm run dev                       # http://localhost:3000
```

Put your keys in `.env.local`. All of them are optional.

| Key | What it does |
|---|---|
| `GOOGLE_TTS_API_KEY` | The narration voice: Google's **Chirp 3 HD**. An API key from a Google Cloud project with the *Cloud Text-to-Speech API* enabled (console.cloud.google.com → APIs & Services → enable "Cloud Text-to-Speech API" → Credentials → Create credentials → API key). Or set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account JSON file and `pip install google-auth`. It is the only narration voice: without it a lecture stops with that reason (`PANIM_VOICE=silent` builds one without narration). |
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
| `PANIM_PACE=brisk` | Faster lectures: normal voice speed and shorter pauses. The default, `relaxed`, is a slower teaching pace with time to take each line in. |
| `PANIM_AI_ILLUSTRATIONS=0` | No AI illustrations. With `OPENROUTER_API_KEY` set, an image model draws one when no library has a picture; `PANIM_IMAGE_MODEL` picks the model and `PANIM_AI_MAX` (6) caps them per lecture. |

## 4. Check that everything is in place

The bar at the top of every page shows the version and the commit, for example `v0.6.0 · 264831d · <branch>`. It also
lists anything still missing, each with a **download** button:

- **Voice: Google Chirp 3 HD** means narration is ready. Without `GOOGLE_TTS_API_KEY` it says so, and lectures do not build.
- **Illustrations** says whether internet pictures are on (Wikimedia Commons and Openverse).
- **Towns** means small places may not be found.

The app also downloads the voice by itself before the first lecture that needs it.

## Troubleshooting

| You see | Cause | Fix |
|---|---|---|
| Text boxes where illustrations should be | No internet access to Wikimedia Commons or Openverse, or `PANIM_IMAGES=0` | allow the hosts below; check `images.py --illustrations "water cycle"` |
| `Narration is spoken by Google Chirp 3 HD, and no Google credentials are set` | No key | put `GOOGLE_TTS_API_KEY` in `harness/app/.env.local` and restart the app |
| `Google Chirp 3 HD could not speak ...` | Google refused the request: the key is wrong, or the Cloud Text-to-Speech API is not enabled for its project | the dev server log shows Google's message; try `.venv/bin/python harness/lecture/chirp.py "Hello." hello.wav` |
| `KeyError: no place named 'X'` | The gazetteer is missing, or the name is spelt differently | `fetch_gazetteer.py` |
| `ModuleNotFoundError: manim` | The app is not using `.venv` | rerun `setup-python.sh` |
| An equation looks plain | No LaTeX | install LaTeX (optional) |
| `FileNotFoundError: [Errno 2] No such file or directory: 'latex'` | A scene uses `MathTex`, `Tex` or axis numbers, LaTeX is not installed, and the scene was run without the harness's fallback (plain `manim render`, or an older checkout) | update to this version: the app and Forge draw these as plain text without LaTeX; for your own runs use `.venv/bin/python harness/scripts/manim_render.py render ...` instead of `manim render ...`. Or install LaTeX (above) for real typesetting |
| A download fails with 403 or a timeout | A firewall or proxy blocks the host | allow `download.geonames.org` (towns), `github.com` (voice, fonts), `naturalearth.s3.amazonaws.com` (maps), `commons.wikimedia.org`, `upload.wikimedia.org`, `en.wikipedia.org`, `hi.wikipedia.org` and `api.openverse.org`, `images-api.nasa.gov`, `images-assets.nasa.gov`, `collectionapi.metmuseum.org`, `images.metmuseum.org`, `api.si.edu`, `ids.si.edu`, `raw.githubusercontent.com` (photos and illustrations), `texttospeech.googleapis.com` (the Chirp voice) |
