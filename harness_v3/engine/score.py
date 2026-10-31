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
    cast NAME KIND ARGS [mods]      a character made once: `ent NAME at X,Y` (or `ent X NAME ...`) in any shot
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
    music: str | None = None        # `music calm|warm|tense|none` (sound.py)
    sound: bool | None = None       # `sound off`: no small sounds
    texture: bool | None = None     # `texture off`: no line boil, pen wobble, grain or vignette (feel.py)
    parallax: bool | None = None    # `parallax off`: the layers keep together as the camera travels
    motion: str | None = None       # `motion plain`: plain fades instead of the paper world's slaps and peels
    captions: bool | None = None    # `captions on`: the narration's words at the bottom, the one said lit
    progress: bool | None = None    # `progress on|off`: the chapter bar (on when the score has `chapter` lines)
    cast: dict = field(default_factory=dict)   # `cast NAME KIND ARGS MODS`: a character made once, used by name


# What a modifier is followed by (its value's shape).
MODS = {"at": "xy", "size": "n", "color": "s", "fill": "s", "line": "s", "w": "n", "h": "n", "r": "n", "gap": "n",
        "rot": "n", "layer": "n", "badge": "s", "x": "i", "row": None, "col": None, "grid": "i", "ring": "n",
        "bold": None, "italic": None, "serif": None, "solid": None, "dashed": None, "curve": "n", "max": "n",
        "prefix": "s", "suffix": "s", "opacity": "n", "hidden": None, "shadow": None, "flat": None, "cluster": None,
        "to": "s", "label": "s", "width": "n", "zoom": "n", "on": "s", "nudge": "xy", "flag": "s", "img": "s", "sub": "s",
        "map": "s", "year": "i", "names": None, "rivers": None, "outline": None, "side": "s", "who": "s",
        "seal": None, "down": None, "shape": "s", "inverted": None, "numbered": None, "compass": None, "scale": None,
        "n": "i", "below": "s", "above": "s", "left": "s", "right": "s", "step": "n", "sides": None, "angles": None,
        "majority": None, "answer": "i", "digits": "i", "date": "s", "where": "s", "round": None,
        "hat": "s", "tool": "s", "as": "s", "seat": None, "face": "s", "wear": "s", "hair": "s", "beard": None,
        "longbeard": None, "mustache": None, "stubble": None, "named": None, "frame": "s", "full": None, "skin": "s", "mood": "s", "old": None, "kid": None,
        "alive": None, "per": "n", "cols": "i", "lit": "i", "provinces": None, "style": "s",
        "howdah": None, "plain": None, "display": None, "doe": None, "cub": None, "mallard": None, "open": None,
        "empty": None, "rolled": None, "cushion": None, "load": None, "fruit": None, "sign": "s", "of": "s",
        "cloth": "s"}

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
            if shape in ("n", "i") and not re.match(r"^-?[\d.]+$", v):
                i += 2                          # `size big`: a number was meant; left as it would be
                continue
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


# Words a model writes for a verb the grammar has (`appear X` is `in X`).
VERB_ALIAS = {"appear": "in", "show": "in", "enter": "in", "reveal": "in", "add": "in", "disappear": "out",
              "hide": "out", "exit": "out", "remove": "out", "vanish": "out", "camera": "cam", "zoom": "cam",
              "circle": "circle", "emphasize": "pulse", "emphasise": "pulse"}
# Ways a thing comes on or goes (`in X pop`), also written as the verb (`pop X` is `in X pop`).
IN_WAYS = {"fade", "pop", "rise", "drop", "slide-left", "slide-right", "draw", "write", "grow", "unfold", "slap", "speak"}
OUT_WAYS = {"fade", "shrink", "drop", "peel"}
KEYWORDS = {"look", "music", "sound", "shot", "ent", "texture", "parallax", "motion", "captions", "progress", "cast"}


def _is_time(tok: str) -> bool:
    t = tok.strip()
    if t == "end" or WORD.match(t) or SECS.match(t):
        return True
    a, sep, b = t.partition("-")
    return bool(sep) and bool(WORD.match(a) or SECS.match(a)) and bool(WORD.match(b) or SECS.match(b)
                                                                       or re.match(r"^\d+$", b))


KNOWN_VERBS = {"in", "out", "move", "along", "morph", "color", "dim", "lift", "scale", "spin", "pulse", "shake", "count",
               "grow", "cam", "flow", "float", "bracket", "spotlight", "chapter", "bring", "ring", "circle", "mark",
               "underline", "highlight", "strike", "box", "tick", "cross", "stamp", "callout", "pan", "type", "fill",
               "connect", "follow", "tip", "era", "glow", "walk", "run", "point", "wave", "talk", "carry", "sit",
               "stand", "turn", "cheer", "shrug", "think", "bow", "jump", "nod", "emote", "dance", "clap",
               "facepalm", "laugh", "cry", "shiver", "kick", "look", "faint", "hug", "react", "annex", "travel",
               "give", "throw", "push", "tug", "argue", "whisper", "ride", "dismount", "graze", "rear", "fly",
               "open", "shut", "pickup", "put", "drop", "wear", "holdup", "read", "write", "eat", "drink", "phone",
               "type", "hammer", "sweep", "count", "vote", "ring", "stir", "enter", "exit", "climb", "sleep", "use",
               "drive"}
# Every kind of thing (look.build): a line `ent KIND ...` with no name is given one.
KINDS = {"text", "icon", "circle", "rect", "blob", "ring", "waves", "dots", "num", "bar", "arrow", "path", "pic", "photo",
         "flag", "card", "tag", "label", "map", "region", "pin", "river", "land", "islands", "timeline", "event", "span",
         "chart", "pyramid", "cycle", "flow", "quote", "doc", "title", "labels", "compare", "table", "list", "steps",
         "stat", "calendar", "meter", "balance", "venn", "formula", "bubble", "weather", "tree", "numberline", "plot",
         "triangle", "molecule", "equation", "circuit", "race", "parliament", "market", "climate", "quiz", "lens",
         "split", "clock", "odometer", "clipping", "shade", "march", "inset", "layers", "globe", "who", "polaroids",
         "backdrop", "portrait", "person", "phrase", "nation", "country", "isotype", "note", "eyes", "animal", "prop"}
ARG_WORDS = {"stagger", "to", "by", "n", "arc", "zoom", "via", "into", "at", "dim"}


def _mend_action(toks: list[str], names=frozenset()) -> list[list[str]] | None:
    """An action line as the grammar has it (TIME VERB TARGET ARGS), from the ways models get it wrong: the time
    elsewhere on the line, `in fade X`, `fade in X`, `appear X`, `pop X`, `w12-14`, several actions joined by `|`.
    None: not an action a mend can make out."""
    # several actions on one line
    if "|" in toks:
        parts, cur = [], []
        for t in toks:
            if t == "|":
                parts.append(cur)
                cur = []
            else:
                cur.append(t)
        parts.append(cur)
        out, when = [], None
        for p in parts:
            p = [t for t in p if t]
            if not p:
                continue
            if when and not any(_is_time(t) for t in p):
                p = [when] + p
            m = _mend_action(p, names)
            if m:
                out += m
                when = when or m[0][0]
        return out or None
    # the time: the first token if it is one, else the first that is one; a name that looks like one (`w1`) is a name
    times = [i for i, t in enumerate(toks) if _is_time(t) and t not in names]
    if not times:
        return None
    if times[0] == 0:
        times = [0] + [i for i in times[1:] if i <= 2 and toks[i] != toks[0] and len(toks) > i + 1
                       and toks[i + 1] in names]          # `w216 move w216 X`: the time said twice
    when = toks[times[0]]
    a, _, b = when.partition("-")
    if b and re.match(r"^\d+$", b) and a.startswith("w"):
        when = f"{a}-w{b}"                       # w229-230
    rest = [t for i, t in enumerate(toks) if i not in times]
    if not rest:
        return None
    verb = rest[0].lower()
    args = rest[1:]
    if verb not in KNOWN_VERBS and verb not in VERB_ALIAS and verb not in IN_WAYS and args and \
            (args[0].lower() in KNOWN_VERBS or args[0].lower() in VERB_ALIAS):
        verb, args = args[0].lower(), [rest[0]] + args[1:]     # `w46 church appear`: the thing first
    if verb == "fade" and args and args[0] in ("in", "out"):
        verb, args = args[0], args[1:] + ["fade"]
    if not (verb in ("enter", "exit") and len(args) >= 2 and args[1] in names):     # `enter P HOUSE`: a person's
        verb = VERB_ALIAS.get(verb, verb)
    person_use = verb in ("write", "drop") and len(args) >= 2 and args[0] in names and args[1] in names
    if verb in IN_WAYS - {"fade", "draw", "grow"} and args and not person_use:
        verb, args = "in", [args[0], verb] + args[1:]      # `pop X` is `in X pop`
    if verb in ("in", "out") and len(args) >= 2 and args[0] in (IN_WAYS | OUT_WAYS) \
            and args[1] not in (IN_WAYS | OUT_WAYS) and args[1] not in ARG_WORDS \
            and not re.match(r"^-?[\d.,]+$", args[1]):
        args = [args[1], args[0]] + args[2:]               # `in fade X` is `in X fade`
    if verb in ("in", "out") and args:
        ways = IN_WAYS if verb == "in" else OUT_WAYS
        rest_ways = [t for t in args[1:] if t in ways]
        if len(rest_ways) > 1:                             # one way only: the first
            first = rest_ways[0]
            args = [args[0]] + [t for t in args[1:] if t not in ways or t == first]
    return [[when, verb] + args]


def _join_xy(toks: list[str]) -> list[str]:
    """`-1.5, -2.9` or `a, b, c` written with spaces: one token again."""
    out = []
    for t in toks:
        if out and out[-1].endswith(",") and len(out) > 1 and not (" " in out[-1]):
            out[-1] += t
        else:
            out.append(t)
    return out


def parse(text: str, words: list[dict], seconds: float) -> Score:
    """A score's text read against the narration's words. A line that cannot be read is left out, with a note
    (the rest plays). Two mends, each said in the notes (the shots are written one call at a time, and a small
    model forgets): a name made again in a later shot is a new thing (`people` becomes `people_s2` from there on;
    the earlier one stays where it was), and a shot no camera move goes to gets one, as its first action plays."""
    sc = Score(end=seconds)
    state: dict = {"shot": None}
    alias: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        try:
            toks = shlex.split(raw, comments=True)      # a `#` outside quotes starts a comment
        except ValueError as e:
            sc.notes.append(f"line {n}: {e}")
            continue
        if not toks:
            continue
        toks = _join_xy(toks)
        state["raw"] = raw
        items = [toks]
        if toks[0] not in KEYWORDS:
            mended = _mend_action(toks, frozenset(alias))
            if mended:
                if [" ".join(m) for m in mended] != [" ".join(toks)]:
                    sc.notes.append(f"mended line {n}: `{' '.join(toks)[:80]}` read as " +
                                    "; ".join(f"`{' '.join(m)}`" for m in mended))
                items = mended
        for toks in items:
            _one_line(sc, toks, n, words, seconds, alias, state)
    _name_the_nameless(sc, state.get("nameless", []))
    _camera_to_every_shot(sc)
    sc.acts.sort(key=lambda a: a.t0)
    return sc


def _name_the_nameless(sc: Score, nameless: list[tuple[str, str]]) -> None:
    """`ent map eu ...` meant `ent eu map ...` when `eu` is what the other lines call it (`eu.mainz`)."""
    if not nameless:
        return
    used = set()
    for a in sc.acts:                           # what actions act on, and places on it (`eu.mainz`)
        for t in [a.target, *(x for x in a.args if "." in x)]:
            for part in str(t).split(","):
                m = REF.match(part.strip())
                if m:
                    used.add(m.group(1))
    for e in sc.ents.values():
        for v in e.mods.values():
            if isinstance(v, str):
                m = REF.match(v.split(",")[0])
                if m:
                    used.add(m.group(1))
    for name, first in nameless:
        e = sc.ents.get(name)
        if e is None or first not in used or first in sc.ents or not e.args or e.args[0] != first:
            continue
        del sc.ents[name]
        e.name, e.args = first, e.args[1:]
        sc.ents[first] = e
        for a in sc.acts:
            if a.target == name:
                a.target = first
        sc.notes.append(f"mended: {first} is the name of the {e.kind} on line {e.line}")


def _one_line(sc: Score, toks: list[str], n: int, words, seconds, alias: dict, state: dict) -> None:
    """One line of the score read into it (`state` keeps the shot the lines are in)."""
    shot = state.get("shot")
    line = " ".join(toks)
    head = toks[0]
    try:
        if head == "look":
            sc.look = toks[1]
        elif head == "music":
            sc.music = toks[1] if len(toks) > 1 else "calm"
        elif head == "sound":
            sc.sound = (toks[1] if len(toks) > 1 else "on") not in ("off", "none", "0")
        elif head in ("texture", "parallax", "captions", "progress"):
            setattr(sc, head, (toks[1] if len(toks) > 1 else "on") not in ("off", "none", "0", "no"))
        elif head == "motion":
            sc.motion = toks[1] if len(toks) > 1 else "paper"
        elif head == "cast":
            # `cast monk person wear habit hat hood longbeard`: a character once, then `ent m1 monk at X,Y` anywhere,
            # always looking the same (its looks are picked from the cast's name, not the thing's)
            args, mods = parse_mods(toks[3:])
            mods["_name"] = toks[1]
            sc.cast[toks[1]] = (toks[2], args, mods)
        elif head == "shot":
            if len(toks) > 1 and toks[1] in ("at", "zoom"):          # `shot at X,Y`: no name
                toks = [toks[0], f"shot{n}"] + toks[1:]
                sc.notes.append(f"mended line {n}: a shot with no name: called {toks[1]}")
            _, mods = parse_mods(toks[2:])
            if "at" in mods:
                x, y = mods["at"]
            else:
                last = list(sc.shots.values())[-1] if sc.shots else None
                x, y = ((last.x + SHOT_STEP, last.y) if last else (0.0, 0.0))
            shot = Shot(toks[1], x, y, float(mods.get("zoom", 1.0)), n)
            sc.shots[shot.name] = shot
        elif head == "ent":
            cast = None
            if len(toks) > 1 and toks[1] in sc.cast and (len(toks) == 2 or (toks[2] not in sc.cast and toks[2] in MODS)):
                toks = [toks[0], toks[1]] + toks[1:]            # `ent monk at X,Y`: the cast's own name, used
            if len(toks) > 2 and toks[2] in sc.cast:
                # a cast member: its kind, words and looks, with what this line adds (where it stands, its mood...)
                cast = sc.cast[toks[2]]
                toks = toks[:2] + [cast[0]] + toks[3:]
            if len(toks) > 2 and toks[1] in KINDS and toks[2] not in KINDS:
                # `ent map europe ...`: no name, the kind named; the thing is called by its kind (as its actions do)
                name = toks[1]
                k = 2
                while name in sc.ents and sc.ents[name].shot == (shot.name if shot else "main"):
                    name = f"{toks[1]}{k}"
                    k += 1
                sc.notes.append(f"mended line {n}: `{line[:60]}` has no name: called {name}")
                if f'"{toks[2]}"' not in state.get("raw", "") and f"'{toks[2]}'" not in state.get("raw", ""):
                    state.setdefault("nameless", []).append((name, toks[2]))     # (words in quotes are words)
                toks = [toks[0], name] + toks[1:]
            if shot is None:
                shot = Shot("main", 0.0, 0.0, 1.0, n)
                sc.shots["main"] = shot
            # (a prop's or an animal's kind, `prop crown`, is a word, never a renamed thing called crown)
            keep = 4 if toks[2] in ("prop", "animal") else 3
            toks = toks[:keep] + [_renamed(t, alias) for t in toks[keep:]]
            args, mods = parse_mods(toks[3:])
            if cast is not None:
                args, mods = list(cast[1]) + args, {**cast[2], **mods}
            nd = mods.get("nudge")
            if isinstance(nd, tuple) and (abs(nd[0]) > SCREEN_W / 2 or abs(nd[1]) > SCREEN_H / 2):
                # a nudge is a small shift from its place; one as big as the screen is the shot's own place over again
                sc.notes.append(f"line {n}: `nudge {nd[0]:g},{nd[1]:g}` would put {toks[1]} off the screen: no nudge "
                                f"(a nudge is a small shift, in the shot's own coordinates)")
                mods.pop("nudge")
            for k in ("below", "above", "left", "right"):
                # `at X below 0.8`: below X, 0.8 apart
                if isinstance(mods.get(k), str) and re.match(r"^-?[\d.]+$", mods[k]) and isinstance(mods.get("at"), str):
                    mods["gap"] = float(mods[k])
                    mods[k] = mods.pop("at")
            name = toks[1]
            if name in sc.cast and cast is None and toks[2] != sc.cast[name][0]:
                sc.notes.append(f"line {n}: {name!r} is a cast {sc.cast[name][0]}, and this makes it a {toks[2]}: from here "
                                f"on {name} is the {toks[2]} (call it another name, {name}_{toks[2]}, to keep the cast one)")
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
            if verb == "cam" and target == "at" and len(toks) > 3 and "at" not in sc.shots:
                # `cam at X,Y`: the shot at that place (else the one these lines are in)
                try:
                    x, y = _xy(toks[3])
                    near = min(sc.shots.values(), key=lambda s_: abs(s_.x - x) + abs(s_.y - y))
                    target = near.name if abs(near.x - x) + abs(near.y - y) < 1.0 else (shot.name if shot else target)
                except ValueError:
                    target = shot.name if shot else target
                toks = toks[:2] + [target] + toks[4:]
                line = " ".join(toks)
            sc.acts.append(Act(t0, t1, verb, target, toks[3:], n, line))
    except (ValueError, IndexError) as e:
        sc.notes.append(f"line {n}: {e}: {line[:80]}")
    state["shot"] = shot


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
