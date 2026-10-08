"""Animated SVG drawings: SMIL animation evaluated frame by frame, drawn as Manim shapes the phone plays.

An animated SVG says how its parts move with SMIL elements inside it: <animateTransform> (rotate, translate,
scale, skew), <animate> on opacity, colours, a circle's radius, a dash offset. Browsers play them; Manim ignores
them and draws the first frame. This module reads the animation and plays it on Manim's shapes, so a diagram's
drawing moves on the board, and the exporter bakes it into a clip of shapes for the phone (export_dsl's bake):
the phone never gets a video of it.

Two sources:
  * drawings that come animated: the Meteocons weather set (data/icons/meteocons.json: rain falling, a sun
    turning, lightning flashing, snow drifting, a thermometer filling), and any SVG with SMIL in it;
  * library drawings, given a motion that suits what they are (MOTIONS): a gear spins, a heart beats, a tree
    sways, a boat bobs, a flame flickers, a bell shakes. The motion is written into the drawing as SMIL
    (`animated_svg` returns the file), then played the same way.

Every motion repeats in a whole number of frames that divides LOOP (4 s at 30 fps): the exporter stores a
repeating clip once per period and replays it (export_dsl._loop), so a drawing that moves all through a long
explanation costs one period of frames, not one per second it is on the board.

    python harness/lecture/animsvg.py rain gear heart   # which drawing and motion each word gets
"""

from __future__ import annotations

import copy
import math
import re
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
FPS = 30
LOOP = 120                                  # frames every motion's period divides: 4 seconds
# Periods a motion may take (frames): the divisors of LOOP, and whole multiples of it for slow ones.
PERIODS = sorted({d for d in range(1, LOOP + 1) if LOOP % d == 0} | {2 * LOOP, 3 * LOOP})
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
HIDDEN = {"defs", "symbol", "clipPath", "mask", "pattern", "marker", "linearGradient", "radialGradient", "title",
          "desc", "metadata", "style", "script", "filter"}
ANIMATIONS = {"animate", "animateTransform", "set", "animateMotion", "animateColor"}
# Attributes the shapes follow without being drawn again (the rest redraw the frame from its SVG).
QUICK = {"transform", "opacity", "fill-opacity", "stroke-opacity", "fill", "stroke", "stroke-width", "r", "rx",
         "ry", "cx", "cy", "x", "y", "stroke-dashoffset"}

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK)


def local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# --------------------------------------------------------------------------------------------------------------
# Motions written into a drawing that has none: what moves, how, and about which point of it.

MOTIONS = {
    # name: (SMIL animateTransform type or "opacity", values, keyTimes, keySplines, period in frames, pivot)
    "spin": [("rotate", "0; 360", None, None, 120, "centre")],
    "pulse": [("scale", "1; 1.13; 1; 1.07; 1", "0; .14; .3; .44; 1", None, 30, "centre")],
    "breathe": [("scale", "1; 1.05; 1", "0; .5; 1", ".45 0 .55 1; .45 0 .55 1", 120, "bottom")],
    "bob": [("translate", "0 0; 0 -0.06; 0 0", "0; .5; 1", ".45 0 .55 1; .45 0 .55 1", 60, "centre")],
    "sway": [("rotate", "-4; 4; -4", "0; .5; 1", ".45 0 .55 1; .45 0 .55 1", 120, "bottom")],
    "shake": [("rotate", "0; -9; 9; -9; 9; 0; 0", "0; .05; .1; .15; .2; .25; 1", None, 60, "top")],
    "flicker": [("scale", "1; 1.05; .98; 1.04; 1", "0; .25; .5; .75; 1", None, 30, "bottom"),
                ("opacity", "1; .82; 1; .9; 1", "0; .25; .5; .75; 1", None, 30, None)],
    "drift": [("translate", "0 0; 0.07 0; 0 0", "0; .5; 1", ".45 0 .55 1; .45 0 .55 1", 120, "centre")],
    "hop": [("translate", "0 0; 0 -0.12; 0 0; 0 0", "0; .2; .4; 1", ".2 0 .4 1; .6 0 .8 1; 0 0 1 1", 60, "centre")],
}

# What a drawing of a thing does, by the words in its name.
MOTION_WORDS = {
    "spin": "gear cog cogwheel wheel fan turbine windmill propeller rotor motor dynamo generator pinwheel "
            "centrifuge mill tyre tire roulette",
    "pulse": "heart pulse heartbeat cardiac",
    "breathe": "lung lungs balloon sponge stomach",
    "bob": "fish boat ship duck buoy bird bee butterfly insect plane airplane aeroplane rocket satellite drone "
           "helicopter jellyfish whale dolphin parrot eagle owl pigeon crow moth dragonfly submarine raft canoe",
    "sway": "tree plant flower grass crop wheat rice leaf palm seedling sapling corn maize forest bush reed kelp "
            "seaweed sunflower rose tulip cactus bamboo fern vine sugarcane mangrove",
    "shake": "bell alarm phone telephone earthquake rattle",
    "flicker": "fire flame candle torch bulb lamp lantern spark diya campfire bonfire match fireworks",
    "drift": "cloud clouds smoke fog mist steam vapour vapor",
    "hop": "frog rabbit kangaroo grasshopper cricket ball",
}
_WORD_MOTION = {w: m for m, words in MOTION_WORDS.items() for w in words.split()}

# Words that have an animated weather drawing (Meteocons), and which.
WEATHER = {
    "rain": "rain", "rainy": "rain", "raining": "rain", "rainfall": "rain", "precipitation": "rain",
    "monsoon": "rain", "shower": "rain", "showers": "rain", "drizzle": "drizzle",
    "storm": "thunderstorms", "thunderstorm": "thunderstorms", "thunder": "thunderstorms",
    "lightning": "lightning-bolt", "snow": "snow", "snowfall": "snow", "snowflake": "snowflake",
    "sleet": "sleet", "hail": "hail", "wind": "wind", "windy": "wind", "breeze": "wind", "gale": "wind",
    "sun": "clear-day", "sunny": "clear-day", "sunshine": "clear-day", "sunlight": "clear-day",
    "moon": "clear-night", "night": "clear-night", "cloud": "cloudy", "clouds": "cloudy", "cloudy": "cloudy",
    "overcast": "overcast", "fog": "fog", "mist": "mist", "haze": "haze", "smoke": "smoke", "dust": "dust",
    "tornado": "tornado", "hurricane": "hurricane", "cyclone": "hurricane", "typhoon": "hurricane",
    "thermometer": "thermometer", "temperature": "thermometer", "heat": "sun-hot",
    "hot": "sun-hot", "cold": "thermometer-colder", "humidity": "humidity", "raindrop": "raindrop",
    "raindrops": "raindrops", "water drop": "raindrop", "droplet": "raindrop", "barometer": "barometer",
    "pressure": "barometer", "compass": "compass", "sunrise": "sunrise", "sunset": "sunset",
    "rainbow": "rainbow", "evaporation": "sunrise", "condensation": "cloudy", "star": "star", "stars": "starry-night",
}


def motion_for(name: str) -> str | None:
    """The motion that suits a drawing of `name` (a word or a library id), or None: most things hold still."""
    words = re.findall(r"[a-z]+", str(name).lower().split(":", 1)[-1] if ":" in str(name) else str(name).lower())
    for word in words:
        for form in (word, word[:-1] if word.endswith("s") else word, word[:-2] if word.endswith("es") else word):
            if form in _WORD_MOTION:
                return _WORD_MOTION[form]
    return None


@lru_cache(maxsize=1)
def _meteocons() -> dict:
    path = HERE / "data" / "icons" / "meteocons.json"
    try:
        import json

        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def weather_icon(name: str) -> str | None:
    """The animated Meteocons drawing for a weather word ("rain", "a thunderstorm", "evaporation"), as its icon
    name, preferring the filled version (it shows on light boards as on dark ones), or None."""
    icons = _meteocons().get("icons") or {}
    if not icons:
        return None
    text = " ".join(re.findall(r"[a-z]+", str(name).lower().split(":")[-1]))
    if text.replace(" ", "-") in icons:
        hit = text.replace(" ", "-")
    else:
        hit = WEATHER.get(text) or next((WEATHER[w] for w in text.split() if w in WEATHER), None)
    if not hit:
        return None
    for candidate in (f"{hit}-fill", hit):
        if candidate in icons:
            return candidate
    return None


def weather_svg(icon: str) -> str:
    data = _meteocons()
    entry = data["icons"][icon]
    w, h = entry.get("width", data.get("width", 512)), entry.get("height", data.get("height", 512))
    return (f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK}" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{entry["body"]}</svg>')


# Colours a written figure may name instead of a hex value, so one SVG suits every board style (light or dark):
# INK is the board's writing colour, MUTED its faint lines, BOARD the board itself (to blank out a line behind a
# symbol), the rest the style's palette.
TOKENS = ("INK", "MUTED", "BOARD", "ROSE", "GREEN", "GOLD", "RIVER", "TERRA", "TEAL", "VIOLET", "SAND", "DUNE", "RUST", "OLIVE")


def paint(text: str, palette: dict) -> str:
    """The SVG with its colour tokens (fill="ROSE", stroke: INK) replaced by the style's colours."""
    def swap(m):
        value = palette.get(m.group(2).upper())
        return f"{m.group(1)}{value}{m.group(3)}" if value else m.group(0)

    names = "|".join(TOKENS)
    text = re.sub(rf'((?:fill|stroke|stop-color|color)\s*=\s*")({names})(")', swap, text, flags=re.I)
    return re.sub(rf"((?:fill|stroke|stop-color|color)\s*:\s*)({names})(\s*[;\"])", swap, text, flags=re.I)


# --------------------------------------------------------------------------------------------------------------
# SVG geometry: transforms as 3x3 matrices in the SVG's user space.

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _nums(text) -> list[float]:
    return [float(x) for x in _NUM.findall("" if text is None else str(text))]


def _translate(tx, ty=0.0):
    return np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], dtype=float)


def _scale(sx, sy=None):
    return np.array([[sx, 0, 0], [0, sx if sy is None else sy, 0], [0, 0, 1]], dtype=float)


def _rotate(deg, cx=0.0, cy=0.0):
    a = math.radians(deg)
    r = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]], dtype=float)
    return _translate(cx, cy) @ r @ _translate(-cx, -cy) if (cx or cy) else r


def _function(kind: str, v: list[float]) -> np.ndarray:
    if kind == "translate":
        return _translate(v[0] if v else 0.0, v[1] if len(v) > 1 else 0.0)
    if kind == "scale":
        return _scale(v[0] if v else 1.0, v[1] if len(v) > 1 else None)
    if kind == "rotate":
        return _rotate(v[0] if v else 0.0, v[1] if len(v) > 2 else 0.0, v[2] if len(v) > 2 else 0.0)
    if kind == "skewX":
        return np.array([[1, math.tan(math.radians(v[0] if v else 0)), 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    if kind == "skewY":
        return np.array([[1, 0, 0], [math.tan(math.radians(v[0] if v else 0)), 1, 0], [0, 0, 1]], dtype=float)
    if kind == "matrix" and len(v) >= 6:
        return np.array([[v[0], v[2], v[4]], [v[1], v[3], v[5]], [0, 0, 1]], dtype=float)
    return np.eye(3)


def parse_transform(text) -> np.ndarray:
    m = np.eye(3)
    for kind, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", str(text or "")):
        m = m @ _function(kind, _nums(args))
    return m


def _matrix_text(m: np.ndarray) -> str:
    return "matrix({:.6g} {:.6g} {:.6g} {:.6g} {:.6g} {:.6g})".format(m[0, 0], m[1, 0], m[0, 1], m[1, 1],
                                                                       m[0, 2], m[1, 2])


def _style(el, name: str):
    """A presentation attribute, from the attribute or the style="" declarations (style wins)."""
    for part in str(el.get("style") or "").split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            if key.strip() == name:
                return value.strip()
    return el.get(name)


def _set_style(el, name: str, value) -> None:
    if el.get("style") and re.search(rf"(^|;)\s*{re.escape(name)}\s*:", el.get("style")):
        parts = [p for p in el.get("style").split(";") if p.strip() and p.split(":", 1)[0].strip() != name]
        el.set("style", ";".join(parts))
    el.set(name, str(value))


def _colour(text) -> np.ndarray | None:
    text = str(text or "").strip().lower()
    if text.startswith("#"):
        h = text[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) >= 6:
            try:
                return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)
            except ValueError:
                return None
    m = re.match(r"rgb\(([^)]*)\)", text)
    if m:
        v = _nums(m.group(1))
        return np.array(v[:3], dtype=float) if len(v) >= 3 else None
    named = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "blue": (0, 0, 255),
             "green": (0, 128, 0), "yellow": (255, 255, 0), "orange": (255, 165, 0)}
    return np.array(named[text], dtype=float) if text in named else None


def _hex(rgb) -> str:
    r, g, b = (int(max(0, min(255, round(c)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------------------------------------------
# SMIL timing and values.

def _seconds(text: str) -> float | None:
    text = text.strip()
    m = re.fullmatch(r"([-+]?(?:\d+\.?\d*|\.\d+))\s*(ms|s|min|h)?", text)
    if not m:
        return None
    value = float(m.group(1))
    return value * {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0}.get(m.group(2) or "s", 1.0)


def _snap(frames: float) -> int:
    """The period nearest `frames` that divides LOOP (or is a whole multiple of it)."""
    return min(PERIODS, key=lambda p: (abs(p - frames) / max(frames, 1), p))


def _bezier(x: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """keySplines easing: the y of the cubic Bezier (0,0) (x1,y1) (x2,y2) (1,1) at x."""
    lo, hi = 0.0, 1.0
    for _ in range(30):
        u = (lo + hi) / 2
        bx = 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u ** 2 * x2 + u ** 3
        if bx < x:
            lo = u
        else:
            hi = u
    u = (lo + hi) / 2
    return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u ** 2 * y2 + u ** 3


class Anim:
    """One SMIL animation element, its timing snapped to whole frames that repeat within LOOP."""

    def __init__(self, el, target):
        self.target = target
        self.tag = local(el.tag)
        self.attr = el.get("attributeName") or ("transform" if self.tag == "animateTransform" else "")
        self.kind = el.get("type") or "translate"
        self.additive = el.get("additive") == "sum"
        self.freeze = el.get("fill") == "freeze"
        dur = _seconds(el.get("dur") or "") or 0.0
        begins = [b.strip() for b in str(el.get("begin") or "0s").split(";") if b.strip()]
        offsets = [s for s in (_seconds(b) for b in begins) if s is not None]
        gaps = [_seconds(m.group(1)) or 0.0 for b in begins for m in [re.search(r"\.end\s*([-+][\d.]+m?s?)?", b)] if m
                and m.group(1)] or [0.0 for b in begins if ".end" in b]
        self.begin = offsets[0] if offsets else 0.0
        repeat = el.get("repeatCount")
        if self.tag == "set":
            dur = dur or 1e9
        self.period = None
        if gaps:                                       # begins again some time after it ends: a loop with a rest
            self.period = dur + max(gaps[0], 0.0)
        elif repeat == "indefinite" or el.get("repeatDur") == "indefinite":
            self.period = dur
        self.count = float(repeat) if repeat not in (None, "indefinite") and _seconds(repeat) is not None else 1.0
        if self.period:
            # Snapped to a period that divides LOOP; its parts keep their proportions.
            snapped = _snap(self.period * FPS) / FPS
            factor = snapped / self.period
            self.period, dur, self.begin = snapped, dur * factor, self.begin * factor
        self.dur = max(dur, 1e-6)
        self.values = self._values(el)
        n = len(self.values)
        self.calc = el.get("calcMode") or ("discrete" if self.tag == "set" else "linear")
        times = _nums(el.get("keyTimes")) if el.get("keyTimes") else []
        if len(times) != n:
            times = [i / n for i in range(n)] if self.calc == "discrete" else \
                [i / max(n - 1, 1) for i in range(n)]
        self.times = times
        splines = [s for s in str(el.get("keySplines") or "").split(";") if s.strip()]
        self.splines = [_nums(s) for s in splines] if self.calc == "spline" else []

    def _values(self, el) -> list:
        raw = el.get("values")
        if self.tag == "set":
            raw = el.get("to")
        if raw is None:
            frm, to, by = el.get("from"), el.get("to"), el.get("by")
            if frm is not None and to is not None:
                raw = f"{frm};{to}"
            elif to is not None:
                raw = to
            elif by is not None and frm is not None:
                raw = f"{frm};{by}"
            else:
                raw = ""
        parts = [v.strip() for v in str(raw).split(";") if v.strip()]
        return parts or ["0"]

    def progress(self, t: float) -> float | None:
        """Where it is, 0..1, at t seconds; None when it is not acting (its attribute keeps its own value)."""
        if t < self.begin - 1e-9:
            return None
        u = t - self.begin
        if self.period:
            phase = u % self.period
            return phase / self.dur if phase < self.dur - 1e-9 else None
        if u < self.dur * self.count:
            return (u % self.dur) / self.dur
        return 1.0 if self.freeze else None

    def value(self, p: float):
        """The animated value at progress p: numbers, a colour or a string."""
        values, times = self.values, self.times
        if len(values) == 1:
            return values[0]
        if self.calc == "discrete":
            index = max(i for i, k in enumerate(times) if k <= p + 1e-9) if p >= times[0] else 0
            return values[min(index, len(values) - 1)]
        i = 0
        while i < len(times) - 2 and p > times[i + 1]:
            i += 1
        span = max(times[i + 1] - times[i], 1e-9)
        f = min(max((p - times[i]) / span, 0.0), 1.0)
        if self.splines and i < len(self.splines) and len(self.splines[i]) == 4:
            f = _bezier(f, *self.splines[i])
        a, b = values[i], values[i + 1]
        ca, cb = _colour(a), _colour(b)
        if ca is not None and cb is not None:
            return _hex(ca + (cb - ca) * f)
        na, nb = _nums(a), _nums(b)
        if na and len(na) == len(nb):
            if self.attr == "d":
                # A path's shape changing: its numbers move, its commands stay.
                it = iter([x + (y - x) * f for x, y in zip(na, nb)])
                return _NUM.sub(lambda _m: f"{next(it):.4f}", a)
            return [x + (y - x) * f for x, y in zip(na, nb)]
        return a if f < 0.5 else b

    def matrix(self, p: float) -> np.ndarray:
        v = self.value(p)
        return _function(self.kind, v if isinstance(v, list) else _nums(v))


# --------------------------------------------------------------------------------------------------------------
# A document: the SVG with its <use>s written out, its animations read off it.

class Doc:
    def __init__(self, text: str):
        self.root = ET.fromstring(text)
        self.parents: dict = {}
        self._expand_uses()
        self.parents = {child: parent for parent in self.root.iter() for child in parent}
        self.anims: list[Anim] = []
        for el in list(self.root.iter()):
            if local(el.tag) in ANIMATIONS:
                href = el.get(f"{{{XLINK}}}href") or el.get("href")
                target = self._by_id(href[1:]) if href and href.startswith("#") else self.parents.get(el)
                parent = self.parents.get(el)
                if parent is not None:
                    parent.remove(el)
                if target is not None and local(el.tag) != "animateMotion" and not self._hidden_now(target):
                    self.anims.append(Anim(el, target))
        self.parents = {child: parent for parent in self.root.iter() for child in parent}
        self.leaves = [el for el in self.root.iter() if local(el.tag) in SHAPES and not self._hidden(el)]
        # Labels: Manim's SVG reader draws no <text>, so each is set in the lecture's own font (make's `label`).
        self.texts = [el for el in self.root.iter() if local(el.tag) == "text" and not self._hidden(el)
                      and " ".join("".join(el.itertext()).split())]
        self.by_target: dict = {}
        for anim in self.anims:
            self.by_target.setdefault(anim.target, []).append(anim)

    # -- structure -------------------------------------------------------------------------------------------
    def _by_id(self, key: str):
        for el in self.root.iter():
            if el.get("id") == key:
                return el
        return None

    def _hidden_now(self, el) -> bool:
        """_hidden while elements are still being taken out of the tree (its parents read afresh)."""
        self.parents = {child: parent for parent in self.root.iter() for child in parent}
        return self._hidden(el)

    def _hidden(self, el) -> bool:
        parents = self.parents
        node = el
        while node is not None:
            if local(node.tag) in HIDDEN or _style(node, "display") == "none":
                return True
            node = parents.get(node)
        return False

    def _expand_uses(self) -> None:
        """Each <use> as a group holding a copy of what it uses (a symbol fitted to the use's box), so every
        drawn shape is an element of its own, in the order it is drawn."""
        for _ in range(8):
            parents = {child: parent for parent in self.root.iter() for child in parent}
            uses = [el for el in self.root.iter() if local(el.tag) == "use" and not self._in_defs(el, parents)]
            if not uses:
                return
            for use in uses:
                href = use.get(f"{{{XLINK}}}href") or use.get("href") or ""
                source = self._by_id(href[1:]) if href.startswith("#") else None
                parent = parents.get(use)
                if parent is None:
                    continue
                index = list(parent).index(use)
                parent.remove(use)
                if source is None:
                    continue
                group = ET.Element(f"{{{SVG_NS}}}g")
                for key, value in use.attrib.items():
                    if key not in ("x", "y", "width", "height", "href", f"{{{XLINK}}}href", "transform", "id"):
                        group.set(key, value)
                m = parse_transform(use.get("transform")) @ _translate(float(use.get("x") or 0),
                                                                        float(use.get("y") or 0))
                if local(source.tag) in ("symbol", "svg") and source.get("viewBox"):
                    vx, vy, vw, vh = (_nums(source.get("viewBox")) + [0, 0, 1, 1])[:4]
                    w = float(_nums(use.get("width"))[0]) if use.get("width") else vw
                    h = float(_nums(use.get("height"))[0]) if use.get("height") else vh
                    k = min(w / max(vw, 1e-9), h / max(vh, 1e-9))
                    m = m @ _translate((w - vw * k) / 2, (h - vh * k) / 2) @ _scale(k) @ _translate(-vx, -vy)
                    kids = [copy.deepcopy(c) for c in source]
                else:
                    kids = [copy.deepcopy(source)]
                group.set("transform", _matrix_text(m))
                for kid in kids:
                    for el in kid.iter():
                        if local(el.tag) not in ANIMATIONS:
                            el.attrib.pop("id", None)
                    group.append(kid)
                parent.insert(index, group)

    @staticmethod
    def _in_defs(el, parents) -> bool:
        node = parents.get(el)
        while node is not None:
            if local(node.tag) in ("defs", "symbol"):
                return True
            node = parents.get(node)
        return False

    def chain(self, el) -> list:
        out = []
        while el is not None and el is not self.root:
            out.append(el)
            el = self.parents.get(el)
        return out[::-1]

    def text_spec(self, el) -> dict:
        """A label: its words, where its anchor point is in user space, its size (user units), colour, weight,
        and how it hangs off that point (text-anchor, dominant-baseline)."""
        words = " ".join("".join(el.itertext()).split())
        x, y = _nums(el.get("x"))[:1], _nums(el.get("y"))[:1]
        for span in el:
            if local(span.tag) == "tspan":
                x = x or _nums(span.get("x"))[:1]
                y = y or _nums(span.get("y"))[:1]
        point = self.static_ctm(el) @ np.array([(x or [0.0])[0], (y or [0.0])[0], 1.0])
        size = _nums(self.inherited(el, "font-size", None)) or [16.0]
        scale = abs(np.linalg.det(self.static_ctm(el)[:2, :2])) ** 0.5 or 1.0
        weight = str(self.inherited(el, "font-weight", None) or "")
        return {"text": words, "at": point[:2], "size": size[0] * scale,
                "fill": self.inherited(el, "fill", None) or "#000000",
                "anchor": self.inherited(el, "text-anchor", None) or "start",
                "middle": (self.inherited(el, "dominant-baseline", None) or "") in ("middle", "central"),
                "bold": weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600)}

    def part_of(self, el) -> str | None:
        """The part an element belongs to: the id of its outermost ancestor (or itself) that has one."""
        for node in self.chain(el):
            if node.get("id") and local(node.tag) not in ANIMATIONS:
                return node.get("id")
        return None

    def part_ids(self) -> list[str]:
        """The figure's parts, in drawing order (what a lecture reveals and points at by id)."""
        out: list[str] = []
        for el in [*self.leaves, *self.texts]:
            key = self.part_of(el)
            if key and key not in out:
                out.append(key)
        order = {el: i for i, el in enumerate(self.root.iter())}
        firsts = {}
        for el in [*self.leaves, *self.texts]:
            key = self.part_of(el)
            if key:
                firsts[key] = min(firsts.get(key, 1 << 30), order[el])
        return sorted(out, key=lambda k: firsts[k])

    @property
    def quick(self) -> bool:
        """Whether every animation moves, fades or recolours shapes (drawn once, then followed), or some must be
        drawn again each frame from the SVG (a path's own shape changing, a rectangle's size)."""
        return all(a.attr in QUICK for a in self.anims)

    def period(self) -> int:
        """Frames after which the whole drawing repeats (LOOP when anything repeats; 1 when nothing moves)."""
        periods = [round(a.period * FPS) for a in self.anims if a.period]
        if not periods:
            return 1
        out = 1
        for p in periods:
            out = out * p // math.gcd(out, p)
        return out

    # -- a moment ------------------------------------------------------------------------------------------
    def state(self, t: float) -> dict:
        """{element: (transform matrix to append, {attribute: value}, replace)} for what the animations do at t."""
        out: dict = {}
        for el, anims in self.by_target.items():
            matrix, attrs, replace = np.eye(3), {}, False
            for anim in anims:
                p = anim.progress(t)
                if p is None:
                    continue
                if anim.attr == "transform":
                    if anim.additive:
                        matrix = matrix @ anim.matrix(p)
                    else:
                        matrix, replace = anim.matrix(p), True
                else:
                    v = anim.value(p)
                    attrs[anim.attr] = v[0] if isinstance(v, list) and len(v) == 1 else (
                        " ".join(f"{x:.4f}" for x in v) if isinstance(v, list) else v)
            if replace or attrs or not np.allclose(matrix, np.eye(3)):
                out[el] = (matrix, attrs, replace)
        return out

    def static_matrix(self, el) -> np.ndarray:
        return parse_transform(el.get("transform"))

    def static_ctm(self, el) -> np.ndarray:
        cache = self.__dict__.setdefault("_static", {})
        if el not in cache:
            cache[el] = self.ctm(el, None)
        return cache[el]

    def ctm(self, el, state: dict | None) -> np.ndarray:
        """The leaf's matrix into user space: every ancestor's transform, with what is animated at this moment."""
        m = np.eye(3)
        for node in self.chain(el):
            static = self.static_matrix(node)
            if state and node in state:
                anim, attrs, replace = state[node]
                m = m @ (anim if replace else static @ anim) @ self._shape_change(node, attrs)
            else:
                m = m @ static
        return m

    @staticmethod
    def _shape_change(el, attrs: dict) -> np.ndarray:
        """A circle's radius or a shape's position animated, as the matrix that does the same to its outline."""
        if not attrs:
            return np.eye(3)
        tag = local(el.tag)
        m = np.eye(3)
        if tag in ("circle", "ellipse"):
            cx, cy = float(el.get("cx") or 0), float(el.get("cy") or 0)
            nx, ny = float(_nums(attrs.get("cx", cx))[0]), float(_nums(attrs.get("cy", cy))[0])
            sx = sy = 1.0
            if "r" in attrs and float(el.get("r") or 0):
                sx = sy = float(_nums(attrs["r"])[0]) / float(el.get("r"))
            if "rx" in attrs and float(el.get("rx") or 0):
                sx = float(_nums(attrs["rx"])[0]) / float(el.get("rx"))
            if "ry" in attrs and float(el.get("ry") or 0):
                sy = float(_nums(attrs["ry"])[0]) / float(el.get("ry"))
            m = _translate(nx, ny) @ _scale(sx, sy) @ _translate(-cx, -cy)
        elif tag == "rect" and ("x" in attrs or "y" in attrs):
            m = _translate(float(_nums(attrs.get("x", el.get("x") or 0))[0]) - float(el.get("x") or 0),
                           float(_nums(attrs.get("y", el.get("y") or 0))[0]) - float(el.get("y") or 0))
        return m

    def opacity(self, el, state: dict | None) -> float:
        """The product of `opacity` down the leaf's chain at this moment (Manim reads no `opacity`)."""
        out = 1.0
        for node in self.chain(el):
            value = _style(node, "opacity")
            if state and node in state and "opacity" in state[node][1]:
                value = state[node][1]["opacity"]
            if value is not None and _nums(value):
                out *= min(max(_nums(value)[0], 0.0), 1.0)
        return out

    def inherited(self, el, name: str, state: dict | None):
        """A presentation attribute as the leaf draws with it (its own, else the nearest ancestor's)."""
        for node in reversed(self.chain(el)):
            if state and node in state and name in state[node][1]:
                return state[node][1][name]
            value = _style(node, name)
            if value is not None and value != "inherit":
                return value
        return None

    def text(self, t: float | None = None, marks: tuple | None = None, fold: bool = True) -> str:
        """The SVG at moment t as a still drawing (t None: as it stands, without animation): every animated
        transform and attribute written in, opacity folded into fill and stroke opacity, two corner marks
        (invisible) at `marks` so a reader can tell where user space went."""
        root = copy.deepcopy(self.root)
        mapping = dict(zip(self.root.iter(), root.iter()))
        state = self.state(t) if t is not None else {}
        for el, (matrix, attrs, replace) in state.items():
            twin = mapping[el]
            if replace:
                twin.set("transform", _matrix_text(matrix))
            elif not np.allclose(matrix, np.eye(3)):
                twin.set("transform", (twin.get("transform") or "") + " " + _matrix_text(matrix))
            for key, value in attrs.items():
                if key not in ("opacity",):
                    _set_style(twin, key, value)
        for leaf in (self.leaves if fold else []):
            twin = mapping[leaf]
            alpha = self.opacity(leaf, state)
            if alpha < 1.0:
                for name in ("fill-opacity", "stroke-opacity"):
                    own = self.inherited(leaf, name, state)
                    base = _nums(own)[0] if own is not None and _nums(own) else 1.0
                    _set_style(twin, name, f"{base * alpha:.4f}")
        for parent in list(root.iter()):
            for child in list(parent):
                if local(child.tag) == "text":
                    parent.remove(child)        # labels are set as text mobjects (make's `label`), not read by Manim
        for el in root.iter():
            if "opacity" in el.attrib:
                del el.attrib["opacity"]
            if el.get("style"):
                el.set("style", ";".join(p for p in el.get("style").split(";")
                                         if p.split(":", 1)[0].strip() != "opacity"))
        if marks:
            for x, y in marks:
                ET.SubElement(root, f"{{{SVG_NS}}}path", {"d": f"M {x:.4f} {y:.4f} h 0.001", "fill": "#000",
                                                           "fill-opacity": "0", "stroke": "none"})
        return ET.tostring(root, encoding="unicode")


# --------------------------------------------------------------------------------------------------------------
# Writing a motion into a drawing.

def add_motion(text: str, motion: str, box: tuple[float, float, float, float]) -> str:
    """The SVG with `motion` (a MOTIONS name) written into it as SMIL on a group around the whole drawing.
    `box` is the drawing's extent in user space (x, y, w, h): the motion's pivot and its distances follow it."""
    root = ET.fromstring(text)
    x, y, w, h = box
    pivots = {"centre": (x + w / 2, y + h / 2), "bottom": (x + w / 2, y + h), "top": (x + w / 2, y)}
    kids = [c for c in list(root) if local(c.tag) not in HIDDEN]
    for spec in MOTIONS[motion]:
        kind, values, times, splines, period, pivot = spec
        px, py = pivots.get(pivot or "centre")
        outer = ET.Element(f"{{{SVG_NS}}}g", {"transform": f"translate({px:.4f} {py:.4f})"})
        inner = ET.SubElement(outer, f"{{{SVG_NS}}}g", {"transform": f"translate({-px:.4f} {-py:.4f})"})
        if kind == "translate":
            # Distances are a share of the drawing's size.
            values = "; ".join(f"{float(a) * w:.4f} {float(b) * h:.4f}"
                               for a, b in (v.split() for v in values.split(";")))
        attrs = {"attributeName": "opacity" if kind == "opacity" else "transform", "values": values,
                 "dur": f"{period / FPS:.4f}s", "repeatCount": "indefinite"}
        if kind != "opacity":
            attrs.update({"type": kind, "additive": "sum"})
        if times:
            attrs["keyTimes"] = times
        if splines:
            attrs.update({"calcMode": "spline", "keySplines": splines})
        ET.SubElement(outer, f"{{{SVG_NS}}}{'animate' if kind == 'opacity' else 'animateTransform'}", attrs)
        for kid in kids:
            root.remove(kid)
            inner.append(kid)
        root.append(outer)
        kids = [outer]
    return ET.tostring(root, encoding="unicode")


# --------------------------------------------------------------------------------------------------------------
# The drawing on the board.

def _parse(text: str):
    """Manim's reading of an SVG, in its own units (not centred or scaled), from a file named by the text's hash
    (Manim caches by file)."""
    import hashlib
    import tempfile

    from manim import SVGMobject

    folder = Path(tempfile.gettempdir()) / "pocketanim-animsvg"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{hashlib.sha1(text.encode()).hexdigest()[:16]}.svg"
    if not path.exists():
        tmp = path.with_suffix(f".{__import__('os').getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return SVGMobject(str(path), height=None, width=None, should_center=False)


def _map(raw0, raw1, user0, user1):
    """The axis-by-axis linear map that takes two points of one space to two of another: (scale, offset)."""
    raw0, raw1, user0, user1 = (np.asarray(v, dtype=float)[:2] for v in (raw0, raw1, user0, user1))
    span = np.where(np.abs(user1 - user0) < 1e-12, 1.0, user1 - user0)
    scale = (raw1 - raw0) / span
    return scale, raw0 - scale * user0


def make(text: str, height: float = 1.0, style=None, strokes: bool = False, label=None):
    """A Manim mobject of the animated SVG `text`, `height` tall, its motion played by `drawing.show(t)`.

    `style(mob)` restyles each freshly read drawing (the board's ink and marker weight). `strokes` scales the
    SVG's own stroke widths with the drawing (a drawing of lines, like the weather set's)."""

    doc = Doc(text)
    marks = ((0.0, 0.0), (100.0, 100.0))
    # Without `opacity` folded in: the parts are read at their own fill and stroke opacity, and each frame
    # multiplies in the opacity of that moment (a raindrop at opacity 0 until it falls).
    still = _parse(doc.text(None, marks, fold=not doc.quick))
    parts = still.family_members_with_points()
    raw0, raw1 = parts[-2].get_center(), parts[-1].get_center()
    for mark in parts[-2:]:
        _detach(still, mark)
    to_raw = _map(raw0, raw1, *marks)                       # user space -> Manim's units
    leaves = still.family_members_with_points()
    if not leaves:
        raise ValueError("an SVG with nothing drawn")
    pts = np.concatenate([leaf.points for leaf in leaves])
    lo_raw, hi_raw = pts[:, :2].min(axis=0), pts[:, :2].max(axis=0)
    user_lo = (lo_raw - to_raw[1]) / to_raw[0]
    user_hi = (hi_raw - to_raw[1]) / to_raw[0]
    u0, u1 = np.minimum(user_lo, user_hi), np.maximum(user_lo, user_hi)     # the drawing's box in user space
    specs = [doc.text_spec(el) for el in doc.texts]
    for spec in specs:
        # Room for the labels too: about half an em a letter, an em tall above the baseline.
        wide = 0.55 * spec["size"] * len(spec["text"])
        left = {"middle": spec["at"][0] - wide / 2, "end": spec["at"][0] - wide}.get(spec["anchor"], spec["at"][0])
        top = spec["at"][1] - (0.5 if spec["middle"] else 0.95) * spec["size"]
        u0 = np.minimum(u0, [left, top])
        u1 = np.maximum(u1, [left + wide, top + 1.2 * spec["size"]])
    k = height / max(u1[1] - u0[1], 1e-9)
    width = (u1[0] - u0[0]) * k
    # Scene placement: the box's corners; the anchor's two points carry them through every move and scale.
    a0 = np.array([-width / 2, height / 2, 0.0])
    a1 = np.array([width / 2, -height / 2, 0.0])

    drawing = AnimatedDrawing(doc, still, to_raw, (u0, u1), style, strokes, k)
    drawing.anchor.set_points_as_corners([a0, a1])
    drawing.place()
    drawing.add_labels(specs, label)
    return drawing


def _outline(points: np.ndarray, samples: int = 12):
    """A part's outline (cubic Bezier points, 4 a curve) as a dense polyline and the distance along it."""
    curves = points[: len(points) // 4 * 4].reshape(-1, 4, 2)
    u = np.linspace(0, 1, samples + 1)[:, None]
    lines = []
    for a, b, c, d in curves:
        lines.append((1 - u) ** 3 * a + 3 * (1 - u) ** 2 * u * b + 3 * (1 - u) * u ** 2 * c + u ** 3 * d)
    line = np.concatenate(lines) if lines else np.zeros((0, 2))
    steps = np.linalg.norm(np.diff(line, axis=0), axis=1) if len(line) > 1 else np.zeros(0)
    return line, np.concatenate([[0.0], np.cumsum(steps)])


def _dashes(outline, pattern: list[float], offset: float) -> np.ndarray:
    """The dashes of a dashed outline, as straight cubic pieces (4 points a piece, a new path where one ends)."""
    line, along = outline
    total = along[-1] if len(along) else 0.0
    cycle = sum(pattern) * (1 if len(pattern) % 2 == 0 else 2)
    pattern = pattern if len(pattern) % 2 == 0 else pattern * 2
    if total <= 0 or cycle <= 0:
        return np.zeros((4, 2))
    out = []
    start = -(offset % cycle)
    while start < total:
        at = start
        for k, length in enumerate(pattern):
            if k % 2 == 0:
                lo, hi = max(at, 0.0), min(at + length, total)
                if hi > lo:
                    xs = np.concatenate([[lo], along[(along > lo) & (along < hi)], [hi]])
                    pts = np.stack([np.interp(xs, along, line[:, 0]), np.interp(xs, along, line[:, 1])], axis=1)
                    for p, q in zip(pts, pts[1:]):
                        out.extend([p, p + (q - p) / 3, p + 2 * (q - p) / 3, q])
            at += length
        start += cycle
    return np.array(out) if out else np.zeros((4, 2))


def _detach(group, mob) -> None:
    for parent in [group, *group.get_family()]:
        if mob in getattr(parent, "submobjects", []):
            parent.remove(mob)


try:
    from manim import VGroup as _VGroup, VMobject as _VMobject
except Exception:  # noqa: BLE001 -- the module is also a command-line tool
    _VGroup = object
    _VMobject = object


class AnimatedDrawing(_VGroup):
    """A drawing whose parts move as its SMIL says. Its first part is an invisible anchor on the drawing's box:
    whatever scales or moves the drawing moves the anchor too, and each frame is placed by it."""

    def __init__(self, doc: Doc, still, to_raw, box, style, strokes: bool, k: float):
        from manim import VMobject

        self.doc = doc
        self.to_raw = to_raw
        self.box = box
        self.style = style
        self.strokes = strokes
        self.anchor = VMobject(stroke_width=0, fill_opacity=0, stroke_opacity=0)
        self.art = still
        super().__init__(self.anchor, still)
        self.leaves = still.family_members_with_points()
        self.quick = doc.quick and len(self.leaves) == len(doc.leaves)
        # Each leaf's outline in user space, and the opacity Manim read for it (fill-opacity, without opacity).
        self.user = [self._to_user(leaf.points) for leaf in self.leaves]
        self.base_width = [leaf.get_stroke_width() for leaf in self.leaves]
        if style is not None:
            style(self.art)
        # The opacity each part is drawn with before any `opacity` (Manim reads fill-opacity, not opacity).
        self.fill_alpha = [leaf.get_fill_opacity() for leaf in self.leaves]
        self.stroke_alpha = [leaf.get_stroke_opacity() for leaf in self.leaves]
        self.base_k = k
        self.moving = [any(n in doc.by_target for n in doc.chain(el)) for el in doc.leaves] if self.quick else []
        self.inverse = [np.linalg.inv(doc.static_ctm(el)) for el in doc.leaves] if self.quick else []
        # Dashed outlines (Manim draws dashes solid): the parts drawn with a stroke-dasharray, as a dense line of
        # their outline, cut into dashes each frame from the dash offset of that moment.
        self.dashed = {}
        if self.quick:
            for i, el in enumerate(doc.leaves):
                pattern = [x for x in _nums(doc.inherited(el, "stroke-dasharray", None)) if x >= 0]
                if pattern and sum(pattern) > 0:
                    self.dashed[i] = _outline(self.user[i]), pattern
                    if any(n in doc.by_target and any(a.attr == "stroke-dashoffset" for a in doc.by_target[n])
                           for n in doc.chain(el)):
                        self.moving[i] = True
        self.period = doc.period()
        self.cache: dict = {}

    def _to_user(self, points: np.ndarray) -> np.ndarray:
        scale, offset = self.to_raw
        return (points[:, :2] - offset) / scale

    def _to_scene(self):
        """user space -> scene, from where the anchor is now."""
        a = self.anchor.points
        if len(a) < 2:
            return np.array([1.0, -1.0]), np.zeros(2)
        p0, p1 = a[0][:2], a[-1][:2]
        u0, u1 = self.box[0], np.array([self.box[1][0], self.box[1][1]])
        # The anchor runs from the box's top left (user u0) to its bottom right (user u1).
        scale = (p1 - p0) / np.where(np.abs(u1 - u0) < 1e-12, 1.0, u1 - u0)
        return scale, p0 - scale * u0

    def zoom(self) -> float:
        """How much bigger than first made it is drawn now (the diagram's own scaling)."""
        scale, _ = self._to_scene()
        return abs(scale[0]) / max(self.base_k, 1e-12)

    def place(self) -> None:
        self.show(0.0, first=True)

    def add_labels(self, specs: list[dict], label=None) -> None:
        """Each <text> as a text mobject at its place: `label(words, colour, bold)` makes it (the lecture's font),
        sized to its font-size and hung off its point as text-anchor says."""
        from manim import Text

        make_text = label or (lambda words, colour, bold: Text(words, color=colour, weight="BOLD" if bold else "NORMAL"))
        scale, offset = self._to_scene()
        unit = abs(scale[0])
        refs: dict = {}
        self.labels = []
        for el, spec in zip(self.doc.texts, specs):
            colour = _hex(_colour(spec["fill"])) if _colour(spec["fill"]) is not None else "#000000"
            mob = make_text(spec["text"], colour, spec["bold"])
            if spec["bold"] not in refs:
                refs[spec["bold"]] = max(make_text("Mg", colour, spec["bold"]).height, 1e-6)
            mob.scale(spec["size"] * unit * 0.95 / refs[spec["bold"]])
            point = np.array([*(spec["at"] * scale + offset), 0.0])
            centre_y = point[1] if spec["middle"] else point[1] + 0.33 * spec["size"] * unit
            if spec["anchor"] == "middle":
                mob.move_to([point[0], centre_y, 0])
            elif spec["anchor"] == "end":
                mob.move_to([point[0] - mob.width / 2, centre_y, 0])
            else:
                mob.move_to([point[0] + mob.width / 2, centre_y, 0])
            # Where it sits against its point, in the drawing's units, to follow the point when it moves.
            rel = (mob.get_center()[:2] - point[:2]) / unit
            moving = any(n in self.doc.by_target for n in self.doc.chain(el))
            self.labels.append((el, mob, spec["at"], rel, moving))
            self.add(mob)

    def parts(self) -> tuple[dict, list]:
        """{part id: VGroup of its shapes and labels} for the outermost elements with an id, and the rest (drawn
        with the figure, never revealed on their own). One part only when the drawing is redrawn each frame."""
        from manim import VGroup

        groups: dict = {}
        rest: list = []
        if self.quick:
            members = list(zip(self.doc.leaves, self.leaves)) + [(el, mob) for el, mob, *_ in self.labels]
            for el, mob in members:
                key = self.doc.part_of(el)
                (groups.setdefault(key, []) if key else rest).append(mob)
        else:
            rest = [self.art, *[mob for _, mob, *_ in self.labels]]
        order = self.doc.part_ids()
        return {k: VGroup(*groups[k]) for k in order if k in groups}, rest

    def show(self, t: float, first: bool = False) -> None:
        """Draw the moment t seconds into the motion (it repeats every period)."""
        frame = int(round(t * FPS)) % max(self.period, 1)
        moment = frame / FPS
        if self.quick:
            self._quick(moment, first)
        else:
            self._redraw(moment)

    def _quick(self, moment: float, first: bool) -> None:
        doc = self.doc
        state = doc.state(moment)
        if getattr(self, "labels", None):
            self._move_labels(state, first)
        scale, offset = self._to_scene()
        z = self.base_k * self.zoom()
        for i, (el, leaf) in enumerate(zip(doc.leaves, self.leaves)):
            if not first and not self.moving[i]:
                continue
            m = doc.ctm(el, state) @ self.inverse[i]
            user = self.user[i]
            if i in self.dashed:
                line, pattern = self.dashed[i]
                # Dash lengths are in the part's own units: user space over the part's own scaling.
                unit = abs(np.linalg.det(doc.static_ctm(el)[:2, :2])) ** 0.5 or 1.0
                shift = doc.inherited(el, "stroke-dashoffset", state)
                user = _dashes(line, [x * unit for x in pattern], (_nums(shift) or [0.0])[0] * unit)
            moved = user @ m[:2, :2].T + m[:2, 2]
            points = np.zeros((len(moved), 3))
            points[:, :2] = moved * scale + offset
            leaf.points = points
            alpha = doc.opacity(el, state)
            changed = {key for node in doc.chain(el) if node in state for key in state[node][1]}
            for name, paint in (("fill", leaf.set_fill), ("stroke", leaf.set_stroke)):
                if name in changed:
                    value = doc.inherited(el, name, state)
                    if _colour(value) is not None:
                        paint(color=_hex(_colour(value)), family=False)
            leaf.set_fill(opacity=self.fill_alpha[i] * alpha, family=False)
            leaf.set_stroke(opacity=self.stroke_alpha[i] * alpha, family=False)
            if self.strokes:
                width = self.base_width[i]
                own = doc.inherited(el, "stroke-width", state)
                if own is not None and _nums(own):
                    width = _nums(own)[0]
                # A stroke as wide, against the drawing, as in the SVG: user units -> Manim's (1/100 of a unit).
                leaf.set_stroke(width=width * z * 100 * abs(np.linalg.det(m[:2, :2])) ** 0.5, family=False)

    def keep_labels_where_they_are(self) -> None:
        """After the labels were moved on the board (pocket_lecture.settle_svg_labels): each keeps its new place
        against its point, so a moving part carries it from there."""
        if not getattr(self, "labels", None):
            return
        scale, offset = self._to_scene()
        unit = abs(scale[0]) or 1.0
        state = self.doc.state(0.0)
        kept = []
        for el, mob, at, rel, moving in self.labels:
            m = self.doc.ctm(el, state) @ np.linalg.inv(self.doc.static_ctm(el))
            point = m @ np.array([at[0], at[1], 1.0])
            expected = point[:2] * scale + offset + rel * unit
            kept.append((el, mob, at, rel + (mob.get_center()[:2] - expected) / unit, moving))
        self.labels = kept

    def _move_labels(self, state: dict, first: bool) -> None:
        scale, offset = self._to_scene()
        unit = abs(scale[0])
        for el, mob, at, rel, moving in getattr(self, "labels", []):
            if not moving and not first:
                continue
            m = self.doc.ctm(el, state) @ np.linalg.inv(self.doc.static_ctm(el))
            point = m @ np.array([at[0], at[1], 1.0])
            mob.move_to([*(point[:2] * scale + offset + rel * unit), 0.0])
            mob.set_opacity(self.doc.opacity(el, state))

    def _redraw(self, moment: float) -> None:
        key = round(moment * FPS)
        raw = self.cache.get(key)
        if raw is None:
            marks = ((0.0, 0.0), (100.0, 100.0))
            raw = _parse(self.doc.text(moment, marks))
            for mark in raw.family_members_with_points()[-2:]:
                _detach(raw, mark)
            if self.style is not None:
                self.style(raw)
            if len(self.cache) < 4 * LOOP:
                self.cache[key] = raw
        scale, offset = self._to_scene()
        fresh = raw.copy()
        for leaf in fresh.family_members_with_points():
            user = self._to_user(leaf.points)
            points = np.zeros((len(user), 3))
            points[:, :2] = user * scale + offset
            leaf.points = points
        self.art.become(fresh)


# --------------------------------------------------------------------------------------------------------------

def plan(name: str) -> dict:
    """What a diagram's drawing of `name` will be and do: {"source": weather|library, "icon"?, "motion"?}."""
    icon = weather_icon(name)
    if icon:
        return {"source": "weather", "icon": f"meteocons:{icon}", "motion": "its own"}
    motion = motion_for(name)
    return {"source": "library", "motion": motion}


if __name__ == "__main__":
    import json

    for word in sys.argv[1:] or ["rain", "gear", "heart", "tree", "boat", "candle", "bell", "cloud", "cow"]:
        print(json.dumps({word: plan(word)}))
