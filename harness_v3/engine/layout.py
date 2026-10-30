"""The layout check: the score's things built as the render builds them (with the real pictures, after the assets
step) and looked at before anything is played, so what the score model could not see is said in words it can act
on: things that cover each other without meaning to, things off their shot's screen or off the map they are put on,
pieces with nothing in them. Each problem names its shot and the word it starts at, with the real sizes.

    python layout.py video.score run_dir            -> prints `layout: {...}` (the problems by shot, and the sizes)

What is meant to be on another is left alone: a label on its card, an icon on its badge, a pin or region on its map,
an event on its timeline, labels on their picture, a thing put `at` another or against it (`below X`), a thing given
another `layer`, paths and arrows (they join things), a backdrop and the weather.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from manim import tempconfig

import look
import render as R
import score as S

# Kinds never said to cover another: what joins things, what lies behind or over a whole shot, what is drawn on a
# piece where it stands.
FREE = {"path", "arrow", "waves", "backdrop", "weather", "region", "river", "pin", "event", "span", "labels", "bubble",
        "march", "lens", "shade", "inset", "split"}
WORDS_KINDS = ("text", "tag", "label", "card", "title", "quote")
SOLID = {"card", "photo", "pic", "portrait", "doc", "quote", "clipping", "polaroids", "who", "flag", "stat"}


class CheckScene(R.ScoreScene):
    """The renderer's scene, built and laid out, never played."""

    def construct(self):
        sc = self.SCORE
        look.use(sc.look)
        self.E, self.alpha, self.marks, self.fills, self.follows = {}, {}, {}, {}, []
        self.up, self.tweens, self.clock = set(), [], 0.0
        self.texture = self.motion = self.parallax = False
        self.hud, self.hud_hooks, self.boiled, self.boil_ids = [], [], [], {}
        self._build()
        self._spread()


def _box(m) -> tuple[float, float, float, float]:
    """A thing's box on the screen; a cut-out picture's is what shows of it (not the clear margin round its shadow)."""
    lo, hi = m.get_corner(R.DOWN + R.LEFT), m.get_corner(R.UP + R.RIGHT)
    fx, fy = getattr(m, "shown", (1.0, 1.0))
    cx, cy, hw, hh = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (hi[0] - lo[0]) * fx / 2, (hi[1] - lo[1]) * fy / 2
    return float(cx - hw), float(cy - hh), float(cx + hw), float(cy + hh)


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _cover(a, b) -> float:
    """How much of the smaller of two boxes the other covers (0..1)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / max(1e-6, min(_area(a), _area(b)))


def _word_at(words: list[dict], t: float) -> str:
    if not words or t <= 0:
        return "the start"
    k = min(range(len(words)), key=lambda i: abs(float(words[i]["start"]) - t))
    return f"w{words[k]['i']}"


def check(score_text: str, words_json: dict) -> dict:
    sc = S.parse(score_text, words_json["words"], float(words_json["seconds"]))
    CheckScene.SCORE, CheckScene.WORDS, CheckScene.WAV = sc, words_json, None
    with tempconfig({"disable_caching": True, "verbosity": "ERROR", "progress_bar": "none",
                     "media_dir": str(Path("/tmp") / "v3-layout-media")}):
        scene = CheckScene()
        scene.setup()
        scene.construct()
    E = scene.E
    times = scene._up_times()
    words = words_json["words"]
    problems: dict[str, list[str]] = {}
    sizes: dict[str, list[str]] = {}

    def say(shot: str, text: str) -> None:
        problems.setdefault(shot, [])
        if text not in problems[shot]:
            problems[shot].append(text)

    def where(name: str, box) -> str:
        e = sc.ents[name]
        o = scene._origin(e.shot)
        return (f"{name} ({e.kind}, {box[2] - box[0]:.1f} wide x {box[3] - box[1]:.1f} tall, at "
                f"{(box[0] + box[2]) / 2 - o[0]:.1f},{(box[1] + box[3]) / 2 - o[1]:.1f})")

    # Where each thing is while it is up: as built, and after each move that takes all of it somewhere else.
    spans: dict[str, list[tuple[float, float, tuple]]] = {}
    for name, m in E.items():
        t0, t1 = times.get(name, (0.0, 1e9))
        b = _box(m)
        moves = sorted((a for a in sc.acts if a.verb in ("move", "walk", "scale") and name in a.target.split(",")),
                       key=lambda a: a.t0)
        cur, start = b, t0
        for a in moves:
            end = a.t1 if a.t1 is not None else a.t0 + 0.9
            dest = _moved(scene, sc, name, a, cur)
            if dest is None:
                continue
            spans.setdefault(name, []).append((start, end, cur))
            cur, start = dest, end
        spans.setdefault(name, []).append((start, t1, cur))

    for shot in sc.shots.values():
        mine = [e for e in sc.ents.values() if e.shot == shot.name and e.name in E]
        o = scene._origin(shot.name)
        hw, hh = S.SCREEN_W / shot.zoom / 2, S.SCREEN_H / shot.zoom / 2
        sizes[shot.name] = [where(e.name, _box(E[e.name])) for e in mine]
        for e in mine:
            b = _box(E[e.name])
            # empty pieces
            if e.kind in WORDS_KINDS and not (e.args and str(e.args[0]).strip()):
                say(shot.name, f"{e.name} ({e.kind}) has no words: give it words or leave it out")
            if e.kind == "timeline" and not any(x.mods.get("on") == e.name for x in sc.ents.values()):
                say(shot.name, f"{e.name} (timeline) has no event or span on it: add the dates the narration names "
                               "(event YEAR \"WORDS\" on " + e.name + ") or leave it out")
            # off the screen
            if e.kind not in ("backdrop", "weather") and not (e.kind == "map" and e.mods.get("full")):
                out = max(o[0] - hw - b[0], b[2] - (o[0] + hw), o[1] - hh - b[1], b[3] - (o[1] + hh))
                if out > 0.15:
                    say(shot.name, f"{where(e.name, b)} runs {out:.1f} off the screen (x from -{hw:.1f} to {hw:.1f}, "
                                   f"y from -{hh:.1f} to {hh:.1f})")
            if e.kind in ("tag", "title") and b[2] - b[0] > hw * 2 * 0.85:
                say(shot.name, f"{where(e.name, b)} is very wide: fewer words or a smaller size")
            # a place beyond its map (drawn at the map's edge)
            for a in [*e.args, str(e.mods.get("at") or "")]:
                base, _, place = str(a).partition(".")
                if place and base in E and sc.ents[base].kind == "map":
                    far = getattr(getattr(E[base], "places", None), "outside", {})
                    if place in far:
                        lon, lat = far[place]
                        say(shot.name, f"{e.name} uses {a}, which is beyond the map {base} (at {lon:.0f}E, {lat:.0f}N; "
                                       f"the map shows {', '.join(f'{v:.0f}' for v in E[base].bounds)}): it is drawn at "
                                       "the map's edge; widen the map (or name a region that holds it) or use a "
                                       "place on it")
            # put at a map's place outside the map
            at = e.mods.get("at")
            if isinstance(at, str) and "." in at:
                base = at.split(".", 1)[0]
                if base in E and sc.ents[base].kind == "map":
                    sea = _box(E[base][0])
                    c = E[e.name].get_center()
                    if not (sea[0] <= c[0] <= sea[2] and sea[1] <= c[1] <= sea[3]):
                        say(shot.name, f"{e.name} is put at {at}, which is outside the map {base}")
        # things covering each other while both are up
        for i, a in enumerate(mine):
            for b in mine[i + 1:]:
                if not _judged(scene, sc, a, b):
                    continue
                for (a0, a1, ab) in spans.get(a.name, []):
                    for (b0, b1, bb) in spans.get(b.name, []):
                        t0, t1 = max(a0, b0), min(a1, b1)
                        if t1 - t0 < 0.3:
                            continue
                        k = _cover(ab, bb)
                        # words hidden: said whatever the share (a corner of a card over another's title hides it)
                        hid = k > 0.02 and (_on_words(scene, E[a.name], ab, bb) or _on_words(scene, E[b.name], bb, ab))
                        # two opaque pieces (cards, prints, cut-outs) one partly over the other look broken at any share
                        solid = a.kind in SOLID and b.kind in SOLID and k > 0.05
                        if (k >= 0.2 or hid or solid) and not _held(scene, a, b, ab, bb):
                            say(shot.name, f"from {_word_at(words, t0)}: {where(a.name, ab)} and {where(b.name, bb)} "
                                           f"overlap ({k * 100:.0f}% of the smaller is covered"
                                           + (", over the words" if hid else "") + ")")
    # lines the engine could not read or play (each is left out of the video): said in the shot they are in
    for shot, text in _unplayable(scene, sc, score_text):
        say(shot, text)
    count = sum(len(v) for v in problems.values())
    return {"count": count, "problems": problems, "sizes": sizes, "notes": sc.notes}


VERBS = (set(R.DEFAULT_RUN) | set(R.MARKS) | set(R.PERSON_VERBS) |
         {"in", "out", "move", "along", "morph", "color", "dim", "lift", "scale", "spin", "pulse", "shake", "count",
          "grow", "cam", "flow", "float", "bracket", "spotlight", "chapter", "bring"})


def _unplayable(scene, sc, score_text: str) -> list[tuple[str, str]]:
    """(shot, problem) for each line left out: one the grammar cannot read, a thing that cannot be drawn, an action
    with no such verb or on no such thing."""
    starts = sorted((s.line, s.name) for s in sc.shots.values())

    def shot_at(line: int) -> str | None:
        here = [name for ln, name in starts if ln <= line]
        return here[-1] if here else (starts[0][1] if starts else None)
    lines = score_text.splitlines()
    out = []
    for n in sc.notes:
        m = re.match(r"^line (\d+): (.*)$", n)
        if not m or "was made again" in m.group(2):     # (a mend, not a loss)
            continue
        k = int(m.group(1))
        shot = shot_at(k)
        src = lines[k - 1].strip() if 0 < k <= len(lines) else ""
        if shot:
            out.append((shot, f"`{src[:90]}` is left out ({m.group(2)[:160]}): write it in the grammar or drop it"))
    for a in sc.acts:
        shot = shot_at(a.line)
        if not shot:
            continue
        if a.verb not in VERBS:
            out.append((shot, f"`{a.text[:90]}` is left out: there is no verb {a.verb!r} (TIME VERB TARGET; "
                              "e.g. `w12 in NAME pop`, `w14 out NAME`, `w16-w18 in PHRASE speak`)"))
            continue
        if a.verb in ("cam", "chapter"):
            continue
        for ref in a.target.split(","):
            base = re.sub(r"\[.*", "", ref.strip()).split(".", 1)[0]
            if base and base not in scene.E:
                out.append((shot, f"`{a.text[:90]}` is left out: there is no thing named {base!r} (make it with an "
                                  "`ent` line, or use a name that is made)"))
                break
    return out


def _moved(scene, sc, name, a, cur):
    """The box a `move` of the whole thing takes it to, or None (a move of its parts, or one not understood)."""
    args = a.args
    w, h = cur[2] - cur[0], cur[3] - cur[1]
    c = np.array([(cur[0] + cur[2]) / 2, (cur[1] + cur[3]) / 2])
    if a.verb == "scale":                       # grown (or shrunk) about its middle, as the score asks (the render
        try:                                    # holds a growth back from what is beside it: said here to fix)
            k = float(args[0]) if args else 1.2
        except ValueError:
            return None
        return (c[0] - w * k / 2, c[1] - h * k / 2, c[0] + w * k / 2, c[1] + h * k / 2)
    try:
        if "to" in args:
            ref = args[args.index("to") + 1]
            if re.match(r"^-?[\d.]+,-?[\d.]+$", ref):
                o = scene._origin(sc.ents[name].shot)
                c = o[:2] + np.array([float(v) for v in ref.split(",")])
            else:
                c = scene._locate(ref, sc.ents[name].shot)[:2]
        elif "by" in args:
            c = c + np.array([float(v) for v in args[args.index("by") + 1].split(",")])
        else:
            return None
    except (ValueError, IndexError, KeyError):
        return None
    return (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)


def _on_words(scene, m, box_now, other) -> bool:
    """Whether `other` lies over m's words, m's words taken where they are now (moved and grown with m's box)."""
    b0 = _box(m)
    kx = (box_now[2] - box_now[0]) / max(1e-6, b0[2] - b0[0])
    ky = (box_now[3] - box_now[1]) / max(1e-6, b0[3] - b0[1])
    for w in scene.words_of(m):
        ww = (box_now[0] + (w[0] - b0[0]) * kx, box_now[1] + (w[1] - b0[1]) * ky,
              box_now[0] + (w[2] - b0[0]) * kx, box_now[1] + (w[3] - b0[1]) * ky)
        ox, oy = min(ww[2], other[2]) - max(ww[0], other[0]), min(ww[3], other[3]) - max(ww[1], other[1])
        if ox > 0 and oy > 0 and ox * oy > 0.12 * min((ww[2] - ww[0]) * (ww[3] - ww[1]),
                                                       (other[2] - other[0]) * (other[3] - other[1])):
            return True
    return False


def _judged(scene, sc, a, b) -> bool:
    """Whether two things are ones the check says anything about (not one meant to be on the other)."""
    if a.kind in FREE or b.kind in FREE:
        return False
    for x, y in ((a, b), (b, a)):
        if x.mods.get("on") in (y.name,) or x.mods.get("map") == y.name or (x.kind == "note" and x.mods.get("to") == y.name):
            return False
        at = x.mods.get("at")
        if isinstance(at, str) and at.split(".", 1)[0] == y.name and not (
                "." in at and y.kind in R.PIECES and x.kind in R.BESIDE_KINDS):
            return False                        # put at it, or at a place on it, on purpose (not beside a part)
        if any(isinstance(x.mods.get(k), str) and x.mods[k] == y.name for k in R.REL):
            return False                        # put against the whole of it: beside it by construction
    if ("layer" in a.mods or "layer" in b.mods) and a.mods.get("layer") != b.mods.get("layer"):
        return False
    return True


def _held(scene, a, b, ab, bb) -> bool:
    """One set on the other on purpose (render.ScoreScene.nested): a label on its card, letters in their tray, a coin
    in a hand, tools on a map; never anything over words."""
    return scene.nested(a, b, ab, bb) or scene.nested(b, a, bb, ab)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("run_dir")
    a = ap.parse_args()
    words = json.loads((Path(a.run_dir) / "words.json").read_text())
    rep = check(Path(a.score).read_text(), words)
    print("layout: " + json.dumps(rep), flush=True)


if __name__ == "__main__":
    main()
