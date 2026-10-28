"""The two kinds of call that write a video, kept small enough for a small model.

    STORYBOARD (one call a video): the narration with its words numbered -> shots: for each idea, a visual
    metaphor, the words it covers, the things it shows.
    SCORE (one call a shot, in order): the shot's words with their numbers and times, the shot's plan, the last
    shot's entities still up -> the shot's lines in the score's grammar (score.py).

The grammar card is the whole manual: a few hundred tokens, no examples of polished templates, so a model builds
from a few plain pieces and the actions, not from a catalogue.
"""

from __future__ import annotations

import re

GRAMMAR = """SCORE GRAMMAR (one item per line; # starts a comment)
shot NAME at X,Y              a new shot on the canvas (shots ~18 apart). Its `ent` lines follow.
ent NAME KIND ARGS [MODS]     a thing in the current shot. The screen is 14.2 wide, 8 tall, centred on the shot.
  KINDS: text "WORDS" | icon NAME (Lucide names: ship, train-front, factory, wheat, users, landmark, castle, lock,
         coins, flag, scroll, crown, mountain-snow, globe, school, anchor, swords, book-open...) | circle | rect | blob
         | ring | waves N | land japan | dots N | num V | bar V | arrow A B | path P P P...
  MODS: at X,Y | at LAND.PLACE | size S | color C | fill C | badge C (icon on a disc) | bold | x N (N copies) with
        row|col|grid C|ring R and gap G | on PATH (copies spread along it) | nudge X,Y | layer N | rot DEG |
        w W h H r R | max M | suffix "..." prefix "..." | dashed | curve C | grid C | cluster
  COLORS: ink navy coral teal gold green sky soft sand red white
TIME VERB TARGET [ARGS]       an action. TIME: wN (as word N is said), wN-wM (over those words), wN+0.4, tSECONDS, end
  in T [fade|pop|rise|drop|slide-left|slide-right|draw|write|grow|unfold] [stagger S]
  out T [fade|shrink|drop] [stagger S]
  move T to X,Y | to ENT | by DX,DY [arc A] [stagger S]
  along T PATH | flow PATH n N COLOR | float T AMP
  morph A B [stagger S] (A becomes B; B never shown before)
  count NUM V | grow BAR V | color T C | dim T O | lift T | scale T K | spin T DEG | pulse T | shake T
  ring T C | mark T C
  cam SHOT | cam SHOT X,Y zoom Z | cam ENT zoom Z | cam wide
TARGET: NAME, NAME[2], NAME[0:3], or A,B,C.
RULES
- Nothing is a slide: keep things up and change them (move, morph, count, grow, color) instead of replacing them.
- Something moves on every phrase; land each action on the word that names it.
- Start every shot with `cam SHOT` on its first word: the camera only goes where a `cam` line sends it.
- A name is one thing for the whole video: a thing from the shot before is used by its name (no new `ent` line for
  it); a new thing gets a new name.
- Lay things apart on the screen (x from -6 to 6, y from -3.4 to 3.4; side by side at least 3 apart). Overlap only
  to put one on another on purpose (a label on its card, an icon on its badge).
- Use few kinds; get life from actions: stagger, arcs, morphs, flows, the camera.
- Keep text short (1-4 words). The narration says the sentences."""

STORYBOARD = """You are planning a short animated explainer. Read the narration (its words are numbered) and cut it into
SHOTS: one idea each (usually 1-2 sentences, 5-10 seconds). For each shot give one line:
SHOT name | words wA-wB | metaphor: what we SEE that makes the idea clear | things: 3-6 plain things on screen
for example:
SHOT bay | words w0-w14 | metaphor: four dark ships slide into a quiet bay | things: sea, ships, map of Japan, 1853
The shots cover every word, in order, without gaps.
Prefer things that can move, transform or count (dots for people, a bar for a gap, a map, icons that turn into
other icons) over text. Keep continuity: a thing may carry on into the next shot."""

SCORE = """You write one SHOT of an animated explainer's score, in the grammar below. You get the shot's plan, its
narration with every word numbered and timed, and what the shot before left up. Answer with only the shot's
lines: its `shot` line, its `ent` lines, then its actions in time order."""


def storyboard_prompt(words: list[dict]) -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}" for w in words)
    return STORYBOARD, f"NARRATION: {said}\n\nWrite the shots, one line each."


SHOT_LINE = re.compile(
    r"^[\s*#>\-\d.)]*(?:shot\b\s*(?:\d+\s*[:.\-]?\s*)?)?(?P<name>[^|]*?)\s*[|:]\s*(?:words?\s*)?"
    r"w?(?P<a>\d+)\s*(?:-|–|—|to)\s*w?(?P<b>\d+)\s*\|(?P<plan>.*)$", re.I)


def parse_storyboard(text: str, words: int) -> list[dict]:
    """The storyboard's shot lines, read leniently (a model may drop `SHOT`, number its lines, bold them, or write
    `words 3-9`): [{name, a, b, plan}], the shots in word order, each a plain unique name."""
    shots: list[dict] = []
    for line in text.splitlines():
        m = SHOT_LINE.match(line.strip().replace("**", ""))
        if not m:
            continue
        a, b = int(m.group("a")), int(m.group("b"))
        if a > b or a >= max(words, 1):
            continue
        name = re.sub(r"[^a-z0-9]+", "_", m.group("name").lower()).strip("_")[:20] or f"s{len(shots) + 1}"
        if name[0].isdigit():
            name = "s" + name
        while any(x["name"] == name for x in shots):
            name += "2"
        shots.append({"name": name, "a": a, "b": min(b, words - 1) if words else b, "plan": m.group("plan").strip(" |")})
    return sorted(shots, key=lambda x: x["a"])


def score_prompt(plan: str, words: list[dict], shot_at: tuple[float, float], before: str = "") -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}@{w['start']:.1f}" for w in words)
    user = (f"SHOT PLAN: {plan}\nPLACE IT: at {shot_at[0]:g},{shot_at[1]:g}\nWORDS: {said}\n"
            + (f"UP FROM THE SHOT BEFORE (use these names, never `ent` them again; or move them out): {before}\n" if before else "")
            + (f"Start with: w{words[0]['i']} cam SHOT_NAME\n" if words else "")
            + "Write the shot's lines.")
    return SCORE + "\n\n" + GRAMMAR, user


CRITIC = """You judge frames of an animated explainer, each with its time and the words being said. Point out only
real faults, one line each: `tSECONDS: FAULT` -- dead time (nothing moving for long), text too small or cut off,
things overlapping, an action far from its word, a change that feels like a slide (everything replaced at once).
Answer `ok` when there is none."""


SCRIPT = """You are a great teacher turning pages of a book into the narration of short animated explainer videos.
Read the pages and write VIDEOS: each one idea of the pages, about SECONDS seconds spoken (WORDS words), together
covering what the pages teach, in the book's order. Write only this, nothing else:

VIDEO: a short title
one spoken sentence a line
...

HOW A GREAT TEACHER TELLS IT:
- One story with one big question, asked in the first video and answered by the last. Each video picks up where the
  one before leaves off and ends on something open that the next one answers (the last ends on the answer).
- Concrete before abstract: a scene, an object, a number made tangible, then the term. Everyday life is the best
  source.
- Make them guess before you tell: ask, let them think a beat, then answer. Name the wrong idea students usually
  hold, then show why it fails.
- Say things that can be SHOWN: things that move, grow, split, join, count up, travel on a map, turn into other
  things. The video draws what the sentences name, so name it plainly.
- Short sentences, one a line, as they are spoken; vary the rhythm. Never read out a list, never a summary.
- Facts come from the pages only: no invented events, people, quotes, numbers or dates. A scene you imagine is said
  as imagined ("imagine...")."""


def script_prompt(pages: str, videos: int, seconds: int, notes: str = "") -> tuple[str, str]:
    words = f"{int(seconds * 2.2)}-{int(seconds * 2.7)}"
    system = SCRIPT.replace("SECONDS", str(seconds)).replace("WORDS", words)
    user = (f"Write {videos} video{'s' if videos != 1 else ''} at most (fewer when the pages hold less).\n"
            + (f"THE TEACHER'S NOTES: {notes}\n" if notes.strip() else "")
            + f"\nTHE PAGES:\n{pages}")
    return system, user


def parse_script(text: str) -> list[dict]:
    """`VIDEO: title` then its lines -> [{title, narration}]."""
    out: list[dict] = []
    for line in text.splitlines():
        s = line.strip().strip("*").strip()
        if not s or s.startswith("```"):
            continue
        low = s.lower()
        if low.startswith("video:") or low.startswith("video "):
            title = s.split(":", 1)[1].strip() if ":" in s else s[6:].strip()
            out.append({"title": title.strip("*# ") or f"Video {len(out) + 1}", "lines": []})
        elif out:
            out[-1]["lines"].append(s.lstrip("-• ").strip())
    return [{"title": v["title"], "narration": "\n".join(x for x in v["lines"] if x)} for v in out if v["lines"]]
