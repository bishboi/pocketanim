"""The two kinds of call that write a video, kept small enough for a small model.

    STORYBOARD (one call a video): the narration with its words numbered -> shots: for each idea, a visual
    metaphor, the words it covers, the things it shows.
    SCORE (one call a shot, in order): the shot's words with their numbers and times, the shot's plan, the last
    shot's entities still up -> the shot's lines in the score's grammar (score.py).

The grammar card is the whole manual: a few hundred tokens, no examples of polished templates, so a model builds
from a few plain pieces and the actions, not from a catalogue.
"""

from __future__ import annotations

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
- Bring a new shot in with `cam SHOT` over the first words of its idea; the old shot stays where it was.
- Use few kinds; get life from actions: stagger, arcs, morphs, flows, the camera.
- Keep text short (1-4 words). The narration says the sentences."""

STORYBOARD = """You are planning a short animated explainer. Read the narration (its words are numbered) and cut it into
SHOTS: one idea each (usually 1-2 sentences, 5-10 seconds). For each shot give one line:
SHOT name | words wA-wB | metaphor: what we SEE that makes the idea clear | things: 3-6 plain things on screen
Prefer things that can move, transform or count (dots for people, a bar for a gap, a map, icons that turn into
other icons) over text. Keep continuity: a thing may carry on into the next shot."""

SCORE = """You write one SHOT of an animated explainer's score, in the grammar below. You get the shot's plan, its
narration with every word numbered and timed, and what the shot before left up. Answer with only the shot's
lines: its `shot` line, its `ent` lines, then its actions in time order."""


def storyboard_prompt(words: list[dict]) -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}" for w in words)
    return STORYBOARD, f"NARRATION: {said}\n\nWrite the shots, one line each."


def score_prompt(plan: str, words: list[dict], shot_at: tuple[float, float], before: str = "") -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}@{w['start']:.1f}" for w in words)
    user = (f"SHOT PLAN: {plan}\nPLACE IT: at {shot_at[0]:g},{shot_at[1]:g}\nWORDS: {said}\n"
            + (f"UP FROM THE SHOT BEFORE (its names; reuse them, or move them out): {before}\n" if before else "")
            + "Write the shot's lines.")
    return SCORE + "\n\n" + GRAMMAR, user


CRITIC = """You judge frames of an animated explainer, each with its time and the words being said. Point out only
real faults, one line each: `tSECONDS: FAULT` -- dead time (nothing moving for long), text too small or cut off,
things overlapping, an action far from its word, a change that feels like a slide (everything replaced at once).
Answer `ok` when there is none."""
