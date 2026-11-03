"""The layout solver: the score's things built with their real sizes (after the assets step), and each one that
covers another while both are up, or hangs off its shot's screen, moved to the nearest free place on the screen (a
figure along the ground), made a little smaller only when nowhere is free. The new places are written back into the
score as `at X,Y` (and `shrink K`), so the score stays the one truth the timeline, the player and the render read.
No model is asked: this is what the layout step does in place of a rewrite of each shot.

    python arrange.py video.score run_dir            -> rewrites video.score; prints `arrange: {...}`

What is meant to be on another is left alone (as layout.py judges it): a label on its card, a pin on its map, a thing
put `at` another or beside it, one given another `layer`, two things an action brings together (a rider and a horse).
What is set on a thing that moves (a badge on its card) moves with it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from manim import tempconfig

import layout as LY
import look
import render as R
import score as S

# Kinds the solver never moves: what fills the shot, what joins things, what is drawn where it is on purpose.
FIXED = LY.FREE | {"map", "backdrop", "land", "waves", "islands", "weather", "globe"}
SHRINKS = (0.88, 0.76, 0.64)


class ArrangeScene(R.ScoreScene):
    """The renderer's scene, built and laid out as the score says (no mend of its own), never played."""

    def construct(self):
        sc = self.SCORE
        look.use(sc.look)
        self.E, self.alpha, self.marks, self.fills, self.follows = {}, {}, {}, {}, []
        self.up, self.tweens, self.clock = set(), [], 0.0
        self.texture = self.motion = self.parallax = False
        self.hud, self.hud_hooks, self.boiled, self.boil_ids = [], [], [], {}
        self._build()


def _overlap(a, b) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 0 and min(a[3], b[3]) - max(a[1], b[1]) > 0


def _shifted(b, d):
    return (b[0] + d[0], b[1] + d[1], b[2] + d[0], b[3] + d[1])


def solve(score_text: str, words_json: dict) -> tuple[str, dict]:
    sc = S.parse(score_text, words_json["words"], float(words_json["seconds"]))
    ArrangeScene.SCORE, ArrangeScene.WORDS, ArrangeScene.WAV = sc, words_json, None
    with tempconfig({"disable_caching": True, "verbosity": "ERROR", "progress_bar": "none",
                     "media_dir": str(Path("/tmp") / "v3-arrange-media")}):
        scene = ArrangeScene()
        scene.setup()
        scene.construct()
    E = scene.E
    times = scene._up_times()
    # A thing's box and the boxes of its words, measured once for each place it stands (asked for over and over
    # below): what the solver moves it marks as moved.
    ver: dict[int, int] = {}
    found: dict = {}
    words_of, box_of = scene.words_of, LY._box

    def cached(fn):
        def get(m):
            k = (fn.__name__, id(m), ver.get(id(m), 0))
            if k not in found:
                found[k] = fn(m)
            return found[k]
        return get
    scene.words_of = cached(words_of)
    LY._box = cached(box_of)

    def shift(m, d):
        m.shift([d[0], d[1], 0])
        ver[id(m)] = ver.get(id(m), 0) + 1
    together = set()
    for act in sc.acts:
        for x in act.args:
            if x in sc.ents and x != act.target:
                together.add(frozenset((act.target, x)))
    moves: dict[str, list] = {}         # name -> [dx, dy, shrink, how]   (how: "at" or "nudge")
    acts: dict[int, tuple] = {}         # an action's line -> (the action, dx, dy) or (the action, k) for a scale
    notes: list[str] = []
    outs: list[tuple[int, str]] = []    # (the line after which, an `out` action) for things that give way

    def how(e) -> str | None:
        """How a thing may be moved: by its own place (`at`), by a small nudge from the place it is put at (a place
        on a map, beside another), or not at all."""
        if (e.kind not in scene.SPREAD and e.kind != "phrase") or e.kind in FIXED or e.mods.get("on"):
            return None
        if e.kind == "prop" and scene._flat(e.name):
            return None
        if isinstance(e.mods.get("at"), str) or any(isinstance(e.mods.get(k), str) for k in R.REL):
            return "nudge"
        return "at"

    def clash(e, b, o, ob) -> bool:
        """Whether e (with box b) and o (with box ob) cover each other as the layout check would say."""
        if frozenset((e.name, o.name)) in together or not LY._judged(scene, sc, e, o):
            return False
        k = LY._cover(b, ob)
        if k <= 0.02:
            return False
        hid = LY._on_words(scene, E[e.name], b, ob) or LY._on_words(scene, E[o.name], ob, b)
        solid = e.kind in LY.SOLID and o.kind in LY.SOLID and k > 0.05
        if not (k >= 0.2 or hid or solid):
            return False
        return not LY._held(scene, e, o, b, ob)

    def room(e, bx, others, o, hw, hh, figure, reach=None):
        """The nearest shift that puts box bx clear of every other (box) on the shot's screen, or None."""
        xs = np.arange(o[0] - hw - bx[0], o[0] + hw - bx[2] + 1e-6, 0.2)
        ys = np.arange(o[1] - hh - bx[1], o[1] + hh - bx[3] + 1e-6, 0.2)
        if figure and o[1] - hh - 0.3 <= bx[1] and bx[3] <= o[1] + hh + 0.3:
            ys = np.array([0.0])                # a figure keeps its ground
        if len(xs) == 0 or len(ys) == 0:
            return None
        cands = sorted(((dx, dy) for dx in xs for dy in ys), key=lambda d: d[0] ** 2 + d[1] ** 2)
        for dx, dy in cands:
            if reach is not None and dx * dx + dy * dy > reach * reach:
                return None
            c = _shifted(bx, (dx, dy))
            if not any(_overlap(c, ob) and clash(e, c, x, ob) for x, ob in others):
                return dx, dy
        return None

    # -- where each thing first stands -------------------------------------------------------------------------------
    for shot in sc.shots.values():
        mine = [e for e in sc.ents.values() if e.shot == shot.name and e.name in E]
        if not mine:
            continue
        o = scene._origin(shot.name)
        hw, hh = S.SCREEN_W / shot.zoom / 2 - 0.55, S.SCREEN_H / shot.zoom / 2 - 0.45
        box = {e.name: LY._box(E[e.name]) for e in mine}
        up = {e.name: times.get(e.name, (0.0, 1e9)) for e in mine}
        riders = {e.name: [x for x in mine if x is not e and how(x) and scene.nested(e, x)] for e in mine}
        ridden = {x.name for xs in riders.values() for x in xs}
        order = sorted(mine, key=lambda e: (how(e) is not None, how(e) == "at", up[e.name][0], -LY._area(box[e.name]), e.line))
        placed = []
        for e in order:
            b = box[e.name]
            live = [(p, box[p.name]) for p in placed
                    if min(up[p.name][1], up[e.name][1]) - max(up[p.name][0], up[e.name][0]) > 0.3]
            off = max(o[0] - hw - b[0], b[2] - (o[0] + hw), o[1] - hh - b[1], b[3] - (o[1] + hh))
            mode = how(e)
            if mode is None or e.name in ridden or (off <= 0.15 and not any(clash(e, b, p, pb) for p, pb in live)):
                placed.append(e)
                continue
            m = E[e.name]
            figure = scene._figure(e)
            anchor = m.feet() if figure else (m.get_bottom() if e.kind == "prop" else m.get_center())
            best = None
            for k in (1.0, *SHRINKS):
                w, h = (b[2] - b[0]) * k, (b[3] - b[1]) * k
                if w > 2 * hw or h > 2 * hh:
                    continue
                bx = (anchor[0] + (b[0] - anchor[0]) * k, anchor[1] + (b[1] - anchor[1]) * k,
                      anchor[0] + (b[2] - anchor[0]) * k, anchor[1] + (b[3] - anchor[1]) * k)
                d = room(e, bx, live, o, hw, hh, figure, 1.8 if mode == "nudge" else None)
                if d:
                    best = (d[0], d[1], k, _shifted(bx, d))
                    break
            if best is None:
                # No room anywhere: what is in its way (and came before it) goes as it comes in, so the shot moves
                # on instead of piling up.
                came = next((a for a in sc.acts if a.verb == "in" and e.name in a.target.split(",")), None)
                gone = [p for p, pb in live if clash(e, b, p, pb) and how(p) and up[p.name][0] < up[e.name][0]
                        and not any(e is x for x in riders[p.name])]
                tok = re.match(r"^(w\d+)", came.text.strip()) if came else None
                rest_clear = not any(clash(e, b, p, pb) for p, pb in live if p not in gone)
                if gone and tok and rest_clear:
                    for p in gone:
                        up[p.name] = (up[p.name][0], up[e.name][0])
                    outs.append((came.line, f"{tok.group(1)} out {','.join(p.name for p in gone)}"))
                    notes.append(f"{shot.name}: {', '.join(p.name for p in gone)} goes as {e.name} comes in (no room for both)")
                else:
                    notes.append(f"{shot.name}: no free room for {e.name}: left where it is")
                placed.append(e)
                continue
            dx, dy, k, c = best
            if k != 1.0:
                m.scale(k, about_point=anchor)
            shift(m, (dx, dy))
            box[e.name] = c
            moves[e.name] = [dx, dy, k, mode]
            for x in riders[e.name]:
                shift(E[x.name], (dx, dy))
                box[x.name] = _shifted(box[x.name], (dx, dy))
                moves[x.name] = [dx, dy, 1.0, how(x)]
            placed.append(e)
            notes.append(f"{shot.name}: {e.name} moved {dx:+.1f},{dy:+.1f}" + (f", made {k:g} as big" if k != 1.0 else ""))

    # -- where moves and growths take things -------------------------------------------------------------------------
    def spans_of(name):
        b = LY._box(E[name])
        t0, t1 = times.get(name, (0.0, 1e9))
        out, cur, start = [], b, t0
        for a in sorted((a for a in sc.acts if a.verb in ("move", "walk", "scale") and name in a.target.split(",")),
                        key=lambda a: a.t0):
            dest = LY._moved(scene, sc, name, a, cur)
            if dest is None:
                continue
            end = a.t1 if a.t1 is not None else a.t0 + 0.9
            out.append((start, end, cur, None))
            cur, start = dest, end
            out.append((start, t1, cur, a))
        return out or [(t0, t1, b, None)]
    spans = {n: spans_of(n) for n in E if n in sc.ents}
    for a in sorted((a for a in sc.acts if a.verb in ("move", "walk", "scale")), key=lambda a: a.t0):
        name = a.target
        if name not in spans or "," in name or name not in sc.ents:
            continue
        e = sc.ents[name]
        shot = sc.shots.get(e.shot)
        if shot is None or how(e) is None:
            continue
        mine = [x for x in spans[name] if x[3] is a]
        if not mine:
            continue
        s0, s1, bx, _ = mine[0]
        others = [(sc.ents[n], ob) for n, sp in spans.items() if n != name and sc.ents[n].shot == e.shot
                  for (t0, t1, ob, _) in sp if min(t1, s1) - max(t0, s0) > 0.3]
        if not any(clash(e, bx, x, ob) for x, ob in others):
            continue
        o = scene._origin(e.shot)
        hw, hh = S.SCREEN_W / shot.zoom / 2 - 0.55, S.SCREEN_H / shot.zoom / 2 - 0.45
        if a.verb == "scale":
            try:
                k0 = float(a.args[0]) if a.args else 1.2
            except ValueError:
                continue
            prev = [x for x in spans[name] if x[1] <= s0 + 1e-6]
            base = prev[-1][2] if prev else bx
            c = ((base[0] + base[2]) / 2, (base[1] + base[3]) / 2)
            fixed = None
            for k in np.linspace(k0, 1.0, 6)[1:]:
                kb = (c[0] - (base[2] - base[0]) * k / 2, c[1] - (base[3] - base[1]) * k / 2,
                      c[0] + (base[2] - base[0]) * k / 2, c[1] + (base[3] - base[1]) * k / 2)
                if not any(clash(e, kb, x, ob) for x, ob in others):
                    fixed = float(k)
                    break
            if fixed is None or abs(fixed - 1.0) < 1e-3:
                continue
            acts[a.line] = (a, fixed)
            a.args[0] = f"{fixed:.2f}"
            notes.append(f"{e.shot}: {name} grows {fixed:.2f} (not {k0:g}): room for it")
        else:
            key = "to" if "to" in a.args else ("by" if "by" in a.args else None)
            if key is None or a.args.index(key) + 1 >= len(a.args) or \
                    not re.match(r"^-?[\d.]+,-?[\d.]+$", a.args[a.args.index(key) + 1]):
                continue
            d = room(e, bx, others, o, hw, hh, scene._figure(e))
            if not d:
                continue
            i = a.args.index(key) + 1
            x, y = (float(v) for v in a.args[i].split(","))
            a.args[i] = f"{x + d[0]:.1f},{y + d[1]:.1f}"
            acts[a.line] = (a, key, a.args[i])
            notes.append(f"{e.shot}: {name}'s move lands {d[0]:+.1f},{d[1]:+.1f} further: room for it")
        spans[name] = spans_of(name)
    LY._box = box_of
    return _write(score_text, sc, moves, acts, outs), {"moved": len(moves), "actions": len(acts), "notes": notes}


def _write(text: str, sc: S.Score, moves: dict, acts: dict, outs: list) -> str:
    """The score with each moved thing's place said anew on its own `ent` line (`at X,Y`, or a `nudge` from the
    place it is put at, and `shrink K`), and each re-aimed move or growth on its own action line."""
    lines = text.splitlines()
    for name, (dx, dy, k, mode) in moves.items():
        e = sc.ents[name]
        i = e.line - 1
        if not (0 <= i < len(lines)) or not re.match(rf"^\s*ent\s+{re.escape(name)}\b", lines[i]):
            continue
        ln = lines[i]
        if mode == "nudge":
            nd = e.mods.get("nudge") if isinstance(e.mods.get("nudge"), tuple) else (0.0, 0.0)
            new = f"nudge {nd[0] + dx:.1f},{nd[1] + dy:.1f}"
            ln, n = re.subn(r"\bnudge\s+-?[\d.]+\s*,\s*-?[\d.]+", new, ln, count=1)
        else:
            at = e.mods.get("at") if isinstance(e.mods.get("at"), tuple) else (0.0, 0.0)
            new = f"at {at[0] + dx:.1f},{at[1] + dy:.1f}"
            ln, n = re.subn(r"\bat\s+-?[\d.]+\s*,\s*-?[\d.]+", new, ln, count=1)
        if not n:
            ln = ln.rstrip() + " " + new
        if k != 1.0:
            old = e.mods.get("shrink")
            kk = k * (float(old) if old else 1.0)
            ln, n = re.subn(r"\bshrink\s+[\d.]+", f"shrink {kk:.2f}", ln, count=1)
            if not n:
                ln = ln.rstrip() + f" shrink {kk:.2f}"
        lines[i] = ln
    for line, fix in acts.items():
        i = line - 1
        if not (0 <= i < len(lines)):
            continue
        a = fix[0]
        if len(fix) == 2:                       # a growth made smaller
            lines[i] = re.sub(rf"(\bscale\s+{re.escape(a.target)}\s+)[\d.]+", rf"\g<1>{fix[1]:.2f}", lines[i], count=1)
        else:                                   # a move re-aimed
            lines[i] = re.sub(rf"(\b{fix[1]}\s+)-?[\d.]+\s*,\s*-?[\d.]+", rf"\g<1>{fix[2]}", lines[i], count=1)
    for line, act in sorted(outs, key=lambda x: -x[0]):
        lines.insert(line, act + "        # (no room for both: the layout solver)")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("run_dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    words = json.loads((Path(a.run_dir) / "words.json").read_text())
    text, rep = solve(Path(a.score).read_text(), words)
    Path(a.out or a.score).write_text(text)
    print("arrange: " + json.dumps(rep), flush=True)


if __name__ == "__main__":
    main()
