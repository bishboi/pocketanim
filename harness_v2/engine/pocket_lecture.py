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

Narration: each beat's line is spoken by Gemini 3.8 Flash-Lite TTS (gemini_tts.py; Chirp 3 HD with PANIM_TTS=chirp), and its
measured length times the beat. With PANIM_VOICE=silent there is no audio: the
length is estimated from the word count and the picture still plays.
"""

from __future__ import annotations

import hashlib
import math
import json
import os
import re
import shutil
import threading
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
    VGroup, VMobject, Write, config, Ellipse, Polygon,
)

HERE = Path(__file__).resolve().parent

# Without LaTeX, MathTex, Tex and axis numbers in a scene are drawn from Pango text instead of failing with
# "No such file or directory: 'latex'" (nolatex.py).
import nolatex  # noqa: E402
from manim.utils.rate_functions import ease_out_cubic, ease_out_expo  # noqa: E402

nolatex.install()

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
        track="#E0E0DA", anim="write", map_stroke="#1B1B1B", voice="am_adam",
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
        track="#2E5243", anim="write", map_stroke="#F4F0E4", voice="am_michael",
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
    # The art styles' picture fonts (artstyle.ART_FONTS).
    "SourceSans3[wght].ttf": "ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf",
    "ArchitectsDaughter-Regular.ttf": "ofl/architectsdaughter/ArchitectsDaughter-Regular.ttf",
    "Quicksand[wght].ttf": "ofl/quicksand/Quicksand%5Bwght%5D.ttf",
    "Caveat[wght].ttf": "ofl/caveat/Caveat%5Bwght%5D.ttf",
    # Hindi in typeset equations (XeLaTeX, nolatex.SCRIPT_FONTS).
    "Hind-Regular.ttf": "ofl/hind/Hind-Regular.ttf",
    "Hind-Bold.ttf": "ofl/hind/Hind-Bold.ttf",
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
builtins_range = range          # range(), where a parameter is called range (big_timeline)
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
    merged = {**base, **{k: v for k, v in theme.items() if k not in ("pal", "base")}, "pal": pal,
              "base_style": theme.get("base", "atlas")}
    THEMES[name] = merged


def _luminance(colour: str) -> float:
    """WCAG relative luminance of a #hex colour."""
    h = str(colour).lstrip("#")[:6]
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two #hex colours (1 to 21)."""
    lo, hi = sorted((_luminance(a), _luminance(b)))
    return (hi + 0.05) / (lo + 0.05)


def readable(colour: str, on: str, need: float = 3.0) -> str:
    """`colour`, or the nearest shade of it (toward black on a light ground, white on a dark one) that reads at
    `need`:1 against `on`."""
    if not (isinstance(colour, str) and colour.startswith("#") and len(colour) >= 7):
        return colour
    if contrast(colour, on) >= need:
        return colour
    toward = 0.0 if _luminance(on) > 0.18 else 1.0
    rgb = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    for step in range(1, 21):
        t = step / 20
        mixed = "#" + "".join(f"{round(255 * (c + (toward - c) * t)):02X}" for c in rgb)
        if contrast(mixed, on) >= need:
            return mixed
    return "#000000" if toward == 0.0 else "#FFFFFF"


# The roles that mark things on the background (a highlight ring, an ally's arrow, a label's tone): each style's
# colour for them is checked against its background and, below 3:1, shaded until it reads (CONTRAST_FIXED).
CONTRAST_ROLES = ("ink", "muted", "accent", "highlight", "friendly", "enemy", "ally", "neutral")
CONTRAST_FIXED: list[str] = []


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
    CONTRAST_FIXED.clear()
    for key in CONTRAST_ROLES:
        was = getattr(P, f"role_{key}")
        now = readable(was, P.BG)
        if now != was:
            setattr(P, f"role_{key}", now)
            CONTRAST_FIXED.append(f"{key} {was}->{now}")
    config.background_color = TH["bg"]
    # The art style draws the pictures; left to "auto" it is the one this template draws with (artstyle.py).
    import artstyle

    artstyle.from_env(TH.get("art") or (name if name in artstyle.TEMPLATE_ART else TH.get("base_style", name)))
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
# The type scale: no word on screen is set smaller than MIN_TEXT (a phone held at arm's length reads 15pt at 1080p
# and not much less); only a picture's credit or a source line, which nobody needs to read, goes below (fine=True).
MIN_TEXT = 15
TYPE = {"fine": 11, "small": 15, "label": 17, "body": 20, "heading": 24, "title": 34}


def _complex(text: str) -> bool:
    return any(lo <= ord(c) <= hi for c in text for lo, hi in COMPLEX_SCRIPTS)


def T(text: str, size: float = 24, color: str | None = None, font: str | None = None,
      weight=NORMAL, fine: bool = False, **kw) -> Text:
    """Text in the style's body font (in a picture being drawn, the art style's: artstyle.font). Characters a font
    lacks are swapped. Set no smaller than MIN_TEXT unless `fine` (a credit, a source line)."""
    if not fine:
        size = max(size, MIN_TEXT)
    if font is None:
        import artstyle

        font = artstyle.font()
    font = font or TH["sans"]
    if font == "Permanent Marker":
        text = text.replace("≈", "~")
    if weight == BOLD and not _has_bold(font):
        # A font with no bold of its own (Patrick Hand, Architects Daughter) is faked bold by the text engine, which
        # on some systems spaces the letters unevenly: written in its own weight instead.
        weight = NORMAL
    if size < LAYOUT_SIZE:
        # Laid out large and scaled down: at small sizes the text engine rounds each letter's place to whole
        # pixels, which on some systems (macOS especially) leaves uneven gaps ("pro te cts") and drops spaces
        # ("servesloyally"). The same for every script, not only Hindi.
        mob = Text(text, font=font, font_size=LAYOUT_SIZE, color=color or P.CREAM, weight=weight, **kw)
        return mob.scale(size / LAYOUT_SIZE)
    return Text(text, font=font, font_size=size, color=color or P.CREAM, weight=weight, **kw)


_BOLD: dict[str, bool] = {}


def _has_bold(font: str) -> bool:
    """Whether a font family has a bold face of its own (fontconfig); True when that cannot be told."""
    if font not in _BOLD:
        try:
            out = subprocess.run(["fc-list", f":family={font}", "style", "weight"], capture_output=True, text=True,
                                 timeout=10).stdout
        except Exception:  # noqa: BLE001 -- no fontconfig: leave the weight as asked
            out = ""
        # A variable font (one file, every weight) lists its weight range, e.g. "weight=[400 200]".
        _BOLD[font] = (not out.strip()) or bool(re.search(r"bold|weight=\[|weight=(?:2\d\d|1[5-9]\d)", out, re.I))
    return _BOLD[font]


def _art(mob) -> None:
    """Draw a picture in the lecture's art style (artstyle.py): its colours and lines, and the extras on its still
    parts. Parts that move were marked live and are painted every frame instead."""
    import artstyle

    try:
        artstyle.dress(mob)
    except Exception as error:  # noqa: BLE001 -- a picture the style cannot dress is shown as it was drawn
        SKIPPED.append(f"art style left a picture as drawn: {type(error).__name__}: {error}"[:300])


def tok(name: str, default: float) -> float:
    """A style token -- a size a style pack may retune without code."""
    return float((TH.get("tokens") or {}).get(name, default))


def _tint_on_bg(colour: str, amount: float) -> ManimColor:
    """A light wash of a colour, mixed into the background: looks like a translucent fill, but is solid, so
    nothing left behind a box shows through it."""
    return interpolate_color(ManimColor(P.BG), ManimColor(colour), amount)


def _flat(*mobs):
    """Interface pieces (cards, chips, tracks) the art style leaves as they are: no sheen, hatching or wobble on a
    card; its look is the house's, clean and flat."""
    for mob in mobs:
        for part in mob.get_family():
            part._art_none = True
    return mobs[0] if len(mobs) == 1 else mobs


def ui_chip(text: str, tone: str | None = None, size: float = 17, ink: str | None = None):
    """A pill with a few words or a number in it (a date, a step's number, a choice's letter): the tone's solid
    colour, the words in the board's own colour on it."""
    tone = tone or P.SAND
    words = T(str(text), size, ink or P.BG, weight=BOLD)
    pill = RoundedRectangle(corner_radius=(words.height + 0.2) / 2, width=max(words.width + 0.38, words.height + 0.2),
                            height=words.height + 0.2, fill_color=tone, fill_opacity=1, stroke_width=0)
    words.move_to(pill)
    return VGroup(_flat(pill), words)


def ui_surface(width: float, height: float, tone: str | None = None, radius: float = 0.22, wash: float = 0.10):
    """A card's face: a soft wash of the tone over the board, a hairline edge in the tone."""
    tone = tone or P.SAND
    return _flat(RoundedRectangle(corner_radius=min(radius, height / 2, width / 2), width=width, height=height,
                                  fill_color=_tint_on_bg(tone, wash), fill_opacity=1,
                                  stroke_color=_tint_on_bg(tone, 0.5), stroke_width=1.4))


# A drawing's outline weight at full size.
OUTLINE = 4.5


# The smallest size (in the font's points, as drawn on the frame) an arrow's words in a diagram are shown at.
READABLE_LABEL = 17

# What an arrow means, as how it is drawn: what is given is a plain line, what is owed or promised is dashed, power
# over another is bold. A script may name the look itself (dashed, bold) or the meaning; a meaning word not here is
# dashed. Each meaning word a diagram uses goes in its legend.
EDGE_LOOKS = {"solid": "solid", "gives": "solid", "give": "solid", "provides": "solid", "flow": "solid",
              "dashed": "dashed", "owes": "dashed", "owe": "dashed", "promises": "dashed", "promise": "dashed",
              "duty": "dashed", "loyalty": "dashed", "serves": "dashed", "obligation": "dashed",
              "bold": "bold", "thick": "bold", "power": "bold", "rules": "bold", "controls": "bold",
              "commands": "bold", "authority": "bold"}


def edge_look(style) -> str:
    word = str(style or "").strip().lower()
    return EDGE_LOOKS.get(word, "dashed") if word else "solid"


def edge_legend(styles) -> "VGroup | None":
    """A small key under a diagram whose arrows carry meanings: a sample of each look and the word it stands for."""
    words = [str(x).strip().lower() for x in styles if x and str(x).strip().lower() not in ("solid", "dashed", "bold",
                                                                                            "thick")]
    words = list(dict.fromkeys(words))
    if not words:
        return None
    rows = []
    for word in words:
        look = edge_look(word)
        line = Line(LEFT * 0.35, RIGHT * 0.35, color=P.HI if look == "bold" else P.CREAM,
                    stroke_width=OUTLINE * (2.2 if look == "bold" else 0.8))
        line._art_keep_width = look == "bold"
        sample = DashedVMobject(line, num_dashes=5) if look == "dashed" else line
        rows.append(VGroup(sample, marker(word, 16)).arrange(RIGHT, buff=0.15))
    return VGroup(*rows).arrange(RIGHT, buff=0.5)


def marker_card_style(role: str | None) -> dict:
    """How a diagram's box looks for what it stands for: a person, a place, an event, an idea (or a thing)."""
    role = str(role or "").strip().lower()
    return {"person": dict(corner_radius=0.5), "place": dict(corner_radius=0.06), "event": dict(corner_radius=0.02),
            "idea": dict(corner_radius=0.32)}.get(role, dict(corner_radius=0.18))


def marker(text: str, size: float = 20, color: str | None = None):
    """A diagram's words: the style's own font, bold, in the board's ink."""
    return T(str(text), size, color or P.CREAM, weight=BOLD)


# Above every picture on the stage: the labels written on a picture (its tags, their lines and dots).
Z_LABEL = 26.0


def lift_labels(mob) -> None:
    """Put the labels marked to sit on a picture (`_panim_above`) back above it: setting a group's z-index sets it on
    every member, labels too, and a label level with its picture was drawn under it on the phone."""
    for part in mob.get_family():
        if getattr(part, "_panim_above", False):
            part.set_z_index(Z_LABEL)
        elif getattr(part, "_panim_z", None) is not None:
            part.set_z_index(part._panim_z)     # a part with a depth of its own (a photo frame's overlay)


_DARK_PAINT = re.compile(r'((?:fill|stroke)\s*[=:]\s*"?)(#[0-9a-fA-F]{3,6}|black)\b')


# Credits a scene owes beyond its pictures' (historical borders: "historical:<year>").
USED_DRAWINGS: set[str] = set()

# An old script's library ids ("coco:123-cow", "bioicons:cell", "draw:cow"): only the words of the thing are kept.
_LIBRARY_ID = re.compile(r"^(?:[a-z0-9]+(?:-[a-z0-9]+)*):(?=\S)")


def thing_words(name) -> str:
    """What a picture of a thing is asked for in: the name, without an old library id's prefix and number."""
    text = _LIBRARY_ID.sub("", str(name or "").strip())
    text = re.sub(r"^\d+[-_]", "", text)
    return re.sub(r"[-_]+", " ", text).strip()


def thing_picture(name) -> str:
    """The picture of a thing (a tree, a factory, a cow): a cutout PNG made by the illustration model (genimage.py)
    the first time it is asked for, and the same file every time after. Nothing is drawn from an SVG library. A
    KeyError when it cannot be made (no image model, refused, offline)."""
    import images

    words = thing_words(name)
    # Made already when the script was compiled (compile_lecture._thing_op asks for the same picture).
    row = images.fetch(subject=words, style=os.environ.get("LECTURE_STYLE"), aspect="1:1", look="child") \
        if words else None
    if not row or not row.get("file"):
        raise KeyError(f"no picture of {name!r}")
    return str(row["file"])


def _families_zipped(self):
    """Transform's parts paired with their start and end, as Manim does. Manim lines the three up before the play
    starts, so they differ only when a part rebuilds itself during it -- a live readout writing its next number while
    it fades in (a trace's slope) -- and Manim's strict pairing stopped the whole render there. Then the parts are
    paired by place in the whole family, which a readout keeps (it refills or empties its pieces, and only adds new
    ones at the end): each glyph with its own start and end, the pieces it added since left as they are."""
    mobs = [self.mobject, self.starting_mobject, self.target_copy]
    families = [mob.family_members_with_points() for mob in mobs]
    if len({len(f) for f in families}) == 1:
        return zip(*families)
    # Shapes only: a plain Group in the family has nothing to fade.
    return [parts for parts in zip(*(mob.get_family() for mob in mobs))
            if all(hasattr(part, "fill_rgbas") for part in parts)]


from manim.animation.transform import Transform as _Transform  # noqa: E402

_Transform.get_all_families_zipped = _families_zipped

# Pictures a build left out because they could not be drawn (Lecture.safe), for export_scene.py to report.
SKIPPED: list[str] = []

# ---------------- what is shown, on the words that say it ----------------
# Inside a beat each picture that names something (a marker's place, a diagram part revealed or focused, an area
# shaded, a term defined) starts as its words are said, and a thing on the screen the line names again (a diagram's
# part, a timeline's date, a map's place, a card's heading) is drawn attention to on its words: from the line's word
# times (the voice's, or aligned here by Whisper: line_words). SYNC counts it for the build's report.
SYNC: dict[int, dict] = {}      # chapter -> {"beats", "on_words", "pointed"}


def sync_counts(chapters=None) -> dict:
    """SYNC summed over these chapters (all when None): a build of a window of chapters counts its own."""
    out = {"beats": 0, "on_words": 0, "pointed": 0}
    for number, counts in SYNC.items():
        if chapters is None or number in chapters:
            for k, v in counts.items():
                out[k] = out.get(k, 0) + v
    return out
class PrimitiveRun:
    """How long the base animations take, in seconds: a thing shown (a card, a label, a point coming on), hidden (the
    last picture cleared), and the most any one is given. Quick, so each is done before the next begins and the
    screen keeps up with the voice."""
    SHOW = 0.6
    HIDE = 0.5
    MOST = 2.5


SAY_STOP = {"the", "a", "an", "of", "and", "in", "on", "to", "at", "for", "is", "are", "its", "his", "her"}
SYNC_LEAD = 0.2          # seconds a picture starts before its words: it is there as they are heard
POINT_MOST = 4           # things pointed at in one line, at most


def _say_tokens(text) -> list[str]:
    """A line's words for matching, lower case: a Latin letter's accent dropped ("Zürich" is "zurich"), but the
    marks of other scripts kept inside their words -- a Devanagari vowel sign is a combining mark, and dropping it
    cut "देता" into "द" and "त", so "दिया" could be heard in it and "को" not at all (Hinglish lines)."""
    import unicodedata

    out, word, base = [], [], ""
    for c in unicodedata.normalize("NFKD", str(text)):
        if unicodedata.category(c).startswith("M"):
            if word and not ("LATIN" in unicodedata.name(base, "")):
                word.append(c)              # a vowel sign, a nukta, a virama: part of its word
            continue                        # an accent on a Latin letter (or a stray mark): dropped
        if c.isalnum():
            word.append(c)
            base = c
        else:
            if word:
                out.append("".join(word))
            word, base = [], ""
    if word:
        out.append("".join(word))
    return [unicodedata.normalize("NFC", w).lower() for w in out]


def _same_word(spoken: str, wanted: str) -> bool:
    if spoken == wanted:
        return True
    return (len(spoken) >= 4 and len(wanted) >= 4 and abs(len(spoken) - len(wanted)) <= 3
            and (spoken.startswith(wanted) or wanted.startswith(spoken)))


def said_at(words, phrase) -> float | None:
    """When a line's voice says a phrase (a label, a place, a term), in seconds into the line, from its word times
    ([{"w", "start", "end"}]); None when it is not said. Its words in order, small words between them skipped
    ("Gulf of Mannar" in "...across the gulf of Mannar..."), a plural or a possessive taken as the word."""
    if not words or not phrase:
        return None
    flat = [(token, float(w.get("start") or 0)) for w in words for token in _say_tokens(w.get("w", ""))]
    for variant in dict.fromkeys([str(phrase), speechify(str(phrase))]):
        tokens = _say_tokens(variant)
        wanted = [t for t in tokens if t not in SAY_STOP] or tokens
        if not wanted or (len(wanted) == 1 and len(wanted[0]) < 3 and not wanted[0].isdigit()):
            continue
        for i, (token, start) in enumerate(flat):
            if not _same_word(token, wanted[0]):
                continue
            j, found = i, True
            for want in wanted[1:]:
                k = next((k for k in range(j + 1, min(len(flat), j + 4)) if _same_word(flat[k][0], want)), None)
                if k is None:
                    found = False
                    break
                j = k
            if found:
                return start
    return None
# Called with (scene, chapter number) as each chapter begins, before anything of it is drawn.
CHAPTER_HOOKS: list = []


def skipped(message: str) -> None:
    """Report a picture left out, once: a drawing used on every node of a diagram is one problem, not ten."""
    if message not in SKIPPED:
        SKIPPED.append(message)


def _playable(anim):
    """An animation Manim can play, or None: a group with nothing in it (a step that found nothing to show, an
    empty LaggedStart) is dropped, at any depth, instead of stopping the render with "Called Scene.play with no
    animations" or "Trying to play AnimationGroup without animations"."""
    if anim is None:
        return None
    if not isinstance(anim, AnimationGroup):
        return anim
    kids = [k for k in (_playable(k) for k in anim.animations) if k is not None]
    if not kids:
        return None
    if len(kids) == len(anim.animations):
        return anim
    return AnimationGroup(*kids, lag_ratio=anim.lag_ratio)


def sketch_mob(name: str, height: float = 0.9):
    """The picture of a thing, at most `height` tall (thing_picture): made by the illustration model, shown as the
    model drew it. A KeyError when there is none."""
    return cutout_mob(thing_picture(name), height * 1.8, height)


def _bbox(mob, pad: float = 0.0):
    """(x0, y0, x1, y1) of a mobject, padded."""
    lo, hi = mob.get_corner(DL), mob.get_corner(UR)
    return (lo[0] - pad, lo[1] - pad, hi[0] + pad, hi[1] + pad)


def _overlap(a, b) -> float:
    """The area two boxes share."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def has_image(mob) -> bool:
    """Whether a picture holds a photo (an ImageMobject): it is then grouped with Group and faded in, as a photo
    cannot be written like a line."""
    return mob is not None and any(isinstance(m, ImageMobject) for m in mob.get_family())


def group_of(*mobs):
    """VGroup of these, or Group when one holds a photo."""
    return Group(*mobs) if any(has_image(m) for m in mobs) else VGroup(*mobs)


def write_in(mob):
    """Write a picture onto the board, or fade it in when it holds a photo; a child's drawing in it drawn on
    (draw_on)."""
    if getattr(mob, "_panim_child", False):
        return draw_on(mob)
    if not any(getattr(m, "_panim_child", False) for m in mob.get_family()):
        return FadeIn(mob) if has_image(mob) else Write(mob)
    return AnimationGroup(*[write_in(part) for part in mob.submobjects])


def is_cutout(path) -> bool:
    """A picture the image model made (genimage.py): a cutout, shown without a frame."""
    return Path(str(path)).name.startswith("gen-")


_TRIMS: dict[str, tuple] = {}


def trim_box(path) -> tuple[str, tuple]:
    """A picture without the empty margin round it, and where in the original it was cut from ((u0, v0, u1, v1),
    0 to 1 across and down): a cutout's transparent edges, or a flat white or black border round a photo or a book's
    figure. Kept beside the original; the original itself when there is nothing to cut."""
    key = str(path)
    if key in _TRIMS:
        return _TRIMS[key]
    whole = (key, (0.0, 0.0, 1.0, 1.0))
    p = Path(key)
    try:
        from PIL import Image

        with Image.open(p) as img:
            rgba = np.asarray(img.convert("RGBA"))
    except Exception:  # noqa: BLE001 -- a picture PIL cannot open is shown as it is
        _TRIMS[key] = whole
        return whole
    rows, cols = rgba.shape[0], rgba.shape[1]
    alpha = rgba[..., 3]
    if (alpha < 250).mean() > 0.01:
        keep = alpha > 12
    else:
        corners = np.array([rgba[0, 0, :3], rgba[0, -1, :3], rgba[-1, 0, :3], rgba[-1, -1, :3]], dtype=float)
        flat = corners.max(axis=0) - corners.min(axis=0)
        level = corners.mean()
        if flat.max() > 24 or 40 < level < 215:
            # The corners differ, or are a colour of the picture (a sky, a field): no border to cut.
            _TRIMS[key] = whole
            return whole
        keep = np.abs(rgba[..., :3].astype(float) - corners.mean(axis=0)).max(axis=2) > 20
    found_r, found_c = np.where(keep.any(axis=1))[0], np.where(keep.any(axis=0))[0]
    if not len(found_r) or not len(found_c):
        _TRIMS[key] = whole
        return whole
    pad = 2
    r0, r1 = max(0, found_r[0] - pad), min(rows, found_r[-1] + 1 + pad)
    c0, c1 = max(0, found_c[0] - pad), min(cols, found_c[-1] + 1 + pad)
    if (r1 - r0) * (c1 - c0) > 0.97 * rows * cols:
        _TRIMS[key] = whole
        return whole
    out = p.with_name(f"{p.stem}.trim.png")
    if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
        from PIL import Image

        part = out.with_suffix(f".{os.getpid()}.part.png")
        Image.fromarray(rgba[r0:r1, c0:c1]).save(part)
        os.replace(part, out)
    found = (str(out), (c0 / cols, r0 / rows, c1 / cols, r1 / rows))
    _TRIMS[key] = found
    return found


def remap_labels(labels, box) -> list:
    """Labels ([(text, x, y)] or with their part's box, x0..y1) of a picture, moved to a part of it cut out at `box`
    ((u0, v0, u1, v1), 0 to 1 across and down): each place as a fraction of the cut-out part, kept on it."""
    u0, v0, u1, v1 = box
    if not labels or box == (0.0, 0.0, 1.0, 1.0):
        return list(labels or [])
    su, sv = max(u1 - u0, 1e-6), max(v1 - v0, 1e-6)

    def across(v):
        return min(max((float(v) - u0) / su, 0.0), 1.0)

    def down(v):
        return min(max((float(v) - v0) / sv, 0.0), 1.0)

    return [(t[0], across(t[1]), down(t[2]),
             *((across(t[3]), down(t[4]), across(t[5]), down(t[6])) if len(t) >= 7 else ())) for t in labels]


def cover_box(path, aspect: float) -> tuple[str, tuple]:
    """A picture cut to `aspect` (width over height) from its middle, as a screen it fills shows it, and where in
    the picture it was cut from ((u0, v0, u1, v1)). The picture itself when it has that shape already."""
    p = Path(str(path))
    try:
        from PIL import Image

        with Image.open(p) as img:
            cols, rows = img.size
            have = cols / max(rows, 1)
            if abs(have - aspect) < 0.02:
                return str(p), (0.0, 0.0, 1.0, 1.0)
            if have > aspect:
                keep = aspect / have
                box = ((1 - keep) / 2, 0.0, (1 + keep) / 2, 1.0)
            else:
                keep = have / aspect
                box = (0.0, (1 - keep) / 2, 1.0, (1 + keep) / 2)
            out = p.with_name(f"{p.stem}.{aspect:.3f}.png")
            if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
                part = out.with_suffix(f".{os.getpid()}.part.png")
                img.crop((round(box[0] * cols), round(box[1] * rows), round(box[2] * cols),
                          round(box[3] * rows))).save(part)
                os.replace(part, out)
            return str(out), box
    except Exception:  # noqa: BLE001 -- a picture that cannot be cut is shown whole
        return str(p), (0.0, 0.0, 1.0, 1.0)


def trimmed(path) -> str:
    return trim_box(path)[0]


def has_alpha(path) -> bool:
    """Whether a picture is a cutout with clear parts (a sticker on the board: no frame round it)."""
    try:
        from PIL import Image

        with Image.open(str(path)) as img:
            if "A" not in img.getbands():
                return False
            return bool((np.asarray(img.getchannel("A")) < 250).mean() > 0.02)
    except Exception:  # noqa: BLE001
        return False


def board_colour_at(scene, point) -> str:
    """The board's colour at a point: the background with the backdrop's soft discs over it (the vignette, the
    paper's light), so a patch laid there in it cannot be told from the board."""
    colour = np.array(color_to_rgb(P.BG), dtype=float)
    for top in getattr(scene, "mobjects", []):
        if not getattr(top, "is_backdrop", False):
            continue
        for m in top.get_family():
            if not isinstance(m, Circle):
                continue
            try:
                opacity = float(m.get_fill_opacity())
            except Exception:  # noqa: BLE001
                continue
            if opacity <= 0:
                continue
            c = m.get_center()
            a, b = m.width / 2, m.height / 2
            if ((point[0] - c[0]) / max(a, 1e-6)) ** 2 + ((point[1] - c[1]) / max(b, 1e-6)) ** 2 <= 1:
                colour = colour * (1 - opacity) + np.array(color_to_rgb(m.get_fill_color()), dtype=float) * opacity
    return rgb_to_hex(np.clip(colour, 0, 1))


def photo_frame(scene, image, radius: float = 0.16):
    """A modern frame for a picture with edges (a photo, a scene, a book's figure): its corners rounded (four small
    patches of the board's colour over them), a hairline edge, and depth -- a soft shadow on a light board, a faint
    glow on a dark one. (behind, over): what goes under the picture, and what over it."""
    import artstyle

    lo, hi = image.get_corner(DL), image.get_corner(UR)
    w, h = hi[0] - lo[0], hi[1] - lo[1]
    r = min(radius, w / 6, h / 6)
    edge = RoundedRectangle(corner_radius=r, width=w, height=h, stroke_color=_tint_on_bg(P.CREAM, 0.35),
                            stroke_width=1.6, fill_opacity=0).move_to(image)
    corners = VGroup()
    for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        corner = np.array([lo[0] if sx < 0 else hi[0], hi[1] if sy > 0 else lo[1], 0])
        centre = corner + np.array([-sx * r, -sy * r, 0])
        # The quarter circle on the corner's side, from the edge across to the edge up or down.
        start = 0.0 if sx > 0 else PI
        arc = [centre + r * np.array([np.cos(t), np.sin(t), 0])
               for t in np.linspace(start, start + sx * sy * PI / 2, 9)]
        patch = VMobject().set_points_as_corners([corner, *arc, corner])
        patch.set_fill(board_colour_at(scene, corner), 1).set_stroke(width=0)
        corners.add(patch)
    if artstyle.dark_board():
        depth = RoundedRectangle(corner_radius=r + 0.04, width=w + 0.08, height=h + 0.08, fill_opacity=0,
                                 stroke_color=_tint_on_bg(P.SAND, 0.5), stroke_width=7, stroke_opacity=0.12)
        depth.move_to(image)
    else:
        depth = RoundedRectangle(corner_radius=r, width=w, height=h, fill_color="#000000", fill_opacity=0.18,
                                 stroke_width=0)
        depth.move_to(image).shift(RIGHT * 0.05 + DOWN * 0.08)
    over = VGroup(corners, edge)
    for part in [*over.get_family(), *depth.get_family()]:
        part._art_none = True
    return depth, over


def circle_cut(path) -> str | None:
    """A photograph cut to a circle from its middle (clear outside it), kept beside it; None when it cannot be."""
    p = Path(str(path))
    out = p.with_name(f"{p.stem}.round.png")
    try:
        if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
            from PIL import Image, ImageDraw

            with Image.open(p) as img:
                side = min(img.size)
                left, top = (img.width - side) // 2, (img.height - side) // 2
                square = img.convert("RGBA").crop((left, top, left + side, top + side))
                mask = Image.new("L", (side, side), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, side - 1, side - 1), fill=255)
                square.putalpha(mask)
                part = out.with_suffix(f".{os.getpid()}.part.png")
                square.save(part)
                os.replace(part, out)
        return str(out)
    except Exception:  # noqa: BLE001
        return None


def cutout_mob(path, width: float, height: float):
    """A picture an image model made, as the board shows it: the cutout PNG in its own colours, no frame, at most
    width x height, its empty margin cut away (trim_box). The phone draws the same PNG (the program's `image`
    lines)."""
    mob = ImageMobject(trimmed(path))
    mob.scale_to_fit_height(height)
    if mob.width > width:
        mob.scale_to_fit_width(width)
    if Path(str(path)).name.startswith("gen-diagram-"):
        # A book's diagram the diagram model redrew in this style: the art style leaves it as drawn.
        mob._art_none = True
    mob._panim_src = str(trimmed(path))
    if Path(str(path)).name.startswith("gen-child-") or (Path(str(path)).name.startswith("gen-diagram-")
                                                         and os.environ.get("PANIM_REDRAW_LOOK") != "art"):
        # A child's drawing (genimage CHILD_LOOK): the board draws it on, outline first (draw_on).
        mob._panim_child = True
    return mob


def sketch_lines(image, most_paths: int = 60, most_points: int = 1800) -> VGroup:
    """The outlines of a child's drawing as crayon strokes over it: the shapes its colours make (blurred a little,
    so a scribbled fill reads as one shape) traced (contourpy) where the picture is on the screen, longest first,
    each drawn in the colour of the crayon under it."""
    import contourpy
    from PIL import Image
    from scipy import ndimage

    with Image.open(getattr(image, "_panim_src")) as img:
        img = img.convert("RGBA")
        scale = 220 / max(img.size)
        if scale < 1:
            img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
        rgba = np.asarray(img).astype(float)
    rows, cols = rgba.shape[:2]
    # Where a crayon went: not paper (far from white) and not clear.
    drawn = (np.abs(rgba[..., :3] - 255.0).max(axis=2) > 60) & (rgba[..., 3] > 128)
    if drawn.mean() < 0.005:
        drawn = rgba[..., 3] > 128
    field = ndimage.gaussian_filter(np.pad(drawn.astype(float), 2), 1.4)
    lines = [np.asarray(line) for line in contourpy.contour_generator(z=field).lines(0.5) if len(line) >= 10]
    lines.sort(key=len, reverse=True)
    lo, hi = image.get_corner(DL), image.get_corner(UR)
    colours = rgba[..., :3]
    out, used = VGroup(), 0
    for line in lines[:most_paths]:
        step = 2 if len(line) > 40 else 1
        pts = line[::step]
        if used + len(pts) > most_points:
            break
        used += len(pts)
        cs = np.clip((pts[:, 0] - 2).round().astype(int), 0, cols - 1)
        rs = np.clip((pts[:, 1] - 2).round().astype(int), 0, rows - 1)
        under = colours[rs, cs][drawn[rs, cs]]
        colour = rgb_to_hex(np.median(under, axis=0) / 255.0) if len(under) else P.CREAM
        xs = lo[0] + (pts[:, 0] - 2) / max(cols - 1, 1) * (hi[0] - lo[0])
        ys = hi[1] - (pts[:, 1] - 2) / max(rows - 1, 1) * (hi[1] - lo[1])
        path = VMobject(stroke_color=colour, stroke_width=2.6, fill_opacity=0)
        path.set_points_as_corners(np.column_stack([xs, ys, np.zeros(len(xs))]))
        out.add(path)
    for part in out.get_family():
        part._art_none = True
    return out


def draw_on(image):
    """A child's drawing brought onto the board as one is drawn: its outlines drawn with the pen, then its colours
    filled in under them as the pen's lines go."""
    try:
        lines = sketch_lines(image)
    except Exception:  # noqa: BLE001 -- a picture whose outline cannot be traced fades in
        lines = VGroup()
    if not len(lines):
        return FadeIn(image)
    lines.set_z_index(float(getattr(image, "z_index", 0) or 0) + 0.3)
    drift = image.__dict__.get("_panim_drift")
    if drift:
        set_drift([lines], drift)
    return AnimationGroup(Create(lines, lag_ratio=0.15, rate_func=linear, run_time=1.4),
                          AnimationGroup(FadeIn(image), FadeOut(lines), run_time=0.6), lag_ratio=1.0)


def cutout_strokes(mob, batches: int = 10) -> list:
    """The pieces a picture is brought onto the board in: a picture is one piece, faded in."""
    return [mob]


def icon_mob(name: str, color: str | None = None, height: float = 0.5):
    """A picture of a thing, anywhere in a lecture (a map's marker, a panel's line, an illustration): made by the
    illustration model (sketch_mob). `color` is kept for the call sites; a picture has its own colours."""
    return sketch_mob(name, height=height)


def wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width)) or text


def _short_caption(text: str, limit: int = 110) -> str:
    """A figure's caption at a length that can be read under it: a PDF's long description is cut at a word."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


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


# Units and symbols in a Hindi line, said in Hindi: the English words SAY puts in ("percent", "to") made a
# Hindi voice switch accent mid-sentence.
SAY_HI: dict[str, str] = {
    "km²": " वर्ग किलोमीटर", "°C": " डिग्री सेल्सियस", "°N": " डिग्री उत्तर", "°E": " डिग्री पूर्व",
    "mm": " मिलीमीटर", "MW": " मेगावाट", "%": " प्रतिशत", "m/s²": " मीटर प्रति सेकंड वर्ग",
    "m/s": " मीटर प्रति सेकंड", "km/h": " किलोमीटर प्रति घंटा", "kg": " किलोग्राम", "km": " किलोमीटर",
}


def _respell(text: str, table: dict) -> str:
    for key in sorted(table, key=len, reverse=True):
        pattern = (r"\b" if key[0].isalnum() else "") + re.escape(key) + (r"\b" if key[-1].isalnum() else "")
        text = re.sub(pattern, table[key], text)
    return text


def _show(mob, on: bool, opacity: float = 1.0) -> None:
    """Show or hide a part without taking it off the picture (a clip keeps the same members every frame). Shown
    again, each piece gets back its own opacity (a translucent fill stays translucent), times `opacity`."""
    for part in mob.get_family():
        kept = getattr(part, "_panim_alpha", None)
        if kept is None:
            try:
                kept = (float(part.get_fill_opacity()), float(part.get_stroke_opacity()))
            except Exception:  # noqa: BLE001 -- a part without colours
                continue
            part._panim_alpha = kept
        part.set_fill(opacity=kept[0] * opacity if on else 0.0, family=False)
        part.set_stroke(opacity=kept[1] * opacity if on else 0.0, family=False)


CAPTION_MAX = 184        # characters two caption lines hold at a readable size


def caption_pieces(text: str, most: int = CAPTION_MAX) -> list[str]:
    """A line's caption in pieces that each fit two lines: whole sentences together while they fit, a sentence too
    long for two lines cut at a comma or a dash, else between words near its middle. A short line is one piece."""
    text = " ".join(str(text).split())
    if len(text) <= most:
        return [text]
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    parts: list[str] = []
    for sentence in sentences:
        while len(sentence) > most:
            cut = max((m.end() for m in re.finditer(r"[,;:—–]\s", sentence[:most])), default=0)
            if cut < most * 0.4:
                cut = sentence.rfind(" ", 0, most) + 1 or most
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            parts.append(sentence)
    out: list[str] = []
    for part in parts:
        if out and len(out[-1]) + 1 + len(part) <= most:
            out[-1] += " " + part
        else:
            out.append(part)
    return out or [text]


def speechify(text: str) -> str:
    """Rewrite a caption into something a voice can say, on word boundaries (a Hindi line's units in Hindi)."""
    if spoken_lang(text) == "hi":
        text = _respell(_respell(text, SAY_HI), {k: v for k, v in SAY.items() if k not in SAY_HI})
        return text.replace("–", " से ").replace("·", ",").replace("≈", "लगभग ").replace("→", " से ")
    text = _respell(text, SAY)
    return text.replace("–", " to ").replace("·", ",").replace("≈", "about ").replace("→", " to ")


# The teaching pace, PANIM_PACE: (voice speed, the hold after each line, the hold at a paragraph's end). "natural",
# the default: the voice at its own speed, one line running into the next as a teacher speaks, a short breath
# between paragraphs. "relaxed" and "slow" leave longer holds after each line. "teacher": the voice 10% slower
# (pitch kept: the voice modules' ffmpeg atempo; its lines cached apart), the pauses it left between lines kept but
# never under 0.4 s, and a longer breath between paragraphs -- an explainer's unhurried pace.
PACES = {"natural": (1.0, 0.3, 0.8), "relaxed": (1.0, 0.7, 1.5), "slow": (1.0, 1.4, 2.8), "teacher": (0.9, 0.4, 1.4)}
VOICE_SPEED, BEAT_PAD, PARAGRAPH_PAD = PACES.get(os.environ.get("PANIM_PACE", "natural"), PACES["natural"])
THINK_SECONDS = 7.0      # the silence a question on the stage leaves for thinking


def estimate_seconds(text: str) -> float:
    """About 143 words a minute at normal speed: a line's length when it is not spoken (PANIM_VOICE=silent)."""
    return max(1.2, len(text.split()) * 0.42 / VOICE_SPEED)


def audio_dir() -> Path:
    folder = Path(os.environ.get("PANIM_AUDIO_DIR") or (Path.cwd() / "build_audio"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


def _cached_seconds(out: Path) -> float | None:
    """The cached line's length, or None when there is none to use: missing, empty, or unreadable (cut short by a
    run stopped mid-write, before writes were whole-or-nothing). An unreadable one is removed, to be spoken again."""
    if not (out.exists() and out.stat().st_size > 44):
        return None
    try:
        return _wav_seconds(out)
    except (EOFError, wave.Error, OSError):
        out.unlink(missing_ok=True)
        return None


def _private(out: Path, tag: str) -> Path:
    """A working file of this process and thread only: two runs speaking the same line at once (the narration
    spoken ahead beside the build) wrote the same file, and the build read it half-written (EOFError)."""
    return out.with_name(f"{out.stem}_{tag}{os.getpid()}_{threading.get_ident()}.wav")


# Scripts a line may be written in. A line's language is taken from the line itself (chirp.runs splits a
# mixed one further, a language run at a time).
SCRIPT_LANGS = (("hi", 0x0900, 0x097F),)


def spoken_lang(text: str) -> str:
    """'hi' when most letters are Devanagari, else 'en'."""
    letters = [c for c in text if c.isalpha()]
    for lang, lo, hi in SCRIPT_LANGS:
        if letters and sum(lo <= ord(c) <= hi for c in letters) / len(letters) > 0.4:
            return lang
    return "en"


class VoiceUnavailable(RuntimeError):
    """The narration voice (Gemini 3.8 Flash-Lite TTS, or Chirp 3 HD) cannot speak: no key, or Google refused. The lecture stops rather
    than being spoken by another voice or left silent."""


def voice_mode() -> str:
    """The voice lines are spoken in: gemini:<voice> (Gemini 3.8 Flash-Lite TTS), chirp:<voice> (Google Chirp 3 HD, with
    PANIM_TTS=chirp), or silent.

    PANIM_VOICE=silent is the one way to build without a voice (tests, a quick look at the pictures): the beats
    then hold for an estimate of each line. Otherwise the voice must be set up (tts.py: GEMINI_API_KEY);
    `PANIM_VOICE=<engine>:<voice>` or `:<voice>` picks a speaker, else the style's. The mode is part of each line's
    cache key.
    """
    import tts

    mode = os.environ.get("PANIM_VOICE", "auto")
    if mode == "silent":
        return "silent"
    name = tts.engine_name()
    voice = tts.engine(name)
    if not voice.configured():
        raise VoiceUnavailable(tts.setup_hint() + " PANIM_VOICE=silent builds without narration.")
    chosen = mode.split(":", 1)[1] if ":" in mode else ""
    return f"{name}:{chosen or voice.voice_for(STYLE)}"


def _finish(raw: Path, out: Path) -> None:
    """The house treatment every line gets: band-limit, level, 44.1 kHz stereo (as is without ffmpeg). The line
    appears in the cache whole or not at all (written aside, then renamed): a reader never sees it half-written."""
    if not shutil.which("ffmpeg"):
        raw.replace(out)
        return
    done = _private(out, "done")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                        "highpass=f=70,loudnorm=I=-17:TP=-2,apad=pad_dur=0.1", "-ar", "44100", "-ac", "2", str(done)],
                       check=True, timeout=120)
        done.replace(out)
    finally:
        done.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)


def audio_file(mode: str, spoken: str) -> Path:
    """Where a line spoken in `mode` is cached: named by the voice, its speed and the words (Forge's
    narrate stage fills the same files ahead of the render)."""
    key = f"{mode}|{spoken}" if VOICE_SPEED == 1.0 else f"{mode}|{VOICE_SPEED:g}|{spoken}"
    if ":" in mode:
        import tts

        engine = mode.split(":", 1)[0]
        key += f"|r{tts.engine(engine).REVISION}"      # how the voice's lines are made changed: speak them again
        language = getattr(tts.engine(engine), "language_setting", None)
        if language and language() != "auto":
            key += f"|{language()}"                        # another accent is another line
        if engine != "chirp":
            key = f"{tts.engine(engine).model()}|{key}"  # another Gemini model is another voice
    return audio_dir() / f"{hashlib.md5(key.encode()).hexdigest()[:12]}.wav"


def cost_file(wav: Path) -> Path:
    """Where a spoken line's cost is kept: {"usd", "in", "out"} (or "chars" for Chirp) beside its wav."""
    return wav.with_suffix(".cost.json")


def line_cost(mode: str, spoken: str) -> float | None:
    """What a line cost when it was spoken (US dollars), or None when it is not spoken yet or was spoken before
    costs were kept."""
    path = cost_file(audio_file(mode, spoken))
    try:
        return float(json.loads(path.read_text()).get("usd", 0.0))
    except (OSError, ValueError):
        return None


_BEATS_DONE = 0


# Off while a build of some chapters runs the chapters before them (export_dsl's window): those beats are
# another build's to count.
PROGRESS_ON = [True]


def _progress_beat() -> None:
    """One more beat drawn, for the page's progress (PANIM_PROGRESS_FILE, which prespeak.py started). Builds of a
    lecture's chapters side by side (PANIM_CHUNK) each keep their own count in the file, and the page sees the
    sum."""
    global _BEATS_DONE
    if not PROGRESS_ON[0]:
        return
    _BEATS_DONE += 1
    path = os.environ.get("PANIM_PROGRESS_FILE")
    if not path:
        return
    window = os.environ.get("PANIM_CHUNK")
    try:
        import fcntl

        with open(path + ".lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(Path(path).read_text()) if Path(path).exists() else {}
            if window:
                counts = dict(state.get("windows") or {})
                counts[window] = _BEATS_DONE
                state["windows"] = counts
                done = sum(int(v) for v in counts.values())
            else:
                done = _BEATS_DONE
            # The phase is the caller's ("render" while exporting, "video" while rendering the MP4).
            state.update(phase=state.get("phase") or "render", done=done,
                         total=state.get("beats") or state.get("total") or 0)
            tmp = Path(path + f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(state))
            tmp.replace(path)
    except (OSError, ValueError):
        pass                                  # progress is a nicety: never a reason for a render to fail


def narrate(text: str) -> tuple[str | None, float]:
    """(wav path or None, seconds) for one line, spoken by the narration voice and cached by voice and words.

    With PANIM_VOICE=silent: no audio, and an estimate of the line's length. A line Google will not speak is an
    error (VoiceUnavailable, with Google's message), not a line in another voice.
    """
    import tts

    spoken = speechify(text)
    mode = voice_mode()
    if mode == "silent":
        return None, estimate_seconds(spoken)
    out = audio_file(mode, spoken)
    cached = _cached_seconds(out)
    if cached is not None:
        return _tight(out)[::2]
    raw = _private(out, "raw")
    engine, voice = mode.split(":", 1)
    speaker = tts.engine(engine)
    try:
        # Said as the voice director marked it, when it did (voice_director.py: delivery tags and emphasis); the
        # line is cached under its plain words all the same.
        raw.write_bytes(speaker.speak(delivery(mode, spoken) or spoken, voice, VOICE_SPEED))
    except RuntimeError as error:
        raw.unlink(missing_ok=True)
        raise VoiceUnavailable(f"{speaker.NAME} could not speak {text[:60]!r}: {error}") from None
    # What the line cost, beside it: a lecture's voice cost is the sum over its lines, and a cached line was paid
    # for once, when it was spoken.
    spent = speaker.last_cost() if hasattr(speaker, "last_cost") else {}
    cost_file(out).write_text(json.dumps({**spent, "engine": engine}))
    # When each word is said, from a voice that says (ElevenLabs): the animations are timed to it (align_cues.py).
    if hasattr(speaker, "last_words"):
        said = speaker.last_words()
        if said:
            words_file(out).write_text(json.dumps(said))
    _finish(raw, out)
    return _tight(out)[::2]


# A line's own silence at either end, cut to a breath: the voices leave a quarter second or more at each end, and
# with the hold after each line it made long gaps between sentences.
LEAD_KEPT, TAIL_KEPT = 0.04, 0.1


def _tight(wav: Path) -> tuple[str, float, float]:
    """(the line with its silence at either end trimmed, the seconds cut from its start, its length). Made once,
    beside the line (the voice is not asked again); the line as it is when it cannot be read."""
    wav = Path(wav)
    out, meta = wav.with_name(f"{wav.stem}.tight.wav"), wav.with_name(f"{wav.stem}.tight.json")
    try:
        known = json.loads(meta.read_text())
        if out.exists():
            return str(out), float(known["lead"]), float(known["seconds"])
    except (OSError, ValueError, KeyError):
        pass
    try:
        with wave.open(str(wav)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            raw = w.readframes(w.getnframes())
        if width != 2:
            raise ValueError("not 16-bit")
        samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
        loud = np.where(np.abs(samples).max(axis=1) > 32768 * 10 ** (-45 / 20))[0]
        if not len(loud):
            raise ValueError("silent")
        first = max(0, loud[0] - int(LEAD_KEPT * rate))
        last = min(len(samples), loud[-1] + 1 + int(TAIL_KEPT * rate))
        part = out.with_name(f"{out.stem}.{os.getpid()}.{threading.get_ident()}.part.wav")
        with wave.open(str(part), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(samples[first:last].tobytes())
        part.replace(out)
        found = (first / rate, (last - first) / rate)
    except (OSError, ValueError, wave.Error):
        return str(wav), 0.0, _wav_seconds(wav)
    meta.write_text(json.dumps({"lead": round(found[0], 4), "seconds": round(found[1], 4)}))
    return str(out), found[0], found[1]


def words_file(wav: Path) -> Path:
    """Where a spoken line's words and their times are kept, beside its wav: [{"w", "start", "end"}] (seconds)."""
    return wav.with_suffix(".words.json")


def line_words(text: str) -> list[dict] | None:
    """The words of a line as the voice said them, with their times: as the voice timed them (ElevenLabs), else
    aligned to its audio here, once, by a small local model (local_align.py) and kept beside the line. None when
    the line is not spoken yet or cannot be aligned."""
    mode = voice_mode()
    if mode == "silent":
        return None
    spoken = speechify(text)
    wav = audio_file(mode, spoken)
    kept = words_file(wav)
    try:
        words = json.loads(kept.read_text())
    except (OSError, ValueError):
        if _cached_seconds(wav) is None:
            return None
        import local_align

        words = local_align.align(wav, spoken)
        # An estimate (no aligner here: local_align.estimate) is used, never kept: the aligner times it once it can.
        if words and not any(w.get("est") for w in words):
            part = kept.with_suffix(f".{os.getpid()}.{threading.get_ident()}.part")
            part.write_text(json.dumps(words, ensure_ascii=False))
            part.replace(kept)
    if not words:
        return words
    # Timed on the line as the voice made it: moved to the line as it is played, its leading silence cut (_tight).
    lead = _tight(wav)[1]
    if lead:
        words = [{**w, "start": max(0.0, float(w["start"]) - lead), "end": max(0.0, float(w["end"]) - lead)}
                 for w in words]
    return words


def delivery_file(mode: str, spoken: str) -> Path:
    """Where the voice director's marked-up version of a line is kept (voice_director.py), beside the lines."""
    return audio_file(mode, spoken).with_suffix(".say.txt")


def delivery(mode: str, spoken: str) -> str | None:
    """The line as the voice director marked it for delivery, or None (the line is said as written)."""
    try:
        marked = delivery_file(mode, spoken).read_text(encoding="utf-8").strip()
        # Spoken at an even pace: a tag that slows the voice or stops it for long is left out (an older marking
        # may carry one).
        return re.sub(r"\s*[\[<](?:slowly|slow|long pause|pause|very slowly)[\]>]\s*", " ", marked,
                      flags=re.I).strip() or None
    except OSError:
        return None


# How batching went this run (narrate_many): batches cut cleanly, batches whose audio could not be cut, batches that
# failed. When it does not work for this voice (two failures and no more successes than failures), the rest of the
# run is spoken a line at a time: a failed batch costs its request and then one request a line.
BATCHES = {"ok": 0, "uncut": 0, "failed": 0, "take_ok": 0, "take_uncut": 0, "take_failed": 0}
_BATCH_LOCK = threading.Lock()


def batching_works() -> bool:
    bad = BATCHES["uncut"] + BATCHES["failed"]
    return bad < 2 or BATCHES["ok"] > bad


def narrate_many(texts: list[str], take: bool = False, fallback: int = 0) -> None:
    """Lines spoken ahead of a build, several in one request where the voice can (gemini_tts.speak_many,
    eleven_tts.speak_many), into the cache narrate() reads: Google allows only so many requests a minute.

    `take`: the lines are a chapter's, spoken whole in one take (tools/prespeak.py), and each keeps the pause the
    voice left after it ("gap" beside its cost), which its beat holds (line_gap). A take that cannot be cut back
    into its lines, or that fails, is spoken again `fallback` lines at a time; a batch that cannot, a line at a time
    (narrate)."""
    import tts

    mode = voice_mode()
    if mode == "silent":
        return
    engine, voice = mode.split(":", 1)
    speaker = tts.engine(engine)
    todo = [t for t in dict.fromkeys(texts) if _cached_seconds(audio_file(mode, speechify(t))) is None]
    many = getattr(speaker, "speak_many", None)
    if many is not None and len(todo) > 1 and (take or batching_works()):
        failed = False
        try:
            # Said as the voice director marked each line, as narrate() says it.
            spoken = many([delivery(mode, speechify(t)) or speechify(t) for t in todo], voice, VOICE_SPEED)
        except Exception:  # noqa: BLE001 -- spoken again below, where the reason is reported
            spoken, failed = None, True
        with _BATCH_LOCK:
            key = "ok" if spoken is not None else "failed" if failed else "uncut"
            BATCHES[f"take_{key}" if take else key] += 1
        if spoken is not None:
            for text, (wav, spent) in zip(todo, spoken):
                out = audio_file(mode, speechify(text))
                raw = _private(out, "raw")
                raw.write_bytes(wav)
                said = spent.pop("words", None)
                if not take:
                    spent.pop("gap", None)
                cost_file(out).write_text(json.dumps({**spent, "engine": engine}))
                if said:
                    words_file(out).write_text(json.dumps(said))
                _finish(raw, out)
            return
        if fallback and len(todo) > fallback:
            for i in range(0, len(todo), fallback):
                narrate_many(todo[i:i + fallback])
            return
    for text in todo:
        narrate(text)


def beat_pad(text: str) -> float:
    """The hold after a line: after a line of a chapter's take, the pause the voice left there (less the breath
    each line keeps at its ends, _tight), so the chapter plays as it was spoken; else the pace's (BEAT_PAD)."""
    pace = os.environ.get("PANIM_PACE", "natural")
    gap = line_gap(text) if pace in ("natural", "teacher") else None
    if gap is None:
        return BEAT_PAD
    held = max(0.12, min(1.2, gap - LEAD_KEPT - TAIL_KEPT))
    return max(held, BEAT_PAD) if pace == "teacher" else held


def line_gap(text: str) -> float | None:
    """The pause the voice left after this line when it was spoken in a chapter's take (narrate_many), in seconds;
    None when it was spoken on its own, or last in its take."""
    mode = voice_mode()
    if mode == "silent":
        return None
    try:
        gap = json.loads(cost_file(audio_file(mode, speechify(text))).read_text()).get("gap")
    except (OSError, ValueError, AttributeError):
        return None
    return float(gap) if isinstance(gap, (int, float)) else None


# ════════════════════════════════════════════════════════════════════════
#  MAP DATA (Natural Earth through Cartopy)
# ════════════════════════════════════════════════════════════════════════


@lru_cache(None)
def _records(name: str, category: str = "cultural", resolution: str = "10m") -> list:
    """A Natural Earth layer's records, (attributes, geometry). Reading a shapefile builds every shape in pure Python
    (1-3 s a layer, and every compile is its own process), so the records are kept once read, pickled beside the
    other caches, and loaded from there (0.03-0.2 s); a newer shapefile is read again."""
    import pickle

    import cartopy.io.shapereader as shpreader

    path = Path(shpreader.natural_earth(resolution=resolution, category=category, name=name))
    stat = path.stat()
    kept = (Path(os.environ.get("PANIM_MAP_CACHE") or Path(__file__).resolve().parent / ".cache" / "maps")
            / f"{name}-{category}-{resolution}-{int(stat.st_mtime)}-{stat.st_size}.pickle")
    try:
        return pickle.loads(kept.read_bytes())
    except (OSError, ValueError, EOFError, pickle.UnpicklingError, AttributeError, ImportError):
        pass
    records = [(rec.attributes, rec.geometry) for rec in shpreader.Reader(str(path)).records()]
    try:
        kept.parent.mkdir(parents=True, exist_ok=True)
        part = kept.with_suffix(f".{os.getpid()}.part")
        part.write_bytes(pickle.dumps(records, protocol=pickle.HIGHEST_PROTOCOL))
        part.replace(kept)                      # whole or not at all: compiles run side by side
    except OSError:
        pass
    return records


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


# Every map draws borders as India does (Natural Earth's India point of view): the whole of Jammu and Kashmir and
# Ladakh -- Gilgit-Baltistan, PoK and Aksai Chin -- inside India. PANIM_MAP_VIEW=default (or a region's
# "view": "default") draws Natural Earth's own borders instead.
MAP_VIEW = os.environ.get("PANIM_MAP_VIEW", "ind").strip().lower() or "ind"


def countries_dataset(view: str | None = None) -> str:
    """The country borders a map draws: India's view unless asked otherwise."""
    return "admin_0_countries_ind" if (view or MAP_VIEW) == "ind" else "admin_0_countries"


def country(name: str, view: str | None = None):
    """A country's outline, its borders as India draws them (countries_dataset)."""
    dataset = countries_dataset(view)
    wanted = _norm(name)
    for attrs, geom in _records(dataset):
        names = {_norm(attrs.get(k)) for k in ("ADMIN", "NAME", "NAME_LONG", "SOVEREIGNT", "ISO_A3")}
        if wanted in names:
            return _valid(geom)
    raise KeyError(f"no country named {name!r} in Natural Earth")


def _home_parts(geom):
    """A country's land at home, without its overseas parts: the largest piece, and every piece that is big beside
    it (Alaska) or lies near it (Corsica, the Andamans). French Guiana, Reunion, the Canaries and Hawaii go, so a
    map of France or Western Europe is not stretched across an ocean."""
    from shapely.geometry import MultiPolygon
    from shapely.ops import unary_union

    if geom is None or geom.geom_type != "MultiPolygon":
        return geom
    parts = sorted(geom.geoms, key=lambda p: p.area, reverse=True)
    big = parts[0]
    lon0, lat0, lon1, lat1 = big.bounds
    reach = max(3.0, 0.35 * max(lon1 - lon0, lat1 - lat0))
    kept = [big] + [p for p in parts[1:] if p.area >= 0.15 * big.area or p.distance(big) <= reach]
    return kept[0] if len(kept) == 1 else MultiPolygon(kept) if all(
        k.geom_type == "Polygon" for k in kept) else unary_union(kept)


def country_home(name: str, view: str | None = None):
    """A country's outline without its overseas parts (_home_parts): what a map of it is fitted to and draws."""
    return _home_parts(country(name, view))


# ---------------- areas: the world, a continent, a world region ----------------
WORLD_NAMES = {"world", "the world", "whole world", "earth", "the earth", "globe", "world map", "planet earth"}
# Groups Natural Earth does not tag, by their member countries (its ADMIN names).
AREA_GROUPS = {
    "middle east": ["Saudi Arabia", "Iran", "Iraq", "Syria", "Jordan", "Israel", "Palestine", "Lebanon", "Turkey",
                    "Egypt", "Yemen", "Oman", "United Arab Emirates", "Qatar", "Bahrain", "Kuwait", "Cyprus"],
    "indian subcontinent": ["India", "Pakistan", "Bangladesh", "Nepal", "Bhutan", "Sri Lanka", "Maldives"],
    "subcontinent": ["India", "Pakistan", "Bangladesh", "Nepal", "Bhutan", "Sri Lanka", "Maldives"],
    "saarc": ["India", "Pakistan", "Bangladesh", "Nepal", "Bhutan", "Sri Lanka", "Maldives", "Afghanistan"],
    "americas": None, "the americas": None,      # both continents (below)
}
# Where the map of an area is framed, when its countries reach far beyond it (Natural Earth's Europe holds all of
# Russia, to the Pacific).
AREA_FRAMES = {"europe": (-25.0, 34.0, 45.0, 72.0)}


def _area_key(name: str) -> str:
    return _norm(str(name).replace("&", "and"))


@lru_cache(None)
def area_members(name: str) -> tuple:
    """The countries (ADMIN names) of an area -- the world, a continent ("Asia"), a UN subregion ("Southern Asia",
    "Western Europe"), a World Bank region ("South Asia", "Middle East and North Africa") or a group ("Middle
    East", "Indian subcontinent") -- or () when the name is none of these."""
    key = _area_key(name)
    rows = [(str(a.get("ADMIN")), a) for a, _ in _records(countries_dataset())]
    if key in WORLD_NAMES:
        return tuple(n for n, a in rows if a.get("CONTINENT") not in ("Antarctica", "Seven seas (open ocean)"))
    if key in ("americas", "the americas"):
        return tuple(n for n, a in rows if a.get("CONTINENT") in ("North America", "South America"))
    if key in AREA_GROUPS:
        wanted = {_norm(x) for x in AREA_GROUPS[key]}
        return tuple(n for n, _ in rows if _norm(n) in wanted)
    for field in ("CONTINENT", "SUBREGION", "REGION_WB", "REGION_UN"):
        found = tuple(n for n, a in rows if _area_key(a.get(field) or "") == key)
        if found:
            return found
    return ()


@lru_cache(None)
def area(name: str):
    """An area's land, the union of its countries (simplified a little: a continent need not be drawn to the
    metre)."""
    from shapely.ops import unary_union

    members = {_norm(m) for m in area_members(name)}
    if not members:
        raise KeyError(f"no country, continent or world area named {name!r}")
    # Each country without its overseas parts (France without French Guiana): Western Europe ends at the Atlantic.
    # The world keeps every island.
    whole = _area_key(name) in WORLD_NAMES
    parts = [_valid(g if whole else _home_parts(_valid(g))).simplify(0.02)
             for a, g in _records(countries_dataset()) if _norm(a.get("ADMIN")) in members]
    return _valid(unary_union(parts))


def region_kind(region: dict) -> str:
    """"state", "country" or "area" (the world, a continent, a world region) for a script's region; KeyError when
    it names none of these."""
    if region.get("state"):
        state(region["state"], region.get("country"))
        return "state"
    name = region.get("area") or region.get("continent") or region.get("country")
    if not name:
        raise KeyError("a region names a country, a state (with its country) or an area")
    if not (region.get("area") or region.get("continent")):
        try:
            country(name, region.get("view"))
            return "country"
        except KeyError:
            pass
    if area_members(name):
        return "area"
    raise KeyError(f"no country, state, continent or world area named {name!r}")


# India's union territories as India draws them: Jammu and Kashmir with PoK (Pakistan's "Azad Kashmir"), Ladakh with
# Gilgit-Baltistan (Pakistan's "Northern Areas") and Aksai Chin.
INDIA_CLAIMS = {"jammu and kashmir": ["Azad Kashmir"], "ladakh": ["Northern Areas"]}


def _raw_state(name: str, country_name: str | None = None):
    """(its country, its shape) as Natural Earth has it."""
    wanted = _norm(name)
    scope = _norm(country_name) if country_name else None
    for attrs, geom in _records("admin_1_states_provinces"):
        if scope and scope not in (_norm(attrs.get("admin")), _norm(attrs.get("adm0_a3"))):
            continue
        if wanted in (_norm(attrs.get("name")), _norm(attrs.get("name_en"))):
            return str(attrs.get("admin")), _valid(geom)
    raise KeyError(f"no state named {name!r}" + (f" in {country_name}" if country_name else ""))


@lru_cache(None)
def _india_states() -> dict:
    """India's states and union territories with their borders as India draws them (MAP_VIEW "ind")."""
    from shapely.ops import unary_union

    rows = {str(a.get("name")): _valid(g) for a, g in _records("admin_1_states_provinces")
            if _norm(a.get("admin")) == "india"}
    india = country("India")
    claimed = {}
    for own, others in INDIA_CLAIMS.items():
        key = next((k for k in rows if _norm(k) == own), None)
        if key is None:
            continue
        claimed[key] = [rows[key]] + [_raw_state(o, "Pakistan")[1] for o in others]
    # What India's outline holds that no state does (Aksai Chin, the Shaksgam valley) is Ladakh's.
    covered = unary_union(list(rows.values()) + [g for parts in claimed.values() for g in parts[1:]])
    rest = _valid(india.difference(covered))
    # Only real land in the north (Aksai Chin, Shaksgam): elsewhere the difference is slivers where the two
    # datasets' lines do not quite meet.
    pieces = [g for g in getattr(rest, "geoms", [rest]) if g.geom_type == "Polygon" and g.area > 0.05
              and g.centroid.y > 32.0 and 72.0 < g.centroid.x < 81.0]
    ladakh = next((k for k in claimed if _norm(k) == "ladakh"), None)
    if ladakh and pieces:
        claimed[ladakh] += pieces
    for key, parts in claimed.items():
        rows[key] = _valid(unary_union(parts).intersection(india))
    return rows


def _india_view() -> bool:
    return MAP_VIEW == "ind"


def state(name: str, country_name: str | None = None):
    """A first-level division (state, province) by name, its borders as the map draws them: in India's view a
    state of India keeps all India claims (Jammu and Kashmir with PoK, Ladakh with Gilgit-Baltistan and Aksai
    Chin), and another country's is cut to its border as India draws it."""
    home, geom = _raw_state(name, country_name)
    if not _india_view():
        return geom
    if _norm(home) == "india":
        rows = _india_states()
        key = next((k for k in rows if _norm(k) == _norm(name)), None)
        if key is not None:
            return rows[key]
    clipped = _valid(geom.intersection(country(home)))
    return geom if clipped.is_empty else clipped


# English names of regions Natural Earth keeps under their own (a French region, a part of a country).
REGION_ALIASES = {"normandy": "normandie", "brittany": "bretagne", "burgundy": "bourgogne-franche-comte",
                  "aquitaine": "nouvelle-aquitaine", "provence": "provence-alpes-cote-d'azur",
                  "alsace": "grand est", "lorraine": "grand est", "champagne": "grand est",
                  "picardy": "hauts-de-france", "flanders": "vlaanderen", "wallonia": "wallonie"}


@lru_cache(None)
def _state_group(name: str, country_name: str | None = None):
    """A region made of several first-level divisions, by the region they belong to: England, Scotland and Wales
    (the United Kingdom's countries), Normandy and Brittany (France's regions), Flanders. Their union; KeyError
    when no division belongs to one so named."""
    from shapely.ops import unary_union

    wanted = _norm(REGION_ALIASES.get(_norm(name), name))
    scope = _norm(country_name) if country_name else None
    parts = []
    for attrs, geom in _records("admin_1_states_provinces"):
        if scope and scope not in (_norm(attrs.get("admin")), _norm(attrs.get("adm0_a3"))):
            continue
        if wanted in (_norm(attrs.get("region")), _norm(attrs.get("geonunit")), _norm(attrs.get("region_sub"))):
            parts.append(_valid(geom))
    if not parts:
        raise KeyError(f"no region named {name!r}")
    return _valid(unary_union(parts))


# ---------------- places a lecture names that no gazetteer has: its own ("places") ----------------
# A script may carry "places": {name: spec}, filled by the map agent (harness/scripts/map_agent.py) for what the
# lookups below cannot find (a chain of shoals, a climate zone, a country's own name for its highlands):
#   {"lonlat": [lon, lat]}                       a point
#   {"states": [province, ...]}                   an area: those first-level divisions of the map's country, joined
#   {"outline": [[lon, lat], ...]}                an area drawn round, cut to the land (unless "sea": true)
#   an area with "kind": "mountains"              a range: relief draws it
# The compiler hands them to the scene with set_places(); place(), area_shape() and relief() look there first.
PLACES: dict = {}


def set_places(places: dict | None, country_name: str | None = None) -> None:
    """The lecture's own places (see PLACES), by their normalised names."""
    PLACES.clear()
    for name, spec in (places or {}).items():
        if isinstance(spec, dict) and _norm(name):
            PLACES[_norm(name)] = {**spec, "_name": str(name), "_country": spec.get("country") or country_name}
    _own_shape.cache_clear()


def own_place(name: str) -> dict | None:
    return PLACES.get(_norm(name))


@lru_cache(None)
def _own_shape(key: str):
    """The shape of one of the lecture's own areas, or None (a point, or a spec that draws nothing)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    spec = PLACES.get(key) or {}
    home = spec.get("_country")
    parts = []
    for province in spec.get("states") or []:
        try:
            parts.append(state(str(province), home))
        except KeyError:
            continue
    outline = spec.get("outline") or []
    if len(outline) >= 3:
        try:
            ring = _valid(Polygon([(float(p[0]), float(p[1])) for p in outline]))
            if home and not spec.get("sea"):
                try:
                    ring = _valid(ring.intersection(country(home)))
                except KeyError:
                    pass
            if not ring.is_empty:
                parts.append(ring)
        except (TypeError, ValueError, IndexError):
            pass
    return _valid(unary_union(parts)) if parts else None


def _own_point(name: str, bounds=None):
    spec = own_place(name)
    if not spec:
        return None
    if isinstance(spec.get("lonlat"), (list, tuple)) and len(spec["lonlat"]) == 2:
        return float(spec["lonlat"][0]), float(spec["lonlat"][1])
    shape = _own_shape(_norm(name))
    return _shape_point(shape, bounds) if shape is not None else None


def _shape_point(shape, bounds=None):
    """Where a name on an area goes: inside the part of it on the map (the Bay of Bengal's label in the bay on a
    map of Sri Lanka, not 600 km north of it)."""
    if bounds:
        on_map = shape.intersection(_box(bounds))
        if not on_map.is_empty:
            shape = on_map
    point = shape.representative_point()
    return round(point.x, 4), round(point.y, 4)


# Natural Earth's physical names: seas, bays, gulfs and straits; peaks; capes; deserts, ranges and plateaus.
PHYSICAL_LAYERS = (("geography_marine_polys", "name"), ("geography_regions_elevation_points", "name"),
                   ("geography_regions_points", "name"), ("geography_regions_polys", "NAME"))


@lru_cache(None)
def _physical_by_name() -> dict:
    """Natural Earth's physical features by each of their names (normalised): [(layer, attributes, shape)]. A layer
    that cannot be had (not downloaded, and no network) is left out."""
    out: dict = {}
    for layer, field in PHYSICAL_LAYERS:
        try:
            records = _records(layer, "physical", "10m")
        except Exception:  # noqa: BLE001 -- the other lookups still work
            continue
        for attrs, geom in records:
            if geom is None:
                continue
            names = {attrs.get(field), attrs.get("name_en"), attrs.get("NAME_EN")}
            for alt in str(attrs.get("namealt") or attrs.get("NAMEALT") or attrs.get("name_alt") or "").split("|"):
                names.add(alt)
            for key in {_norm(n) for n in names if n} - {""}:
                out.setdefault(key, []).append((layer, attrs, geom))
    return out


def physical_feature(name: str, bounds=None):
    """A sea, bay, gulf, strait, peak, cape, range or plateau by name: (its shape, its kind), one on the map first;
    None when Natural Earth has none so named."""
    wanted = _norm(name)
    rows = _physical_by_name().get(wanted) or _physical_by_name().get(re.sub(r"^the ", "", wanted))
    if not rows:
        return None
    on_map = [r for r in rows if not bounds or r[2].intersects(_box(bounds))]
    layer, attrs, geom = (on_map or rows)[0]
    shape = geom if geom.geom_type in ("Point", "MultiPoint") else _valid(geom)
    return shape, str(attrs.get("featurecla") or attrs.get("FEATURECLA") or layer)


def is_water(name: str) -> bool:
    """A sea, bay, gulf or strait (Natural Earth's marine names, or the lecture's own with "sea": true): named on
    the water, not shaded like a country."""
    own = own_place(name)
    if own:
        return bool(own.get("sea"))
    rows = _physical_by_name().get(_norm(name)) or []
    return bool(rows) and all(layer == "geography_marine_polys" for layer, _a, _g in rows)


def area_shape(name: str, country_name: str | None = None):
    """The land a name stands for on a map, when it is an area rather than a point: a state or province (of the
    map's country first), a country, or a wider area (a continent, "Western Europe"). Raises KeyError when the
    name is none of them (a town, a site). The lecture's own places first; Natural Earth's seas, bays and ranges
    last."""
    if own_place(name):
        shape = _own_shape(_norm(name))
        if shape is None:
            raise KeyError(f"{name!r} is a point of this lecture's own, not an area")
        return shape
    if country_name:
        try:
            return state(name, country_name)
        except KeyError:
            pass
    try:
        return country(name)
    except KeyError:
        pass
    try:
        return state(name, None)
    except (KeyError, TypeError):
        pass
    for scope in ([country_name] if country_name else []) + [None]:
        try:
            return _state_group(name, scope)
        except KeyError:
            pass
    try:
        return area(name)
    except KeyError:
        feature = physical_feature(name)
        if feature is None or feature[0].geom_type in ("Point", "MultiPoint"):
            raise
        return feature[0]


def states_of(country_name: str) -> list[tuple[str, object]]:
    scope = _norm(country_name)
    if _india_view() and scope in ("india", "ind"):
        return list(_india_states().items())
    rows = [
        (str(attrs.get("name")), geom)
        for attrs, geom in _records("admin_1_states_provinces")
        if scope in (_norm(attrs.get("admin")), _norm(attrs.get("adm0_a3")))
    ]
    if not _india_view() or not rows:
        return rows
    try:
        outline = country(country_name)
    except KeyError:
        return rows
    out = []
    for name, geom in rows:
        geom = _valid(geom)
        clipped = _valid(geom.intersection(outline))
        # A state India counts as its own (PoK, Gilgit-Baltistan) leaves only slivers inside the border: dropped.
        if not clipped.is_empty and clipped.area > 0.05 * max(geom.area, 1e-9):
            out.append((name, clipped))
    return out


def countries_in(bounds, view: str | None = None, exclude=()) -> list[tuple[str, object]]:
    from shapely.geometry import box

    frame = box(*bounds)
    dataset = countries_dataset(view)
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


def _inside(point, bounds) -> bool:
    if not bounds or point is None:
        return True
    lon0, lat0, lon1, lat1 = bounds
    return lon0 <= point[0] <= lon1 and lat0 <= point[1] <= lat1


@lru_cache(None)
def _places_by_name() -> dict:
    """Natural Earth's populated places by each of their names (normalised): built once, not a scan of all 7,000
    with every name normalised again for each place a lecture names."""
    out: dict[str, list] = {}
    for attrs, _geom in _records("populated_places"):
        for key in {_norm(attrs.get("NAME")), _norm(attrs.get("NAMEASCII")), _norm(attrs.get("NAME_EN"))} - {""}:
            out.setdefault(key, []).append(attrs)
    return out


def _natural_earth_place(name: str, scope: str | None, bounds=None):
    """The most populous place of that name, preferring one on the map (`bounds`): two towns share a name."""
    wanted = _norm(name)
    if not wanted:
        return None
    best = None
    for attrs in _places_by_name().get(wanted, ()):
        if scope and scope not in (_norm(attrs.get("ADM0NAME")), _norm(attrs.get("SOV0NAME")), _norm(attrs.get("ADM0_A3"))):
            continue
        point = (float(attrs["LONGITUDE"]), float(attrs["LATITUDE"]))
        rank = (_inside(point, bounds), float(attrs.get("POP_MAX") or 0))
        if best is None or rank > best[0]:
            best = (rank, point)
    return best[1] if best else None


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


def _geonames_place(name: str, country_name: str | None, bounds=None):
    rows = _geonames().get(_norm(name))
    if not rows:
        return None
    if country_name:
        code = _country_codes().get(_norm(country_name))
        rows = [r for r in rows if r[3] == code] if code else rows
    if not rows:
        return None
    best = max(rows, key=lambda r: (_inside((r[1], r[2]), bounds), r[0]))
    return best[1], best[2]


def _geocode_cache_path() -> Path:
    return Path(os.environ.get("PANIM_GEOCODE_CACHE") or (HERE / ".cache" / "geocode.json"))


# What a teaching map marks: towns, regions, historic sites, natural features. A hospital or a shop that shares a
# name ("Kalinga") is not it.
_GEO_CLASSES = {"place": 3, "boundary": 3, "historic": 3, "natural": 2, "tourism": 2, "waterway": 1, "landuse": 1}


def _geocode(name: str, country_name: str | None, bounds=None):
    """OpenStreetMap's Nominatim, once per name, cached on disk. PANIM_GEOCODE=0 turns it off.

    It is asked for a few answers, near the map when its bounds are known, and the best is kept: one on the map
    before one off it, a town, region or historic site before a building that shares the name, then the most
    important. The cache makes a render reproducible and offline after the first lookup; a failed lookup is
    cached too, so a missing name costs one request.
    """
    import json

    if os.environ.get("PANIM_GEOCODE", "1") == "0":
        return None
    box = ",".join(f"{v:.1f}" for v in bounds) if bounds else ""
    key = f"{_norm(name)}|{_norm(country_name)}|{box}"
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

        params = {"q": f"{name}, {country_name}" if country_name else name, "format": "json", "limit": 6}
        if bounds:
            lon0, lat0, lon1, lat1 = bounds
            params["viewbox"] = f"{lon0},{lat1},{lon1},{lat0}"
        request = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{urllib.parse.urlencode(params)}",
                                         headers={"User-Agent": "pocketanim-lecture/0.4 (map lectures)"})
        with urllib.request.urlopen(request, timeout=8) as response:
            rows = json.loads(response.read().decode())
        best = None
        for row in rows:
            point = (round(float(row["lon"]), 4), round(float(row["lat"]), 4))
            rank = (_inside(point, bounds), _GEO_CLASSES.get(str(row.get("class")), 0), float(row.get("importance") or 0))
            if rank[1] and (best is None or rank > best[0]):
                best = (rank, point)
        found = best[1] if best else None
    except Exception:  # noqa: BLE001 -- offline, blocked or rate limited: not cached, tried again next time
        return None
    cache[key] = list(found) if found else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    return found


def place(name: str, country_name: str | None = None, bounds=None) -> tuple[float, float]:
    """(lon, lat) of a place.

    From, in order: the lecture's own places (set_places); Natural Earth's populated places (the most populous
    match), under the name or its renamed form; data/places_extra.csv (historic and teaching sites); the GeoNames
    gazetteer when fetch_gazetteer.py has downloaded it; Natural Earth's seas, gulfs, straits and peaks; then
    OpenStreetMap, cached. First in `country_name`, then anywhere (Harappa on a map of India
    is in Pakistan). With the map's `bounds`, a place on the map wins over one of the same name off it (two towns
    called Aurangabad); one off it is kept only if nothing on it matches. Raises KeyError when none knows it.
    """
    own = _own_point(name, bounds)
    if own is not None:
        return own
    names = [name]
    for old, new in PLACE_ALIASES.items():
        if _norm(name) == _norm(old):
            names.append(new)
        elif _norm(name) == _norm(new):
            names.append(old)
    extra = _extra_places()
    off_map = None
    for scope_name in ([country_name, None] if country_name else [None]):
        scope = _norm(scope_name) if scope_name else None
        found = []
        for candidate in names:
            found.append(_natural_earth_place(candidate, scope, bounds))
            row = extra.get(_norm(candidate))
            found.append((row[0], row[1]) if row and (not scope or row[2] == scope) else None)
            found.append(_geonames_place(candidate, scope_name, bounds))
        if scope_name is None:
            # A sea, a gulf, a strait, a peak (Natural Earth's physical names): in no country.
            feature = physical_feature(name, bounds)
            found.append(_shape_point(feature[0], bounds) if feature else None)
        found.append(_geocode(name, scope_name, bounds))
        for point in found:
            if point and _inside(point, bounds):
                return point
            if point and off_map is None:
                off_map = point
    # A country named as a place (Flanders' revolt "in France"): the middle of its land at home.
    try:
        home = country_home(name)
        point = home.representative_point()
        point = (round(point.x, 4), round(point.y, 4))
        if _inside(point, bounds) or not off_map:
            return point
    except KeyError:
        pass
    if off_map:
        return off_map
    hint = "" if GEONAMES.exists() else " (run harness/scripts/fetch_gazetteer.py to add 150,000 more towns)"
    raise KeyError(f"no place named {name!r}" + (f" in {country_name}" if country_name else "") + hint)


# How far past the map's land a place may lie and still be looked up on it: a country's or a state's map shows its
# neighbours round it (Harappa on a map of India); an area's map is the area, a little past its edge.
PLACE_MARGIN = {"area": 0.12, "country": 0.45, "state": 0.45}


def _padded(bounds, share: float) -> tuple:
    lon0, lat0, lon1, lat1 = bounds
    pad = max(lon1 - lon0, lat1 - lat0) * share
    return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)


def map_bounds(region: dict) -> tuple | None:
    """The lon/lat window places are looked up in on a region's map (MapLecture.place_bounds): the land the map is
    fitted to (a country without its overseas parts, an area's frame), a little past it."""
    try:
        kind = region_kind(region)
        if kind == "state":
            focus = state(region["state"], region.get("country"))
        elif kind == "area":
            name = region.get("area") or region.get("continent") or region.get("country")
            frame = AREA_FRAMES.get(_area_key(name))
            focus = _box(frame) if frame else area(name)
        else:
            focus = country_home(region["country"], region.get("view"))
    except KeyError:
        return None
    return _padded(focus.bounds, PLACE_MARGIN[kind])


def _on_globe(geom, least: float = 2.0):
    """A map's focus as it can be projected: cut to the globe (a box padded past a pole or the date line went off
    it), and at least `least` degrees each way (one place, a line of latitude: a map of nothing across)."""
    from shapely.geometry import box

    world = box(-180.0, -85.0, 180.0, 85.0)
    try:
        inside = geom if world.contains(geom) else _valid(geom).intersection(world)
    except Exception:  # noqa: BLE001 -- a shape that cannot be cut: its bounds
        inside = box(*geom.bounds)
    if inside.is_empty:
        lon0, lat0, lon1, lat1 = geom.bounds
        lon0, lon1 = sorted((min(max(lon0, -180.0), 180.0), min(max(lon1, -180.0), 180.0)))
        lat0, lat1 = sorted((min(max(lat0, -85.0), 85.0), min(max(lat1, -85.0), 85.0)))
        inside = box(lon0, lat0, lon1, lat1)
    lon0, lat0, lon1, lat1 = inside.bounds
    if lon1 - lon0 >= least and lat1 - lat0 >= least:
        return inside
    cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    half_w, half_h = max(lon1 - lon0, least) / 2, max(lat1 - lat0, least) / 2
    cx, cy = min(max(cx, -180.0 + half_w), 180.0 - half_w), min(max(cy, -85.0 + half_h), 85.0 - half_h)
    return box(cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def _cut_at(geom, lon: float, gap: float = 1e-4):
    """A shape cut along a meridian into its parts either side (none of them crosses it)."""
    from shapely.geometry import box
    from shapely.ops import unary_union

    west, east = box(-180.0, -90.0, lon - gap, 90.0), box(lon + gap, -90.0, 180.0, 90.0)
    lo, hi = geom.bounds[0], geom.bounds[2]
    if hi < lon - gap or lo > lon + gap:
        return geom
    whole = _valid(geom) if geom.geom_type in ("Polygon", "MultiPolygon") else geom
    parts = [g for g in (whole.intersection(west), whole.intersection(east)) if not g.is_empty]
    return unary_union(parts) if parts else geom


class MapFrame:
    """One projection and one linear map into scene units, for every layer.

    Every map element -- outlines, rivers, markers, graticules -- goes through
    the same Cartopy projection and the same scale and offset, which is what
    keeps them lined up.
    """

    def __init__(self, focus, center=(-3.0, 0.2), height=6.3, width=6.5, crs=None, clip=True):
        import cartopy.crs as ccrs

        focus = _on_globe(focus)
        lon0, lat0, lon1, lat1 = focus.bounds
        # What is drawn is cut to a window round the map first: a conic projection sends what lies far from it (the
        # far side of Russia on a map of Europe) to infinity. Robinson can draw anything: no window.
        self.window = None
        self.seam = None
        if crs is None and lon1 - lon0 > 100:
            # The world, or most of a hemisphere: a conic projection tears; Robinson draws it as an atlas does.
            middle = 0.0 if lon1 - lon0 > 300 else (lon0 + lon1) / 2
            crs = ccrs.Robinson(central_longitude=middle)
            # Turned from Greenwich, the map's back edge is a meridian Natural Earth's shapes run across (they are
            # cut at 180 only): a coast on both sides of it was joined by a line straight across the map. Shapes are
            # cut there before they are drawn.
            back = (middle + 180.0 + 180.0) % 360.0 - 180.0
            if abs(abs(back) - 180.0) > 1e-6:
                self.seam = back
        elif crs is None:
            from shapely.geometry import box as _shape_box

            pad = max(lon1 - lon0, lat1 - lat0, 5.0)
            self.window = _shape_box(max(-180.0, lon0 - pad), max(-85.0, lat0 - pad),
                                     min(180.0, lon1 + pad), min(85.0, lat1 + pad))
        if crs is None:
            span = max(lat1 - lat0, 1.0)
            crs = ccrs.LambertConformal(
                central_longitude=(lon0 + lon1) / 2, central_latitude=(lat0 + lat1) / 2,
                standard_parallels=(lat0 + span / 6, lat1 - span / 6),
            )
        self.crs = crs
        self.pc = ccrs.PlateCarree()
        x0, y0, x1, y1 = self.project_geom(focus, scale=False).bounds
        if not all(np.isfinite([x0, y0, x1, y1])) or x1 - x0 <= 1e-9 or y1 - y0 <= 1e-9:
            # Nothing measurable came out of the projection (a shape it sends to a point or to infinity): the box
            # round it, on the world's own projection, rather than a map that cannot be scaled.
            self.window, self.seam = None, None
            self.crs = ccrs.Robinson(central_longitude=0.0)
            x0, y0, x1, y1 = self.project_geom(_box(focus.bounds), scale=False).bounds
        self.c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        self.s = min(height / (y1 - y0), width / (x1 - x0))
        self.center = np.array(center, dtype=float)
        # Shapes are cut at the panel's left edge: nothing under the panel is
        # ever seen, and baking it only makes the asset bigger.
        # Cut at the panel's edge (a number: at that x instead, for a map drawn across the whole frame).
        right = PANEL_X if clip is True else float(clip) if clip else None
        self.clip = (-7.4, -4.3, right, 4.3) if right is not None else None

    def xy(self, lon, lat) -> np.ndarray:
        lon = np.atleast_1d(np.asarray(lon, float))
        # Off the poles: a conic projection sends the pole away from its cone to no number at all (NaN), and one
        # NaN point made the player's whole film unreadable ("Unexpected token 'N'").
        lat = np.clip(np.atleast_1d(np.asarray(lat, float)), -85.0, 85.0)
        p = self.crs.transform_points(self.pc, lon, lat)[:, :2]
        out = (p - self.c) * self.s + self.center
        # What the projection still cannot place (far round the globe) is put far off the map, never NaN.
        return np.where(np.isfinite(out), np.clip(out, -1e3, 1e3), 1e3)

    def pt(self, lon, lat) -> np.ndarray:
        x, y = self.xy(lon, lat)[0]
        return np.array([x, y, 0.0])

    def project_geom(self, geom, scale=True):
        from shapely.ops import transform

        if self.window is not None and not self.window.contains(geom):
            geom = geom.intersection(self.window)
        if self.seam is not None:
            geom = _cut_at(geom, self.seam)

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
        group = VGroup()
        for p in polys:
            if p.area < min_area:
                continue
            pts = np.array(p.exterior.coords)
            m = VMobject(**style)
            m.set_points_as_corners(np.c_[pts, np.zeros(len(pts))])
            # Natural Earth's line, as projected: an art style colours it but never moves a point (artstyle.exact).
            m._art_exact = True
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
            m._art_exact = True
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
_SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
_SUB_OK = set("0123456789+-=()aehijklmnoprstuvx")
_SUPER_OK = set("0123456789+-=()ni")


def _script(body: str, ok: set, table, mark: str) -> str:
    """A sub- or superscript in Unicode when every character has a small form, else written out (F_(net))."""
    body = body.strip()
    if body and all(c in ok for c in body):
        return body.translate(table)
    return f"{mark}{body}" if len(body) == 1 else f"{mark}({body})"
_TEX_WORDS = {r"\times": "×", r"\cdot": "·", r"\pm": "±", r"\div": "÷", r"\leq": "≤", r"\geq": "≥",
              r"\neq": "≠", r"\approx": "≈", r"\infty": "∞", r"\rightarrow": "→", r"\to": "→",
              r"\leftrightarrow": "↔", r"\rightleftharpoons": "⇌", r"\Delta": "Δ", r"\delta": "δ",
              r"\pi": "π", r"\theta": "θ", r"\lambda": "λ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ",
              r"\omega": "ω", r"\Omega": "Ω", r"\mu": "μ", r"\sigma": "σ", r"\rho": "ρ", r"\phi": "φ",
              r"\sum": "Σ", r"\int": "∫", r"\partial": "∂", r"\nabla": "∇", r"\degree": "°", r"\circ": "°",
              r"\Rightarrow": "⇒", r"\implies": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔", r"\iff": "⇔",
              r"\leftarrow": "←", r"\le": "≤", r"\ge": "≥", r"\ne": "≠", r"\sim": "~", r"\propto": "∝",
              r"\perp": "⊥", r"\parallel": "∥", r"\angle": "∠", r"\triangle": "△", r"\therefore": "∴",
              r"\because": "∵", r"\cdots": "⋯", r"\ldots": "…", r"\dots": "…", r"\hbar": "ħ", r"\ell": "ℓ",
              r"\tau": "τ", r"\epsilon": "ε", r"\varepsilon": "ε", r"\eta": "η", r"\kappa": "κ", r"\nu": "ν",
              r"\xi": "ξ", r"\psi": "ψ", r"\chi": "χ", r"\zeta": "ζ", r"\varphi": "φ", r"\Phi": "Φ",
              r"\Sigma": "Σ", r"\Lambda": "Λ", r"\Gamma": "Γ", r"\Theta": "Θ", r"\Pi": "Π", r"\Psi": "Ψ",
              r"\%": "%", r"\{": "{", r"\}": "}", r"\&": "&", r"\#": "#"}
# TeX that only changes how maths looks: dropped, keeping what it wraps.
_TEX_FONTS = r"text|textrm|textbf|textit|mathrm|mathbf|mathit|mathsf|mathcal|boldsymbol|bm|operatorname|mbox|hbox"


def unicode_math(tex: str) -> str:
    """LaTeX-ish maths as plain Unicode, for machines without LaTeX: E = mc^2 -> E = mc², H_2O -> H₂O."""
    text = str(tex)
    text = re.sub(r"\\[td]frac", r"\\frac", text)
    text = re.sub(r"\\frac\s*(\d)\s*(\d)", r"\\frac{\1}{\2}", text)       # \frac12
    text = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)(?![a-zA-Z])\s*", "", text)
    text = re.sub(r"\\(?:displaystyle|textstyle|limits|nolimits)(?![a-zA-Z])\s*", "", text)
    text = re.sub(r"\\(?:quad|qquad)(?![a-zA-Z])\s*", "  ", text)
    text = re.sub(r"\\[,;:!> ]", " ", text)
    text = re.sub(r"\\(?:vec|overrightarrow)\{([^{}]*)\}", "\\1\u20d7", text)
    text = re.sub(r"\\(?:bar|overline)\{([^{}]*)\}", "\\1\u0304", text)
    text = re.sub(r"\\hat\{([^{}]*)\}", "\\1\u0302", text)
    for _ in range(4):
        text = re.sub(r"\\(?:" + _TEX_FONTS + r")\s*\{([^{}]*)\}", r"\1", text)
    # Font switches without braces: \rm ext, \mathbf F.
    text = re.sub(r"(\{)?\\(?:rm|bf|it|sf|mathbf|mathrm|boldsymbol)(?![a-zA-Z])\s*",
                  lambda m: m.group(1) or "{}", text)
    # Innermost first, until nothing changes: a square root inside a fraction.
    for _ in range(6):
        before = text
        text = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", text)
        # A simple fraction reads F/m; one with an operator in it keeps brackets, (a + b)/(2c).
        text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}",
                      lambda m: "/".join(f"({p.strip()})" if re.search(r"[\s+\-−=·×]", p.strip()) else p.strip()
                                         for p in m.groups()), text)
        text = re.sub(r"\^\{([^{}\\]*)\}", lambda m: _script(m.group(1), _SUPER_OK, _SUPER, "^"), text)
        text = re.sub(r"_\{([^{}\\]*)\}", lambda m: _script(m.group(1), _SUB_OK, _SUB, "_"), text)
        if text == before:
            break
    # A command swallows the space after it, as in LaTeX.
    for word in sorted(_TEX_WORDS, key=len, reverse=True):
        symbol = _TEX_WORDS[word]
        swallow = " ?" if symbol.isalpha() else ""      # Greek letters join the next symbol; operators keep space
        text = re.sub(re.escape(word) + r"(?![a-zA-Z])" + swallow, symbol, text)
    text = text.replace("\\sqrt", "√")
    text = re.sub(r"\^([0-9n+\-i])", lambda m: m.group(1).translate(_SUPER), text)
    text = re.sub(r"_([0-9])|_([aehijklmnoprstuvx])(?![a-zA-Z])", lambda m: (m.group(1) or m.group(2)).translate(_SUB),
                  text)
    text = text.replace("<=>", "⇌").replace("->", "→").replace("*", "·").replace("{", "").replace("}", "")
    return re.sub(r"\\([a-zA-Z]+)", r"\1", text)


# The backdrop drifts: a slow sway (a little across and up, a breath larger and smaller, a hair of a turn), each
# part of it on its own long period, so it never visibly repeats. A picture on the stage drifts too, slower and
# smaller (a camera easing over a photograph), about its own centre from where it stood when it came on, and its
# labels, boxes and camera views with it. The drift is applied where things are drawn (Lecture._drift_view), never
# to their points, so whatever else moves them (a fade, a label's line, the camera moving in) works as if nothing
# drifted. The phone's players move them by the same formula from the program's `drift` lines (export_dsl), so
# the motion costs the program nothing.
DRIFT = {"period": 26.0, "amp": 0.3, "scale": 0.025, "turn": 0.012}
PICTURE_DRIFT = {"period": 17.0, "amp": 0.14, "scale": 0.035, "turn": 0.0}


def drift_at(t: float, period: float, amp: float, scale: float, turn: float) -> tuple[float, float, float, float]:
    """(dx, dy, scale, turn) of a drift t seconds in."""
    w = 2 * math.pi * t / period
    return (amp * math.sin(w), 0.6 * amp * math.sin(w / 1.3 + 1.1), 1 + scale * math.sin(w / 1.7 + 0.4),
            turn * math.sin(w / 2.1 + 2.0))


def drift_matrix(spec: dict, t: float) -> np.ndarray:
    """A drift's 2x3 transform at t seconds: about (cx, cy) (the origin for a backdrop), and with t0 relative to
    where it stood then (a picture starts still). dsl/interpret.drift_matrix and the phone's Drift.at are the same."""
    cx, cy = float(spec.get("cx", 0.0)), float(spec.get("cy", 0.0))

    def raw(time: float) -> np.ndarray:
        dx, dy, k, turn = drift_at(time, *(float(spec.get(n, DRIFT[n])) for n in ("period", "amp", "scale", "turn")))
        c, s = k * math.cos(turn), k * math.sin(turn)
        return np.array([[c, -s, cx + dx - (c * cx - s * cy)], [s, c, cy + dy - (s * cx + c * cy)], [0, 0, 1.0]])

    m = raw(t)
    if spec.get("t0") is not None:
        m = m @ np.linalg.inv(raw(float(spec["t0"])))
    return m[:2]


def drifts_on() -> bool:
    return os.environ.get("PANIM_BACKDROP_DRIFT", "1") != "0"


def set_drift(mobs, spec: dict | None) -> None:
    """Give every part of these the drift `spec` (shared: they move as one), or none."""
    for mob in mobs:
        if mob is None:
            continue
        for part in mob.get_family():
            if spec is None:
                part.__dict__.pop("_panim_drift", None)
            else:
                part._panim_drift = spec


def follow_drift(mobs, f: float, centre, shift) -> None:
    """These were scaled by f about `centre` and moved by `shift`: the drifts they carry turn about the same point
    of the picture as before (a stale centre swung a moved picture and its labels apart)."""
    seen = set()
    for mob in mobs:
        for part in (mob.get_family() if mob is not None else []):
            spec = part.__dict__.get("_panim_drift")
            if spec is None or id(spec) in seen or "cx" not in spec:
                continue
            seen.add(id(spec))
            spec["cx"] = float(centre[0] + f * (float(spec["cx"]) - centre[0]) + shift[0])
            spec["cy"] = float(centre[1] + f * (float(spec.get("cy", 0.0)) - centre[1]) + shift[1])


def _still(_mob, dt: float) -> None:
    """An updater that does nothing: something drifting is drawn afresh every frame (Manim caches what has none)."""


def backdrop() -> tuple[VGroup, VGroup]:
    """The style's texture as (what drifts, what stays still): soft discs, paper fibres, a grid, dots, stars or
    chalk dust that move slowly (drifting: they reach past the frame's edge, so its edge never shows), and a page's
    ruled border or a board's frame, which stay where they are."""
    w, h = config.frame_width + 2.0, config.frame_height + 2.0       # past the frame, by the drift's reach and more
    rng = np.random.default_rng(7)
    parts, still = VGroup(), VGroup()
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
        for _ in range(90):
            x, y = rng.uniform(-w / 2, w / 2), rng.uniform(-h / 2, h / 2)
            length = rng.uniform(0.3, 1.4)
            parts.add(Line([x, y, 0], [x + length, y + rng.uniform(-0.02, 0.02), 0],
                           stroke_color="#7A5530", stroke_width=rng.uniform(0.6, 1.4), stroke_opacity=0.22))
    elif texture == "board":
        still.add(Rectangle(width=config.frame_width - 0.12, height=config.frame_height - 0.12,
                            stroke_color="#C9C9C0", stroke_width=6, fill_opacity=0))
        for _ in range(6):
            parts.add(Circle(radius=rng.uniform(0.8, 2.2), stroke_width=0, fill_color="#E6E6DE", fill_opacity=0.35)
                      .stretch(0.4, 1).move_to([rng.uniform(-6, 6), rng.uniform(-3.5, 3.5), 0]))
    elif texture == "grid":
        for x in np.arange(-8.0, 8.01, 0.5):
            major = abs(x / 2.5 - round(x / 2.5)) < 1e-6
            parts.add(Line([x, -h / 2, 0], [x, h / 2, 0], stroke_color="#3F74A8",
                           stroke_width=1.2 if major else 0.6, stroke_opacity=0.55 if major else 0.3))
        for y in np.arange(-5.0, 5.01, 0.5):
            major = abs(y / 2.5 - round(y / 2.5)) < 1e-6
            parts.add(Line([-w / 2, y, 0], [w / 2, y, 0], stroke_color="#3F74A8",
                           stroke_width=1.2 if major else 0.6, stroke_opacity=0.55 if major else 0.3))
    elif texture == "parchment":
        # Age spots, and a ruled double frame like a page from an old atlas (the frame stays still).
        for _ in range(9):
            parts.add(Circle(radius=rng.uniform(0.8, 2.4), stroke_width=0, fill_color="#D9C39A",
                             fill_opacity=rng.uniform(0.05, 0.11)).stretch(rng.uniform(0.5, 0.9), 1)
                      .move_to([rng.uniform(-6.5, 6.5), rng.uniform(-3.6, 3.6), 0]))
        fw, fh = config.frame_width, config.frame_height
        still.add(Rectangle(width=fw - 0.25, height=fh - 0.25, stroke_color="#8C6E45", stroke_width=2.5, fill_opacity=0))
        still.add(Rectangle(width=fw - 0.45, height=fh - 0.45, stroke_color="#8C6E45", stroke_width=0.8, fill_opacity=0))
    elif texture == "dots":
        for x in np.arange(-8.0, 8.01, 0.5):
            for y in np.arange(-5.0, 5.01, 0.5):
                parts.add(Dot([x, y, 0], radius=0.012, color="#B8CCCC", fill_opacity=0.8))
    elif texture == "stars":
        for _ in range(170):
            parts.add(Dot([rng.uniform(-w / 2, w / 2), rng.uniform(-h / 2, h / 2), 0],
                          radius=rng.uniform(0.006, 0.022), color="#FFFFFF", fill_opacity=rng.uniform(0.25, 0.9)))
        for i, r in enumerate((5.5, 4.0)):
            parts.add(Circle(radius=r, stroke_width=0, fill_color="#3B2F7A", fill_opacity=0.08 + 0.04 * i)
                      .move_to(LEFT * 2.5 + UP * 1.2))
    elif texture == "chalk":
        for _ in range(8):
            parts.add(Circle(radius=rng.uniform(0.9, 2.6), stroke_width=0, fill_color="#2A5242", fill_opacity=0.35)
                      .stretch(0.35, 1).move_to([rng.uniform(-6, 6), rng.uniform(-3.5, 3.5), 0]))
    for group in (parts, still):
        group.set_z_index(Z_BACK)
        group.is_backdrop = True        # layout checks skip it: everything sits on it by design
        group._panim_static = True      # no animation changes it: a bake need not look at it
    if drifts_on() and len(parts):
        set_drift([parts], dict(DRIFT))
        parts.add_updater(_still)
        parts._panim_drift_updater = _still
    return parts, still


def _what(mob) -> str:
    """A mobject named for a log: its first words, else its kind."""
    for m in mob.get_family():
        if isinstance(m, Text) and getattr(m, "original_text", ""):
            return repr(m.original_text[:30])
    return type(mob).__name__


def hud_frame(width: float, height: float, color: str | None = None, stroke: float = 3.5, glow: bool = True):
    """The house frame for something looked at (a picture's part, the camera's view, a place on the map): four
    corner brackets over a faint full rim, with a soft glow under the brackets, in the manner of a modern
    interface's focus ring. Centred on the origin; move it where it goes."""
    color = color or role("highlight")
    w, h = max(width, 0.12), max(height, 0.12)
    arm = max(0.08, min(0.38, 0.22 * min(w, h)))
    rim = Rectangle(width=w, height=h, stroke_color=color, stroke_width=1.2, stroke_opacity=0.45, fill_opacity=0)
    corners = []
    for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        corner = np.array([sx * w / 2, sy * h / 2, 0])
        corners.append(VMobject().set_points_as_corners([corner + np.array([0, -sy * arm, 0]), corner,
                                                         corner + np.array([-sx * arm, 0, 0])]))
    brackets = VGroup(*corners).set_stroke(color, width=stroke, opacity=1).set_fill(opacity=0)
    parts = [rim]
    if glow:
        parts.append(brackets.copy().set_stroke(color, width=stroke * 3.2, opacity=0.18))
    parts.append(brackets)
    frame = VGroup(*parts)
    frame.brackets = brackets
    return frame


def _modern_motion(animations, kwargs) -> None:
    """The house motion: things arrive fast and settle (an ease-out: ease_out_cubic, rush_from) and leave by
    gathering speed (rush_into), instead of Manim's even ease both ways. Only where an animation keeps Manim's
    default and the play sets none; all are rates the phone's players have."""
    if kwargs.get("rate_func") is not None:
        return
    from manim import Create, DrawBorderThenFill, GrowFromEdge, SpinInFromNothing

    todo = list(animations)
    while todo:
        anim = todo.pop()
        subs = getattr(anim, "animations", None)
        if subs:
            todo.extend(subs)
            continue
        if getattr(anim, "rate_func", None) is not smooth or getattr(anim, "_panim_bake", False):
            continue
        if isinstance(anim, FadeOut):
            anim.rate_func = rush_into
        elif isinstance(anim, FadeIn):
            anim.rate_func = ease_out_cubic
        elif isinstance(anim, (Create, GrowFromCenter, GrowFromEdge, DrawBorderThenFill, SpinInFromNothing)):
            anim.rate_func = rush_from


def _with_sound(method, kind: str):
    """A picture method whose animation makes this sound effect (sfx.py) when it plays."""
    def wrapped(self, *args, **kwargs):
        anim = method(self, *args, **kwargs)
        if anim is not None:
            try:
                anim.panim_sfx = kind
            except AttributeError:
                pass
        return anim

    wrapped.__name__, wrapped.__doc__ = method.__name__, method.__doc__
    return wrapped


class Lecture(Scene):
    """Beats, captions, a fact panel and chapter cards, in the current style."""

    SECTIONS: list[str] = []
    SECTION = 0
    board_mode = False      # teaching on the whole frame (stem.BoardMixin.board)
    # Where panel text starts. A map lecture keeps the left for the map and
    # the panel to its right; without a map the column sits near the centre.
    TEXT_LEFT = -3.0
    PANEL_BOX = (-3.55, 5.9)   # the panel's left and right edges

    def setup(self):
        self.cap = None
        self.panel_items = Group()
        self.panel_images = Group()     # figures: images cannot join a VGroup
        self.stage_items = Group()      # the picture on the stage: a photo, a figure or an illustration
        self.stage_extra: list = []     # parts added to it later (a diagram's revealed nodes, a focus ring)
        self.diagrams: dict = {}        # diagram id -> its nodes, edges and what is shown
        self._question = None           # the question on the stage: its timer track and its answer, placed
        self.stage_body = None          # what the stage shows (without its backing card)
        self.stage_pending: list = []   # parts of it not shown yet (a diagram's later nodes): they move with it
        self._next_pending: list = []   # those of a picture being built, before it goes up
        self.works: dict = {}           # worked solutions on the stage: where their next line goes
        self._problem = None            # the problem on the board: where its solution is written
        self._full_figure = None        # the full-frame figure on screen, faded at the next beat
        self._new_figure = None         # one built for this beat (its call runs before beat() does)
        self._beat_new: list = []       # stage pictures built for the coming beat, not shown yet
        self._beat_revealed: list = []  # diagram parts the coming beat reveals
        self._beat_asides: list = []    # cards put beside the drawing for the coming beat
        self._beat_added: list = []     # parts added to the stage for the coming beat
        self._stage_keys: set = set()   # diagrams on the stage now: revealing a part of another one is skipped
        self._next_keys: set = set()    # diagrams built for the picture about to go up
        self.panel_y = 2.35
        self.chrome = VGroup()
        self._drift_view()
        for back in backdrop():
            if len(back):
                self.add(back)
        self.section(self.SECTION)

    def _drift_view(self) -> None:
        """Draw what drifts (a backdrop, a picture and its labels) where its drift has it now (drift_matrix, from the
        render clock), its points put back after each frame: nothing that reads or animates them sees the drift."""
        camera = getattr(getattr(self, "renderer", None), "camera", None)
        if camera is None or getattr(camera, "_panim_drifting", False):
            return
        draw = camera.capture_mobjects

        def capture(mobjects, **kwargs):
            now = float(getattr(self.renderer, "time", 0.0) or 0.0)
            moved, made, seen = [], {}, set()
            try:
                for top in mobjects:
                    for part in top.get_family():
                        spec = part.__dict__.get("_panim_drift")
                        if not spec or not len(part.points) or id(part) in seen:
                            continue
                        seen.add(id(part))
                        if "t0" not in spec and "cx" in spec:
                            spec["t0"] = now          # a picture starts still, from the frame it is first drawn on
                        key = id(spec)
                        if key not in made:
                            made[key] = drift_matrix(spec, now)
                        m = made[key]
                        moved.append((part, part.points))
                        part.points = part.points @ np.array([[m[0, 0], m[1, 0], 0], [m[0, 1], m[1, 1], 0],
                                                              [0, 0, 1]]) + np.array([m[0, 2], m[1, 2], 0])
                return draw(mobjects, **kwargs)
            finally:
                for part, points in reversed(moved):
                    part.points = points

        camera.capture_mobjects = capture
        camera._panim_drifting = True

    # ---------------- beat log ----------------
    def safe(self, build, what: str = "", said: str | None = None):
        """One picture's call, run so that one which fails is left out with its reason, not the whole lecture.

        A diagram the model described in a way the engine cannot draw (a point list of the wrong shape, an
        expression with nothing to plot) stopped an hour-long render with a bare numpy error and no beat named.
        The narration goes on; the reason, and the beat, are kept in SKIPPED for the build to report.

        `said`: the words the picture shows (a place, a part's name): it starts as they are said (beat); a list:
        words any of which the line may say, the picture starting with the first said."""
        try:
            made = build()
            if said and made is not None:
                try:
                    if isinstance(said, (list, tuple)):
                        # Its words, any of which may be said: it comes on with the first said (_on_words).
                        made.panim_alts = [str(w) for w in said if str(w).strip()]
                        made.panim_said = made.panim_alts[0] if made.panim_alts else None
                    else:
                        made.panim_said = str(said)
                except AttributeError:
                    pass
            return made
        except VoiceUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 -- the model's picture: its error is the message
            import traceback

            frames = traceback.extract_tb(error.__traceback__)
            where = f" (at {Path(frames[-1].filename).name}:{frames[-1].lineno})" if frames else ""
            # An error deep in Manim names its own file; the line of the model's block that called it is the one
            # to mend (a free block runs as "<id>").
            own = [f for f in frames if f.filename.startswith("<") and f.filename != "<string>"]
            if own and own[-1] is not frames[-1]:
                where = f"{where[:-1]}, called from {own[-1].filename}:{own[-1].lineno})"
            message = f"{what}: {type(error).__name__}: {str(error)[:200]}{where}"
            skipped(message)
            print("picture skipped:", message, file=sys.stderr)
            self._log("skipped", what=what, error=message)
            return None

    def name_part(self, phrase, mob, shown=None, act=None, auto: bool = True) -> None:
        """Something on the screen with a name the narration may say again (a timeline's date, a map's place, a
        card's heading): pointed at on its words (beat). `shown()`, when given, says whether it is drawn now; `act()`,
        when given, is what pointing at it does (a picture's part lit, the rest shaded), else it pulses. `auto`: the
        engine may point at it by itself when a line names it (never in a strict chapter); False: only `point` does."""
        if mob is None or not str(phrase or "").strip():
            return
        parts = self.__dict__.setdefault("_named_parts", [])
        parts.append({"say": str(phrase), "mob": mob, "beat": self.__dict__.get("_sync_beat", 0), "shown": shown,
                      "act": act, "auto": auto})

    def _pointers(self, words, seconds: float, hinted: set) -> list:
        """[(the pointing animation, [start, seconds])] for the things on the screen this line names: each once,
        on its words, at most POINT_MOST; not one a picture of this line already shows on those words. None in a
        strict chapter: there the script points (point, shade, focus)."""
        if self.__dict__.get("_strict"):
            return []
        now = self.__dict__.get("_sync_beat", 0)
        on_screen = {id(m) for top in self.mobjects for m in top.get_family()}
        # What stays up through this line: a thing this line's pictures take away (the timeline a comparison
        # replaces) is on the screen until they play, and a pulse on it put it back, over the new picture.
        held = self._held()
        candidates = list(self.__dict__.get("_named_parts", []))
        for key, d in getattr(self, "diagrams", {}).items():
            labels = self.__dict__.get("_diagram_labels", {}).get(key) or {}
            for node, mob in (d.get("nodes") or {}).items():
                if node in labels:
                    candidates.append({"say": labels[node], "mob": mob, "beat": d.get("_beat", -1),
                                       "shown": lambda d=d, node=node: node in d["shown"] and not d.get("gone")})
        out, used = [], set()
        for part in candidates:
            mob = part["mob"]
            if id(mob) in used or _norm(part["say"]) in hinted or not part.get("auto", True):
                continue
            if part["shown"] is not None and not part["shown"]():
                continue
            fresh = part["beat"] == now
            # On the screen whole or by its parts (an entrance of a card's parts one after another puts the parts
            # up, not the card's own group).
            if not fresh and id(mob) not in on_screen and \
                    not any(id(x) in on_screen for x in mob.family_members_with_points()):
                continue
            if not any(id(x) in held for x in mob.family_members_with_points()):
                continue
            at = self._said(words, part["say"])
            # A thing put up by this line is pointed at only once it has had time to arrive.
            if at is None or at > seconds - 0.4 or (fresh and at < 1.0):
                continue
            used.add(id(mob))
            out.append((at, mob, part.get("act")))
        out.sort(key=lambda r: r[0])
        made, last = [], -9.0
        # Built in the order they are said: a camera move starts from where the one before it left the camera.
        for at, mob, act in out[:POINT_MOST]:
            anim = act() if act is not None else None
            if anim is not None:
                last = at
                anim.panim_camera = True
                made.append((anim, [max(0.0, at - SYNC_LEAD), getattr(anim, "panim_run", None) or self.LOOK_RUN]))
            else:
                made.append((ScaleInPlace(mob, 1.12, rate_func=there_and_back), [max(0.0, at - 0.1), 0.7]))
        return made

    def point(self, target: str):
        """The script's own pointing (`point`): what is on the screen by that name (a diagram's node, a picture's
        part, a card, a place, a gallery's picture) pulses once. None, and a note, when nothing up has that name."""
        want = _norm(target)
        found = None
        for part in reversed(self.__dict__.get("_named_parts", [])):
            if _norm(part["say"]) == want and (part["shown"] is None or part["shown"]()):
                found = part["mob"]
                break
        if found is None:
            for key, d in getattr(self, "diagrams", {}).items():
                labels = self.__dict__.get("_diagram_labels", {}).get(key) or {}
                for node, mob in (d.get("nodes") or {}).items():
                    if node in d["shown"] and not d.get("gone") and want in (_norm(node), _norm(labels.get(node, ""))):
                        found = mob
        on_screen = {id(m) for top in self.mobjects for m in top.get_family()}
        if found is None or not any(id(x) in on_screen for x in (found.family_members_with_points() or [found])):
            skipped(f"point: nothing on the screen called {target!r}")
            return None
        pulse = ScaleInPlace(found, 1.12, rate_func=there_and_back)
        pulse.panim_run = 0.7
        return pulse

    def _view_of(self, part: str):
        """(the labelled picture up with a part of that name, its name as laid out), else (None, None)."""
        want = _norm(part)
        for view in reversed(self.__dict__.get("_views", [])):
            name = next((n for n in view["parts"] if _norm(n) == want), None)
            if name is not None and self._view_on(view):
                return view, name
        return None, None

    def shade_part(self, part: str, hold: bool = False):
        """The script's own light on a labelled picture's part (`shade`): the rest of the picture shaded round it
        (its label brought on first if it is not on yet), until the next line, or a shade on another part; with
        `hold`, until an `unshade` (over the lines between)."""
        view, name = self._view_of(part)
        if view is None:
            skipped(f"shade: no labelled picture up with a part {part!r}")
            return None
        look = self._look(view, name)
        if look is not None:
            look.panim_run = self.LOOK_RUN
            view["held_light"] = bool(hold)
        return look

    def unshade(self):
        """The light lifted from the labelled picture up (`unshade`): the whole picture clear again."""
        for view in self.__dict__.get("_views", []):
            if view.get("lens") is not None:
                view["held_light"] = False
                back = self._look_out(view)
                if back is not None:
                    return back
        return None

    def label(self, part: str):
        """A labelled picture's label the script held back, brought on now (`label`): its box, line and name."""
        view, name = self._view_of(part)
        if view is None:
            skipped(f"label: no labelled picture up with a part {part!r}")
            return None
        if name in view["revealed"]:
            return None
        anim = self._label_reveal(view, name)
        anim.panim_run = 0.8
        return anim

    def unlabel(self, part: str):
        """A label taken off the picture (`unlabel`): its box, line and name fade; the picture stays."""
        view, name = self._view_of(part)
        if view is None or name not in view["revealed"]:
            return None
        piece = view["parts"][name]
        going = [m for m in [*self._pointer_pieces(piece), piece["tag"]] if m is not None]
        view["revealed"].discard(name)
        self.stage_extra = [x for x in self.stage_extra if all(x is not m for m in going)]
        self.stage_pending.extend(going)
        anim = AnimationGroup(*[FadeOut(m) for m in going])
        anim.panim_run = 0.5
        return anim

    def unfocus(self, key: str):
        """A diagram's focus lifted (`unfocus`): the veils over its other parts gone, the whole diagram clear."""
        d = getattr(self, "diagrams", {}).get(key)
        going = self._unveil(d) if d else []
        if not going:
            return None
        anim = AnimationGroup(*going)
        anim.panim_run = 0.5
        return anim

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
        self._section_at = index
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
        # Big enough to read at a glance on a phone: where in the lecture this is.
        tag = fit(T(f"{index:02d}  ·  {name.upper()}", 23, P.MUTED, weight=BOLD), config.frame_width * 0.62)
        tag.to_corner(UL, buff=0.26).shift(DOWN * 0.04)
        # On a card the colour of the page, so a map drawn under it never runs through its words.
        card = RoundedRectangle(corner_radius=0.08, width=tag.width + 0.3, height=tag.height + 0.18, fill_color=P.BG,
                                fill_opacity=0.92, stroke_width=0).move_to(tag)
        for part in card.get_family():
            part._art_decorated = True
        self.chrome = Group(track, done, card, tag)       # a Group: the emblem may be a picture, not shapes
        mark = self.emblem(0.42)
        if mark is not None:
            # The lecture's emblem beside the chapter's name: one motif through the whole series.
            mark.next_to(card, RIGHT, buff=0.12)
            self.chrome.add(mark)
        self.chrome.set_z_index(Z_CHROME)
        self.add(self.chrome)

    # ---------------- narration beat ----------------
    def play(self, *animations, **kwargs):
        """Manim's play, without the empty groups it refuses (see _playable); nothing to play is no play."""
        animations = [a for a in (_playable(a) for a in animations) if a is not None]
        if self.WORD_CAPTION and animations:
            animations = self._kara_moves(animations, kwargs)
        if animations and getattr(self, "_free_ink", None):
            import stem

            stem.ink_animations(animations, P.CREAM)     # a free block's white, on a light board
        if animations:
            _modern_motion(animations, kwargs)
            self._sound_for(animations, kwargs)
            super().play(*animations, **kwargs)

    SFX_GAP = 0.18           # seconds between two sound effects, at least: a run of quick plays is not a rattle

    def _sound_for(self, animations, kwargs) -> None:
        """The play's sound effect (sfx.py: a pop, a tick, a whoosh, the camera's zoom...), started with it."""
        import sfx

        if not sfx.enabled() or getattr(self, "_free_ink", None):
            return
        animations = [a for a in animations if not getattr(a, "_m_karaoke", False)]
        if not animations:
            return                                          # the caption's underline moving: no sound
        if voice_mode() == "silent" and os.environ.get("PANIM_SFX") != "1":
            return                                          # a silent build (a preview, a test) stays silent
        kind, _ = sfx.classify(animations)
        if kind is None:
            return
        now = float(getattr(getattr(self, "renderer", None), "time", 0.0) or 0.0)
        if now - self.__dict__.get("_last_sfx", -9.0) < self.SFX_GAP and kind not in ("chapter", "intro", "answer"):
            return
        wav = sfx.path(kind)
        if wav:
            self._last_sfx = now
            self.add_sound(wav, gain=sfx.gain(kind))

    # ---------------- the word being said, and the music under the voice ----------------
    # Copied from the motion engine (motion.py: its caption, _karaoke_plan, _karaoke, _m_music), for this engine's
    # lectures: the caption underlines each word as it is said (laid out a line at a time, where each word sits
    # measured, so any script works, Hindi's joined letters too), the underline moving as fades in the holds, which
    # the exporter writes as verbs (the phone and the web player show it); and a quiet music bed under each line
    # (music.py), ducked under its words. Only with a voice. PANIM_KARAOKE=0 / PANIM_MUSIC=off turn them off. The
    # motion engine has its own of both (WORD_CAPTION and MUSIC_BED off there).
    WORD_CAPTION = True
    MUSIC_BED = True
    MUSIC_MOOD = "calm"
    KARAOKE_SWAP = 0.05      # seconds an underline takes to move to the next word

    def beat(self, text: str, *anims, rt: float | None = None, pad: float | None = None,
             cues: list | None = None) -> float:
        """A line (_beat), its caption underlining each word as it is said, the music bed under it."""
        self._kara = self._kara_plan(text) if self.WORD_CAPTION else None
        self._bed_line = {"text": text, "pad": beat_pad(text) if pad is None else float(pad)} if self.MUSIC_BED \
            else None
        try:
            return self._beat(text, *anims, rt=rt, pad=pad, cues=cues)
        finally:
            k, self._kara, self._kara_ready, self._bed_line = self.__dict__.get("_kara"), None, {}, None
            if k and k.get("cur") is not None and any(k["cur"] is m for m in self.mobjects):
                self.remove(k["cur"])

    @staticmethod
    def _kara_on() -> bool:
        return os.environ.get("PANIM_KARAOKE", "1") != "0"

    def _kara_width(self, word: str, size: float) -> float:
        cache = self.__dict__.setdefault("_kara_widths", {})
        key = (word, size)
        if key not in cache:
            try:
                if _complex(word):
                    raise ValueError("joined script")
                cache[key] = T(word, size, disable_ligatures=True).width
            except ValueError:
                cache[key] = T(word, size).width
        return cache[key]

    def _word_caption(self, text: str) -> VGroup:
        """The caption a line of words at a time, with where each word sits (`_kara_words`: (left, right, bottom))."""
        lines = textwrap.wrap(text, 92)
        if len(lines) > 2:
            lines = textwrap.wrap(text, int(len(text) / 2) + 8)
        size = tok("caption_size", 19)
        terms = os.environ.get("PANIM_CAPTION_TERMS", "1") != "0"
        colour = readable(getattr(P, "role_highlight", P.GOLD), TH["cap_bg"], 4.5)
        if contrast(colour, TH["cap_fg"]) < 1.6:
            colour = readable(P.GOLD, TH["cap_bg"], 4.5)
        rows = []
        for line in lines:
            try:
                if _complex(line):
                    raise ValueError("joined script")
                t = T(line, size, TH["cap_fg"], disable_ligatures=True)
            except ValueError:
                t = T(line, size, TH["cap_fg"])
            spans = self._caption_spans(line) if terms else []
            if spans and self._colour_spans(t, line, spans, colour):
                t._panim_terms = [line[a:b] for a, b in spans]
            if len(t.submobjects) == len(line):
                t.remove(*[g for g, c in zip(list(t.submobjects), line) if c.isspace()])
            rows.append((line, t))
        block = VGroup(*[t for _, t in rows]).arrange(DOWN, buff=0.1)
        fit(block, 13.2)
        box = RoundedRectangle(corner_radius=0.03 if TH["upper"] else 0.12, width=block.width + 0.5,
                               height=block.height + 0.3, fill_color=TH["cap_bg"], fill_opacity=TH["cap_op"],
                               stroke_width=1.2 if STYLE == "blueprint" else 0, stroke_color=P.MUTED)
        box.move_to([0, CAPTION_Y, 0])
        block.move_to(box)
        group = VGroup(box, block)
        if STYLE == "cardboard":
            shadow = box.copy().set_fill("#000000", 0.28).shift(RIGHT * 0.05 + DOWN * 0.05)
            group = VGroup(shadow, box, block).rotate(-0.006)
        group.set_z_index(Z_CAPTION)
        spots = []
        space = max(1e-3, self._kara_width("a a", size) - 2 * self._kara_width("a", size))
        for line, t in rows:
            words = line.split()
            widths = [self._kara_width(w, size) for w in words]
            natural = sum(widths) + space * max(0, len(words) - 1)
            k = t.width / natural if natural > 0 else 1.0
            x, bottom = t.get_left()[0], t.get_bottom()[1]
            for width in widths:
                spots.append((x, x + width * k, bottom))
                x += (width + space) * k
        group._kara_words = spots
        return group

    def _kara_plan(self, text: str) -> dict | None:
        """The underlines of a line and when each comes on: its caption's pieces made now (caption() hands them
        out as the line puts them up), each word's underline at its time, never before its piece is up."""
        if not self._kara_on() or voice_mode() == "silent":
            return None
        try:
            words = line_words(text)
            _, seconds = narrate(text)
        except Exception:  # noqa: BLE001 -- no word times: the caption as ever
            return None
        if not words:
            return None
        pieces = caption_pieces(text)
        swaps = self._caption_swaps(text, pieces, seconds, words)
        starts = [0.0] + [at for at, _ in swaps]
        tokens = " ".join(str(text).split()).split()
        n, m = len(tokens), len(words)
        colour = readable(getattr(P, "role_highlight", P.GOLD), TH["cap_bg"], 3.0)
        ready, events, i, last = {}, [], 0, 0.0
        for p, piece in enumerate(pieces):
            cap = self._word_caption(piece)
            ready[piece] = cap
            begin = starts[p] if p < len(starts) else starts[-1]
            if p:
                events.append((begin, None))
            for left, right, bottom in cap._kara_words:
                k = i if n == m else round(i * (m - 1) / max(1, n - 1))
                at = max(float(words[min(k, m - 1)].get("start") or 0.0), begin, last)
                bar = Rectangle(width=max(0.06, right - left), height=0.055, stroke_width=0, fill_color=colour,
                                fill_opacity=1).move_to([(left + right) / 2, bottom - 0.05, 0])
                bar.set_z_index(Z_CAPTION + 1)
                events.append((at, bar))
                last, i = at, i + 1
        events.append((max(last, float(words[-1].get("end") or last)) + 0.1, None))
        self._kara_ready = ready
        return {"t0": None, "events": events, "cur": None}

    def _kara_moves(self, animations, kwargs):
        """A hold with the underline's moves that fall in it, as fades (an empty fade for each stretch between), so
        the exporter writes them as one `lag` of verbs. Only in a hold: beside a play's own animations the players
        hid a picture that play moved; a word said during a play is underlined as the play ends."""
        k = self.__dict__.get("_kara")
        if not k or k.get("t0") is None or not k["events"] or kwargs.get("rate_func") is not None:
            return animations
        if not all(type(a).__name__ == "Wait" for a in animations):
            return animations
        run = float(kwargs["run_time"]) if kwargs.get("run_time") is not None else \
            max((float(getattr(a, "run_time", 0.0) or 0.0) for a in animations), default=0.0)
        if run <= self.KARAOKE_SWAP * 2:
            return animations
        now = float(self.renderer.time) - k["t0"]
        end, cursor, steps = now + run, now, []
        swap = self.KARAOKE_SWAP
        while k["events"] and k["events"][0][0] <= end - swap - 1e-3:
            at, bar = k["events"].pop(0)
            at = max(at, cursor)
            if at - cursor > 1e-3:
                steps.append(FadeOut(VMobject(), run_time=at - cursor))
            moves = [x for x in (FadeOut(k["cur"], run_time=swap) if k["cur"] is not None else None,
                                 FadeIn(bar, run_time=swap) if bar is not None else None) if x is not None]
            if moves:
                steps.append(AnimationGroup(*moves, run_time=swap) if len(moves) > 1 else moves[0])
            cursor = at + swap
            k["cur"] = bar
        if not steps:
            return animations
        if end - cursor > 1e-3:
            steps.append(FadeOut(VMobject(), run_time=end - cursor))
        moves = LaggedStart(*steps, lag_ratio=1.0, rate_func=linear)
        moves._m_karaoke = True                 # the caption's own (no sound effect; a hold stays a hold)
        return [moves]

    def _bed(self, begun: float, seconds: float) -> None:
        """The music bed under the line now spoken, from where its voice begins to the end of its pause."""
        line = self.__dict__.get("_bed_line")
        if not line:
            return
        import music

        if not music.enabled() or voice_mode() == "silent":
            return
        try:
            words = line_words(line["text"]) or []
        except Exception:  # noqa: BLE001 -- no word times: ducked under the whole line
            words = []
        if not words:
            words = [{"start": 0.0, "end": seconds}]
        root = Path(os.environ.get("PANIM_AUDIO_DIR") or Path(__file__).resolve().parent / ".cache") / "music"
        self._bed_gap(begun)
        length = seconds + float(line.get("pad") or 0.0)
        path = music.piece(self.MUSIC_MOOD, begun, length, words, root)
        if path:
            self.add_sound(path, gain=0)
            self._bed_end = max(float(self.__dict__.get("_bed_end", 0.0)), begun + length)

    def _bed_mood(self) -> str:
        return self.MUSIC_MOOD

    def _bed_gap(self, until: float) -> None:
        """The bed through what plays between two lines' pieces (a map coming in, a picture changing, a chapter's
        card, the credits): from where the last piece ended to `until`, at its level between words, so the music
        never stops for an animation. From the lecture's start before the first line."""
        import music

        if not music.enabled() or voice_mode() == "silent":
            return
        start = float(self.__dict__.get("_bed_end", 0.0))
        if until - start <= 0.05:
            return
        root = Path(os.environ.get("PANIM_AUDIO_DIR") or Path(__file__).resolve().parent / ".cache") / "music"
        path = music.piece(self._bed_mood(), start, until - start, [], root)
        if path:
            now = float(getattr(getattr(self, "renderer", None), "time", 0.0) or 0.0)
            self.add_sound(path, time_offset=start - now, gain=0)
        self._bed_end = until

    def tear_down(self):
        """The bed on to the end of the video (its last line's hold, the outro, the credits), when it played at all."""
        if "_bed_end" in self.__dict__:
            self._bed_gap(float(getattr(getattr(self, "renderer", None), "time", 0.0) or 0.0))
        super().tear_down()

    def _beat(self, text: str, *anims, rt: float | None = None, pad: float | None = None,
              cues: list | None = None) -> float:
        """One narration line and the animations that go with it.

        The line is spoken first and measured; the animations take 55% of it
        (1.2 to 3.2 s) so motion lands while the sentence is still going, and
        the rest of the line plus a pause (`pad`, BEAT_PAD by default) is a hold.

        `cues`, filled in after the voice is made (align_cues.py): one [start, seconds] a animation, in the order
        given, timing each to the words it goes with; the animations then play one after another at those times
        instead of all together as the line begins.
        """
        pad = beat_pad(text) if pad is None else pad
        # Live pictures (stem.py: sims, traces, sweeps, continuous motions) stop at the next line unless kept.
        getattr(self, "_live_next", lambda: None)()
        if self._full_figure is not None:
            self.play(FadeOut(self._full_figure), run_time=0.4)
            self._full_figure = None
        self._full_figure, self._new_figure = self._new_figure, None
        wav, seconds = narrate(text)
        self._log("beat", text=text, seconds=round(seconds, 3), wav=wav)
        _progress_beat()
        self._coming = anims
        # When each word is said (the voice's times, or aligned here): the pictures go on their words.
        try:
            words = line_words(text) if voice_mode() != "silent" else None
        except Exception:  # noqa: BLE001 -- no word times: the pictures play as the line begins
            words = None
        # A line too long for two caption lines is captioned a piece at a time, each as its words are said.
        pieces = caption_pieces(text)
        cap = self.caption(pieces[0])
        swaps = self._caption_swaps(text, pieces, seconds, words)
        self._coming = ()
        self._speak(wav, seconds)
        if self.cap is not None:
            self.remove(self.cap)
        self.add(cap)
        self.cap = cap
        spent = 0.0
        given = [(_playable(a), (cues[i] if cues and i < len(cues) else None)) for i, a in enumerate(anims)]
        given = [(a, c) for a, c in given if a is not None]
        self._line_draws = bool(given)
        given = self._queued(given, words, seconds)
        given = self._on_words(given, words, seconds, text)
        anims = [a for a, _ in given]
        if getattr(self, "_cover", None) is not None or getattr(self, "_cover_hidden", None):
            anims += self._cover_changes(anims)
        if self.__dict__.get("_map_tidy"):
            anims += self._map_tidy_out(anims)
        if anims:
            spent = rt if rt is not None else self._quick(anims, seconds)
        plan = self._cue_plan(given, anims[len(given):], seconds, spent) if any(c for _, c in given) else None
        if plan:
            spent = max(start + run for start, run, _ in plan)
        # A live process (a titration, cell division) runs from when its picture is in to the end of the line.
        self._beat_span = max(0.6, seconds + pad - spent)
        if plan:
            spent = self._play_cued(plan, swaps)
        elif anims:
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
        self._beat_new = []
        self._beat_revealed = []
        self._beat_asides = []
        self._beat_added = []
        self._moving = []
        self._check_beat(text)
        spent = self._swap_due(spent, swaps)
        back = self._map_return()
        if back:
            # The map moves back out as the line ends, not over its words.
            spent = self._wait_until(spent, max(spent, seconds - 0.4), swaps)
            self.play(*back, run_time=0.8)
            spent = self._swap_due(spent + 0.8, swaps)
        spent = self._wait_until(spent, seconds + pad, swaps)
        self._voice_done(pad)
        self._sync_beat = self.__dict__.get("_sync_beat", 0) + 1
        self._spoken_as = {}                   # a line's anchors are its own (spoken_as)
        return seconds

    @staticmethod
    def _quick(anims, seconds: float) -> float:
        """How long a line's animations take: one that knows its own time (panim_run, a gallery's step) that, anything else
        (a card coming on, a diagram drawing itself, a map moving) a fifth of the line, 0.6 to 1.2 seconds: a thing
        shown, hidden or swapped is quick, done well before the next."""
        runs = [getattr(a, "panim_run", None) for a in anims]
        if runs and all(r is not None for r in runs):
            return min(max(float(r) for r in runs), PrimitiveRun.MOST)
        return min(max(PrimitiveRun.SHOW, seconds * 0.2), 1.2)

    # ---------------- one voice at a time ----------------
    # A line's own count of the time it took (its cue plan) can run ahead of the render's clock: a play that turned
    # out empty, a hold cut short. The next line's voice then started under this one's. So each line's voice is
    # placed by the render's clock, and nothing ends a line, or starts the next voice, before it has been said.

    # ---------------- nothing left behind ----------------
    # Each layout keeps track of what it put up (the stage its picture and parts, the panel its points, the board's
    # strip its title, the map its places), and takes it away again. Whatever is on the screen that none of them
    # holds is a stray -- a part some picture left behind -- and no later picture would ever take it away, so it
    # would sit under everything after it. Strays are cleared as each line begins and whenever the stage changes.

    def _held(self) -> set:
        """Everything on the screen some layout holds: the backdrop, the chapter's heading, the caption, the panel,
        the board's strip, the map while it is up, and the stage's picture and its parts."""
        keep = [getattr(self, "chrome", None), getattr(self, "cap", None), getattr(self, "panel", None),
                getattr(self, "panel_items", None), getattr(self, "panel_images", None),
                getattr(self, "stage_items", None), *getattr(self, "stage_extra", []),
                *getattr(self, "stage_pending", []), getattr(self, "_cover", None), getattr(self, "_inset", None),
                getattr(self, "_map_mask", None), *(getattr(self, "strip", None) or {}).values(),
                *(getattr(self, "_map_spot", None) or [])]
        held = {id(x) for m in keep if m is not None for x in m.get_family()}
        on_map = bool(getattr(self, "_map_on", False))
        for top in self.mobjects:
            if getattr(top, "is_backdrop", False) or getattr(top, "is_map_cover", False) or \
                    (on_map and float(getattr(top, "z_index", 0) or 0) <= Z_MARK + 5):
                held.update(id(x) for x in top.get_family())
        return held

    def strays(self) -> list:
        """What is on the screen that no layout holds."""
        held = self._held()
        out = []
        for top in self.mobjects:
            drawn = [x for x in top.get_family() if len(getattr(x, "points", [])) or isinstance(x, ImageMobject)]
            if drawn and not any(id(x) in held for x in drawn):
                out.append(top)
        return out

    def _clear_strays(self, going=()) -> list:
        """Fade-outs for the strays on the screen, counted in the chapter's report (SYNC "cleared"); not for those
        the line's own animations (`going`) already take away."""
        leaving = set()
        todo = list(going)
        while todo:
            anim = todo.pop()
            todo.extend(getattr(anim, "animations", None) or [])
            if getattr(anim, "remover", False) and getattr(anim, "mobject", None) is not None:
                leaving.update(id(x) for x in anim.mobject.get_family())
        # A thing the line takes away by its parts (a picture slid aside sits on the screen in the group its move
        # made) is not a stray either: cleared early, it went as the line began and its shade came back for the fade.
        found = [m for m in self.strays() if id(m) not in leaving and not any(id(x) in leaving for x in m.get_family())]
        if found:
            counts = SYNC.setdefault(self.__dict__.get("_chapter_no", 0), {"beats": 0, "on_words": 0, "pointed": 0})
            counts["cleared"] = counts.get("cleared", 0) + len(found)
            self._log("strays", count=len(found), what=[_what(m) for m in found][:8])
        return [FadeOut(m) for m in found]

    def _speak(self, wav, seconds: float) -> None:
        """Start a line's voice: once the line before has finished on the render's clock, never over it."""
        now = float(getattr(self.renderer, "time", 0.0) or 0.0)
        still = self.__dict__.get("_voice_until", 0.0) - now
        if still > 0.02:
            self._log("voice_wait", seconds=round(still, 3))
            self.wait(still)
            now += still
        self._voice_until = now + float(seconds or 0.0)
        if wav:
            self.add_sound(wav)
            # Where the voice begins on the video's clock: a QA run lines the players' clock up with it by these.
            self._log("voice", wav=str(wav), at=round(now, 3))
            k = self.__dict__.get("_kara")
            if k is not None and k.get("t0") is None:
                k["t0"] = now
            if self.MUSIC_BED:
                self._bed(now, float(seconds or 0.0))

    def _voice_done(self, pad: float = 0.0) -> None:
        """Hold until the line's voice has been said (and its pause), by the render's clock."""
        rest = self.__dict__.get("_voice_until", 0.0) + max(pad, 0.0) - float(getattr(self.renderer, "time", 0.0) or 0.0)
        if rest > 0.02:
            self._log("voice_hold", seconds=round(rest, 3))
            self.wait(rest)

    def _queued(self, given: list, words, seconds: float) -> list:
        """The line's pictures with what their calls queued to come on by themselves (a labelled picture's labels,
        each on its part's words), and the light lifted from a picture whose parts this line does not name.
        Without word times the labels follow the picture, one after another."""
        queue = self.__dict__.pop("_word_queue", [])
        away = self._clear_strays([a for a, _ in given]) + self._looks_away(words)
        if words:
            return [*[(a, [0.0, PrimitiveRun.HIDE]) for a in away], *given, *[(a, None) for a in queue]]
        out = [*[(a, c) for a, c in given], *[(a, None) for a in away]]
        queue = [a for a in (self._from_queue(holder, False) for holder in queue) if a is not None]
        if queue:
            start = min(1.4, max(0.4, seconds * 0.35))
            step = max(0.3, min(0.8, (seconds - start) / max(len(queue), 1)))
            # Every picture of the line timed, so the labels are after the picture, not over its drawing-in.
            out = [(a, c if isinstance(c, (list, tuple)) and c else [0.0, None]) for a, c in out]
            out += [(a, [round(start + k * step, 3), 0.6]) for k, a in enumerate(queue)]
        return out

    STAGE_WAIT = 1.2         # seconds at most a new stage picture waits for its words (else: as the line begins)

    def _on_words(self, given: list, words, seconds: float, text: str) -> list:
        """The line's pictures with each one that names something started on its words, and pointers added for
        the things on the screen the line names; in the order they start. Unchanged without word times."""
        if not words:
            return given
        counts = SYNC.setdefault(self.__dict__.get("_chapter_no", 0), {"beats": 0, "on_words": 0, "pointed": 0})
        out, hinted, timed = [], set(), 0
        # The word each timed cue is on (by the cue list's id): a look that lands things on their words reads it.
        self._word_cues = {}
        for anim, cue in given:
            alts = getattr(anim, "panim_alts", None)
            if alts:
                # Timed by whichever of its words the line says first.
                heard = [(t_, a) for t_, a in ((self._said(words, a), a) for a in alts) if t_ is not None]
                try:
                    anim.panim_said = min(heard)[1] if heard else None
                except AttributeError:
                    pass
            said = getattr(anim, "panim_said", None)
            at = self._said(words, said) if said else None
            if at is not None and getattr(anim, "panim_stage", False) and not self.__dict__.get("_strict") \
                    and at > min(self.STAGE_WAIT, seconds * 0.25):
                # A new picture on the stage does not wait long for its words (a diagram whose only word said
                # was the line's last left the screen empty the whole line): it comes on as the line begins,
                # and its parts still on their own words.
                at = None
            if at is not None and at < seconds:          # (kept inside the line by _cue_plan)
                run = float(cue[1]) if isinstance(cue, (list, tuple)) and len(cue) > 1 and cue[1] else PrimitiveRun.SHOW
                cue = [round(max(0.0, at - SYNC_LEAD), 3), min(run, 1.0)]
                self._word_cues[id(cue)] = at
                if isinstance(anim, SimpleNamespace):
                    anim.panim_heard = True
                hinted.add(_norm(said))
                timed += 1
            out.append((anim, cue))
        # A label whose part this line does not say comes on after the picture is in, one after another (in a
        # strict chapter, as the line begins, with its picture).
        late = [i for i, (a, c) in enumerate(out) if isinstance(a, SimpleNamespace) and not c]
        strict = bool(self.__dict__.get("_strict"))
        begin = 0.0 if strict else min(1.4, max(0.4, seconds * 0.35))
        for k, i in enumerate(late):
            out[i] = (out[i][0], [0.0 if strict else round(min(begin + 0.5 * k, max(0.0, seconds - 0.4)), 3), 0.6])
        out = self._with_looks(out, seconds)
        pointers = self._pointers(words, seconds, hinted)
        out += pointers
        out += self._lifts(out, seconds)
        counts["looked"] = counts.get("looked", 0) + sum(1 for a, _ in out if getattr(a, "panim_camera", False))
        if timed or pointers or late:
            start = lambda c: float(c[0]) if isinstance(c, (list, tuple)) and c else 0.0  # noqa: E731
            out.sort(key=lambda g: start(g[1]))
            # Every picture with a time: one with none starts as the line begins.
            out = [(a, c if isinstance(c, (list, tuple)) and c else [0.0, None]) for a, c in out]
            counts["on_words"] += timed
            counts["pointed"] += len(pointers)
            self._log("on_words", text=text, timed=timed, pointed=len(pointers))
        counts["beats"] += 1
        return out

    def _map_return(self) -> list:
        return []

    def _with_looks(self, given: list, seconds: float) -> list:
        """A labelled picture's labels, each built now, in the order they come on: a part the line says has its
        label come on and the light moved to it, on its word; a part it does not say, its label alone, in turn."""
        queued = sorted((float(c[0]) if isinstance(c, (list, tuple)) and c else 0.0, i)
                        for i, (a, c) in enumerate(given) if isinstance(a, SimpleNamespace))
        if not queued:
            return given
        heard = [(at, i) for at, i in queued if given[i][0].panim_heard and getattr(given[i][0], "panim_look", None)]
        out = list(given)
        for at, i in queued:
            holder, cue = given[i]
            if getattr(holder, "panim_build", None) is not None:
                # Anything else queued on its words (a gallery's next picture, a diagram's next step): built now,
                # in the order they come, each from where the one before left it.
                out[i] = (self._from_queue(holder, holder.panim_heard), cue)
                continue
            view, name = holder.panim_look
            if not self._view_on(view):
                # Its picture is gone (another took the stage in this line): its label is not drawn over what
                # replaced it.
                out[i] = (Wait(0.05), cue)
                continue
            look = None
            if holder.panim_heard and self._view_on(view) and not self.__dict__.get("_strict"):
                # Every part said gets the light, however soon the next is said (the move is cut to fit): lit only
                # where the narration stayed a moment, the light stayed on the sheep while the goats were named.
                look = self._look(view, name)
            if look is not None:
                look.panim_camera = True
                out[i] = (look, [cue[0], self.LOOK_RUN])
            else:
                out[i] = (self._label_reveal(view, name), cue)
        return out

    def spoken_as(self, table: dict) -> None:
        """The words the line about to play says for each part of its pictures, by the part's name (the scene
        writer's "on" anchors, compile_lecture.anchors): a part is timed by those words, not its name, for that
        line. "Third law" said as "reaction", a node "Craftsmen" said as "कारीगर"."""
        self._spoken_as = {_norm(k): str(v) for k, v in (table or {}).items() if str(v or "").strip()}

    def _said(self, words, phrase) -> float | None:
        """When the line says `phrase` (a part's name): by the words its anchor names for this line, else by the
        phrase itself (said_at). In a strict chapter by its anchor only: a thing with none is not looked for in
        the line, and comes on as the line begins."""
        if not phrase:
            return None
        anchor = (self.__dict__.get("_spoken_as") or {}).get(_norm(phrase))
        if anchor:
            at = said_at(words, anchor)
            if at is not None:
                return at
        if self.__dict__.get("_strict"):
            return None
        return said_at(words, phrase)

    def strict_beats(self, on: bool) -> None:
        """A strict chapter's lines (compile_lecture: the chapter's "strict"): everything that comes on, and when,
        is the script's own -- each thing on its anchor, one with none as its line begins; nothing pointed at,
        lit or revealed by the engine because a line says its name."""
        self._strict = bool(on)

    def queue_on_words(self, say: str, build) -> None:
        """Queue `build(heard)` to make what comes on when `say` is said in the line about to play (beat): heard is
        False where the line does not say it and it simply comes on in turn."""
        self.__dict__.setdefault("_word_queue", []).append(
            SimpleNamespace(panim_said=str(say or ""), panim_build=build, panim_heard=False))

    def _from_queue(self, holder, heard: bool):
        """The animation a queued holder makes (a label's, or a build's), or a hold when it has none."""
        if getattr(holder, "panim_build", None) is not None:
            anim = holder.panim_build(heard)
        else:
            anim = self._label_reveal(*holder.panim_look)
        return anim if anim is not None else Wait(0.05)

    # ---------------- animations timed to the words (cues) ----------------
    CUE_MIN, CUE_MAX = 0.3, 2.5          # seconds an animation may take when timed to the words

    def _cue_plan(self, given: list, extra: list, seconds: float, default: float) -> list:
        """[(start, seconds, [animations])] in order: each animation at its cue, never before the one given before
        it, each finished before the next starts (or cut to fit). An animation with no cue starts with the line."""
        timed = []
        floor = 0.0
        for anim, cue in given:
            start, run = 0.0, default
            if isinstance(cue, (list, tuple)) and cue:
                try:
                    start = float(cue[0])
                    run = float(cue[1]) if len(cue) > 1 and cue[1] is not None else default
                except (TypeError, ValueError):
                    start, run = 0.0, default
            start = min(max(start, floor, 0.0), max(0.0, seconds - self.CUE_MIN))
            floor = start
            timed.append([start, min(max(run, self.CUE_MIN), self.CUE_MAX), anim])
        # A new panel clears the old one before its facts arrive (as an untimed beat does).
        head = [t for t in timed if getattr(t[2], "panel_head", False)]
        if head:
            after = head[0][0] + head[0][1] * 0.5
            for t in timed:
                if getattr(t[2], "panel_item", False):
                    t[0] = max(t[0], after)
        if extra:
            timed.append([0.0, default, None])
        groups: list = []
        for start, run, anim in sorted(timed, key=lambda t: t[0]):
            if groups and start - groups[-1][0] < 0.05:
                groups[-1][1] = max(groups[-1][1], run)
            else:
                groups.append([start, run, []])
            if anim is not None:
                groups[-1][2].append(anim)
            else:
                groups[-1][2].extend(extra)
        for i in range(len(groups) - 1):
            groups[i][1] = max(self.CUE_MIN, min(groups[i][1], groups[i + 1][0] - groups[i][0]))
        return [(start, run, anims) for start, run, anims in groups if anims]

    def _play_cued(self, plan: list, swaps: list | None = None) -> float:
        """Play a cue plan from the line's start: a hold until each group's time, then the group. Seconds taken."""
        swaps = swaps if swaps is not None else []
        elapsed = 0.0
        for start, run, anims in plan:
            elapsed = self._wait_until(elapsed, start, swaps)
            self.play(*anims, run_time=run)
            elapsed = self._swap_due(elapsed + run, swaps)
        return elapsed

    # ---------------- a long line's caption, a piece at a time ----------------

    def _caption_swaps(self, text: str, pieces: list[str], seconds: float, said=None) -> list:
        """[(seconds into the line, piece)] for each caption piece after the first: when its first word is said, from
        the line's word times when they are known (as the voice timed them, or as they were aligned), else by how
        far into the line its words are."""
        if len(pieces) < 2:
            return []
        total = sum(len(p.split()) for p in pieces) or 1
        out, before = [], 0
        for piece in pieces[:-1]:
            before += len(piece.split())
            share = before / total
            if said:
                at = float(said[min(len(said) - 1, int(round(share * len(said))))]["start"])
            else:
                at = share * seconds
            out.append((max(0.3, min(at, seconds - 0.3)), pieces[len(out) + 1]))
        return out

    def _swap_caption(self, piece: str) -> None:
        cap = self.caption(piece)
        if self.cap is not None:
            self.remove(self.cap)
        self.add(cap)
        self.cap = cap

    def _swap_due(self, elapsed: float, swaps: list) -> float:
        """The caption pieces whose time has come, put up now (after an animation that ran over their time)."""
        while swaps and swaps[0][0] <= elapsed + 1e-6:
            self._swap_caption(swaps.pop(0)[1])
        return elapsed

    def _wait_until(self, elapsed: float, target: float, swaps: list) -> float:
        """Hold from `elapsed` to `target` seconds into the line, putting up each caption piece on its time."""
        while swaps and swaps[0][0] <= target:
            at, piece = swaps.pop(0)
            if at > elapsed + 0.02:
                self.wait(at - elapsed)
                elapsed = at
            self._swap_caption(piece)
        if target > elapsed + 0.02:
            self.wait(target - elapsed)
            elapsed = target
        return elapsed

    # ---------------- the visual check ----------------
    # After each beat's animations, what is on screen is checked the way a viewer would see it: words too small to
    # read, words off the frame, words over other words, a stage left nearly empty. Words off the frame are brought
    # back in (said as fixed); the rest are written to PANIM_CHECK_LOG (one JSON line a beat), with the frame
    # saved to PANIM_CHECK_FRAMES when set, for the app to show a vision model (lib/visualcheck.ts).
    CHECK_MIN_TEXT = 13.0            # points, as drawn on the frame
    CHECK_OVERLAP = 0.3              # share of the smaller of two words' boxes they may share

    def _visible_texts(self) -> list:
        out = []
        for top in self.mobjects:
            for m in top.get_family():
                if not isinstance(m, Text) or not len(m.submobjects):
                    continue
                if getattr(m, "z_index", 0) >= Z_CAPTION or top is self.cap:
                    continue
                try:
                    if m.get_fill_opacity() < 0.2 and m.get_stroke_opacity() < 0.2:
                        continue
                except Exception:  # noqa: BLE001
                    pass
                if m.width > 1e-3 and m.height > 1e-3:
                    out.append(m)
        return out

    def _check_beat(self, text: str) -> list[str]:
        log, frames = os.environ.get("PANIM_CHECK_LOG"), os.environ.get("PANIM_CHECK_FRAMES")
        if not log and not os.environ.get("PANIM_CHECK"):
            return []
        issues, fixed = [], []
        half_w, half_h = config.frame_width / 2, config.frame_height / 2
        texts = [m for m in self._visible_texts() if m not in getattr(self, "chrome", VGroup()).get_family()]
        for m in texts:
            words = (getattr(m, "original_text", "") or "").strip()[:40]
            size = float(getattr(m, "font_size", 0) or 0)
            if size and size < 10:
                # Past reading on a phone: grown to the smallest readable size where it is.
                m.scale(self.CHECK_MIN_TEXT / size)
                fixed.append(f"tiny text ({size:.0f}pt) grown to {self.CHECK_MIN_TEXT:.0f}pt: {words!r}")
            elif size and size < self.CHECK_MIN_TEXT:
                issues.append(f"small text ({size:.0f}pt): {words!r}")
            lo, hi = m.get_corner(DL), m.get_corner(UR)
            dx = max(0.0, -half_w + 0.05 - lo[0]) - max(0.0, hi[0] - (half_w - 0.05))
            dy = max(0.0, -half_h + 0.05 - lo[1]) - max(0.0, hi[1] - (half_h - 0.05))
            if abs(dx) > 0.02 or abs(dy) > 0.02:
                # Brought back onto the frame: a word half off the screen is read by no one.
                m.shift(np.array([dx, dy, 0]))
                fixed.append(f"text off the frame brought in: {words!r}")
        boxes = [(m, _bbox(m)) for m in texts]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i][1], boxes[j][1]
                shared = _overlap(a, b)
                small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1e-9
                if shared / small > self.CHECK_OVERLAP and boxes[i][0] not in boxes[j][0].get_family() \
                        and boxes[j][0] not in boxes[i][0].get_family():
                    names = " / ".join(repr((getattr(x, "original_text", "") or "")[:30])
                                       for x in (boxes[i][0], boxes[j][0]))
                    # The later words moved just clear of the earlier, up or down, whichever stays on the frame.
                    mover = boxes[j][0]
                    down = a[1] - b[3] - 0.06
                    up = a[3] - b[1] + 0.06
                    step = down if b[1] + down > -half_h + 0.9 else up
                    if abs(step) < 1.2:
                        mover.shift(np.array([0, step, 0]))
                        boxes[j] = (mover, _bbox(mover))
                        fixed.append(f"words over words moved apart: {names}")
                    else:
                        issues.append(f"words over words: {names}")
        body = getattr(self, "stage_body", None)
        if body is not None and getattr(self, "stage_items", None) is not None and len(body.get_family()) > 1:
            cx, cy, w, h = self.STAGE
            share = (body.width * body.height) / max(w * h, 1e-6)
            if share < 0.12:
                issues.append(f"the stage's picture is small ({share:.0%} of its space)")
        if not issues and not fixed:
            return []
        self._checks = getattr(self, "_checks", 0) + 1
        row = {"beat": self._checks, "say": text[:200], "issues": issues[:12], "fixed": fixed[:12]}
        if frames and issues:
            try:
                from PIL import Image

                Path(frames).mkdir(parents=True, exist_ok=True)
                self.renderer.update_frame(self, ignore_skipping=True)
                target = Path(frames) / f"beat-{os.getpid()}-{self._checks:04d}.png"
                Image.fromarray(self.renderer.get_frame()).convert("RGB").resize((960, 540)).save(target)
                row["frame"] = str(target)
            except Exception as error:  # noqa: BLE001 -- the check is said without its frame
                row["frame_error"] = f"{type(error).__name__}: {error}"[:160]
        if log:
            with open(log, "a", encoding="utf-8") as out:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        return issues

    def pause(self, seconds: float = 0.6) -> None:
        self.wait(seconds)

    # Caption keywords: the words of a label on screen (a diagram's box, a defined term, a place) that the line
    # also says are coloured in the subtitle, so the ear, the eye and the picture meet on the same word.
    CAPTION_TERMS = 3
    _TERM_SKIP = {"the", "and", "for", "with", "from", "this", "that", "into", "then", "what", "when", "where"}

    def _screen_terms(self) -> list[str]:
        """The short labels on screen now, or arriving with this line (`_coming`): one to four words each."""
        mobs = list(self.mobjects)
        coming = list(getattr(self, "_coming", ()) or ())
        while coming:
            # A group of animations builds its own mobject only when played: its parts are looked into instead.
            anim = coming.pop()
            if getattr(anim, "mobject", None) is not None:
                mobs.append(anim.mobject)
            coming.extend(getattr(anim, "animations", ()) or ())
        chrome = set(id(m) for m in getattr(self, "chrome", VGroup()).get_family())
        terms = []
        for top in mobs:
            if top is self.cap:
                continue
            for m in top.get_family():
                if not isinstance(m, Text) or id(m) in chrome:
                    continue
                words = " ".join(str(getattr(m, "original_text", "") or "").split())
                n = len(words.split())
                if 1 <= n <= 4 and len(words) >= 4 and words.lower() not in self._TERM_SKIP and words not in terms:
                    terms.append(words)
        return terms

    def _caption_spans(self, text: str) -> list[tuple[int, int]]:
        """Where the line says a label that is on screen: (start, end) character spans, longest labels first,
        no two overlapping, at most CAPTION_TERMS."""
        spans: list[tuple[int, int]] = []
        for term in sorted(self._screen_terms(), key=len, reverse=True):
            pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in term.split()) + r"(?!\w)"
            hit = re.search(pattern, text, re.I)
            if hit and not any(a < hit.end() and hit.start() < b for a, b in spans):
                spans.append(hit.span())
            if len(spans) >= self.CAPTION_TERMS:
                break
        return spans

    @staticmethod
    def _colour_spans(t: Text, text: str, spans, colour: str) -> bool:
        """Colour the glyphs of `t` (made from `text`) inside `spans`. One glyph per character (with ligatures off,
        spaces and line breaks are glyphs too) or per character that is not a space; a script whose glyphs join
        (Hindi) matches neither and is left as it is."""
        for glyphs in (list(range(len(text))), [i for i, c in enumerate(text) if not c.isspace()]):
            if len(glyphs) == len(t.submobjects):
                break
        else:
            return False
        for k, i in enumerate(glyphs):
            if any(a <= i < b for a, b in spans):
                t.submobjects[k].set_fill(colour, opacity=1)
        return True

    def caption(self, text: str) -> VGroup:
        ready = self.__dict__.get("_kara_ready") or {}
        if text in ready:
            return ready.pop(text)
        lines = textwrap.wrap(text, 92)
        if len(lines) > 2:
            lines = textwrap.wrap(text, int(len(text) / 2) + 8)
        shown = "\n".join(lines)
        # No ligatures ("fi" drawn as one glyph): one glyph per letter, so the said terms can be coloured. Not for a
        # script whose letters join (Hindi): Manim refuses that, and its joined shapes are what is read.
        size = tok("caption_size", 19)
        try:
            if _complex(shown):
                raise ValueError("joined script")
            t = fit(T(shown, size, TH["cap_fg"], line_spacing=0.9, disable_ligatures=True), 13.2)
        except ValueError:
            t = fit(T(shown, size, TH["cap_fg"], line_spacing=0.9), 13.2)
        spans = self._caption_spans(shown) if os.environ.get("PANIM_CAPTION_TERMS", "1") != "0" else []
        if spans:
            # The highlight's colour, shaded until it reads on the caption box and stands apart from its words.
            colour = readable(getattr(P, "role_highlight", P.GOLD), TH["cap_bg"], 4.5)
            if contrast(colour, TH["cap_fg"]) < 1.6:
                colour = readable(P.GOLD, TH["cap_bg"], 4.5)
            if self._colour_spans(t, shown, spans, colour):
                t._panim_terms = [shown[a:b].replace("\n", " ") for a, b in spans]
        if len(t.submobjects) == len(shown):
            # A space or a line break is a blank glyph: none goes to the phone as a shape.
            t.remove(*[g for g, c in zip(list(t.submobjects), shown) if c.isspace()])
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
        group._panim_static = True
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
        """Clear the panel and head it. Returns the animation. On a board: the strip's title. On a wide map (no
        panel): nothing, the chapter's tag at the top already names it."""
        if getattr(self, "_wide", False) and getattr(self, "_map_on", False) and not self.board_mode:
            return None
        if self.board_mode:
            head = self.board_title(title, sub)
            if self.stage_body is not None and not self._beat_new and not self._beat_revealed:
                # A new topic: last topic's picture, question or working leaves with its title, rather than
                # staying up for the next picture to be set beside.
                going = self._stage_leaving()
                if going:
                    # Flat: the exporter plays one level of plain group (a group inside one it did not).
                    return AnimationGroup(*going, *([head] if head is not None else []))
            return head
        old = self.panel_items
        if (getattr(self, "_question", None) or {}).get("in_panel"):
            self._question = None       # its card leaves with the panel's words: no answer after it is gone
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
        self.panel_items = Group(items)
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
        """A line in the panel, wrapped at 36 characters. On a board: the strip's one key point."""
        if self.board_mode:
            return self.board_point(text, color)
        # Its words alone (no bullet): the panel's points are set apart by the space between them.
        t = fit(T(wrap(text, 36), tok("fact_size", size), color or P.CREAM, line_spacing=0.85), 4.95)
        group = self._stack(VGroup(t), 0.22)
        return self.reveal(group, t)

    def big_stat(self, value: str, label: str, color: str | None = None):
        """A large number with a small label under it."""
        if self.board_mode:
            return self.board_stat(value, label, color)
        v = fit(T(value, tok("stat_size", 44), color or P.GOLD, font=TH["serif"], weight=BOLD), 4.9)
        lab = fit(T(wrap(label, 40), 17, P.MUTED), TEXT_W - 0.25)
        lab.next_to(v, DOWN, aligned_edge=LEFT, buff=0.08)
        words = VGroup(v, lab)
        # A slim bar of the number's colour down its left: a figure that stands out from the points round it.
        bar = _flat(RoundedRectangle(corner_radius=0.03, width=0.06, height=words.height, fill_color=color or P.GOLD,
                                     fill_opacity=1, stroke_width=0))
        bar.next_to(words, LEFT, buff=0.18)
        group = self._stack(VGroup(bar, words), 0.3)
        return self.reveal(group, v)

    def panel_icon(self, name: str, label: str = "", color: str | None = None):
        """An icon with a line beside it in the panel: "sugarcane -- the west's cash crop"."""
        if self.board_mode:
            return self.board_point(label or name.split(":")[-1].replace("-", " "), color)
        try:
            mob = icon_mob(name, color, height=0.62)
        except KeyError:
            # No picture of it could be made: its line alone.
            return self.fact(label, color) if label else None
        row = Group(mob)
        if label:
            text = fit(T(wrap(label, 30), tok("fact_size", 20), P.CREAM, line_spacing=0.85), 4.1)
            text.next_to(mob, RIGHT, buff=0.22)
            row.add(text)
        group = self._stack(row, 0.25)
        return self.reveal(group, row[1] if label else None)

    def bar_chart(self, items, color: str | None = None, unit: str = "", width: float = 3.0):
        """Horizontal bars in the panel, each growing from a shared axis (on a board: across the board)."""
        if self.board_mode:
            return self.board_bars(items, color, unit)
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
        self.leave_board()
        self.panel = self.panel_bg()
        self.play(FadeIn(self.panel), run_time=run_time)

    def clear_panel(self):
        if self.board_mode:
            return self._strip(clear=True)
        old = [m for m in (self.panel_items, self.panel_images) if len(m)]
        self.panel_items = Group()
        self.panel_images = Group()
        self.panel_y = 2.35
        if (getattr(self, "_question", None) or {}).get("in_panel"):
            self._question = None
        return AnimationGroup(*[FadeOut(m) for m in old]) if old else None

    # ---------------- the stage: pictures where the map would be ----------------
    # Centre x, centre y, width, height: the map's half of the frame, left of the panel.
    STAGE = (-3.05, 0.3, 6.5, 6.1)

    def _stage_card(self):
        """What a stage picture sits on: invisible itself, and over a map the map's cover (_map_cover) under it."""
        cx, cy, w, h = self.STAGE
        covering = bool(getattr(self, "layers", None)) and getattr(self, "_map_on", False)
        card = Rectangle(width=w + 0.5, height=h + 0.6, fill_color=P.BG, fill_opacity=0, stroke_width=0)
        card.move_to([cx, cy, 0])
        cover = self._map_cover() if covering else None
        if cover is not None and getattr(self, "_cover_holder", None) is None:
            # The first picture over the map brings the cover in with it (it fades in with the picture); from
            # then on the cover stays up on its own while pictures come and go over it.
            card.add(cover)
            self._cover_holder = card
        import artstyle

        marks = artstyle.stage_marks(self.STAGE)
        if len(marks):
            card.add(marks)
        return card

    def _map_cover(self):
        """What hides the map while pictures are on the stage: the backdrop's colour over the whole of the map's
        part of the frame. A card the size of the stage left the map's edges showing round the picture, and,
        going out with each picture, put the whole map back up for a moment every time the picture changed."""
        cover = getattr(self, "_cover", None)
        if cover is None:
            left = -config.frame_width / 2
            right = self._map_right() if hasattr(self, "_map_right") else self.STAGE[0] + self.STAGE[2] / 2
            cover = Rectangle(width=right - left, height=config.frame_height, fill_color=P.BG, fill_opacity=1,
                              stroke_width=0).move_to([(left + right) / 2, 0, 0])
            cover.is_map_cover = True
            self._cover = cover
            self._cover_holder = None
        return cover

    def _keep_cover(self) -> None:
        """The cover stays when the picture it came in with leaves: it is taken out of that picture's card and
        stays on the screen by itself, under the pictures that follow."""
        cover, holder = getattr(self, "_cover", None), getattr(self, "_cover_holder", None)
        if cover is None or not holder or not any(cover is m for m in holder.submobjects):
            return
        holder.remove(cover)
        self._cover_holder = False
        if any(holder is m for m in self.get_mobject_family_members()):
            # Just under the stage's level: the picture leaving still fades out over it.
            self.add(cover.set_z_index(Z_MARK + 9.9))
        else:
            # Its picture never came up (replaced in the same beat): the next picture brings a cover of its own.
            self._cover = self._cover_holder = None

    def _cover_changes(self, going=()) -> list:
        """What the map shows above the cover goes and comes back with it: its labels and markers sit above the
        stage's own level (so they are read over the map's fills), and a cover under the pictures left them
        showing through ("Madrid" under a diagram). Only the map's own things: never a picture of the stage (one
        the line takes away was kept as a map label, and came back over the map when the cover went)."""
        hidden = getattr(self, "_cover_hidden", [])
        leaving = set()
        todo = list(going)
        while todo:
            anim = todo.pop()
            todo.extend(getattr(anim, "animations", None) or [])
            if getattr(anim, "remover", False) and getattr(anim, "mobject", None) is not None:
                leaving.update(id(x) for x in anim.mobject.get_family())
        if getattr(self, "_cover", None) is None:
            self._cover_hidden = []
            return [FadeIn(m) for m in hidden]
        keep = {id(x) for m in [self.stage_items, *self.stage_extra, getattr(self, "chrome", None),
                                getattr(self, "panel", None), self.cap, self._cover]
                if m is not None for x in m.get_family()}
        right = self._map_right() if hasattr(self, "_map_right") else self.STAGE[0] + self.STAGE[2] / 2
        out = []
        for m in list(self.mobjects):
            if id(m) in keep or id(m) in leaving or any(m is h for h in hidden) or \
                    any(getattr(x, "_panim_staged", False) for x in m.get_family()):
                continue
            zs = [getattr(x, "z_index", 0) for x in m.get_family()]
            if not zs or max(zs) < Z_MARK + 10 or max(zs) >= Z_CARD or m.get_center()[0] > right:
                continue
            hidden.append(m)
            out.append(FadeOut(m))
        self._cover_hidden = hidden
        return out

    def _drop_cover(self) -> list:
        """Fade-outs for the map's cover: the stage is cleared back to the map."""
        self._keep_cover()
        cover, self._cover, self._cover_holder = getattr(self, "_cover", None), None, None
        if cover is None or not any(cover is m for m in self.mobjects):
            return []
        return [FadeOut(cover)]

    def _stage_leaving(self) -> list:
        """Fade-outs for everything on the stage: the picture and any parts revealed on it since."""
        self._keep_cover()
        going = [FadeOut(m) for m in [self.stage_items, *self.stage_extra] if len(m.get_family()) > 1 or len(m.points)]
        # A labelled picture's shade (and a heading it moved aside) goes with it, wherever its list put it: a shade
        # left up sat over the next diagram.
        self.__dict__.pop("_full_bands", None)
        listed = {id(m) for m in [self.stage_items, *self.stage_extra]}
        on_screen = {id(m) for m in self.mobjects}
        for view in self.__dict__.get("_views", []):
            lens, hidden = view.get("lens"), view.get("hidden") or []
            if lens is not None and id(lens) not in listed and id(lens) in on_screen:
                going.append(FadeOut(lens))
            going += [FadeIn(m) for m in hidden if id(m) not in on_screen]
            view.update(lit=None, lens=None, hidden=[])
        # And whatever else is on the screen that no layout holds (strays: a part a picture left behind, a free
        # figure's piece dropped from the stage's list): the stage changes, so nothing of the old one stays.
        # Not the parts of a free figure that goes on (stem.BoardMixin.free).
        keep_on = {id(x) for m in (getattr(self, "_free_owned", []) if getattr(self, "_free_going_on", False) else [])
                   for x in m.get_family()}
        going += [a for a in self._clear_strays(going) if id(a.mobject) not in keep_on]
        for key in getattr(self, "_stage_keys", ()):
            if key in self.diagrams:
                self.diagrams[key]["gone"] = True
        self._stage_keys = set()
        self._gallery = None
        self.stage_items = Group()
        self.stage_extra = []
        if not (getattr(self, "_question", None) or {}).get("in_panel"):
            self._question = None      # a question in the panel stays there, with its answer to come
        self.stage_body = None
        self.stage_pending = []
        self.works = {}
        self._problem = None
        return going

    def _to_stage(self, group, draw=None, still: bool = False, entrance=None):
        """Put a picture on the stage, over the map; the one there before fades.

        A second picture for the same beat (a figure and its equation, say) goes beside the first rather
        than replacing it before it was ever seen: the stage splits in two. `draw`: the picture's parts, to be
        written in one after another (outlines, then their colours, as on a whiteboard) instead of faded in.
        `still`: the picture simply appears (nothing about it moves or is drawn in). `entrance`: how the picture
        comes on, built by its maker (a timeline drawing itself in), in place of a fade."""
        # Drawn in the lecture's art style (artstyle.py): the picture, and its parts still to be revealed.
        for picture in [group, *self._next_pending]:
            _art(picture)
        body = self.stage_body
        if self._panel_up() and getattr(group, "is_text_card", False) and body is not None \
                and not getattr(body, "is_text_card", False) and len(body.get_family()) > 1:
            # Words about the picture up (a question, a definition) go in the panel: the picture keeps the stage,
            # instead of the stage splitting into two narrow columns beside the panel.
            pending, self._next_pending = self._next_pending, []
            self._next_keys = set()
            return self._card_to_panel(group, pending)
        if self.__dict__.pop("_join_next", False) and body is not None and not self._beat_new \
                and len(group.get_family()) > 1 and len(body.get_family()) > 1 \
                and not any(getattr(m, "is_aside", False) for m in self.stage_extra):
            return self._join(group)
        if len(self._beat_new) == 1 and self.stage_body is self._beat_new[0] and len(group.get_family()) > 1 \
                and len(self.stage_body.get_family()) > 1:
            return self._beside(group)
        going = self._stage_leaving()
        new = Group(self._stage_card(), group)
        # A picture that drifts takes its card with it.
        set_drift([new[0]], group.__dict__.get("_panim_drift"))
        new.set_z_index(Z_MARK + 10)
        new._panim_staged = True
        lift_labels(new)
        self.stage_items = new
        self.stage_body = group
        self.stage_pending, self._next_pending = self._next_pending, []
        self._stage_keys, self._next_keys = set(self._next_keys), set()
        self._beat_new.append(group)
        if still:
            # No entrance at all: the picture before it leaves, and it is simply there. (An animation returned to
            # the beat is stretched over the line, so a fade of a frame became a fade of seconds.)
            if going:
                self.play(*going, run_time=0.4)
            self.add(new)
            return None
        if entrance is not None:
            show = AnimationGroup(FadeIn(new[0]), entrance)
        elif draw:
            show = AnimationGroup(FadeIn(new[0]), LaggedStart(*[write_in(m) for m in draw], lag_ratio=0.3))
        else:
            show = FadeIn(new, shift=UP * 0.2)
        # The old picture is gone before the new one arrives: overlapping them put a new diagram over a
        # half-faded photo.
        anim = AnimationGroup(AnimationGroup(*going, run_time=0.4), show, lag_ratio=1.0) if going else show
        anim.panim_stage = True
        return anim

    def _solving(self) -> bool:
        """A problem is on the board and its answer not boxed yet."""
        return self._problem is not None and not self._problem.get("answered")

    def _halves(self):
        cx, cy, w, h = self.STAGE
        return (cx - w / 4, cy, w / 2 - 0.25, h), (cx + w / 4, cy, w / 2 - 0.25, h)

    @staticmethod
    def _fit_box(mobs, box, grow: float = 1.0):
        """Scale and move these together (a picture and its parts still to come) to fill the box."""
        whole = Group(*mobs)
        cx, cy, w, h = box
        f = min((w - 0.2) / max(whole.width, 0.01), (h - 0.2) / max(whole.height, 0.01), grow)
        centre = whole.get_center()
        for m in mobs:
            m.scale(f, about_point=centre).shift(np.array([cx, cy, 0]) - centre)
        follow_drift(mobs, f, centre, np.array([cx, cy, 0]) - centre)
        return f, np.array(centre, dtype=float), np.array([cx, cy, 0]) - centre

    PAIR_GAP = 0.35          # between two pictures sharing the stage
    PAIR_PICTURE = 0.3       # the least a picture is shrunk to when it shares the stage (it still reads)
    PAIR_WORDS = 0.65        # the least a thing of words (a timeline, a comparison, a diagram) is shrunk to

    def _pair_boxes(self, first: list, second: list, grow: float = 1.3) -> tuple:
        """Two boxes on the stage for two things shown together (each with its parts): side by side or one above
        the other, and the split between them, chosen so that each is shown as large as it needs: a picture still
        reads at a third of its size, words (a timeline's, a comparison's, a diagram's) need two thirds. The layout
        whose worse-off thing is furthest above its need wins (then the one that fills the most of the stage): a
        timeline beside a photo gets the wider share, two pictures share alike."""
        cx, cy, w, h = self.STAGE
        a, b = Group(*first), Group(*second)
        aw, ah, bw, bh = max(a.width, 0.01), max(a.height, 0.01), max(b.width, 0.01), max(b.height, 0.01)
        need = [self.PAIR_PICTURE if has_image(m) else self.PAIR_WORDS for m in (a, b)]
        gap = self.PAIR_GAP
        best, chosen = None, None
        for stacked in (False, True):
            for r in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7):
                if stacked:
                    ha, hb = (h - gap) * r, (h - gap) * (1 - r)
                    box_a, box_b = (cx, cy + h / 2 - ha / 2, w, ha), (cx, cy - h / 2 + hb / 2, w, hb)
                else:
                    wa, wb = (w - gap) * r, (w - gap) * (1 - r)
                    box_a, box_b = (cx - w / 2 + wa / 2, cy, wa, h), (cx + w / 2 - wb / 2, cy, wb, h)
                fa = min((box_a[2] - 0.2) / aw, (box_a[3] - 0.2) / ah, 1.0)
                fb = min((box_b[2] - 0.2) / bw, (box_b[3] - 0.2) / bh, grow)
                filled = (fa * fa * aw * ah + fb * fb * bw * bh) / (w * h)
                score = (min(fa / need[0], fb / need[1]), filled)
                if best is None or score > best:
                    best, chosen = score, (box_a, box_b)
        return chosen

    def screen_join(self) -> None:
        """The script's `"screen": "join"` (a beat's): the line's new main picture joins the one already up instead
        of replacing it (_join)."""
        self._join_next = True

    def _join(self, group):
        """A new picture joining the one up from an earlier line (the script's "screen": "join"): the one up, with its
        parts, slides into its share of the stage and the new one comes on in the other, where each is seen best
        (_pair_boxes)."""
        firsts = [self.stage_items, *self.stage_extra, *self.stage_pending]
        news = [group, *self._next_pending]
        box_a, box_b = self._pair_boxes(firsts, news)
        whole = Group(*firsts)
        f = min((box_a[2] - 0.2) / max(whole.width, 0.01), (box_a[3] - 0.2) / max(whole.height, 0.01), 1.0)
        slide = self._move_stage(f, whole.get_center(), box_a)
        self._fit_box(news, box_b, grow=1.3)
        group.is_aside = True
        group.aside_box = box_b
        self.stage_pending = [*self.stage_pending, *self._next_pending]
        self._next_pending = []
        self._stage_keys |= self._next_keys
        self._next_keys = set()
        self._beat_new.append(group)
        self._stage_add(group)
        show = FadeIn(group, scale=1.02)
        return AnimationGroup(slide, show, lag_ratio=0.6) if slide is not None else show

    def _beside(self, group):
        """The beat's second picture: the drawing takes the left half, the words about it (a definition, an
        equation, a question) the right. Neither is on screen yet, so the two are simply laid out again."""
        left, right = self._halves()
        first = self.stage_body
        self._leave_full_screen(shown=False)
        if self._panel_up() and getattr(first, "is_text_card", False) and not getattr(group, "is_text_card", False):
            # The card came first and a panel is up: the card goes in the panel, the drawing takes the stage whole.
            self.stage_items.remove(first)
            self.stage_items.add(group)
            group.set_z_index(Z_MARK + 10)
            lift_labels(group)
            moved = self._card_to_panel(first, self.stage_pending)
            self.stage_body = group
            self.stage_pending, self._next_pending = self._next_pending, []
            self._stage_keys |= self._next_keys
            self._next_keys = set()
            self._beat_new = [m for m in self._beat_new if m is not first] + [group]
            return moved
        if getattr(first, "is_text_card", False) and not getattr(group, "is_text_card", False):
            # The card came first: the drawing takes its place in the stage group, the card goes beside it.
            self.stage_items.remove(first)
            self.stage_items.add(group)
            group.set_z_index(Z_MARK + 10)
            lift_labels(group)
            picture, card = group, first
            picture_parts, card_parts = self._next_pending, self.stage_pending
            self.stage_body = group
        else:
            picture, card = first, group
            picture_parts, card_parts = self.stage_pending, self._next_pending
        # What the beat already added to the first picture (its revealed parts, a spotlight's ring) moves with it:
        # left behind, the parts sat over the second picture and the ring pointed at nothing.
        added = list(self.stage_extra)
        if picture is first:
            picture_parts = [*picture_parts, *added]
        else:
            card_parts = [*card_parts, *added]
        # The two laid out together where each is seen best: side by side or one over the other (a wide timeline
        # under a picture), the stage split where neither ends up small.
        left, right = self._pair_boxes([picture, *picture_parts], [card, *card_parts])
        moved = self._fit_box([picture, *picture_parts], left)
        self._fit_box([card, *card_parts], right, grow=1.3)
        card.is_aside = True
        card.aside_box = right
        self.stage_pending = [m for m in [*picture_parts, *card_parts] if all(m is not a for a in added)]
        self._next_pending = []
        self._stage_keys |= self._next_keys
        self._next_keys = set()
        self._beat_new.append(group)
        self._stage_add(card)
        return FadeIn(card, scale=1.02)

    def _leave_full_screen(self, shown: bool = True) -> list:
        """A full-screen picture made smaller (a card set beside it): what only a full-screen picture has goes
        first -- the shade round a part (the heading it moved aside comes back) and the soft bands under the heading
        and the caption, which shrunk with it became a dim box. Fade-outs (`shown`), or simply taken away."""
        out = []
        for view in self.__dict__.get("_views", []):
            if view.get("lens") is not None and self._view_on(view):
                back = self._look_out(view)
                if back is not None and shown:
                    out.append(back)
        holder, bands = self.__dict__.pop("_full_bands", (None, []))
        body = getattr(self, "stage_body", None)
        if holder is not None and body is not None and any(holder is m for m in body.get_family()):
            for band in bands:
                if any(band is m for m in holder.submobjects):
                    holder.remove(band)
                if shown and any(band is m for top in self.mobjects for m in top.get_family()):
                    out.append(FadeOut(band, run_time=0.4))
        return out

    def _panel_up(self) -> bool:
        """A side panel of text is on the screen (a panel chapter, a map with its panel)."""
        panel = getattr(self, "panel", None)
        return not self.board_mode and panel is not None and any(panel is m for m in self.mobjects) \
            and not getattr(self, "_wide", False)

    def _card_to_panel(self, card, extras=()):
        """A card (a question, a definition, an equation) written in the panel under what is there, at the panel's
        width; `extras` (its answer, still to come) move with it and are the panel's too. When the panel has no
        room left, its points go first (its title stays)."""
        going = []
        bottom = CAPTION_Y + 0.55

        def scale_for() -> float:
            return min(1.0, TEXT_W / max(card.width, 0.01), max(self.panel_y - bottom, 0.3) / max(card.height, 0.01))

        if scale_for() < 0.6 and len(self.panel_items) > 1:
            head, rest = self.panel_items[0], list(self.panel_items[1:])
            going = [FadeOut(m) for m in rest]
            self.panel_items = Group(head)
            self.panel_y = head.get_bottom()[1] - 0.3
        f = scale_for()
        centre = card.get_center().copy()
        for m in [card, *extras]:
            m.scale(f, about_point=centre)
        shift = np.array([self.TEXT_LEFT, self.panel_y, 0]) - card.get_corner(UL)
        for m in [card, *extras]:
            m.shift(shift)
            m.set_z_index(Z_PANEL_TEXT)
            m._panim_panel = True
        self.panel_y = card.get_bottom()[1] - 0.25
        card.is_in_panel = True
        self.panel_items.add(card)
        show = FadeIn(card, shift=RIGHT * 0.2)
        return AnimationGroup(AnimationGroup(*going), show, lag_ratio=1.0) if going else show

    def _aside(self, mob, grow: float = 1.3):
        """Put `mob` (a definition, an equation) in the right half of the board, beside the drawing on the stage
        (moved into the left half). None when there is no drawing to sit beside: a card beside a question or
        an equation is not about it. Two cards in one beat stack in that half; a later one replaces them."""
        body = self.stage_body
        if not self.board_mode or body is None or self.works or self._problem is not None \
                or getattr(body, "is_text_card", False) or not len(body.get_family()) > 1:
            return None
        left, right = self._halves()
        mob.is_aside = True
        mob.aside_box = right
        if self._beat_asides:
            # Not shown yet: the beat's cards are laid out again, one under the other.
            cards = [*self._beat_asides, mob]
            stack = Group(*cards).arrange(DOWN, buff=0.45)
            self._fit_box([stack], right, grow=1.0)
            self._beat_asides.append(mob)
            self._stage_add(mob)
            return FadeIn(mob, shift=LEFT * 0.2)
        old = [m for m in self.stage_extra if getattr(m, "is_aside", False)]
        self._beat_asides.append(mob)
        if old:
            # A card is already beside the drawing: the new one takes its place.
            for m in old:
                self.stage_extra.remove(m)
            self._fit_box([mob], right, grow=grow)
            self._stage_add(mob)
            # One after the other as a lagged group, which the exporter plays (a Succession of groups it did not).
            return AnimationGroup(AnimationGroup(*[FadeOut(m) for m in old]), FadeIn(mob, shift=LEFT * 0.2),
                                  lag_ratio=1.0)
        # Sized with the parts still to be revealed: fitted without them, a later arrow's label ran off the frame.
        moved = Group(self.stage_body, *self.stage_extra, *self.stage_pending)
        cx, cy, w, h = left
        f = min((w - 0.2) / max(moved.width, 0.01), (h - 0.2) / max(moved.height, 0.01), 1.0)
        slide = self._move_stage(f, moved.get_center(), left)
        self._fit_box([mob], right, grow=grow)
        self._stage_add(mob)
        arrive = FadeIn(mob, shift=LEFT * 0.2)
        return AnimationGroup(slide, arrive, lag_ratio=1.0) if slide is not None else arrive

    def _move_stage(self, f: float, centre, box):
        """Scale the stage's picture and parts by f about `centre` and move them to the box's centre. Parts
        already on screen slide there; parts this beat is still bringing in (a node being revealed, a picture
        not shown yet) are simply put there, since two animations on one part fight and it stayed behind."""
        if getattr(self.stage_body, "free_area", None) == "left":
            # A free-form figure drawn in the left half already: what comes beside it takes the right half, and the
            # figure stays where its blocks draw (moved, their next parts would land beside it).
            return None
        leaving = self._leave_full_screen()
        cx, cy = box[0], box[1]
        shift = np.array([cx, cy, 0]) - centre
        # The map's cover stays the size of the map: moved with the picture's card, it shrank and the map showed.
        cover, holder = getattr(self, "_cover", None), getattr(self, "_cover_holder", None)
        if cover is not None and holder and any(cover is m for m in holder.submobjects):
            holder.remove(cover)
            self._cover_holder = False
            self.add(cover.set_z_index(Z_MARK + 9.9))
        arriving = {id(m) for m in [*self._beat_new, *self._beat_revealed]}
        # A free-form figure moved aside is frozen first: a part that redraws itself (a TracedPath, always_redraw)
        # changed its shape during the move, which the exporter could not write, and the whole build stopped.
        free = getattr(self, "_free_group", None)
        if free is not None:
            # Kept first (a group's clear clears its parts too), so the figure's next block, moved home first, has
            # its sweep or traced path going again.
            for x in free.get_family():
                if x.updaters:
                    x.panim_held_updaters = list(x.updaters)
            for x in free.get_family():
                x.clear_updaters()
        slides = []
        for m in [self.stage_items, *self.stage_extra]:
            if id(m) in arriving or (m is self.stage_items and id(self.stage_body) in arriving):
                m.scale(f, about_point=centre).shift(shift)
            else:
                # Written as the move it is (an xform the players apply to the whole picture), not a morph of the
                # picture into a copy of itself: a morph pairs the shapes up one by one, and with a drawing that
                # moves (a gear turning) they no longer line up, so parts shrank late and the picture warped.
                import stem

                slides.append(stem._moving(m.animate.scale(f, about_point=centre).shift(shift)))
                # Not there until the beat plays: what is laid out over it later in this beat (a labelled part's
                # shade) is placed where it is going (_where), not where it was.
                self.__dict__.setdefault("_moving", []).append(
                    ({id(x) for x in m.get_family()}, f, np.array(centre, dtype=float), np.array(shift, dtype=float)))
        for m in self.stage_pending:
            m.scale(f, about_point=centre).shift(shift)
        follow_drift([self.stage_items, *self.stage_extra, *self.stage_pending], f, np.array(centre, dtype=float), shift)
        slides = leaving + slides
        return AnimationGroup(*slides) if slides else None

    def _stage_add(self, mob):
        """A part added to the picture already on the stage; it leaves with it."""
        mob.set_z_index(Z_MARK + 11)
        lift_labels(mob)
        mob._panim_staged = True
        self.stage_extra.append(mob)
        self._beat_added.append(mob)
        return mob

    def clear_stage(self):
        """Take the stage picture away, showing the map again. None when there is none.

        Not when this beat has already put something up: a script that clears after a beat's working (the
        order a model often writes) would wipe what the beat is about to show."""
        if self._beat_new or self._beat_added:
            return None
        going = self._stage_leaving() + self._drop_cover()
        return AnimationGroup(*going) if going else None

    # How a picture on the stage moves once it is drawn: (kind) -> what it does over time. It starts when the
    # drawing-in is over (PICTURE_SETTLE seconds) and goes on while the picture is up.
    PICTURE_MOVES = ("bob", "sway", "breathe", "drift")
    PICTURE_SETTLE = 3.3

    def _move_picture(self, image, extras, kind: str) -> None:
        """Set a drawn picture (and its labels) moving: bob (up and down, a boat), sway (rocking about its foot, a
        flag, a tree), breathe (swelling a little, a heart, a lung), drift (on across the stage, a ship, a
        caravan). Each a small, steady motion that repeats exactly, so the phone plays it as a looping clip."""
        if kind not in self.PICTURE_MOVES or not hasattr(self, "_live_start"):
            return
        state = {"shift": 0.0, "angle": 0.0, "scale": 1.0}
        parts = [image, *extras]
        foot = image.get_bottom()
        settle = self.PICTURE_SETTLE

        def step(t: float, _p: float) -> None:
            ramp = min(1.0, max(0.0, (t - settle) / 1.0))
            ease = ramp * ramp * (3 - 2 * ramp)
            k = t - settle
            if kind == "bob":
                want = 0.09 * ease * math.sin(2 * PI * k / 3.0)
                for m in parts:
                    m.shift(UP * (want - state["shift"]))
                state["shift"] = want
            elif kind == "drift":
                # On by half a unit, back past where it began, and home again every twelve seconds: slow enough to read.
                want = 0.5 * ease * math.sin(2 * PI * k / 12.0)
                for m in parts:
                    m.shift(RIGHT * (want - state["shift"]))
                state["shift"] = want
            elif kind == "sway":
                want = 0.045 * ease * math.sin(2 * PI * k / 4.0)
                image.rotate(want - state["angle"], about_point=foot)
                state["angle"] = want
            elif kind == "breathe":
                want = 1.0 + 0.035 * ease * math.sin(2 * PI * k / 3.5)
                image.scale(want / state["scale"])
                state["scale"] = want

        self._live_start(image, step, "loop", keep=True)

    def stage_image(self, path: str, caption: str = "", credit: str = "", labels=(), move: str | None = None,
                    points=(), hold=(), notes=None):
        """A photo or a document's figure, large, on the stage. Not while a problem is being solved: it took
        the problem, its figure and its working off the board mid-solution.

        A picture the image model made is drawn in, shape by shape (cutout_strokes). `labels` ([(text, x, y)] or
        [(text, x, y, x0, y0, x1, y1)], x and y from 0 to 1 across and down the picture, x0..y1 the box round the
        part) are each written beside it as the part is said, a box round the part and a line to it, and the rest of
        the picture shaded round the part (_picture_view)."""
        if self.board_mode and self._solving() and not self._beat_new:
            self._log("skipped", what="figure during a problem", path=str(path))
            return None
        # The script's own say over its labels (BEAT_SCRIPT.md, picture): those held back come on with a `label`
        # op on a later line; a short note under a label's name.
        self._label_opts = {"hold": {_norm(x) for x in hold or ()},
                            "notes": {_norm(k): str(v) for k, v in (notes or {}).items() if str(v or "").strip()}}
        try:
            return self._stage_image(path, caption, credit, labels, move, points)
        finally:
            self._label_opts = None

    def _stage_image(self, path: str, caption: str, credit: str, labels, move, points):
        cx, cy, w, h = self.STAGE
        line = None
        if caption:
            line = T(wrap(_short_caption(caption), 70), 16, P.CREAM, line_spacing=0.85)
        room = h - (line.height + 0.3 if line is not None else 0) - (0.3 if credit else 0)
        if is_cutout(path) and points:
            return self._split_picture(path, [str(p) for p in points if str(p).strip()][:5], caption, move)
        labels = [tuple(x) for x in labels or () if isinstance(x, (list, tuple)) and len(x) >= 3]
        cutout = is_cutout(path)
        # The picture without its empty margin, its labels moved to match.
        src, box = trim_box(path)
        labels = remap_labels(labels, box)
        if self._full_screen():
            return self._full_picture(src, labels, cutout, move)
        # The stage's whole width (and no more: never under the panel), its labels written on it, as on a
        # full-screen picture.
        image = cutout_mob(src, w, room) if cutout else ImageMobject(src)
        if not cutout:
            image.scale_to_fit_width(w)
            if image.height > room:
                image.scale_to_fit_height(room)
        parts = [image]
        if line is not None:
            parts.append(fit(line, max(image.width, 4.0)).next_to(image, DOWN, buff=0.14))
        if credit:
            parts.append(fit(T(credit, TYPE["fine"], P.MUTED, fine=True), w).next_to(parts[-1], DOWN, buff=0.06))
        group = Group(*parts)
        group.shift(np.array([cx, cy, 0]) - group.get_center())
        framed = not has_alpha(src)
        depth = over = None
        if framed:
            # A photo, a scene, a book's figure: a modern frame (photo_frame); a cutout stays a sticker.
            depth, over = photo_frame(self, image)
            group = Group(depth, *parts, over)
        if not move and drifts_on():
            # It keeps moving, slowly, while it is on (PICTURE_DRIFT); its labels move with it (_picture_view).
            centre = image.get_center()
            set_drift([group], dict(PICTURE_DRIFT, cx=float(centre[0]), cy=float(centre[1])))
        if cutout:
            shown = self._to_stage(group, draw=[*([depth] if depth is not None else []), *cutout_strokes(image),
                                                *parts[1:], *([over] if over is not None else [])])
        else:
            shown = self._to_stage(group)
        if over is not None:
            # Over the picture, under the camera's view of a part and the labels' lines.
            over.set_z_index(Z_MARK + 10.5)
        if labels:
            # The labels come on as their parts are said (beat): not with the picture, all at once; each on the
            # picture beside its part.
            # A labelled picture stays where it is: its boxes, labels and lights are on its parts.
            self._picture_view(image, labels, w, inside=True)
        elif move and cutout:
            self._move_picture(image, [], move)
        return shown

    # ---------------- a picture with the screen to itself ----------------
    # A picture that is the line's whole visual (no panel beside it, nothing else built for the line) fills the
    # screen: a scene or a photo cut to the screen's shape and drawn edge to edge, a little larger than the frame so
    # its slow drift never shows an edge; a cutout as large as the screen holds. The chapter's tag, the board's title
    # and the caption lie over it, on soft bands of the board's colour so they read; its labels are written on it,
    # beside their parts.
    FULL_BLEED = 1.06

    def _full_screen(self) -> bool:
        """Whether a picture going up now has the screen to itself."""
        # Not while a side panel is up, even an empty one: drawn over it, the picture lay under the panel's words
        # when they came, and the map's cover hid its left part.
        return (not len(self.panel_items) and not self._beat_new and not self._solving() and not self._panel_up()
                and not self.__dict__.get("_keep_whole") and os.environ.get("PANIM_FULL_SCREEN", "1") != "0")

    def _bands(self) -> list:
        """Soft bands of the board's colour along the top and the bottom of a full-screen picture: the heading and
        the caption read over it."""
        fw, fh = config.frame_width, config.frame_height
        out = []
        steps = 8
        for top, depth in ((True, 1.4), (False, 1.7)):
            edge = fh / 2 if top else -fh / 2
            # Stacked strips from the edge in, each a little shorter: where they overlap the colour is deepest, so it
            # fades smoothly from the edge to the picture.
            for k in range(steps):
                height = depth * (steps - k) / steps
                band = Rectangle(width=fw * self.FULL_BLEED, height=height, stroke_width=0, fill_color=P.BG,
                                 fill_opacity=0.11).move_to([0, edge - height / 2 if top else edge + height / 2, 0])
                band._art_none = True
                out.append(band)
        return out

    def _full_picture(self, src: str, labels, cutout: bool, move: str | None):
        fw, fh = config.frame_width, config.frame_height
        if has_alpha(src):
            # A cutout on the board: as large as fits between the heading and the caption.
            image = cutout_mob(src, fw - 1.0, fh - 2.0)
            image.move_to([0, -0.1, 0])
            parts = [image]
        else:
            src, box = cover_box(src, fw / fh)
            labels = remap_labels(labels, box)
            image = ImageMobject(src)
            image.stretch_to_fit_width(fw * self.FULL_BLEED)
            image.stretch_to_fit_height(fh * self.FULL_BLEED)
            image.move_to(ORIGIN)
            parts = [image, *self._bands()]
        group = Group(*parts)
        if not move and drifts_on():
            set_drift([group], dict(PICTURE_DRIFT, cx=0.0, cy=0.0))
        shown = self._to_stage(group, draw=[image] if getattr(image, "_panim_child", False) else None)
        for band in parts[1:]:
            band.set_z_index(Z_MARK + 10.5)
            band._panim_z = Z_MARK + 10.5
        self._full_bands = (group, parts[1:])
        if labels:
            self._picture_view(image, labels, fw, inside=True)
        elif move and cutout:
            self._move_picture(image, [], move)
        return shown

    def _split_picture(self, path: str, points: list[str], caption: str = "", move: str | None = None):
        """The split layout: the picture large on the left, the few words to take away from it on the right, each
        with a bullet in the style's accent, written in after the picture is drawn."""
        cx, cy, w, h = self.STAGE
        left_w = w * 0.52
        image = cutout_mob(path, left_w - 0.2, h - 0.4)
        image.move_to([cx - w / 2 + left_w / 2, cy, 0])
        room = w - left_w - 0.3
        rows = []
        for words in points:
            dot = Dot(radius=0.07, color=role("accent"))
            text = fit(T(wrap(words, 34), 22, P.CREAM, line_spacing=0.9), room - 0.4)
            rows.append(VGroup(dot, text).arrange(RIGHT, buff=0.18, aligned_edge=UP))
            dot.shift(DOWN * 0.12)
        column = VGroup(*rows).arrange(DOWN, buff=0.32, aligned_edge=LEFT)
        if caption:
            head = fit(T(_short_caption(caption), 24, P.TITLE, font=TH["serif"], weight=BOLD), room)
            column = VGroup(head, column).arrange(DOWN, buff=0.36, aligned_edge=LEFT)
        if column.height > h - 0.4:
            column.scale((h - 0.4) / column.height)
        column.move_to([cx - w / 2 + left_w + 0.3 + column.width / 2, cy, 0])
        group = Group(image, column)
        draw = [*cutout_strokes(image), *column]
        shown = self._to_stage(group, draw=draw)
        if move:
            self._move_picture(image, [], move)
        return shown

    def _label_opt(self, kind: str, name: str):
        return ((self.__dict__.get("_label_opts") or {}).get(kind) or {}).get(_norm(name)) if kind != "hold" \
            else _norm(name) in ((self.__dict__.get("_label_opts") or {}).get("hold") or set())

    def _label_tag(self, text: str, room: float, size: float = 17):
        """A picture's label as it is written on the stage: its words on a highlight -- a solid patch of the
        board's colour with a gold edge -- so they read over a white picture, a dark one, or the board; with the
        script's short note under the name, smaller, when it gives one."""
        words = fit(marker(text, size), room - 0.2)
        note = self._label_opt("notes", text)
        if note:
            small = fit(T(wrap(str(note), 32), max(12, size - 4), P.MUTED), room - 0.2)
            words = VGroup(words, small).arrange(DOWN, buff=0.05, aligned_edge=LEFT)
        patch = SurroundingRectangle(words, buff=0.08, corner_radius=0.08, color=P.GOLD, stroke_width=2,
                                     fill_color=P.BG, fill_opacity=0.92)
        return VGroup(patch, words)

    # ---------------- a labelled picture: each part named as it is said, the rest shaded ----------------
    # A picture with labels is shown whole. Each label comes on as its part is said: a box round the part and its
    # name. Where the narration stays on a part a moment, the rest of the picture is shaded dark and the part left
    # lit; the light moves to each part as it is named, and lifts once every part has been talked about (LOOK_HOLD
    # after the last) or when the narration moves on; the labels and boxes stay. A heading lying over the
    # part steps aside while it is talked about. Shapes fading in and out: the phone plays it as the video does.
    LOOK_RUN = 0.6           # seconds the shade takes to come on or move
    SHADE = 0.62             # how dark the rest of the picture goes
    Z_LOOK = Z_LABEL - 0.7   # the shade: over the picture, under the parts' boxes, lines and names

    def _picture_view(self, image, labels, width: float, inside: bool = False) -> dict:
        """Lay out a picture's labels (not yet shown), queue each to come on as its part is said (beat), and let a
        later line that names a part light it again (name_part)."""
        view = {"image": image, "parts": {}, "revealed": set(), "lit": None, "lens": None, "hidden": [],
                "beat": self.__dict__.get("_sync_beat", 0),
                "drift": image.__dict__.get("_panim_drift")}
        for piece in (self._labels_on(image, labels) if inside else self._label_layout(image, labels, width)):
            view["parts"][piece["name"]] = piece
            # Each label drifts with its picture: its name, box and line stay on the part.
            set_drift([piece["tag"], *self._pointer_pieces(piece)], view["drift"])
            # Not shown yet, it is still the picture's: when the stage moves or shrinks the picture (a card set
            # beside it, a word's strip over it) the label moves and shrinks with it, not left where it was laid out.
            self.stage_pending.extend([*self._pointer_pieces(piece), piece["tag"]])
        views = self.__dict__.setdefault("_views", [])
        views.append(view)
        queue = self.__dict__.setdefault("_word_queue", [])
        for name, piece in view["parts"].items():
            # Built when the line plays (_with_looks), in the order the parts are said: each label's coming on and
            # each light starts from where the one before left the picture. A label the script holds back
            # comes on later, with its `label` op.
            if not self._label_opt("hold", name):
                queue.append(SimpleNamespace(panim_said=name, panim_look=(view, name), panim_heard=False))
            self.name_part(name, piece["tag"], shown=lambda v=view, n=name: n in v["revealed"] and self._view_on(v),
                           act=lambda v=view, n=name: self._look(v, n))
        return view

    def _view_on(self, view) -> bool:
        """Whether a labelled picture is still the one on the stage (and on the screen)."""
        body = getattr(self, "stage_body", None)
        if body is None or not any(m is view["image"] for m in body.get_family()):
            return False
        return any(m is view["image"] for top in self.mobjects for m in top.get_family()) or \
            any(m is body for m in self._beat_new)

    def _where(self, mob) -> tuple:
        """(lower left, upper right) of `mob` once this beat has played: a stage move built this beat (_move_stage)
        is an animation, so the picture is still where it was until it plays. A shade laid out from where it was
        lay far off the picture (it had moved aside for a card), over the card's words."""
        lo, hi = np.array(mob.get_corner(DL), dtype=float), np.array(mob.get_corner(UR), dtype=float)
        for ids, f, centre, shift in self.__dict__.get("_moving", []):
            if id(mob) in ids:
                lo, hi = (lo - centre) * f + centre + shift, (hi - centre) * f + centre + shift
        return lo, hi

    def _part_rect(self, view, box) -> tuple:
        """(x0, y0, x1, y1) on the screen of a box given across and down the picture (0 to 1)."""
        lo, hi = self._where(view["image"])
        u0, v0, u1, v1 = box
        return (lo[0] + u0 * (hi[0] - lo[0]), hi[1] - v1 * (hi[1] - lo[1]),
                lo[0] + u1 * (hi[0] - lo[0]), hi[1] - v0 * (hi[1] - lo[1]))

    def _label_layout(self, image, labels, width: float) -> list:
        """Each label's pieces, placed: the tag beside the picture (left-half parts to its left, the rest to its
        right, in order down the picture, spread so no two touch), the box round its part, the line from the box's
        near side to the tag, a dot where they meet."""
        lo, hi = image.get_corner(DL), image.get_corner(UR)
        iw, ih = hi[0] - lo[0], hi[1] - lo[1]
        room = max((width - image.width) / 2 - 0.35, 0.9)
        sides: dict[int, list] = {-1: [], 1: []}
        for entry in labels:
            text, x, y = str(entry[0]), float(entry[1]), float(entry[2])
            if len(entry) >= 7:
                box = tuple(float(v) for v in entry[3:7])
            else:
                # No box from the label finder: a patch round its point.
                rw, rh = min(0.09, 0.3 * ih / max(iw, 1e-6)) * max(1.0, ih / max(iw, 1e-6)), 0.09
                box = (max(0.0, x - rw), max(0.0, y - rh), min(1.0, x + rw), min(1.0, y + rh))
            point = np.array([lo[0] + x * iw, hi[1] - y * ih, 0])
            sides[-1 if x < 0.5 else 1].append((text, point, box))
        out = []
        for side, items in sides.items():
            items.sort(key=lambda item: -item[1][1])
            tags = [self._label_tag(text, room) for text, _, _ in items]
            ys, gap = [], 0.12
            for tag, (_, point, _) in zip(tags, items):
                want = point[1]
                if ys:
                    want = min(want, ys[-1][0] - ys[-1][1] / 2 - gap - tag.height / 2)
                ys.append((want, tag.height))
            bottom = lo[1] + ys[-1][1] / 2 if ys else 0
            if ys and ys[-1][0] < bottom:
                lift = bottom - ys[-1][0]
                ys = [(y + lift, height) for y, height in ys]
            for tag, (text, point, box), (y, _) in zip(tags, items, ys):
                edge = lo[0] - 0.3 if side < 0 else hi[0] + 0.3
                tag.move_to([edge + side * tag.width / 2, y, 0])
                x0, y0 = lo[0] + box[0] * iw, hi[1] - box[3] * ih
                x1, y1 = lo[0] + box[2] * iw, hi[1] - box[1] * ih
                # Corner brackets round the part (hud_frame), over a dark halo so they read on any picture.
                halo_frame = hud_frame(x1 - x0, y1 - y0, P.BG, stroke=7, glow=False)
                halo_frame[0].set_stroke(opacity=0)
                halo_frame.brackets.set_stroke(opacity=0.8)
                frame = VGroup(halo_frame, hud_frame(x1 - x0, y1 - y0, P.GOLD, stroke=3.2))
                frame.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
                # The line from the tag to the side of the box facing it, at the part's height (kept on the box).
                start = tag.get_right() if side < 0 else tag.get_left()
                end = np.array([x0 if side < 0 else x1, min(max(point[1], y0 + 0.04), y1 - 0.04), 0])
                halo = Line(end, start, color=P.BG, stroke_width=7, stroke_opacity=0.9)
                pointer = Line(end, start, color=P.GOLD, stroke_width=3)
                dot = Dot(end, radius=0.07, color=P.GOLD, stroke_color=P.BG, stroke_width=3)
                for m in (frame, halo, pointer, dot):
                    m.set_z_index(Z_LABEL - 0.5)
                    for part in m.get_family():
                        part._panim_above = True
                tag.set_z_index(Z_LABEL)
                for part in tag.get_family():
                    part._panim_above = True
                out.append({"name": text, "box": box, "tag": tag, "frame": frame, "halo": halo, "line": pointer,
                            "dot": dot})
        return out

    def _labels_on(self, image, labels) -> list:
        """Labels written on a full-screen picture: each name beside its part's box (above it, else below, else to
        a side), clear of the names before it, of the heading and of the caption."""
        lo, hi = image.get_corner(DL), image.get_corner(UR)
        iw, ih = hi[0] - lo[0], hi[1] - lo[1]
        fw, fh = config.frame_width, config.frame_height
        x_lo, x_hi, y_lo, y_hi = -fw / 2 + 0.3, fw / 2 - 0.3, -fh / 2 + 1.25, fh / 2 - 1.15
        # A picture smaller than the screen keeps its names on itself.
        x_lo, x_hi = max(x_lo, lo[0] + 0.08), min(x_hi, hi[0] - 0.08)
        y_lo, y_hi = max(y_lo, lo[1] + 0.08), min(y_hi, hi[1] - 0.08)
        placed: list = []
        out = []
        for entry in labels:
            text, x, y = str(entry[0]), float(entry[1]), float(entry[2])
            box = tuple(float(v) for v in entry[3:7]) if len(entry) >= 7 else \
                (max(0.0, x - 0.06), max(0.0, y - 0.06), min(1.0, x + 0.06), min(1.0, y + 0.06))
            x0, y0 = lo[0] + box[0] * iw, hi[1] - box[3] * ih
            x1, y1 = lo[0] + box[2] * iw, hi[1] - box[1] * ih
            tag = self._label_tag(text, min(4.0, max(x_hi - x_lo, 1.0)), 21 if iw > 9 else 18)
            tw, th = tag.width, tag.height
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            spots = [(cx, y1 + 0.12 + th / 2), (cx, y0 - 0.12 - th / 2), (x1 + 0.15 + tw / 2, cy),
                     (x0 - 0.15 - tw / 2, cy)]
            best = None
            for sx, sy in spots:
                sx = min(max(sx, x_lo + tw / 2), x_hi - tw / 2)
                sy = min(max(sy, y_lo + th / 2), y_hi - th / 2)
                rect = (sx - tw / 2, sy - th / 2, sx + tw / 2, sy + th / 2)
                clash = any(not (rect[2] < r[0] or rect[0] > r[2] or rect[3] < r[1] or rect[1] > r[3])
                            for r in placed)
                if best is None:
                    best = (sx, sy, rect)
                if not clash:
                    best = (sx, sy, rect)
                    break
            tag.move_to([best[0], best[1], 0])
            placed.append(best[2])
            halo_frame = hud_frame(x1 - x0, y1 - y0, P.BG, stroke=7, glow=False)
            halo_frame[0].set_stroke(opacity=0)
            halo_frame.brackets.set_stroke(opacity=0.8)
            frame = VGroup(halo_frame, hud_frame(x1 - x0, y1 - y0, P.GOLD, stroke=3.2))
            frame.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
            for m in (frame, tag):
                m.set_z_index(Z_LABEL if m is tag else Z_LABEL - 0.5)
                for part in m.get_family():
                    part._panim_above = True
            out.append({"name": text, "box": box, "tag": tag, "frame": frame, "halo": None, "line": None,
                        "dot": None})
        return out

    @staticmethod
    def _pointer_pieces(piece) -> list:
        return [m for m in (piece["frame"], piece["halo"], piece["line"], piece["dot"]) if m is not None]

    def _label_reveal(self, view, name: str):
        """A label coming on: the box drawn round its part, the line out to its name, the name."""
        piece = view["parts"][name]
        view["revealed"].add(name)
        for m in [*self._pointer_pieces(piece), piece["tag"]]:
            self.stage_pending = [x for x in self.stage_pending if x is not m]
            if all(m is not x for x in self.stage_extra):
                self.stage_extra.append(m)
        # The box locks on to the part (in from a little larger), the line runs out from the part to the name, and
        # the name fades in.
        pointers = [FadeIn(piece["frame"], scale=1.25)]
        if piece["line"] is not None:
            pointers += [GrowFromCenter(piece["dot"]), AnimationGroup(Create(piece["halo"]), Create(piece["line"]))]
        return LaggedStart(*pointers, FadeIn(piece["tag"]), lag_ratio=0.3)

    def _shade(self, view, name: str):
        """Dark panels over the picture all round a part's box (with a margin): the rest of the picture shaded, the
        part lit."""
        (X0, Y0), (X1, Y1) = self._picture_rect(view)
        x0, y0, x1, y1 = self._part_rect(view, view["parts"][name]["box"])
        pad = 0.12
        x0, y0, x1, y1 = max(X0, x0 - pad), max(Y0, y0 - pad), min(X1, x1 + pad), min(Y1, y1 + pad)
        panels = VGroup()
        # Above and below the part, the picture's whole width; beside it, its height.
        for a, b, c, d in ((X0, y1, X1, Y1), (X0, Y0, X1, y0), (X0, y0, x0, y1), (x1, y0, X1, y1)):
            if c - a > 0.01 and d - b > 0.01:
                panels.add(Rectangle(width=c - a, height=d - b, stroke_width=0, fill_color="#000000",
                                     fill_opacity=self.SHADE).move_to([(a + c) / 2, (b + d) / 2, 0]))
        panels.set_z_index(self.Z_LOOK)
        for part in panels.get_family():
            part._panim_z = self.Z_LOOK
            part._art_none = True
        set_drift([panels], view.get("drift"))
        return panels

    def _picture_rect(self, view) -> tuple:
        """(lower left, upper right) of what the shade covers: the picture itself, without a margin round it that
        is not the picture (a dressed card's edge and shadow: view["content"], 0 to 1 across and down)."""
        lo, hi = self._where(view["image"])
        u0, v0, u1, v1 = view.get("content") or (0.0, 0.0, 1.0, 1.0)
        w, h = hi[0] - lo[0], hi[1] - lo[1]
        return (lo[0] + u0 * w, hi[1] - v1 * h), (lo[0] + u1 * w, hi[1] - v0 * h)

    def _overlays_over(self, view, name: str) -> list:
        """The headings lying over a part of a full-screen picture (the chapter's tag, the board's title)."""
        x0, y0, x1, y1 = self._part_rect(view, view["parts"][name]["box"])
        out = []
        for mob in [getattr(self, "chrome", None), *(getattr(self, "strip", None) or {}).values()]:
            if mob is None or not len(mob.get_family()) or mob not in self.mobjects:
                continue
            lo, hi = mob.get_corner(DL), mob.get_corner(UR)
            if lo[0] < x1 and hi[0] > x0 and lo[1] < y1 + 0.2 and hi[1] > y0:
                out.append(mob)
        return out

    def _look(self, view, name: str):
        """Shade the rest of a labelled picture round a part (its label first if it is not on yet), from wherever the
        shade is. None when it is round this part already, or cannot be."""
        if not self._view_on(view) or name not in view["parts"]:
            return None
        if view["lit"] == name:
            return None
        steps = []
        if name not in view["revealed"]:
            steps.append(self._label_reveal(view, name))
        moves = []
        old = self._look_out(view)
        if old is not None:
            moves.append(old)
        shade = self._shade(view, name)
        self.stage_extra.append(shade)
        moves.append(FadeIn(shade, run_time=self.LOOK_RUN))
        # A heading over the part steps aside while it is talked about.
        hidden = self._overlays_over(view, name)
        moves += [FadeOut(m, run_time=self.LOOK_RUN) for m in hidden]
        view.update(lit=name, lens=shade, hidden=hidden)
        view.setdefault("spoken", set()).add(name)
        steps.append(AnimationGroup(*moves))
        look = AnimationGroup(*steps, lag_ratio=1.0)
        look.panim_view = view
        return look

    LOOK_HOLD = 1.4          # seconds the light stays on the last part before the whole picture comes back

    def _lifts(self, given: list, seconds: float) -> list:
        """The light lifted from a labelled picture once every one of its parts has been talked about: LOOK_HOLD after
        the last part's light came on (in this line, or as the next line begins when this one ends first). The labels
        and their boxes stay; the whole picture is clear again."""
        out = []
        for view in self.__dict__.get("_views", []):
            if view.get("lit") is None or view.get("held_light") or not view["parts"] or \
                    not set(view["parts"]) <= view.get("spoken", set()):
                continue
            lit = [c for a, c in given if getattr(a, "panim_view", None) is view and isinstance(c, (list, tuple)) and c]
            if not lit:
                continue
            last = max(float(c[0]) + float(c[1] or self.LOOK_RUN) for c in lit)
            at = last + self.LOOK_HOLD
            if at > seconds - self.LOOK_RUN:
                if last + 0.4 > seconds - self.LOOK_RUN:
                    view["lift_next"] = True     # lifted as the next line begins (_looks_away)
                    continue
                at = seconds - self.LOOK_RUN
            back = self._look_out(view)
            if back is not None:
                out.append((back, [round(at, 3), self.LOOK_RUN]))
        return out

    def _look_out(self, view):
        """The shade lifted (and a heading that stepped aside back)."""
        shade = view.get("lens")
        if shade is None:
            return None
        hidden = view.get("hidden") or []
        view.update(lit=None, lens=None, hidden=[])
        if any(shade is x for x in self.stage_extra):
            self.stage_extra.remove(shade)
        return AnimationGroup(FadeOut(shade, run_time=self.LOOK_RUN), *[FadeIn(m, run_time=self.LOOK_RUN) for m in hidden])

    def _looks_away(self, words) -> list:
        """At a line's start: the shade lifted from a picture whose parts this line does not name (or that is gone,
        the heading it moved aside back)."""
        out = []
        for view in self.__dict__.get("_views", []):
            if view["lit"] is None or (view.get("held_light") and self._view_on(view)):
                continue
            if self._view_on(view) and words and any(self._said(words, n) is not None for n in view["parts"]) \
                    and not view.pop("lift_next", False):
                continue
            if not self._view_on(view):
                hidden, lens = view.get("hidden") or [], view.get("lens")
                view.update(lit=None, lens=None, hidden=[])
                out += [FadeIn(m) for m in hidden if m not in self.mobjects]
                if lens is not None and lens in self.mobjects:
                    out.append(FadeOut(lens))
                continue
            back = self._look_out(view)
            if back is not None:
                out.append(back)
        return out

    def illustration(self, hero: str, items=(), title: str | None = None, color: str | None = None):
        """An illustration built from pictures of things: one large, up to four small ones labelled beneath."""
        cx, cy, w, h = self.STAGE
        big = icon_mob(hero, color, height=2.5)
        parts = Group(big)
        if title:
            parts.add(fit(T(title.upper() if TH["upper"] else title, 30, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
        parts.arrange(DOWN, buff=0.3)
        row = Group()
        for item in list(items)[:4]:
            name, label = (item, "") if isinstance(item, str) else (item[0], item[1] if len(item) > 1 else "")
            try:
                small = icon_mob(name, color, height=0.85)
            except KeyError:
                continue
            cell = Group(small)
            if label:
                cell.add(fit(T(label, 15, P.CREAM), 1.5).next_to(small, DOWN, buff=0.1))
            row.add(cell)
        if len(row):
            row.arrange(RIGHT, buff=0.45, aligned_edge=UP)
            fit(row, w - 0.4)
            composition = Group(parts, row).arrange(DOWN, buff=0.55)
        else:
            composition = parts
        if composition.height > h - 0.2:
            composition.scale_to_fit_height(h - 0.2)
        composition.move_to([cx, cy, 0])
        return self._to_stage(Group(composition))

    # ---------------- subject kits: drawings for science, maths and history ----------------
    def _fit_stage(self, mob, margin: float = 0.3, grow: float = 1.0):
        """Fit a drawing to the stage: shrink it to fit, or grow it up to `grow` times to fill the stage."""
        cx, cy, w, h = self.STAGE
        factor = min((w - margin) / max(mob.width, 0.01), (h - margin) / max(mob.height, 0.01), grow)
        if factor < 1 or grow > 1:
            mob.scale(factor)
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
        if self.board_mode and (self._solving() or self.works and self._problem is None):
            # A problem is being solved: the equation is the next line of its working, not a new picture
            # that wipes the problem off the board.
            key = next(iter(self.works), None) or (self._problem or {}).get("key") or "working"
            return self.work(key, [tex])
        try:
            body = MathTex(tex, color=P.CREAM).scale(1.4)
        except Exception:  # noqa: BLE001 -- TeX that will not compile: the same maths as text
            body = T(unicode_math(tex), 56, P.CREAM, font=TH["serif"])
        parts = VGroup(body)
        if label:
            parts.add(fit(T(label, 20, P.MUTED), w - 0.4))
        parts.arrange(DOWN, buff=0.45)
        parts.is_text_card = True
        if not self._beat_new:
            # A drawing on the board: the equation goes beside it, so the drawing (and parts of it revealed
            # in this beat) stays in view.
            beside = self._aside(parts, grow=1.0)
            if beside is not None:
                return beside
        self._fit_stage(parts, 0.6)
        card = Group(parts)
        card.is_text_card = True
        return self._to_stage(card)

    def process(self, steps, title: str | None = None, cycle: bool = False):
        """Steps joined by arrows: a chain (snaking into rows) or a cycle."""
        cx, cy, w, h = self.STAGE
        steps = [str(x) for x in list(steps)[:8]]
        boxes = VGroup()
        tones = [P.SAND, P.RIVER, P.GREEN, P.ROSE, P.GOLD, P.TEAL, P.VIOLET, P.DUNE]
        for i, step in enumerate(steps):
            tone = tones[i % 8]
            badge = VGroup(Circle(radius=0.22, fill_color=tone, fill_opacity=1, stroke_width=0),
                           T(str(i + 1), 17, P.BG, weight=BOLD))
            badge[1].move_to(badge[0])
            text = VGroup(badge, T(wrap(step, 16), 26, P.CREAM, line_spacing=0.9)).arrange(RIGHT, buff=0.22)
            boxes.add(self._card(text, tone, pad=0.3))
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
            parts.add(fit(T(title.upper() if TH["upper"] else title, 30, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
            parts.arrange(UP, buff=0.4)
        self._fit_stage(parts, grow=1.4)
        return self._to_stage(Group(parts))

    def _room_for_arrows(self, mobs: dict, edges, shortest: float = 0.75) -> None:
        """Spread a diagram's nodes apart (their places, not their sizes) until every arrow between them has room to
        be seen: a ring of four big drawings left the arrows between them a few hundredths long, so they were never
        drawn. The diagram is fitted to the stage afterwards, so spreading it only makes the nodes a little smaller."""
        pairs = [(mobs[str(e[0])], mobs[str(e[1])]) for e in edges
                 if str(e[0]) in mobs and str(e[1]) in mobs and str(e[0]) != str(e[1])]
        if not pairs:
            return
        centre = Group(*mobs.values()).get_center()
        for _ in range(12):
            gaps = [np.linalg.norm(end - start) * (1 if np.dot(end - start, b.get_center() - a.get_center()) > 0 else -1)
                    for a, b in pairs for start, end in [self._edge_points(a, b)]]
            if min(gaps) >= shortest:
                return
            for mob in mobs.values():
                mob.shift((mob.get_center() - centre) * 0.15)

    @staticmethod
    def _inside_box(mob, point, pad: float = 0.0) -> bool:
        lo, hi = mob.get_corner(DL), mob.get_corner(UR)
        return lo[0] - pad <= point[0] <= hi[0] + pad and lo[1] - pad <= point[1] <= hi[1] + pad

    def _clear_arrow(self, a, b, others):
        """An arrow from box a to box b that crosses no other box: straight when the way is clear, else bowed to
        one side, as little as clears them (a straight arrow from the first card to the third ran through the
        second)."""
        style = dict(color=P.CREAM, stroke_width=OUTLINE * 1.2)
        start, end = self._edge_points(a, b)

        def crossings(points) -> int:
            return sum(1 for m in others if any(self._inside_box(m, p, 0.1) for p in points))

        straight = [start + (end - start) * t for t in np.linspace(0, 1, 41)]
        if not others or not crossings(straight):
            return Arrow(start, end, buff=0.08, max_tip_length_to_length_ratio=0.22,
                         max_stroke_width_to_length_ratio=12, **style)
        from manim import ArcBetweenPoints, CurvedArrow

        best = None
        for angle in (0.45, -0.45, 0.8, -0.8, 1.2, -1.2, 1.7, -1.7):
            arc = ArcBetweenPoints(a.get_center(), b.get_center(), angle=angle)
            points = [arc.point_from_proportion(t) for t in np.linspace(0, 1, 81)]
            # The part of the curve between the two boxes, a little clear of each.
            first = next((k for k, p in enumerate(points) if not self._inside_box(a, p, 0.08)), None)
            last = next((k for k in range(len(points) - 1, -1, -1) if not self._inside_box(b, points[k], 0.08)), None)
            if first is None or last is None or last - first < 4:
                continue
            score = crossings(points[first:last + 1])
            if best is None or score < best[0]:
                best = (score, points[first], points[last], angle * (last - first) / (len(points) - 1))
            if score == 0:
                break
        if best is None:
            return Arrow(start, end, buff=0.08, max_tip_length_to_length_ratio=0.22,
                         max_stroke_width_to_length_ratio=12, **style)
        _, p0, p1, angle = best
        length = float(np.linalg.norm(p1 - p0))
        return CurvedArrow(p0, p1, angle=angle, tip_length=min(0.25, 0.22 * max(length, 0.3)), **style)

    @staticmethod
    def _edge_points(a, b):
        """Where an arrow between two boxes leaves one and meets the other."""
        start, end = a.get_center(), b.get_center()
        direction = end - start
        length = np.linalg.norm(direction) or 1.0
        unit = direction / length

        def exit_point(box, sign):
            # A drawing has no box: its edge is the drawing and its name together.
            frame = box if getattr(box, "is_drawing", False) else box[0]
            half_w, half_h = frame.width / 2, frame.height / 2
            scale = min(half_w / (abs(unit[0]) or 1e-9), half_h / (abs(unit[1]) or 1e-9))
            return box.get_center() + sign * unit * (scale + 0.08)

        return exit_point(a, 1), exit_point(b, -1)

    TIMELINE_MOST = 10       # events on one timeline
    SPAN_TONES = ("GOLD", "RIVER", "ROSE", "GREEN", "VIOLET", "TEAL")

    TIMELINE_ENTRANCES = ("draw", "travel", "whole")

    def big_timeline(self, events, title: str | None = None, range=None, spans=None, scale: str | None = None,
                     enter: str | None = None):
        """A timeline across the stage: a track, a ringed node on it for each event, the date in a pill on a stem,
        the event's words beyond it, alternately above and below, each event's picture (a photo, a figure, a
        drawing: (date, label, picture)) beyond its words. It is still: it appears whole.

        v2: in PROPORTION when every date reads as a year (timeline_dates.year: "1526", "500 BC", "1920s", "16th
        century"...): each event sits at its date, with a scale of round years under the track; `range` (from, to)
        sets the years the track covers (events outside it are left out); `spans` [(from, to, label)] shade periods
        along the track (a reign, an era, a war), overlapping ones in lanes. Events too close for their words are
        spread apart along their side, each with a slanted stem back to its true date. `scale` "even": evenly
        spaced, as before (steps with no real dates).

        `enter` (v2, the script's): how it comes on. "draw": the title and the track draw themselves, then each event
        pops onto the track (its node, its stem, its date and words); "travel": the same, with a marker that runs
        along the track to each event as it comes; "whole" (or none): it is simply there. An event with words of its
        own (its "on") comes on with them; the others in date order after the track. Its events are never pointed at
        by the engine because a line names them: only the script's `point` does."""
        import timeline_dates as td

        cx, cy, w, h = self.STAGE
        events = [tuple(e) + (None,) * (3 - len(e)) for e in list(events)[:self.TIMELINE_MOST]]
        width = w - 0.6
        years = [td.year(e[0]) for e in events]
        wanted = (td.year(range[0]), td.year(range[1])) if range and len(range) == 2 else (None, None)
        if wanted[0] is not None and wanted[1] is not None and wanted[0] > wanted[1]:
            wanted = (wanted[1], wanted[0])
        proportional = scale != "even" and len(events) >= 2 and all(y is not None for y in years) \
            and len(set(years)) > 1
        span_list = []
        if proportional:
            for sp in spans or []:
                if not isinstance(sp, (list, tuple)) or len(sp) < 2:
                    continue
                a, b = td.year(sp[0]), td.year(sp[1])
                if a is not None and b is not None and a != b:
                    span_list.append((min(a, b), max(a, b), str(sp[2]) if len(sp) > 2 and sp[2] else ""))
            span_list = span_list[:6]
            if wanted[0] is not None and wanted[1] is not None and wanted[1] > wanted[0]:
                lo, hi = wanted
                kept = [(e, y) for e, y in zip(events, years) if lo <= y <= hi]
                if len(kept) < len(events):
                    self._log("skipped", what="timeline events outside its range",
                              error=", ".join(str(e[0]) for e, y in zip(events, years) if not lo <= y <= hi))
                events, years = [e for e, _ in kept], [y for _, y in kept]
                span_list = [(max(a, lo), min(b, hi), t) for a, b, t in span_list if b > lo and a < hi]
            else:
                ends = years + [v for a, b, _ in span_list for v in (a, b)]
                lo, hi = min(ends), max(ends)
                pad = max((hi - lo) * 0.06, 0.5)
                lo, hi = lo - pad, hi + pad
            order = sorted(builtins_range(len(events)), key=lambda k: years[k])
            events, years = [events[k] for k in order], [years[k] for k in order]
            if len(events) < 1:
                return None

            def at(y):
                return -width / 2 + (y - lo) / max(hi - lo, 1e-9) * width
            xs = [at(y) for y in years]
        else:
            slot = width / max(len(events), 1)
            xs = [-width / 2 + slot * (k + 0.5) for k in builtins_range(len(events))]
        n = max(len(events), 1)
        pictured = any(e[2] for e in events)
        tone = P.SAND
        track = _flat(Line(LEFT * width / 2, RIGHT * width / 2, color=P.MUTED, stroke_width=9, stroke_opacity=0.35))
        lit = _flat(Line(LEFT * width / 2, RIGHT * width / 2, color=tone, stroke_width=3, stroke_opacity=0.9))
        extras = []
        scale_drop = 0.0
        if proportional:
            # The scale of round years under the track: a tick on it and the year beneath.
            any_bc = lo < 0
            marks_ = []
            for t in td.ticks(lo, hi, 7 if width > 9 else 5):
                x = at(t)
                if not -width / 2 - 1e-6 <= x <= width / 2 + 1e-6:
                    continue
                tick = Line([x, -0.13, 0], [x, 0.13, 0], color=P.MUTED, stroke_width=2.5, stroke_opacity=0.8)
                word = T(td.label(t, any_bc), 15, P.MUTED, fine=True).move_to([x, -0.36, 0])
                marks_.append(_flat(VGroup(tick, word)))
            if marks_:
                extras.append(VGroup(*marks_))
                scale_drop = 0.42
            # Periods (spans): each a tint on the track over its years, and a labelled bar in a strip under the scale
            # (clear of the event nodes on the track), in lanes where they (or their words) would overlap.
            strip_top = -(0.36 + 0.22) if marks_ else -0.3
            lanes: list[float] = []
            placed = []
            for k, (a, b, text) in enumerate(sorted(span_list)):
                x0, x1 = at(a), at(b)
                word = T(text, 16, P.CREAM, weight=BOLD) if text else None
                if word is not None and word.width > 2.6:
                    word.scale_to_fit_width(2.6)
                reach = (min(x0, (x0 + x1) / 2 - word.width / 2), max(x1, (x0 + x1) / 2 + word.width / 2)) \
                    if word is not None else (x0, x1)
                lane = next((m for m, end in enumerate(lanes) if reach[0] >= end + 0.15), len(lanes))
                if lane == len(lanes):
                    lanes.append(reach[1])
                else:
                    lanes[lane] = reach[1]
                placed.append((x0, x1, text, word, lane, k))
            lane_h = 0.5
            for x0, x1, text, word, lane, k in placed:
                colour = getattr(P, self.SPAN_TONES[k % len(self.SPAN_TONES)], tone)
                y = strip_top - 0.1 - lane * lane_h
                tint = Line([x0, 0, 0], [x1, 0, 0], color=colour, stroke_width=7, stroke_opacity=0.55)
                bar = RoundedRectangle(corner_radius=0.06, width=max(x1 - x0, 0.06), height=0.13, stroke_width=0,
                                       fill_color=colour, fill_opacity=0.8).move_to([(x0 + x1) / 2, y, 0])
                ends = VGroup(*[Line([x, y - 0.1, 0], [x, y + 0.1, 0], color=colour, stroke_width=2.5) for x in (x0, x1)])
                parts = [tint, bar, ends]
                if word is not None:
                    word.move_to([(x0 + x1) / 2, y - 0.1 - word.height / 2 - 0.04, 0])
                    lo_x, hi_x = -width / 2 + word.width / 2, width / 2 - word.width / 2
                    word.set_x(min(max(word.get_x(), lo_x), hi_x))
                    parts.append(word)
                    self.name_part(text, bar)
                extras.append(_flat(VGroup(*parts)))
            if placed:
                scale_drop = -strip_top - 0.45 + 0.1 + len(lanes) * lane_h + 0.05

        def build(picture_height, cap):
            """Each event's pieces at their natural size, the words no wider than `cap`."""
            out = []
            for k, (date, label, picture) in enumerate(events):
                up = k % 2 == 0
                chip = ui_chip(str(date), tone, 23)
                fit(chip, cap)
                lab = fit(T(wrap(str(label), 16), 20, P.CREAM, weight=BOLD, line_spacing=0.85), cap)
                VGroup(chip, lab).arrange(UP if up else DOWN, buff=0.12)      # the date by the track, the words beyond
                pieces = [chip, lab]
                pic = self._picture(picture, picture_height, cap, motion="none") if picture else None
                if pic is not None:
                    pic.next_to(lab, UP if up else DOWN, buff=0.12).set_x(lab.get_x())
                    pieces.append(pic)
                out.append((up, group_of(*pieces)))
            return out

        def spread(items):
            """Centres for the heads on one side: as near their dates as they can be without touching."""
            gap = 0.22
            centres = []
            for k, (x, head) in enumerate(items):
                half = head.width / 2
                c = max(x, -width / 2 + half)
                if centres:
                    px, pw = centres[-1]
                    c = max(c, px + pw / 2 + gap + half)
                centres.append((c, head.width))
            # Pulled back inside the track from the right, keeping the gaps.
            for k in builtins_range(len(centres) - 1, -1, -1):
                c, wd = centres[k]
                limit = width / 2 - wd / 2 if k == len(centres) - 1 else centres[k + 1][0] - centres[k + 1][1] / 2 - gap - wd / 2
                centres[k] = (min(c, limit), wd)
            return [c for c, _ in centres]

        side_count = max(sum(1 for k in builtins_range(n) if k % 2 == 0), sum(1 for k in builtins_range(n) if k % 2))
        cap = min(2.6, (width - 0.22 * side_count) / max(side_count, 1))
        height = min(1.5, (h - 1.6) / 2 - 0.9) if pictured else 0
        heads = build(height, cap)
        for _ in builtins_range(6):
            # Too wide together for their side: everything a little smaller.
            widest = max(sum(hd.width for up, hd in heads if up), sum(hd.width for up, hd in heads if not up))
            if widest + 0.22 * side_count <= width or cap < 0.9:
                break
            cap *= 0.85
            height *= 0.85
            heads = build(height, cap)
        marks = []
        placed_x = [0.0] * n
        for up in (True, False):
            idx = [k for k in builtins_range(n) if (k % 2 == 0) == up]
            for k, c in zip(idx, spread([(xs[k], heads[k][1]) for k in idx])):
                placed_x[k] = c
        for k, (date, label, picture) in enumerate(events):
            up, head = heads[k]
            sign = 1 if up else -1
            x, c = xs[k], placed_x[k]
            base = 0.45 if up else 0.45 + scale_drop
            ring = Circle(radius=0.17, stroke_color=tone, stroke_width=4, fill_color=P.BG, fill_opacity=1)
            node = _flat(VGroup(ring, Dot(radius=0.075, color=tone)).move_to([x, 0, 0]))
            head.move_to([c, 0, 0])
            head.shift(UP * (sign * base) + UP * (sign * head.height / 2))
            # The stem: from the node to the head, slanted when the head was moved along to make room.
            stem = _flat(Line([x, sign * 0.19, 0], [c, sign * (base - 0.02), 0], color=tone, stroke_width=2.5,
                              stroke_opacity=0.7))
            marks.append(group_of(node, stem, head))
        drawing = Group(track, lit, *extras, *marks)
        for (date, label, _picture), mark in zip(events, marks):
            # The script points at an event (`point`); the engine does not, because a line says its date.
            self.name_part(date, mark, auto=False)
            self.name_part(label, mark, auto=False)
        parts = Group(drawing)
        if title:
            parts.add(fit(T(title.upper() if TH["upper"] else title, 32, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4))
            parts.arrange(UP, buff=0.5)
        self._fit_stage(parts, grow=1.25)
        if enter in ("draw", "travel"):
            return self._timeline_in(parts, drawing, track, lit, extras, marks, events, enter == "travel")
        # Still: it is simply there, whole (b189db3: an entrance handed to the beat is stretched over the line).
        return self._to_stage(Group(parts), still=True)

    def _timeline_in(self, parts, drawing, track, lit, extras, marks, events, travel: bool):
        """A timeline that builds itself: the title and the track (its scale, its periods) drawn in as it comes on;
        each event held back and brought on in turn (on its own words when it has them), a marker running along
        the track to it first when `travel`."""
        title = parts[1] if len(parts.submobjects) > 1 else None
        for mark in marks:
            drawing.remove(mark)
        self._next_pending.extend(marks)
        intro = ([FadeIn(title, shift=DOWN * 0.15)] if title is not None else []) + \
            [AnimationGroup(Create(track), Create(lit), run_time=0.9)] + [Create(x) for x in extras]
        marker = None
        if travel:
            marker = Dot(radius=0.11, color=P.GOLD).move_to(track.get_left())
            marker.set_z_index(Z_MARK + 12)
            halo = Circle(radius=0.2, stroke_width=0, fill_color=P.GOLD, fill_opacity=0.25).move_to(marker)
            marker = VGroup(halo, marker)
            drawing.add(marker)
            intro.append(FadeIn(marker, scale=0.5))
        shown = self._to_stage(Group(parts), entrance=LaggedStart(*intro, lag_ratio=0.3))
        for (date, label, _picture), mark in zip(events, marks):
            holder = SimpleNamespace(panim_said=str(label), panim_alts=[str(label), str(date)], panim_heard=False,
                                     panim_build=lambda heard, mark=mark: self._timeline_event(mark, marker))
            self.__dict__.setdefault("_word_queue", []).append(holder)
        return shown

    def _timeline_event(self, mark, marker=None):
        """One event onto its timeline: the marker run to it (a travelling timeline), its node popping onto the
        track, its stem growing out and its date and words coming in along it."""
        if not any(mark is x for x in self.stage_pending) and any(mark is x for x in self.stage_extra):
            return None                                  # already on
        node, stem, head = mark.submobjects[:3]
        self.stage_pending = [x for x in self.stage_pending if x is not mark]
        self.stage_extra.append(mark)
        out = node.get_center() - head.get_center()
        steps = []
        if marker is not None:
            steps.append(marker.animate.move_to(node.get_center()))
        steps += [GrowFromCenter(node), Create(stem), FadeIn(head, shift=out / max(np.linalg.norm(out), 1e-6) * 0.25)]
        anim = LaggedStart(*steps, lag_ratio=0.45)
        anim.panim_run = 0.9
        return anim

    # ---------------- several pictures at once, and diagrams built on the stage ----------------
    # ---------------- a gallery: several pictures, each brought forward as it is said ----------------
    # Spotlight (the default): one picture large, every picture as a thumbnail in a strip beneath it, a ring on the
    # one in the spotlight. As the narration names the next picture it slides into the spotlight (the one before
    # slides out the other way), its caption is written under it and the ring glides along the strip; a later line
    # that names one brings it back. Grid: the pictures side by side, each popping in as it is named, the ring on the
    # one being talked about.
    GALLERY_MOST = 6

    def gallery(self, items, title: str | None = None, layout: str | None = None):
        """items: [(path, caption)] or [(path, caption, say)], `say` the words that bring each forward (its caption
        by default). layout: "spotlight" or "grid" (two to four pictures)."""
        items = [(str(i[0]), str(i[1] or "") if len(i) > 1 else "", str(i[2] or "") if len(i) > 2 else "")
                 for i in list(items)[:self.GALLERY_MOST] if i and i[0]]
        if not items:
            return None
        if len(items) == 1:
            return self.stage_image(items[0][0], items[0][1])
        if self.board_mode and self._solving() and not self._beat_new:
            self._log("skipped", what="gallery during a problem")
            return None
        layout = layout if layout in ("spotlight", "grid") else ("grid" if len(items) <= 2 else "spotlight")
        if layout == "grid" and len(items) > 4:
            layout = "spotlight"
        g = {"items": items, "layout": layout, "at": 0, "shown": {0}, "beat": self.__dict__.get("_sync_beat", 0)}
        cx, cy, w, h = self.STAGE
        head = None
        top = cy + h / 2
        if title:
            head = fit(T(title.upper() if TH["upper"] else title, 24, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4)
            head.move_to([cx, top - head.height / 2 - 0.05, 0])
            top = head.get_bottom()[1] - 0.25
        bottom = cy - h / 2
        if layout == "spotlight":
            self._gallery_spotlight(g, top, bottom)
        else:
            self._gallery_grid_layout(g, top, bottom)
        going = self._stage_leaving()
        card = self._stage_card()
        card.set_z_index(Z_MARK + 10)
        self.stage_items = Group(card)
        self.stage_body = card
        self._beat_new.append(card)
        self._gallery = g
        veils = g.get("veils") or []
        parts = [m for m in (head, *g["thumbs"], *veils[1:], g.get("ring")) if m is not None]
        for m in parts:
            self._stage_add(m)
        first = self._gallery_piece(g, 0)
        self._stage_add(first)
        arrivals = [FadeIn(card)]
        if head is not None:
            arrivals.append(FadeIn(head))
        if g["thumbs"]:
            arrivals.append(LaggedStart(*[FadeIn(t, shift=UP * 0.15) for t in g["thumbs"]], lag_ratio=0.15))
            arrivals.append(AnimationGroup(*[FadeIn(v) for v in veils[1:]]))
        arrivals.append(FadeIn(first, shift=UP * 0.2))
        if g.get("ring") is not None:
            arrivals.append(FadeIn(g["ring"]))
        show = LaggedStart(*arrivals, lag_ratio=0.3)
        show.run_time = 1.6
        show.panim_run = 1.6
        show.panim_sfx = "whoosh"
        # Each other picture comes forward as it is said: in this line by the queue (each step built in the order
        # they play, from where the one before left the gallery), in a later line by its name (name_part). One never
        # said waits in the strip (in a grid, off until it is said).
        for k in range(1, len(items)):
            self.queue_on_words(self._gallery_say(g, k), lambda heard, k=k: self._gallery_step(g, k) if heard else None)
        for k in range(len(items)):
            self.name_part(self._gallery_say(g, k), g["thumbs"][k] if g["thumbs"] else g["cells"][k],
                           shown=lambda k=k: self.__dict__.get("_gallery") is g and g["at"] != k
                           and self.__dict__.get("_sync_beat", 0) != g["beat"],
                           act=lambda k=k: self._gallery_step(g, k))
        if not going:
            return show
        both = AnimationGroup(AnimationGroup(*going, run_time=0.4), show, lag_ratio=1.0)
        both.panim_run = 2.0
        return both

    @staticmethod
    def _gallery_say(g, k: int) -> str:
        path, caption, say = g["items"][k]
        return say or caption or Path(path).stem.replace("_", " ")

    def _gallery_framed(self, path: str, width: float, height: float):
        """A gallery's picture at most width x height: a photo in its frame (photo_frame), a cutout as it is."""
        if is_cutout(path):
            return Group(cutout_mob(path, width, height))
        image = ImageMobject(trimmed(path))
        image.scale_to_fit_height(height)
        if image.width > width:
            image.scale_to_fit_width(width)
        depth, over = photo_frame(self, image, radius=0.12)
        over.set_z_index(Z_MARK + 11.5)
        for part in over.get_family():
            part._panim_z = Z_MARK + 11.5
        return Group(depth, image, over)

    def _gallery_spotlight(self, g, top: float, bottom: float) -> None:
        cx, cy, w, h = self.STAGE
        n = len(g["items"])
        strip_h = max(0.55, min(0.95, (top - bottom) * 0.17))
        gap = 0.18
        thumbs = []
        for path, _, _ in g["items"]:
            thumb = self._gallery_framed(path, strip_h * 1.8, strip_h)
            thumbs.append(thumb)
        row = Group(*thumbs).arrange(RIGHT, buff=gap)
        if row.width > w - 0.4:
            row.scale_to_fit_width(w - 0.4)
        row.move_to([cx, bottom + row.height / 2 + 0.05, 0])
        caption_room = 0.5
        hero_top, hero_bottom = top, row.get_top()[1] + 0.3 + caption_room
        g.update(thumbs=thumbs, hero_box=(cx, (hero_top + hero_bottom) / 2, w, hero_top - hero_bottom),
                 caption_y=hero_bottom - caption_room / 2 - 0.05, heroes={}, captions={})
        ring = hud_frame(thumbs[0].width + 0.16, thumbs[0].height + 0.16, P.GOLD, stroke=3.2).move_to(thumbs[0])
        ring.set_z_index(Z_LABEL - 0.5)
        g["ring"] = ring
        # The strip's others dimmed a little under a veil of the board's colour (the phone draws a picture's
        # opacity only as it fades in or out): the one in the spotlight is clear.
        g["veils"] = []
        for t in thumbs:
            veil = _flat(RoundedRectangle(corner_radius=0.08, width=t.width, height=t.height, fill_color=P.BG,
                                          fill_opacity=0.45, stroke_width=0)).move_to(t)
            veil.set_z_index(Z_MARK + 11.8)
            g["veils"].append(veil)

    def _gallery_grid_layout(self, g, top: float, bottom: float) -> None:
        cx, cy, w, h = self.STAGE
        items = g["items"]
        room = top - bottom
        rows, cols = self._gallery_grid([self._aspect(p) for p, _, _ in items], w, room)
        cell_w = (w - 0.3 * (cols - 1)) / cols
        cell_h = (room - 0.35 * (rows - 1)) / rows - 0.45
        cells = []
        for path, caption, _ in items:
            pic = self._gallery_framed(path, cell_w, cell_h)
            parts = [pic]
            if caption:
                parts.append(fit(T(wrap(caption, 26), 15, P.CREAM, line_spacing=0.85), cell_w)
                             .next_to(pic, DOWN, buff=0.12))
            cells.append(Group(*parts))
        grid = Group(*cells).arrange_in_grid(rows=rows, cols=cols, buff=(0.3, 0.35))
        if len(cells) == 3 and rows == 2:
            cells[2].set_x(grid.get_center()[0])
        if grid.height > room:
            grid.scale_to_fit_height(room)
        grid.move_to([cx, (top + bottom) / 2, 0])
        g.update(cells=cells, thumbs=[])
        first = cells[0][0]
        ring = hud_frame(first.width + 0.18, first.height + 0.18, P.GOLD, stroke=3.2).move_to(first)
        ring.set_z_index(Z_LABEL - 0.5)
        g["ring"] = ring

    def _gallery_piece(self, g, k: int):
        """What comes on for picture k: in the spotlight, the picture large with its caption under it (made once);
        in a grid, its cell."""
        if g["layout"] == "grid":
            return g["cells"][k]
        if k not in g["heroes"]:
            path, caption, _ = g["items"][k]
            hx, hy, hw, hh = g["hero_box"]
            hero = self._gallery_framed(path, hw, hh)
            hero.move_to([hx, hy, 0])
            if drifts_on():
                set_drift([hero], dict(PICTURE_DRIFT, cx=hx, cy=hy))
            parts = [hero]
            if caption:
                chip = ui_chip(_short_caption(caption, 60), size=17)
                chip.move_to([hx, g["caption_y"], 0])
                for part in chip.get_family():
                    part._panim_above = True
                parts.append(chip)
            g["heroes"][k] = Group(*parts)
        return g["heroes"][k]

    def _gallery_step(self, g, k: int):
        """Bring picture k forward: the one in the spotlight slides out, k slides in (from the side it sits on in
        the strip), the ring glides to it. In a grid: k pops in if it is not up yet, and the ring moves to it."""
        if self.__dict__.get("_gallery") is not g or g["at"] == k:
            return None
        before, g["at"] = g["at"], k
        g["shown"].add(k)
        moves = []
        ring = g.get("ring")
        if g["layout"] == "grid":
            cell = g["cells"][k]
            if all(cell is not m for m in self.stage_extra):
                self._stage_add(cell)
                moves.append(FadeIn(cell, shift=UP * 0.2))
            target = cell[0]
        else:
            way = RIGHT if k > before else LEFT
            old = g["heroes"].get(before)
            new = self._gallery_piece(g, k)
            if old is not None and any(old is m for m in self.stage_extra):
                self.stage_extra.remove(old)
                moves.append(FadeOut(old, shift=-way * 1.2, rate_func=rush_into, run_time=0.45))
            self._stage_add(new)
            moves.append(FadeIn(new, shift=-way * 1.2, rate_func=ease_out_expo, run_time=0.6))
            target = g["thumbs"][k]
            # The strip: the one that was in the spotlight dims, this one clears.
            veils = g["veils"]
            if any(veils[k] is m for m in self.stage_extra):
                self.stage_extra.remove(veils[k])
                moves.append(FadeOut(veils[k], run_time=0.4))
            if all(veils[before] is not m for m in self.stage_extra):
                moves.append(FadeIn(self._stage_add(veils[before]), run_time=0.4))
        if ring is not None:
            import stem

            moves.append(stem._moving(ring.animate(rate_func=ease_out_expo).move_to(target)))
        anim = AnimationGroup(*moves)
        anim.run_time = 0.7
        anim.panim_run = 0.7
        anim.panim_sfx = "whoosh"
        return anim

    @staticmethod
    def _aspect(path: str) -> float:
        """A picture's width over its height (1 when it cannot be read)."""
        try:
            mob = cutout_mob(path, 4.0, 4.0) if is_cutout(path) else ImageMobject(path)
            return max(0.2, min(5.0, mob.width / max(mob.height, 1e-6)))
        except Exception:  # noqa: BLE001
            return 1.0

    @staticmethod
    def _gallery_grid(aspects: list[float], width: float, height: float) -> tuple[int, int]:
        """(rows, cols) for pictures of these shapes in a width x height box: the grid in which they come out
        largest (three tall portraits side by side in one row; four wide scenes two by two)."""
        n = len(aspects)
        if n <= 1:
            return 1, 1
        best = None
        for rows in range(1, n + 1):
            cols = -(-n // rows)
            if (rows - 1) * cols >= n:
                continue
            cell_w = (width - 0.3 * (cols - 1)) / cols
            cell_h = (height - 0.35 * (rows - 1)) / rows - 0.45
            if cell_w <= 0 or cell_h <= 0:
                continue
            # The area each picture gets, fitted to its cell; the smallest counts double, so none is left tiny.
            areas = []
            for a in aspects:
                pic_h = min(cell_h, cell_w / a)
                areas.append(pic_h * pic_h * a)
            score = sum(areas) + min(areas)
            if best is None or score > best[0]:
                best = (score, rows, cols)
        return (best[1], best[2]) if best else (1, n)

    def _picture(self, spec, height: float, width: float | None = None, motion: str | None = None):
        """A picture beside words in a diagram's node, a timeline's event or a map's label, at most height x width:
        spec is (kind, value) as the compiler resolved it -- ("image", a picture or figure file), ("entity", the name
        of a thing, made by the illustration model). None when it cannot be drawn (the words carry on alone)."""
        if not spec:
            return None
        kind, value = str(spec[0]), spec[1]
        width = width or height * 1.6
        try:
            if kind == "entity":
                return self._entity(str(value), height, motion)
            if kind == "cutout" or (kind == "image" and is_cutout(value)):
                return cutout_mob(str(value), width, height)
            if kind == "image":
                image = ImageMobject(trimmed(str(value)))
                image._panim_src = trimmed(str(value))
                image.scale_to_fit_height(height)
                if image.width > width:
                    image.scale_to_fit_width(width)
                # A hairline, softly rounded edge (it may sit on a card, so its corners are not masked).
                edge = _flat(RoundedRectangle(corner_radius=min(0.08, image.height / 6), width=image.width,
                                              height=image.height, stroke_color=_tint_on_bg(P.CREAM, 0.4),
                                              stroke_width=1.4, fill_opacity=0).move_to(image))
                return Group(image, edge)
        except Exception as error:  # noqa: BLE001 -- a picture that will not draw leaves its words alone
            skipped(f"a picture {value!r} left out: {type(error).__name__}: {error}"[:300])
        return None

    # A node's motion (its `anim`, or the diagram's `animate` choice) as a picture's move (PICTURE_MOVES).
    NODE_MOVES = {"bob": "bob", "hop": "bob", "sway": "sway", "shake": "sway", "flicker": "sway", "spin": "sway",
                  "pulse": "breathe", "breathe": "breathe", "drift": "drift"}

    def _entity(self, name: str | None, height: float, motion: str | None = None):
        """The picture of what a diagram's node stands for (a tree, a factory, a cow), made by the illustration
        model, or None. With a motion (NODE_MOVES) it moves while its diagram is up (_diagram_moves)."""
        if not name:
            return None
        try:
            mob = sketch_mob(str(name), height=height)
        except Exception:  # noqa: BLE001 -- no picture of it (no image model, refused): the label carries the node
            return None
        move = self.NODE_MOVES.get(str(motion or ""))
        if move:
            mob._panim_move = move
        return mob

    def _node(self, label: str, entity: str | None, tone: str, small: bool = False, items=None, number=None,
              motion: str | None = None, picture=None, role: str | None = None):
        """A diagram's node, as drawn on a board: the thing's drawing above its name in an outlined box; or, for a
        diagram of words (categories, steps), a card in a flat colour with its name, a number, and its items.

        `role` says what it stands for, and so how it looks: a person (a portrait in a round frame, a rounded card),
        a place (a pin before its name), an event (a square tag with a bar of colour), an idea (a soft card)."""
        role = str(role or "").strip().lower() or None
        drawing = self._entity(entity, 1.0 if small else 1.35, motion)
        if drawing is None and picture:
            # A photo, a book figure or a drawing of the thing (the compiler fetched or drew it): large enough to
            # see what it is, not an icon.
            drawing = self._picture(picture, 1.5 if small else 2.0, motion=motion)
        items = [str(i) for i in (items or [])][:5]
        if drawing is not None:
            return self._picture_node(drawing, label, tone, small, items, number)
        words_only = drawing is None
        size = (19 if small else 23) + (2 if words_only and not items else 0)
        text = marker(wrap(str(label), 14 if words_only else 12), size)
        if role == "place":
            # A map pin before a place's name.
            pin = VGroup(Triangle(fill_color=tone, fill_opacity=1, stroke_width=0).scale(0.13).rotate(PI),
                         Circle(radius=0.11, fill_color=tone, fill_opacity=1, stroke_color=P.CREAM, stroke_width=1.5))
            pin[1].next_to(pin[0], UP, buff=-0.06)
            text = VGroup(pin, text).arrange(RIGHT, buff=0.12)
        if drawing is not None and not items and number is None and role is None:
            # A thing as a teacher draws it: the drawing, its name in capitals under it, no box.
            node = group_of(drawing, text).arrange(DOWN, buff=0.18)
            node.is_drawing = True
            return node
        parts = [drawing] if drawing is not None else []
        head = text
        if number is not None:
            badge = VGroup(Circle(radius=0.2, fill_color=tone, fill_opacity=1, stroke_color=P.CREAM, stroke_width=2),
                           T(str(number), 15, P.BG, weight=BOLD))
            badge[1].move_to(badge[0])
            head = VGroup(badge, text).arrange(RIGHT, buff=0.15)
        parts.append(head)
        if items:
            rule = Line(LEFT, RIGHT, stroke_color=tone, stroke_width=2)
            lines = VGroup(*[T("• " + wrap(i, 22), 17 if small else 19, P.CREAM, line_spacing=0.88) for i in items])
            lines.arrange(DOWN, aligned_edge=LEFT, buff=0.08)
            rule.set_width(max(lines.width, head.width))
            parts += [rule, lines]
        inner = group_of(*parts).arrange(DOWN, buff=0.14)
        if items:
            inner[-1].align_to(inner[-2], LEFT)
        # Words alone sit on a card of flat colour, like a marker-filled box; a drawing keeps a light one.
        look = marker_card_style(role)
        box = RoundedRectangle(corner_radius=min(look["corner_radius"], (inner.height + 0.4) / 2 - 0.01),
                               width=max(inner.width + 0.45, 1.8), height=inner.height + 0.4,
                               stroke_color=P.CREAM, stroke_width=OUTLINE * 0.8,
                               fill_color=_tint_on_bg(tone, 0.45), fill_opacity=1)
        if role == "event":
            # An event's tag: a bar of its colour down the left.
            bar = Rectangle(width=0.16, height=box.height, fill_color=tone, fill_opacity=1, stroke_width=0)
            bar.align_to(box, LEFT)
            return group_of(box, bar, inner.move_to(box).shift(RIGHT * 0.08))
        return group_of(box, inner.move_to(box))

    def _picture_node(self, picture, label: str, tone: str, small: bool = False, items=(), number=None):
        """A diagram's step that is a picture: the picture on a soft disc of the step's colour with a ring round it
        (a photograph cut round to fit it), its name in bold under it, its few points under that in a quieter
        colour. No card round it."""
        images = [m for m in picture.get_family() if isinstance(m, ImageMobject)]
        if len(images) == 1 and not has_alpha(getattr(images[0], "_panim_src", "") or "") and \
                getattr(images[0], "_panim_src", None):
            # A photograph, cut round.
            round_src = circle_cut(images[0]._panim_src)
            if round_src:
                cut = ImageMobject(round_src)
                cut.scale_to_fit_height(min(picture.height, picture.width))
                cut.move_to(picture)
                picture = cut
        radius = max(picture.width, picture.height) / 2 + (0.14 if small else 0.2)
        disc = _flat(Circle(radius=radius, fill_color=tone, fill_opacity=0.16, stroke_color=tone, stroke_width=3))
        disc.move_to(picture)
        head = T(f"{number}. {label}" if number is not None else str(label), 19 if small else 22, P.CREAM,
                 weight=BOLD)
        head = fit(head, max(2 * radius + 0.8, 2.4))
        parts = [disc, picture, head]
        lines = None
        if items:
            lines = VGroup(*[fit(T(str(i), 15 if small else 17, P.MUTED), max(2 * radius + 0.6, 2.2))
                             for i in items]).arrange(DOWN, buff=0.06)
            parts.append(lines)
        head.next_to(disc, DOWN, buff=0.16)
        if lines is not None:
            lines.next_to(head, DOWN, buff=0.08)
        node = group_of(*parts)
        node.is_drawing = True
        return node

    def diagram(self, key: str, kind: str, nodes, edges=(), title: str | None = None, show=None,
                animate: bool = True, flow: bool | None = None, numbered: bool = False):
        """A diagram built on the stage: nodes (a picture of each thing, made by the illustration model, and its
        name) joined by arrows.

        kind: flow, cycle (round) or hub (the first node in the middle, the rest around it). A flow takes its
        layout from its connections: a chain (in order, left to right, wrapping), a hierarchy (edges that only
        branch downwards from one top: the whole on top, its kinds below, theirs below them: _hierarchy; a
        category's card lists its items) or a flowchart (branches, joins, loops, shapes or lanes: _flowchart).
        `numbered` numbers a chain's cards (steps). The older kinds still work: tree, hierarchy and categories
        (a hierarchy, the first node over the rest when there are no edges), flowchart, steps (numbered).
        nodes: [{id, label, entity?, items?}]: entity is a thing to picture (a tree, a factory); items are short lines
        listed in the node (a category's members). edges: [[from, to, label?]] (a flow, cycle or steps without
        edges joins its nodes in order; categories join the first node to the rest). `show` is the node ids to
        draw now (default all); `reveal_nodes` brings in the rest, a beat at a time. Everything is written in as
        on a whiteboard: outlines first, then their colours.

        Moving pictures: a node's "anim" (bob, sway, breathe, drift, and the older names NODE_MOVES reads) sets its
        picture moving for as long as the diagram is up; with `flow` (a flow or cycle by default) dots run along
        the arrows, the way the process goes."""
        cx, cy, w, h = self.STAGE
        nodes = [dict(n) for n in list(nodes)[:20]]
        ids = [str(n["id"]) for n in nodes]
        # Its parts by their names, to point at as the narration says them (beat, _pointers).
        self.__dict__.setdefault("_diagram_labels", {})[key] = {str(n["id"]): str(n.get("label") or n["id"])
                                                                for n in nodes}
        edges = [list(e) for e in edges or []]
        import hierarchy as _hier

        if kind == "steps":
            kind, numbered = "flow", True
        if kind == "pyramid":
            return self._pyramid(key, nodes[:7], title, show)
        # Words on the arrows ("includes") keep a hierarchy a hierarchy: the tree layout writes them on its
        # connectors.
        plain = not any(n.get("shape") or n.get("lane") for n in nodes)
        if kind == "hub" and plain and len(ids) > 2:
            # The thing all the others hang from goes on top, the others below it (a hub drawn with its centre in the
            # middle and the rest around it read as no order at all).
            hub_edges = edges or [[ids[0], i] for i in ids[1:]]
            if _hier.is_tree(ids, hub_edges):
                kind, edges = "tree", hub_edges
        if kind in ("tree", "categories", "hierarchy") or (kind == "flow" and plain and _hier.is_tree(ids, edges)):
            # A whole above its kinds, each above its own kinds (hierarchy.py): the main thing on top.
            nodes, ids = nodes[:20], ids[:20]
            if not edges:
                edges = [[ids[0], i] for i in ids[1:]]
            return self._hierarchy(key, nodes, edges, title, show, animate, bool(flow))
        nodes, ids = nodes[:16], ids[:16]
        # Words on the arrows alone do not make a flowchart: a chain with labelled arrows is laid out in rows that
        # wrap (each step large), not in one long line of ranks that shrinks every box to fit.
        shaped = any(n.get("shape") or n.get("lane") for n in nodes)
        if kind == "flowchart" or (kind == "flow" and (shaped or len(ids) > 9
                                                       or (edges and self._branching(ids, edges)))):
            # Branches, joins, decisions and loops (or more steps than a row of boxes holds): laid out as a
            # flowchart (flowchart.py).
            if not edges:
                edges = [[a, b] for a, b in zip(ids, ids[1:])]
            return self._flowchart(key, nodes, edges, title, show, animate, True if flow is None else bool(flow))
        nodes = nodes[:9]
        ids = ids[:9]
        if not edges and kind in ("flow", "cycle"):
            edges = [[a, b] for a, b in zip(ids, ids[1:])] + ([[ids[-1], ids[0]]] if kind == "cycle" and len(ids) > 2 else [])
        tones = [P.SAND, P.RIVER, P.GREEN, P.ROSE, P.GOLD, P.TEAL, P.VIOLET, P.DUNE]
        small = len(nodes) > 5
        flow = kind in ("flow", "cycle") if flow is None else bool(flow)
        mobs = {i: self._node(n.get("label", i), n.get("entity"), tones[k % 8], small, items=n.get("items"),
                              picture=n.get("picture"),
                              number=k + 1 if numbered else None,
                              motion=(n.get("anim") or "auto") if animate else "none", role=n.get("kind"))
                for k, (i, n) in enumerate(zip(ids, nodes))}
        # Layout.
        if kind == "cycle":
            radius = 1.7 + 0.12 * len(ids)
            for k, i in enumerate(ids):
                angle = PI / 2 - 2 * PI * k / len(ids)
                mobs[i].move_to([radius * 1.15 * math.cos(angle), radius * 0.8 * math.sin(angle), 0])
        elif kind == "hub":
            # The thing at the centre, drawn biggest; the rest at its sides, as a board is wider than it is tall.
            if getattr(mobs[ids[0]], "is_drawing", False):
                centre = mobs[ids[0]]
                centre[0].scale(1.6)
                centre.arrange(DOWN, buff=0.18)                 # the drawing grows; its name stays the same size
            mobs[ids[0]].move_to(ORIGIN)
            ring = ids[1:]
            sides = [150, 30, 210, 330, 90, 270, 180, 0]
            for k, i in enumerate(ring):
                angle = math.radians(sides[k % len(sides)])
                mobs[i].move_to([4.2 * math.cos(angle), 2.2 * math.sin(angle), 0])
            if not edges:
                edges = [[ids[0], i] for i in ring]
        else:                                                           # flow
            # As many to a row as the stage is wide for: three on the whole frame, two beside a panel.
            most = 3 if w >= 9 else 2
            per_row = max(len(ids), 1) if len(ids) <= most else (most if len(ids) > 4 or most == 2 else 2)
            rows = [Group(*[mobs[i] for i in ids[r:r + per_row]]).arrange(
                RIGHT if (r // per_row) % 2 == 0 else LEFT, buff=0.8) for r in range(0, len(ids), per_row)]
            Group(*rows).arrange(DOWN, buff=0.7)
        self._room_for_arrows(mobs, edges)
        arrows = []
        for e in edges:
            a, b = str(e[0]), str(e[1])
            if a not in mobs or b not in mobs:
                continue
            start, end = self._edge_points(mobs[a], mobs[b])
            arrow = self._clear_arrow(mobs[a], mobs[b], [m for k, m in mobs.items() if k not in (a, b)])
            look = edge_look(e[3] if len(e) > 3 else "")
            if look == "bold":
                arrow.set_stroke(P.HI, width=OUTLINE * 2.2)
                for tip in arrow.get_tips() if hasattr(arrow, "get_tips") else []:
                    tip.set_fill(P.HI)
                for part in arrow.get_family():
                    part._art_keep_width = True
            guide = arrow
            if look == "dashed":
                # Dashed along its line, its head kept whole; the solid line stays as the guide its words and its
                # moving dots follow, unseen.
                guide = arrow.copy()
                tips = arrow.pop_tips() if hasattr(arrow, "pop_tips") else VGroup()
                arrow = VGroup(DashedVMobject(arrow, num_dashes=max(6, int(arrow.get_arc_length() / 0.2)),
                                              dashed_ratio=0.6), *tips)
            label = None
            if len(e) > 2 and e[2]:
                label = marker(str(e[2]), 17)
                along = end - start
                # Beside the arrow: above a level one, to the right of a steep one.
                side = np.array([0, 0.22, 0]) if abs(along[0]) >= abs(along[1]) else np.array([label.width / 2 + 0.15, 0, 0])
                label.move_to(guide.point_from_proportion(0.5) + side)
                label.is_label = True         # stem._settle_labels moves it off another arrow or a node
            edge = VGroup(arrow, *([label] if label else []))
            if flow and guide.get_arc_length() > 0.55:          # (before the fit to the stage, about x1.5)
                edge.flow = self._flow_dots(guide)
                edge.add(edge.flow)
            arrows.append((a, b, edge))
        legend = edge_legend([e[3] for e in edges if len(e) > 3])
        if legend is not None:
            # The key to what the arrows mean, under the diagram.
            body = Group(*mobs.values(), *[m for _, _, m in arrows])
            legend.next_to(body, DOWN, buff=0.45)
        return self._diagram_finish(key, ids, mobs, arrows, edges, title, show, backdrop=legend)

    # ------------------------------------------------------------------ pyramids

    def _pyramid(self, key, nodes, title, show):
        """Ranks as a pyramid, the first at the narrow top and each below it wider (the three orders, feudal ranks,
        a food pyramid): each a band of its own colour with its name, its items beside it, and its picture at
        its side when it has one. Bands are revealed like a diagram's nodes."""
        cx, cy, w, h = self.STAGE
        n = max(len(nodes), 1)
        tones = [P.GOLD, P.ROSE, P.RIVER, P.GREEN, P.SAND, P.TEAL, P.VIOLET]
        band_h = min(1.25, (h - (1.0 if title else 0.4)) / n - 0.08)
        top_w, base_w = min(2.4, w * 0.25), min(w * 0.72, 8.6)
        mobs, ids = {}, []
        for k, node in enumerate(nodes):
            i = str(node["id"])
            ids.append(i)
            upper = top_w + (base_w - top_w) * k / n
            lower = top_w + (base_w - top_w) * (k + 1) / n
            y = -k * (band_h + 0.08)
            band = Polygon([-upper / 2, y + band_h / 2, 0], [upper / 2, y + band_h / 2, 0],
                           [lower / 2, y - band_h / 2, 0], [-lower / 2, y - band_h / 2, 0],
                           fill_color=_tint_on_bg(tones[k % len(tones)], 0.5), fill_opacity=1,
                           stroke_color=P.CREAM, stroke_width=OUTLINE * 0.8)
            name = fit(marker(str(node.get("label", i)), 24 if n <= 4 else 20), upper * 0.9 if k else upper * 0.95)
            name.move_to(band.get_center())
            parts = [band, name]
            items = [str(x) for x in node.get("items") or []][:3]
            if items:
                side = T(" · ".join(items), 20, P.CREAM)
                side = fit(side, max(1.6, (w - lower) / 2 - 0.3))
                side.next_to(band, RIGHT, buff=0.25)
                parts.append(side)
            if node.get("picture"):
                pic = self._picture(node["picture"], band_h * 0.95)
                if pic is not None:
                    pic.next_to(band, LEFT, buff=0.25)
                    parts.append(pic)
            mobs[i] = group_of(*parts)
        return self._diagram_finish(key, ids, mobs, [], [], title, show)

    # ------------------------------------------------------------------ hierarchies

    def _hierarchy(self, key, nodes, edges, title, show, animate, flow):
        """A classification drawn as a tree (hierarchy.py lays it out): the whole at the top, its kinds in a row
        below it, each over its own kinds, down to the last; leaves stacked in columns when a row would be too
        wide. Each child is joined straight up to a bar it shares with its siblings and on into its parent, where
        an open triangle marks "is a kind of". Each branch of the top keeps one colour all the way down."""
        import hierarchy as hi

        cx, cy, w, h = self.STAGE
        ids = [str(n["id"]) for n in nodes]
        roots, children, parent = hi.structure(ids, edges)
        many = len(ids) > 9
        tones = [P.SAND, P.RIVER, P.GREEN, P.ROSE, P.GOLD, P.TEAL, P.VIOLET, P.DUNE]
        branch = {}
        for r in roots:
            branch[r] = 0
            for k, c in enumerate(children[r]):
                stack = [c]
                while stack:
                    v = stack.pop()
                    branch[v] = 1 + k % (len(tones) - 1)
                    stack.extend(children[v])
        mobs = {}
        for n in nodes:
            i = str(n["id"])
            mobs[i] = self._node(n.get("label", i), n.get("entity"), tones[branch.get(i, 0)], many, items=n.get("items"),
                                 picture=n.get("picture"),
                                 motion=(n.get("anim") or "auto") if animate else "none", role=n.get("kind"))
        sizes = {i: (m.width, m.height) for i, m in mobs.items()}
        lay = hi.layout(ids, edges, sizes, board=(w - 0.3, h - (0.9 if title else 0.3)))
        for i, (x, y) in lay.centres.items():
            mobs[i].move_to([x, y, 0])
        line = dict(stroke_color=P.CREAM, stroke_width=OUTLINE * 0.75)
        labels = {(str(e[0]), str(e[1])): str(e[2]) for e in edges if len(e) > 2 and e[2]}
        built = []
        for p, c, pts in lay.connectors:
            path = VMobject(**line).set_fill(opacity=0)
            path.set_points_as_corners([[x, y, 0] for x, y in pts])
            jx, jy = lay.joins[p]
            t = 0.2
            mark = Polygon([jx, jy, 0], [jx - t * 0.6, jy - t, 0], [jx + t * 0.6, jy - t, 0], fill_color=P.BG,
                           fill_opacity=1, **line)
            parts = [path, mark]
            if (p, c) in labels:
                tag = marker(labels[(p, c)], 17)
                x0, y0 = pts[0]
                tag.next_to([x0, y0, 0], UP, buff=0.08).shift(RIGHT * (tag.width / 2 + 0.1))
                tag.is_label = True
                parts.append(tag)
            edge = VGroup(*parts)
            edge.path = path
            if flow and path.get_arc_length() > 0.7:
                edge.flow = self._flow_dots(path)
                edge.add(edge.flow)
            built.append((p, c, edge))
        return self._diagram_finish(key, ids, mobs, built, edges, title, show)

    # ------------------------------------------------------------------ flowcharts

    FLOW_SHAPES = ("process", "decision", "start", "end", "io", "store", "note")
    FLOW_TONES = {"start": "GREEN", "end": "ROSE", "decision": "GOLD", "process": "RIVER", "io": "VIOLET",
                  "store": "TEAL", "note": "MUTED"}

    def _flow_node(self, label: str, shape: str, tone: str, size: float, width: float | None = None,
                   entity: str | None = None, motion: str | None = None, picture=None):
        """A flowchart's step, in the shape a flowchart gives it: a rounded box for a process, a diamond for a
        decision, a pill for start and end, a slanted box for what goes in or comes out, a drum for a store, a
        folded note. Its name is written inside; a step with an entity has its drawing beside the name."""
        text = marker(wrap(str(label), 12 if shape == "decision" else 14), size)
        inner = text
        drawing = self._entity(entity, 0.75, motion) if entity else None
        if drawing is None and picture and shape in ("process", "start", "end", "", None):
            # A step that is a photograph: the picture, its name on a chip over its foot (the box's shape is for
            # words).
            photo = self._picture(picture, 1.3, 1.6, motion)
            if photo is not None and has_image(photo):
                node = self._picture_node(photo, label, tone, small=True)
                node.flow_shape = shape
                return node
        if drawing is None and picture:
            drawing = self._picture(picture, 0.9, 1.4, motion)
        if drawing is not None:
            inner = group_of(drawing, text).arrange(RIGHT, buff=0.15)
        fill = _tint_on_bg(tone, 0.4)
        line = dict(stroke_color=tone, stroke_width=OUTLINE * 0.75, fill_color=fill, fill_opacity=1)
        w = max(inner.width + 0.55, width or 0)
        hgt = inner.height + 0.42
        if shape == "decision":
            dw, dh = max(inner.width * 1.5 + 0.7, 2.0), max(inner.height * 1.7 + 0.6, 1.25)
            frame = Polygon([0, dh / 2, 0], [dw / 2, 0, 0], [0, -dh / 2, 0], [-dw / 2, 0, 0], **line)
        elif shape in ("start", "end"):
            frame = RoundedRectangle(corner_radius=hgt / 2, width=w + 0.25, height=hgt, **line)
        elif shape == "io":
            slant = 0.28
            frame = Polygon([-w / 2 + slant, hgt / 2, 0], [w / 2 + slant, hgt / 2, 0], [w / 2 - slant, -hgt / 2, 0],
                            [-w / 2 - slant, -hgt / 2, 0], **line)
        elif shape == "store":
            hgt += 0.25
            k = np.linspace(0, np.pi, 17)
            rx, ry = w / 2, 0.16
            front = [[-rx * np.cos(t), -hgt / 2 + 0.1 - ry * np.sin(t), 0] for t in k]   # bottom, the near half
            outline = [[-rx, hgt / 2 - 0.1, 0], *front, [rx, hgt / 2 - 0.1, 0]]
            outline += [[rx * np.cos(t), hgt / 2 - 0.1 + ry * np.sin(t), 0] for t in k]   # top, the far half
            body = Polygon(*outline, **line)
            lid = Ellipse(width=2 * rx, height=2 * ry, **{**line, "fill_color": _tint_on_bg(tone, 0.6)})
            lid.move_to([0, hgt / 2 - 0.1, 0])
            frame = VGroup(body, lid)
            inner.shift(DOWN * 0.08)
        elif shape == "note":
            fold = 0.25
            frame = Polygon([-w / 2, hgt / 2, 0], [w / 2 - fold, hgt / 2, 0], [w / 2, hgt / 2 - fold, 0],
                            [w / 2, -hgt / 2, 0], [-w / 2, -hgt / 2, 0], **{**line, "stroke_width": OUTLINE * 0.5})
            ear = Polygon([w / 2 - fold, hgt / 2, 0], [w / 2 - fold, hgt / 2 - fold, 0], [w / 2, hgt / 2 - fold, 0],
                          **{**line, "fill_color": tone, "fill_opacity": 0.5, "stroke_width": OUTLINE * 0.4})
            frame = VGroup(frame, ear)
        else:
            frame = RoundedRectangle(corner_radius=0.16, width=w, height=hgt, **line)
        node = group_of(frame, inner.move_to(frame.get_center()))
        node.flow_shape = shape
        return node

    @staticmethod
    def _branching(ids, edges) -> bool:
        """A flow that is more than a chain: a step with two ways out or in, or an arrow back to an earlier one."""
        outs, ins = {}, {}
        for e in edges:
            a, b = str(e[0]), str(e[1])
            outs[a] = outs.get(a, 0) + 1
            ins[b] = ins.get(b, 0) + 1
            if a in ids and b in ids and ids.index(b) < ids.index(a):
                return True
        return any(v > 1 for v in outs.values()) or any(v > 1 for v in ins.values())

    def _flowchart(self, key, nodes, edges, title, show, animate, flow):
        """A flowchart (flowchart.py lays it out): steps in ranks that follow the flow, decisions with their
        labelled branches, loops drawn round the outside, lanes for who does what, curved connectors that leave
        and enter each box at their own places, and dots running the way the process goes."""
        import flowchart as fc

        ids = [str(n["id"]) for n in nodes]
        many = len(ids) > 9
        size = 16 if many else 19
        shapes = {}
        for k, n in enumerate(nodes):
            shape = str(n.get("shape") or "").lower()
            if shape not in self.FLOW_SHAPES:
                outs = sum(1 for e in edges if str(e[0]) == ids[k])
                asks = str(n.get("label", "")).strip().endswith("?")
                shape = ("decision" if asks and outs > 1
                         else "start" if k == 0 and not any(str(e[1]) == ids[k] for e in edges) and len(ids) > 3
                         else "end" if outs == 0 and len(ids) > 3 else "process")
            shapes[ids[k]] = shape
        tone_of = {i: getattr(P, self.FLOW_TONES[shapes[i]]) for i in ids}
        for n in nodes:
            if n.get("tone"):
                try:
                    tone_of[str(n["id"])] = role(str(n["tone"]))
                except KeyError:
                    pass
        # Boxes of a kind share a width: a chart of equal boxes reads as one thing.
        probe = {i: marker(wrap(str(n.get("label", i)), 14), size).width for i, n in zip(ids, nodes)}
        common = min(max([probe[i] for i in ids if shapes[i] in ("process", "io")] or [1.2]) + 0.55, 3.6)
        mobs = {}
        for i, n in zip(ids, nodes):
            mobs[i] = self._flow_node(n.get("label", i), shapes[i], tone_of[i], size,
                                      width=common if shapes[i] in ("process", "io", "store", "note") else None,
                                      entity=n.get("entity"), motion=(n.get("anim") or "auto") if animate else "none",
                                      picture=n.get("picture"))
        lanes = {str(n["id"]): str(n["lane"]) for n in nodes if n.get("lane")}
        # A step with two or more after it is a parent with its children: above them, always.
        outs = {}
        for e in edges:
            outs[str(e[0])] = outs.get(str(e[0]), 0) + 1
        branches = any(v > 1 for v in outs.values())
        lay = fc.layout(ids, [(str(e[0]), str(e[1])) for e in edges],
                        {i: (m.width, m.height) for i, m in mobs.items()}, lanes=lanes or None,
                        direction="down" if branches and not lanes else "auto",
                        board=(self.STAGE[2], self.STAGE[3] - (0.8 if title else 0.2)), gap_rank=0.95, gap_step=0.45)
        for i, (x, y) in lay.centres.items():
            mobs[i].move_to([x, y, 0])
        right = lay.direction == "right"
        ahead = np.array([1.0, 0, 0]) if right else np.array([0, -1.0, 0])
        across = np.array([0, -1.0, 0]) if right else np.array([1.0, 0, 0])

        def side(m, direction, offset=0.0):
            """The point on m's edge facing `direction`, `offset` along that edge."""
            c = m.get_center()
            if abs(direction[0]) > 0.5:
                return c + direction * m[0].width / 2 + np.array([0, offset, 0])
            return c + direction * m[0].height / 2 + np.array([offset, 0, 0])

        # Ports: arrows that leave or enter one side of a box are spread along it, in the order of the boxes
        # they go to or come from, so they never start on top of each other.
        style = {}
        labels = {}
        for e in edges:
            a, b = str(e[0]), str(e[1])
            if len(e) > 2 and e[2]:
                labels[(a, b)] = str(e[2])
            if len(e) > 3 and e[3]:
                style[(a, b)] = str(e[3])
        forward = [(a, b, way) for a, b, way, back in lay.routes if not back]
        backs = [(a, b) for a, b, way, back in lay.routes if back]
        across_of = (lambda pt: -pt[1]) if right else (lambda pt: pt[0])
        leaving, entering = {}, {}
        for a, b, way in forward:
            first = way[0] if way else lay.centres[b]
            last = way[-1] if way else lay.centres[a]
            leaving.setdefault(a, []).append((across_of(first), b))
            entering.setdefault(b, []).append((across_of(last), a))

        def spread(m, items, key):
            items.sort()
            n = len(items)
            length = (m[0].height if right else m[0].width) * (0.6 if getattr(m, "flow_shape", "") != "decision" else 0.0)
            out = {}
            for k, (_, other) in enumerate(items):
                t = (k + 0.5) / n - 0.5 if n > 1 else 0.0
                out[(other, key)] = t * length * (-1 if right else 1)
            return out

        port_out, port_in = {}, {}
        for a, items in leaving.items():
            port_out.update({(a, b): v for (b, _), v in spread(mobs[a], items, "o").items()})
        for b, items in entering.items():
            port_in.update({(a, b): v for (a, _), v in spread(mobs[b], items, "i").items()})

        def bezier_path(points, tangents):
            path = VMobject()
            path.set_points([points[0]])
            pts = []
            for (p, tp), (q, tq) in zip(zip(points, tangents), zip(points[1:], tangents[1:])):
                d = max(np.linalg.norm(q - p), 0.2) * 0.45
                pts += [p, p + tp * d, q - tq * d, q]
            path.points = np.array(pts, dtype=float)
            return path

        def tip_at(end, direction, colour):
            u = direction / (np.linalg.norm(direction) or 1)
            n = np.array([-u[1], u[0], 0])
            L, W = 0.24, 0.13
            return Polygon(end, end - u * L + n * W, end - u * L - n * W, stroke_width=0, fill_color=colour,
                           fill_opacity=1)

        arrows = []
        for a, b, way in forward:
            ma, mb = mobs[a], mobs[b]
            start_dir = ahead
            if getattr(ma, "flow_shape", "") == "decision" and len(leaving.get(a, [])) > 1:
                # A decision's branches leave from its corners: straight on, and up or down (left or right).
                rank = sorted(leaving[a])
                idx = [o for _, o in rank].index(b)
                mid = (len(rank) - 1) / 2
                if idx < mid:
                    start_dir = -across
                elif idx > mid:
                    start_dir = across
                if len(rank) == 2:
                    start_dir = ahead if idx == 0 else across
                start = side(ma, start_dir)
            else:
                start = side(ma, ahead, port_out.get((a, b), 0.0))
            end = side(mb, -ahead, port_in.get((a, b), 0.0))
            pts = [start] + [np.array([x, y, 0.0]) for x, y in way] + [end]
            tangents = [start_dir] + [ahead] * len(way) + [ahead]
            arrows.append((a, b, pts, tangents, False))
        lo = min(m.get_bottom()[1] for m in mobs.values()) if right else min(m.get_left()[0] for m in mobs.values())
        hi = max(m.get_top()[1] for m in mobs.values()) if right else max(m.get_right()[0] for m in mobs.values())
        for k, (a, b) in enumerate(backs):
            ma, mb = mobs[a], mobs[b]
            # A loop goes round the outside, on the side of the chart its two steps are nearer.
            middle = (lo + hi) / 2
            if right:
                low_side = (ma.get_center()[1] + mb.get_center()[1]) / 2 < middle
                out = np.array([0, -1.0, 0]) if low_side else np.array([0, 1.0, 0])
            else:
                low_side = (ma.get_center()[0] + mb.get_center()[0]) / 2 < middle
                out = np.array([-1.0, 0, 0]) if low_side else np.array([1.0, 0, 0])
            reach = 0.55 + 0.3 * k
            start = side(ma, out, 0.0)
            end = side(mb, out, 0.0)
            edge_line = (lo - reach) if low_side else (hi + reach)
            if right:
                far = np.array([0, edge_line, 0])
                p1, p2 = np.array([start[0], far[1], 0]), np.array([end[0], far[1], 0])
            else:
                far = np.array([edge_line, 0, 0])
                p1, p2 = np.array([far[0], start[1], 0]), np.array([far[0], end[1], 0])
            pts = [start, p1, p2, end]
            tangents = [out, (p2 - p1) / (np.linalg.norm(p2 - p1) or 1), (p2 - p1) / (np.linalg.norm(p2 - p1) or 1), -out]
            arrows.append((a, b, pts, tangents, True))

        built = []
        for a, b, pts, tangents, back in arrows:
            kind = edge_look(style.get((a, b), "")) if style.get((a, b)) else ""
            colour = P.SAND if back else (P.HI if kind == "bold" else P.CREAM)
            width = OUTLINE * (2.2 if kind == "bold" else 0.75)
            path = bezier_path(pts, tangents)
            path.set_stroke(colour, width=width).set_fill(opacity=0)
            path._art_keep_width = kind == "bold"
            seen = DashedVMobject(path, num_dashes=max(6, int(path.get_arc_length() / 0.18)), dashed_ratio=0.6) \
                if kind == "dashed" or back else path
            tip = tip_at(pts[-1], pts[-1] - path.points[-2], colour)
            parts = [seen, tip]
            label = None
            if (a, b) in labels:
                label = marker(labels[(a, b)], 17, P.GOLD if getattr(mobs[a], "flow_shape", "") == "decision" else None)
                spot = path.point_from_proportion(0.3 if getattr(mobs[a], "flow_shape", "") == "decision" else 0.5)
                label.move_to(spot + (np.array([0, 0.2, 0]) if abs((pts[-1] - pts[0])[0]) > abs((pts[-1] - pts[0])[1])
                                      else np.array([label.width / 2 + 0.12, 0, 0])))
                label.is_label = True
                parts.append(label)
            edge = VGroup(*parts)
            edge.path = path
            if flow and path.get_arc_length() > 0.7 and not back:
                edge.flow = self._flow_dots(path)
                edge.add(edge.flow)
            built.append((a, b, edge))

        backdrop = None
        if lay.lanes:
            all_nodes = Group(*mobs.values())
            bands = VGroup()
            for k, (name, b_lo, b_hi) in enumerate(lay.lanes):
                if right:
                    width = all_nodes.width + 1.6
                    band = RoundedRectangle(corner_radius=0.12, width=width, height=b_hi - b_lo,
                                            fill_color=P.MUTED, fill_opacity=0.06 if k % 2 else 0.12,
                                            stroke_color=P.MUTED, stroke_width=1.2, stroke_opacity=0.5)
                    band.move_to([all_nodes.get_center()[0] - 0.35, (b_lo + b_hi) / 2, 0])
                    tag = T(name.upper(), 14, P.MUTED, weight=BOLD).rotate(PI / 2)
                    tag.move_to([band.get_left()[0] + 0.25, band.get_center()[1], 0])
                else:
                    height = all_nodes.height + 1.2
                    band = RoundedRectangle(corner_radius=0.12, width=b_hi - b_lo, height=height,
                                            fill_color=P.MUTED, fill_opacity=0.06 if k % 2 else 0.12,
                                            stroke_color=P.MUTED, stroke_width=1.2, stroke_opacity=0.5)
                    band.move_to([(b_lo + b_hi) / 2, all_nodes.get_center()[1] + 0.25, 0])
                    tag = T(name.upper(), 14, P.MUTED, weight=BOLD)
                    tag.move_to([band.get_center()[0], band.get_top()[1] - 0.22, 0])
                bands.add(VGroup(band, tag))
            # A backdrop, not a thing: the art style colours it but gives it no sheen, hatching or glow.
            for part in bands.get_family():
                part._art_decorated = True
            backdrop = bands
        legend = edge_legend(style.values())
        if legend is not None:
            # The key to what the arrows mean, under the chart.
            chart = Group(*mobs.values(), *[m for _, _, m in built])
            legend.next_to(chart, DOWN, buff=0.45)
            backdrop = legend if backdrop is None else Group(backdrop, legend)
        return self._diagram_finish(key, ids, mobs, built, edges, title, show, backdrop=backdrop)

    def _diagram_finish(self, key, ids, mobs, arrows, edges, title, show, backdrop=None, settle: bool = True):
        """A diagram's last steps, for every kind: its arrows' words settled clear of the rest, its title, the
        whole fitted to the stage, and what shows now and what waits for a reveal."""
        cx, cy, w, h = self.STAGE
        whole = Group(*([backdrop] if backdrop is not None else []), *mobs.values(), *[m for _, _, m in arrows])
        if settle and any(len(e) > 2 and e[2] for e in edges):
            import stem

            # An arrow's words beside it, clear of the other arrows and the nodes they join (before the fit).
            stem._settle_labels([*mobs.values(), *[m for _, _, m in arrows]],
                                (whole.get_center()[0], whole.get_center()[1], whole.width + 0.6, whole.height + 0.6),
                                backing=P.BG)
        head = None
        if title:
            head = fit(T(title.upper() if TH["upper"] else title, 24, P.TITLE, font=TH["serif"], weight=BOLD), w - 0.4)
        # Fit the finished diagram to the stage, so revealing more never moves what is already there.
        room_h = h - (0.8 if head else 0.2)
        scale = min(1.45, (w - 0.3) / max(whole.width, 0.01), room_h / max(whole.height, 0.01))
        whole.scale(scale)
        whole.move_to([cx, cy - (0.3 if head else 0), 0])
        # A big diagram laid out and fitted to the stage shrinks its arrows' words with it, past reading: they are
        # grown back to a readable size (READABLE_LABEL), and set again clear of the arrows and nodes.
        labels = [m for _, _, edge in arrows for m in edge.get_family() if getattr(m, "is_label", False)]
        small = []
        for label in labels:
            # Its size now (the layout and the fit may both have shrunk it), in the font's own points.
            size = getattr(label, "font_size", None)
            if not size or size <= 0:
                continue
            grow = min(READABLE_LABEL / float(size), 3.0)
            if grow > 1.02:
                label.scale(grow)
                small.append(label)
        if small:
            import stem

            stem._settle_labels([*mobs.values(), *[m for _, _, m in arrows]],
                                (cx, whole.get_center()[1], w - 0.2, room_h), backing=P.BG)
        if head:
            head.next_to(whole, UP, buff=0.3)
            if head.get_top()[1] > cy + h / 2:
                head.move_to([cx, cy + h / 2 - head.height / 2, 0])
        # Built as it is told: the first part now, each of the others (and the arrows into it) as the narration
        # says it, or one after another through the line where it does not (queue_on_words).
        stepped = show is None and len(ids) >= 3 and os.environ.get("PANIM_DIAGRAM_STEPS", "1") != "0"
        shown = {ids[0]} if stepped else set(ids if show is None else [str(x) for x in show])
        self.diagrams[key] = {"nodes": mobs, "edges": arrows, "shown": shown, "focus": None, "write": True,
                              "_beat": self.__dict__.get("_sync_beat", 0)}
        self._diagram_moves(key, [mobs[i] for i in ids if i in shown]
                            + [m for a, b, m in arrows if a in shown and b in shown])
        self._next_keys.add(key)
        first = [mobs[i] for i in ids if i in shown] + [m for a, b, m in arrows if a in shown and b in shown]
        self._next_pending.extend([mobs[i] for i in ids if i not in shown]
                                  + [m for a, b, m in arrows if not (a in shown and b in shown)])
        lead = ([head] if head else []) + ([backdrop] if backdrop is not None else [])
        body = Group(*lead, *first)
        # Written in node by node, each arrow after the nodes it joins, as a teacher draws it on a board.
        order = lead + [mobs[i] for i in ids if i in shown]
        for a, b, m in arrows:
            if a in shown and b in shown:
                order.insert(max(order.index(mobs[a]), order.index(mobs[b])) + 1, m)
        shown_now = self._to_stage(Group(body), draw=order)
        if stepped:
            names = self.__dict__.get("_diagram_labels", {}).get(key) or {}
            for i in ids[1:]:
                self.queue_on_words(names.get(i, i), lambda heard, i=i: self.reveal_nodes(key, [i]))
        return shown_now

    @staticmethod
    def _edge_in(mob):
        """An arrow coming on: drawn along its length; a picture's own arrow (picture_flow) drawn on where it is
        in the picture (draw_on: its outline traced, then its colour)."""
        if isinstance(mob, VMobject) and all(isinstance(m, VMobject) for m in mob.get_family()):
            return Create(mob, rate_func=ease_out_cubic)
        return write_in(mob)

    # ---------------- a flow drawn as one picture (picture_flow.py) ----------------
    def picture_flow(self, key: str, nodes, edges, parts: dict, title: str | None = None, show=None):
        """A flow the image model drew as ONE picture, revealed in that picture itself: the compiler found where
        each step and each arrow is in it (picture_flow.split), and each is drawn on exactly where it is in the
        picture (its outline traced, then its colour: draw_on), a label under each step, so the picture builds up
        as it is spoken of and ends as the picture the model drew. Nothing is moved or laid out again: the whole
        is only fitted to the stage (_diagram_finish). Its first step comes on with it, each other step (the arrow
        into it first) on the words that name it; reveal and focus work on it by its steps' ids. parts: {"size": [w, h], "nodes": [[file, x0, y0, x1, y1]],
        "edges": [[file, x0, y0, x1, y1] or None]}, in the picture's pixels; an arrow it has no picture of is
        drawn."""
        w_px, h_px = (float(v) for v in parts["size"])
        # Laid out at the size it will have on the stage (with room for the title and the labels under the steps),
        # so _diagram_finish's fit leaves the labels at their size.
        _, _, sw, sh = self.STAGE
        unit = min((sw - 0.6) / max(w_px, 1.0), (sh - (1.6 if title else 1.0)) / max(h_px, 1.0))
        nodes = [dict(n) for n in nodes]
        ids = [str(n["id"]) for n in nodes]
        labels = {str(n["id"]): str(n.get("label") or n["id"]) for n in nodes}
        self.__dict__.setdefault("_diagram_labels", {})[key] = labels

        def placed(row):
            file, x0, y0, x1, y1 = row
            image = ImageMobject(str(file))
            image._panim_child = True           # drawn on in place (write_in -> draw_on), not faded in
            image.scale_to_fit_width(max((float(x1) - float(x0)) * unit, 0.05))
            image.move_to([((float(x0) + float(x1)) / 2 - w_px / 2) * unit,
                           -((float(y0) + float(y1)) / 2 - h_px / 2) * unit, 0])
            image._panim_src = str(file)
            return image

        mobs = {}
        for k, i in enumerate(ids):
            image = placed(parts["nodes"][k])
            tag = self._label_tag(labels[i], max(2.2, image.width + 0.8), size=18)
            tag.next_to(image, DOWN, buff=0.12)
            mobs[i] = Group(image, tag)
        arrows, edge_list = [], []
        for e, edge in enumerate(edges):
            a, b = str(edge[0]), str(edge[1])
            if a not in mobs or b not in mobs:
                continue
            start, end = mobs[a][0].get_center(), mobs[b][0].get_center()
            way = (end - start) / max(float(np.linalg.norm(end - start)), 1e-6)
            row = parts["edges"][e] if e < len(parts.get("edges") or []) else None
            if row:
                mob = placed([self._readable_ink(row[0]), *row[1:]])
            else:
                reach = lambda m: 0.5 * min(m.width, m.height)  # noqa: E731 -- from near each picture's edge
                mob = Arrow(start + way * reach(mobs[a][0]), end - way * reach(mobs[b][0]), buff=0.2,
                            color=P.MUTED, stroke_width=6, max_tip_length_to_length_ratio=0.15)
            group = Group(mob)
            words = str(edge[2]) if len(edge) > 2 and edge[2] else ""
            if words:
                label = T(words, 18, P.MUTED)
                label.is_label = True
                side = np.array([-way[1], way[0], 0.0])
                if side[1] < 0:
                    side = -side
                label.next_to(mob, side, buff=0.08)
                group.add(label)
            group._panim_dir = way
            arrows.append((a, b, group))
            edge_list.append([a, b] + ([words] if words else []))
        return self._diagram_finish(key, ids, mobs, arrows, edge_list, title, show)

    @staticmethod
    def _readable_ink(path: str) -> str:
        """A picture's arrow (one ink on transparent) in a shade that reads on this board: the model draws its
        arrows dark, and on a dark board a dark arrow is not seen. The file itself when it reads already."""
        from PIL import Image

        with Image.open(path) as im:
            rgba = np.asarray(im.convert("RGBA")).astype(np.float64)
        solid = rgba[..., 3] > 128
        if not solid.any():
            return path
        mean = rgba[solid][:, :3].mean(axis=0)
        ink = "#" + "".join(f"{int(round(v)):02X}" for v in mean)
        board = str(TH.get("bg") or P.BG)
        if contrast(ink, board) >= 3.0:
            return path
        better = readable(P.MUTED if contrast(P.MUTED, board) >= 3.0 else P.CREAM, board, 3.0)
        out = Path(path).with_name(f"{Path(path).stem}-ink{better.lstrip('#')}.png")
        if not out.exists():
            rgb = [int(better[i:i + 2], 16) for i in (1, 3, 5)]
            rgba[..., 0], rgba[..., 1], rgba[..., 2] = rgb
            Image.fromarray(rgba.astype(np.uint8), "RGBA").save(out, optimize=True)
        return str(out)

    def reveal_nodes(self, key: str, nodes):
        """The next part of a diagram: these nodes, and the arrows that now join shown nodes."""
        d = self.diagrams.get(key)
        if not d or d.get("gone"):
            # Its picture has left the stage: drawing its parts now put them over whatever replaced it.
            return None
        new = [str(n) for n in nodes if str(n) in d["nodes"] and str(n) not in d["shown"]]
        d["shown"].update(new)
        # The focus moves on: the veils lift.
        before = self._unveil(d)
        drawn = [d["nodes"][i] for i in new] + [mob for a, b, mob in d["edges"]
                                                 if (a in new or b in new) and a in d["shown"] and b in d["shown"]]
        self.stage_pending = [m for m in self.stage_pending if all(m is not x for x in drawn)]
        self._beat_revealed.extend(drawn)
        # A sketch or graph draws its parts in, as on a board; a diagram's nodes fade in.
        # The arrow into a part is drawn first, then the part pops in at its tip (a picture, a card) or is written
        # (a sketch's lines are drawn).
        arrows = [self._edge_in(self._stage_add(mob)) for a, b, mob in d["edges"]
                  if (a in new or b in new) and a in d["shown"] and b in d["shown"]]
        anims = arrows + [Create(self._stage_add(d["nodes"][i])) if d.get("draw") else
                          write_in(self._stage_add(d["nodes"][i])) for i in new]
        self._diagram_moves(key, drawn)
        if before:
            reveal = LaggedStart(*anims, lag_ratio=0.3) if anims else None
            return AnimationGroup(AnimationGroup(*before), *([reveal] if reveal else []), lag_ratio=1.0)
        return LaggedStart(*anims, lag_ratio=0.3) if anims else None

    def _flow_dots(self, arrow, count: int = 3):
        """Dots that run along an arrow, start to tip, over and over: which way the process goes."""
        dots = VGroup(*[Dot(radius=0.055, color=P.GOLD) for _ in range(count)])

        def place(t: float) -> None:
            for k, dot in enumerate(dots):
                f = (t / 2.0 + k / count) % 1.0                  # once along every 2 s: a period LOOP divides
                dot.move_to(arrow.point_from_proportion(0.04 + 0.86 * f))
                dot.set_fill(opacity=math.sin(math.pi * f) ** 0.6)

        dots.place = place
        place(0.0)
        return dots

    def _diagram_moves(self, key: str, parts) -> None:
        """Set the moving pictures among a diagram's parts going (a node's picture that bobs or sways, dots along
        arrows): from the line they are drawn on, for as long as the diagram is on the stage (export_dsl bakes
        them)."""
        start = getattr(self, "_live_start", None)
        if start is None:
            return
        for part in parts:
            for mob in part.get_family():
                move = getattr(mob, "_panim_move", None)
                if move and isinstance(mob, ImageMobject) and not getattr(mob, "_panim_moving", False):
                    mob._panim_moving = True
                    self._move_picture(mob, [], move)
            dots = getattr(part, "flow", None)
            if dots is not None:
                start(dots, lambda t, _p, dots=dots: dots.place(t), "loop", True)

    # The rest of a diagram while one part is talked about: under a veil of the board's colour this opaque.
    DIM_VEIL = 0.6

    def _unveil(self, d: dict) -> list:
        """The veils over a diagram's other parts lifted (the focus moved on, or more of it is shown)."""
        going = [FadeOut(v) for v in d.get("veils") or []]
        for v in d.get("veils") or []:
            if v in self.stage_extra:
                self.stage_extra.remove(v)
        d["veils"] = []
        return going

    def spotlight(self, key: str, node: str):
        """Draw the eye to one node of a diagram: the rest of the diagram dimmed under a veil of the board's colour
        while it is talked about. No box is drawn around the node: the veil alone sets it apart, and nothing moves
        (the stage was moved in on a big diagram; the camera is off)."""
        d = self.diagrams.get(key)
        if not d or d.get("gone") or str(node) not in d["nodes"] or str(node) not in d["shown"]:
            # Its picture has left the stage: a ring now would circle an empty patch of whatever replaced it.
            return None
        target = d["nodes"][str(node)]
        if not len(target.get_family()) or target.width < 1e-3 and target.height < 1e-3:
            return None
        anims = []
        if d["focus"] is not None:
            anims.append(FadeOut(d["focus"]))
            if d["focus"] in self.stage_extra:
                self.stage_extra.remove(d["focus"])
        anims += self._unveil(d)
        push, moved = None, None
        # One focal point: every other part shown so far goes quiet under a veil; the arrows into and out of this one
        # stay clear.
        if not d.get("drawing"):
            veils = []
            for other, mob in d["nodes"].items():
                if other == str(node) or other not in d["shown"] or not len(mob.get_family()):
                    continue
                veil = RoundedRectangle(corner_radius=0.12, width=mob.width + 0.16, height=mob.height + 0.16,
                                        fill_color=P.BG, fill_opacity=self.DIM_VEIL, stroke_width=0).move_to(mob)
                if moved is not None:
                    moved(veil)
                veil._art_decorated = True
                veils.append(self._stage_add(veil))
            d["veils"] = veils
            anims += [FadeIn(v) for v in veils]
        d["focus"] = None
        if not anims:
            return push
        lit = AnimationGroup(*anims, lag_ratio=0.2)
        return AnimationGroup(push, lit, lag_ratio=1.0) if push is not None else lit

    @staticmethod
    def _card(inner, tone: str, pad: float = 0.42, width: float | None = None):
        """A text card: the words on a soft wash of the tone with a hairline edge (ui_surface), and a slim pill of
        the tone down the left, so a card reads as one thing on any board instead of words floating on it."""
        box = ui_surface(width or inner.width + 2 * pad + 0.2, inner.height + 2 * pad, tone)
        bar = _flat(RoundedRectangle(corner_radius=0.035, width=0.07, height=max(box.height - 0.56, 0.2),
                                     fill_color=tone, fill_opacity=1, stroke_width=0))
        bar.align_to(box, LEFT).shift(RIGHT * 0.22)
        inner.move_to(box).shift(RIGHT * 0.1)
        return VGroup(box, bar, inner)

    def define(self, term: str, meaning: str, entity: str | None = None):
        """A hard word, big, with what it means in plain words (and a drawing of it when there is one)."""
        if self.board_mode and (self._solving() or self.works and self._problem is None) and not self._beat_new:
            # A problem or a working is on the board: the word goes in the key-point strip, not over them.
            return self.board_point(f"{term}: {meaning}")
        cx, cy, w, h = self.STAGE
        drawing = self._entity(entity, 1.6)
        word = fit(T(term, 48, P.SAND, font=TH["serif"], weight=BOLD), w - 1.2)
        body = fit(T(wrap(meaning, 30), 28, P.CREAM, line_spacing=1.0), w - 1.2)
        rule = Line(LEFT, RIGHT, color=P.SAND, stroke_width=3).set_width(min(max(word.width, 1.6), body.width))
        text = VGroup(word, rule, body).arrange(DOWN, buff=0.26, aligned_edge=LEFT)
        card = self._card(text, P.SAND)
        parts = group_of(*([drawing] if drawing is not None else []), card).arrange(DOWN, buff=0.3)
        # On the board, beside the drawing being explained rather than in place of it.
        parts.is_text_card = True
        strip = self._term_strip(term, meaning) if drawing is None and not self._panel_up() else None
        if strip is not None:
            return strip
        beside = self._aside(parts, grow=1.2) if not self._beat_new else None
        if beside is not None:
            return beside
        self._fit_stage(parts, grow=1.8 if self.board_mode else 1.25)
        card = Group(parts)
        card.is_text_card = True
        return self._to_stage(card)

    def _term_strip(self, term: str, meaning: str):
        """A word defined while a picture is up (a timeline, a diagram, a drawing): a slim highlighted strip across
        the top of the stage (the word in the accent colour, what it means after it), the picture moved down and
        shrunk only as much as the strip needs. A card beside the picture took half the stage from it, and laid
        over it the picture was hidden. None when there is no picture to keep (the card is shown as before)."""
        body = self.stage_body
        if body is None or getattr(body, "is_text_card", False) or not len(body.get_family()) > 1 \
                or self.works or self._problem is not None:
            return None
        cx, cy, w, h = self.STAGE
        word = T(term, 30, P.GOLD, font=TH["serif"], weight=BOLD)
        room = w - 1.0 - word.width - 0.4
        body_text = T(wrap(meaning, max(24, int(room * 6.2))), 24, P.CREAM, line_spacing=0.95)
        line = VGroup(word, body_text).arrange(RIGHT, buff=0.4, aligned_edge=UP)
        line = fit(line, w - 1.0)
        back = RoundedRectangle(corner_radius=0.16, width=w - 0.3, height=line.height + 0.4,
                                fill_color=_tint_on_bg(P.GOLD, 0.16), fill_opacity=1,
                                stroke_color=_tint_on_bg(P.GOLD, 0.7), stroke_width=2)
        bar = RoundedRectangle(corner_radius=0.04, width=0.09, height=max(back.height - 0.24, 0.2), fill_color=P.GOLD,
                               fill_opacity=1, stroke_width=0).align_to(back, LEFT).shift(RIGHT * 0.16)
        line.move_to(back).align_to(back, LEFT).shift(RIGHT * 0.4)
        strip = VGroup(back, bar, line)
        strip.move_to([cx, cy + h / 2 - strip.height / 2 - 0.05, 0])
        strip.is_term_strip = True
        anims = []
        old = [m for m in self.stage_extra if getattr(m, "is_term_strip", False)]
        for m in old:
            # One word at a time: the next one takes the strip's place, the picture stays where it is.
            self.stage_extra.remove(m)
            anims.append(FadeOut(m))
        if not old:
            # The picture (and its parts still to come) moves down under the strip, shrunk only to fit.
            below = (cx, cy - (strip.height + 0.15) / 2, w, h - strip.height - 0.15)
            # Everything on the stage moves together, a card beside the drawing too (moved alone, the drawing slid
            # under the card).
            picture = Group(*[m for m in [body, *self.stage_extra, *self.stage_pending]])
            f = min(1.0, (below[2] - 0.2) / max(picture.width, 0.01), (below[3] - 0.2) / max(picture.height, 0.01))
            slide = self._move_stage(f, picture.get_center(), below)
            if slide is not None:
                anims.append(slide)
        self._stage_add(strip)
        show = FadeIn(strip, shift=DOWN * 0.15)
        return AnimationGroup(AnimationGroup(*anims), show, lag_ratio=1.0) if anims else show

    def compare_cards(self, columns, title: str | None = None):
        """Two or three things side by side: a name and a few short points each (a picture of each is a picture op
        of its own)."""
        cx, cy, w, h = self.STAGE
        columns = list(columns)[:3]
        tones = [P.RIVER, P.ROSE, P.GREEN]
        col_w = (w - 0.3 * (len(columns) - 1)) / max(len(columns), 1)
        cards = VGroup()
        for k, col in enumerate(columns):
            drawing = None
            name = fit(T(str(col.get("title", "")), 32, tones[k], font=TH["serif"], weight=BOLD), col_w - 0.7)
            points = VGroup(*[fit(T("• " + wrap(str(p), 24), 26, P.CREAM, line_spacing=0.92), col_w - 0.8)
                              for p in list(col.get("points") or [])[:4]]).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
            rule = Line(LEFT, RIGHT, color=tones[k], stroke_width=2.5).set_width(max(name.width, points.width))
            inner = VGroup(*([drawing] if drawing is not None else []), name, rule, points).arrange(DOWN, buff=0.24)
            points.align_to(rule, LEFT)
            cards.add(self._card(inner, tones[k]))
        # The cards as wide as the widest needs, not the whole stage: words fill a card instead of a corner of it.
        widest = max((c[0].width for c in cards), default=0)
        for c in cards:
            c[0].stretch_to_fit_width(widest)
            c[1].align_to(c[0], LEFT).shift(RIGHT * 0.2)
            c[2].move_to(c[0]).shift(RIGHT * 0.1)
        top = max(c[0].height for c in cards) if len(cards) else 0
        for c in cards:
            c[0].stretch_to_fit_height(top)
            c[1].stretch_to_fit_height(top - 0.5).align_to(c[0], UP).shift(DOWN * 0.25)
            c[2].align_to(c[0], UP).shift(DOWN * 0.42)
        cards.arrange(RIGHT, buff=0.3, aligned_edge=UP)
        for col, card in zip(columns, cards):
            self.name_part(str(col.get("title", "")), card)
        parts = VGroup(cards)
        if title:
            parts = VGroup(fit(T(title.upper() if TH["upper"] else title, 30, P.TITLE, font=TH["serif"], weight=BOLD),
                               w - 0.4), cards).arrange(DOWN, buff=0.35)
        self._fit_stage(parts, grow=1.4)
        return self._to_stage(Group(parts))

    QUESTION_HEADS = {"en": "Think about it", "hi": "सोचिए"}

    def question(self, text: str, choices=(), answer=None, title: str | None = None):
        """A question for the class, on the stage: a heading, the question, big, and its choices (A, B, C, D).

        `answer` is the right choice's index, or the answer in words for a question without choices. It is laid
        out now, so the card does not move, and shown later by answer(). think() runs the time-to-think bar
        under the heading.
        """
        cx, cy, w, h = self.STAGE
        w = min(w, 9.0)             # on the board, a card of reading width rather than the whole frame
        # A question about the drawing already up ("इस diagram में सोचो, कौन सा force लग रहा है?") goes beside it:
        # the drawing moves to the left half and stays, so the class can see what it is asked about.
        about_drawing = self._drawing_up()
        if about_drawing:
            w = self._halves()[1][2]
        head = T(title or self.QUESTION_HEADS.get(spoken_lang(text), self.QUESTION_HEADS["en"]), 20, P.SAND,
                 weight=BOLD)
        mark = Circle(radius=0.26, fill_color=P.SAND, fill_opacity=1, stroke_width=0)
        head = VGroup(VGroup(mark, T("?", 24, P.BG, weight=BOLD).move_to(mark)), head).arrange(RIGHT, buff=0.2)
        track = Line(LEFT * (w / 2 - 0.4), RIGHT * (w / 2 - 0.4), color=P.MUTED, stroke_width=4, stroke_opacity=0.35)
        body = fit(T(wrap(text, 30), 30, P.CREAM, font=TH["serif"], weight=BOLD, line_spacing=0.95), w - 0.6)
        parts = VGroup(head, track, body)
        options = VGroup()
        for k, choice in enumerate(list(choices)[:4]):
            letter = ui_chip("ABCD"[k], P.SAND, 17)
            words = fit(T(wrap(str(choice), 30), 21, P.CREAM, line_spacing=0.9), w - 1.5)
            row = VGroup(letter, words).arrange(RIGHT, buff=0.25)
            box = ui_surface(w - 0.6, row.height + 0.34, P.SAND, radius=0.18, wash=0.07)
            options.add(VGroup(box, row.move_to(box).align_to(box, LEFT).shift(RIGHT * 0.2)))
        if len(options):
            parts.add(options.arrange(DOWN, buff=0.16))
        shown = None
        if isinstance(answer, int) and 0 <= answer < len(options):
            shown = answer             # the ring is drawn once the card has its final size
        elif isinstance(answer, str) and answer.strip():
            said = fit(T(wrap(answer, 34), 22, P.GREEN, line_spacing=0.9), w - 0.6)
            parts.add(said)             # laid out with the card, then held back until answer()
        parts.arrange(DOWN, buff=0.3)
        head.align_to(track, LEFT)
        if about_drawing:
            return self._question_beside(parts, options, shown, answer, track)
        self._fit_stage(parts, grow=1.2)
        if isinstance(answer, str) and answer.strip() and not isinstance(shown, int):
            shown = parts[-1]
            parts.remove(shown)
            self._next_pending.append(shown)      # moves with the card, shown by answer()
        card = Group(parts)
        card.is_text_card = True
        anim = self._to_stage(card)
        if isinstance(shown, int):
            # Drawn once the card is where it will stay (beside a drawing, it is smaller).
            box = options[shown][0]
            ring = RoundedRectangle(corner_radius=0.16, width=box.width + 0.12, height=box.height + 0.12,
                                    stroke_color=P.GREEN, stroke_width=5).move_to(box)
            tick = T("✓", 30, P.GREEN, weight=BOLD).scale_to_fit_height(ring.height * 0.45).move_to(ring) \
                .align_to(ring, RIGHT).shift(LEFT * 0.25)
            shown = VGroup(ring, tick)
        self._question = {"track": track, "answer": shown, "options": options,
                          "right": answer if isinstance(answer, int) else None,
                          "in_panel": bool(getattr(card, "is_in_panel", False))}
        return anim

    def _drawing_up(self) -> bool:
        """A drawing from an earlier beat is on the board, with room beside it (not during a problem's working).
        A drawing from this same beat is handled by _to_stage, which puts the two side by side already."""
        body = self.stage_body
        return bool(self.board_mode and body is not None and not self.works and self._problem is None
                    and not getattr(body, "is_text_card", False) and len(body.get_family()) > 1
                    and body not in self._beat_new)

    def _question_beside(self, parts, options, shown, answer, track):
        """The question card in the right half, the drawing it is about moved into the left half."""
        card = Group(parts)
        card.is_text_card = True
        anim = self._aside(card, grow=1.2)
        if anim is None:                     # no room after all: the card takes the stage as before
            return self._to_stage(card)
        if isinstance(answer, str) and answer.strip() and not isinstance(shown, int):
            said = parts[-1]                 # already placed with the card; shown later by answer()
            parts.remove(said)
            said.is_aside = True
            shown = said
        elif isinstance(shown, int):
            box = options[shown][0]
            ring = RoundedRectangle(corner_radius=0.16, width=box.width + 0.12, height=box.height + 0.12,
                                    stroke_color=P.GREEN, stroke_width=5).move_to(box)
            tick = T("✓", 30, P.GREEN, weight=BOLD).scale_to_fit_height(ring.height * 0.45).move_to(ring) \
                .align_to(ring, RIGHT).shift(LEFT * 0.25)
            shown = VGroup(ring, tick)
            shown.is_aside = True
        self._question = {"track": track, "answer": shown, "aside": True, "options": options,
                          "right": answer if isinstance(answer, int) else None}
        return anim

    def think(self, seconds: float = THINK_SECONDS) -> None:
        """Silence while the class thinks about the question on the stage, a bar filling under its heading."""
        if not self._question:
            self.wait(seconds)
            return
        track = self._question["track"]
        bar = Line(track.get_start(), track.get_end(), color=P.SAND, stroke_width=6)
        bar.is_aside = self._question.get("aside", False)      # leaves with its card
        self._stage_add(bar)
        self._log("think", seconds=round(seconds, 3))
        self.play(Create(bar), run_time=seconds, rate_func=linear)

    def option(self, choice: int, right: bool | None = None):
        """One choice of the question on the stage, while the narration explains it: the right one ringed in
        green with a tick (the answer, shown now), a wrong one crossed out in red and faded. `right` decides for
        a question given without its answer. None when no question with that choice is up."""
        q = self._question or {}
        options = q.get("options")
        if not options or not 0 <= choice < len(options):
            return None
        correct = q.get("right") == choice if q.get("right") is not None else bool(right)
        box, row = options[choice][0], options[choice][1]
        if correct and q.get("answer") is not None and not isinstance(q.get("answer"), (str, int)):
            mark = q["answer"]                   # the ring laid out with the card
            q["answer"] = None                   # answer() has nothing left to show
        else:
            colour = P.GREEN if correct else P.ROSE
            ring = RoundedRectangle(corner_radius=0.16, width=box.width + 0.12, height=box.height + 0.12,
                                    stroke_color=colour, stroke_width=5).move_to(box)
            size = ring.height * 0.36
            sign = (VGroup(Line(LEFT * size * 0.5 + DOWN * size * 0.05, DOWN * size * 0.5, color=colour, stroke_width=7),
                           Line(DOWN * size * 0.5, RIGHT * size * 0.7 + UP * size * 0.6, color=colour, stroke_width=7))
                    if correct else
                    VGroup(Line(UL * size * 0.5, DR * size * 0.5, color=colour, stroke_width=7),
                           Line(UR * size * 0.5, DL * size * 0.5, color=colour, stroke_width=7)))
            sign.move_to(ring).align_to(ring, RIGHT).shift(LEFT * 0.3)
            mark = VGroup(ring, sign)
        mark.is_aside = q.get("aside", False)
        self._stage_add(mark)
        if correct:
            return FadeIn(mark, scale=1.05)
        return AnimationGroup(Create(mark[0]), Create(mark[1]), row.animate.set_opacity(0.4))

    def answer(self):
        """The answer to the question on the stage: the right choice ringed, or the answer in words. None when
        no question is up."""
        shown = (self._question or {}).get("answer")
        if shown is None:
            return None
        self._question["answer"] = None
        if self._question.get("in_panel"):
            # The question is in the panel: its answer is written there too.
            shown.set_z_index(Z_PANEL_TEXT)
            self.panel_items.add(shown)
        else:
            self._stage_add(shown)
        return FadeIn(shown, scale=1.05)

    def quote(self, text: str, who: str = ""):
        """A quotation, large, with who said it."""
        cx, cy, w, h = self.STAGE
        mark = T("“", 110, P.SAND, font=TH["serif"], weight=BOLD)
        body = fit(T(wrap(text, 30), 34, P.CREAM, font=TH["serif"], line_spacing=1.0), w - 1.4)
        words = VGroup(mark, body)
        if who:
            words.add(fit(T(f"— {who}", 24, P.SAND, weight=BOLD), w - 1.4))
        words.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        parts = self._card(words, P.SAND, pad=0.5)
        self._fit_stage(parts)
        return self._to_stage(Group(parts))

    def figure(self, path: str, caption: str = "", where: str = "panel", credit: str = ""):
        """A figure from a source document: in the panel, or across the frame for one beat. `credit`: a photo the
        web had in place of the book's own (its author and licence, shown under it on the stage)."""
        if where in ("panel", "full") and self.board_mode:
            # The board already spans the frame: a "full" figure there covered the title strip, and anything
            # else the beat put on the stage stayed hidden under it.
            where = "stage"
        if where == "stage" or is_cutout(path):
            # A picture the image model made (a book's diagram redrawn, a photo made again) is vector shapes,
            # drawn in on the stage, large: a detailed diagram needs the room, and the panel takes only images.
            # Always whole (_keep_whole): a book's figure is any shape, and cut to the screen's shape to fill it,
            # its top and bottom (a tall page) or its sides were lost.
            self._keep_whole = True
            try:
                return self.stage_image(path, caption, credit=credit)
            finally:
                self._keep_whole = False
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
            # What was on the stage leaves under it, so it does not reappear when the figure goes.
            going = self._stage_leaving()
            return AnimationGroup(FadeIn(group), *going) if going else FadeIn(group)
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
        # A short, solid rule of the accent between the number and the name: a pill, not a hairline.
        rule = _flat(RoundedRectangle(corner_radius=0.04, width=1.4, height=0.08 if not TH.get("highlight") else 0.12,
                                      fill_color=TH.get("highlight", P.SAND), fill_opacity=1, stroke_width=0))
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

    # The lecture's emblem (a crown for feudalism, a wheel for the Industrial Revolution): one small picture made
    # once, on the title, every chapter card and beside the chapter's name. None: no emblem.
    EMBLEM: str | None = None

    def emblem(self, height: float):
        """The emblem at a height, or None."""
        if not self.EMBLEM or not Path(str(self.EMBLEM)).is_file():
            return None
        try:
            return cutout_mob(str(self.EMBLEM), height * 1.6, height)
        except Exception as error:  # noqa: BLE001 -- an emblem that will not draw is left off
            skipped(f"the emblem left off: {type(error).__name__}: {error}"[:300])
            self.EMBLEM = None
            return None

    def chapter(self, num: int, title: str, sub: str, narration: str) -> None:
        """A full-frame title card over the first beat of a chapter.

        A chapter starts on an empty stage. In one scene holding a whole
        lecture, the last chapter's map and panel are cleared first rather
        than left under the card.
        """
        self._chapter_no = int(num)        # the chapter its beats' counts go under (SYNC)
        # A build that records some chapters only (export_dsl's chapter window, chapters built side by side)
        # starts and stops recording here.
        # The title, for a hook that lists the chapters (the phone's chapter list: export_dsl).
        self._chapter_title = title
        for hook in CHAPTER_HOOKS:
            hook(self, num)
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
        mark = self.emblem(1.0)
        if mark is not None:
            mark.next_to(card, UP, buff=0.3).set_z_index(Z_CARD)
            if mark.get_top()[1] > config.frame_height / 2 - 0.7:
                mark.shift(DOWN * (mark.get_top()[1] - config.frame_height / 2 + 0.7))
            intro = AnimationGroup(intro, write_in(mark))
            card = Group(*card, mark)
        intro.panim_sfx = "chapter"
        self.beat(narration, intro, rt=2.2)
        self.play(FadeOut(card, shift=UP * 0.3), run_time=0.8)

    def title_slide(self, title: str, sub: str = "", tag: str = "AN ILLUSTRATED LECTURE", narration: str = ""):
        head = T(title.upper() if TH["upper"] else title, 88, P.SAND, font=TH["serif"], weight=BOLD)
        fit(head, 12)
        line = T(sub, 30, P.CREAM, font=TH["serif"]) if sub else VGroup()
        fit(line, 12)
        label = T(tag, 16, P.MUTED, weight=BOLD)
        mark = self.emblem(1.3)
        group = Group(*([mark] if mark is not None else []), label, head, line).arrange(DOWN, buff=0.28)
        group.move_to(UP * 0.4)
        group.set_z_index(Z_CARD)
        opening = LaggedStart(*([FadeIn(mark, scale=0.8)] if mark is not None else []), FadeIn(label), Write(head),
                              FadeIn(line, shift=UP * 0.2), lag_ratio=0.35)
        opening.panim_sfx = "intro"
        self.beat(narration or f"{title}. {sub}", opening, rt=3.0)
        self.play(FadeOut(group, shift=UP * 0.3), run_time=0.8)

    def recap(self, points, narration=None) -> None:
        """Up to eight idea cards in a grid, one beat each."""
        palette = [P.SAND, P.MOUNT, P.GREEN, P.DUNE, P.RIVER, P.TEAL, P.OLIVE, P.ROSE]
        cards = VGroup()
        for i, (head, body) in enumerate(points[:8]):
            color = palette[i % len(palette)]
            # A numbered card: the number in a pill of the card's colour, the idea bold, a line of what it means.
            chip = ui_chip(f"{i + 1:02d}", color, 17)
            tt = fit(T(head, 28, P.CREAM, font=TH["serif"], weight=BOLD), 3.2)
            ss = fit(T(wrap(body, 28), 19, P.MUTED, line_spacing=0.9), 3.2)
            words = VGroup(chip, tt, ss).arrange(DOWN, buff=0.18, aligned_edge=LEFT)
            box = ui_surface(3.65, max(2.2, words.height + 0.6), color, wash=0.12)
            if STYLE == "cardboard":
                box.set_fill(P.PANEL, 1)
            words.move_to(box).align_to(box, LEFT).shift(RIGHT * 0.25)
            cards.add(VGroup(box, words))
        # One height for the row, the tallest card's, so the words never cross a card's edge.
        tallest = max((c[0].height for c in cards), default=1.7)
        for c in cards:
            c[0].stretch_to_fit_height(tallest)
        cols = 4 if len(cards) > 3 else len(cards)
        rows = math.ceil(len(cards) / max(cols, 1))
        cards.arrange_in_grid(rows=rows, cols=cols, buff=(0.2, 0.3)).move_to(UP * 0.35)
        if cards.width < 11.5 and cards.height < 4.5:
            # A few cards: large enough to read across the room.
            cards.scale(min(12.0 / cards.width, 5.0 / cards.height, 1.45)).move_to(UP * 0.35)
        cards.set_z_index(Z_PANEL_TEXT)
        lines = narration or [f"{h}. {b}." for h, b in points[:8]]
        for card, line in zip(cards, lines):
            self.beat(line, LaggedStart(FadeIn(card[0], shift=UP * 0.2, scale=0.95),
                                        FadeIn(card[1], shift=UP * 0.12), lag_ratio=0.3), rt=1.0)
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
        self._stack(parts, 0.3)
        self.add(parts)                                   # still: simply there, nothing drawn in
        return None

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
        if any(d.startswith("historical:") for d in USED_DRAWINGS):
            import historical

            note = f"{note}  {historical.CREDIT}."
        credit = fit(T(line, 14, P.MUTED), 13).move_to(DOWN * 1.9)
        small = fit(T(note, 13, P.MUTED), 13).next_to(credit, DOWN, buff=0.15)
        parts = [credit, small]
        if extra:
            parts.append(fit(T(wrap(extra, 150), TYPE["fine"], P.MUTED, line_spacing=0.8, fine=True), 13).next_to(small, DOWN, buff=0.15))
        self.play(*[FadeIn(p) for p in parts], run_time=1.0)
        self.wait(seconds + (2.0 if extra else 0.0))
        self.play(*[FadeOut(p) for p in parts], run_time=0.8)

    # How a chapter gives way to the next, by style: a page turned (an old page, a cardboard sheet), a chalk smudge
    # rubbed across the board, a whiteboard's eraser wipe; the rest fade. PANIM_TRANSITION (page, smudge, wipe,
    # fade) sets one for every style.
    TRANSITIONS = {"parchment": "page", "cardboard": "page", "chalkboard": "smudge", "whiteboard": "wipe",
                   "blueprint": "wipe"}

    def transition_kind(self) -> str:
        kind = os.environ.get("PANIM_TRANSITION") or TH.get("transition") or \
            self.TRANSITIONS.get(STYLE) or self.TRANSITIONS.get(TH.get("base_style", ""), "fade")
        return kind if kind in ("page", "smudge", "wipe") else "fade"

    def _sweeper(self, kind: str) -> VGroup:
        """The sheet that sweeps across the frame: the board's colour, with an edge that says what it is."""
        w, h = config.frame_width, config.frame_height
        sheet = Rectangle(width=w + 0.2, height=h + 0.2, fill_color=P.BG, fill_opacity=1, stroke_width=0)
        parts = [sheet]
        lead = sheet.get_left()[0]
        if kind == "page":
            # A page's turned edge: a soft shadow ahead of it and a crisp line.
            for k, opacity in enumerate((0.16, 0.1, 0.05)):
                shade = Rectangle(width=0.18, height=h + 0.2, fill_color="#000000", fill_opacity=opacity,
                                  stroke_width=0).move_to([lead - 0.09 - 0.18 * k, 0, 0])
                parts.append(shade)
            parts.append(Line([lead, -h / 2 - 0.1, 0], [lead, h / 2 + 0.1, 0], stroke_color=P.MUTED, stroke_width=2))
        elif kind == "smudge":
            # Chalk rubbed across: a ragged, half-clear edge.
            rng = np.random.default_rng(7)
            ys = np.linspace(-h / 2 - 0.1, h / 2 + 0.1, 24)
            edge = [[lead - 0.35 - 0.3 * float(rng.random()), y, 0] for y in ys]
            rag = Polygon(*edge, [lead + 0.01, h / 2 + 0.1, 0], [lead + 0.01, -h / 2 - 0.1, 0],
                          fill_color=P.BG, fill_opacity=0.7, stroke_width=0)
            parts.append(rag)
        else:
            # The eraser: a felt bar leading the wipe.
            parts.append(Rectangle(width=0.3, height=h + 0.2, fill_color=P.MUTED, fill_opacity=0.85,
                                   stroke_width=0).move_to([lead - 0.15, 0, 0]))
        group = VGroup(*parts)
        for part in group.get_family():
            part._art_decorated = True
        group.set_z_index(Z_CHROME - 0.5)
        return group

    def outro_fade(self, run_time: float = 1.0) -> None:
        """Fade everything a chapter added; keep the backdrop and chrome. In a style with a transition of its own
        (transition_kind), a sheet sweeps across instead, taking the chapter with it."""
        going = self.on_stage()
        self.clear_caption()
        kind = self.transition_kind()
        if going and kind != "fade":
            sheet = self._sweeper(kind)
            # Turned from the right, as a book's page; rubbed and wiped from the left.
            sign = -1 if kind == "page" else 1
            if sign < 0:
                sheet.rotate(PI)
            width = config.frame_width + 1.2
            sheet.move_to([-sign * width, 0, 0])
            self.play(sheet.animate.move_to(ORIGIN), run_time=run_time * 0.55, rate_func=smooth)
            self.remove(*going)
            self.play(sheet.animate.move_to([sign * width, 0, 0]), run_time=run_time * 0.45, rate_func=smooth)
            self.remove(sheet)
        elif going:
            self.play(*[FadeOut(m) for m in going], run_time=run_time)
        self._stage_reset()

    def _stage_reset(self) -> None:
        """Forget what a chapter (or a run of map beats) put up, once it has gone."""
        self.panel_items = Group()
        self.panel_images = Group()
        self.stage_items = Group()
        self.stage_extra = []
        self.diagrams = {}
        self._full_figure = self._new_figure = None
        self._map_on = False
        self._map_names, self._map_tidy = [], []
        self._cover = self._cover_holder = None
        self._cover_hidden = []
        self._shaded = {}
        self.panel_y = 2.35
        self.stage_body, self.stage_pending, self._next_pending = None, [], []
        self.works, self._problem, self._question = {}, None, None
        self.strip = {"title": None, "point": None}


from stem import BoardMixin  # noqa: E402 -- the board layout and the STEM drawings


# A question for the class sounds a two-note call; its answer, a brighter chime (sfx.py).
Lecture.question = _with_sound(Lecture.question, "question")
Lecture.answer = _with_sound(Lecture.answer, "answer")


class MapLecture(BoardMixin, Lecture):
    """A lecture over one region's map, with neighbours, state lines and markers.

    REGION names the focus: dict(country="India"), dict(state="Rajasthan", country="India"), or an area
    (dict(area="World"), dict(area="South Asia")). Borders are drawn as India draws them (countries_dataset).
    """

    REGION: dict = dict(country="India")
    MAP_CENTER = (-3.0, 0.2)
    MAP_SIZE = (6.3, 6.5)
    TEXT_LEFT = TEXT_X
    PANEL_BOX = (PANEL_X, 7.05)

    # ---------------- region ----------------
    @property
    def area_name(self) -> str | None:
        """The world, a continent or a world region this map shows (REGION area, continent, or a country name that
        is not a country), or None for a country's or a state's map."""
        if not hasattr(self, "_area_name"):
            self._area_name = None
            if region_kind(self.REGION) == "area":
                self._area_name = self.REGION.get("area") or self.REGION.get("continent") or self.REGION.get("country")
        return self._area_name

    @property
    def home_country(self) -> str | None:
        """The country places are looked up in first: none on a map of an area."""
        return None if self.area_name else self.REGION.get("country")

    @property
    def focus(self):
        if not hasattr(self, "_focus"):
            region = self.REGION
            if region.get("state"):
                self._focus = state(region["state"], region.get("country"))
            elif self.area_name:
                self._focus = area(self.area_name)
            else:
                self._focus = country_home(region["country"], region.get("view"))
        return self._focus

    @property
    def mainland(self):
        g = self.focus
        if self.area_name:
            # An area is framed whole (all its countries), or to its own frame where its countries reach far away.
            frame = AREA_FRAMES.get(_area_key(self.area_name))
            return _box(frame) if frame else g
        return max(g.geoms, key=lambda p: p.area) if g.geom_type == "MultiPolygon" else g

    # A lon/lat box to fit the map to instead of the whole focus: a
    # battlefield a few kilometres across inside its province.
    FRAME_BBOX: tuple | None = None

    @property
    def frame(self) -> MapFrame:
        if not hasattr(self, "_frame"):
            height, width = self.MAP_SIZE
            fit_to = _box(self.FRAME_BBOX) if self.FRAME_BBOX else self.mainland
            self._frame = MapFrame(fit_to, center=self.MAP_CENTER, height=height, width=width,
                                   clip=7.4 if getattr(self, "_wide", False) else True)
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
        # The land the map is fitted to (an area's frame, not all Russia on a map of Europe).
        lon0, lat0, lon1, lat1 = self.mainland.bounds if self.area_name else self.focus.bounds
        pad = margin if margin is not None else max(lon1 - lon0, lat1 - lat0) * 0.45
        return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)

    def place_bounds(self):
        """Where a place named on this map is looked up (map_bounds, which the compiler checks markers against):
        a battlefield's box when the map is fitted to one."""
        if self.FRAME_BBOX:
            return self.lonlat_bounds()
        return map_bounds(self.REGION) or self.lonlat_bounds()

    def at(self, where) -> tuple[float, float]:
        """An anchor, a place name, or a (lon, lat) pair, as (lon, lat)."""
        if isinstance(where, str) and where in self.ANCHORS:
            lon, lat = self.ANCHORS[where]
            return float(lon), float(lat)
        if isinstance(where, str):
            return place(where, self.home_country, self.place_bounds())
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
        if self.area_name:
            # Every country of the area outlined inside it; the countries round it as neighbours.
            members = list(area_members(self.area_name))
            for name, geom in countries_in(bounds, region.get("view"), exclude=members):
                nb.add(fr.poly(geom, simplify=0.01, min_area=0.001, **style))
            wanted = {_norm(m) for m in members}
            inner = VGroup(*[
                fr.poly(geom, simplify=0.01, min_area=0.0005, fill_opacity=0, stroke_color=TH["st_stroke"],
                        stroke_width=0.8)
                for name, geom in countries_in(bounds, region.get("view")) if _norm(name) in wanted
            ])
        elif region.get("state"):
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
        import artstyle

        artstyle.dress_map(nb, inner, outline)
        # The base map changes only by an animation (a fade, a dim), never by an updater: a bake that is not
        # animating it need not hash its thousands of points every frame (export_dsl.bake).
        for layer in (nb, inner, outline):
            layer._panim_static = True
        inner.set_z_index(Z_LINES)
        outline.set_z_index(Z_OUTLINE)
        self.layers = SimpleNamespace(neighbours=nb, lines=inner, outline=outline)
        return nb, inner, outline

    # A map chapter with nothing for the panel is drawn across the whole frame: the map, and the pictures that take
    # its place on the stage, get the width an empty panel would have wasted.
    WIDE_MAP = dict(MAP_CENTER=(0.0, 0.05), MAP_SIZE=(6.6, 13.3), STAGE=(0.0, 0.2, 13.0, 6.1))

    def _map_right(self) -> float:
        """The map's right edge on screen: the panel's edge, or the frame's when the map is wide."""
        return config.frame_width / 2 - 0.2 if getattr(self, "_wide", False) else PANEL_X - 0.08

    def show_map(self, panel: bool = True, run_time: float = 1.4, wide: bool = False) -> None:
        """Draw the base map (and the panel) in one move. `wide`: no panel, the map across the whole frame."""
        self.leave_board()
        was = getattr(self, "_wide", False)
        self._wide = bool(wide)
        for key, value in self.WIDE_MAP.items():
            if wide:
                setattr(self, key, value)
            else:
                self.__dict__.pop(key, None)
        if wide != was and hasattr(self, "_frame"):
            del self._frame
        if wide:
            panel = False
        self._map_on = True
        self._map_taken = []          # what the map's labels and pictures cover so far (place_label)
        self._map_names, self._map_tidy = [], []
        nb, inner, outline = self.base()
        anims = [FadeIn(nb), Create(outline)]
        if len(inner):
            anims.append(FadeIn(inner))
        if panel:
            self.panel = self.panel_bg()
            anims.append(FadeIn(self.panel))
        inset = self.locator()
        self._inset = inset
        if inset is not None:
            anims.append(FadeIn(inset))
        self.play(*anims, run_time=run_time)

    def map_in(self, bbox: tuple | None = None, places=(), wide: bool = True) -> None:
        """A run of beats taught on the map, in a chapter on the board: what is up goes, and the map comes in fitted
        to the places these beats show (use_frame), across the whole frame unless they put facts in a panel."""
        self.map_away()
        self.use_frame(bbox)
        self.show_map(wide=wide)
        if places:
            self.reserve_places(list(places))

    def map_away(self, board: bool | None = None, run_time: float = 0.7) -> None:
        """The map's run of beats is over: the map, its marks and its panel go. `board`: back to the board (True)
        or to a side panel (False); None leaves the layout to the caller."""
        going = self.on_stage()
        if going:
            self.play(*[FadeOut(m) for m in going], run_time=run_time)
        self._stage_reset()
        if getattr(self, "_wide", False):
            for key in self.WIDE_MAP:
                self.__dict__.pop(key, None)
            self._wide = False
            if hasattr(self, "_frame"):
                del self._frame
        self.panel = None
        if board is True:
            self.board()
        elif board is False:
            self.add_panel()

    def region_fill(self, geom, color: str, opacity: float = 0.6, z: float = Z_FILL, clip=None) -> VGroup:
        # Cut to the map's focus (its borders as drawn), or to `clip` (the map's whole window: a neighbouring
        # country shaded on a map of an area).
        m = self.frame.poly(_valid(geom).intersection(self.focus if clip is None else clip), simplify=0.006,
                            min_area=0.002,
                            fill_color=color, fill_opacity=opacity, stroke_width=0)
        _art(m)
        m.set_z_index(z)
        return m

    def fill_state(self, name: str, color: str | None = None, opacity: float = 0.6, label: str | None = None):
        """An area shaded on the map, its name written on it: a state or province, a country or a wider area
        (area_shape). A country or a region is the land it covers, not a dot at its middle."""
        try:
            shape = state(name, self.home_country)
        except KeyError:
            shape = area_shape(name, self.home_country)
        if not color:
            # Each area shaded in a tone of its own: Normandy in the same sand as France was France.
            tones = [P.SAND, P.RIVER, P.ROSE, P.GREEN, P.GOLD, P.TEAL, P.VIOLET]
            self._shade_k = getattr(self, "_shade_k", -1) + 1
            color = tones[self._shade_k % len(tones)]
        # Its land on the screen: within the map's focus where it lies there, else (a neighbour of the area the
        # map is about: Spain on a map of Western Europe) within the map's window, wider than the screen so the
        # screen's edge, not a straight cut, ends it.
        window = _box(self.lonlat_bounds())
        inside = _valid(shape.intersection(self.focus))
        clip = None if not inside.is_empty and inside.area >= 0.5 * _valid(shape.intersection(window)).area else window
        m = self.region_fill(shape, color, opacity, clip=clip)
        self.name_part(label or name, m, act=lambda m=m: self._map_look(m, m.get_center(), area=True))
        # Shaded again (England in its own colour once the war begins): the new shading takes the old one's place,
        # its name written once.
        shaded = getattr(self, "_shaded", {})
        self._shaded = shaded
        going = [FadeOut(x) for x in shaded.pop(_norm(name), ()) if any(x is y for y in self.mobjects)]
        shaded[_norm(name)] = (m,)
        if not label:
            return AnimationGroup(*going, FadeIn(m)) if going else FadeIn(m)
        # The name where the area is widest on the screen (a point inside it, never in a bay or a hole).
        on_map = _valid(shape.intersection(self.focus if clip is None else clip))
        if on_map.is_empty:
            return FadeIn(m)
        spot = on_map.representative_point()
        tag = self._map_text(label, 20, color)
        centre = self.frame.pt(spot.x, spot.y)
        taken = self._taken()

        def clear_at(p):
            tag.move_to(p)
            l, b, r, t = tag.get_left()[0], tag.get_bottom()[1], tag.get_right()[0], tag.get_top()[1]
            return not any(l < x1 and x0 < r and b < y1 and y0 < t for x0, y0, x1, y1 in taken)

        # On the area, where it covers no town's dot or name: the middle, else a step up, down or to a side.
        step_y, step_x = tag.height + 0.12, tag.width * 0.6 + 0.12
        for d in (ORIGIN, UP * step_y, DOWN * step_y, LEFT * step_x, RIGHT * step_x, UP * step_y * 2,
                  DOWN * step_y * 2):
            if clear_at(centre + d):
                break
        else:
            tag.move_to(centre)
        tag.set_z_index(Z_MARK + 2)
        box = (tag.get_left()[0], tag.get_bottom()[1], tag.get_right()[0], tag.get_top()[1])
        self._taken().append(box)
        self._name_on_map(tag, None, box)
        shaded[_norm(name)] = (m, tag)
        show = AnimationGroup(FadeIn(m), FadeIn(tag, scale=0.9), lag_ratio=0.5)
        return AnimationGroup(AnimationGroup(*going), show) if going else show

    def river(self, name: str, color: str | None = None, width: float = 5):
        """Create a Natural Earth river, cut to the map's box."""
        m = self.frame.line(river(name, self.lonlat_bounds()), stroke_color=color or P.RIVER, stroke_width=width)
        _art(m)
        m.set_z_index(7)
        return Create(m)

    def path(self, lonlats, color: str | None = None, width: float = 5, smooth: bool = True):
        """Create a hand-digitised line (a ridge, a canal) from lon/lat points."""
        m = self.frame.path(lonlats, smooth=smooth, stroke_color=color or P.HI, stroke_width=width)
        _art(m)
        m.set_z_index(8)
        return Create(m)

    def journey(self, stops, color: str | None = None, labels=None, width: float = 5, pictures=None):
        """A journey on the map, drawn as it happens: a traveller moves from stop to stop over the line, the route
        drawn behind it, each stop marked and named as it is reached (the Dandi March, Vasco da Gama's voyage, the
        Silk Road, the monsoon winds). `stops` are place names or (lon, lat); `labels` rename them."""
        color = color or P.GOLD
        stops = list(stops)
        names = list(labels or [])
        names += [s if isinstance(s, str) else "" for s in stops[len(names):]]
        lonlats = [self.at(s) for s in stops]
        full = self.frame.path(lonlats, smooth=False, stroke_color=color, stroke_width=width)
        route = full.copy().set_z_index(8)
        traveller = Dot(radius=0.12, color=color).set_z_index(Z_MARK + 1)
        points = [self.frame.pt(*ll) for ll in lonlats]
        # Every stop's dot is spoken for before any label is placed, so no stop's name covers a later stop.
        for q in points:
            self._taken().append((q[0] - 0.13, q[1] - 0.13, q[0] + 0.13, q[1] + 0.13))
        # A journey is one moving picture (its stops shown as it reaches them): drawings only, not photos.
        pictures = [pic if pic and str(pic[0]) != "image" else None for pic in list(pictures or [])] + [None] * len(stops)
        markers = [self.marker(s, label=n or None, color=color, size=19, picture=pic)
                   for s, n, pic in zip(stops, names, pictures)]
        legs = np.cumsum([0.0] + [float(np.linalg.norm(b - a)) for a, b in zip(points, points[1:])])
        reach = [float(x / max(legs[-1], 1e-9)) for x in legs]
        body = group_of(route, *markers, traveller)

        def where(f):
            """The point a fraction f of the way along the route, by distance travelled."""
            d = f * legs[-1]
            k = max(0, min(len(points) - 2, int(np.searchsorted(legs, d, side="right")) - 1))
            leg = max(legs[k + 1] - legs[k], 1e-9)
            return points[k] + (points[k + 1] - points[k]) * (d - legs[k]) / leg, k, (d - legs[k]) / leg

        def step(t: float, p: float) -> None:
            f = min(1.0, max(0.0, (p - 0.05) / 0.85))
            at, k, part = where(f)
            # The route so far: the legs behind the traveller, and the one it is on as far as it has come.
            corners = [*points[:k + 1], at] if f > 0 else [points[0], points[0] + np.array([1e-3, 0, 0])]
            route.set_points_as_corners(corners)
            traveller.move_to(at)
            for marker, needed in zip(markers, reach):
                _show(marker, f >= needed - 1e-6)

        step(0.0, 0.0)
        self._live_start(body, step, "process")
        return FadeIn(body, run_time=0.3)

    def flow(self, lonlats, color: str | None = None, width: float = 7, label: str | None = None):
        """A curved arrow along lon/lat points: a smoothed path and a tip. With a label (what moves: "spices",
        "the Aryans", "monsoon winds"), the label rides the arrow's head as it is drawn and stays at its middle."""
        color = color or P.RIVER
        fr = self.frame
        line = fr.path(lonlats, stroke_color=color, stroke_width=width)
        # A pale edge under it, so the arrow stands out from the borders and coastlines it crosses.
        edge = fr.path(lonlats, stroke_color=P.BG, stroke_width=width + 5, stroke_opacity=0.75)
        a, b = fr.pt(*lonlats[-2]), fr.pt(*lonlats[-1])
        tip = Triangle(fill_color=color, fill_opacity=1, stroke_color=P.BG, stroke_width=2).scale(0.2)
        tip.rotate(math.atan2(b[1] - a[1], b[0] - a[0]) - PI / 2).move_to(b)
        group = VGroup(edge, line, tip)
        group.set_z_index(15)
        if not label:
            return AnimationGroup(Create(edge), Create(line), FadeIn(tip), lag_ratio=0.4)
        tag = self._map_text(str(label), 17, color)
        tag.set_z_index(Z_MARK)

        def at(f: float, side: float) -> np.ndarray:
            """Beside the line a fraction f along it, on one side (+1: the upper)."""
            f = min(max(f, 1e-3), 1 - 1e-3)
            here, ahead = line.point_from_proportion(f), line.point_from_proportion(min(f + 0.01, 1.0))
            d = ahead - here
            normal = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d[:2]) or 1.0)
            if normal[1] < 0 or (normal[1] == 0 and normal[0] < 0):
                normal = -normal
            # Far enough along the normal that the card's nearest corner clears the line.
            reach = abs(normal[0]) * tag.width / 2 + abs(normal[1]) * tag.height / 2
            return here + side * normal * (reach + width / 100 + 0.1)

        # Where it comes to rest: near the middle, on the side and at the point where it covers the fewest labels
        # already on the map.
        taken = self._taken()
        best = None
        for f in self.ARROW_LABEL_RESTS:
            for side in (1.0, -1.0):
                tag.move_to(at(f, side))
                cost = sum(_overlap(_bbox(tag, 0.04), t) for t in taken)
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, f, side)
        _, rest, side = best

        def ride(m, alpha: float) -> None:
            m.move_to(at(min(alpha, rest), side))
            m.set_opacity(min(1.0, alpha * 6))

        ride(tag, 1.0)
        taken.append(_bbox(tag, 0.04))
        ride(tag, 0.0)
        drawing = AnimationGroup(Create(edge), Create(line), UpdateFromAlphaFunc(tag, ride))
        return AnimationGroup(drawing, FadeIn(tip), lag_ratio=0.85)

    # Where along its arrow a riding label may come to rest, the most wanted first (its middle).
    ARROW_LABEL_RESTS = (0.5, 0.4, 0.6, 0.3, 0.7)

    # ---------------- historical borders (historical.py) ----------------
    def empire(self, name: str, year: int, color: str | None = None, opacity: float = 0.42, label: str | None = None):
        """A state as it stood in a year, filled on the map with its border and its name (the Mughal Empire in
        1600, the Maurya Empire under Ashoka): the historical-basemaps map nearest that year. Nothing (and a note in
        SKIPPED) when the state or the map cannot be found."""
        import historical

        try:
            found = historical.empire(name, int(year))
        except Exception as error:  # noqa: BLE001
            found = None
            SKIPPED.append(f"historical map for {name!r}: {type(error).__name__}: {error}"[:300])
        if not found:
            SKIPPED.append(f"no state named {name!r} on the historical map of {year}")
            return None
        shape, map_name, map_year = found
        USED_DRAWINGS.add("historical:" + map_name)
        color = color or P.ROSE
        piece = _valid(shape).intersection(_box(self.lonlat_bounds(margin=0.9)))
        if piece.is_empty:
            SKIPPED.append(f"{map_name} ({map_year}) lies outside this map")
            return None
        fill = self.frame.poly(piece, simplify=0.006, min_area=0.002, fill_color=color, fill_opacity=opacity,
                               stroke_width=0)
        edge = self.frame.poly(piece, simplify=0.006, min_area=0.002, fill_opacity=0, stroke_color=color,
                               stroke_width=2.6)
        _art(fill)
        _art(edge)
        fill.set_z_index(Z_FILL + 0.5)
        edge.set_z_index(Z_OUTLINE + 0.5)
        when = f"{-int(year)} BC" if int(year) < 0 else f"{int(year)}"
        words = f"{label or name} ({when})"
        tag = self._map_text(words, 19, color)
        shown = self.frame.project_geom(piece)
        inside = shown.representative_point() if not shown.is_empty else None
        point = np.array([inside.x, inside.y, 0.0]) if inside is not None else np.array([*self.MAP_CENTER, 0.0])
        lead = self.place_label(tag, point, 0.0, UP, reserve_point=False)
        tag.set_z_index(Z_MARK)
        parts = [FadeIn(fill), Create(edge), FadeIn(tag)]
        if lead is not None:
            lead.set_z_index(Z_MARK)
            parts.append(Create(lead))
        return AnimationGroup(*parts, lag_ratio=0.35)

    # ---------------- relief ----------------
    RELIEF_KINDS = ("Range/mtn", "Plateau")
    RELIEF_STEP = 0.32          # the hill marks' spacing, in scene units
    RELIEF_MOST = 700
    RELIEF_MIN_AREA = 0.06      # a range smaller than this on screen is left out
    RELIEF_NAMES = 4            # how many ranges are named when none were asked for

    def relief(self, names=None, label: bool = True):
        """The mountains and plateaus on the map, as an atlas draws them in line: each range shaded and filled with
        small hill marks (vector, so the phone draws it like every other line), and named. `names`: only these
        (the Himalayas, the Western Ghats); otherwise every range in view."""
        from shapely.geometry import Point

        bounds = _box(self.lonlat_bounds())
        wanted = {_norm(n) for n in (names or [])}
        ranges = []
        for attrs, geom in _records("geography_regions_polys", "physical", "10m"):
            if attrs.get("FEATURECLA") not in self.RELIEF_KINDS or not geom.intersects(bounds):
                continue
            name = str(attrs.get("NAME") or "")
            if wanted and not any(w and (w in _norm(name) or _norm(name) in w) for w in wanted):
                continue
            ranges.append((name, _valid(geom).intersection(bounds), attrs.get("FEATURECLA")))
        # A range Natural Earth does not have (Sri Lanka's Central Highlands): the lecture's own (set_places).
        for name in names or []:
            shape = _own_shape(_norm(name)) if own_place(name) else None
            if shape is not None and shape.intersects(bounds):
                ranges = [r for r in ranges if _norm(r[0]) != _norm(name)]
                ranges.append((own_place(name)["_name"], shape.intersection(bounds), "Range/mtn"))
        if not ranges:
            SKIPPED.append(f"no mountains to draw here{' named ' + ', '.join(names) if names else ''}")
            return None
        ink = readable(P.MOUNT, P.BG, 1.6)
        shade, marks, tags = VGroup(), VGroup(), VGroup()
        count = 0
        # The ranges big enough to see, largest first; named only the largest few unless asked for by name.
        sized = sorted(((self.frame.project_geom(g).area, n, g, k) for n, g, k in ranges), key=lambda r: -r[0])
        ranges = [(n, g, k) for a, n, g, k in sized if a >= self.RELIEF_MIN_AREA or wanted]
        # Named first: the ranges on the land the map is about (the Himalayas on a map of India), then the largest.
        focus = self.focus
        by_note = sorted(ranges, key=lambda r: not r[1].intersects(focus))
        named = {n for n, _, _ in by_note[:len(ranges) if wanted else self.RELIEF_NAMES]}
        share = max(10, self.RELIEF_MOST // max(1, len(ranges)))
        for name, geom, kind in ranges:
            shape = self.frame.poly(geom, simplify=0.01, min_area=0.004, fill_color=P.MOUNT, fill_opacity=0.22,
                                    stroke_width=0)
            if not len(shape):
                continue
            shade.add(shape)
            shown = self.frame.project_geom(geom)
            x0, y0, x1, y1 = shown.bounds
            # Spaced so each range gets its share of the marks: a vast plateau sparser, a thin range as drawn.
            step = max(self.RELIEF_STEP * (1.4 if kind == "Plateau" else 1.0), math.sqrt(shown.area / share))
            mine = 0
            for row, y in enumerate(np.arange(y0 + step / 2, y1, step * 0.8)):
                for x in np.arange(x0 + step / 2 + (step / 2 if row % 2 else 0), x1, step):
                    if count >= self.RELIEF_MOST or mine >= share or not shown.contains(Point(x, y)):
                        continue
                    mine += 1
                    # A hill: a small peak (a plateau: a flat-topped one).
                    w, h = step * 0.32, step * 0.24
                    if kind == "Plateau":
                        pts = [[x - w, y - h / 2, 0], [x - w / 3, y + h / 2, 0], [x + w / 3, y + h / 2, 0],
                               [x + w, y - h / 2, 0]]
                    else:
                        pts = [[x - w, y - h / 2, 0], [x, y + h / 2, 0], [x + w, y - h / 2, 0]]
                    hill = VMobject(stroke_color=ink, stroke_width=1.6, stroke_opacity=0.85)
                    hill.set_points_as_corners(np.array(pts, dtype=float))
                    marks.add(hill)
                    count += 1
            if label and name in named and shape.width > 0.8:
                tag = T(name.replace(" Mts.", " Mountains").replace(" Ra.", " Range"), 15, ink, slant=ITALIC)
                inside = shown.representative_point()
                tag.move_to([inside.x, inside.y, 0])
                # Clear of the caption and the title strip.
                low, high = CAPTION_Y + 0.5, config.frame_height / 2 - 0.55
                tag.shift(UP * (max(0.0, low - tag.get_bottom()[1]) - max(0.0, tag.get_top()[1] - high)))
                if not any(_overlap(_bbox(tag, 0.04), t) for t in self._taken()):
                    self._taken().append(_bbox(tag, 0.04))
                    tags.add(tag)
        for part in (*shade.get_family(), *marks.get_family()):
            part._art_decorated = True
        shade.set_z_index(Z_FILL - 0.5)
        marks.set_z_index(Z_LINES + 0.5)
        tags.set_z_index(Z_MARK - 1)
        return AnimationGroup(FadeIn(shade), LaggedStart(*[FadeIn(m) for m in marks], lag_ratio=0.01),
                              FadeIn(tags), lag_ratio=0.3)

    # ---------------- locator inset ----------------
    # A map zoomed in to a few places gets a small map in its corner: the whole country (or area), with a box
    # where the big map is, so where on Earth this is stays clear. Only when the view is under this share of it.
    LOCATOR_BELOW = 0.5
    LOCATOR_SIZE = 1.55

    def locator(self):
        """The inset (a VGroup), or None when the map is not zoomed in."""
        if not self.FRAME_BBOX or os.environ.get("PANIM_LOCATOR") == "0":
            return None
        context = self.mainland
        lon0, lat0, lon1, lat1 = self.FRAME_BBOX
        c0, d0, c1, d1 = context.bounds
        share = max((lon1 - lon0) / max(c1 - c0, 1e-6), (lat1 - lat0) / max(d1 - d0, 1e-6))
        if share >= self.LOCATOR_BELOW:
            return None
        size = self.LOCATOR_SIZE
        left = -config.frame_width / 2 + 0.25
        bottom = -config.frame_height / 2 + 0.75
        centre = (left + size / 2 + 0.1, bottom + size / 2 + 0.1)
        small = MapFrame(context, center=centre, height=size, width=size, clip=False)
        land = small.poly(context, simplify=0.01, min_area=0.0005, fill_color=TH.get("land") or P.SAND,
                          fill_opacity=0.9 if TH.get("land") else 0.35, stroke_color=P.MUTED, stroke_width=1.2)
        view = _box(self.FRAME_BBOX)
        here = small.poly(view, simplify=0.0, min_area=0.0, fill_color=P.ROSE, fill_opacity=0.25,
                          stroke_color=role("highlight"), stroke_width=2.4)
        if not len(here):
            return None
        # Never smaller than a dot: a battlefield in a big country is still seen.
        if here.width < 0.12:
            here = VGroup(Square(0.12, stroke_color=role("highlight"), stroke_width=2.4, fill_color=P.ROSE,
                                 fill_opacity=0.25).move_to(here.get_center()))
        both = VGroup(land, here)
        card = RoundedRectangle(corner_radius=0.08, width=both.width + 0.24, height=both.height + 0.24,
                                fill_color=P.BG, fill_opacity=0.88, stroke_color=P.MUTED, stroke_width=1.2)
        card.move_to(both)
        for part in card.get_family():
            part._art_decorated = True
        inset = VGroup(card, land, here)
        # Kept inside the frame, above the caption.
        inset.shift(RIGHT * max(0.0, left - card.get_left()[0]) + UP * max(0.0, bottom - card.get_bottom()[1]))
        inset.set_z_index(Z_MARK - 1)
        self._taken().append(_bbox(inset, 0.05))
        return inset

    @staticmethod
    def _map_text(words: str, size: float, color: str):
        """A map label that reads over any coastline or border: the words in the board's ink, bold, on a
        paper-coloured card edged in the marker's colour."""
        text = T(str(words), size, P.CREAM, weight=BOLD)
        card = RoundedRectangle(corner_radius=0.08, width=text.width + 0.22, height=text.height + 0.14,
                                fill_color=P.BG, fill_opacity=0.9, stroke_color=color, stroke_width=1.6)
        card.move_to(text)
        for part in card.get_family():
            part._art_decorated = True            # a backing, not a thing: no hatching or sheen on it
        return VGroup(card, text)

    def marker(self, where, label: str | None = None, color: str | None = None, d=RIGHT, size: float = 21,
               r: float = 0.075, picture=None):
        """Dot, halo and label at a place name or (lon, lat); with a picture (a photo, a figure, a drawing of what
        is there) above the label. The label goes where it overlaps nothing on the map (place_label), on a card so
        borders and coastlines never cross its words."""
        color = color or P.CREAM
        p = self.frame.pt(*self.at(where))
        dot = Dot(p, radius=r, color=color)
        halo = Circle(radius=r * 2.2, color=color, stroke_width=2.2, stroke_opacity=0.8).move_to(p)
        text = self._map_text(label or (where if isinstance(where, str) else ""), size, color)
        pic = self._picture(picture, 0.7, 1.1) if picture else None
        tag = group_of(pic, text).arrange(DOWN, buff=0.06) if pic is not None else text
        lead = self.place_label(tag, p, r * 2.2 + 0.05, d)
        if pic is not None and tag.get_center()[1] < p[1]:
            # Set below the place: its name above the picture, next to the dot (the same box, so still clear).
            text.align_to(tag, UP)
            pic.next_to(text, DOWN, buff=0.06)
        group = group_of(halo, dot, tag, *([lead] if lead is not None else []))
        group.set_z_index(Z_MARK)
        self.name_part(label or (where if isinstance(where, str) else ""), group,
                       act=lambda group=group, dot=dot: self._map_look(group, dot.get_center()))
        return group

    def reserve_places(self, places, gap: float = 0.13) -> None:
        """Speak for these places' dots before any label is placed (all a chapter will mark), so a label set now
        never covers a marker that comes later. A place the map cannot find is passed over."""
        for where in places:
            try:
                q = self.frame.pt(*self.at(where))
            except Exception:  # noqa: BLE001 -- unknown here: its marker reports it when it comes
                continue
            self._taken().append((q[0] - gap, q[1] - gap, q[0] + gap, q[1] + gap))

    def _taken(self) -> list:
        if not hasattr(self, "_map_taken"):
            self._map_taken = []
        return self._map_taken

    def place_label(self, tag, point, gap: float, prefer=RIGHT, reserve_point: bool = True):
        """Put a map label (words, or a picture with its words) beside `point` where it overlaps no label, picture
        or marker already on the map, and stays on the map (clear of the panel and the frame's edge): beside it
        first (the preferred side, then right, left, above, below, the corners), then a little further out with a
        line back to the point. If nowhere is clear, the place it overlaps least. Returns that line, or None."""
        taken = self._taken()
        point = np.array(point, dtype=float)
        right = getattr(self, "_map_right", None)
        left_edge, right_edge = -config.frame_width / 2 + 0.15, right() if right else PANEL_X - 0.08
        bottom, top = -config.frame_height / 2 + 0.55, config.frame_height / 2 - 0.45   # caption, title strip
        sides = []
        for v in (prefer, RIGHT, LEFT, UP, DOWN, UR, DR, UL, DL):
            v = np.array(v, dtype=float)
            if not any(np.allclose(v, x) for x in sides):
                sides.append(v)
        best = None
        for reach in (0.0, 0.35, 0.8, 1.3):
            for v in sides:
                u = v / np.linalg.norm(v)
                # The label's near edge (or corner) `gap + reach` from the point, along u.
                half = np.array([tag.width / 2, tag.height / 2, 0])
                centre = point + u * (gap + reach) + np.sign(np.round(u, 6)) * half
                tag.move_to(centre)
                box = _bbox(tag, 0.04)
                out = (max(0.0, left_edge - box[0]) + max(0.0, box[2] - right_edge)
                       + max(0.0, bottom - box[1]) + max(0.0, box[3] - top))
                cost = sum(_overlap(box, t) for t in taken) + 10 * out
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, centre, reach)
                if cost == 0:
                    break
            if best[0] == 0:
                break
        _, centre, reach = best
        tag.move_to(centre)
        box = _bbox(tag, 0.04)
        taken.append(box)
        if reserve_point:
            taken.append((point[0] - gap, point[1] - gap, point[0] + gap, point[1] + gap))
        lead = None
        if reach:
            # A thin line from the point to the label's nearest edge, so a label set further out still says where.
            lo, hi = tag.get_corner(DL), tag.get_corner(UR)
            near = np.array([min(max(point[0], lo[0]), hi[0]), min(max(point[1], lo[1]), hi[1]), 0.0])
            lead = Line(point, near, stroke_color=P.MUTED, stroke_width=1.5, stroke_opacity=0.8, buff=gap * 0.6)
        register = getattr(self, "_name_on_map", None)
        if register is not None:
            register(tag, lead, box)
        return lead

    # A map shows at most this many place names at once: as the next is named, the oldest name goes (its dot or
    # its shading stays), and the room it took is free again. The map stays readable however many places a chapter
    # names, and each name sits near its place.
    MAP_NAMES = 4

    def _name_on_map(self, tag, lead, box) -> None:
        names = self.__dict__.setdefault("_map_names", [])
        names.append((tag, lead, box))
        while len(names) > self.MAP_NAMES:
            old, old_lead, old_box = names.pop(0)
            taken = self._taken()
            if old_box in taken:
                taken.remove(old_box)
            going = self.__dict__.setdefault("_map_tidy", [])
            going += [old, *([old_lead] if old_lead is not None else [])]

    def _map_tidy_out(self, anims) -> list:
        """Fade-outs for the oldest names on the map (_name_on_map), as this line names new ones: the ones on the
        screen and not taken away by the line already."""
        going = self.__dict__.pop("_map_tidy", [])
        on = {id(m) for top in self.mobjects for m in top.get_family()}
        leaving = set()
        todo = list(anims)
        while todo:
            anim = todo.pop()
            todo.extend(getattr(anim, "animations", None) or [])
            if getattr(anim, "remover", False) and getattr(anim, "mobject", None) is not None:
                leaving.update(id(m) for m in anim.mobject.get_family())
        return [FadeOut(m, run_time=0.5) for m in going if id(m) in on and id(m) not in leaving]

    def pop(self, m: VGroup):
        return LaggedStart(GrowFromCenter(m[1]), GrowFromCenter(m[0]), FadeIn(m[2], shift=UP * 0.05),
                           *[FadeIn(x) for x in m[3:]], lag_ratio=0.25)

    def mark(self, where, label=None, color=None, d=RIGHT, picture=None):
        """Build and pop a marker: the one-call form used by beat scripts."""
        return self.pop(self.marker(where, label, color, d, picture=picture))

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
                if -config.frame_width / 2 + 0.2 < x < self._map_right() - 0.02 and abs(y) < config.frame_height / 2 - 0.2]
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
            self._taken().append(_bbox(tag, 0.04))
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
        group = Group()
        for spot in spots:
            try:
                mob = icon_mob(name, color, height=size)
            except KeyError:
                # No picture of it could be made: a dot marks the place.
                mob = Dot(radius=0.09, color=role(color or "accent"))
            mob.move_to(self.frame.pt(*self.at(spot)))
            group.add(mob)
        if label:
            tag = T(label, 14, role(color or "ink"), weight=BOLD).next_to(group[0], DOWN, buff=0.06)
            group.add(tag)
        group.set_z_index(Z_MARK + 1)
        return LaggedStart(*[GrowFromCenter(m) for m in group], lag_ratio=0.2)

    # ---------------- the map's camera: in on a place as the narration names it ----------------
    # A place or an area already on the map, named again, is looked at: on a line that draws nothing new on the map
    # the map moves in on it (MAP_PUSH times, the place brought toward the middle), the rest of the map dims round
    # a box on it, an area's border is traced and a place's dot sends out a ripple; by the end of the line the map is
    # back as it was, so the next line's places and labels are set on the map as it is.
    MAP_PUSH = 1.4
    MAP_VEIL = 0.5           # how dark the rest of the map goes while a place is looked at

    def _map_showing(self) -> bool:
        return bool(getattr(self, "_map_on", False)) and getattr(self, "stage_body", None) is None \
            and not getattr(self, "board_mode", False)

    def _map_region(self) -> tuple:
        """(x0, y0, x1, y1) of the map's part of the frame."""
        cx, cy = self.MAP_CENTER
        right = self._map_right()
        return (-config.frame_width / 2, cy - self.MAP_SIZE[0] / 2 - 0.2, right, cy + self.MAP_SIZE[0] / 2 + 0.2)

    def _map_content(self) -> list:
        """What on the screen is the map (its land, lines, fills, places and labels): what its camera moves."""
        skip = {id(m) for m in [getattr(self, "cap", None), getattr(self, "chrome", None), getattr(self, "panel", None),
                                getattr(self, "_inset", None), getattr(self, "_map_mask", None),
                                *getattr(self, "panel_items", []), *getattr(self, "_map_spot", [])] if m is not None}
        out = []
        for m in self.mobjects:
            z = float(getattr(m, "z_index", 0) or 0)
            if id(m) in skip or z <= Z_BACK + 1 or z >= Z_PANEL or getattr(m, "is_map_cover", False):
                continue
            if not len(m.get_family()) or (m.width < 1e-3 and m.height < 1e-3):
                continue
            out.append(m)
        return out

    # Whether the map also moves in on the place it looks at (off: the rest of the map is shaded, nothing moves).
    MAP_PUSH_IN = False

    def _map_look(self, mob, point, area: bool = False):
        """Look at a place or an area on the map (see above). None when the map is not what is on the screen."""
        if not self._map_showing() or mob is None or not any(mob is m for top in self.mobjects
                                                              for m in top.get_family()):
            return None
        if getattr(self, "_map_spot", None):
            return None                          # one look a line: a second would draw over the first
        import stem

        point = np.array(point, dtype=float)
        x0, y0, x1, y1 = self._map_region()
        middle = np.array([*self.MAP_CENTER, 0.0])
        push, moved = None, (lambda p: np.array(p, dtype=float))
        if self.MAP_PUSH_IN and not getattr(self, "_line_draws", False):
            f = self.MAP_PUSH
            shift = (middle - point) * 0.6
            moving = self._map_content()
            if moving:
                push = AnimationGroup(*[stem._moving(m.animate.scale(f, about_point=point).shift(shift))
                                        for m in moving])
                self._map_pushed = (f, point, shift, moving)
                moved = lambda p, f=f, point=point, shift=shift: (np.array(p, dtype=float) - point) * f + point + shift  # noqa: E731
                if getattr(self, "_map_mask", None) is None and not getattr(self, "_wide", False):
                    # The panel's side of the frame, in the board's colour under the panel: the map moved in on
                    # stays on its own side.
                    mask = Rectangle(width=config.frame_width / 2 - x1 + 0.5, height=config.frame_height + 1,
                                     fill_color=P.BG, fill_opacity=1, stroke_width=0)
                    mask.move_to([(x1 + config.frame_width / 2 + 0.5) / 2, 0, 0]).set_z_index(Z_PANEL - 0.5)
                    mask._art_decorated = True
                    self._map_mask = mask
                    self.add(mask)
        lo, hi = moved(mob.get_corner(DL)), moved(mob.get_corner(UR))
        pad = 0.25
        bx0, by0 = max(lo[0] - pad, x0), max(lo[1] - pad, y0)
        bx1, by1 = min(hi[0] + pad, x1), min(hi[1] + pad, y1)
        if bx1 - bx0 < 0.3 or by1 - by0 < 0.3:
            c = moved(point)
            bx0, by0, bx1, by1 = c[0] - 0.5, c[1] - 0.5, c[0] + 0.5, c[1] + 0.5
        # The rest of the map dimmed round a box on the place: four panels of the board's colour.
        veil = VGroup(*[Rectangle(width=max(w, 0.01), height=max(h, 0.01), fill_color=P.BG, fill_opacity=self.MAP_VEIL,
                                  stroke_width=0).move_to([cx, cy, 0])
                        for w, h, cx, cy in ((bx0 - x0, y1 - y0, (x0 + bx0) / 2, (y0 + y1) / 2),
                                             (x1 - bx1, y1 - y0, (bx1 + x1) / 2, (y0 + y1) / 2),
                                             (bx1 - bx0, y1 - by1, (bx0 + bx1) / 2, (by1 + y1) / 2),
                                             (bx1 - bx0, by0 - y0, (bx0 + bx1) / 2, (y0 + by0) / 2))
                        if w > 0.01 and h > 0.01])
        frame = hud_frame(bx1 - bx0, by1 - by0).move_to([(bx0 + bx1) / 2, (by0 + by1) / 2, 0])
        veil.set_z_index(Z_MARK + 3)
        frame.set_z_index(Z_MARK + 4)
        for part in [*veil.get_family(), *frame.get_family()]:
            part._art_decorated = True
        # The veil comes down and the frame locks on to the place, in from larger.
        shows = [FadeIn(veil), FadeIn(frame, scale=1.35)]
        spot = [veil, frame]
        if area:
            # The area's border traced in the highlight colour.
            edge = mob.copy().set_fill(opacity=0).set_stroke(role("highlight"), width=4.5, opacity=1)
            for part in edge.get_family():
                if isinstance(part, Text):
                    part.set_opacity(0)
            edge.scale(self._map_pushed[0] if push is not None else 1.0, about_point=point)
            if push is not None:
                edge.shift(self._map_pushed[2])
            edge.set_z_index(Z_MARK + 4)
            shows.append(Create(edge))
            spot.append(edge)
        else:
            c = moved(point)
            # Two rings ripple out from the place, one after the other.
            for k in range(2):
                ring = Circle(radius=0.16, color=role("highlight"), stroke_width=4 - k).move_to(c).set_z_index(Z_MARK + 4)
                shows.append(Succession(GrowFromCenter(ring, run_time=0.3), FadeOut(ring, scale=2.8 + k)))
        self._map_spot = spot
        lit = AnimationGroup(*shows, lag_ratio=0.15)
        lit.panim_sfx = "ping"
        both = AnimationGroup(push, lit, lag_ratio=1.0) if push is not None else lit
        if push is not None:
            both.panim_sfx = "zoom"
        return both

    def _map_return(self) -> list:
        """The map back as it was at the end of a line that looked at a place: the veil and box gone, the map moved
        back out."""
        anims = [FadeOut(m) for m in getattr(self, "_map_spot", None) or [] if any(m is x for x in self.mobjects)]
        self._map_spot = []
        pushed = getattr(self, "_map_pushed", None)
        self._map_pushed = None
        if pushed is not None:
            import stem

            f, point, shift, moving = pushed
            on = {id(m) for m in self.mobjects}
            anims += [stem._moving(m.animate.shift(-shift).scale(1 / f, about_point=point)) for m in moving
                      if id(m) in on]
        return anims

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


# The pictures these build write their words in the art style's font (artstyle.drawing); titles keep the template's.
import artstyle as _artstyle  # noqa: E402

_artstyle.drawn_by(Lecture, ("diagram", "plot", "process", "molecule", "big_timeline", "network", "timeline",
                             "compare"))
_artstyle.drawn_by(MapLecture, ("journey", "marker", "mark", "route", "unit", "icon", "flow", "graticule", "clock",
                                         "empire", "locator", "relief"))

__all__ = [name for name in globals() if not name.startswith("_") or name == "_box"]
