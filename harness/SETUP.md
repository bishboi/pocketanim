# Running the harness locally

This guide covers everything a lecture needs on your own machine: the Python environment, the downloaded
libraries (illustrations, icons, place names, voice, maps, fonts) and the optional keys.

## 1. Tools to install first

| Tool | Why | macOS | Ubuntu / Debian |
|---|---|---|---|
| Python 3.11+ | Manim and the lecture engine | `brew install python@3.13` | `sudo apt install python3.12 python3.12-venv` |
| Node.js 20+ | the web app | `brew install node` | from nodejs.org, or `nvm install 20` |
| ffmpeg | the video, the audio mix | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Cairo and Pango | Manim draws text and shapes with them | `brew install cairo pango pkg-config` | `sudo apt install libcairo2-dev libpango1.0-dev pkg-config` |
| espeak-ng (optional) | a fallback voice when Kokoro can't run | `brew install espeak-ng` | `sudo apt install espeak-ng` |
| LaTeX (optional) | typeset equations; without it they are drawn in plain Unicode | `brew install --cask basictex` | `sudo apt install texlive-latex-extra` |

On Windows, use WSL (Ubuntu) and follow the Ubuntu column.

## 2. Python environment and every library, in one step

From the repository root:

```sh
harness/scripts/setup-python.sh
```

The script:
- creates `.venv`;
- installs `harness/requirements.txt` (Manim, Cartopy, RDKit, kokoro-onnx and the rest);
- runs `fetch_all.py`, which downloads the libraries below.

It takes a few minutes and about 475 MB the first time. Run it again whenever you like: anything already
downloaded is skipped.

To fetch the libraries again, or only some of them:

```sh
.venv/bin/python harness/scripts/fetch_all.py                 # all of them; ends with a ready/FAILED table
.venv/bin/python harness/scripts/fetch_all.py --skip voice    # leave one out
.venv/bin/python harness/scripts/fetch_icons.py               # or one at a time
.venv/bin/python harness/scripts/fetch_gazetteer.py
.venv/bin/python harness/scripts/fetch_voice.py
```

| Library | What it gives a lecture | Where it goes | Size |
|---|---|---|---|
| Icons | About 45,000 SVGs, colour first: Fluent Emoji, Twemoji, Streamline Emojis, Noto, EmojiOne, OpenMoji, Firefox emoji and Meteocons. Silhouettes (game-icons, Material Design Icons, Health Icons) are the fallback. They are used for **illustrations**, icons on maps, and panel icons. `PANIM_ICON_FAMILY` picks the family that comes first. | `harness/lecture/data/icons/` | 75 MB |
| Gazetteer | GeoNames, about 150,000 towns, so markers find small places (Lakhimpur Kheri, Prayagraj). | `harness/lecture/data/geonames/` | 10 MB |
| Voice | Kokoro-82M, the narration voice, and the `kokoro-onnx` package. | `harness/models/` | 350 MB |
| Maps | Natural Earth borders, states, rivers and towns. | Cartopy's data folder (`~/.local/share/cartopy`) | 40 MB |
| Fonts | The styles' Google Fonts: Playfair, Poppins, EB Garamond, Cinzel and others. | `~/.fonts` (Linux), `~/Library/Fonts` (macOS) | 10 MB |

These folders are not in git, so each machine downloads them once.

Other pictures are fetched per lecture, as needed, and cached:
- **Photos** come from Wikimedia Commons, reusable licences only. They are cached in `harness/lecture/.cache/images`.
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
| `OPENROUTER_API_KEY` | Lectures are written by a model. Without it, the app uses an offline test script. |
| `OPENROUTER_MODEL` | Which model writes them. |
| `DATALAB_API_KEY` | Clean PDF conversion, with figures cut out properly. Without it, pypdf is used. |
| `PANIM_IMAGES=0` | Turn off internet photos. |
| `PANIM_ICON_FAMILY` | The icon family to prefer, e.g. `twemoji`, or `fluent-emoji` for shaded 3-D emoji (`fetch_icons.py --sets fluent-emoji`). |

## 4. Check that everything is in place

The bar at the top of every page shows the version and the commit, for example `v0.6.0 · 264831d · <branch>`. It also
lists anything still missing, each with a **download** button:

- **Voice: Kokoro-82M** means narration is ready.
- **Icons: NONE** means lectures would show text instead of illustrations.
- **Towns** means small places may not be found.

The app also downloads the icons and the voice by itself before the first lecture that needs them. The log
says so ("Downloading the icon library…").

## Troubleshooting

| You see | Cause | Fix |
|---|---|---|
| Text boxes where illustrations should be | The icon library isn't downloaded | `fetch_icons.py`, or the download button next to Icons |
| A silent video | No voice installed | `fetch_voice.py`, or the button next to Voice |
| `KeyError: no place named 'X'` | The gazetteer is missing, or the name is spelt differently | `fetch_gazetteer.py` |
| `ModuleNotFoundError: manim` | The app is not using `.venv` | rerun `setup-python.sh` |
| An equation looks plain | No LaTeX | install LaTeX (optional) |
| A download fails with 403 or a timeout | A firewall or proxy blocks the host | allow `registry.npmjs.org` (icons), `download.geonames.org` (towns), `github.com` (voice, fonts), `naturalearth.s3.amazonaws.com` (maps) |
