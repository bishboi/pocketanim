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
  KINDS: text "WORDS" | circle | rect | blob | ring | waves N | dots N (`shape user`: little drawn people) | num V
         | bar V | arrow A B | path P P P...
         | pic "WHAT" (a small hand-drawn picture, cut out on paper: ONE object, person or building; 1-3 a shot;
           there are no icons: a small thing is a pic)
         | photo "A SCENE" (a framed print of a place or scene). Say exactly what to draw, of its time and place:
           pic "a 14th-century English silver penny, worn, both faces stamped" not pic "a coin"; photo "a muddy
           medieval village street at dawn, timber houses, a church tower behind" not photo "a village". No words in it.
         | flag CODE (jp us in gb fr de cn...) | card "TITLE" [flag CODE] [img "WHAT"] [sub "a line"] (a paper card)
         | tag "WORDS" (bold words on the accent colour: the key number or claim) | label "WORDS" (small spaced
           capitals: a heading over something, a caption, a source)
         | phrase "KEY WORDS" [w W] (a key phrase the voice says: `wA-wB in P speak` puts each word on as it is said)
         | note "WORDS" [to T] (a handwritten note in the margin, a curved arrow to T; `/` breaks its line: an aside,
           a correction, "← not this one!")
  MODS: at X,Y | at NAME.PLACE (a place on a map, a year on a timeline; a picture at a flow's node goes beside it) |
        below X | above X | left X | right X (against X's edge, `gap G`; X a thing or a part: below fl.town) | size S | color C | fill C | bold | x N (N copies) with
        row|col|grid C|ring R and gap G | on PATH (copies spread along it) | nudge X,Y | layer N | rot DEG |
        w W h H r R | max M | suffix "..." prefix "..." | dashed | curve C | grid C | cluster
  COLORS: ink navy coral teal gold green sky soft sand red white
TIME VERB TARGET [ARGS]       an action. TIME: wN (as word N is said), wN-wM (over those words), wN+0.4, tSECONDS, end
  in T [fade|pop|rise|drop|slide-left|slide-right|draw|write|grow|unfold|slap|speak] [stagger S]
        (with no way said, a pic, photo, card, tag or quote is slapped down like a sticker; the rest fades)
  out T [fade|shrink|drop|peel] [stagger S]   (with no way said, a cut-out is peeled off and flicked away)
  move T to X,Y | to ENT | by DX,DY [arc A] [stagger S]
  along T PATH | flow PATH n N COLOR | float T AMP
  travel T PATH (a ship, cart, train or rider along a route: it turns to face its way, tilts with the slope, bobs,
        and the route is drawn behind it as dashes; `face left` on its ent if its picture faces left)
  morph A B [stagger S] (A becomes B; B never shown before)
  count NUM V | grow BAR V | color T C | dim T O | lift T | scale T K | spin T DEG | pulse T | shake T
  MARKS (stay until the thing goes): ring T C | underline T | highlight T | strike T | box T | tick T | cross T |
        stamp T "WORDS" | callout T "WORDS" [left|right|up|down] | bracket A,B,C "WORDS" | spotlight T (all else
        veiled; `lift X` brings one back)
  pan PHOTO [zoom K] (a slow push into a still) | type T (letter by letter) | fill SHAPE 60 C (fills like water)
  connect A B "WORDS" (an arrow drawn between them) | follow T [zoom Z] (the camera keeps a moving thing in view)
  react T idea|question|exclaim|shock|love|zzz|anger|sweat|sparkle (a doodle pops over its head, then goes: a
  person's or anything's reaction, on the word that causes it)
  glow T C (a soft light behind it) | era MAP YEAR (its borders change to that year's) | tip BALANCE left|right
  cam SHOT | cam SHOT X,Y zoom Z | cam ENT zoom Z | cam wide | cam SHOT via page|tear|whip (a page turned, torn
  paper, a fast swing: for a change of chapter) | cam SHOT via dive into M.place (into a pin or a picture, which
  opens on the next shot)
  bring T to SHOT [X,Y] (at the camera's move: T rides along into the next shot and stays; one thread carried on)
  chapter "TITLE" (on a chapter's first word: the bar along the bottom names it; 3-6 a short video, one every few
  minutes of a long one; when the plan says `chapter: TITLE`, on the shot's first word)
TARGET: NAME, NAME[2], NAME[0:3], A,B,C, or a named part of a piece (soc.nobles, fl.market).
RULES
- Every action is one line that starts with its time, then the verb, then the thing: `w12 in seal pop`,
  `w14-w18 move ship to 3,0`, `w20 out seal`, `w21 ring seal`, `w22-w26 in key speak`. One action a line; the only
  verbs are those above (no `appear`, `fade in`, `show`); a thing is made by an `ent` line before it is used.
- Nothing is a slide: keep things up and change them (move, morph, count, grow, color) instead of replacing them.
- Something moves on every phrase; land each action on the word that names it.
- Start every shot with `cam SHOT` on its first word: the camera only goes where a `cam` line sends it.
- A name is one thing for the whole video: a thing from the shot before is used by its name (no new `ent` line for
  it); a new thing gets a new name.
- Lay things apart on the screen (x from -6 to 6, y from -3.4 to 3.4; side by side at least 3 apart). Overlap only
  to put one on another on purpose (a label on its card, a pin on its map).
- Show real things: a pic, a photo, a flag or a card. No icons. One big picture per idea; few small pics.
- A thing on a map is at a place on it (MAP.place); a place beyond the map's region is drawn at its edge: choose
  a region that holds every place you name.
- Words on screen: a tag for the key number, a label for a heading; never sentences (the voice says them).
- Use few kinds; get life from actions: stagger, arcs, morphs, flows, the camera.
- Keep text short (1-4 words). The narration says the sentences; a `phrase` spoken word by word is the exception
  (one a shot at most, the key line). A `num` put `in` on the word that says it counts up as it is said."""

# The bigger pieces, each told to a shot's call only when its plan asks for it (the storyboard names them), so the
# card a small model reads stays short. Each is one `ent` placed freely; its parts come on by the actions.
KIT = {
    "map": """  map REGION   a real, accurate map: europe, british isles, mediterranean, middle east, india, china, world...,
               a country's name, or "LON0,LAT0,LON1,LAT1"; `year Y` draws the states of that time; `names`, `rivers`,
               `compass`, `scale` (a scale bar); it comes in an atlas frame (`frame plain` for a bare one; `full`:
               the whole screen, edge to edge, for a shot that is all map: put pins, people, arrows on it);
               `w 12 h 6.6` (it fills that). Every place on it is MAP.PLACE: eu.paris, eu.constantinople, eu.north_sea
  region "NAME" on M   a country, a state of the map's year ("Holy Roman Empire") or a sea, shaded where it really
               is; `color`, `opacity`, `outline`
  pin "PLACE" on M     a town marked, its name beside (`side left`)  |  river "NAME" on M
  shade "WHAT" on M K:V ...   countries coloured by a value, with a key (a choropleth)
  march M.a M.b M.c [width W]   a thick arrow swelling along a route (armies, migrations, trade winds)
  annex A B    B goes over to A (a war won, a land annexed, a vote flipped): B takes A's colour, its border flares;
               A and B regions (or B a region not yet shown: it comes on in A's colour). A front line that moves:
               two paths, then `morph LINE1 LINE2`
  travel SHIP ROUTE   along a route, turning, tilting, its dashed track drawn behind it (`ent route path M.a M.b M.c`)
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
  isotype N "WHAT" [per K] [shape person|coin|book|house|box|drop|tree|bread] [cols C] [lit L] [img "..."]
            a picture row: N/K little figures in rows, the first L lit in the accent colour, a key "= K WHAT"
            under them ("1 in 4 could read": isotype 4 "people" lit 1; `in iso stagger .05` one by one)
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
    "people": """  person [wear shirt|tunic|robe|habit|dress|gown|coat|suit|armor|apron|toga|uniform|lab|overalls|vest]
               [hat top|bowler|cap|beret|straw|cowboy|crown|helmet|tricorn|mitre|turban|hood|veil|chef|hardhat|wreath|
               headscarf] [hair short|long|bob|bun|ponytail|curly|spiky|bald(-black|brown|blonde|red|grey|white)]
               [beard|longbeard] [mustache] [skin fair|light|tan|brown|dark]
               [mood FACE] [stubble]
               [tool book|scroll|quill|coin|bag|sword|shield|staff|spear|flag|sign|hammer|pickaxe|torch|lantern|basket|
               cane|pointer|briefcase] [color C] [seat] [old] [kid] [face left] [size H]
               a little drawn figure, dressed for who they are (a monk: wear habit hat hood; a king: wear gown hat
               crown; a merchant: wear coat hat top tool bag), standing with its feet at its place
  walk P to X,Y|ENT|M.place | run P to ... | point P at T | wave P | talk P "WORDS" (mouth moves; a bubble only
  for words the narration quotes) | carry P THING (it goes into the hands) | sit P | stand P | turn P left|right
  | cheer P | shrug P | think P | bow P | jump P | nod P | dance P | clap P | facepalm P | laugh P | cry P | shiver P
  | kick P | look P at T | faint P (falls flat; `stand P` gets it up) | hug P OTHER
  TWO AT ONCE: give A B THING (handed over; it stays in B's hands) | throw A B THING (flies in an arc, caught)
  | shake A B (a handshake: a deal, a treaty) | push A B (shoved aside) | tug A B [THING] (a tug of war, a rope
  between them: two sides wanting one thing) | argue A B "WORDS" "WORDS" ... (turn by turn, angry bubbles)
  | whisper A B "WORDS" (a hand to the mouth, B surprised). A walks up to B first when they stand apart.
  | emote P FACE (the face turns into another and stays;
  `mood FACE` on the ent line is how it looks to begin with). FACES: happy calm joy laugh excited playful proud smug
  cool sad crying angry furious annoyed suspicious surprised shocked scared worried nervous embarrassed confused
  think dazed pained sleepy disgusted. Faces carry the story: emote on the word that turns the feeling.
  People act out what the voice says: 1-3 a shot, feet at y about -2.9, at least 2 apart. Never put a person at
  a map's place (they stand taller than a country): mark places on maps with pins.
  nation NAME [year Y] [color C] [mood FACE] [named] [size H] [face left]   a COUNTRY AS A CHARACTER: its real shape
               for a body, stick legs and arms, a face; every verb above works (walk, talk, point, emote, shiver,
               hug...). For history told as countries' relations (a big power leaning on a small one, two rivals
               squabbling, an ally's hug): 2-4 a shot, sized by their importance (size 1.2-3.4), feet at y about -2.6.
  pic "WHAT" alive [mood FACE] [size H]   A THING COME ALIVE: the picture with a face, stick legs and arms; every
               verb above works (a coin that walks off, a lock that crosses its arms, a book that cries); feet at y
               about -2.6. One a shot, for the idea the story turns on.
  react P idea|question|exclaim|shock|love|zzz|anger|sweat|sparkle   a doodle over the head: a feeling at a glance""",
    "labels": """  labels "PART" "PART" ... on PIC   the parts of a pic or photo named: a dot on each, a line out to its name
               (where each part is, is found in the picture; `"PART@X,Y"`, 0..1 from its top left, says it)""",
}
KIT_WORDS = {
    "map": r"\bmaps?\b|\broute|\bregion|\bpin\b|border|empire|coast|march|migrat|globe|earth's|layers|literacy|rate in|"
           r"annex|conquer|seiz|sail|voyage|front line|province|territor",
    "timeline": r"timeline|\byears?\b|centur|date|\bera\b",
    "chart": r"chart|graph|\bbars?\b|donut|\bshare|percent|population|rise|fall|fifth|half|quarter|million|"
             r"isotype|out of|in every|\bone in\b|thousand",
    "diagram": r"flow|diagram|pyramid|cycle|hierarch|rotation|chain|process|orders|tree|venn|overlap|both",
    "science": r"number line|graph of|equation|formula|triangle|angle|molecule|atom|circuit|current|solve|plot|curve",
    "civics": r"election|parliament|seats|vote|supply|demand|market|price|climate|rainfall|rain|temperature|race|rank|overtook",
    "story": r"quiz|guess|question|zoom in|detail|look closer|clock|hour|newspaper|headline|counter|who was|meet|born|photos?|split",
    "lists": r"compare|versus|\bvs\b|before|after|table|\blist|steps|stages|instead",
    "measure": r"calendar|days?\b|year and|thermomet|temperat|heat|cold|balance|scales|weigh|outgrew|faster than",
    "scene": r"backdrop|weather|snow|rain|storm|winter|portrait|king|queen|ruler|said|speech|forest|village",
    "paper": r"title|quote|saying|\bsaid\b|document|charter|\blaw\b|letter|decree|formula|equation|reaction",
    "labels": r"label|parts? of|named parts|inside",
    "people": r"\bperson|people|\bm[ae]n\b|wom[ae]n|merchant|monk|farmer|worker|soldier|travell?er|\bwalk|"
              r"carr(y|ied)|pointed|buyer|seller|peasant|crowd|alliance|allies|\brival|treaty|neighbou?r|invad|"
              r"annex|bull(y|ied)|nation|\bga(ve|ive)\b|thr(ew|ow)|argu|quarrel|whisper|handshake|shook hands|"
              r"deal\b|push|tug|alive|character",
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
             "inset": "map", "globe": "map", "layers": "map", "era": "map", "annex": "map", "travel": "map",
             "isotype": "chart", "alive": "people", "react": "people", "person": "people", "walk": "people", "nation": "people", "country": "people",
             "figure": "people"}
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
map coloured by value), march (an army or migration arrow), inset, globe, layers, annex (land changing hands),
travel (a ship, cart or train along a route), isotype (a picture row: "1 in 4"), people (stick figures who walk,
point, talk, carry things, give, argue, shake hands: acting out what is said; countries as characters; a thing come
alive with a face and legs).
The shots cover every word, in order, without gaps.
Prefer real things (a picture of an object, a person, a building; a flag; a paper card) and things that move,
transform or count (dots for people, a bar for a gap, a map) over text. Keep continuity: a thing may carry on into the next shot.
After the shots, give each CHARACTER seen in two or more shots (a person, a country as a character, a thing come alive)
one line, so it looks the same every time:
cast NAME person [wear W] [hat H] [hair H] [beard] [tool T] [mood FACE]   (wear habit|gown|coat|suit|armor|tunic...)
cast NAME nation COUNTRY [color C] [mood FACE] [named]
cast NAME pic "WHAT, as a cut-out" alive [mood FACE]   (an object with a face, legs and arms)
for example: cast monk person wear habit hat hood longbeard mood calm"""

SCORE = """You write one SHOT of an animated explainer's score, in the grammar below. You get the shot's plan, its
narration with every word numbered and timed, and what the shot before left up. Answer with only the shot's
lines: its `shot` line, its `ent` lines, then its actions in time order."""


# The language a video is told in, said to every call that writes it (English needs no note).
LANG = {
    "hinglish": """
THE NARRATION IS IN HINGLISH: everyday Hindi in Roman letters, with English words where people naturally use them
("Socho, 1440 mein ek kitaab banane mein mahine lagte the."). Plans, and the words a picture is made from (pic,
photo, backdrop, img), stay in English: the image model reads English. Words ON THE SCREEN (tag, label, card, title,
note, bubble, callout, stamp) are short and read as an Indian viewer reads them: the narration's own Hinglish words or
plain English terms, in Roman letters (never Devanagari). A `phrase` uses the narration's exact words.""",
}
SCRIPT_LANG = {
    "hinglish": """
WRITE IN HINGLISH, as a popular Indian YouTube explainer speaks: everyday Hindi in Roman letters (never Devanagari),
mixing in English words where people naturally use them (technical terms, names, many nouns), e.g. "Socho, 1440 mein
ek kitaab banane mein mahine lagte the. Ek monk, ek candle, aur bas." Simple common spellings (hai, mein, kya, nahi,
bahut, kyunki, lekin, aur); numbers as digits; friendly and direct ("dekho", "socho", "aapko pata hai?"). The VIDEO
titles in Hinglish too.""",
}


def with_language(system: str, language: str | None) -> str:
    return system + LANG.get(language or "en", "")


def storyboard_prompt(words: list[dict], part: dict | None = None, cast: list[str] | None = None,
                      before: str = "", language: str | None = None) -> tuple[str, str]:
    """The storyboard call: the whole narration, or (a long video) one part of it, told where it stands, what came
    just before, and the cast already made for the whole video."""
    said = " ".join(f"w{w['i']}:{w['w']}" for w in words)
    if not part:
        return with_language(STORYBOARD, language), f"NARRATION: {said}\n\nWrite the shots, one line each, then the cast lines (if any)."
    user = (f"This is PART {part['k'] + 1} of {part['n']} of a long video (about {part['minutes']:.0f} minutes in all; "
            f"this part about {part['seconds'] / 60:.1f} minutes). Storyboard only this part's words, w{words[0]['i']} "
            f"to w{words[-1]['i']}, every one of them.\n"
            + (f"JUST BEFORE THIS PART, THE VOICE SAID: \"{before}\"\n" if before else "")
            + ("THE CAST (made once for the whole video: use these characters by name in the plans; write no cast "
               "lines):\n" + "\n".join(cast) + "\n" if cast else "")
            + "When this part opens a new chapter of the story, its first shot's plan says `chapter: TITLE`.\n"
            + f"NARRATION: {said}\n\nWrite this part's shots, one line each.")
    return with_language(STORYBOARD, language), user


CAST = """You plan the recurring characters of a long animated explainer. Read the whole narration and list each
character who comes back again and again (a person, a country acting as a character, an object that comes alive), so
it looks the same every time. One line each, nothing else:
cast NAME person [wear habit|gown|coat|suit|armor|tunic|robe|dress|uniform|lab|apron|toga|shirt] [hat H] [hair H]
     [beard|longbeard] [mustache] [skin fair|light|tan|brown|dark] [tool T] [old|kid] [mood FACE]
cast NAME nation COUNTRY [color C] [mood FACE] [named]
cast NAME pic "WHAT, a cut-out object" alive [mood FACE]
NAME is one short lowercase word (gutenberg, monk, prussia, coin). At most 8 characters; none at all is fine
(answer `none`)."""


def cast_prompt(words: list[dict], language: str | None = None) -> tuple[str, str]:
    said = " ".join(w["w"] for w in words)
    return with_language(CAST, language), f"NARRATION: {said}\n\nWrite the cast lines."


CAST_LINE = re.compile(r"^[\s*>\-`]*(cast\s+[A-Za-z_]\w*\s+(?:person|nation|country|pic)\b.*?)[`\s]*$", re.I)


def parse_cast(text: str) -> list[str]:
    """The storyboard's `cast` lines (a character made once for the whole video), each a line of the score."""
    out, seen = [], set()
    for line in text.splitlines():
        m = CAST_LINE.match(line.strip().replace("**", ""))
        if m:
            ln = re.sub(r"^cast", "cast", m.group(1), flags=re.I)
            name = ln.split()[1].lower()
            if name not in seen:
                seen.add(name)
                out.append(re.sub(r"^(cast\s+)(\S+)", lambda x: x.group(1) + x.group(2).lower(), ln))
    return out


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


def _cast_card(cast: list[str] | None) -> str:
    if not cast:
        return ""
    return ("CAST (characters made once for the whole video; none needs its own look again: put one in this shot "
            "with `ent NAME at X,Y` and its name, e.g. `ent " + cast[0].split()[1] + " at -3,-2.6`, then `in` it; "
            "`mood FACE` on that line changes its face):\n" + "\n".join(cast) + "\n")


def score_prompt(plan: str, words: list[dict], shot_at: tuple[float, float], before: str = "",
                 cast: list[str] | None = None, language: str | None = None) -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}@{w['start']:.1f}" for w in words)
    user = (f"SHOT PLAN: {plan}\nPLACE IT: at {shot_at[0]:g},{shot_at[1]:g}\nWORDS: {said}\n" + _cast_card(cast)
            + (f"THE SHOT BEFORE (for continuity; it is written at the same time, so make every thing you use): {before}\n"
               if before else "")
            + (f"Start with: w{words[0]['i']} cam SHOT_NAME\n" if words else "")
            + "Write the shot's lines.")
    kit = kit_for(plan)
    cards = ("\nKIT (these bigger pieces too; ent NAME PIECE ...):\n" + "\n".join(KIT[k] for k in kit)) if kit else ""
    return with_language(SCORE + "\n\n" + GRAMMAR + cards, language), user


REPAIR = """You fix one SHOT of an animated explainer's score. The engine built it with the real sizes of everything
(the pictures as they were made) and found the PROBLEMS below. Rewrite the shot's lines so that:
- nothing covers another unless on purpose (a label on its card, a pin on its map);
- everything stays on the screen (x from -6.6 to 6.6, y from -3.6 to 3.6), a heading clear of what is under it;
- nothing is empty (a tag with words, a timeline with its dates on it), or it is left out.
Keep the same things, the same words and the same timing; change where things are and how big. Use the REAL SIZES
to place them, or put one against another: `below X`, `above X`, `left X`, `right X` (X a thing or a part of a piece,
like `below fl.economic`; `gap G`). Answer with only the shot's lines, its `shot` line first.
Things set wholly on a bigger thing on purpose (pins and pictures on a map, letters in a tray, a coin in a hand, words
on a card) are not reported and stay as they are: move only what the problems name."""


def repair_prompt(shot_text: str, problems: list[str], sizes: list[str], words: list[dict],
                  cast: list[str] | None = None, language: str | None = None) -> tuple[str, str]:
    said = " ".join(f"w{w['i']}:{w['w']}@{w['start']:.1f}" for w in words)
    kit = kit_for(shot_text)
    cards = ("\nKIT (these bigger pieces too; ent NAME PIECE ...):\n" + "\n".join(KIT[k] for k in kit)) if kit else ""
    user = ("PROBLEMS:\n" + "\n".join(f"- {p}" for p in problems)
            + "\n\nREAL SIZES (each thing as built, in the shot's own frame):\n" + "\n".join(f"- {x}" for x in sizes)
            + (f"\n\nWORDS: {said}" if said else "") + ("\n\n" + _cast_card(cast) if cast else "")
            + f"\n\nTHE SHOT NOW:\n{shot_text}\n\nWrite the fixed shot's lines.")
    return with_language(REPAIR + "\n\n" + GRAMMAR + cards, language), user


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


LONG = """
A LONG VIDEO (this one runs MINUTES minutes): tell it as a documentary in CHAPTERS, not as one long lesson.
- Open with a hook in the first 20 seconds: a scene, a puzzle or a surprising number, and the big question.
- 5-10 chapters of 2-4 minutes, each with its own small question, built on the one before. Start each chapter with
  a line that names where we are going ("Now, the money."), so the viewer always knows.
- A few recurring characters (people, a country, an object) carry the story from chapter to chapter: name them the
  same way every time.
- Every 3-4 minutes, one sentence that sums up what we have so far, then a turn ("But that raised a new problem.").
- Vary the pace: a stretch of story, then a number made tangible, then a comparison, then story again. Never more
  than four sentences in a row of abstract explanation.
- End on the answer to the opening question and one line that looks forward."""


def script_prompt(pages: str, videos: int, seconds: int, notes: str = "", language: str | None = None) -> tuple[str, str]:
    words = f"{int(seconds * 2.2)}-{int(seconds * 2.7)}"
    system = SCRIPT.replace("SECONDS", str(seconds)).replace("WORDS", words)
    if seconds >= 300:                          # minutes, not seconds: a long video has chapters (runs.py parts)
        system += LONG.replace("MINUTES", f"{seconds / 60:.0f}")
    system += SCRIPT_LANG.get(language or "en", "")
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
