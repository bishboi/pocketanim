"""pocket_lecture: narrated, captioned, map-animated lectures that play on the phone.

The engine from the map-lecture guide -- beats, captions, a fact panel, chapter
cards, maps that draw themselves, five visual styles -- rebuilt so that every
picture it makes exports at tier 1. That rules out two things the original
scripts leaned on:

* **Images.** A background texture or a Cartopy raster is an ImageMobject, and
  the program has no way to carry pixels. Textures here are drawn as a handful
  of vector shapes (a grid, fibres, a board frame) baked once into one asset.
* **Per-letter typing.** AddTextLetterByLetter has no verb. The blueprint
  style writes its text on instead.

Everything else is ordinary Manim, so a scene written against this module
renders in Manim exactly as it exports: the harness previews the program, the
phone plays the program, and `manim` renders the same file to video.

A scene picks its style before importing, and then uses the API:

    import os
    os.environ.setdefault("LECTURE_STYLE", "vox")
    from pocket_lecture import *

    class GeneratedScene(MapLecture):
        REGION = dict(country="India")
        SECTIONS = ["Introduction", "Rivers"]

        def construct(self):
            self.chapter(1, "Rivers", "Two families", "Chapter one. The rivers.")
            self.show_map()
            self.beat("The Ganga is India's longest river.",
                      self.panel_title("Rivers"), self.river("Ganges"),
                      self.big_stat("2,525 km", "Ganga: longest river"))
            self.outro_fade()

Narration: each beat's line is spoken by espeak-ng when it is installed (or by
Kokoro with PANIM_VOICE=kokoro:<voice>), and its measured length times the
beat. With neither, or with PANIM_VOICE=silent, the length is estimated from
the word count and the picture still plays.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import wave
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from manim import *  # noqa: F401,F403 -- the scene file re-exports Manim through this module
from manim import (
    BOLD, DOWN, LEFT, NORMAL, ORIGIN, PI, RIGHT, UL, UP, AnimationGroup, Circle, Create,
    DashedVMobject, Dot, FadeIn, FadeOut, GrowFromCenter, GrowFromEdge, Indicate, LaggedStart,
    Line, Rectangle, RoundedRectangle, Scene, Square, SurroundingRectangle, Text, Triangle,
    VGroup, VMobject, Write, config,
)

HERE = Path(__file__).resolve().parent

# ════════════════════════════════════════════════════════════════════════
#  STYLES
# ════════════════════════════════════════════════════════════════════════

_DARK = dict(SAND="#E3B25A", DUNE="#C9793A", TERRA="#B5523B", RUST="#8E3B2E", TEAL="#3FB8AF",
             RIVER="#5AB4F0", GREEN="#86B86A", OLIVE="#6E8B3D", CREAM="#F4E9D8", MUTED="#8A93A6",
             ROSE="#E06C75", GOLD="#F2C14E", VIOLET="#A78BFA", HI="#FFFFFF", MOUNT="#C9D3E0")
_INK = dict(SAND="#C8870E", DUNE="#B5652A", TERRA="#A2412B", RUST="#7E2F22", TEAL="#1F7F78",
            RIVER="#1F6FB2", GREEN="#4E7F2F", OLIVE="#5B6E2A", CREAM="#161616", MUTED="#6B665C",
            ROSE="#C0392B", GOLD="#A87700", VIOLET="#6D4BC2", HI="#111111", MOUNT="#8E9AAB")

THEMES: dict[str, dict] = {
    "atlas": dict(
        label="Atlas", pal=_DARK, bg="#0D1117", texture="vignette",
        sans="Poppins", serif="Playfair Display", upper=False, title_col="#E3B25A",
        panel="#141A23", panel_style="solid", cap_bg="#05070A", cap_fg="#F4E9D8", cap_op=0.78,
        nb_fill="#171C24", nb_stroke="#2E3848", nb_hi="#2A1F26", st_stroke="#3A4658", st_hi="#5A6A80",
        track="#222A36", anim="fade", voice="bf_emma",
    ),
    "vox": dict(
        label="Vox", pal=_INK, bg="#EFE8DA", texture="paper",
        sans="Libre Franklin", serif="Oswald", upper=True, title_col="#111111", highlight="#FFD02F",
        panel="#EFE8DA", panel_style="rule", cap_bg="#111111", cap_fg="#FFFFFF", cap_op=0.92,
        nb_fill="#DCD3C2", nb_stroke="#BFB5A2", nb_hi="#F3C9B8", st_stroke="#B3A994", st_hi="#8C8472",
        track="#D6CDBB", anim="fade", land="#FBF8F1", voice="af_bella",
    ),
    "cardboard": dict(
        label="Cardboard", pal=dict(_INK, CREAM="#2B1D10", MUTED="#5E4631", SAND="#B8741F", HI="#2B1D10"),
        bg="#B98A57", texture="kraft", sans="Patrick Hand", serif="Permanent Marker", upper=False,
        title_col="#2B1D10", panel="#F3E6C8", panel_style="note", cap_bg="#F3E6C8", cap_fg="#2B1D10",
        cap_op=0.97, nb_fill="#A57B4B", nb_stroke="#86613A", nb_hi="#C49A6A", st_stroke="#B99468",
        st_hi="#8C6A45", track="#9E7446", anim="drop", land="#EAD6AA", shadow=0.075, voice="am_michael",
    ),
    "whiteboard": dict(
        label="Whiteboard",
        pal=dict(_INK, SAND="#D9730D", RIVER="#1565C0", TEAL="#00897B", GREEN="#2E7D32", ROSE="#C62828",
                 GOLD="#B26A00", VIOLET="#6A1B9A", CREAM="#1B1B1B", MUTED="#5F6368", HI="#1B1B1B"),
        bg="#F7F7F3", texture="board", sans="Kalam", serif="Kalam", upper=False, title_col="#1565C0",
        panel="#F7F7F3", panel_style="marker", cap_bg="#FFFFFF", cap_fg="#1B1B1B", cap_op=0.9,
        nb_fill="#ECECE6", nb_stroke="#C9C9C0", nb_hi="#F6D5D5", st_stroke="#BDBDB5", st_hi="#8F8F87",
        track="#E0E0DA", anim="write", map_stroke="#1B1B1B", jitter=0.012, voice="am_adam",
    ),
    "blueprint": dict(
        label="Blueprint",
        pal=dict(_DARK, SAND="#FFD166", RIVER="#8ECAFF", TEAL="#7FE0D0", GREEN="#A6E3A1", ROSE="#FF8FA3",
                 GOLD="#FFD166", VIOLET="#C3B1FF", CREAM="#EAF2FF", MUTED="#9FB8D9", HI="#FFFFFF",
                 MOUNT="#DDE8F7"),
        bg="#0E3A66", texture="grid", sans="IBM Plex Mono", serif="IBM Plex Mono", upper=True,
        title_col="#FFFFFF", panel="#0E3A66", panel_style="dashed", cap_bg="#0A2C4E", cap_fg="#EAF2FF",
        cap_op=0.88, nb_fill="#0C3359", nb_stroke="#3B77AE", nb_hi="#1B4F80", st_stroke="#3F7DB5",
        st_hi="#8ECAFF", track="#1D5285", anim="type", map_stroke="#FFFFFF", voice="am_eric",
    ),
    "chalkboard": dict(
        label="Chalkboard",
        pal=dict(_DARK, SAND="#F2E27A", CREAM="#F4F0E4", MUTED="#B9C8BE", RIVER="#9FD4E0", TEAL="#9FE0C8",
                 GREEN="#C5E1A5", GOLD="#F2E27A", ROSE="#F4A6A6", HI="#FFFFFF", MOUNT="#E6EEE8"),
        bg="#1B3A2F", texture="chalk", sans="Kalam", serif="Kalam", upper=False, title_col="#F2E27A",
        panel="#1B3A2F", panel_style="marker", cap_bg="#12291F", cap_fg="#F4F0E4", cap_op=0.85,
        nb_fill="#224536", nb_stroke="#3E6B58", nb_hi="#2E5A47", st_stroke="#4F7D69", st_hi="#9FC7B5",
        track="#2E5243", anim="write", map_stroke="#F4F0E4", jitter=0.01, voice="am_michael",
    ),
    # History: an old page. Brown ink, a serif for reading, capitals for titles.
    "parchment": dict(
        label="Parchment",
        pal=dict(_INK, SAND="#8C5A2B", DUNE="#9C6B3A", TERRA="#8E3B2E", CREAM="#3B2A1A", MUTED="#7A6650",
                 GOLD="#A0781E", ROSE="#8E2C23", RIVER="#2F5D7C", TEAL="#3E6E63", GREEN="#566B2E",
                 HI="#2A1B0E", VIOLET="#5D3A6E", MOUNT="#8A7A62"),
        bg="#EFE3C6", texture="parchment", sans="EB Garamond", serif="Cinzel", upper=False,
        title_col="#6B2E1A", panel="#E9DBB8", panel_style="rule", cap_bg="#3B2A1A", cap_fg="#F6EEDC",
        cap_op=0.9, nb_fill="#E2D3AE", nb_stroke="#C2AE85", nb_hi="#E9C9A8", st_stroke="#B8A47C",
        st_hi="#8C7650", track="#D8C79F", anim="fade", land="#F6ECD4", map_stroke="#5A4128", voice="bm_george",
    ),
    # Biology and chemistry: a clean bench. White, teal, a sans throughout.
    "lab": dict(
        label="Lab",
        pal=dict(_INK, SAND="#0F8B8D", DUNE="#E07A5F", TERRA="#C8553D", CREAM="#12303A", MUTED="#5B7480",
                 GOLD="#E8A33D", ROSE="#D1495B", RIVER="#2E86AB", TEAL="#0F8B8D", GREEN="#43A047",
                 HI="#0B1F26", VIOLET="#7B61FF", MOUNT="#90A4AE"),
        bg="#F4F8F8", texture="dots", sans="Poppins", serif="Poppins", upper=False,
        title_col="#0F8B8D", panel="#FFFFFF", panel_style="solid", cap_bg="#12303A", cap_fg="#FFFFFF",
        cap_op=0.92, nb_fill="#E3ECEC", nb_stroke="#C5D3D3", nb_hi="#D6EEEE", st_stroke="#C5D3D3",
        st_hi="#8FAFB0", track="#DCE6E6", anim="fade", land="#FFFFFF", map_stroke="#12303A", voice="af_sarah",
    ),
    # Physics and space: a night sky. Cyan light on deep blue.
    "cosmos": dict(
        label="Cosmos",
        pal=dict(_DARK, SAND="#7DD3FC", DUNE="#F9A8D4", TERRA="#FB923C", CREAM="#E6ECFF", MUTED="#8B95B8",
                 GOLD="#FDE68A", ROSE="#F472B6", RIVER="#60A5FA", TEAL="#5EEAD4", GREEN="#86EFAC",
                 HI="#FFFFFF", VIOLET="#C4B5FD", MOUNT="#A5B4FC"),
        bg="#0A0E1F", texture="stars", sans="Poppins", serif="Poppins", upper=True,
        title_col="#7DD3FC", panel="#0F1530", panel_style="solid", cap_bg="#05070F", cap_fg="#E6ECFF",
        cap_op=0.85, nb_fill="#121836", nb_stroke="#2A3566", nb_hi="#1E2750", st_stroke="#2F3B70",
        st_hi="#6D7BC4", track="#1B2350", anim="fade", map_stroke="#A5B4FC", voice="am_adam",
    ),
}

# Fonts the styles name. Missing ones fall back through Pango; the glyphs are
# baked at export, so the phone shows whatever the exporting machine drew.
FONTS = {
    "PlayfairDisplay.ttf": "ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf",
    "Poppins-Regular.ttf": "ofl/poppins/Poppins-Regular.ttf",
    "Poppins-Bold.ttf": "ofl/poppins/Poppins-Bold.ttf",
    "Kalam-Regular.ttf": "ofl/kalam/Kalam-Regular.ttf",
    "Kalam-Bold.ttf": "ofl/kalam/Kalam-Bold.ttf",
    "PatrickHand-Regular.ttf": "ofl/patrickhand/PatrickHand-Regular.ttf",
    "PermanentMarker-Regular.ttf": "apache/permanentmarker/PermanentMarker-Regular.ttf",
    "Oswald[wght].ttf": "ofl/oswald/Oswald%5Bwght%5D.ttf",
    "EBGaramond[wght].ttf": "ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf",
    "Cinzel[wght].ttf": "ofl/cinzel/Cinzel%5Bwght%5D.ttf",
    "LibreFranklin[wght].ttf": "ofl/librefranklin/LibreFranklin%5Bwght%5D.ttf",
    "IBMPlexMono-Regular.ttf": "ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
    "IBMPlexMono-Bold.ttf": "ofl/ibmplexmono/IBMPlexMono-Bold.ttf",
}


def setup_fonts() -> None:
    """Download the styles' Google Fonts once. Offline is not an error."""
    import urllib.request

    folder = Path.home() / ("Library/Fonts" if sys.platform == "darwin" else ".fonts")
    fetched = False
    for name, rel in FONTS.items():
        dest = folder / name
        if dest.exists():
            continue
        for base in ("https://raw.githubusercontent.com/google/fonts/main/",
                     "https://github.com/google/fonts/raw/main/"):
            try:
                folder.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(base + rel, dest)
                fetched = True
                break
            except Exception:  # noqa: BLE001 -- a font is a nicety
                continue
    if fetched and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class _Palette(SimpleNamespace):
    """The current style's colours, read at call time.

    Python binds default arguments when a function is defined, so a palette
    copied into module constants goes stale the moment a scene switches
    style. Every helper here reads P at call time instead.
    """


P = _Palette()
TH: dict = {}
STYLE = ""


# Semantic roles. A script says `tone: enemy`, never a colour; each style
# decides what enemy looks like. These defaults read a role off the palette,
# and a style pack may set any of them outright.
ROLE_DEFAULTS = {
    "ink": "CREAM", "muted": "MUTED", "accent": "SAND", "highlight": "GOLD",
    "friendly": "RIVER", "enemy": "ROSE", "ally": "GREEN", "neutral": "MUTED",
    "water": "RIVER", "land": "SAND",
}
ROLES = tuple(ROLE_DEFAULTS)


def role(name: str) -> str:
    """The current style's colour for a semantic role (or a palette key, or #hex)."""
    if isinstance(name, str) and name.startswith("#"):
        return name
    value = getattr(P, f"role_{name}", None) or getattr(P, str(name).upper(), None)
    if value is None:
        raise KeyError(f"no role or colour named {name!r}")
    return value


def register_style(name: str, theme: dict) -> None:
    """Add a style resolved elsewhere -- a Lecture Forge style pack -- to THEMES.

    `theme` has the THEMES keys, plus optional `base` (a THEMES entry to start
    from) and `roles` (semantic role -> #hex).
    """
    base = dict(THEMES.get(theme.get("base", "atlas"), THEMES["atlas"]))
    pal = dict(base["pal"])
    pal.update(theme.get("pal") or {})
    merged = {**base, **{k: v for k, v in theme.items() if k not in ("pal", "base")}, "pal": pal}
    THEMES[name] = merged


def use_style(name: str) -> dict:
    """Switch every colour, font and treatment to one entry of THEMES."""
    global TH, STYLE
    if name not in THEMES:
        raise KeyError(f"unknown style {name!r}; one of {', '.join(THEMES)}")
    STYLE = name
    TH = THEMES[name]
    for key, value in TH["pal"].items():
        setattr(P, key, value)
    P.BG = TH["bg"]
    P.PANEL = TH["panel"]
    P.TITLE = TH["title_col"]
    roles = TH.get("roles") or {}
    for key, source in ROLE_DEFAULTS.items():
        setattr(P, f"role_{key}", roles.get(key) or TH["pal"].get(source) or TH["pal"]["CREAM"])
    if TH.get("land") and "land" not in roles:
        P.role_land = TH["land"]
    config.background_color = TH["bg"]
    return TH


use_style(os.environ.get("LECTURE_STYLE", "atlas"))

# ════════════════════════════════════════════════════════════════════════
#  TEXT
# ════════════════════════════════════════════════════════════════════════


# Scripts whose glyphs combine (a vowel sign on a consonant, a conjunct):
# Pango rounds glyph positions to whole units at small sizes, which pulls
# these clusters apart, so such text is laid out large and scaled down.
COMPLEX_SCRIPTS = ((0x0900, 0x0DFF), (0x0600, 0x06FF), (0x0E00, 0x0E7F))
LAYOUT_SIZE = 48


def _complex(text: str) -> bool:
    return any(lo <= ord(c) <= hi for c in text for lo, hi in COMPLEX_SCRIPTS)


def T(text: str, size: float = 24, color: str | None = None, font: str | None = None,
      weight=NORMAL, **kw) -> Text:
    """Text in the style's body font. Characters a font lacks are swapped."""
    font = font or TH["sans"]
    if font == "Permanent Marker":
        text = text.replace("≈", "~")
    if size < LAYOUT_SIZE and _complex(text):
        mob = Text(text, font=font, font_size=LAYOUT_SIZE, color=color or P.CREAM, weight=weight, **kw)
        return mob.scale(size / LAYOUT_SIZE)
    return Text(text, font=font, font_size=size, color=color or P.CREAM, weight=weight, **kw)


def tok(name: str, default: float) -> float:
    """A style token -- a size a style pack may retune without code."""
    return float((TH.get("tokens") or {}).get(name, default))


# Icons a scene drew, for the credits line (their sets' licences ask for it).
USED_ICONS: set[str] = set()


def icon_mob(name: str, color: str | None = None, height: float = 0.5):
    """An icon from the downloaded sets (icons.py) as a vector mobject.

    A single-colour icon is filled with `color` (a role, palette name or #hex;
    the style's accent by default); a colour emoji keeps its own colours.
    """
    import icons

    icon_id = icons.resolve(name)
    if icon_id is None:
        hint = "" if icons.available() else " (run harness/scripts/fetch_icons.py)"
        raise KeyError(f"no icon for {name!r}{hint}")
    fill = role(color or "accent") if icons.is_mono(icon_id) else None
    mob = SVGMobject(str(icons.svg_file(icon_id, fill)), height=height, stroke_width=0)
    USED_ICONS.add(icon_id)
    return mob


def wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width)) or text


def fit(mob, width: float):
    """Shrink, never grow, to a width. Wide fonts overflow the panel otherwise."""
    if mob.width > width:
        mob.scale_to_fit_width(width)
    return mob


# ════════════════════════════════════════════════════════════════════════
#  NARRATION
# ════════════════════════════════════════════════════════════════════════

# Respellings for the voice. Captions keep the correct spelling.
SAY: dict[str, str] = {
    "km²": " square kilometres", "°C": " degrees Celsius", "°N": " degrees north",
    "°E": " degrees east", "mm": " millimetres", "MW": " megawatts", "%": " percent",
    "Rajasthan": "Raajasthaan", "Thar": "Tar", "Aravalli": "Arra-valli", "Ganga": "Gunga",
    "Himadri": "Hi-maadri", "Mawsynram": "Maw-sin-ram", "Godavari": "Go-daavari",
    "Kaveri": "Kaa-veri", "Narmada": "Nurmuda", "Mahanadi": "Maha-nuddi",
    "Brahmaputra": "Brahma-pootra", "Deccan": "Deckun", "Ghats": "Gaats", "Chambal": "Chumbal",
    "Jaisalmer": "Jaysalmair", "Kota": "Kotaa", "Lakshadweep": "Luck-shud-weep",
}


def speechify(text: str) -> str:
    """Rewrite a caption into something a voice can say, on word boundaries."""
    for key in sorted(SAY, key=len, reverse=True):
        pattern = (r"\b" if key[0].isalnum() else "") + re.escape(key) + (r"\b" if key[-1].isalnum() else "")
        text = re.sub(pattern, SAY[key], text)
    return text.replace("–", " to ").replace("·", ",").replace("≈", "about ").replace("→", " to ")


def estimate_seconds(text: str) -> float:
    """About 143 words a minute, which is what espeak at -s 148 measures."""
    return max(1.2, len(text.split()) * 0.42)


def audio_dir() -> Path:
    folder = Path(os.environ.get("PANIM_AUDIO_DIR") or (Path.cwd() / "build_audio"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


# Scripts a line may be written in, and the voice each needs. A Hindi line
# read by an English voice comes out as noise, so the language is taken from
# the line itself, whatever voice the style names.
SCRIPT_LANGS = (("hi", 0x0900, 0x097F),)
KOKORO_VOICES = {"hi": "hf_alpha"}


def spoken_lang(text: str) -> str:
    """'hi' when most letters are Devanagari, else 'en'."""
    letters = [c for c in text if c.isalpha()]
    for lang, lo, hi in SCRIPT_LANGS:
        if letters and sum(lo <= ord(c) <= hi for c in letters) / len(letters) > 0.4:
            return lang
    return "en"


# The Kokoro voice each style speaks in (the editor's lecture templates name the same).
STYLE_VOICES = {"atlas": "bf_emma", "vox": "af_bella", "cardboard": "am_michael", "whiteboard": "am_adam",
                "blueprint": "am_eric", "chalkboard": "am_michael", "parchment": "bm_george", "lab": "af_sarah",
                "cosmos": "am_adam"}
KOKORO_WEIGHTS = (HERE.parent / "models" / "kokoro-v1.0.onnx", HERE.parent / "models" / "voices-v1.0.bin")


def kokoro_ready() -> bool:
    """Kokoro can speak here: the package is installed and its weights are downloaded."""
    import importlib.util

    return importlib.util.find_spec("kokoro_onnx") is not None and all(
        w.exists() and w.stat().st_size > 1_000_000 for w in KOKORO_WEIGHTS)


def _espeak_binary() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def voice_mode() -> str:
    """The voice lines are actually spoken in: kokoro:<voice>, espeak or silent.

    PANIM_VOICE asks for one: `auto` (the default) is Kokoro when it is ready,
    else espeak-ng when installed, else silent; `kokoro[:voice]` falls back the
    same way. The answer is part of each line's cache key, so installing a
    better voice re-speaks lines an older one cached.
    """
    mode = os.environ.get("PANIM_VOICE", "auto")
    if mode == "silent":
        return "silent"
    if mode in ("auto", "kokoro") or mode.startswith("kokoro:"):
        if kokoro_ready():
            voice = mode.split(":", 1)[1] if ":" in mode else STYLE_VOICES.get(STYLE, "af_sarah")
            return f"kokoro:{voice}"
    return "espeak" if _espeak_binary() else "silent"


@lru_cache(None)
def _kokoro():
    from kokoro_onnx import Kokoro

    return Kokoro(str(KOKORO_WEIGHTS[0]), str(KOKORO_WEIGHTS[1]))


def _finish(raw: Path, out: Path, echo: bool = False) -> None:
    """The house treatment every line gets: band-limit, level, 44.1 kHz stereo (as is without ffmpeg)."""
    if not shutil.which("ffmpeg"):
        raw.replace(out)
        return
    chain = "highpass=f=70,lowpass=f=7500,aecho=0.8:0.6:35:0.12," if echo else "highpass=f=70,"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    chain + "loudnorm=I=-17:TP=-2,apad=pad_dur=0.1", "-ar", "44100", "-ac", "2", str(out)],
                   check=True, timeout=120)
    raw.unlink(missing_ok=True)


def narrate(text: str) -> tuple[str | None, float]:
    """(wav path or None, seconds) for one line, cached by its voice and spoken text.

    The voice is voice_mode()'s. A voice that fails is an estimate, not a
    crash: the beat still holds for as long as the sentence would take, and
    the beat log records wav=None so the app can say the lecture is silent.
    """
    spoken = speechify(text)
    mode = voice_mode()
    if mode == "silent":
        return None, estimate_seconds(spoken)
    digest = hashlib.md5(f"{mode}|{spoken}".encode()).hexdigest()[:12]
    out = audio_dir() / f"{digest}.wav"
    if out.exists() and out.stat().st_size > 44:
        return str(out), _wav_seconds(out)

    lang = spoken_lang(spoken)
    raw = out.with_name(out.stem + "_raw.wav")
    if mode.startswith("kokoro:"):
        voice = mode.split(":", 1)[1]
        if lang != "en" and not voice.startswith(lang[0]):
            voice = KOKORO_VOICES[lang]
        try:
            import soundfile as sf

            samples, rate = _kokoro().create(spoken, voice=voice, speed=1.0, lang=lang if lang != "en" else
                                             ("en-gb" if voice.startswith("b") else "en-us"))
            sf.write(str(raw), np.asarray(samples, dtype=np.float32), rate, subtype="PCM_16")
            _finish(raw, out)
            return str(out), _wav_seconds(out)
        except Exception as error:  # noqa: BLE001 -- fall through to espeak or silence
            print(f"pocket_lecture: Kokoro could not speak ({error}); trying espeak", file=sys.stderr)

    espeak = _espeak_binary()
    if espeak:
        voice = lang if lang != "en" else (os.environ.get("LECTURE_VOICE") or _espeak_voice(espeak))
        try:
            subprocess.run([espeak, "-v", voice, "-s", "148", "-p", "42", "-g", "4", "-w", str(raw), spoken],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            _finish(raw, out, echo=True)
            return str(out), _wav_seconds(out)
        except Exception:  # noqa: BLE001
            pass
    return None, estimate_seconds(spoken)


@lru_cache(None)
def _espeak_voice(binary: str) -> str:
    try:
        probe = subprocess.run([binary, "-v", "mb-en1", "-w", os.devnull, "test"], capture_output=True)
        if probe.returncode == 0 and not probe.stderr:
            return "mb-en1"
    except OSError:
        pass
    return "en-gb"


# ════════════════════════════════════════════════════════════════════════
#  MAP DATA (Natural Earth through Cartopy)
# ════════════════════════════════════════════════════════════════════════


@lru_cache(None)
def _records(name: str, category: str = "cultural", resolution: str = "10m") -> list:
    import cartopy.io.shapereader as shpreader

    path = shpreader.natural_earth(resolution=resolution, category=category, name=name)
    return [(rec.attributes, rec.geometry) for rec in shpreader.Reader(path).records()]


def _norm(value) -> str:
    """A name for matching: lower case, words only, accents off Latin letters.

    Letters of every script are kept ("प्रयागराज" stays itself); only a mark on
    a Latin letter is dropped, so "Zürich" and "Zurich" match.
    """
    import unicodedata

    out: list[str] = []
    for c in unicodedata.normalize("NFKD", str(value or "")).lower():
        kind = unicodedata.category(c)
        if kind.startswith("M"):
            if out and ord(out[-1]) >= 0x250:
                out.append(c)
        elif kind[0] in "LN":
            out.append(c)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _valid(geom):
    from shapely.validation import make_valid

    return make_valid(geom).buffer(0)


def country(name: str, view: str | None = None):
    """A country's outline. view="ind" draws borders as India claims them."""
    dataset = "admin_0_countries_ind" if view == "ind" else "admin_0_countries"
    wanted = _norm(name)
    for attrs, geom in _records(dataset):
        names = {_norm(attrs.get(k)) for k in ("ADMIN", "NAME", "NAME_LONG", "SOVEREIGNT", "ISO_A3")}
        if wanted in names:
            return _valid(geom)
    raise KeyError(f"no country named {name!r} in Natural Earth")


def state(name: str, country_name: str | None = None):
    """A first-level division (state, province) by name."""
    wanted = _norm(name)
    scope = _norm(country_name) if country_name else None
    for attrs, geom in _records("admin_1_states_provinces"):
        if scope and scope not in (_norm(attrs.get("admin")), _norm(attrs.get("adm0_a3"))):
            continue
        if wanted in (_norm(attrs.get("name")), _norm(attrs.get("name_en"))):
            return _valid(geom)
    raise KeyError(f"no state named {name!r}" + (f" in {country_name}" if country_name else ""))


def states_of(country_name: str) -> list[tuple[str, object]]:
    scope = _norm(country_name)
    return [
        (str(attrs.get("name")), geom)
        for attrs, geom in _records("admin_1_states_provinces")
        if scope in (_norm(attrs.get("admin")), _norm(attrs.get("adm0_a3")))
    ]


def countries_in(bounds, view: str | None = None, exclude=()) -> list[tuple[str, object]]:
    from shapely.geometry import box

    frame = box(*bounds)
    dataset = "admin_0_countries_ind" if view == "ind" else "admin_0_countries"
    skip = {_norm(x) for x in exclude}
    out = []
    for attrs, geom in _records(dataset):
        label = str(attrs.get("ADMIN") or attrs.get("NAME"))
        if _norm(label) in skip or not geom.intersects(frame):
            continue
        out.append((label, _valid(geom).intersection(frame)))
    return out


def river(name: str, bounds=None):
    """A river centreline from Natural Earth, optionally cut to a lon/lat box."""
    from shapely.geometry import box
    from shapely.ops import unary_union

    wanted = _norm(name)
    parts = [geom for attrs, geom in _records("rivers_lake_centerlines", "physical")
             if wanted in (_norm(attrs.get("name")), _norm(attrs.get("name_en")))]
    if not parts:
        raise KeyError(f"no river named {name!r} in Natural Earth")
    geom = unary_union(parts)
    return geom.intersection(box(*bounds)) if bounds else geom


# Renamed places: a script may use either name; Natural Earth knows one of them.
PLACE_ALIASES = {
    "Prayagraj": "Allahabad", "Bangalore": "Bengaluru", "Calcutta": "Kolkata", "Bombay": "Mumbai",
    "Madras": "Chennai", "Poona": "Pune", "Benares": "Varanasi", "Banaras": "Varanasi", "Kashi": "Varanasi",
    "Gauhati": "Guwahati", "Cawnpore": "Kanpur", "Cochin": "Kochi", "Trivandrum": "Thiruvananthapuram",
    "Baroda": "Vadodara", "Simla": "Shimla", "Gurugram": "Gurgaon", "Mysuru": "Mysore",
    "Puducherry": "Pondicherry", "Belagavi": "Belgaum", "Mangaluru": "Mangalore", "Hubballi": "Hubli",
    "Kalaburagi": "Gulbarga", "Trichy": "Tiruchirappalli", "Tiruchchirappalli": "Tiruchirappalli",
    "Delhi": "New Delhi", "Peking": "Beijing", "Canton": "Guangzhou", "Rangoon": "Yangon", "Saigon": "Ho Chi Minh City",
}


@lru_cache(None)
def _extra_places() -> dict:
    """data/places_extra.csv: name or alias (normalised) -> (lon, lat, country)."""
    import csv

    out = {}
    path = HERE / "data" / "places_extra.csv"
    if not path.exists():
        return out
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    for row in csv.DictReader(rows):
        entry = (float(row["lon"]), float(row["lat"]), _norm(row["country"]))
        for name in [row["name"]] + [a for a in (row.get("aliases") or "").split("|") if a]:
            out.setdefault(_norm(name), entry)
    return out


def _natural_earth_place(name: str, scope: str | None):
    wanted = _norm(name)
    if not wanted:
        return None
    best = None
    for attrs, _geom in _records("populated_places"):
        if wanted not in (_norm(attrs.get("NAME")), _norm(attrs.get("NAMEASCII")), _norm(attrs.get("NAME_EN"))):
            continue
        if scope and scope not in (_norm(attrs.get("ADM0NAME")), _norm(attrs.get("SOV0NAME")), _norm(attrs.get("ADM0_A3"))):
            continue
        pop = float(attrs.get("POP_MAX") or 0)
        if best is None or pop > best[0]:
            best = (pop, float(attrs["LONGITUDE"]), float(attrs["LATITUDE"]))
    return (best[1], best[2]) if best else None


GEONAMES = HERE / "data" / "geonames" / "cities.txt"


@lru_cache(None)
def _country_codes() -> dict:
    """Country name (normalised) -> ISO 3166 alpha-2, from Natural Earth's countries."""
    out = {}
    for attrs, _geom in _records("admin_0_countries"):
        code = attrs.get("ISO_A2_EH") or attrs.get("ISO_A2")
        if code and code != "-99":
            for key in ("NAME", "ADMIN", "NAME_LONG", "FORMAL_EN"):
                if attrs.get(key):
                    out[_norm(attrs[key])] = code
    return out


@lru_cache(None)
def _geonames() -> dict:
    """GeoNames cities: every name and alternate name (normalised) -> [(population, lon, lat, country code)].

    Absent until harness/scripts/fetch_gazetteer.py has run; then an empty dict.
    """
    index: dict = {}
    if not GEONAMES.exists():
        return index
    with GEONAMES.open(encoding="utf-8") as handle:
        for line in handle:
            f = line.rstrip("\n").split("\t")
            if len(f) < 15:
                continue
            row = (int(f[14] or 0), float(f[5]), float(f[4]), f[8])
            names = {f[1], f[2]} | {a for a in f[3].split(",") if a}
            for name in names:
                key = _norm(name)
                if key:
                    index.setdefault(key, []).append(row)
    return index


def _geonames_place(name: str, country_name: str | None):
    rows = _geonames().get(_norm(name))
    if not rows:
        return None
    if country_name:
        code = _country_codes().get(_norm(country_name))
        rows = [r for r in rows if r[3] == code] if code else rows
    if not rows:
        return None
    best = max(rows, key=lambda r: r[0])
    return best[1], best[2]


def _geocode_cache_path() -> Path:
    return Path(os.environ.get("PANIM_GEOCODE_CACHE") or (HERE / ".cache" / "geocode.json"))


def _geocode(name: str, country_name: str | None):
    """OpenStreetMap's Nominatim, once per name, cached on disk. PANIM_GEOCODE=0 turns it off.

    The cache makes a render reproducible and offline after the first lookup;
    a failed lookup is cached too, so a missing name costs one request.
    """
    import json

    if os.environ.get("PANIM_GEOCODE", "1") == "0":
        return None
    key = f"{_norm(name)}|{_norm(country_name)}"
    path = _geocode_cache_path()
    try:
        cache = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        cache = {}
    if key in cache:
        return tuple(cache[key]) if cache[key] else None
    found = None
    try:
        import urllib.parse
        import urllib.request

        query = urllib.parse.urlencode({"q": f"{name}, {country_name}" if country_name else name, "format": "json",
                                        "limit": 1})
        request = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{query}",
                                         headers={"User-Agent": "pocketanim-lecture/0.4 (map lectures)"})
        with urllib.request.urlopen(request, timeout=8) as response:
            rows = json.loads(response.read().decode())
        if rows:
            found = (round(float(rows[0]["lon"]), 4), round(float(rows[0]["lat"]), 4))
    except Exception:  # noqa: BLE001 -- offline, blocked or rate limited: not cached, tried again next time
        return None
    cache[key] = list(found) if found else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    return found


def place(name: str, country_name: str | None = None) -> tuple[float, float]:
    """(lon, lat) of a place.

    In order: Natural Earth's populated places (the most populous match),
    under the name or its renamed form; data/places_extra.csv; the GeoNames
    gazetteer when fetch_gazetteer.py has downloaded it; then OpenStreetMap,
    cached. Raises KeyError when none knows it.
    """
    scope = _norm(country_name) if country_name else None
    names = [name]
    for old, new in PLACE_ALIASES.items():
        if _norm(name) == _norm(old):
            names.append(new)
        elif _norm(name) == _norm(new):
            names.append(old)
    for candidate in names:
        found = _natural_earth_place(candidate, scope)
        if found:
            return found
    extra = _extra_places()
    for candidate in names:
        row = extra.get(_norm(candidate))
        if row and (not scope or row[2] == scope):
            return row[0], row[1]
    for candidate in names:
        found = _geonames_place(candidate, country_name)
        if found:
            return found
    found = _geocode(name, country_name)
    if found:
        return found
    hint = "" if GEONAMES.exists() else " (run harness/scripts/fetch_gazetteer.py to add 150,000 more towns)"
    raise KeyError(f"no place named {name!r}" + (f" in {country_name}" if country_name else "") + hint)


class MapFrame:
    """One projection and one linear map into scene units, for every layer.

    Every map element -- outlines, rivers, markers, graticules -- goes through
    the same Cartopy projection and the same scale and offset, which is what
    keeps them lined up.
    """

    def __init__(self, focus, center=(-3.0, 0.2), height=6.3, width=6.5, crs=None, clip=True):
        import cartopy.crs as ccrs

        lon0, lat0, lon1, lat1 = focus.bounds
        if crs is None:
            span = max(lat1 - lat0, 1.0)
            crs = ccrs.LambertConformal(
                central_longitude=(lon0 + lon1) / 2, central_latitude=(lat0 + lat1) / 2,
                standard_parallels=(lat0 + span / 6, lat1 - span / 6),
            )
        self.crs = crs
        self.pc = ccrs.PlateCarree()
        x0, y0, x1, y1 = self.project_geom(focus, scale=False).bounds
        self.c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        self.s = min(height / (y1 - y0), width / (x1 - x0))
        self.center = np.array(center, dtype=float)
        # Shapes are cut at the panel's left edge: nothing under the panel is
        # ever seen, and baking it only makes the asset bigger.
        self.clip = (-7.4, -4.3, 1.05, 4.3) if clip else None

    def xy(self, lon, lat) -> np.ndarray:
        lon = np.atleast_1d(np.asarray(lon, float))
        lat = np.atleast_1d(np.asarray(lat, float))
        p = self.crs.transform_points(self.pc, lon, lat)[:, :2]
        return (p - self.c) * self.s + self.center

    def pt(self, lon, lat) -> np.ndarray:
        x, y = self.xy(lon, lat)[0]
        return np.array([x, y, 0.0])

    def project_geom(self, geom, scale=True):
        from shapely.ops import transform

        def f(x, y, z=None):
            p = self.crs.transform_points(self.pc, np.asarray(x, float), np.asarray(y, float))
            if scale:
                q = (p[:, :2] - self.c) * self.s + self.center
                return q[:, 0], q[:, 1]
            return p[:, 0], p[:, 1]

        return transform(f, geom)

    def poly(self, geom, simplify=0.006, min_area=0.0005, **style) -> VGroup:
        from shapely.geometry import box

        g = self.project_geom(geom).simplify(simplify, preserve_topology=True)
        if self.clip:
            g = _valid(g).intersection(box(*self.clip))
        polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
        jitter = TH.get("jitter", 0)
        group = VGroup()
        for p in polys:
            if p.area < min_area:
                continue
            pts = np.array(p.exterior.coords)
            if jitter:
                k = np.arange(len(pts))
                pts = pts + jitter * np.c_[np.sin(k * 0.9) + np.sin(k * 0.23), np.cos(k * 0.7) + np.sin(k * 0.31)]
            m = VMobject(**style)
            m.set_points_as_corners(np.c_[pts, np.zeros(len(pts))])
            group.add(m)
        return group

    def line(self, geom, simplify=0.006, **style) -> VGroup:
        from shapely.geometry import box

        g = self.project_geom(geom).simplify(simplify)
        if self.clip:
            g = g.intersection(box(*self.clip))
        lines = [g] if g.geom_type == "LineString" else [x for x in getattr(g, "geoms", []) if x.geom_type == "LineString"]
        group = VGroup()
        for part in lines:
            if len(part.coords) < 2:
                continue
            pts = np.c_[np.array(part.coords), np.zeros(len(part.coords))]
            m = VMobject(**style)
            m.set_points_smoothly(pts) if len(pts) > 3 else m.set_points_as_corners(pts)
            group.add(m)
        return group

    def path(self, lonlats, smooth=True, **style) -> VMobject:
        ll = np.array(lonlats, float)
        pts = np.c_[self.xy(ll[:, 0], ll[:, 1]), np.zeros(len(ll))]
        m = VMobject(**style)
        m.set_points_smoothly(pts) if smooth and len(pts) > 2 else m.set_points_as_corners(pts)
        return m


# ════════════════════════════════════════════════════════════════════════
#  THE LECTURE SCENE
# ════════════════════════════════════════════════════════════════════════

# Screen layout, in Manim units (the frame is 14.22 x 8).
PANEL_X = 1.05          # the panel's left edge; the map lives left of it
TEXT_X = 1.6            # where panel text starts
TEXT_W = 5.0            # and how wide it may get
CAPTION_Y = -3.45

# Draw order, as z_index.
Z_BACK, Z_LAND, Z_FILL, Z_LINES, Z_OUTLINE, Z_MARK = -100, 0.5, 2, 4, 5, 10
Z_PANEL, Z_PANEL_TEXT, Z_CARD, Z_CHROME, Z_CAPTION = 20, 25, 40, 50, 60


_SUPER = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_TEX_WORDS = {r"\times": "×", r"\cdot": "·", r"\pm": "±", r"\div": "÷", r"\leq": "≤", r"\geq": "≥",
              r"\neq": "≠", r"\approx": "≈", r"\infty": "∞", r"\rightarrow": "→", r"\to": "→",
              r"\leftrightarrow": "↔", r"\rightleftharpoons": "⇌", r"\Delta": "Δ", r"\delta": "δ",
              r"\pi": "π", r"\theta": "θ", r"\lambda": "λ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ",
              r"\omega": "ω", r"\Omega": "Ω", r"\mu": "μ", r"\sigma": "σ", r"\rho": "ρ", r"\phi": "φ",
              r"\sum": "Σ", r"\int": "∫", r"\partial": "∂", r"\nabla": "∇", r"\degree": "°", r"\circ": "°"}


def unicode_math(tex: str) -> str:
    """LaTeX-ish maths as plain Unicode, for machines without LaTeX: E = mc^2 -> E = mc², H_2O -> H₂O."""
    text = str(tex)
    # Innermost first, until nothing changes: a square root inside a fraction.
    for _ in range(6):
        before = text
        text = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", text)
        text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", text)
        text = re.sub(r"\^\{([^{}]*)\}", lambda m: m.group(1).translate(_SUPER), text)
        text = re.sub(r"_\{([^{}]*)\}", lambda m: m.group(1).translate(_SUB), text)
        if text == before:
            break
    # A command swallows the space after it, as in LaTeX.
    for word in sorted(_TEX_WORDS, key=len, reverse=True):
        symbol = _TEX_WORDS[word]
        swallow = " ?" if symbol.isalpha() else ""      # Greek letters join the next symbol; operators keep space
        text = re.sub(re.escape(word) + r"(?![a-zA-Z])" + swallow, symbol, text)
    text = text.replace("\\sqrt", "√")
    text = re.sub(r"\^([0-9n+\-i])", lambda m: m.group(1).translate(_SUPER), text)
    text = re.sub(r"_([0-9])", lambda m: m.group(1).translate(_SUB), text)
    text = text.replace("<=>", "⇌").replace("->", "→").replace("*", "·").replace("{", "").replace("}", "")
    return re.sub(r"\\([a-zA-Z]+)", r"\1", text)


_SAFE = {name: getattr(np, name) for name in ("sin", "cos", "tan", "exp", "log", "log10", "log2", "sqrt", "abs",
                                               "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "floor", "ceil")}
_SAFE.update(pi=np.pi, e=np.e, ln=np.log)


def safe_function(expr: str):
    """f(x) from an expression like "x^2 - 3*x" or "sin(x)*exp(-x/5)": numpy names only, nothing else."""
    import ast as _ast

    source = str(expr).replace("^", "**").strip()
    tree = _ast.parse(source, mode="eval")
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name) and node.id != "x" and node.id not in _SAFE:
            raise ValueError(f"unknown name {node.id!r} in {expr!r}")
        if isinstance(node, (_ast.Attribute, _ast.Subscript, _ast.Lambda, _ast.Call)) and not (
                isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)):
            raise ValueError(f"not a plain expression: {expr!r}")
    code = compile(tree, "<plot>", "eval")

    def f(x):
        with np.errstate(all="ignore"):
            return eval(code, {"__builtins__": {}}, {**_SAFE, "x": x})  # noqa: S307 -- names checked above

    return f


def backdrop() -> VGroup:
    """The style's texture, as a few vector shapes baked into one asset."""
    w, h = config.frame_width, config.frame_height
    rng = np.random.default_rng(7)
    parts = VGroup()
    texture = TH["texture"]
    if texture == "vignette":
        # A soft glow left of centre: nested discs, each barely lighter.
        for i, r in enumerate((7.5, 6.0, 4.6, 3.3)):
            parts.add(Circle(radius=r, stroke_width=0, fill_color="#26303F", fill_opacity=0.16 + 0.02 * i)
                      .move_to(LEFT * 1.8 + UP * 0.3))
    elif texture == "paper":
        for i, r in enumerate((8.5, 7.0)):
            parts.add(Circle(radius=r, stroke_width=0, fill_color="#FFFFFF", fill_opacity=0.06 + 0.04 * i)
                      .move_to(LEFT * 1.5))
    elif texture == "kraft":
        for _ in range(70):
            x, y = rng.uniform(-w / 2, w / 2), rng.uniform(-h / 2, h / 2)
            length = rng.uniform(0.3, 1.4)
            parts.add(Line([x, y, 0], [x + length, y + rng.uniform(-0.02, 0.02), 0],
                           stroke_color="#7A5530", stroke_width=rng.uniform(0.6, 1.4), stroke_opacity=0.22))
    elif texture == "board":
        parts.add(Rectangle(width=w - 0.12, height=h - 0.12, stroke_color="#C9C9C0", stroke_width=6, fill_opacity=0))
        for _ in range(6):
            parts.add(Circle(radius=rng.uniform(0.8, 2.2), stroke_width=0, fill_color="#E6E6DE", fill_opacity=0.35)
                      .stretch(0.4, 1).move_to([rng.uniform(-6, 6), rng.uniform(-3.5, 3.5), 0]))
    elif texture == "grid":
        for x in np.arange(-7.0, 7.01, 0.5):
            major = abs(x / 2.5 - round(x / 2.5)) < 1e-6
            parts.add(Line([x, -h / 2, 0], [x, h / 2, 0], stroke_color="#3F74A8",
                           stroke_width=1.2 if major else 0.6, stroke_opacity=0.55 if major else 0.3))
        for y in np.arange(-4.0, 4.01, 0.5):
            major = abs(y / 2.5 - round(y / 2.5)) < 1e-6
            parts.add(Line([-w / 2, y, 0], [w / 2, y, 0], stroke_color="#3F74A8",
                           stroke_width=1.2 if major else 0.6, stroke_opacity=0.55 if major else 0.3))
    elif texture == "parchment":
        # Age spots and a ruled double frame, like a page from an old atlas.
        for _ in range(9):
            parts.add(Circle(radius=rng.uniform(0.8, 2.4), stroke_width=0, fill_color="#D9C39A",
                             fill_opacity=rng.uniform(0.05, 0.11)).stretch(rng.uniform(0.5, 0.9), 1)
                      .move_to([rng.uniform(-6.5, 6.5), rng.uniform(-3.6, 3.6), 0]))
        parts.add(Rectangle(width=w - 0.25, height=h - 0.25, stroke_color="#8C6E45", stroke_width=2.5, fill_opacity=0))
        parts.add(Rectangle(width=w - 0.45, height=h - 0.45, stroke_color="#8C6E45", stroke_width=0.8, fill_opacity=0))
    elif texture == "dots":
        for x in np.arange(-7.0, 7.01, 0.5):
            for y in np.arange(-4.0, 4.01, 0.5):
                parts.add(Dot([x, y, 0], radius=0.012, color="#B8CCCC", fill_opacity=0.8))
    elif texture == "stars":
        for _ in range(140):
            parts.add(Dot([rng.uniform(-w / 2, w / 2), rng.uniform(-h / 2, h / 2), 0],
                          radius=rng.uniform(0.006, 0.022), color="#FFFFFF", fill_opacity=rng.uniform(0.25, 0.9)))
        for i, r in enumerate((5.5, 4.0)):
            parts.add(Circle(radius=r, stroke_width=0, fill_color="#3B2F7A", fill_opacity=0.08 + 0.04 * i)
                      .move_to(LEFT * 2.5 + UP * 1.2))
    elif texture == "chalk":
        for _ in range(8):
            parts.add(Circle(radius=rng.uniform(0.9, 2.6), stroke_width=0, fill_color="#2A5242", fill_opacity=0.35)
                      .stretch(0.35, 1).move_to([rng.uniform(-6, 6), rng.uniform(-3.5, 3.5), 0]))
    parts.set_z_index(Z_BACK)
    return parts


class Lecture(Scene):
    """Beats, captions, a fact panel and chapter cards, in the current style."""

    SECTIONS: list[str] = []
    SECTION = 0
    # Where panel text starts. A map lecture keeps the left for the map and
    # the panel to its right; without a map the column sits near the centre.
    TEXT_LEFT = -3.0
    PANEL_BOX = (-3.55, 5.9)   # the panel's left and right edges

    def setup(self):
        self.cap = None
        self.panel_items = VGroup()
        self.panel_images = Group()     # figures: images cannot join a VGroup
        self.stage_items = Group()      # the picture on the stage: a photo, a figure or an illustration
        self._full_figure = None        # the full-frame figure on screen, faded at the next beat
        self._new_figure = None         # one built for this beat (its call runs before beat() does)
        self.panel_y = 2.35
        self.chrome = VGroup()
        back = backdrop()
        if len(back):
            self.add(back)
        self.section(self.SECTION)

    # ---------------- beat log ----------------
    def _log(self, kind: str, **fields) -> None:
        """Append where a beat or chapter starts to PANIM_BEAT_LOG, if set.

        Rendered time, not script time: subtitles, chapter marks and the
        contact sheet read this, and it is what the video actually did.
        """
        target = os.environ.get("PANIM_BEAT_LOG")
        if not target:
            return
        import json

        start = float(getattr(getattr(self, "renderer", None), "time", 0.0) or 0.0)
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"kind": kind, "start": round(start, 3), **fields}) + "\n")

    # ---------------- chrome ----------------
    def section(self, index: int) -> None:
        """Show the progress bar and chapter tag for section `index`."""
        if len(self.chrome):
            self.remove(self.chrome)
            self.chrome = VGroup()
        if index <= 0 or not self.SECTIONS:
            return
        total = max(len(self.SECTIONS) - 1, 1)
        half = config.frame_width / 2
        track = Line(LEFT * half, RIGHT * half, stroke_width=3, color=TH["track"]).to_edge(UP, buff=0.0)
        done = Line(LEFT * half, LEFT * half + RIGHT * config.frame_width * min(index, total) / total,
                    stroke_width=3, color=P.SAND).align_to(track, UP)
        name = self.SECTIONS[index] if index < len(self.SECTIONS) else ""
        tag = T(f"{index:02d}  ·  {name.upper()}", 15, P.MUTED, weight=BOLD).to_corner(UL, buff=0.28).shift(DOWN * 0.05)
        self.chrome = VGroup(track, done, tag)
        self.chrome.set_z_index(Z_CHROME)
        self.add(self.chrome)

    # ---------------- narration beat ----------------
    def beat(self, text: str, *anims, rt: float | None = None, pad: float = 0.45) -> float:
        """One narration line and the animations that go with it.

        The line is spoken first and measured; the animations take 55% of it
        (1.2 to 3.2 s) so motion lands while the sentence is still going, and
        the rest of the line plus a short pause is a hold.
        """
        if self._full_figure is not None:
            self.play(FadeOut(self._full_figure), run_time=0.4)
            self._full_figure = None
        self._full_figure, self._new_figure = self._new_figure, None
        wav, seconds = narrate(text)
        self._log("beat", text=text, seconds=round(seconds, 3), wav=wav)
        cap = self.caption(text)
        if wav:
            self.add_sound(wav)
        if self.cap is not None:
            self.remove(self.cap)
        self.add(cap)
        self.cap = cap
        spent = 0.0
        anims = [a for a in anims if a is not None]
        if anims:
            spent = rt if rt is not None else min(max(1.2, seconds * 0.55), 3.2)
            head = [a for a in anims if getattr(a, "panel_head", False)]
            items = [a for a in anims if getattr(a, "panel_item", False)]
            if head and items:
                # A new panel clears the old one before its facts arrive;
                # played together, the facts landed on the fading old panel.
                rest = [a for a in anims if a not in items]
                self.play(*rest, run_time=spent * 0.5)
                self.play(*items, run_time=spent * 0.5)
            else:
                self.play(*anims, run_time=spent)
        rest = seconds + pad - spent
        if rest > 0.02:
            self.wait(rest)
        return seconds

    def pause(self, seconds: float = 0.6) -> None:
        self.wait(seconds)

    def caption(self, text: str) -> VGroup:
        lines = textwrap.wrap(text, 92)
        if len(lines) > 2:
            lines = textwrap.wrap(text, int(len(text) / 2) + 8)
        t = fit(T("\n".join(lines), tok("caption_size", 19), TH["cap_fg"], line_spacing=0.9), 13.2)
        box = RoundedRectangle(corner_radius=0.03 if TH["upper"] else 0.12, width=t.width + 0.5,
                               height=t.height + 0.3, fill_color=TH["cap_bg"], fill_opacity=TH["cap_op"],
                               stroke_width=1.2 if STYLE == "blueprint" else 0, stroke_color=P.MUTED)
        box.move_to([0, CAPTION_Y, 0])
        t.move_to(box)
        group = VGroup(box, t)
        if STYLE == "cardboard":
            shadow = box.copy().set_fill("#000000", 0.28).shift(RIGHT * 0.05 + DOWN * 0.05)
            group = VGroup(shadow, box, t).rotate(-0.006)
        group.set_z_index(Z_CAPTION)
        return group

    def clear_caption(self) -> None:
        if self.cap is not None:
            self.remove(self.cap)
            self.cap = None

    # ---------------- side panel ----------------
    def panel_bg(self) -> VGroup:
        left, right = self.PANEL_BOX
        r = Rectangle(width=right - left, height=6.55, fill_color=P.PANEL, fill_opacity=0.94, stroke_width=0)
        r.move_to(RIGHT * (left + right) / 2 + UP * 0.35)
        style = TH["panel_style"]
        if style == "solid":
            parts = [r, Line(r.get_corner(UL), r.get_corner([-1, -1, 0]), color=P.SAND, stroke_width=2,
                             stroke_opacity=0.5)]
        elif style == "rule":
            parts = [Line(r.get_corner(UL) + DOWN * 0.1, r.get_corner([-1, -1, 0]), color=P.CREAM, stroke_width=2.5)]
        elif style == "note":
            note = Rectangle(width=5.75, height=6.35, fill_color=P.PANEL, fill_opacity=1, stroke_width=0)
            note.move_to(r).shift(RIGHT * 0.1)
            shadow = note.copy().set_fill("#000000", 0.3).shift(RIGHT * 0.08 + DOWN * 0.08)
            tape = Rectangle(width=1.5, height=0.36, fill_color="#F7F1DE", fill_opacity=0.72, stroke_width=0)
            tape.move_to(note.get_top()).rotate(0.05)
            parts = [VGroup(shadow, note).rotate(-0.012), tape]
        elif style == "marker":
            pts = [np.array([left + 0.07 + 0.02 * np.sin(i * 1.7), 3.5 - i * 0.26, 0]) for i in range(26)]
            parts = [VMobject(stroke_color=P.CREAM, stroke_width=3.2).set_points_smoothly(pts)]
        else:  # dashed
            parts = [DashedVMobject(r.copy().set_fill(opacity=0).set_stroke(P.MUTED, 1.5), num_dashes=90)]
        group = VGroup(*parts)
        group.set_z_index(Z_PANEL)
        return group

    def reveal(self, group, text_part=None):
        """The style's entrance for panel content."""
        anim = self._entrance(group, text_part)
        anim.panel_item = True
        return anim

    def _entrance(self, group, text_part):
        mode = TH["anim"]
        if mode in ("write", "type") and text_part is not None:
            rest = [m for m in group if m is not text_part]
            return AnimationGroup(Write(text_part), *[FadeIn(m) for m in rest])
        if mode == "drop":
            group.rotate(float(np.random.default_rng(len(self.panel_items)).uniform(-0.025, 0.025)))
            return FadeIn(group, shift=DOWN * 0.25, scale=1.08)
        return FadeIn(group, shift=UP * 0.12)

    def panel_title(self, title: str, sub: str | None = None):
        """Clear the panel and head it. Returns the animation."""
        old = self.panel_items
        t = T(title.upper() if TH["upper"] else title, tok("panel_title_size", 34), P.TITLE, font=TH["serif"], weight=BOLD)
        t.move_to(RIGHT * self.TEXT_LEFT + UP * 3.05, aligned_edge=LEFT)
        if t.width > 5.2:
            t.scale_to_fit_width(5.2).align_to(RIGHT * self.TEXT_LEFT, LEFT)
        items = VGroup(t)
        if TH.get("highlight"):
            bar = Rectangle(width=t.width + 0.3, height=t.height * 0.62, fill_color=TH["highlight"],
                            fill_opacity=1, stroke_width=0).move_to(t).shift(DOWN * t.height * 0.12)
            items = VGroup(bar, t)
        elif TH["panel_style"] == "marker":
            under = VMobject(stroke_color=P.TITLE, stroke_width=3).set_points_smoothly(
                [t.get_corner([-1, -1, 0]) + DOWN * 0.08 + RIGHT * x + UP * 0.03 * np.sin(x * 5)
                 for x in np.linspace(0, t.width, 8)])
            items = VGroup(t, under)
        y = t.get_bottom()[1] - 0.25
        if sub:
            s = fit(T(sub, 17, P.MUTED), TEXT_W)
            s.next_to(t, DOWN, aligned_edge=LEFT, buff=0.12)
            items.add(s)
            y = s.get_bottom()[1] - 0.25
        self.panel_y = y - 0.05
        items.set_z_index(Z_PANEL_TEXT)
        self.panel_items = VGroup(items)
        show = Write(items) if TH["anim"] == "write" else FadeIn(items, shift=RIGHT * 0.2)
        going = [FadeOut(old)] if len(old) else []
        if len(self.panel_images):
            going.append(FadeOut(self.panel_images))
            self.panel_images = Group()
        anim = AnimationGroup(AnimationGroup(*going), show, lag_ratio=0.5) if going else show
        anim.panel_head = True
        return anim

    def _stack(self, group, gap: float):
        group.move_to(RIGHT * self.TEXT_LEFT + UP * self.panel_y, aligned_edge=UL)
        self.panel_y = group.get_bottom()[1] - gap
        group.set_z_index(Z_PANEL_TEXT)
        self.panel_items.add(group)
        return group

    def fact(self, text: str, color: str | None = None, bullet: str | None = None, size: float = 20):
        """A bulleted line in the panel, wrapped at 36 characters."""
        dot = Dot(radius=0.05, color=bullet or P.SAND)
        t = fit(T(wrap(text, 36), tok("fact_size", size), color or P.CREAM, line_spacing=0.85), 4.95)
        t.next_to(dot, RIGHT, buff=0.18, aligned_edge=UP)
        dot.shift(DOWN * 0.1)
        group = self._stack(VGroup(dot, t), 0.22)
        return self.reveal(group, t)

    def big_stat(self, value: str, label: str, color: str | None = None):
        """A large number with a small label under it."""
        v = fit(T(value, tok("stat_size", 44), color or P.GOLD, font=TH["serif"], weight=BOLD), 5.1)
        lab = fit(T(wrap(label, 40), 17, P.MUTED), TEXT_W)
        lab.next_to(v, DOWN, aligned_edge=LEFT, buff=0.08)
        group = self._stack(VGroup(v, lab), 0.3)
        return self.reveal(group, v)

    def panel_icon(self, name: str, label: str = "", color: str | None = None):
        """An icon with a line beside it in the panel: "sugarcane -- the west's cash crop"."""
        mob = icon_mob(name, color, height=0.62)
        row = VGroup(mob)
        if label:
            text = fit(T(wrap(label, 30), tok("fact_size", 20), P.CREAM, line_spacing=0.85), 4.1)
            text.next_to(mob, RIGHT, buff=0.22)
            row.add(text)
        group = self._stack(row, 0.25)
        return self.reveal(group, row[1] if label else None)

    def bar_chart(self, items, color: str | None = None, unit: str = "", width: float = 3.0):
        """Horizontal bars in the panel, each growing from a shared axis."""
        items = list(items)[:7]
        top = max((float(v) for _, v in items), default=1.0) or 1.0
        labels = [fit(T(str(name), 16, P.CREAM), 1.3) for name, _ in items]
        column = max((m.width for m in labels), default=0.5)
        axis_x = self.TEXT_LEFT + column + 0.2
        rows = VGroup()
        y = self.panel_y - 0.15
        for label, (_, value) in zip(labels, items):
            bar = Rectangle(width=max(0.04, width * float(value) / top), height=0.26,
                            fill_color=color or P.SAND, fill_opacity=0.9, stroke_width=0)
            bar.move_to([axis_x, y, 0], aligned_edge=LEFT)
            label.move_to([axis_x - 0.15, y, 0], aligned_edge=RIGHT)
            text = f"{value:g}" if isinstance(value, (int, float)) else str(value)
            num = T(text + unit, 14, P.MUTED).next_to(bar, RIGHT, buff=0.12)
            rows.add(VGroup(label, bar, num))
            y -= 0.42
        rows.set_z_index(Z_PANEL_TEXT)
        self.panel_items.add(rows)
        self.panel_y = rows.get_bottom()[1] - 0.3
        anim = LaggedStart(*[AnimationGroup(FadeIn(r[0]), GrowFromEdge(r[1], LEFT), FadeIn(r[2]))
                             for r in rows], lag_ratio=0.2)
        anim.panel_item = True
        return anim

    def add_panel(self, run_time: float = 0.8) -> None:
        """Put the panel up on its own, for a chapter with no map."""
        self.panel = self.panel_bg()
        self.play(FadeIn(self.panel), run_time=run_time)

    def clear_panel(self):
        old = [m for m in (self.panel_items, self.panel_images) if len(m)]
        self.panel_items = VGroup()
        self.panel_images = Group()
        self.panel_y = 2.35
        return AnimationGroup(*[FadeOut(m) for m in old]) if old else None

    # ---------------- the stage: pictures where the map would be ----------------
    # Centre x, centre y, width, height: the map's half of the frame, left of the panel.
    STAGE = (-3.05, 0.3, 6.5, 6.1)

    def _stage_card(self):
        """What a stage picture sits on: opaque over a map, invisible on the bare backdrop."""
        cx, cy, w, h = self.STAGE
        covering = bool(getattr(self, "layers", None)) and getattr(self, "_map_on", False)
        card = Rectangle(width=w + 0.5, height=h + 0.6, fill_color=P.BG, fill_opacity=1 if covering else 0,
                         stroke_width=0)
        return card.move_to([cx, cy, 0])

    def _to_stage(self, group):
        """Put a picture on the stage, over the map; the one there before fades."""
        old = self.stage_items
        new = Group(self._stage_card(), group)
        new.set_z_index(Z_MARK + 10)
        self.stage_items = new
        show = FadeIn(new, scale=1.02)
        return AnimationGroup(FadeOut(old), show, lag_ratio=0.4) if len(old) else show

    def clear_stage(self):
        """Take the stage picture away, showing the map again. None when there is none."""
        old = self.stage_items
        self.stage_items = Group()
        return FadeOut(old) if len(old) else None

    def stage_image(self, path: str, caption: str = "", credit: str = ""):
        """A photo or a document's figure, large, on the stage."""
        cx, cy, w, h = self.STAGE
        image = ImageMobject(path)
        room = h - (0.55 if caption else 0) - (0.3 if credit else 0)
        image.scale_to_fit_width(w)
        if image.height > room:
            image.scale_to_fit_height(room)
        frame = SurroundingRectangle(image, buff=0.0, color=P.MUTED, stroke_width=1.5)
        parts = [image, frame]
        if caption:
            parts.append(fit(T(caption, 16, P.CREAM), w).next_to(image, DOWN, buff=0.14))
        if credit:
            parts.append(fit(T(credit, 10, P.MUTED), w).next_to(parts[-1], DOWN, buff=0.06))
        group = Group(*parts).move_to([cx, cy, 0])
        return self._to_stage(group)

    def illustration(self, hero: str, items=(), title: str | None = None, color: str | None = None):
        """An illustration built from icons: one large, up to four small ones labelled beneath."""
        cx, cy, w, h = self.STAGE
        big = icon_mob(hero, color, height=2.5)
        parts = VGroup(big)
        if title:
            parts.add(fit(T(title.upper() if TH["upper"] else title, 30, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
        parts.arrange(DOWN, buff=0.3)
        row = VGroup()
        for item in list(items)[:4]:
            name, label = (item, "") if isinstance(item, str) else (item[0], item[1] if len(item) > 1 else "")
            small = icon_mob(name, color, height=0.85)
            cell = VGroup(small)
            if label:
                cell.add(fit(T(label, 15, P.CREAM), 1.5).next_to(small, DOWN, buff=0.1))
            row.add(cell)
        if len(row):
            row.arrange(RIGHT, buff=0.45, aligned_edge=UP)
            fit(row, w - 0.4)
            composition = VGroup(parts, row).arrange(DOWN, buff=0.55)
        else:
            composition = parts
        if composition.height > h - 0.2:
            composition.scale_to_fit_height(h - 0.2)
        composition.move_to([cx, cy, 0])
        return self._to_stage(Group(composition))

    # ---------------- subject kits: drawings for science, maths and history ----------------
    def _fit_stage(self, mob, margin: float = 0.3):
        cx, cy, w, h = self.STAGE
        if mob.width > w - margin:
            mob.scale_to_fit_width(w - margin)
        if mob.height > h - margin:
            mob.scale_to_fit_height(h - margin)
        return mob.move_to([cx, cy, 0])

    def molecule(self, name: str, label: str | None = None, hydrogens: str = "auto"):
        """A structural formula, laid out by RDKit: atoms in CPK colours, bonds with their order."""
        import molecules

        smiles = molecules.resolve(name)
        if smiles is None:
            raise KeyError(f"no molecule {name!r}")
        shape = molecules.layout(smiles, hydrogens)
        unit = 0.95
        points = {i: np.array([a["x"] * unit, a["y"] * unit, 0.0]) for i, a in enumerate(shape["atoms"])}
        bonds = VGroup()
        for bond in shape["bonds"]:
            a, b = points[bond["a"]], points[bond["b"]]
            normal = np.array([-(b - a)[1], (b - a)[0], 0.0])
            normal = normal / (np.linalg.norm(normal) or 1.0) * 0.07
            offsets = {1: [0.0], 2: [-1.0, 1.0], 3: [-1.6, 0.0, 1.6]}.get(bond["order"], [0.0])
            for k in offsets:
                bonds.add(Line(a + normal * k, b + normal * k, color=P.MUTED, stroke_width=5))
        atoms = VGroup()
        for i, atom in enumerate(shape["atoms"]):
            small = atom["symbol"] == "H"
            ball = Circle(radius=0.17 if small else 0.27, fill_color=atom["colour"], fill_opacity=1,
                          stroke_color=P.role_ink, stroke_width=1.5).move_to(points[i])
            ink = "#111111" if atom["symbol"] in ("H", "S", "Cl", "F", "Ca", "Mg", "Si") else "#FFFFFF"
            text = atom["symbol"] + ("+" if atom["charge"] > 0 else "−" if atom["charge"] < 0 else "")
            atoms.add(VGroup(ball, T(text, 13 if small else 17, ink, weight=BOLD).move_to(points[i])))
        drawing = VGroup(bonds, atoms)
        cx, cy, w, h = self.STAGE
        self._fit_stage(drawing, 1.4)
        title = VGroup(T(label or name.title(), 26, P.TITLE, font=TH["serif"], weight=BOLD),
                       T(molecules.formula(smiles), 20, P.MUTED)).arrange(RIGHT, buff=0.3)
        fit(title, w - 0.3).next_to(drawing, DOWN, buff=0.35)
        group = VGroup(drawing, title)
        self._fit_stage(group)
        anim = self._to_stage(Group(group))
        # Bonds draw, then the atoms pop on: the eye follows the structure being built.
        group.set_opacity(1)
        return anim

    def equation(self, tex: str, label: str | None = None):
        """An equation, large: typeset by LaTeX when installed, readable Unicode maths otherwise."""
        cx, cy, w, h = self.STAGE
        if shutil.which("latex"):
            body = MathTex(tex, color=P.CREAM).scale(1.4)
        else:
            body = T(unicode_math(tex), 56, P.CREAM, font=TH["serif"])
        parts = VGroup(body)
        if label:
            parts.add(fit(T(label, 20, P.MUTED), w - 0.4))
        parts.arrange(DOWN, buff=0.45)
        self._fit_stage(parts, 0.6)
        return self._to_stage(Group(parts))

    def plot(self, exprs, x_range=(-5.0, 5.0), label: str | None = None, x_label: str = "x", y_label: str = "y",
             names=()):
        """Graphs of one or more functions of x on labelled axes (no LaTeX needed)."""
        cx, cy, w, h = self.STAGE
        exprs = [exprs] if isinstance(exprs, str) else list(exprs)
        fns = [safe_function(e) for e in exprs]
        xs = np.linspace(float(x_range[0]), float(x_range[1]), 200)
        ys = np.concatenate([np.asarray(f(xs), dtype=float) for f in fns])
        ys = ys[np.isfinite(ys)]
        lo, hi = (float(ys.min()), float(ys.max())) if ys.size else (-1.0, 1.0)
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.1
        axes = Axes(x_range=[float(x_range[0]), float(x_range[1]), (float(x_range[1]) - float(x_range[0])) / 10],
                    y_range=[lo - pad, hi + pad, (hi - lo + 2 * pad) / 8], x_length=w - 1.0, y_length=h - 2.0,
                    tips=False, axis_config={"color": P.MUTED, "include_numbers": False, "stroke_width": 2})
        tones = [P.SAND, P.ROSE, P.RIVER, P.GREEN]
        curves = VGroup(*[axes.plot(f, color=tones[i % 4], stroke_width=5, use_smoothing=False,
                                    discontinuities=None) for i, f in enumerate(fns)])
        labels = VGroup(T(x_label, 18, P.MUTED).next_to(axes.x_axis, RIGHT, buff=0.1).shift(LEFT * 0.4 + DOWN * 0.3),
                        T(y_label, 18, P.MUTED).next_to(axes.y_axis, UP, buff=0.1))
        keys = VGroup(*[T(names[i] if i < len(names) else exprs[i], 16, tones[i % 4]) for i in range(len(fns))])
        keys.arrange(RIGHT, buff=0.4)
        body = VGroup(axes, curves, labels)
        parts = VGroup(body, keys)
        if label:
            parts.add(fit(T(label, 22, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
        parts.arrange(DOWN, buff=0.25)
        self._fit_stage(parts)
        new = Group(parts)
        anim = self._to_stage(Group(VGroup(axes, labels, keys, *parts[2:])))
        # The curves draw after the axes appear.
        self.stage_items.add(curves)
        curves.set_z_index(Z_MARK + 11)
        return AnimationGroup(anim, Create(curves, lag_ratio=0.2), lag_ratio=0.6)

    def process(self, steps, title: str | None = None, cycle: bool = False):
        """Steps joined by arrows: a chain (snaking into rows) or a cycle."""
        cx, cy, w, h = self.STAGE
        steps = [str(x) for x in list(steps)[:8]]
        boxes = VGroup()
        tones = [P.SAND, P.RIVER, P.GREEN, P.ROSE, P.GOLD, P.TEAL, P.VIOLET, P.DUNE]
        for i, step in enumerate(steps):
            text = T(wrap(step, 16), 18, P.CREAM, line_spacing=0.85)
            box = RoundedRectangle(corner_radius=0.15, width=max(text.width + 0.4, 1.9), height=text.height + 0.4,
                                   stroke_color=tones[i % 8], stroke_width=3, fill_color=tones[i % 8], fill_opacity=0.14)
            boxes.add(VGroup(box, text.move_to(box)))
        if cycle:
            radius = 1.9 + 0.1 * len(boxes)
            for i, b in enumerate(boxes):
                angle = PI / 2 - 2 * PI * i / len(boxes)
                b.move_to([radius * math.cos(angle), radius * 0.8 * math.sin(angle), 0])
        else:
            per_row = 3 if len(boxes) > 4 else len(boxes) if len(boxes) <= 3 else 2
            rows = [boxes[i:i + per_row] for i in range(0, len(boxes), per_row)]
            for r, row in enumerate(rows):
                group = VGroup(*row).arrange(RIGHT if r % 2 == 0 else LEFT, buff=0.7)
                group.move_to(DOWN * r * 1.6)
        arrows = VGroup()
        pairs = list(zip(boxes, boxes[1:])) + ([(boxes[-1], boxes[0])] if cycle and len(boxes) > 2 else [])
        for a, b in pairs:
            arrows.add(Arrow(a.get_center(), b.get_center(), buff=0.0, color=P.MUTED, stroke_width=4,
                             max_tip_length_to_length_ratio=0.2)
                       .put_start_and_end_on(*self._edge_points(a, b)))
        drawing = VGroup(arrows, boxes)
        parts = VGroup(drawing)
        if title:
            parts.add(fit(T(title.upper() if TH["upper"] else title, 26, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
            parts.arrange(UP, buff=0.4)
        self._fit_stage(parts)
        return self._to_stage(Group(parts))

    @staticmethod
    def _edge_points(a, b):
        """Where an arrow between two boxes leaves one and meets the other."""
        start, end = a.get_center(), b.get_center()
        direction = end - start
        length = np.linalg.norm(direction) or 1.0
        unit = direction / length

        def exit_point(box, sign):
            half_w, half_h = box[0].width / 2, box[0].height / 2
            scale = min(half_w / (abs(unit[0]) or 1e-9), half_h / (abs(unit[1]) or 1e-9))
            return box.get_center() + sign * unit * (scale + 0.08)

        return exit_point(a, 1), exit_point(b, -1)

    def big_timeline(self, events, title: str | None = None):
        """A timeline across the stage: dates large, labels alternating above and below."""
        cx, cy, w, h = self.STAGE
        events = list(events)[:7]
        width = w - 0.6
        line = Line(LEFT * width / 2, RIGHT * width / 2, color=P.MUTED, stroke_width=4)
        marks = VGroup()
        for i, (date, label) in enumerate(events):
            x = -width / 2 + width * (i + 0.5) / max(len(events), 1)
            dot = Dot([x, 0, 0], radius=0.1, color=P.SAND)
            d = T(str(date), 24, P.SAND, font=TH["serif"], weight=BOLD)
            lab = fit(T(wrap(str(label), 14), 15, P.CREAM, line_spacing=0.85), width / max(len(events), 1) + 0.3)
            if i % 2 == 0:
                d.next_to(dot, UP, buff=0.15)
                lab.next_to(d, UP, buff=0.08)
            else:
                d.next_to(dot, DOWN, buff=0.15)
                lab.next_to(d, DOWN, buff=0.08)
            marks.add(VGroup(dot, d, lab))
        drawing = VGroup(line, marks)
        parts = VGroup(drawing)
        if title:
            parts.add(fit(T(title.upper() if TH["upper"] else title, 26, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
            parts.arrange(UP, buff=0.5)
        self._fit_stage(parts)
        return self._to_stage(Group(parts))

    def quote(self, text: str, who: str = ""):
        """A quotation, large, with who said it."""
        cx, cy, w, h = self.STAGE
        mark = T("“", 120, P.SAND, font=TH["serif"], weight=BOLD)
        body = fit(T(wrap(text, 34), 28, P.CREAM, font=TH["serif"], line_spacing=0.95), w - 0.6)
        parts = VGroup(mark, body)
        if who:
            parts.add(fit(T(f"— {who}", 20, P.MUTED), w - 0.6))
        parts.arrange(DOWN, buff=0.25, aligned_edge=LEFT)
        self._fit_stage(parts)
        return self._to_stage(Group(parts))

    def figure(self, path: str, caption: str = "", where: str = "panel"):
        """A figure from a source document: in the panel, or across the frame for one beat."""
        if where == "stage":
            return self.stage_image(path, caption)
        image = ImageMobject(path)
        if where == "full":
            image.scale_to_fit_height(5.4)
            if image.width > 12.4:
                image.scale_to_fit_width(12.4)
            back = Rectangle(width=config.frame_width, height=config.frame_height, fill_color=P.BG,
                             fill_opacity=0.96, stroke_width=0)
            parts = [back, image.move_to(UP * 0.45)]
            if caption:
                parts.append(fit(T(caption, 16, P.MUTED), 12.4).next_to(image, DOWN, buff=0.15))
            group = Group(*parts)
            group.set_z_index(Z_CARD)
            self._new_figure = group
            return FadeIn(group)
        image.scale_to_fit_width(TEXT_W - 0.1)
        if image.height > 2.6:
            image.scale_to_fit_height(2.6)
        image.move_to(RIGHT * self.TEXT_LEFT + UP * self.panel_y, aligned_edge=UL)
        group = Group(image)
        if caption:
            group.add(fit(T(wrap(caption, 44), 13, P.MUTED, line_spacing=0.85), TEXT_W - 0.1)
                      .next_to(image, DOWN, aligned_edge=LEFT, buff=0.08))
        group.set_z_index(Z_PANEL_TEXT)
        self.panel_y = group.get_bottom()[1] - 0.3
        self.panel_images.add(group)
        anim = FadeIn(group, shift=UP * 0.12)
        anim.panel_item = True
        return anim

    # ---------------- cards ----------------
    def chapter_card(self, num: int, title: str, sub: str) -> VGroup:
        n = T(f"{num:02d}", 96, P.TITLE if TH.get("highlight") else P.SAND, font=TH["serif"], weight=BOLD)
        t = fit(T(title.upper() if TH["upper"] else title, 54, P.CREAM, font=TH["serif"], weight=BOLD), 12)
        s = fit(T(sub, 22, P.MUTED), 12)
        rule = Line(LEFT * 1.6, RIGHT * 1.6, color=TH.get("highlight", P.SAND),
                    stroke_width=6 if TH.get("highlight") else 2)
        card = VGroup(n, rule, t, s).arrange(DOWN, buff=0.28).move_to(UP * 0.35)
        if STYLE == "cardboard":
            paper = Rectangle(width=max(card.width + 1.4, 7), height=card.height + 1.0, fill_color=P.PANEL,
                              fill_opacity=1, stroke_width=0).move_to(card)
            shadow = paper.copy().set_fill("#000000", 0.3).shift(RIGHT * 0.1 + DOWN * 0.1)
            tape = Rectangle(width=1.6, height=0.38, fill_color="#F7F1DE", fill_opacity=0.75,
                             stroke_width=0).move_to(paper.get_top()).rotate(-0.06)
            back = VGroup(shadow, paper, tape).rotate(0.015)
            card = VGroup(n, back, t, s)
            card.set_z_index(Z_CARD + 1)
            back.set_z_index(Z_CARD - 1)
            return card
        if STYLE == "blueprint":
            frame = DashedVMobject(SurroundingRectangle(card, buff=0.45, color=P.MUTED, stroke_width=1.5),
                                   num_dashes=80)
            card = VGroup(n, VGroup(rule, frame), t, s)
        card.set_z_index(Z_CARD)
        return card

    def on_stage(self) -> list:
        """What a chapter put up: everything but the backdrop and chrome."""
        keep = {id(m) for m in self.chrome}
        keep.update(id(m) for m in self.mobjects if getattr(m, "z_index", 0) == Z_BACK)
        if self.cap is not None:
            keep.add(id(self.cap))
        return [m for m in self.mobjects if id(m) not in keep and m is not self.chrome]

    def chapter(self, num: int, title: str, sub: str, narration: str) -> None:
        """A full-frame title card over the first beat of a chapter.

        A chapter starts on an empty stage. In one scene holding a whole
        lecture, the last chapter's map and panel are cleared first rather
        than left under the card.
        """
        if self.on_stage():
            self.outro_fade(0.6)
        self._log("chapter", number=num, title=title)
        if self.SECTIONS:
            self.section(num)
        card = self.chapter_card(num, title, sub)
        if TH["anim"] in ("write", "type"):
            intro = LaggedStart(Write(card[0]), Create(card[1]), Write(card[2]), FadeIn(card[3]), lag_ratio=0.3)
        elif TH["anim"] == "drop":
            intro = LaggedStart(FadeIn(card[1], shift=DOWN * 0.6, scale=1.1), FadeIn(card[0]), FadeIn(card[2]),
                                FadeIn(card[3]), lag_ratio=0.25)
        else:
            intro = LaggedStart(FadeIn(card[0], scale=1.2), GrowFromCenter(card[1]),
                                FadeIn(card[2], shift=UP * 0.2), FadeIn(card[3]), lag_ratio=0.3)
        self.beat(narration, intro, rt=2.2)
        self.play(FadeOut(card, shift=UP * 0.3), run_time=0.8)

    def title_slide(self, title: str, sub: str = "", tag: str = "AN ILLUSTRATED LECTURE", narration: str = ""):
        head = T(title.upper() if TH["upper"] else title, 88, P.SAND, font=TH["serif"], weight=BOLD)
        fit(head, 12)
        line = T(sub, 30, P.CREAM, font=TH["serif"]) if sub else VGroup()
        fit(line, 12)
        label = T(tag, 16, P.MUTED, weight=BOLD)
        group = VGroup(label, head, line).arrange(DOWN, buff=0.28).move_to(UP * 0.4)
        group.set_z_index(Z_CARD)
        self.beat(narration or f"{title}. {sub}", LaggedStart(FadeIn(label), Write(head), FadeIn(line, shift=UP * 0.2),
                                                             lag_ratio=0.35), rt=3.0)
        self.play(FadeOut(group, shift=UP * 0.3), run_time=0.8)

    def recap(self, points, narration=None) -> None:
        """Up to eight idea cards in a grid, one beat each."""
        palette = [P.SAND, P.MOUNT, P.GREEN, P.DUNE, P.RIVER, P.TEAL, P.OLIVE, P.ROSE]
        cards = VGroup()
        for i, (head, body) in enumerate(points[:8]):
            color = palette[i % len(palette)]
            box = RoundedRectangle(corner_radius=0.14, width=3.25, height=1.7, stroke_color=color, stroke_width=2,
                                   fill_color=P.PANEL if STYLE == "cardboard" else color,
                                   fill_opacity=1 if STYLE == "cardboard" else 0.08)
            tt = fit(T(head, 24, color, font=TH["serif"], weight=BOLD), 2.95)
            ss = fit(T(wrap(body, 24), 16, P.CREAM, line_spacing=0.9), 2.95)
            VGroup(tt, ss).arrange(DOWN, buff=0.14).move_to(box)
            cards.add(VGroup(box, tt, ss))
        cols = 4 if len(cards) > 3 else len(cards)
        rows = math.ceil(len(cards) / max(cols, 1))
        cards.arrange_in_grid(rows=rows, cols=cols, buff=(0.2, 0.3)).move_to(UP * 0.35)
        cards.set_z_index(Z_PANEL_TEXT)
        lines = narration or [f"{h}. {b}." for h, b in points[:8]]
        for card, line in zip(cards, lines):
            self.beat(line, FadeIn(card, shift=UP * 0.2, scale=0.95), rt=1.0)
        self.play(FadeOut(cards, shift=UP * 0.3), run_time=1.0)
        self.clear_caption()

    # ---------------- panel diagrams ----------------
    def compare(self, left: tuple, right: tuple, left_tone: str = "friendly", right_tone: str = "enemy"):
        """Two big numbers side by side: (value, label) each."""
        cols = VGroup()
        for (value, label), tone in ((left, left_tone), (right, right_tone)):
            v = fit(T(str(value), 38, role(tone), font=TH["serif"], weight=BOLD), 2.4)
            lab = fit(T(wrap(str(label), 18), 15, P.MUTED), 2.4)
            lab.next_to(v, DOWN, aligned_edge=LEFT, buff=0.08)
            cols.add(VGroup(v, lab))
        cols.arrange(RIGHT, buff=0.4, aligned_edge=UP)
        group = self._stack(cols, 0.3)
        return self.reveal(group, None)

    def timeline(self, events, tone: str = "accent"):
        """A horizontal time line in the panel: [(date, label), ...], labels alternating."""
        events = list(events)[:6]
        width = 4.8
        line = Line(LEFT * width / 2, RIGHT * width / 2, color=P.MUTED, stroke_width=2)
        parts = VGroup(line)
        for i, (date, label) in enumerate(events):
            x = -width / 2 + width * (i + 0.5) / max(len(events), 1)
            tick = Dot([x, 0, 0], radius=0.06, color=role(tone))
            d = T(str(date), 14, role(tone), weight=BOLD)
            lab = fit(T(wrap(str(label), 14), 12, P.CREAM, line_spacing=0.8), 1.2)
            if i % 2 == 0:
                d.next_to(tick, UP, buff=0.1)
                lab.next_to(d, UP, buff=0.05)
            else:
                d.next_to(tick, DOWN, buff=0.1)
                lab.next_to(d, DOWN, buff=0.05)
            parts.add(VGroup(tick, d, lab))
        group = self._stack(parts, 0.3)
        return AnimationGroup(Create(line), LaggedStart(*[FadeIn(p, shift=UP * 0.05) for p in parts[1:]],
                                                         lag_ratio=0.2), lag_ratio=0.3)

    def network(self, nodes, edges=(), tone: str = "accent"):
        """People and alliances: labelled nodes on a ring, edges between them.

        nodes: names, or (name, tone) pairs. edges: (a, b) or (a, b, label).
        """
        nodes = [(n, tone) if isinstance(n, str) else (n[0], n[1] if len(n) > 1 else tone) for n in list(nodes)[:7]]
        radius = 1.25
        centre = np.array([self.TEXT_LEFT + 2.5, self.panel_y - 1.55, 0])
        at = {}
        dots = VGroup()
        for i, (name, node_tone) in enumerate(nodes):
            angle = PI / 2 + 2 * PI * i / max(len(nodes), 1)
            p = centre + radius * np.array([math.cos(angle), math.sin(angle), 0])
            at[name] = p
            dot = Circle(radius=0.13, color=role(node_tone), fill_color=role(node_tone), fill_opacity=0.85,
                         stroke_width=1.5).move_to(p)
            lab = fit(T(str(name), 13, P.CREAM), 1.6)
            lab.next_to(dot, UP if p[1] >= centre[1] else DOWN, buff=0.06)
            dots.add(VGroup(dot, lab))
        lines = VGroup()
        for edge in edges:
            a, b = edge[0], edge[1]
            if a not in at or b not in at:
                continue
            ln = Line(at[a], at[b], color=P.MUTED, stroke_width=2).set_opacity(0.8)
            ln.set_z_index(Z_PANEL_TEXT - 1)
            parts = VGroup(ln)
            if len(edge) > 2 and edge[2]:
                parts.add(fit(T(str(edge[2]), 11, P.MUTED), 1.4).move_to(ln.get_center() + UP * 0.12))
            lines.add(parts)
        dots.set_z_index(Z_PANEL_TEXT)
        lines.set_z_index(Z_PANEL_TEXT - 1)
        self.panel_items.add(VGroup(lines, dots))
        self.panel_y = centre[1] - radius - 0.55
        anim = AnimationGroup(LaggedStart(*[GrowFromCenter(d[0]) for d in dots], lag_ratio=0.15),
                              LaggedStart(*[FadeIn(d[1]) for d in dots], lag_ratio=0.15),
                              LaggedStart(*[Create(e[0]) for e in lines], lag_ratio=0.15),
                              *[FadeIn(e[1]) for e in lines if len(e) > 1])
        anim.panel_item = True
        return anim

    def credits(self, line: str, note: str = "Some boundaries and figures are simplified or approximate for teaching.",
                seconds: float = 3.0, extra: str = "") -> None:
        """The closing credits. `extra` carries photo attributions, which their licences require."""
        self.clear_caption()
        if USED_ICONS:
            import icons

            note = f"{note}  {icons.credit(USED_ICONS)}."
        credit = fit(T(line, 14, P.MUTED), 13).move_to(DOWN * 1.9)
        small = fit(T(note, 13, P.MUTED), 13).next_to(credit, DOWN, buff=0.15)
        parts = [credit, small]
        if extra:
            parts.append(fit(T(wrap(extra, 150), 11, P.MUTED, line_spacing=0.8), 13).next_to(small, DOWN, buff=0.15))
        self.play(*[FadeIn(p) for p in parts], run_time=1.0)
        self.wait(seconds + (2.0 if extra else 0.0))
        self.play(*[FadeOut(p) for p in parts], run_time=0.8)

    def outro_fade(self, run_time: float = 1.0) -> None:
        """Fade everything a chapter added; keep the backdrop and chrome."""
        going = self.on_stage()
        self.clear_caption()
        if going:
            self.play(*[FadeOut(m) for m in going], run_time=run_time)
        self.panel_items = VGroup()
        self.panel_images = Group()
        self.stage_items = Group()
        self._full_figure = self._new_figure = None
        self._map_on = False
        self.panel_y = 2.35


class MapLecture(Lecture):
    """A lecture over one region's map, with neighbours, state lines and markers.

    REGION names the focus: dict(country="India"), dict(country="India",
    view="ind") for India's own view of its borders, or dict(state="Rajasthan",
    country="India").
    """

    REGION: dict = dict(country="India")
    MAP_CENTER = (-3.0, 0.2)
    MAP_SIZE = (6.3, 6.5)
    TEXT_LEFT = TEXT_X
    PANEL_BOX = (PANEL_X, 7.05)

    # ---------------- region ----------------
    @property
    def focus(self):
        if not hasattr(self, "_focus"):
            region = self.REGION
            if region.get("state"):
                self._focus = state(region["state"], region.get("country"))
            else:
                self._focus = country(region["country"], region.get("view"))
        return self._focus

    @property
    def mainland(self):
        g = self.focus
        return max(g.geoms, key=lambda p: p.area) if g.geom_type == "MultiPolygon" else g

    # A lon/lat box to fit the map to instead of the whole focus: a
    # battlefield a few kilometres across inside its province.
    FRAME_BBOX: tuple | None = None

    @property
    def frame(self) -> MapFrame:
        if not hasattr(self, "_frame"):
            height, width = self.MAP_SIZE
            fit_to = _box(self.FRAME_BBOX) if self.FRAME_BBOX else self.mainland
            self._frame = MapFrame(fit_to, center=self.MAP_CENTER, height=height, width=width)
        return self._frame

    def use_frame(self, bbox: tuple | None = None) -> None:
        """Refit the map: to a box, or back to the whole focus. Units stay behind."""
        self.FRAME_BBOX = tuple(bbox) if bbox else None
        if hasattr(self, "_frame"):
            del self._frame
        self.units = {}

    def lonlat_bounds(self, margin=None):
        if self.FRAME_BBOX:
            lon0, lat0, lon1, lat1 = self.FRAME_BBOX
            pad = max(lon1 - lon0, lat1 - lat0) * (0.6 if margin is None else margin)
            return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)
        lon0, lat0, lon1, lat1 = self.focus.bounds
        pad = margin if margin is not None else max(lon1 - lon0, lat1 - lat0) * 0.45
        return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)

    def at(self, where) -> tuple[float, float]:
        """An anchor, a place name, or a (lon, lat) pair, as (lon, lat)."""
        if isinstance(where, str) and where in self.ANCHORS:
            lon, lat = self.ANCHORS[where]
            return float(lon), float(lat)
        if isinstance(where, str):
            return place(where, self.REGION.get("country"))
        lon, lat = where
        return float(lon), float(lat)

    # ---------------- layers ----------------
    def base(self, opacity: float = 0.08):
        """(neighbours, internal lines, focus outline), styled and layered."""
        fr = self.frame
        region = self.REGION
        bounds = self.lonlat_bounds()
        home = region.get("country")
        nb = VGroup()
        style = dict(fill_color=TH["nb_fill"], fill_opacity=1, stroke_color=TH["nb_stroke"], stroke_width=1)
        if region.get("state"):
            for name, geom in states_of(home or ""):
                if _norm(name) == _norm(region["state"]):
                    continue
                piece = geom.intersection(_box(bounds))
                if not piece.is_empty:
                    nb.add(fr.poly(piece, simplify=0.01, min_area=0.001, **style))
            for name, geom in countries_in(bounds, region.get("view"), exclude=[home] if home else []):
                nb.add(fr.poly(geom, simplify=0.01, min_area=0.001, **style))
            inner = VGroup()
        else:
            for name, geom in countries_in(bounds, region.get("view"), exclude=[region["country"]]):
                nb.add(fr.poly(geom, simplify=0.01, min_area=0.001, **style))
            inner = VGroup(*[
                fr.poly(geom, simplify=0.008, min_area=0.0003, fill_opacity=0, stroke_color=TH["st_stroke"],
                        stroke_width=0.8)
                for _, geom in states_of(region["country"])
            ])
        land = TH.get("land")
        outline = fr.poly(self.focus, simplify=0.004, min_area=0.00005, fill_color=P.SAND,
                          fill_opacity=0 if land else opacity,
                          stroke_color=TH.get("map_stroke", P.CREAM if land else P.SAND), stroke_width=2.2)
        if land:
            under = VGroup()
            if TH.get("shadow"):
                shadow = fr.poly(self.focus, simplify=0.006, min_area=0.0003, fill_color="#000000",
                                 fill_opacity=0.32, stroke_width=0)
                shadow.shift(RIGHT * TH["shadow"] + DOWN * TH["shadow"])
                under.add(shadow)
            under.add(fr.poly(self.focus, simplify=0.006, min_area=0.00005, fill_color=land, fill_opacity=1,
                              stroke_width=0))
            under.set_z_index(Z_LAND)
            nb.add(under)
        inner.set_z_index(Z_LINES)
        outline.set_z_index(Z_OUTLINE)
        self.layers = SimpleNamespace(neighbours=nb, lines=inner, outline=outline)
        return nb, inner, outline

    def show_map(self, panel: bool = True, run_time: float = 1.4) -> None:
        """Draw the base map (and the panel) in one move."""
        self._map_on = True
        nb, inner, outline = self.base()
        anims = [FadeIn(nb), Create(outline)]
        if len(inner):
            anims.append(FadeIn(inner))
        if panel:
            self.panel = self.panel_bg()
            anims.append(FadeIn(self.panel))
        self.play(*anims, run_time=run_time)

    def region_fill(self, geom, color: str, opacity: float = 0.6, z: float = Z_FILL) -> VGroup:
        m = self.frame.poly(_valid(geom).intersection(self.focus), simplify=0.006, min_area=0.002,
                            fill_color=color, fill_opacity=opacity, stroke_width=0)
        m.set_z_index(z)
        return m

    def fill_state(self, name: str, color: str | None = None, opacity: float = 0.6):
        """FadeIn one first-level division of the focus country."""
        m = self.region_fill(state(name, self.REGION.get("country")), color or P.SAND, opacity)
        return FadeIn(m)

    def river(self, name: str, color: str | None = None, width: float = 5):
        """Create a Natural Earth river, cut to the map's box."""
        m = self.frame.line(river(name, self.lonlat_bounds()), stroke_color=color or P.RIVER, stroke_width=width)
        m.set_z_index(7)
        return Create(m)

    def path(self, lonlats, color: str | None = None, width: float = 5, smooth: bool = True):
        """Create a hand-digitised line (a ridge, a canal) from lon/lat points."""
        m = self.frame.path(lonlats, smooth=smooth, stroke_color=color or P.HI, stroke_width=width)
        m.set_z_index(8)
        return Create(m)

    def flow(self, lonlats, color: str | None = None, width: float = 7):
        """A curved arrow along lon/lat points: a smoothed path and a tip."""
        color = color or P.RIVER
        fr = self.frame
        line = fr.path(lonlats, stroke_color=color, stroke_width=width)
        a, b = fr.pt(*lonlats[-2]), fr.pt(*lonlats[-1])
        tip = Triangle(fill_color=color, fill_opacity=1, stroke_width=0).scale(0.14)
        tip.rotate(math.atan2(b[1] - a[1], b[0] - a[0]) - PI / 2).move_to(b)
        group = VGroup(line, tip)
        group.set_z_index(15)
        return AnimationGroup(Create(line), FadeIn(tip), lag_ratio=0.8)

    def marker(self, where, label: str | None = None, color: str | None = None, d=RIGHT, size: float = 15,
               r: float = 0.055) -> VGroup:
        """Dot, halo and label at a place name or (lon, lat)."""
        color = color or P.CREAM
        p = self.frame.pt(*self.at(where))
        dot = Dot(p, radius=r, color=color)
        halo = Circle(radius=r * 2.2, color=color, stroke_width=1.5, stroke_opacity=0.6).move_to(p)
        text = T(label or (where if isinstance(where, str) else ""), size, color)
        text.next_to(dot, d, buff=r * 2.2 + 0.05)
        # A label that would cross the panel or the frame flips to the left.
        if text.get_right()[0] > PANEL_X - 0.05 or text.get_left()[0] < -config.frame_width / 2 + 0.2:
            text.next_to(dot, LEFT if d is RIGHT else RIGHT, buff=r * 2.2 + 0.05)
        group = VGroup(halo, dot, text)
        group.set_z_index(Z_MARK)
        return group

    def pop(self, m: VGroup):
        return LaggedStart(GrowFromCenter(m[1]), GrowFromCenter(m[0]), FadeIn(m[2], shift=UP * 0.05),
                           lag_ratio=0.25)

    def mark(self, where, label=None, color=None, d=RIGHT):
        """Build and pop a marker: the one-call form used by beat scripts."""
        return self.pop(self.marker(where, label, color, d))

    def graticule(self, lat: float | None = None, lon: float | None = None, color: str | None = None,
                  label: str | None = None):
        """A dashed parallel or meridian through the projection, so it curves."""
        lon0, lat0, lon1, lat1 = self.lonlat_bounds(margin=4)
        if lat is not None:
            pts = [(x, lat) for x in np.linspace(lon0, lon1, 40)]
        else:
            pts = [(lon, y) for y in np.linspace(lat0, lat1, 30)]
        # Only the stretch left of the panel is ever seen, so that is all that
        # is drawn, and the label sits at its visible end rather than off-frame.
        screen = self.frame.xy(*np.array(pts).T)
        seen = [p for p, (x, y) in zip(pts, screen)
                if -config.frame_width / 2 + 0.2 < x < PANEL_X - 0.1 and abs(y) < config.frame_height / 2 - 0.2]
        pts = seen if len(seen) >= 2 else pts
        line = DashedVMobject(self.frame.path(pts, stroke_color=color or P.MUTED, stroke_width=2), num_dashes=50)
        group = VGroup(line)
        if label:
            tag = T(label, 15, color or P.MUTED)
            end = self.frame.pt(*pts[-1]) if lat is not None else self.frame.pt(*pts[0])
            if lat is not None:
                tag.next_to(end, UP, buff=0.06).align_to(end, RIGHT)
            else:
                tag.next_to(end, RIGHT, buff=0.08)
            group.add(tag)
        group.set_z_index(12)
        return AnimationGroup(Create(line), *(FadeIn(m) for m in group[1:]))

    def dim(self, *keep, opacity: float = 0.15):
        """Fade every filled layer except `keep` down to `opacity`."""
        fills = [m for m in self.mobjects if getattr(m, "z_index", 0) == Z_FILL and m not in keep]
        return [m.animate.set_fill(opacity=opacity) for m in fills]

    # ---------------- battle operations ----------------
    # Named points a script can use instead of lon/lat: battlefield anchors
    # from a region pack. `at()` looks here before the gazetteer.
    ANCHORS: dict = {}

    UNIT_W, UNIT_H = 0.52, 0.34

    def unit(self, uid: str, where, label: str | None = None, side: str = "friendly", kind: str = "infantry",
             strength: str | None = None):
        """A unit counter: a filled box in the side's colour with a symbol, labelled below."""
        if not hasattr(self, "units"):
            self.units = {}
        colour = role(side)
        p = self.frame.pt(*self.at(where))
        unit_w, unit_h = tok("unit_width", self.UNIT_W), tok("unit_height", self.UNIT_H)
        box = Rectangle(width=unit_w, height=unit_h, fill_color=colour, fill_opacity=0.9,
                        stroke_color=P.role_ink, stroke_width=1.5).move_to(p)
        w, h = unit_w / 2 - 0.05, unit_h / 2 - 0.04
        ink = P.BG
        if kind == "cavalry":
            symbol = VGroup(Line(p + [-w, -h, 0], p + [w, h, 0], color=ink, stroke_width=2))
        elif kind == "artillery":
            symbol = VGroup(Dot(p, radius=0.06, color=ink))
        elif kind == "navy":
            symbol = VGroup(Line(p + [-w, 0, 0], p + [w, 0, 0], color=ink, stroke_width=2),
                            Line(p + [0, -h, 0], p + [0, h, 0], color=ink, stroke_width=2))
        else:  # infantry: the crossed box
            symbol = VGroup(Line(p + [-w, -h, 0], p + [w, h, 0], color=ink, stroke_width=2),
                            Line(p + [-w, h, 0], p + [w, -h, 0], color=ink, stroke_width=2))
        text = fit(T(label or uid, 13, colour, weight=BOLD), 1.8).next_to(box, DOWN, buff=0.06)
        parts = VGroup(box, symbol, text)
        if strength:
            parts.add(T(str(strength), 11, P.MUTED).next_to(text, DOWN, buff=0.02))
        parts.set_z_index(Z_MARK + 1)
        self.units[uid] = parts
        return FadeIn(parts, scale=0.8)

    def _unit(self, uid: str):
        found = getattr(self, "units", {}).get(uid)
        if found is None:
            raise KeyError(f"no unit {uid!r} on the map; place it with unit first")
        return found

    def move_unit(self, uid: str, where):
        """Move a unit so its box sits at a place, anchor or (lon, lat)."""
        parts = self._unit(uid)
        target = self.frame.pt(*self.at(where))
        return parts.animate.shift(target - parts[0].get_center())

    def charge(self, uid: str, where):
        """A move the length of which is the point: the same as move, faster."""
        return self.move_unit(uid, where)

    def rout(self, uid: str, direction=(0.0, -1.0)):
        """A unit breaks: it falls back and fades."""
        parts = self._unit(uid)
        return parts.animate.shift(np.array([direction[0], direction[1], 0.0]) * 0.6).set_opacity(0.25)

    def volley(self, source: str, target=None, tone: str | None = None):
        """Fire from a unit: short dashed lines toward the target, flashing out."""
        parts = self._unit(source)
        start = parts[0].get_center()
        if target is None:
            end = start + RIGHT * 1.2
        elif isinstance(target, str) and target in getattr(self, "units", {}):
            end = self.units[target][0].get_center()
        else:
            end = self.frame.pt(*self.at(target))
        direction = end - start
        normal = np.array([-direction[1], direction[0], 0.0])
        length = np.linalg.norm(direction) or 1.0
        normal = normal / length * 0.12
        shots = VGroup(*[
            DashedVMobject(Line(start + normal * k, start + direction * 0.85 + normal * k,
                                color=role(tone or "highlight"), stroke_width=2.5), num_dashes=8)
            for k in (-1, 0, 1)
        ])
        shots.set_z_index(Z_MARK + 2)
        return AnimationGroup(Create(shots), FadeOut(shots), lag_ratio=1.0)

    def clock(self, time: str):
        """A clock in the map's corner, its hands turning to `time` (HH:MM)."""
        hours, minutes = (int(x) for x in str(time).split(":")[:2])
        centre = np.array([-6.35, 2.95, 0.0])
        if not hasattr(self, "_clock"):
            face = Circle(radius=0.36, color=P.role_ink, stroke_width=2, fill_color=P.BG, fill_opacity=0.85)
            face.move_to(centre)
            ticks = VGroup(*[Line(centre + 0.3 * np.array([math.cos(a), math.sin(a), 0]),
                                  centre + 0.36 * np.array([math.cos(a), math.sin(a), 0]),
                                  color=P.MUTED, stroke_width=1.5)
                             for a in np.linspace(0, 2 * PI, 12, endpoint=False)])
            hour = Line(centre, centre + UP * 0.2, color=P.role_ink, stroke_width=3)
            minute = Line(centre, centre + UP * 0.3, color=P.role_accent, stroke_width=2)
            label = T(f"{hours:02d}:{minutes:02d}", 13, P.role_ink, weight=BOLD).next_to(face, RIGHT, buff=0.12)
            self._clock = SimpleNamespace(face=VGroup(face, ticks), hour=hour, minute=minute, label=label,
                                          at=(0, 0))
            for m in (self._clock.face, hour, minute, label):
                m.set_z_index(Z_CHROME - 1)
            # Start at 12:00 and turn to the first time.
            anims = [FadeIn(self._clock.face), FadeIn(hour), FadeIn(minute), FadeIn(label)]
            first = self._turn(hours, minutes)
            return AnimationGroup(AnimationGroup(*anims), first, lag_ratio=1.0)
        return self._turn(hours, minutes)

    def _turn(self, hours: int, minutes: int):
        from manim import Rotate

        c = self._clock
        h0, m0 = c.at
        total0 = h0 * 60 + m0
        total1 = hours * 60 + minutes
        if total1 < total0:
            total1 += 12 * 60
        delta = total1 - total0
        c.at = (hours % 12, minutes)
        centre = c.face[0].get_center()
        new_label = T(f"{hours:02d}:{minutes:02d}", 13, P.role_ink, weight=BOLD).move_to(c.label)
        new_label.set_z_index(Z_CHROME - 1)
        old = c.label
        c.label = new_label
        return AnimationGroup(
            Rotate(c.minute, angle=-2 * PI * delta / 60, about_point=centre),
            Rotate(c.hour, angle=-2 * PI * delta / 720, about_point=centre),
            FadeOut(old), FadeIn(new_label),
        )

    def route(self, points, tone: str = "accent", labels=None):
        """A dated route through places or (lon, lat): a curved arrow, waypoint labels."""
        lonlats = [self.at(p) for p in points]
        anim = self.flow(lonlats, role(tone))
        tags = VGroup()
        for p, label in zip(lonlats, labels or []):
            if not label:
                continue
            tag = T(str(label), 12, role(tone), weight=BOLD).next_to(self.frame.pt(*p), UP, buff=0.08)
            tags.add(tag)
        if not len(tags):
            return anim
        tags.set_z_index(Z_MARK)
        return AnimationGroup(anim, LaggedStart(*[FadeIn(t) for t in tags], lag_ratio=0.3), lag_ratio=0.4)

    def icon(self, name: str, where=None, color: str | None = None, size: float = 0.6, label: str | None = None):
        """An icon on the map at a place, or one at each of several places.

        where: a place name, (lon, lat), or a list of either -- "sugarcane in
        Meerut, Muzaffarnagar and Saharanpur" is three icons that pop in turn.
        """
        spots = where if isinstance(where, (list, tuple)) and where and not isinstance(where[0], (int, float)) else [where]
        group = VGroup()
        for spot in spots:
            mob = icon_mob(name, color, height=size)
            mob.move_to(self.frame.pt(*self.at(spot)))
            group.add(mob)
        if label:
            tag = T(label, 14, role(color or "ink"), weight=BOLD).next_to(group[0], DOWN, buff=0.06)
            group.add(tag)
        group.set_z_index(Z_MARK + 1)
        return LaggedStart(*[GrowFromCenter(m) for m in group], lag_ratio=0.2)

    def highlight(self, target):
        """Draw the eye: a unit or a marker pulses."""
        if isinstance(target, str) and target in getattr(self, "units", {}):
            return Indicate(self.units[target][0], color=P.role_highlight, scale_factor=1.25)
        p = self.frame.pt(*self.at(target))
        ring = Circle(radius=0.28, color=P.role_highlight, stroke_width=3).move_to(p)
        ring.set_z_index(Z_MARK + 2)
        return AnimationGroup(Create(ring), FadeOut(ring, scale=1.6), lag_ratio=1.0)


def _box(bounds):
    from shapely.geometry import box

    return box(*bounds)


__all__ = [name for name in globals() if not name.startswith("_") or name == "_box"]
