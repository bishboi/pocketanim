"""Words: the right font for the script (Latin, Devanagari, Chinese/Japanese), wrapping to a width, shrinking to fit,
and the look's kinds of type.

    text("दोनों देशों में इतिहास", size=34)          # Hindi in the look's Devanagari font
    text("A long sentence ...", width=6)               # wrapped to 6 units wide
    headline("History was a state job")                # condensed capitals, a highlighter swept behind (vox)
    kicker("CHINA · 145 BCE")                          # the small spaced line above a headline
    label("Kyoto", backing=True)                       # a small label with a backing, readable over a map
    quote("History is ...", who="Sima Qian")
    n = number("1,869"); self.play(count(n))           # a figure that counts up to itself
"""

from __future__ import annotations

import re

from manim import (BOLD, DOWN, ITALIC, LEFT, NORMAL, ORIGIN, RIGHT, UP, Animation, Line, Rectangle, RoundedRectangle, Text,
                   VGroup, linear)
from manim import rate_functions as rf

from .base import Piece
from .look import L

DEVA = re.compile(r"[ऀ-ॿ]")
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")


def script_of(s: str) -> str:
    """"deva", "cjk" or "latin": what the words are mostly written in."""
    if DEVA.search(s):
        return "deva"
    if CJK.search(s):
        return "cjk"
    return "latin"


def font_for(s: str, role: str = "body") -> str:
    """The look's font for these words in this role (head, body, serif, hand, mono)."""
    look = L()
    script = script_of(s)
    if script == "deva":
        if role == "hand":
            return "Kalam"                       # a handwriting with Devanagari
        return look.deva_head if role == "head" else look.deva
    if script == "cjk":
        return look.cjk
    return {"head": look.head, "serif": look.serif, "hand": look.hand, "mono": look.mono}.get(role, look.body)


def _weight(w):
    if w in (None, False, "normal", "NORMAL", NORMAL):
        return NORMAL
    return BOLD


def _wrap(s: str, size: float, font: str, weight, slant, width: float) -> str:
    """Words broken into lines no wider than `width` (an estimate from one measured line, then checked)."""
    if "\n" in s:
        return s
    one = Text(s, font=font, font_size=size, weight=weight, slant=slant)
    if one.width <= width:
        return s
    per_char = one.width / max(1, len(s))
    limit = max(4, int(width / per_char))
    lines, line = [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if len(trial) > limit and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return "\n".join(lines)


class Words(Piece):
    """Text as a piece (its glyphs are the one submobject `text`)."""

    enter_kind = "text"


def text(s: str, size: float = 30, role: str = "body", color: str | None = None, weight=None, width: float | None = None,
         italic: bool = False, upper: bool | None = None, align: str = "left", line_spacing: float = 0.9,
         max_height: float | None = None, font: str | None = None) -> Words:
    """Words in the look: `role` picks the font kind (body, head, serif, hand, mono) and the script picks the family.
    `width` wraps them (and shrinks them if a single word is still too wide); `max_height` shrinks to fit."""
    look = L()
    s = str(s)
    if upper is None:
        upper = role == "head" and look.head_upper and script_of(s) == "latin"
    if upper:
        s = s.upper()
    face = font or font_for(s, role)
    weight = _weight(weight if weight is not None else (look.head_weight if role == "head" else None))
    if face == "Playfair Display":
        weight = NORMAL                          # its bold loses the spaces between words
    slant = ITALIC if italic else NORMAL
    if width:
        s = _wrap(s, size, face, weight, slant, width)
    if "\n" in s and align in ("center", "right"):
        rows = [Text(r, font=face, font_size=size, color=color or look.ink, weight=weight, slant=slant)
                for r in s.split("\n")]
        t = VGroup(*rows).arrange(DOWN, buff=size / 100 * 0.35 * line_spacing,
                                  aligned_edge=RIGHT if align == "right" else ORIGIN)
        t.text = s
    else:
        t = Text(s, font=face, font_size=size, color=color or look.ink, weight=weight, slant=slant,
                 line_spacing=line_spacing)
    if width and t.width > width:
        t.scale_to_fit_width(width)
    if max_height and t.height > max_height:
        t.scale_to_fit_height(max_height)
    w = Words(t)
    w.name_part("text", t)
    return w


def fit(mob, width: float | None = None, height: float | None = None):
    """Shrink (never grow) a mobject to fit inside width x height."""
    if width and mob.width > width:
        mob.scale_to_fit_width(width)
    if height and mob.height > height:
        mob.scale_to_fit_height(height)
    return mob


# ---------------------------------------------------------------- the look's kinds of type -------------------------
class Headline(Piece):
    """A headline: words over a mark (vox: a highlighter bar; blueprint: a ruled underline with end ticks)."""

    enter_kind = "text"

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import sweep_headline
        return sweep_headline(self, run)


def headline(s: str, size: float = 56, color: str | None = None, mark: bool | str = True, width: float | None = 12,
             role: str = "head") -> Headline:
    look = L()
    words = text(s, size=size, role=role, color=color, width=width)
    h = Headline()
    if mark:
        mark_color = mark if isinstance(mark, str) else look.mark
        if look.name == "blueprint":
            y = words.get_bottom()[1] - 0.12
            line = Line([words.get_left()[0] - 0.1, y, 0], [words.get_right()[0] + 0.1, y, 0], color=mark_color,
                        stroke_width=look.stroke)
            ticks = VGroup(*(Line(UP * 0.12, DOWN * 0.12, color=mark_color, stroke_width=look.stroke).move_to(p)
                             for p in (line.get_start(), line.get_end())))
            bar = VGroup(line, ticks)
        else:
            bar = Rectangle(width=words.width + 0.3, height=max(0.18, words[0].height * 0.42), stroke_width=0,
                            fill_color=mark_color, fill_opacity=1)
            bar.move_to(words.get_bottom() + UP * words[0].height * 0.3)
            if "\n" in str(words[0].text):
                bar.stretch_to_fit_height(words.height * 0.25).move_to(words.get_bottom() + UP * 0.15)
        h.add(bar)
        h.name_part("mark", bar)
    h.add(words)
    h.name_part("words", words)
    return h


def kicker(s: str, size: float = 20, color: str | None = None) -> Words:
    """The small line over a headline: spaced capitals in the accent colour (Hindi is left unspaced)."""
    look = L()
    if script_of(s) == "latin":
        s = "   ".join(" ".join(word) for word in s.upper().split())
    return text(s, size=size, role="body" if look.name == "vox" else "mono", color=color or look.accent, weight=True)


class Label(Piece):
    enter_kind = "text"


def label(s: str, size: float = 22, color: str | None = None, backing: bool = True, role: str = "body",
          weight=True, pad: float = 0.1) -> Label:
    """A small label; with a backing the colour of the stage under it (it stays readable over lines and maps)."""
    look = L()
    words = text(s, size=size, role=role, color=color, weight=weight)
    lab = Label()
    if backing:
        back = RoundedRectangle(width=words.width + 2 * pad, height=words.height + 1.4 * pad,
                                corner_radius=min(0.08, (words.height + 1.4 * pad) / 2), stroke_width=0,
                                fill_color=look.bg, fill_opacity=0.85).move_to(words)
        lab.add(back)
        lab.name_part("backing", back)
    lab.add(words)
    lab.name_part("words", words)
    return lab


class Quote(Piece):
    enter_kind = "text"


def quote(s: str, who: str | None = None, size: float = 34, width: float = 9, color: str | None = None) -> Quote:
    """A quotation: serif words, a large quote mark in the accent colour, and who said it."""
    look = L()
    body = text(s, size=size, role="serif", color=color, width=width, italic=script_of(s) == "latin")
    mark = Text("“", font=look.serif, font_size=size * 3.2, color=look.accent)
    mark.next_to(body, UP + LEFT, buff=-0.15).shift(LEFT * 0.2)
    q = Quote(mark, body)
    q.name_part("mark", mark)
    q.name_part("words", body)
    if who:
        by = text(f"— {who}", size=size * 0.6, role="body", color=look.muted, weight=True)
        by.next_to(body, DOWN, buff=0.3, aligned_edge=RIGHT)
        q.add(by)
        q.name_part("who", by)
    return q


class Caption(Piece):
    enter_kind = "text"


def caption(s: str, size: float = 26, width: float = 11) -> Caption:
    """A lower-third line on a band (vox: an ink band with paper words; blueprint: an outlined strip)."""
    look = L()
    vox = look.name != "blueprint"
    words = text(s, size=size, color=look.bg if vox else look.ink, width=width, weight=True)
    band = Rectangle(width=words.width + 0.5, height=words.height + 0.3, stroke_width=0 if vox else 2,
                     stroke_color=look.ink, fill_color=look.ink if vox else look.card, fill_opacity=1 if vox else 0.8)
    band.move_to(words)
    c = Caption(band, words)
    c.name_part("band", band)
    c.name_part("words", words)
    c.to_edge(DOWN, buff=0.45)
    return c


def title_card(title: str, kick: str | None = None, sub: str | None = None, size: float = 72) -> Piece:
    """A chapter's opening: the kicker, the headline, a line under it."""
    look = L()
    g = Piece()
    h = headline(title, size=size)
    g.add(h)
    g.name_part("headline", h)
    if kick:
        k = kicker(kick)
        k.next_to(h, UP, buff=0.35)
        g.add(k)
        g.name_part("kicker", k)
    if sub:
        s = text(sub, size=size * 0.4, color=look.muted, width=10)
        s.next_to(h, DOWN, buff=0.4)
        g.add(s)
        g.name_part("sub", s)
    return g.move_to(0)


# ---------------------------------------------------------------- figures that count -------------------------------
NUMBER = re.compile(r"^(?P<pre>[^\d\-+.]*?)(?P<sign>[+\-−]?)(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)(?P<post>.*)$")


def parse_number(s: str):
    m = NUMBER.match(str(s).strip())
    if not m:
        return None
    raw = m.group("num")
    value = float(raw.replace(",", ""))
    if m.group("sign") in ("-", "−"):
        value = -value
    return m.group("pre"), value, len(raw.split(".")[1]) if "." in raw else 0, "," in raw, m.group("post")


def _format(parsed, value: float) -> str:
    pre, _, decimals, grouped, post = parsed
    body = f"{abs(value):,.{decimals}f}" if grouped else f"{abs(value):.{decimals}f}"
    return f"{pre}{'-' if value < 0 else ''}{body}{post}"


class Number(Piece):
    enter_kind = "text"

    def __init__(self, s: str, size: float, color, role: str):
        super().__init__()
        self.words, self.size, self.color_, self.role = str(s), size, color, role
        t = self.make(self.words)
        self.add(t)
        self.name_part("text", t)

    def make(self, s: str):
        return text(s, size=self.size, role=self.role, color=self.color_, weight=True, upper=False)[0]


def number(s: str, size: float = 80, color: str | None = None, role: str = "head") -> Number:
    """A big figure ("1869", "₹2.4 lakh", "60%"); `count(n)` counts it up from 0 (or `start`)."""
    return Number(s, size, color, role)


class Count(Animation):
    """A Number counting up to its own value, held where it was laid out (left edge fixed)."""

    def __init__(self, n: Number, start: float = 0.0, run_time: float = 1.4, **kw):
        self.n, self.start, self.parsed = n, start, parse_number(n.words)
        super().__init__(n, run_time=run_time, rate_func=linear, **kw)
        self._panim_bake = True

    def begin(self):
        self.left = self.mobject.get_left().copy()
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        if self.parsed is None:
            return
        a = rf.ease_out_cubic(min(max(alpha, 0), 1))
        s = self.n.words if alpha >= 1 else _format(self.parsed, self.start + (self.parsed[1] - self.start) * a)
        made = self.n.make(s)
        made.move_to(self.left, aligned_edge=LEFT)
        self.mobject.submobjects[0].become(made)


def count(n: Number, start: float = 0.0, run: float = 1.4) -> Animation:
    """Count a number() up to its value."""
    return Count(n, start=start, run_time=run)
