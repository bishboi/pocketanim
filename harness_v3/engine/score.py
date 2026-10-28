"""The score: what a video shows and when, as a few short lines a small model can write.

A video is a canvas larger than the screen, cut into SHOTS (one idea each, a region of the canvas). In each shot,
ENTITIES are made (a word, an icon, dots, a shape, a number...) and ACTIONS move them on the narration's words: they
come in, move, morph, count, are pointed at, and the camera travels between them. Nothing is a slide: what is up
stays up until an action takes it away, and the camera moves to what comes next.

    look paper
    shot bay                                    # a shot: the camera's place on the canvas (auto, or `at X,Y`)
    ent sea    waves 3 w 13 color teal at 0,-2.5
    ent ships  icon ship x4 row gap 1.4 badge navy at 3,-1.6
    ent year   text "1853" size 2.4 bold at 0,2.4
    w0         cam bay
    w1         in year write
    w2-w4      in ships slide-left stagger .25
    w7         ring japan coral

Lines:
    look NAME                       the palette (look.py)
    shot NAME [at X,Y] [zoom Z]     a new shot; later `ent` lines belong to it (their `at` is in its frame,
                                    the screen being 14.2 x 8 at zoom 1)
    ent NAME KIND ARGS [mods]       an entity (KIND and ARGS: look.py `build`)
    TIME VERB TARGET [ARGS]         an action (render.py `VERBS`)

TIME: `w12` (as the 12th word is said), `w12-w19` (over those words), `w12+0.4` (seconds after), `t3.5` (seconds
into the video), `end`. A TARGET is an entity, `name[3]` (its 4th part), `name[2:5]` (a run of its parts), or
`a,b,c` (several).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

SCREEN_W, SCREEN_H = 14.22, 8.0
SHOT_STEP = 18.0            # how far apart shots are placed when the score does not say


@dataclass
class Ent:
    name: str
    kind: str
    args: list[str]
    mods: dict
    shot: str
    line: int


@dataclass
class Shot:
    name: str
    x: float
    y: float
    zoom: float
    line: int


@dataclass
class Act:
    t0: float
    t1: float | None          # None: the verb's own length
    verb: str
    target: str
    args: list[str]
    line: int
    text: str


@dataclass
class Score:
    look: str = "paper"
    shots: dict[str, Shot] = field(default_factory=dict)
    ents: dict[str, Ent] = field(default_factory=dict)
    acts: list[Act] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    end: float = 0.0


# What a modifier is followed by (its value's shape).
MODS = {"at": "xy", "size": "n", "color": "s", "fill": "s", "line": "s", "w": "n", "h": "n", "r": "n", "gap": "n",
        "rot": "n", "layer": "n", "badge": "s", "x": "i", "row": None, "col": None, "grid": "i", "ring": "n",
        "bold": None, "italic": None, "serif": None, "solid": None, "dashed": None, "curve": "n", "max": "n",
        "prefix": "s", "suffix": "s", "opacity": "n", "hidden": None, "shadow": None, "flat": None, "cluster": None,
        "to": "s", "label": "s", "width": "n", "zoom": "n", "on": "s", "nudge": "xy", "flag": "s", "img": "s", "sub": "s"}

WORD = re.compile(r"^w(\d+)([+-]\d*\.?\d+)?$")
SECS = re.compile(r"^t(\d*\.?\d+)$")


def _xy(v: str) -> tuple[float, float]:
    a, b = v.split(",")
    return float(a), float(b)


def _time(tok: str, words: list[dict], end: float) -> float:
    tok = tok.strip()
    if tok == "end":
        return end
    m = WORD.match(tok)
    if m:
        k = int(m.group(1))
        if not words:
            raise ValueError("no word times")
        k = max(0, min(k, len(words) - 1))
        return float(words[k]["start"]) + float(m.group(2) or 0)
    m = SECS.match(tok)
    if m:
        return float(m.group(1))
    raise ValueError(f"not a time: {tok!r} (w12, w12+0.4, t3.5 or end)")


def _when(tok: str, words: list[dict], end: float) -> tuple[float, float | None]:
    """`w12` -> (t, None); `w12-w19` -> (t0, t1), the second word's end when it is a word."""
    if "-" in tok[1:] and not WORD.match(tok):
        a, b = tok.split("-", 1) if not tok.startswith("t") else tok.split("-", 1)
        t0 = _time(a, words, end)
        m = WORD.match(b)
        if m and not m.group(2):
            k = max(0, min(int(m.group(1)), len(words) - 1))
            t1 = float(words[k]["end"])
        else:
            t1 = _time(b, words, end)
        return t0, max(t1, t0 + 0.1)
    return _time(tok, words, end), None


def parse_mods(toks: list[str]) -> tuple[list[str], dict]:
    """Positional arguments and modifiers (`at 1,2`, `size 2`, `bold`...)."""
    args, mods, i = [], {}, 0
    while i < len(toks):
        t = toks[i]
        if t in MODS:
            shape = MODS[t]
            if shape is None:
                mods[t] = True
                i += 1
                continue
            if i + 1 >= len(toks):
                raise ValueError(f"{t!r} needs a value")
            v = toks[i + 1]
            if shape == "xy" and not re.match(r"^-?[\d.]+,-?[\d.]+$", v):
                mods[t] = v                 # a place or an entity (`at japan.uraga`): found when it is drawn
            else:
                mods[t] = _xy(v) if shape == "xy" else float(v) if shape == "n" else int(v) if shape == "i" else v
            i += 2
            continue
        if t.startswith("x") and t[1:].isdigit():
            mods["x"] = int(t[1:])          # `x4`: four of it
            i += 1
            continue
        args.append(t)
        i += 1
    return args, mods


REF = re.compile(r"^([A-Za-z_][\w\-]*)(.*)$")


def _renamed(tok: str, alias: dict[str, str]) -> str:
    """A token's entity names (`a`, `a[2]`, `a,b`, `a.place`) as they are known now (see `parse`)."""
    out = []
    for part in tok.split(","):
        m = REF.match(part)
        out.append(alias[m.group(1)] + m.group(2) if m and m.group(1) in alias else part)
    return ",".join(out)


def parse(text: str, words: list[dict], seconds: float) -> Score:
    """A score's text read against the narration's words. A line that cannot be read is left out, with a note
    (the rest plays). Two mends, each said in the notes (the shots are written one call at a time, and a small
    model forgets): a name made again in a later shot is a new thing (`people` becomes `people_s2` from there on;
    the earlier one stays where it was), and a shot no camera move goes to gets one, as its first action plays."""
    sc = Score(end=seconds)
    shot: Shot | None = None
    alias: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        try:
            toks = shlex.split(raw, comments=True)      # a `#` outside quotes starts a comment
        except ValueError as e:
            sc.notes.append(f"line {n}: {e}")
            continue
        if not toks:
            continue
        line = " ".join(toks)
        head = toks[0]
        try:
            if head == "look":
                sc.look = toks[1]
            elif head == "shot":
                _, mods = parse_mods(toks[2:])
                if "at" in mods:
                    x, y = mods["at"]
                else:
                    last = list(sc.shots.values())[-1] if sc.shots else None
                    x, y = ((last.x + SHOT_STEP, last.y) if last else (0.0, 0.0))
                shot = Shot(toks[1], x, y, float(mods.get("zoom", 1.0)), n)
                sc.shots[shot.name] = shot
            elif head == "ent":
                if shot is None:
                    shot = Shot("main", 0.0, 0.0, 1.0, n)
                    sc.shots["main"] = shot
                toks = toks[:3] + [_renamed(t, alias) for t in toks[3:]]
                args, mods = parse_mods(toks[3:])
                name = toks[1]
                if name in alias and sc.ents[alias[name]].shot != shot.name:
                    new = f"{name}_{shot.name}"
                    while new in sc.ents:
                        new += "_"
                    sc.notes.append(f"line {n}: {name!r} was made again in shot {shot.name}: a new thing ({new}); "
                                    f"the one in shot {sc.ents[alias[name]].shot} stays")
                    alias[name] = new
                else:
                    alias.setdefault(name, name)
                sc.ents[alias[name]] = Ent(alias[name], toks[2], args, mods, shot.name, n)
            else:
                t0, t1 = _when(head, words, seconds)
                toks = toks[:2] + [_renamed(t, alias) for t in toks[2:]]
                verb = toks[1]
                target = toks[2] if len(toks) > 2 else ""
                sc.acts.append(Act(t0, t1, verb, target, toks[3:], n, line))
        except (ValueError, IndexError) as e:
            sc.notes.append(f"line {n}: {e}: {line[:80]}")
    _camera_to_every_shot(sc)
    sc.acts.sort(key=lambda a: a.t0)
    return sc


def shot_of(sc: Score, ref: str) -> str | None:
    """The shot an action's target (or a camera move's) is in."""
    if ref in sc.shots:
        return ref
    m = REF.match(ref.split(",")[0])
    e = sc.ents.get(m.group(1)) if m else None
    return e.shot if e else None


def _camera_to_every_shot(sc: Score) -> None:
    shots = list(sc.shots)
    seen = {shot_of(sc, a.target) for a in sc.acts if a.verb == "cam"}
    for k, name in enumerate(shots):
        if name in seen or (k == 0 and not any(a.verb == "cam" for a in sc.acts)):
            continue
        mine = [a for a in sc.acts if a.verb != "cam" and shot_of(sc, a.target) == name]
        if not mine:
            continue
        t = min(a.t0 for a in mine)
        sc.acts.append(Act(t, None, "cam", name, [], sc.shots[name].line, f"cam {name} (added)"))
        sc.notes.append(f"shot {name} had no camera move: the camera goes there at {t:.1f} s, as it starts")
