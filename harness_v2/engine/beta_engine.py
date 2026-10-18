"""The beta engine: a lecture drawn as slides of boxes, each thing animated on the words that bring it.

Three layers, as slide decks (PowerPoint, Keynote) and JSON video tools (Creatomate, Shotstack) have them:

  WHERE   a slide's layout (full, left-right, top-bottom, title-body, grid-2x2, ...) names its slots; an element
          goes in a slot or in its own box ([x, y, w, h] as shares of the board, y down from the top). A slide is laid
          out once, with every element it will hold, so nothing moves or shrinks to make room later and nothing
          overlaps: elements sharing a slot are stacked in it.
  WHAT    elements: text (title, heading, body, callout, caption, quote), a list, an image (made by the image
          model, its parts labelled), an icon, a number, a shape, an equation, a bar chart, an arrow between two
          elements, a timeline (the engine's own). Each has an id; its parts are named id.part (a list's items
          pts.0, pts.1; an image's labels pic.boiler; a chart's bars).
  HOW     entrances (fade, slide from a side, rise, pop, grow, type, write, draw, stagger, appear), emphasis
          (highlight, circle, underline, pulse, flash, color, dim-others, focus, enlarge), exits, moves. Each starts
          `on` a word or phrase of the line (its time from the voice's word times, else from where it is in the
          line), `with` or `after` another, plus a `delay`; one with none follows the one before.

Every animation is one the exporter writes for the phones (FadeIn with shift and scale, Write, Create, Indicate,
Flash, .animate colour, opacity, move and scale, grouped and lagged), so the beta needs nothing new on the players.

A scene compiled by compile_beta.py:

    class GeneratedScene(BetaLecture):
        def construct(self):
            self.chapter(1, "Title", "", "Narration")
            self.board()
            self.beta_slide("left-right", [ {element}, ... ])   # every element of the slide, laid out, not shown
            self.beat("The line said.", spec={"enter": [...], "animate": [...]})

`self.beat(text, spec=...)` is the beta's beat; the voice tools find its line as they find any beat's, and it is
timed by its own anchors (align_cues does not time it).
"""

from __future__ import annotations

import re

import numpy as np
from manim import (BOLD, DOWN, ITALIC, LEFT, ORIGIN, RIGHT, UP, AnimationGroup, Arrow, Circle, Create, FadeIn,
                   FadeOut, Flash, Group, ImageMobject, Indicate, LaggedStart, Line, Rectangle, RoundedRectangle,
                   SurroundingRectangle, Text, VGroup, VMobject, Write, there_and_back)
from manim.utils.rate_functions import ease_out_back

import pocket_lecture as pl
from pocket_lecture import BEAT_PAD, P, TH, MapLecture, T, fit, narrate, said_at, wrap

# ---------------- where ----------------

# Each layout's slots as shares of the board: (x, y down from the top, width, height).
LAYOUTS: dict[str, dict[str, tuple]] = {
    "full": {"main": (0, 0, 1, 1)},
    "center": {"main": (0.15, 0.06, 0.7, 0.88)},
    "left-right": {"left": (0, 0, 0.5, 1), "right": (0.5, 0, 0.5, 1)},
    "wide-left": {"left": (0, 0, 0.62, 1), "right": (0.62, 0, 0.38, 1)},
    "wide-right": {"left": (0, 0, 0.38, 1), "right": (0.38, 0, 0.62, 1)},
    "top-bottom": {"top": (0, 0, 1, 0.46), "bottom": (0, 0.46, 1, 0.54)},
    "title-body": {"title": (0, 0, 1, 0.2), "body": (0, 0.2, 1, 0.8)},
    "title-left-right": {"title": (0, 0, 1, 0.2), "left": (0, 0.2, 0.5, 0.8), "right": (0.5, 0.2, 0.5, 0.8)},
    "three-col": {"left": (0, 0, 1 / 3, 1), "middle": (1 / 3, 0, 1 / 3, 1), "right": (2 / 3, 0, 1 / 3, 1)},
    "grid-2x2": {"tl": (0, 0, 0.5, 0.5), "tr": (0.5, 0, 0.5, 0.5), "bl": (0, 0.5, 0.5, 0.5), "br": (0.5, 0.5, 0.5, 0.5)},
    "focus-side": {"main": (0, 0, 0.7, 1), "side": (0.7, 0, 0.3, 1)},
}
PAD = 0.18                  # inside a slot's edge
GAP = 0.3                   # between elements stacked in one slot

# ---------------- what ----------------

TEXT_STYLES = {
    # size, colour role, weight, font key
    "title": (38, "TITLE", BOLD, "serif"),
    "heading": (30, "SAND", BOLD, "serif"),
    "body": (24, "CREAM", None, None),
    "callout": (27, "GOLD", BOLD, None),
    "caption": (21, "MUTED", None, None),
    "quote": (27, "CREAM", None, "serif"),
    "label": (22, "SAND", BOLD, None),
}
ELEMENT_KINDS = ("text", "list", "image", "icon", "number", "shape", "equation", "bars", "arrow", "timeline")

# ---------------- how ----------------

ENTRANCES = ("fade", "slide", "rise", "drop", "pop", "grow", "type", "write", "draw", "stagger", "appear")
EMPHASES = ("highlight", "circle", "underline", "pulse", "flash", "color", "dim-others", "focus", "enlarge")
EXITS = ("fade", "slide", "shrink", "unwrite")
SIDES = {"left": LEFT, "right": RIGHT, "up": UP, "top": UP, "down": DOWN, "bottom": DOWN}
DURATIONS = {"fade": 0.8, "slide": 0.9, "rise": 0.8, "drop": 0.8, "pop": 0.7, "grow": 0.9, "type": None, "write": 1.3,
             "draw": 1.6, "stagger": None, "appear": 0.3, "highlight": 0.6, "circle": 0.7, "underline": 0.6,
             "pulse": 0.8, "flash": 0.7, "color": 0.6, "dim-others": 0.6, "focus": 0.7, "enlarge": 0.9,
             "out": 0.6, "move": 1.0}
LEAD = 0.2                  # an animation starts this long before its word, so it is there as the word is heard


def _colour(name, default):
    if not name:
        return default
    try:
        return pl.role(str(name))
    except KeyError:
        return default


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", str(text).strip().lower()).strip("-")


class BetaLecture(MapLecture):
    """A lecture on the beta engine: slides of boxed elements, each animated on its words."""

    def _beta(self) -> dict:
        state = self.__dict__.get("_beta_state")
        if state is None:
            state = self._beta_state = {"layout": "full", "slots": {}, "elements": {}, "parts": {}, "shown": set(),
                                        "specs": {}, "leaving": [], "marks": [], "dimmed": []}
        return state

    # ---------------- the board in units ----------------

    def _board_box(self, share) -> tuple:
        """A box given as shares of the board ([x, y down, w, h]) in scene units: (cx, cy, w, h)."""
        import stem

        bx, by, bw, bh = stem.BOARD
        x, y, w, h = (float(v) for v in share)
        left, top = bx - bw / 2, by + bh / 2
        return (left + (x + w / 2) * bw, top - (y + h / 2) * bh, w * bw, h * bh)

    # ---------------- a slide ----------------

    def beta_slide(self, layout: str, elements: list) -> None:
        """A new slide: every element it will hold built and laid out now, nothing shown. What was on the slide
        before leaves as the next line begins."""
        st = self._beta()
        st["leaving"] = [m for k, m in st["elements"].items() if k in st["shown"]] + st["marks"] + st["dimmed"]
        st["marks"] = []
        st.update(layout=layout if layout in LAYOUTS else "full", elements={}, parts={}, shown=set(), specs={},
                  dimmed=[])
        slots = LAYOUTS[st["layout"]]
        groups: dict[str, list] = {}
        for spec in elements:
            if spec.get("kind") == "arrow":
                continue
            key = spec.get("box") and f"box:{spec['id']}" or (spec.get("slot") if spec.get("slot") in slots
                                                                else next(iter(slots)))
            groups.setdefault(key, []).append(spec)
        # On a slide with arrows, what they join keeps clear of its slot's sides, so the arrows between have room.
        joined = any(spec.get("kind") == "arrow" for spec in elements)
        for key, specs in groups.items():
            box = self._board_box(specs[0]["box"]) if key.startswith("box:") else self._board_box(slots[key])
            self._lay_out(specs, box, 0.66 if joined else 0.92)
        # Arrows last: they join elements laid out above.
        for spec in elements:
            if spec.get("kind") == "arrow":
                mob = self._arrow(spec)
                if mob is not None:
                    self._register(spec, mob)

    def _lay_out(self, specs: list, box: tuple, fill: float = 0.92) -> None:
        """Elements sharing a box stacked down it: each fitted to the box's width and a share of its height by its
        own shape, the stack centred in the box."""
        cx, cy, w, h = box
        inner_w, inner_h = max(0.4, w - 2 * PAD), max(0.4, h - 2 * PAD)
        share = inner_h - GAP * (len(specs) - 1)
        built = []
        for spec in specs:
            each_h = max(0.4, share / len(specs)) if len(specs) > 1 else inner_h
            mob = self._build(spec, inner_w, each_h if spec.get("kind") in ("image", "icon", "timeline") else inner_h)
            if mob is None:
                continue
            built.append((spec, mob))
        if not built:
            return
        stack = Group(*[m for _, m in built]).arrange(DOWN, buff=GAP, aligned_edge=LEFT if all(
            s.get("kind") in ("text", "list") and s.get("align", "left") == "left" for s, _ in built) else ORIGIN)
        # Smaller than its slot, a stack grows into it, as far as its least growable element allows: shapes, numbers
        # and equations a lot, headings some, sentences and pictures not at all (they are sized for reading, or fill
        # their box already). A heading alone in a column was a word in an empty board.
        grow = min(_grow(s) for s, _ in built)
        k = min(inner_w * fill / max(stack.width, 0.01), inner_h * 0.85 / max(stack.height, 0.01), grow)
        if k < 1 or grow > 1:
            stack.scale(min(k, inner_w / max(stack.width, 0.01), inner_h / max(stack.height, 0.01)))
        stack.move_to([cx, cy, 0])
        for spec, mob in built:
            self._register(spec, mob)

    def _register(self, spec: dict, mob) -> None:
        st = self._beta()
        mob.set_z_index(pl.Z_MARK + 12)
        st["elements"][spec["id"]] = mob
        st["specs"][spec["id"]] = spec
        for name, part in (getattr(mob, "beta_parts", None) or {}).items():
            st["parts"][f"{spec['id']}.{name}"] = part

    # ---------------- elements ----------------

    def _build(self, spec: dict, w: float, h: float):
        kind = spec.get("kind")
        try:
            return getattr(self, f"_el_{kind}")(spec, w, h)
        except Exception as error:  # noqa: BLE001 -- an element that cannot be drawn is left out, the rest go on
            pl.skipped(f"beta: {kind} {spec.get('id')!r} left out ({error})")
            return None

    def _text_mob(self, text: str, style: str, w: float, color=None, align: str = "left"):
        size, col, weight, font = TEXT_STYLES.get(style, TEXT_STYLES["body"])
        colour = _colour(color, getattr(P, col, P.CREAM))
        chars = max(10, int(w / (size * 0.0058)))
        kw = {"weight": weight} if weight else {}
        if font:
            kw["font"] = TH.get(font)
        if style == "quote":
            text = f"“{text}”"
        mob = T(wrap(str(text), chars), size, colour, line_spacing=0.9, **kw)
        return fit(mob, w)

    def _el_text(self, spec, w, h):
        style = spec.get("style", "body")
        mob = self._text_mob(spec["text"], style, w, spec.get("color"))
        if style == "callout":
            back = RoundedRectangle(corner_radius=0.14, width=mob.width + 0.5, height=mob.height + 0.36,
                                    fill_color=P.BG, fill_opacity=0.85, stroke_color=mob.get_color(), stroke_width=3)
            back.move_to(mob)
            mob = VGroup(back, mob)
            mob.beta_text = mob[1]
        return mob

    def _el_list(self, spec, w, h):
        items = [str(x) for x in spec.get("items") or []][:8]
        numbered = spec.get("numbered")
        rows = VGroup()
        for i, item in enumerate(items):
            mark = T(f"{i + 1}." if numbered else "•", 24, _colour(spec.get("color"), P.SAND), weight=BOLD)
            words = self._text_mob(item, spec.get("style", "body"), max(0.6, w - 0.55))
            row = VGroup(mark, words).arrange(RIGHT, buff=0.22, aligned_edge=UP)
            rows.add(row)
        rows.arrange(DOWN, buff=0.28, aligned_edge=LEFT)
        rows.beta_parts = {str(i): row for i, row in enumerate(rows)}
        rows.beta_items = list(rows)
        return rows

    def _el_number(self, spec, w, h):
        value = T(str(spec["value"]), 64, _colour(spec.get("color"), P.GOLD), weight=BOLD)
        group = VGroup(fit(value, w))
        if spec.get("label"):
            group.add(self._text_mob(spec["label"], "caption", w))
        return group.arrange(DOWN, buff=0.15)

    def _el_shape(self, spec, w, h):
        kind = spec.get("shape", "box")
        colour = _colour(spec.get("color"), P.SAND)
        inside = self._text_mob(spec["text"], "label", w * 0.8, spec.get("text_color")) if spec.get("text") else None
        bw = min(w, max(1.6, (inside.width + 0.6) if inside else 2.2))
        bh = min(h, max(0.9, (inside.height + 0.5) if inside else 1.4))
        if kind == "circle":
            shape = Circle(radius=min(bw, bh) / 2 + 0.1)
        elif kind == "pill":
            shape = RoundedRectangle(corner_radius=bh / 2, width=bw, height=bh)
        else:
            shape = RoundedRectangle(corner_radius=0.12, width=bw, height=bh)
        shape.set_stroke(colour, 4).set_fill(colour, 0.15)
        return VGroup(shape, inside.move_to(shape)) if inside else VGroup(shape)

    def _el_equation(self, spec, w, h):
        from manim import MathTex

        mob = MathTex(str(spec["tex"]), color=_colour(spec.get("color"), P.CREAM), font_size=56)
        group = VGroup(fit(mob, w))
        if spec.get("label"):
            group.add(self._text_mob(spec["label"], "caption", w))
        return group.arrange(DOWN, buff=0.2)

    def _el_bars(self, spec, w, h):
        """Horizontal bars, each its label, its bar (in proportion to the largest) and its number; parts by order."""
        items = [(str(a), float(b)) for a, b in (spec.get("items") or [])[:8]]
        top = max((v for _, v in items), default=1) or 1
        labels = [T(name, 24, P.CREAM) for name, _ in items]
        label_w = min(max((m.width for m in labels), default=1.0), w * 0.35)
        bar_w = max(0.6, w - label_w - 1.4)
        rows = VGroup()
        for k, ((name, value), label) in enumerate(zip(items, labels)):
            y = -k * 0.62
            fit(label, label_w).move_to([label_w, y, 0], aligned_edge=RIGHT)
            bar = Rectangle(width=max(0.05, bar_w * value / top), height=0.4, stroke_width=0,
                            fill_color=_colour(spec.get("color"), P.RIVER), fill_opacity=0.9)
            bar.move_to([label_w + 0.25, y, 0], aligned_edge=LEFT)
            number = T(f"{value:g}", 21, P.MUTED).next_to(bar, RIGHT, buff=0.15)
            rows.add(VGroup(label, bar, number))
        group = VGroup(rows)
        if spec.get("title"):
            group = VGroup(self._text_mob(spec["title"], "label", w), rows).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        group.beta_parts = {str(i): row for i, row in enumerate(rows)}
        group.beta_items = list(rows)
        return group

    def _el_icon(self, spec, w, h):
        mob = pl.icon_mob(str(spec["name"]), height=min(h, 2.2))
        if spec.get("label"):
            return Group(mob, self._text_mob(spec["label"], "caption", w)).arrange(DOWN, buff=0.15)
        return mob

    def _el_image(self, spec, w, h):
        """A picture in its box; with labels, each name beside it (left-half parts to its left, the rest to its
        right) with a line to its part, the part's box kept for a highlight (id.<label>)."""
        labels = [x for x in spec.get("labels") or [] if isinstance(x, (list, tuple)) and len(x) >= 3]
        # Room for the names only on the sides that have them, as wide as the longest name there: a column
        # kept on both sides, whatever the names, left a wide picture half its box.
        cap = w * 0.3
        widths = {True: 0.0, False: 0.0}
        for row in labels:
            name_w = min(T(str(row[0]), 22, P.SAND, weight=BOLD).width, cap)
            widths[float(row[1]) < 0.5] = max(widths[float(row[1]) < 0.5], name_w + 0.45)
        side = cap
        room = max(0.6, w - widths[True] - widths[False])
        if spec.get("scene"):
            picture = ImageMobject(str(spec["file"]))
            picture.scale_to_fit_height(h)
            if picture.width > room:
                picture.scale_to_fit_width(room)
        else:
            picture = pl.cutout_mob(spec["file"], room, h)
        parts = {}
        group = Group(picture)
        if labels:
            left_x, right_x = picture.get_left()[0] - 0.25, picture.get_right()[0] + 0.25
            x0, y0 = picture.get_left()[0], picture.get_top()[1]
            pw, ph = picture.width, picture.height
            for row in labels:
                name, fx, fy = str(row[0]), float(row[1]), float(row[2])
                point = np.array([x0 + fx * pw, y0 - fy * ph, 0])
                tag = fit(T(name, 22, P.SAND, weight=BOLD), side - 0.1)
                on_left = fx < 0.5
                tag.move_to([left_x, point[1], 0], aligned_edge=RIGHT) if on_left else \
                    tag.move_to([right_x, point[1], 0], aligned_edge=LEFT)
                edge = tag.get_right() if on_left else tag.get_left()
                line = Line(edge + (RIGHT if on_left else LEFT) * 0.06, point, color=P.SAND, stroke_width=2.5)
                dot = Circle(radius=0.05, color=P.SAND, fill_opacity=1).move_to(point)
                label = VGroup(tag, line, dot)
                # The part's box, as shares of the picture: made into a box where the picture is when it is pointed
                # at (the slide's layout moves and scales the picture after this).
                label.beta_share = tuple(float(v) for v in row[3:7]) if len(row) >= 7 else (fx - 0.06, fy - 0.06,
                                                                                             fx + 0.06, fy + 0.06)
                label.beta_picture = picture
                parts[_slug(name)] = label
                group.add(label)
            self._spread_tags([p for p in parts.values()])
        group.beta_parts = parts
        group.beta_picture = picture
        return group

    @staticmethod
    def _spread_tags(labels: list) -> None:
        """Labels on one side too close to read: pushed apart down that side, their lines following."""
        for side in (True, False):
            tags = sorted([lb for lb in labels if (lb[0].get_center()[0] < lb[2].get_center()[0]) == side],
                          key=lambda lb: -lb[0].get_center()[1])
            for upper, lower in zip(tags, tags[1:]):
                need = upper[0].get_bottom()[1] - 0.12 - lower[0].get_top()[1]
                if need < 0:
                    lower[0].shift(DOWN * -need)
            for lb in tags:
                tag, line, dot = lb
                edge = tag.get_right() if side else tag.get_left()
                line.put_start_and_end_on(edge + (RIGHT if side else LEFT) * 0.06, dot.get_center())

    def _el_timeline(self, spec, w, h):
        """The engine's own timeline (in proportion to its dates), drawn into the box instead of onto the stage."""
        captured = []
        keep, stage = self._to_stage, self.__dict__.get("STAGE")
        self._to_stage = lambda group, *a, **k: captured.append(group)
        # Laid out for the box (its track as long as the box is wide, its words sized for it), not for the whole
        # stage and then shrunk into the box.
        self.STAGE = (0.0, 0.0, w, h)
        try:
            self.big_timeline([tuple(e) + (None,) * (3 - len(e)) for e in spec["events"]], spec.get("title"),
                              range=tuple(spec["range"]) if spec.get("range") else None,
                              spans=[tuple(s) for s in spec.get("spans") or []] or None, scale=spec.get("scale"))
        finally:
            self._to_stage = keep
            if stage is None:
                self.__dict__.pop("STAGE", None)
            else:
                self.STAGE = stage
        if not captured:
            return None
        mob = captured[0]
        k = min(w / max(mob.width, 0.01), h / max(mob.height, 0.01))
        return mob.scale(k)

    def _arrow(self, spec):
        st = self._beta()
        a, b = st["elements"].get(spec.get("from")), st["elements"].get(spec.get("to"))
        if a is None or b is None:
            pl.skipped(f"beta: arrow {spec.get('id')!r} joins an element not on the slide")
            return None
        ca, cb = a.get_center(), b.get_center()
        d = cb - ca
        horizontal = abs(d[0]) >= abs(d[1])
        start = (a.get_right() if d[0] > 0 else a.get_left()) if horizontal else (a.get_bottom() if d[1] < 0 else a.get_top())
        end = (b.get_left() if d[0] > 0 else b.get_right()) if horizontal else (b.get_top() if d[1] < 0 else b.get_bottom())
        arrow = Arrow(start, end, buff=0.12, color=_colour(spec.get("color"), P.SAND), stroke_width=5)
        group = VGroup(arrow)
        if spec.get("label"):
            tag = T(str(spec["label"]), 20, P.CREAM)
            tag.next_to(arrow, UP if horizontal else RIGHT, buff=0.1)
            group.add(tag)
        return group

    # ---------------- how: one animation ----------------

    def _target(self, ref: str):
        st = self._beta()
        return st["parts"].get(ref) or st["elements"].get(ref)

    def _entrance(self, mob, how: str, side: str | None, dur: float):
        side_v = SIDES.get(str(side or "").lower())
        letters = getattr(mob, "beta_text", None) or mob
        if how in ("slide", "rise", "drop"):
            # Coming from the left moves right: the shift is the way it travels.
            if how == "rise":
                vector = UP
            elif how == "drop":
                vector = DOWN
            else:
                vector = -side_v if side_v is not None else RIGHT
            return FadeIn(mob, shift=vector * 0.8), dur
        if how == "pop":
            return FadeIn(mob, scale=0.6, rate_func=ease_out_back), dur
        if how == "grow":
            return FadeIn(mob, scale=0.2), dur
        if how == "type" and isinstance(letters, (Text, VGroup)) and not isinstance(mob, Group | ImageMobject) \
                and _glyphs(letters):
            glyphs = _glyphs(letters)
            run = min(3.0, max(0.6, 0.045 * len(glyphs)))
            rest = _rest(mob, [letters]) if letters is not mob else []
            anims = [FadeIn(m) for m in rest] + [LaggedStart(*[FadeIn(g) for g in glyphs], lag_ratio=1.0)]
            return AnimationGroup(*anims), run
        if how == "write" and isinstance(mob, VMobject):
            return Write(mob), dur
        if how == "draw" and isinstance(mob, VMobject):
            return pl.write_in(mob), dur
        if how == "stagger" and len(getattr(mob, "beta_items", None) or mob.submobjects) > 1:
            items = getattr(mob, "beta_items", None) or list(mob.submobjects)
            run = min(3.0, 0.45 * len(items) + 0.4)
            rest = _rest(mob, items)
            return AnimationGroup(*[FadeIn(m) for m in rest],
                                  LaggedStart(*[FadeIn(m, shift=UP * 0.25) for m in items], lag_ratio=0.6)), run
        if how == "appear":
            return FadeIn(mob), 0.3
        return FadeIn(mob), dur

    def _emphasis(self, ref: str, mob, how: str, color, dur: float):
        st = self._beta()
        colour = _colour(color, P.GOLD)
        region = _region(mob)
        lift = lambda m: m.set_z_index(pl.Z_MARK + 13)  # noqa: E731 -- a mark goes over the picture it marks
        if how in ("pulse", "flash", "enlarge") and isinstance(mob, (ImageMobject, Group)) and not isinstance(mob, VMobject):
            how = "highlight"
        if how == "highlight":
            ring = lift(SurroundingRectangle(region, color=colour, buff=0.1, corner_radius=0.08, stroke_width=4))
            st["marks"].append(ring)
            return Create(ring), dur
        if how == "circle":
            ring = lift(Circle(color=colour, stroke_width=4).surround(region, buffer_factor=1.25))
            st["marks"].append(ring)
            return Create(ring), dur
        if how == "underline":
            line = Line(region.get_corner(DOWN + LEFT), region.get_corner(DOWN + RIGHT), color=colour,
                        stroke_width=5).shift(DOWN * 0.08)
            lift(line)
            st["marks"].append(line)
            return Create(line), dur
        if how == "pulse":
            return Indicate(mob, color=colour), dur
        if how == "flash":
            return Flash(mob, color=colour), dur
        if how == "color":
            return mob.animate.set_color(colour), dur
        if how == "enlarge":
            return mob.animate(rate_func=there_and_back).scale(1.12), dur
        if how in ("dim-others", "focus"):
            # A veil of the board's colour over each other element (a picture too), taken off as the next line
            # begins: opacities set and set back lost a shape's own fill.
            others = [m for k, m in st["elements"].items() if k in st["shown"] and k != ref.split(".")[0]]
            veils = [Rectangle(width=m.width + 0.2, height=m.height + 0.2, stroke_width=0, fill_color=P.BG,
                               fill_opacity=0.72).move_to(m).set_z_index(pl.Z_MARK + 12.5) for m in others]
            st["dimmed"] += veils
            anims = [FadeIn(v) for v in veils]
            if how == "focus":
                ring = lift(SurroundingRectangle(region, color=colour, buff=0.1, corner_radius=0.08, stroke_width=4))
                st["marks"].append(ring)
                anims.append(Create(ring))
            return (AnimationGroup(*anims) if anims else None), dur
        return Indicate(mob, color=colour), dur

    # ---------------- a beat ----------------

    def beat(self, text: str, *anims, rt: float | None = None, pad: float | None = None, cues: list | None = None,
             spec: dict | None = None) -> float:
        if spec is None:
            return super().beat(text, *anims, rt=rt, pad=pad, cues=cues)
        st = self._beta()
        pad = BEAT_PAD if pad is None else pad
        wav, seconds = narrate(text)
        self._log("beat", text=text, seconds=round(seconds, 3), wav=wav)
        pl._progress_beat()
        try:
            words = pl.line_words(text) if pl.voice_mode() != "silent" else None
        except Exception:  # noqa: BLE001 -- no word times: places in the line stand in for them
            words = None
        pieces = pl.caption_pieces(text)
        cap = self.caption(pieces[0])
        swaps = self._caption_swaps(text, pieces, seconds, words)
        self._speak(wav, seconds)
        if self.cap is not None:
            self.remove(self.cap)
        self.add(cap)
        self.cap = cap
        plan = self._beta_plan(text, spec, seconds, words)
        given = [(a, [start, run]) for start, run, a in sorted(plan, key=lambda p: p[0])]
        spent = 0.0
        if given:
            cued = self._cue_plan(given, [], seconds, 0.8)
            spent = self._play_cued(cued, swaps)
        self._beat_span = max(0.6, seconds + pad - spent)
        spent = self._wait_until(spent, seconds + pad, swaps)
        self._voice_done(pad)
        self._sync_beat = self.__dict__.get("_sync_beat", 0) + 1
        return seconds

    def _beta_plan(self, text: str, spec: dict, seconds: float, words) -> list:
        """[(start, seconds, animation)] for the beat: what leaves (the slide before, last beat's marks and dimming)
        at the line's start, then each element's entrance and each animation at its time."""
        st = self._beta()
        out = []
        going = list(st.pop("leaving", []) or [])
        if not going:
            going = list(st["marks"])
        st["marks"] = [m for m in st["marks"] if m not in going]
        if spec.get("clear"):
            going += [m for k, m in st["elements"].items() if k in st["shown"]] + st["marks"]
            st["shown"] = set()
            st["marks"] = []
        if going:
            out.append((0.0, 0.5, AnimationGroup(*[FadeOut(m) for m in going])))
        if st["dimmed"]:
            out.append((0.0, 0.5, AnimationGroup(*[FadeOut(v) for v in st["dimmed"]])))
            st["dimmed"] = []
        start0 = 0.5 if out else 0.0
        steps = list(spec.get("animate") or [])
        named = {s.get("id") for s in steps if s.get("in") or (not s.get("emphasis") and not s.get("out")
                                                                 and not s.get("move"))}
        # An element entering this beat that no step names comes on in its turn with a fade; one whose parts come
        # on one by one brings only what is not a part (a chart's title), its parts each on their own step.
        for key in spec.get("enter") or []:
            if key in named:
                continue
            if any(str(n).startswith(f"{key}.") for n in named):
                mob = st["elements"].get(key)
                parts = list((getattr(mob, "beta_parts", None) or {}).values())
                rest = _rest(mob, parts) if mob is not None else []
                st["shown"].add(key)
                if rest:
                    out.append((start0, 0.6, AnimationGroup(*[FadeIn(m) for m in rest])))
                continue
            steps.append({"id": key, "in": "fade"})
        ends: dict[str, float] = {}
        starts: dict[str, float] = {}
        last_end = start0
        for step in steps:
            ref = str(step.get("id") or "")
            mob = self._target(ref)
            if mob is None:
                pl.skipped(f"beta: nothing on the slide is called {ref!r}")
                continue
            how = step.get("in") or step.get("emphasis") or ("out" if step.get("out") else None) or \
                ("move" if step.get("move") else None) or "fade"
            dur = float(step.get("dur") or DURATIONS.get(how) or DURATIONS.get(step.get("out") or "", 0.8) or 0.8)
            anim = None
            if step.get("out"):
                anim, dur = self._exit(mob, step["out"], step.get("to"), dur)
                st["shown"].discard(ref)
            elif step.get("move"):
                anim = self._move(mob, step["move"])
            elif step.get("emphasis"):
                anim, dur = self._emphasis(ref, mob, step["emphasis"], step.get("color"), dur)
            else:
                anim, dur = self._entrance(mob, step.get("in") or "fade", step.get("from"), dur)
                st["shown"].add(ref.split(".")[0])
            if anim is None:
                continue
            at = None
            if step.get("on"):
                at = self._word_time(text, str(step["on"]), seconds, words)
                if at is not None:
                    at = max(0.0, at - LEAD)
            if at is None and step.get("with") in starts:
                at = starts[step["with"]]
            if at is None and step.get("after") in ends:
                at = ends[step["after"]]
            if at is None:
                at = last_end
            at = max(at + float(step.get("delay") or 0), start0 if step.get("on") is None else 0.0)
            starts[ref] = at
            ends[ref] = at + dur
            last_end = max(last_end, at + dur)
            out.append((at, dur, anim))
        return out

    def _exit(self, mob, how: str, side, dur: float):
        side_v = SIDES.get(str(side or "").lower())
        if how == "slide":
            return FadeOut(mob, shift=(side_v if side_v is not None else LEFT) * 0.8), dur
        if how == "shrink":
            return FadeOut(mob, scale=0.3), dur
        return FadeOut(mob), dur

    def _move(self, mob, where):
        st = self._beta()
        slots = LAYOUTS.get(st["layout"], {})
        share = slots.get(where) if isinstance(where, str) else where
        if not share:
            return None
        cx, cy, w, h = self._board_box(share)
        k = min((w - 2 * PAD) / max(mob.width, 0.01), (h - 2 * PAD) / max(mob.height, 0.01), 1.6)
        return mob.animate.scale(k).move_to([cx, cy, 0])

    @staticmethod
    def _word_time(text: str, phrase: str, seconds: float, words) -> float | None:
        """When the line says `phrase`: from the voice's word times, else from where it stands in the line."""
        if words:
            at = said_at(words, phrase)
            if at is not None:
                return float(at)
        spot = text.lower().find(phrase.lower().strip())
        if spot < 0:
            return None
        return seconds * spot / max(len(text), 1)


# How much an element may grow to fill its slot (1: not at all).
GROW = {"shape": 1.8, "equation": 1.7, "number": 1.5, "bars": 1.3, "icon": 1.3, "list": 1.45, "arrow": 1.0, "image": 1.0,
        "timeline": 1.0}
TEXT_GROW = {"title": 1.3, "heading": 1.5, "callout": 1.3, "quote": 1.25, "label": 1.4}


def _grow(spec: dict) -> float:
    if spec.get("kind") == "text":
        return TEXT_GROW.get(spec.get("style", "body"), 1.0)
    return GROW.get(spec.get("kind"), 1.0)


def _region(mob):
    """What a highlight goes round: a picture's part's box where the picture now is, else the thing itself."""
    share, picture = getattr(mob, "beta_share", None), getattr(mob, "beta_picture", None)
    if share is None or picture is None:
        return mob
    x0, y0, x1, y1 = share
    left, top = picture.get_left()[0], picture.get_top()[1]
    pw, ph = picture.width, picture.height
    return Rectangle(width=max(0.2, (x1 - x0) * pw), height=max(0.2, (y1 - y0) * ph)) \
        .move_to([left + (x0 + x1) / 2 * pw, top - (y0 + y1) / 2 * ph, 0])


def _rest(mob, parts: list) -> list:
    """What a group holds besides `parts`: its children that are not a part and hold none (a chart's title)."""
    within = {id(x) for p in parts for x in p.get_family()}
    out, todo = [], list(mob.submobjects)
    while todo:
        m = todo.pop(0)
        if id(m) in within:
            continue
        family = {id(x) for x in m.get_family()}
        if family & within:
            todo.extend(m.submobjects)
        else:
            out.append(m)
    return out


def _glyphs(mob) -> list:
    """A text's letters, in reading order: the submobjects with points."""
    out = [m for m in mob.family_members_with_points() if isinstance(m, VMobject) and not isinstance(m, Text)]
    return out if 1 < len(out) <= 400 else []
