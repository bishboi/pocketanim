"""Things on the page: cards, chips, tags, sticky notes, newspaper clippings, documents with seals, books, scrolls,
portrait cards, stat cards and lists. Each is a piece (named parts, its own entrance) drawn in the look: vox puts
paper cards with soft shadows on the page; blueprint draws them as outlined drafting panels.

    c = card(4, 2.5, title="Official history", body="Written by court departments", kick="CHINA")
    p = portrait("Sima Qian", "145–86 BCE", picture=person(hat="official", beard="long", clothes="robe"))
    d = document("史記", lines=9, seal="史", vertical=True)       # a page of Chinese text with a red seal
    b = book("Science and Civilisation in China", color="#2A5D8F")
    s = scroll("The Records of the Grand Historian", width=7)     # appears by unrolling
    l = checklist(["Official histories", "Scholarly writing", "Literature"]); self.play(l.reveal(0))
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, PI, RIGHT, UP, Circle, DashedVMobject, Dot, Group, ImageMobject, Line,
                   Polygon, Rectangle, RoundedRectangle, Square, VGroup, VMobject)

from manim import rate_functions as rf

from .base import Piece, PictureGroup
from .look import L
from .text import fit, kicker, script_of, text


def shadow_of(shape, offset=(0.08, -0.1), layers: int = 3, opacity: float = 0.16) -> VGroup:
    """A soft shadow under a shape (stacked translucent copies)."""
    look = L()
    g = VGroup()
    for i in range(layers):
        s = shape.copy().set_stroke(width=0).set_fill(look.shadow_color, opacity=opacity / (i + 1))
        s.shift(np.array([offset[0], offset[1], 0]) * (1 + i * 0.35))
        s.scale(1 + 0.012 * i)
        g.add(s)
    g.set_z_index(shape.z_index - 1)
    return g


def panel(width: float, height: float, fill: str | None = None, radius: float | None = None,
          edge: bool | None = None) -> VGroup:
    """The bare surface of a card in the look (with its shadow in vox; corner ticks in blueprint)."""
    look = L()
    r = look.radius if radius is None else radius
    box = RoundedRectangle(width=width, height=height, corner_radius=r, fill_color=fill or look.card,
                           fill_opacity=max(look.card_opacity, 0.0), stroke_color=look.card_edge,
                           stroke_width=(look.stroke * 0.5 if edge is None or edge else 0))
    if look.name == "vox" and edge is None:
        box.set_stroke(width=0)
    g = VGroup()
    if look.shadow:
        g.add(shadow_of(box))
    g.add(box)
    if look.name == "blueprint":
        ticks = VGroup()
        for v in box.get_vertices() if r == 0 else []:
            for d in (RIGHT, UP):
                ticks.add(Line(v - d * 0.18, v + d * 0.18, stroke_color=look.ink, stroke_width=1.5))
        g.add(ticks)
    g.box = box
    return g


class Card(Piece):
    enter_kind = "shape"


def card(width: float = 4.0, height: float = 2.6, title: str | None = None, body: str | None = None,
         kick: str | None = None, fill: str | None = None, tilt: float = 0.0, title_size: float = 34,
         body_size: float = 24, content=None, pad: float = 0.3) -> Card:
    """A card with an optional kicker, title and body (wrapped to fit), or any `content` mobject inside it."""
    look = L()
    surf = panel(width, height, fill)
    c = Card(surf)
    c.name_part("panel", surf)
    inner_w = width - 2 * pad
    stack = VGroup()
    if kick:
        k = kicker(kick, size=18)
        stack.add(k)
        c.name_part("kicker", k)
    if title:
        t = text(title, size=title_size, role="head", width=inner_w)
        stack.add(t)
        c.name_part("title", t)
    if body:
        b = text(body, size=body_size, color=look.muted if look.name == "vox" else look.ink, width=inner_w)
        stack.add(b)
        c.name_part("body", b)
    if content is not None:
        stack.add(content)
        c.name_part("content", content)
    if len(stack):
        stack.arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        fit(stack, inner_w, height - 2 * pad)
        stack.move_to(surf.box).align_to(surf.box, LEFT).shift(RIGHT * pad)
        if content is not None and not (kick or title or body):
            stack.move_to(surf.box)
        c.add(stack)
    if tilt:
        c.rotate(tilt * PI / 180)
    return c


def chip(words: str, color: str | None = None, ink: str | None = None, size: float = 22, pad: float = 0.16) -> Card:
    """A rounded pill with words (a category, a date, a tag)."""
    look = L()
    t = text(words, size=size, color=ink or (look.bg if look.name == "vox" else look.ink), weight=True)
    pill = RoundedRectangle(width=t.width + 2 * pad + 0.1, height=t.height + 1.4 * pad,
                            corner_radius=(t.height + 1.4 * pad) / 2, stroke_width=0 if look.name == "vox" else 2,
                            stroke_color=look.ink, fill_color=color or look.accent,
                            fill_opacity=1 if look.name == "vox" else 0.35).move_to(t)
    c = Card(pill, t)
    c.name_part("pill", pill)
    c.name_part("words", t)
    return c


def tag(words: str, color: str | None = None, size: float = 22) -> Card:
    """A luggage tag (vox) or a bracketed spec label (blueprint)."""
    look = L()
    t = text(words, size=size, role="body" if look.name == "vox" else "mono", weight=True,
             color=look.ink)
    if look.name == "blueprint":
        lb, rb = (text(s, size=size, role="mono", color=look.accent) for s in ("[", "]"))
        lb.next_to(t, LEFT, buff=0.08)
        rb.next_to(t, RIGHT, buff=0.08)
        c = Card(lb, t, rb)
        c.name_part("words", t)
        return c
    w, h = t.width + 0.6, t.height + 0.3
    shape = Polygon(LEFT * w / 2 + UP * h / 2, RIGHT * (w / 2 - 0.25) + UP * h / 2, RIGHT * w / 2,
                    RIGHT * (w / 2 - 0.25) + DOWN * h / 2, LEFT * w / 2 + DOWN * h / 2, stroke_width=0,
                    fill_color=color or look.card, fill_opacity=1)
    hole = Circle(radius=0.05, stroke_width=1.5, stroke_color=look.ink, fill_color=look.bg, fill_opacity=1)
    hole.move_to(shape.get_right() + LEFT * 0.17)
    t.move_to(shape).shift(LEFT * 0.1)
    c = Card(shadow_of(shape), shape, hole, t)
    c.name_part("words", t)
    return c


def sticky(words: str, color: str | None = None, size: float = 28, width: float = 2.6, tilt: float = -3) -> Card:
    """A sticky note in handwriting."""
    look = L()
    sq = Square(side_length=width, stroke_width=0 if look.name == "vox" else 2, stroke_color=look.ink,
                fill_color=color or ("#FFE27A" if look.name == "vox" else look.card),
                fill_opacity=1 if look.name == "vox" else 0.6)
    t = text(words, size=size, role="hand", color="#1B1B1B" if look.name == "vox" else look.ink, width=width - 0.4)
    fit(t, width - 0.4, width - 0.4)
    t.move_to(sq)
    c = Card(shadow_of(sq) if look.shadow else VGroup(), sq, t)
    c.name_part("words", t)
    c.rotate(tilt * PI / 180)
    return c


def _text_lines(width: float, n: int, start, gap: float, color, vertical: bool = False, seed: int = 4) -> VGroup:
    """Grey bars standing in for lines of text (a page seen from a distance)."""
    rng = np.random.default_rng(seed)
    g = VGroup()
    for i in range(n):
        length = width * (0.62 + 0.38 * rng.random()) if i % 5 != 4 else width * 0.45
        if vertical:
            ln = Line(start + LEFT * i * gap, start + LEFT * i * gap + DOWN * length, stroke_color=color, stroke_width=5)
        else:
            ln = Line(start + DOWN * i * gap, start + DOWN * i * gap + RIGHT * length, stroke_color=color, stroke_width=5)
        g.add(ln)
    return g


def document(title: str | None = None, lines: int = 9, width: float = 3.2, height: float = 4.2,
             seal: str | None = None, vertical: bool | None = None, paper: str | None = None, tilt: float = 0.0,
             title_size: float = 30) -> Card:
    """A page: a title, lines of text (grey bars), and an optional red seal with characters ("史", "官"). Vertical
    columns read right to left for Chinese/Japanese titles (or `vertical=True`)."""
    look = L()
    vox = look.name == "vox"
    vertical = script_of(title or "") == "cjk" if vertical is None else vertical
    page = Rectangle(width=width, height=height, stroke_width=0 if vox else 2, stroke_color=look.ink,
                     fill_color=paper or ("#F7F0DF" if vox else look.card), fill_opacity=1 if vox else 0.5)
    g = Card()
    if look.shadow:
        g.add(shadow_of(page))
    g.add(page)
    g.name_part("page", page)
    bar_c = "#B9AE98" if vox else look.muted
    if vertical:
        t = None
        if title:
            t = text("\n".join(title), size=title_size, role="serif", color=look.ink, line_spacing=0.8)
            fit(t, width * 0.25, height - 0.5)
            t.move_to(page.get_corner(UP + RIGHT) + LEFT * (0.25 + t.width / 2) + DOWN * (0.3 + t.height / 2))
            g.add(t)
            g.name_part("title", t)
        start = page.get_corner(UP + RIGHT) + LEFT * (0.35 + (t.width + 0.3 if t else 0)) + DOWN * 0.35
        cols = int((width - 0.6 - (t.width + 0.3 if t else 0)) / 0.3)
        body = _text_lines(height - 0.7, max(2, min(lines, cols)), start, 0.3, bar_c, vertical=True)
    else:
        top = page.get_top() + DOWN * 0.35
        if title:
            t = text(title, size=title_size, role="serif", color=look.ink, width=width - 0.5)
            t.move_to(top + DOWN * t.height / 2)
            g.add(t)
            g.name_part("title", t)
            top = t.get_bottom() + DOWN * 0.3
        rows = max(1, min(lines, int((top[1] - page.get_bottom()[1] - 0.3) / 0.32) + 1))
        body = _text_lines(width - 0.6, rows, np.array([page.get_left()[0] + 0.3, top[1], 0]), 0.32, bar_c)
    g.add(body)
    g.name_part("lines", body)
    if seal:
        s = text(seal, size=26, role="head", color="#F7F0DF" if vox else look.bg, weight=True)
        sq = Square(side_length=max(s.width, s.height) + 0.22, stroke_width=0, fill_color="#B3261E" if vox else look.accent,
                    fill_opacity=0.92)
        s.move_to(sq)
        seal_m = VGroup(sq, s).move_to(page.get_corner(DOWN + LEFT) + RIGHT * 0.55 + UP * 0.55).rotate(4 * PI / 180)
        g.add(seal_m)
        g.name_part("seal", seal_m)
    if tilt:
        g.rotate(tilt * PI / 180)
    return g


def clipping(headline_text: str, lines: int = 6, masthead: str | None = None, date: str | None = None,
             width: float = 4.2, tilt: float = -2.0, seed: int = 2) -> Card:
    """A newspaper clipping with torn edges: a masthead, a headline in serif, columns of text."""
    look = L()
    rng = np.random.default_rng(seed)
    vox = look.name == "vox"
    inner = VGroup()
    if masthead:
        m = text(masthead, size=18, role="serif", weight=True, color=look.ink)
        inner.add(m)
    h = text(headline_text, size=34, role="serif", weight=True, color=look.ink, width=width - 0.5)
    inner.add(h)
    if date:
        inner.add(text(date, size=16, role="mono", color=look.muted))
    inner.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
    col_w = (width - 0.7) / 2
    cols = VGroup(*(_text_lines(col_w, lines, ORIGIN, 0.24, "#B5AA94" if vox else look.muted, seed=seed + i)
                    for i in range(2))).arrange(RIGHT, buff=0.2, aligned_edge=UP)
    cols.next_to(inner, DOWN, buff=0.25, aligned_edge=LEFT)
    content = VGroup(inner, cols)
    w, hh = width, content.height + 0.6
    xs = np.linspace(-w / 2, w / 2, 18)
    ys = np.linspace(-hh / 2, hh / 2, 12)
    jag = lambda: rng.uniform(-0.05, 0.05)
    pts = ([(x, hh / 2 + jag()) for x in xs] + [(w / 2 + jag(), y) for y in ys[::-1]] +
           [(x, -hh / 2 + jag()) for x in xs[::-1]] + [(-w / 2 + jag(), y) for y in ys])
    paper = Polygon(*[np.array([x, y, 0]) for x, y in pts], stroke_width=0 if vox else 1.5, stroke_color=look.ink,
                    fill_color="#EFE8D8" if vox else look.card, fill_opacity=1 if vox else 0.5)
    content.move_to(paper)
    c = Card(*( [shadow_of(paper)] if look.shadow else []), paper, content)
    c.name_part("paper", paper)
    c.name_part("headline", h)
    c.name_part("columns", cols)
    c.rotate(tilt * PI / 180)
    return c


def book(title: str, color: str | None = None, width: float = 2.2, height: float = 3.0, author: str | None = None,
         tilt: float = 0.0) -> Card:
    """A book seen from the front: a cover in `color`, a spine band, the title (and author)."""
    look = L()
    vox = look.name == "vox"
    c_ = color or look.palette[2]
    cover = RoundedRectangle(width=width, height=height, corner_radius=0.05, stroke_width=0 if vox else 2,
                             stroke_color=look.ink, fill_color=c_, fill_opacity=1 if vox else 0.4)
    spine = Rectangle(width=0.18, height=height, stroke_width=0, fill_color="#000000", fill_opacity=0.22)
    spine.align_to(cover, LEFT)
    band = Rectangle(width=width - 0.18, height=0.08, stroke_width=0, fill_color="#F2D16B" if vox else look.accent,
                     fill_opacity=0.9).align_to(cover, RIGHT).shift(UP * height * 0.3)
    t = text(title, size=26, role="serif", weight=True, color="#F7F0DF" if vox else look.ink, width=width - 0.5,
             align="center")
    fit(t, width - 0.5, height * 0.5)
    t.move_to(cover).shift(RIGHT * 0.09 + DOWN * height * 0.05)
    g = Card(*([shadow_of(cover)] if look.shadow else []), cover, spine, band, t)
    g.name_part("cover", cover)
    g.name_part("title", t)
    if author:
        a = text(author, size=16, color="#F7F0DF" if vox else look.muted)
        fit(a, width - 0.5)
        a.next_to(cover.get_bottom(), UP, buff=0.25).shift(RIGHT * 0.09)
        g.add(a)
        g.name_part("author", a)
    if tilt:
        g.rotate(tilt * PI / 180)
    return g


def shelf(titles: list[str], colors=None, height: float = 3.0) -> Piece:
    """Book spines standing side by side (a library, an archive, a multi-volume work)."""
    look = L()
    rng = np.random.default_rng(6)
    g = Piece()
    for i, title in enumerate(titles):
        w = 0.42 + 0.18 * rng.random()
        h = height * (0.82 + 0.18 * rng.random())
        c_ = (colors or look.palette)[i % len(colors or look.palette)]
        spine = Rectangle(width=w, height=h, stroke_width=0 if look.name == "vox" else 1.5, stroke_color=look.ink,
                          fill_color=c_, fill_opacity=1 if look.name == "vox" else 0.4)
        t = text(title, size=16, weight=True, color="#F7F0DF" if look.name == "vox" else look.ink)
        t.rotate(PI / 2)
        fit(t, w * 0.8, h * 0.8)
        t.move_to(spine)
        g.add(VGroup(spine, t))
    g.arrange(RIGHT, buff=0.03, aligned_edge=DOWN)
    base = Line(g.get_corner(DOWN + LEFT) + LEFT * 0.2, g.get_corner(DOWN + RIGHT) + RIGHT * 0.2,
                stroke_color=look.ink, stroke_width=look.stroke)
    g.add(base)
    return g


class Scroll(Card):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from manim import AnimationGroup, FadeIn
        from .motion import Unfold, later, owned
        run = run if run is not None else L().run * 2.2
        paper, writing = self.part("paper"), self.part("writing")
        left, right = self.part("rollers")
        start = right.get_center().copy()
        right.move_to(left.get_center() + RIGHT * 0.25)
        return owned(self, AnimationGroup(FadeIn(self.part("rollers"), run_time=0.2),
                                          Unfold(paper, LEFT, run_time=run),
                                          right.animate(run_time=run, rate_func=rf.ease_out_cubic).move_to(start),
                                          later(FadeIn(writing, run_time=run * 0.4), run * 0.7)))


def scroll(title: str | None = None, width: float = 6.5, height: float = 2.6, lines: int = 14,
           vertical: bool | None = None) -> Scroll:
    """A handscroll: paper between two wooden rollers, with a title and columns of text. Appears by unrolling."""
    look = L()
    vox = look.name == "vox"
    vertical = script_of(title or "") == "cjk" if vertical is None else vertical
    paper = Rectangle(width=width, height=height, stroke_width=0 if vox else 2, stroke_color=look.ink,
                      fill_color="#EFE3C4" if vox else look.card, fill_opacity=1 if vox else 0.45)
    sheet = VGroup(paper)
    bar_c = "#A89878" if vox else look.muted
    if vertical:
        cols = _text_lines(height - 0.6, min(lines, int((width - 0.8) / 0.3)), paper.get_corner(UP + RIGHT) + LEFT * 0.4 + DOWN * 0.3,
                           0.3, bar_c, vertical=True)
        sheet.add(cols)
    else:
        rows = _text_lines(width - 1.0, min(lines, int((height - 0.9) / 0.3)), paper.get_corner(UP + LEFT) + RIGHT * 0.5 + DOWN * 0.75,
                           0.3, bar_c)
        sheet.add(rows)
    if title:
        t = text(title, size=30, role="serif", weight=True, color=look.ink, width=width - 1)
        if vertical:
            t = text("\n".join(title), size=28, role="serif", weight=True, color=look.ink, line_spacing=0.8)
            fit(t, 0.6, height - 0.4)
            t.move_to(paper.get_right() + LEFT * 0.45)
            sheet[1].shift(LEFT * 0.5)
        else:
            t.move_to(paper.get_top() + DOWN * 0.42)
        sheet.add(t)
    rollers = VGroup()
    for side in (LEFT, RIGHT):
        r = RoundedRectangle(width=0.22, height=height + 0.5, corner_radius=0.1, stroke_width=0 if vox else 2,
                             stroke_color=look.ink, fill_color="#6B3E22" if vox else look.card, fill_opacity=1)
        r.next_to(paper, side, buff=-0.05)
        rollers.add(r)
    s = Scroll(*([shadow_of(paper)] if look.shadow else []), sheet, rollers)
    s.name_part("sheet", sheet)
    s.name_part("paper", paper)
    s.name_part("writing", VGroup(*sheet[1:]))
    s.name_part("rollers", rollers)
    return s


def portrait(name: str, years: str | None = None, picture=None, role: str | None = None, width: float = 2.8,
             picture_height: float = 2.6, tilt: float | None = None, color: str | None = None,
             how: str | None = None) -> Piece:
    """A portrait card: a picture (a file, treated in the look; a mobject such as person(); or None for a
    silhouette), the name, the years and a role. Vox: a paper card with a coloured band; blueprint: a spec sheet."""
    from .images import photo
    from .people import person

    look = L()
    vox = look.name == "vox"
    band_c = color or look.accent
    inner_w = width - 0.3
    if picture is None:
        pic = person(silhouette=True, height=picture_height)
    elif isinstance(picture, (str,)) or hasattr(picture, "__fspath__"):
        pic = photo(picture, height=picture_height, how=how, frame="none" if not vox else "border", tilt=0, tape=False)
        if pic.width > inner_w:
            pic.scale_to_fit_width(inner_w)
    else:
        pic = picture
        fit(pic, inner_w, picture_height)
    words = VGroup()
    n = text(name, size=30, role="head", width=inner_w)
    words.add(n)
    if years:
        words.add(text(years, size=22, role="mono", color=band_c if vox else look.accent))
    if role:
        words.add(text(role, size=20, color=look.muted, width=inner_w))
    words.arrange(DOWN, buff=0.08)
    height = picture_height + words.height + 0.75
    surf = panel(width, height)
    pic.move_to(surf.box.get_top() + DOWN * (0.2 + picture_height / 2))
    window = Rectangle(width=inner_w, height=picture_height, stroke_width=0,
                       fill_color="#D8CDB8" if vox else look.bg, fill_opacity=1 if vox else 0.4)
    window.move_to(pic)
    band = Rectangle(width=width, height=0.12, stroke_width=0, fill_color=band_c, fill_opacity=1)
    band.move_to(window.get_bottom())
    words.next_to(band, DOWN, buff=0.18)
    cls = PictureGroup if isinstance(pic, Group) and not isinstance(pic, VGroup) else Piece
    g = cls(surf, window, pic, band, words)
    g.name_part("panel", surf)
    g.name_part("picture", pic)
    g.name_part("name", n)
    g.name_part("words", words)
    t = look.tilt if tilt is None else tilt
    if t:
        g.rotate(-t * PI / 180)
    return g


def stat(value: str, words: str, color: str | None = None, width: float = 3.4, size: float = 72) -> Card:
    """A big figure with its meaning under it; count(card.part('number')) counts it up."""
    from .text import number
    look = L()
    n = number(value, size=size, color=color or look.accent)
    w = text(words, size=24, color=look.muted if look.name == "vox" else look.ink, width=width - 0.4)
    stack = VGroup(n, w).arrange(DOWN, buff=0.15)
    surf = panel(max(width, stack.width + 0.6), stack.height + 0.7)
    stack.move_to(surf.box)
    c = Card(surf, stack)
    c.name_part("number", n)
    c.name_part("words", w)
    return c


class Checklist(Piece):
    def reveal(self, i: int, run: float | None = None):
        """Item i comes on (its marker, then its words)."""
        from .motion import enter
        from manim import AnimationGroup
        row = self.rows[i]
        return AnimationGroup(enter(row[0], "pop", run=run), enter(row[1], "rise", run=run), lag_ratio=0.3)

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned, stagger
        return owned(self, stagger([self.reveal(i, run) for i in range(len(self.rows))], lag=0.25))


def checklist(items: list[str], marker: str = "dot", size: float = 28, width: float = 6.0, gap: float = 0.28,
              color: str | None = None) -> Checklist:
    """A list: each row a marker (dot, number, tick, square) and its words. .reveal(i) brings on row i."""
    from .marks import tick
    look = L()
    c_ = color or look.accent
    rows = []
    for i, item in enumerate(items):
        if marker == "number":
            mk = text(str(i + 1), size=size, role="head", color=c_)
        elif marker == "tick":
            mk = tick(size=0.5, color=c_)
        elif marker == "square":
            mk = Square(side_length=0.22, stroke_color=c_, stroke_width=2.5, fill_color=c_, fill_opacity=0.25)
        else:
            mk = Dot(radius=0.08, color=c_)
        words = text(item, size=size, width=width)
        row = VGroup(mk, words).arrange(RIGHT, buff=0.25, aligned_edge=UP if "\n" in str(words[0].text) else ORIGIN)
        rows.append(row)
    g = Checklist(*rows).arrange(DOWN, aligned_edge=LEFT, buff=gap)
    g.rows = rows
    return g
