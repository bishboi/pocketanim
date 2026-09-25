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
    config.background_color = TH["bg"]
    return TH


use_style(os.environ.get("LECTURE_STYLE", "atlas"))

# ════════════════════════════════════════════════════════════════════════
#  TEXT
# ════════════════════════════════════════════════════════════════════════


def T(text: str, size: float = 24, color: str | None = None, font: str | None = None,
      weight=NORMAL, **kw) -> Text:
    """Text in the style's body font. Characters a font lacks are swapped."""
    font = font or TH["sans"]
    if font == "Permanent Marker":
        text = text.replace("≈", "~")
    return Text(text, font=font, font_size=size, color=color or P.CREAM, weight=weight, **kw)


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


def narrate(text: str) -> tuple[str | None, float]:
    """(wav path or None, seconds) for one line, cached by its spoken text.

    PANIM_VOICE picks the voice: `auto` (espeak-ng if installed, else
    silent), `espeak`, `silent`, or `kokoro:<voice>` for the harness's
    Kokoro. A voice that is missing is an estimate, not a crash: the beat
    still holds for as long as the sentence would take.
    """
    spoken = speechify(text)
    mode = os.environ.get("PANIM_VOICE", "auto")
    if mode == "silent":
        return None, estimate_seconds(spoken)
    digest = hashlib.md5(f"{mode}|{spoken}".encode()).hexdigest()[:12]
    out = audio_dir() / f"{digest}.wav"
    if out.exists() and out.stat().st_size > 44:
        return str(out), _wav_seconds(out)

    if mode.startswith("kokoro"):
        voice = mode.split(":", 1)[1] if ":" in mode else TH.get("voice", "af_sarah")
        script = HERE.parent / "scripts" / "kokoro_speak.py"
        try:
            import json

            job = json.dumps({"voice": voice, "lines": [spoken], "out": str(out)})
            result = subprocess.run([sys.executable, str(script)], input=job, capture_output=True,
                                    text=True, timeout=300)
            reply = json.loads(result.stdout.strip().splitlines()[-1])
            if reply.get("ok") and out.exists():
                return str(out), _wav_seconds(out)
        except Exception:  # noqa: BLE001 -- fall through to espeak or silence
            pass

    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak and mode in ("auto", "espeak") or (espeak and mode.startswith("kokoro")):
        voice = os.environ.get("LECTURE_VOICE") or _espeak_voice(espeak)
        raw = out.with_name(out.stem + "_raw.wav")
        try:
            subprocess.run([espeak, "-v", voice, "-s", "148", "-p", "42", "-g", "4", "-w", str(raw), spoken],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            if shutil.which("ffmpeg"):
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                     "highpass=f=70,lowpass=f=7500,aecho=0.8:0.6:35:0.12,loudnorm=I=-17:TP=-2,apad=pad_dur=0.1",
                     "-ar", "44100", "-ac", "2", str(out)],
                    check=True, timeout=120,
                )
                raw.unlink(missing_ok=True)
            else:
                raw.replace(out)
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
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


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


def place(name: str, country_name: str | None = None) -> tuple[float, float]:
    """(lon, lat) of a populated place; the most populous match wins."""
    wanted = _norm(name)
    scope = _norm(country_name) if country_name else None
    best = None
    for attrs, _geom in _records("populated_places"):
        if wanted not in (_norm(attrs.get("NAME")), _norm(attrs.get("NAMEASCII")), _norm(attrs.get("NAME_EN"))):
            continue
        if scope and scope not in (_norm(attrs.get("ADM0NAME")), _norm(attrs.get("SOV0NAME")), _norm(attrs.get("ADM0_A3"))):
            continue
        pop = float(attrs.get("POP_MAX") or 0)
        if best is None or pop > best[0]:
            best = (pop, float(attrs["LONGITUDE"]), float(attrs["LATITUDE"]))
    if best is None:
        raise KeyError(f"no place named {name!r}" + (f" in {country_name}" if country_name else ""))
    return best[1], best[2]


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

    def setup(self):
        self.cap = None
        self.panel_items = VGroup()
        self.panel_y = 2.35
        self.chrome = VGroup()
        back = backdrop()
        if len(back):
            self.add(back)
        self.section(self.SECTION)

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
        wav, seconds = narrate(text)
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
        t = fit(T("\n".join(lines), 19, TH["cap_fg"], line_spacing=0.9), 13.2)
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
        r = Rectangle(width=6.0, height=6.55, fill_color=P.PANEL, fill_opacity=0.94, stroke_width=0)
        r.move_to(RIGHT * 4.05 + UP * 0.35)
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
            pts = [np.array([1.12 + 0.02 * np.sin(i * 1.7), 3.5 - i * 0.26, 0]) for i in range(26)]
            parts = [VMobject(stroke_color=P.CREAM, stroke_width=3.2).set_points_smoothly(pts)]
        else:  # dashed
            parts = [DashedVMobject(r.copy().set_fill(opacity=0).set_stroke(P.MUTED, 1.5), num_dashes=90)]
        group = VGroup(*parts)
        group.set_z_index(Z_PANEL)
        return group

    def reveal(self, group, text_part=None):
        """The style's entrance for panel content."""
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
        t = T(title.upper() if TH["upper"] else title, 34, P.TITLE, font=TH["serif"], weight=BOLD)
        t.move_to(RIGHT * TEXT_X + UP * 3.05, aligned_edge=LEFT)
        if t.width > 5.2:
            t.scale_to_fit_width(5.2).align_to(RIGHT * TEXT_X, LEFT)
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
        if len(old):
            return AnimationGroup(FadeOut(old), show, lag_ratio=0.5)
        return show

    def _stack(self, group, gap: float):
        group.move_to(RIGHT * TEXT_X + UP * self.panel_y, aligned_edge=UL)
        self.panel_y = group.get_bottom()[1] - gap
        group.set_z_index(Z_PANEL_TEXT)
        self.panel_items.add(group)
        return group

    def fact(self, text: str, color: str | None = None, bullet: str | None = None, size: float = 20):
        """A bulleted line in the panel, wrapped at 36 characters."""
        dot = Dot(radius=0.05, color=bullet or P.SAND)
        t = fit(T(wrap(text, 36), size, color or P.CREAM, line_spacing=0.85), 4.95)
        t.next_to(dot, RIGHT, buff=0.18, aligned_edge=UP)
        dot.shift(DOWN * 0.1)
        group = self._stack(VGroup(dot, t), 0.22)
        return self.reveal(group, t)

    def big_stat(self, value: str, label: str, color: str | None = None):
        """A large number with a small label under it."""
        v = fit(T(value, 44, color or P.GOLD, font=TH["serif"], weight=BOLD), 5.1)
        lab = fit(T(wrap(label, 40), 17, P.MUTED), TEXT_W)
        lab.next_to(v, DOWN, aligned_edge=LEFT, buff=0.08)
        group = self._stack(VGroup(v, lab), 0.3)
        return self.reveal(group, v)

    def bar_chart(self, items, color: str | None = None, unit: str = "", width: float = 3.0):
        """Horizontal bars in the panel, each growing from a shared axis."""
        items = list(items)[:7]
        top = max((float(v) for _, v in items), default=1.0) or 1.0
        labels = [fit(T(str(name), 16, P.CREAM), 1.3) for name, _ in items]
        column = max((m.width for m in labels), default=0.5)
        axis_x = TEXT_X + column + 0.2
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
        return LaggedStart(*[AnimationGroup(FadeIn(r[0]), GrowFromEdge(r[1], LEFT), FadeIn(r[2]))
                             for r in rows], lag_ratio=0.2)

    def clear_panel(self):
        old = self.panel_items
        self.panel_items = VGroup()
        self.panel_y = 2.35
        return FadeOut(old) if len(old) else None

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

    def credits(self, line: str, note: str = "Some boundaries and figures are simplified or approximate for teaching.",
                seconds: float = 3.0) -> None:
        self.clear_caption()
        credit = fit(T(line, 14, P.MUTED), 13).move_to(DOWN * 2.3)
        small = fit(T(note, 13, P.MUTED), 13).next_to(credit, DOWN, buff=0.15)
        self.play(FadeIn(credit), FadeIn(small), run_time=1.0)
        self.wait(seconds)
        self.play(FadeOut(credit), FadeOut(small), run_time=0.8)

    def outro_fade(self, run_time: float = 1.0) -> None:
        """Fade everything a chapter added; keep the backdrop and chrome."""
        going = self.on_stage()
        self.clear_caption()
        if going:
            self.play(*[FadeOut(m) for m in going], run_time=run_time)
        self.panel_items = VGroup()
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

    @property
    def frame(self) -> MapFrame:
        if not hasattr(self, "_frame"):
            height, width = self.MAP_SIZE
            self._frame = MapFrame(self.mainland, center=self.MAP_CENTER, height=height, width=width)
        return self._frame

    def lonlat_bounds(self, margin=None):
        lon0, lat0, lon1, lat1 = self.focus.bounds
        pad = margin if margin is not None else max(lon1 - lon0, lat1 - lat0) * 0.45
        return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)

    def at(self, where) -> tuple[float, float]:
        """A place name, or a (lon, lat) pair, as (lon, lat)."""
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


def _box(bounds):
    from shapely.geometry import box

    return box(*bounds)


__all__ = [name for name in globals() if not name.startswith("_") or name == "_box"]
