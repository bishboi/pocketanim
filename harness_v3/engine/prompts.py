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
         | ring | waves N | dots N | num V | bar V | arrow A B | path P P P...
         | pic "WHAT" (a picture made for this video: ONE object, person or building, cut out; 1-3 a shot)
         | photo "A SCENE" (a framed print of a place or scene). Say exactly what to draw, of its time and place:
           pic "a 14th-century English silver penny, worn, both faces stamped" not pic "a coin"; photo "a muddy
           medieval village street at dawn, timber houses, a church tower behind" not photo "a village". No words in it.
         | flag CODE (jp us in gb fr de cn...) | card "TITLE" [flag CODE] [img "WHAT"] [sub "a line"] (a paper card)
         | tag "WORDS" (bold words on the accent colour: the key number or claim) | label "WORDS" (small spaced
           capitals: a heading over something, a caption, a source)
  MODS: at X,Y | at NAME.PLACE (a place on a map, a year on a timeline; a picture at a flow's node goes beside it) |
        below X | above X | left X | right X (against X's edge, `gap G`; X a thing or a part: below fl.town) | size S | color C | fill C | badge C (icon on a disc) | bold | x N (N copies) with
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
  MARKS (stay until the thing goes): ring T C | underline T | highlight T | strike T | box T | tick T | cross T |
        stamp T "WORDS" | callout T "WORDS" [left|right|up|down] | bracket A,B,C "WORDS" | spotlight T (all else
        veiled; `lift X` brings one back)
  pan PHOTO [zoom K] (a slow push into a still) | type T (letter by letter) | fill SHAPE 60 C (fills like water)
  connect A B "WORDS" (an arrow drawn between them) | follow T [zoom Z] (the camera keeps a moving thing in view)
  glow T C (a soft light behind it) | era MAP YEAR (its borders change to that year's) | tip BALANCE left|right
  cam SHOT | cam SHOT X,Y zoom Z | cam ENT zoom Z | cam wide | cam SHOT via page|tear|whip (a page turned, torn
  paper, a fast swing: for a change of chapter)
TARGET: NAME, NAME[2], NAME[0:3], A,B,C, or a named part of a piece (soc.nobles, fl.market).
RULES
- Nothing is a slide: keep things up and change them (move, morph, count, grow, color) instead of replacing them.
- Something moves on every phrase; land each action on the word that names it.
- Start every shot with `cam SHOT` on its first word: the camera only goes where a `cam` line sends it.
- A name is one thing for the whole video: a thing from the shot before is used by its name (no new `ent` line for
  it); a new thing gets a new name.
- Lay things apart on the screen (x from -6 to 6, y from -3.4 to 3.4; side by side at least 3 apart). Overlap only
  to put one on another on purpose (a label on its card, an icon on its badge).
- Show real things: a pic, a photo, a flag or a card says more than a line icon. One big picture per idea.
- Words on screen: a tag for the key number, a label for a heading; never sentences (the voice says them).
- Use few kinds; get life from actions: stagger, arcs, morphs, flows, the camera.
- Keep text short (1-4 words). The narration says the sentences."""

# The bigger pieces, each told to a shot's call only when its plan asks for it (the storyboard names them), so the
# card a small model reads stays short. Each is one `ent` placed freely; its parts come on by the actions.
KIT = {
    "map": """  map REGION   a real, accurate map: europe, british isles, mediterranean, middle east, india, china, world...,
               a country's name, or "LON0,LAT0,LON1,LAT1"; `year Y` draws the states of that time; `names`, `rivers`,
               `compass`, `scale` (a scale bar);
               `w 12 h 6.6` (it fills that). Every place on it is MAP.PLACE: eu.paris, eu.constantinople, eu.north_sea
  region "NAME" on M   a country, a state of the map's year ("Holy Roman Empire") or a sea, shaded where it really
               is; `color`, `opacity`, `outline`
  pin "PLACE" on M     a town marked, its name beside (`side left`)  |  river "NAME" on M
  shade "WHAT" on M K:V ...   countries coloured by a value, with a key (a choropleth)
  march M.a M.b M.c [width W]   a thick arrow swelling along a route (armies, migrations, trade winds)
  inset on M   a small world map in its corner, where M is boxed | `era M 1500`: borders change to 1500's
  globe LON,LAT   the Earth as a globe | layers "TOP" ... "BOTTOM" [round]   bands or a cut-away globe's rings
  Where things happen, use a map, never a blob for a country; routes are `path M.a M.b M.c` (then `along SHIP
  ROUTE`); the camera goes to a place: `cam M.paris zoom 2`.""",
    "timeline": """  timeline Y0 Y1 [w 12]   an axis of years (500bc, 1347); every year on it is TL.YEAR (`move x to tl.1347`)
  event YEAR "WORDS" on TL   a card on a stem at its year (kept clear of the others)
  span Y0 Y1 "WORDS" on TL   a band along the axis  (`in` each on the word that names it)""",
    "science": """  numberline A B [step S]   a number line; NL.3 is a place on it (`move pin to nl.3`)
  plot "x^2 - 2" A B   axes and a curve y = f(x) for x from A to B; PL.2 is the curve at x = 2 (`move dot to pl.2`)
  triangle A:0,0 B:4,0 C:1,3 [sides] [angles]   a shape from its corners, named (lengths, angles marked)
  molecule H2O   balls and sticks (H2O CO2 CH4 NH3 O2 NaCl ...)
  equation "2x + 3 = 7" "2x = 4" "x = 2"   working, line by line, `=` in a column (`in eq[1]`; `highlight eq[2]`)
  formula "6CO_2 + 6H_2O -> C_6H_12O_6"   (_ below, ^ above, -> arrow)
  circuit "battery>bulb>switch"   a circuit loop (also resistor, ammeter, voltmeter); CI.bulb (`glow ci.bulb`)""",
    "civics": """  race "1900|1950|2000" UK:12|8|5 USA:8|14|20   bars racing through the years, re-sorting (`count rc 2000`)
  parliament A:303 B:52 C:100 [majority]   seats in a half circle by party
  market   supply and demand, where they cross; `grow mk 1` moves demand right (-1 left)
  climate J:14:20 F:17:25 ...   a month's temperature (line) and rain (bars): month:°C:mm
  chart scatter 1:2 2:3 ... | chart area K:V ...   points; a line with the ground under it filled""",
    "story": """  quiz "QUESTION?" "A" "B" "C" answer N   question, choices, then the answer shown (`in qz[0]`, the choices,
               a pause for the viewer, then the last part)
  lens "@0.6,0.4" on PIC [zoom 3]   a magnifier: a spot of a picture made bigger beside it
  split "BEFORE" "AFTER"   two halves; SP.left / SP.right are their middles (`at sp.left`)
  clock 9 (`count clk 17`: hours pass) | odometer 0 [digits 4] (`count od 1455`: digits roll)
  clipping "HEADLINE" [sub "THE TIMES"] [date "1914"]   a torn newspaper clipping
  who "NAME" sub "years" where "PLACE" [img "..."]   a person brought in: picture, name, years, place
  polaroids "SCENE" "SCENE" ...   prints dealt on the table""",
    "chart": """  chart line K:V K:V ...    a line through real values (1000:42 1300:73 1400:45); `suffix " m"`, `w`, `h`
  chart bars K:V ...        bars side by side (England:2 France:1.4); `col` upright
  chart donut K:V ...       shares of a whole; `label "WORDS"` in the middle
  chart stack K:V ...       shares in one bar  |  chart waffle K:V ...  a hundred squares shared out (died:20 lived:80)
  stat V "WHAT IT MEANS" [suffix "%"]   a big figure (`count st 20` counts it up)
  Parts: one a value (`in pop stagger .4` draws it point by point; `highlight pop[2]`).""",
    "diagram": """  flow "A>B>C" "B>D:WORDS"   a flow diagram: nodes and arrows laid out in layers (`down`: top to bottom);
               `NAME*` a key node; words after `:` go on the arrow into that node. Parts: the nodes in order,
               each with its arrows in (`in fl[0]`, `in fl[1]`...); nodes are FL.NODE (`ring fl.town`)
  pyramid "TOP" "MIDDLE" "BOTTOM"   levels top first (`inverted`); parts are levels; SOC.LEVEL
  cycle "A" "B" "C"   round a circle, each arrow on to the next; `label "WORDS"` in the middle
  tree "king>lords>knights" "lords>clergy"   a hierarchy from the top down (a flow, downward)
  venn "A" "B" [label "WHAT THEY SHARE"]   two or three overlapping circles""",
    "lists": """  compare "BEFORE" "AFTER" "a:b" "c:d"   two sides and their rows (`in cmp[1]` a row; `strike cmp.a`, `tick cmp.b`)
  table "head|head" "cell|cell" ...   rows of cells, the first the heads; cells are TBL.r1c2
  list "item" "item" ... [numbered]   items one under another (`in lst[2]` as each is named)
  steps "first" "then" "last"   numbered steps in a row""",
    "measure": """  calendar 366   days as small squares; `count cal 366` fills them (time passing)
  meter V "WORDS" [max M]   a thermometer; `grow th 3` moves it (heat, cold, prices, pressure)
  balance "LEFT" "RIGHT"   a pair of scales; `tip bal left|right|level` (more people than food...)""",
    "scene": """  backdrop "A PLACE"   a photo behind the whole shot, softened (made like a photo; `backdrop commons "..."`)
  weather snow|rain   falling over the whole shot while it is up
  portrait "NAME" [sub "years"] [img "commons:NAME portrait"]   a real person's picture and name
  bubble "WORDS" on T   a speech bubble over a person (only words the narration quotes)""",
    "paper": """  title "WORDS" [sub "a line"]   a section opening: big words on a highlighter
  quote "WORDS" [who "who said it"]   a quotation (only words the narration quotes)
  doc "TITLE" [sub "a line"] [seal]   a page of a document (a charter, a law, a letter); `stamp` it
  formula "6CO_2 + 6H_2O -> C_6H_12O_6"   a formula (_ below, ^ above, -> an arrow)""",
    "labels": """  labels "PART" "PART" ... on PIC   the parts of a pic or photo named: a dot on each, a line out to its name
               (where each part is, is found in the picture; `"PART@X,Y"`, 0..1 from its top left, says it)""",
}
KIT_WORDS = {
    "map": r"\bmaps?\b|\broute|\bregion|\bpin\b|border|empire|coast|march|migrat|globe|earth's|layers|literacy|rate in",
    "timeline": r"timeline|\byears?\b|centur|date|\bera\b",
    "chart": r"chart|graph|\bbars?\b|donut|\bshare|percent|population|rise|fall|fifth|half|quarter|million",
    "diagram": r"flow|diagram|pyramid|cycle|hierarch|rotation|chain|process|orders|tree|venn|overlap|both",
    "science": r"number line|graph of|equation|formula|triangle|angle|molecule|atom|circuit|current|solve|plot|curve",
    "civics": r"election|parliament|seats|vote|supply|demand|market|price|climate|rainfall|rain|temperature|race|rank|overtook",
    "story": r"quiz|guess|question|zoom in|detail|look closer|clock|hour|newspaper|headline|counter|who was|meet|born|photos?|split",
    "lists": r"compare|versus|\bvs\b|before|after|table|\blist|steps|stages|instead",
    "measure": r"calendar|days?\b|year and|thermomet|temperat|heat|cold|balance|scales|weigh|outgrew|faster than",
    "scene": r"backdrop|weather|snow|rain|storm|winter|portrait|king|queen|ruler|said|speech|forest|village",
    "paper": r"title|quote|saying|\bsaid\b|document|charter|\blaw\b|letter|decree|formula|equation|reaction",
    "labels": r"label|parts? of|named parts|inside",
}


def kit_for(plan: str) -> list[str]:
    """The kit cards a shot's plan asks for: its `kit:` list, and any piece its words name."""
    m = re.search(r"kit\s*:\s*([^|]*)", plan, re.I)
    named = {w.strip().lower() for w in re.split(r"[,;/ ]+", m.group(1))} if m else set()
    alias = {"flow": "diagram", "pyramid": "diagram", "cycle": "diagram", "tree": "diagram", "venn": "diagram",
             "quote": "paper", "doc": "paper", "title": "paper", "formula": "paper", "bars": "chart", "line": "chart",
             "donut": "chart", "stack": "chart", "waffle": "chart", "stat": "chart", "label": "labels",
             "compare": "lists", "table": "lists", "list": "lists", "steps": "lists", "calendar": "measure",
             "meter": "measure", "balance": "measure", "backdrop": "scene", "weather": "scene", "portrait": "scene",
             "bubble": "scene", "numberline": "science", "plot": "science", "triangle": "science",
             "molecule": "science", "equation": "science", "circuit": "science", "race": "civics",
             "parliament": "civics", "market": "civics", "climate": "civics", "scatter": "civics", "area": "civics",
             "quiz": "story", "lens": "story", "split": "story", "clock": "story", "odometer": "story",
             "clipping": "story", "who": "story", "polaroids": "story", "shade": "map", "march": "map",
             "inset": "map", "globe": "map", "layers": "map", "era": "map"}
    named = {alias.get(w, w) for w in named}
    return [k for k in KIT if k in named or re.search(KIT_WORDS[k], plan, re.I)]


STORYBOARD = """You are planning a short animated explainer. Read the narration (its words are numbered) and cut it into
SHOTS: one idea each (usually 1-2 sentences, 5-10 seconds). For each shot give one line:
SHOT name | words wA-wB | metaphor: what we SEE that makes the idea clear | things: 3-6 plain things on screen | kit: PIECES
for example:
SHOT bay | words w0-w14 | metaphor: four dark ships slide into a quiet bay | things: sea, ships, map of Japan, 1853 | kit: map
KIT (the bigger pieces a shot may use; name those it needs, or none): map (a real map: places, borders of a year,
routes), timeline (years, events), chart (line, bars, donut, stack, waffle from real numbers), stat (a big figure),
flow (how one thing leads to another), tree (a hierarchy), pyramid (ranks), cycle (a round of steps), venn (what two
share), compare (before and after, two sides), table, list, steps, calendar (time passing), meter (heat, cold,
pressure), balance (one thing outweighing another), backdrop (a place behind the shot), weather (snow, rain), portrait
(a real person), bubble (a person's quoted words), quote, doc (a charter, a law), title, formula, labels (a picture's
parts named), numberline, plot (a graph of a function), triangle, molecule, equation, circuit, race (bars racing
through years), parliament, market (supply and demand), climate, quiz (ask the viewer, then reveal), lens (a detail
magnified), split (two halves), clock, odometer, clipping (a newspaper), who (a person brought in), polaroids, shade (a
map coloured by value), march (an army or migration arrow), inset, globe, layers.
The shots cover every word, in order, without gaps.
Prefer real things (a picture of an object, a person, a building; a flag; a paper card) and things that move,
transform or count (dots for people, a bar for a gap, a map) over text. Keep continuity: a thing may carry on into the next shot."""

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
            + (f"THE SHOT BEFORE (for continuity; it is written at the same time, so make every thing you use): {before}\n"
               if before else "")
            + (f"Start with: w{words[0]['i']} cam SHOT_NAME\n" if words else "")
            + "Write the shot's lines.")
    kit = kit_for(plan)
    cards = ("\nKIT (these bigger pieces too; ent NAME PIECE ...):\n" + "\n".join(KIT[k] for k in kit)) if kit else ""
    return SCORE + "\n\n" + GRAMMAR + cards, user


REPAIR = """You fix one SHOT of an animated explainer's score. The engine built it with the real sizes of everything
(the pictures as they were made) and found the PROBLEMS below. Rewrite the shot's lines so that:
- nothing covers another unless on purpose (a label on its card, an icon on its badge, a pin on its map);
- everything stays on the screen (x from -6.6 to 6.6, y from -3.6 to 3.6), a heading clear of what is under it;
- nothing is empty (a tag with words, a timeline with its dates on it), or it is left out.
Keep the same things, the same words and the same timing; change where things are and how big. Use the REAL SIZES
to place them, or put one against another: `below X`, `above X`, `left X`, `right X` (X a thing or a part of a piece,
like `below fl.economic`; `gap G`). Answer with only the shot's lines, its `shot` line first."""


def repair_prompt(shot_text: str, problems: list[str], sizes: list[str], words: list[dict]) -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}@{w['start']:.1f}" for w in words)
    kit = kit_for(shot_text)
    cards = ("\nKIT (these bigger pieces too; ent NAME PIECE ...):\n" + "\n".join(KIT[k] for k in kit)) if kit else ""
    user = ("PROBLEMS:\n" + "\n".join(f"- {p}" for p in problems)
            + "\n\nREAL SIZES (each thing as built, in the shot's own frame):\n" + "\n".join(f"- {x}" for x in sizes)
            + (f"\n\nWORDS: {said}" if said else "") + f"\n\nTHE SHOT NOW:\n{shot_text}\n\nWrite the fixed shot's lines.")
    return REPAIR + "\n\n" + GRAMMAR + cards, user


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
