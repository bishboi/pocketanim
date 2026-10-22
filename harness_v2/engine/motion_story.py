"""Motion templates for history and storytelling (beta: MOTION_ENGINE.md §3): causes feeding an event, a person as a
card, a source set against what is now known, a population by age, people moving between regions, a famous line
spoken word by word, a front page, a letter, a countdown. Each builds part by part on the words that name it. A mixin
of motion.MotionLecture (it uses the lecture's template plumbing: _titled, _fit, _show, _hold_back, _moment, _part).

    cause_web          causes on one side, each joined to the event by an arrow as thick as its weight, on its words
    portrait_card      a person as a trading card: picture, name, dates, role; their facts dealt onto it as said
    source_vs_reality  a source's claim on the left; what historians now hold slides in beside it; a verdict stamped
    population_pyramid two-sided bars by age group growing out from the middle
    migration_flow     regions as discs; flows between them drawn as arcs as wide as the numbers who moved
    quote_reveal       a famous line set large, word by word with the voice, the speaker's portrait fading in
    newspaper          a front page spun onto the board: masthead, date, the headline slammed, columns, a picture
    letter             a handwritten letter written onto a sheet, signed at the end
    countdown          years (or steps) ticking down on a big flip display to the event, which lands last
"""

from __future__ import annotations

import math

import numpy as np
from manim import (BOLD, DOWN, LEFT, ORIGIN, RIGHT, UP, AnimationGroup, ArcBetweenPoints, Circle, FadeIn, FadeOut, Group,
                   Line, Rectangle, RoundedRectangle, Triangle, VGroup)
from manim.utils.rate_functions import ease_out_back, ease_out_cubic, ease_out_expo, smooth

import motion_kit as K
import pocket_lecture as pl
from pocket_lecture import Z_MARK, fit

Z_TEMPLATE = Z_MARK + 10


def _ink(fill: str) -> str:
    try:
        return "#111111" if pl._luminance(str(fill)) > 0.45 else "#FFFFFF"
    except Exception:  # noqa: BLE001
        return "#111111"


def _said(on, *names) -> list[str]:
    if str(on or "").strip():
        return [str(on)]
    return [str(n) for n in names if str(n or "").strip()]


def _spec(item, key: str) -> dict:
    return item if isinstance(item, dict) else {key: str(item)}


def _num(v, default=None):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _serif() -> str:
    return "EB Garamond"


def _hand() -> str:
    return "Caveat"


class StoryTemplates:
    """The templates of this module, as MotionLecture's m_<op> methods."""

    # ---------------------------------------------------------------- cause_web ---------------------------------
    def m_cause_web(self, causes, effect, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """The event (`effect`: a text or {text, on, picture?}) on the right; its causes ({text, weight 1-3, on}) in a
        column on the left, each slid in and joined to the event by an arrow as thick as its weight as it is said;
        the event pulses as the last cause lands."""
        P = pl.P
        tid = id or self._next_id("cause_web")
        specs = [_spec(c, "text") for c in (causes or [])][:6]
        if not specs:
            return None
        e = _spec(effect, "text")
        tone = K.col("accent")
        target_words = fit(K.head(str(e.get("text", "")), 34, _ink(tone)), 3.6)
        target = VGroup(RoundedRectangle(width=target_words.width + 0.8, height=target_words.height + 0.7,
                                         corner_radius=0.12, stroke_width=0, fill_color=tone, fill_opacity=1),
                        target_words)
        target[1].move_to(target[0])
        target.move_to([3.6, 0, 0])
        n = len(specs)
        made = []
        ys = np.linspace(2.2, -2.2, n) if n > 1 else [0.0]
        for s, y in zip(specs, ys):
            words = fit(K.body(str(s.get("text", "")), 24, K.col("card_ink"), 22), 3.6)
            face = K.card(words.width + 0.6, words.height + 0.45)
            words.move_to(face.face)
            card = K.group_of(face, words).move_to([-3.4, y, 0])
            w = int(min(3, max(1, _num(s.get("weight"), 2) or 2)))
            start = card.get_right() + RIGHT * 0.1
            end = target.get_left() + LEFT * 0.12 + UP * (y * 0.18)
            arrow = K.arrow_between(start, end, K.col("accent") if w >= 3 else P.MUTED if w == 1 else P.CREAM,
                                    curve=0.15 * (-1 if y > 0 else 1), width=3 + 3 * w)
            made.append((s, card, arrow))
        body = VGroup(target, *[VGroup(c, a) for _, c, a in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        entrance = K.stagger([self._title_in(top), K.enter(target, "pop")], lag=0.5)
        self._part(tid, e.get("text"), target, point=lambda: K.pulse(target, 1.08))
        last = len(made) - 1
        for k, (s, card, arrow) in enumerate(made):
            self._part(tid, s.get("text"), card, point=lambda m=card: K.pulse(m, 1.06))

            def land(heard, card=card, arrow=arrow, final=(k == last)):
                steps = [K.enter(card, "slide", side="left", run=K.t("base")), K.draw(arrow, run=K.t("base"))]
                if final:
                    steps.append(K.pulse(target, 1.1))
                return K.chain(steps)
            self._moment(_said(s.get("on"), s.get("text")), land)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [VGroup(c, a) for _, c, a in made])
        return anim

    # ---------------------------------------------------------------- portrait_card -----------------------------
    def m_portrait_card(self, name: str, dates: str | None = None, role: str | None = None, file: str | None = None,
                        facts=None, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A person as a trading card turned in: their picture, a name banner, dates and role; each of up to three
        `facts` ({text, on}) dealt onto the card beside it as it is said."""
        P = pl.P
        tid = id or self._next_id("portrait_card")
        cw, ch = 3.9, 5.2
        face = K.card(cw, ch, fill=K.col("card"))
        frame = RoundedRectangle(width=cw - 0.4, height=ch - 0.4, corner_radius=0.06, stroke_color=K.col("accent"),
                                 stroke_width=3, fill_opacity=0).move_to(face.face)
        pic = self._pic(file, ch * 0.5, cw - 0.7)
        if pic is None:
            disc = Circle(radius=1.0, stroke_width=0, fill_color=K.col("second"), fill_opacity=0.5)
            initials = K.head("".join(w[0] for w in str(name).split()[:2]).upper(), 48, _ink(K.col("second")))
            pic = VGroup(disc, initials.move_to(disc))
        pic.move_to(face.face.get_top() + DOWN * (pic.height / 2 + 0.45))
        banner_words = fit(K.head(str(name), 28, _ink(K.col("accent"))), cw - 0.6)
        banner = VGroup(Rectangle(width=cw - 0.3, height=banner_words.height + 0.3, stroke_width=0,
                                  fill_color=K.col("accent"), fill_opacity=1), banner_words)
        banner[1].move_to(banner[0])
        banner.next_to(pic, DOWN, buff=0.2)
        lines = VGroup(*[fit(K.body(str(t), 20, K.col("card_ink"), 26), cw - 0.6) for t in (dates, role) if t])
        if len(lines):
            lines.arrange(DOWN, buff=0.08).next_to(banner, DOWN, buff=0.18)
        card = Group(face, frame, pic, banner, lines)
        fact_specs = [_spec(f, "text") for f in (facts or [])][:3]
        chips = []
        for k, f in enumerate(fact_specs):
            words = fit(K.body(str(f.get("text", "")), 22, K.col("card_ink"), 24), 4.6)
            plate = K.card(words.width + 0.5, words.height + 0.4)
            words.move_to(plate.face)
            chip = K.group_of(plate, words)
            chips.append((f, chip))
        if chips:
            column = Group(*[c for _, c in chips]).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
            column.next_to(card, RIGHT, buff=0.7)
            body = Group(card, column)
        else:
            body = card
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        card_in = K.enter(card, None, run=K.t("base")) if K.forced() else \
            K.timed(FadeIn(card, scale=0.7, shift=UP * 0.4, rate_func=ease_out_back), K.t("base"), "pop")
        entrance = K.stagger([self._title_in(top), card_in], lag=0.5)
        self._part(tid, name, card, point=lambda: K.pulse(card, 1.04))
        for f, chip in chips:
            self._part(tid, f.get("text"), chip, point=lambda m=chip: K.pulse(m, 1.06))
            self._moment(_said(f.get("on"), f.get("text")), lambda heard, m=chip: K.enter(m, "slide", side="right"))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [c for _, c in chips])
        return anim

    # ---------------------------------------------------------------- source_vs_reality -------------------------
    def m_source_vs_reality(self, source, reality, verdict: str | None = None, title: str | None = None,
                            kicker: str | None = None, id: str | None = None):
        """A source's claim (`source`: {text, by?}) as a quoted page on the left; what historians now hold
        (`reality`: {text, on}) slides in on the right on its words; `verdict` ("Disputed", "Exaggerated") is
        stamped across the source."""
        P = pl.P
        tid = id or self._next_id("source_vs_reality")
        src, real = _spec(source, "text"), _spec(reality, "text")
        cw = 5.4
        q = fit(pl.T(pl.wrap("“" + str(src.get("text", "")) + "”", 30), 26, K.col("card_ink"), font=_serif()), cw - 0.7)
        by = fit(K.kicker("— " + str(src.get("by", "the source")), 16, K.col("card_ink")), cw - 0.7)
        kick_l = K.kicker("THE SOURCE SAYS", 16, P.MUTED)
        lstack = VGroup(kick_l, q, by).arrange(DOWN, buff=0.25, aligned_edge=LEFT)
        # Room at the foot of the page for the verdict: stamped over the claim, it hid the words it judged.
        room = 1.0 if verdict else 0.0
        lface = K.card(cw, lstack.height + 0.9 + room)
        lstack.move_to(lface.face).shift(UP * room / 2)
        left = K.group_of(lface, lstack)
        tone = K.col("good")
        r_words = fit(K.body(pl.wrap(str(real.get("text", "")), 32), 26, P.CREAM, 32), cw - 0.6)
        kick_r = K.kicker("WHAT WE NOW KNOW", 16, tone)
        rstack = VGroup(kick_r, r_words).arrange(DOWN, buff=0.25, aligned_edge=LEFT)
        bar = Rectangle(width=0.12, height=rstack.height + 0.3, stroke_width=0, fill_color=tone, fill_opacity=1)
        right = VGroup(bar, rstack).arrange(RIGHT, buff=0.3, aligned_edge=UP)
        pair = Group(left, right).arrange(RIGHT, buff=0.9)
        stamp = None
        if verdict:
            stamp = K.stamp(str(verdict), K.col("stamp"), angle=-8, size=40)
            fit(stamp, min(cw * 0.62, 3.6))
            stamp.move_to(lface.face.get_bottom() + UP * room * 0.55 + RIGHT * cw * 0.12)
            pair.add(stamp)
        whole, top = self._titled(pair, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.enter(left, "rise")], lag=0.5)
        self._part(tid, "source", left, point=lambda: K.pulse(left, 1.04))
        self._part(tid, real.get("text"), right, point=lambda: K.pulse(right, 1.04))

        def reveal(heard):
            steps = [K.together([K.fade_to(q, 0.6, run=K.t("fast")),
                                 K.timed(FadeIn(right, shift=LEFT * 0.8, rate_func=ease_out_expo), K.t("base"), "swish")])]
            if stamp is not None:
                steps.append(K.slam(stamp))
            return K.chain(steps)
        self._moment(_said(real.get("on"), real.get("text")), reveal)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [right] + ([stamp] if stamp is not None else []))
        if stamp is not None:
            stamp.set_z_index(Z_TEMPLATE + 4)
        return anim

    # ---------------------------------------------------------------- population_pyramid ------------------------
    def m_population_pyramid(self, groups, left_label: str = "Men", right_label: str = "Women", unit: str = "",
                             title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Age groups ({label, left, right}, the oldest first) as bars both ways from a middle spine, the left in the
        accent and the right in the second colour, growing out row by row from the youngest up."""
        P = pl.P
        tid = id or self._next_id("population_pyramid")
        specs = [g for g in (groups or []) if isinstance(g, dict)][:10]
        if len(specs) < 2:
            return None
        most = max([_num(g.get("left"), 0) or 0 for g in specs] + [_num(g.get("right"), 0) or 0 for g in specs]) or 1
        half, rh = 4.2, min(0.5, 4.6 / len(specs))
        rows = []
        for k, g in enumerate(specs):
            y = -k * (rh + 0.06)
            lw = max(0.05, half * (_num(g.get("left"), 0) or 0) / most)
            rw = max(0.05, half * (_num(g.get("right"), 0) or 0) / most)
            lb = Rectangle(width=lw, height=rh, stroke_width=0, fill_color=K.col("accent"), fill_opacity=0.95)
            lb.move_to([-0.55, y, 0], aligned_edge=RIGHT)
            rb = Rectangle(width=rw, height=rh, stroke_width=0, fill_color=K.col("second"), fill_opacity=0.95)
            rb.move_to([0.55, y, 0], aligned_edge=LEFT)
            lab = fit(K.kicker(str(g.get("label", "")), 15, P.CREAM), 1.0).move_to([0, y, 0])
            rows.append((g, lb, rb, lab))
        heads = VGroup(fit(K.head(str(left_label), 26, K.col("accent")), 3.0).move_to([-2.6, rh + 0.4, 0]),
                       fit(K.head(str(right_label), 26, K.col("second")), 3.0).move_to([2.6, rh + 0.4, 0]))
        body = VGroup(heads, *[VGroup(lb, rb, lab) for _, lb, rb, lab in rows])
        if unit:
            body.add(fit(K.kicker(str(unit), 15, P.MUTED), 4).next_to(body, DOWN, buff=0.25))
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        grows = [K.together([K.grow_from(lb, RIGHT, run=K.t("base")), K.grow_from(rb, LEFT, run=K.t("base")),
                             K.enter(lab, "fade", run=K.t("fast"))]) for _, lb, rb, lab in rows[::-1]]
        entrance = K.stagger([self._title_in(top), K.enter(heads, "rise"), K.stagger(grows, lag=0.25)], lag=0.4)
        for g, lb, rb, lab in rows:
            self._part(tid, g.get("label"), VGroup(lb, rb), point=lambda a=lb, b=rb: K.together([K.pulse(a, 1.08),
                                                                                                    K.pulse(b, 1.08)]))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- migration_flow ----------------------------
    def m_migration_flow(self, regions, flows, unit: str = "", title: str | None = None, kicker: str | None = None,
                         id: str | None = None):
        """Regions ({name, on?}) as discs round the stage; each flow ({from, to, value, label?, on}) drawn as an arc
        from one to the other as wide as the number who moved, its figure on it, as it is said."""
        P = pl.P
        tid = id or self._next_id("migration_flow")
        names = [_spec(r, "name") for r in (regions or [])][:6]
        if len(names) < 2:
            return None
        n = len(names)
        tones = self._tones(n)
        r = 2.4
        discs = {}
        made = []
        for k, (rg, tone) in enumerate(zip(names, tones)):
            a = math.pi / 2 - 2 * math.pi * k / n if n > 2 else (math.pi if k == 0 else 0)
            c = np.array([r * 1.45 * math.cos(a), r * math.sin(a), 0])
            words = fit(K.head(str(rg.get("name", "")), 24, _ink(tone)), 2.0)
            disc = Circle(radius=max(0.75, words.width / 2 + 0.25), stroke_width=0, fill_color=tone,
                          fill_opacity=1).move_to(c)
            node = VGroup(disc, words.move_to(c))
            discs[str(rg.get("name", "")).lower()] = node
            made.append((rg, node))
        fl = [f for f in (flows or []) if isinstance(f, dict)][:8]
        most = max([_num(f.get("value"), 1) or 1 for f in fl] + [1])
        arcs = []
        for f in fl:
            a, b = discs.get(str(f.get("from", "")).lower()), discs.get(str(f.get("to", "")).lower())
            if a is None or b is None or a is b:
                continue
            d = b.get_center() - a.get_center()
            u = d / (np.linalg.norm(d) or 1)
            s0 = a.get_center() + u * a[0].width / 2
            s1 = b.get_center() - u * (b[0].width / 2 + 0.08)
            width = 4 + 18 * (_num(f.get("value"), 1) or 1) / most
            arc = ArcBetweenPoints(s0, s1, angle=-0.5, stroke_color=K.col("stamp"), stroke_width=width)
            arc.set_stroke(opacity=0.85)
            tip = Triangle(fill_color=K.col("stamp"), fill_opacity=1, stroke_width=0).scale(0.12 + width * 0.006)
            dv = arc.point_from_proportion(1.0) - arc.point_from_proportion(0.95)
            tip.rotate(math.atan2(dv[1], dv[0]) - math.pi / 2).move_to(s1)
            text = f.get("label") or (f"{f.get('value')}{unit}" if f.get("value") not in (None, "") else "")
            tag = None
            if text:
                tag = K.chip(str(text), K.col("card"), K.col("card_ink"), 16)
                fit(tag, 2.4)
                tag.move_to(arc.point_from_proportion(0.5))
            arcs.append((f, VGroup(arc, tip, *([tag] if tag else []))))
        body = VGroup(*[m for _, m in made], *[m for _, m in arcs])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.stagger([K.enter(m, "pop", run=K.t("fast")) for _, m in made],
                                                             lag=0.2)], lag=0.4)
        for rg, m in made:
            self._part(tid, rg.get("name"), m, point=lambda m=m: K.pulse(m, 1.1))
        for f, m in arcs:
            self._part(tid, f.get("label") or f.get("to"), m, point=lambda m=m: K.pulse(m, 1.05))
            self._moment(_said(f.get("on"), f.get("to")),
                         lambda heard, m=m: K.chain([K.draw(m[0], run=K.t("slow")),
                                                     K.together([K.enter(x, "pop", run=K.t("fast")) for x in m[1:]])]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m in arcs])
        return anim

    # ---------------------------------------------------------------- quote_reveal ------------------------------
    def m_quote_reveal(self, text: str, who: str | None = None, file: str | None = None, highlight=None,
                       title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A famous line set large in a serif, its words coming on one by one across the line as it is spoken, the
        `highlight` words in the accent; the speaker's portrait (`file`) and name (`who`) fading in beside it."""
        P = pl.P
        tid = id or self._next_id("quote_reveal")
        words = str(text).split()
        hot = {w.lower().strip(".,;:!?\"'") for w in (highlight if isinstance(highlight, list) else
                                                      str(highlight or "").split())}
        # As many lines as 26 letters a line needs, and the words shared evenly among them (no word left alone).
        n_lines = max(1, math.ceil(len(" ".join(words)) / 26))
        width = len(" ".join(words)) / n_lines
        lines, line = [], []
        for w in words:
            if line and sum(len(x) + 1 for x in line) + len(w) > width + 4 and len(lines) < n_lines - 1:
                lines.append(line)
                line = []
            line.append(w)
        if line:
            lines.append(line)
        rows = VGroup()
        glyph_words = []
        for ln in lines:
            # The row set as one line (one baseline) and cut into its words: words set one by one and lined up by
            # their feet stood higher where a word hangs below the line (a "y", a "g").
            whole_row = pl.T(" ".join(ln), 44, P.TITLE, font=_serif(), disable_ligatures=True)  # a glyph a letter
            glyphs = list(whole_row.submobjects)
            spaced = len(glyphs) == len(" ".join(ln))      # a glyph for each space too, or for letters only
            if spaced or len(glyphs) == sum(len(w) for w in ln):
                row, k = VGroup(), 0
                for w in ln:
                    row.add(VGroup(*glyphs[k:k + len(w)]))
                    k += len(w) + (1 if spaced else 0)
            else:
                row = VGroup(*[pl.T(w, 44, P.TITLE, font=_serif()) for w in ln]).arrange(RIGHT, buff=0.2,
                                                                                       aligned_edge=DOWN)
            for w, m in zip(ln, row):
                if w.lower().strip(".,;:!?\"'") in hot:
                    m.set_color(K.col("accent"))
            rows.add(row)
            glyph_words += list(row)
        rows.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        mark = pl.T("“", 150, K.col("accent"), font=_serif()).next_to(rows, LEFT, buff=0.2).align_to(rows, UP)
        quote = VGroup(mark, rows)
        side = []
        pic = self._pic(file, 3.4, 3.0)
        name = fit(K.kicker("— " + str(who), 20, P.CREAM), 4.5) if who else None
        if pic is not None:
            col = Group(pic, *([name] if name is not None else [])).arrange(DOWN, buff=0.25)
            body = Group(quote, col).arrange(RIGHT, buff=0.8)
            side = [col]
        else:
            body = VGroup(quote, *([name] if name is not None else []))
            if name is not None:
                name.next_to(rows, DOWN, buff=0.4).align_to(rows, LEFT)
                side = [name]
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        # Spoken word by word: the whole line's run, each word a short fade-up in turn.
        run = min(4.5, 0.18 * len(glyph_words) + 0.5)
        typed = K.timed(K.stagger([K.timed(FadeIn(w, shift=UP * 0.15, rate_func=ease_out_cubic), 0.25)
                                   for w in glyph_words], lag=0.75), run, "type")
        entrance = K.stagger([self._title_in(top), K.enter(mark, "pop", run=K.t("fast")), typed,
                              *[K.enter(m, "fade", run=K.t("slow")) for m in side]], lag=0.35)
        self._part(tid, who or text, quote, point=lambda: K.pulse(quote, 1.03))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- newspaper ---------------------------------
    def m_newspaper(self, headline: str, paper: str = "The Daily Courier", date: str | None = None,
                    sub: str | None = None, file: str | None = None, title: str | None = None,
                    kicker: str | None = None, id: str | None = None):
        """A front page spun onto the board (as old films show news breaking): the masthead, the date line, the
        headline slammed on in heavy capitals, a sub-headline, columns of print and a picture."""
        tid = id or self._next_id("newspaper")
        ink, sheet = "#1A1A1A", "#F3EEDF"
        pw, ph = 7.6, 9.2
        page = Rectangle(width=pw, height=ph, stroke_width=0, fill_color=sheet, fill_opacity=1)
        shade = K.shadow_of(page)
        mast = fit(pl.T(str(paper), 50, ink, font="Cinzel"), pw - 0.6).move_to(page.get_top() + DOWN * 0.7)
        rule1 = Line(page.get_left() + RIGHT * 0.3, page.get_right() + LEFT * 0.3, stroke_color=ink,
                     stroke_width=3).next_to(mast, DOWN, buff=0.15)
        dl = fit(K.kicker(str(date or ""), 14, ink), pw - 0.8).next_to(rule1, DOWN, buff=0.1)
        rule2 = rule1.copy().next_to(dl, DOWN, buff=0.1)
        head = fit(pl.T(pl.wrap(str(headline).upper(), 18), 60, ink, font="Oswald", weight=BOLD), pw - 0.6)
        head.next_to(rule2, DOWN, buff=0.25)
        parts = [shade, page, mast, rule1, dl, rule2, head]
        subm = None
        if sub:
            subm = fit(pl.T(pl.wrap(str(sub), 46), 22, ink, font=_serif()), pw - 0.8).next_to(head, DOWN, buff=0.2)
            parts.append(subm)
        low = (subm or head).get_bottom()[1] - 0.3
        pic = self._pic(file, 3.0, pw * 0.5)
        cols = VGroup()
        col_w = (pw - 0.9) / (2 if pic is not None else 3)
        start_x = page.get_left()[0] + 0.3
        for c in range(2 if pic is not None else 3):
            for k in range(14):
                y = low - k * 0.24
                if y < page.get_bottom()[1] + 0.3:
                    break
                w = col_w * (0.6 if k % 5 == 4 else 0.95)
                cols.add(Line([start_x + c * (col_w + 0.15), y, 0], [start_x + c * (col_w + 0.15) + w, y, 0],
                              stroke_color="#8C877A", stroke_width=3))
        parts.append(cols)
        if pic is not None:
            pic.move_to([page.get_right()[0] - pw * 0.27, low - pic.height / 2, 0])
            parts.append(pic)
        front = Group(*parts)
        front.rotate(-2.5 * math.pi / 180)
        whole, top = self._titled(front, title, kicker)
        self._fit(whole, self._box(), grow=1.1, margin=0.3)
        rest = Group(*[m for m in parts if m is not head])
        spin = K.enter(rest, None) if K.forced() else \
            K.timed(K.baked(K.SpinIn(rest, turns=2.0, rate_func=ease_out_cubic)), K.t("slow") * 1.4, "whoosh")
        entrance = K.stagger([self._title_in(top), spin, K.slam(head)], lag=0.9)
        self._part(tid, headline, head, point=lambda: K.pulse(head, 1.05))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- letter ------------------------------------
    def m_letter(self, text: str, to: str | None = None, sign: str | None = None, date: str | None = None,
                 title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A letter on a sheet laid on the board: the date and greeting, its words written on in a hand as the line
        reads them, signed at the end."""
        tid = id or self._next_id("letter")
        ink, sheet = "#23324A", "#FBF6E9"
        body_text = fit(pl.T(pl.wrap(str(text), 40), 34, ink, font=_hand()), 7.6)
        head = []
        if date:
            head.append(fit(pl.T(str(date), 28, ink, font=_hand()), 4))
        if to:
            head.append(fit(pl.T(f"Dear {to},", 34, ink, font=_hand()), 7))
        hd = VGroup(*head).arrange(DOWN, buff=0.2, aligned_edge=LEFT) if head else None
        sig = fit(pl.T(str(sign), 40, ink, font=_hand()), 4) if sign else None
        stack = VGroup(*[m for m in (hd, body_text, sig) if m is not None]).arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        if sig is not None:
            sig.align_to(body_text, RIGHT)
        page = Rectangle(width=stack.width + 1.4, height=stack.height + 1.2, stroke_width=0, fill_color=sheet,
                         fill_opacity=1)
        rules = VGroup(*[Line(page.get_left() + RIGHT * 0.4 + DOWN * (k * 0.55), page.get_right() + LEFT * 0.4 +
                              DOWN * (k * 0.55), stroke_color="#C9D6E8", stroke_width=1.5)
                         for k in range(int(page.height / 0.55))]).move_to(page)
        stack.move_to(page)
        letter = Group(K.shadow_of(page), page, rules, stack).rotate(1.5 * math.pi / 180)
        whole, top = self._titled(letter, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        sheet_in = K.timed(FadeIn(Group(letter[0], page, rules), shift=UP * 0.5, rate_func=ease_out_cubic),
                           K.t("base"), "swish")
        writes = [K.write(m, run=K.t("base")) for m in (hd,) if m is not None]
        writes.append(K.timed(K.write(body_text, run=min(5.0, 0.04 * len(str(text)) + 0.8)),
                              min(5.0, 0.04 * len(str(text)) + 0.8), "draw"))
        if sig is not None:
            writes.append(K.write(sig, run=K.t("slow")))
        entrance = K.stagger([self._title_in(top), sheet_in, K.chain(writes)], lag=0.5)
        self._part(tid, to or "letter", letter, point=lambda: K.pulse(page, 1.03))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- countdown ---------------------------------
    def m_countdown(self, steps, event, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A big flip display: each of `steps` (years or counts, {text, note?, on}) flips in over the last as it is
        said, its note under it; then the `event` ({text, on}) lands with a thud."""
        P = pl.P
        tid = id or self._next_id("countdown")
        specs = [_spec(s, "text") for s in (steps or [])][:6]
        if not specs:
            return None
        ev = _spec(event, "text")
        tile = RoundedRectangle(width=5.4, height=2.6, corner_radius=0.18, stroke_width=0, fill_color=K.col("card"),
                                fill_opacity=1)
        seam = Line(tile.get_left(), tile.get_right(), stroke_color=K.col("card_stroke"), stroke_width=3)
        board = VGroup(K.shadow_of(tile), tile, seam)
        faces = []
        for s in specs:
            num = fit(K.number(str(s.get("text", "")), 120, K.col("card_ink")), 4.8).move_to(tile)
            note = fit(K.body(str(s.get("note", "")), 24, P.CREAM, 40), 7.0).next_to(tile, DOWN, buff=0.35) \
                if s.get("note") else None
            faces.append((s, VGroup(num, *([note] if note is not None else []))))
        ev_words = fit(K.head(str(ev.get("text", "")), 44, _ink(K.col("stamp"))), 8.0)
        ev_band = VGroup(Rectangle(width=ev_words.width + 0.9, height=ev_words.height + 0.5, stroke_width=0,
                                   fill_color=K.col("stamp"), fill_opacity=1), ev_words)
        ev_band[1].move_to(ev_band[0])
        ev_band.next_to(tile, DOWN, buff=1.1)
        body = VGroup(board, *[f for _, f in faces], ev_band)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        first = faces[0][1]
        entrance = K.stagger([self._title_in(top), K.enter(board, "pop"),
                              K.timed(FadeIn(first, shift=DOWN * 0.6, rate_func=ease_out_back), K.t("base"), "tick")],
                             lag=0.4)
        for k in range(1, len(faces)):
            s, face = faces[k]
            prev = faces[k - 1][1]
            self._moment(_said(s.get("on"), s.get("text")),
                         lambda heard, a=prev, b=face: K.together([
                             # Faded, not faded out: a part of a group that fades out comes back when the fade ends.
                             K.fade_to(a, 0.0, run=K.t("fast")),
                             K.timed(FadeIn(b, shift=DOWN * 0.6, rate_func=ease_out_back), K.t("base"), "tick")]))
        self._part(tid, ev.get("text"), ev_band, point=lambda: K.pulse(ev_band, 1.06))
        self._moment(_said(ev.get("on"), ev.get("text")), lambda heard: K.slam(ev_band))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [f for _, f in faces[1:]] + [ev_band])
        return anim
