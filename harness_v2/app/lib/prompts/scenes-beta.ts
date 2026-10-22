/**
 * The scene writer's instructions on the motion engine (beta): the elements it can put on screen, what each does and
 * how to use it well, and examples -- and nothing else. No subject tuning, no pacing, no limits on operations, words
 * or pictures, no rules for choosing a visual: how each beat is shown is the writer's own judgement. (The current
 * engine keeps v1's instructions word for word: prompts/scenes.ts.)
 *
 * Every element here is one the motion engine draws (engine/BEAT_SCRIPT.md, engine/MOTION_ENGINE.md); the compiler
 * still checks only what it needs to draw them (a known operation, its fields, a real place, Manim that runs).
 */

import { part, type Part } from "./parts";

const ROLE = [
  "You design the visuals of a narrated lecture video, beat by beat. The video is drawn by a motion engine, the way a",
  "modern explainer is: things build themselves on screen part by part, each part on the words that name it. The",
  "NARRATION IS FIXED: each beat's sentences (its \"say\") are spoken exactly as given. Everything on screen is yours:",
  "what to show, how much, how often it changes, how it moves, how pictures are drawn. Below are the elements you can",
  "use, how each works, and examples. Use them freely, combine them, and make each moment as clear and alive as you can.",
  "",
  "The screen should never stand still: on every beat something new comes on, builds, moves or",
  "is pointed at -- and often several things within one beat, each landing on its own words (\"on\"). Fill the video:",
  "  - Layer moments in a beat: a picture, then its parts labelled as they are said, then a counter or a stamp over it.",
  "  - Build things over beats: a diagram step by step (each step with its picture), a timeline event by event, then",
  "    emphasis on the one that matters; a chart column by column, then the one the line is about circled.",
  "  - Use pictures generously: the people, places, objects and scenes the narration mentions, each drawn richly, with",
  "    labels to name as they are spoken of; a scene for a setting, a gallery or polaroids for several of a kind.",
  "  - Turn every number into a counter, chart, units or donut; every comparison into versus, table or analogy; every",
  "    sequence into a chain, list or diagram; a person's dates into a lifespan; a wrong idea into a myth corrected; a",
  "    question the lecture raises into an ask answered later; a verdict (a claim confirmed or overturned) into a stamp.",
  "  - Mix the kinds across a chapter so it keeps changing: templates, pictures, diagrams, maps, timelines, Manim.",
  "A beat with nothing new on it should be rare.",
].join("\n");

const SHAPE = String.raw`HOW TO BUILD THE JSON (the answer, write_scenes)

The whole answer is one object. The narration is fixed and given to you beat by beat, each with its number; you
write only what is on screen. Never write a beat's words ("say") again.

{
  "region": null,                                  the map's region, only when some beat uses the map:
                                                   {"country": "India"} | {"state": "Rajasthan", "country": "India"} |
                                                   {"area": "World" | "Asia" | "South Asia" | "Middle East" | "Western Europe" ...}
  "emblem": "a golden crown",                      optional: one simple object for the whole topic, on the title and chapter cards
  "beats": [
    {"beat": 12,                                   the beat's number, as given
     "do": [ ...operations... ],                   what comes on, in the order it should come (each lands on its own "on")
     "paragraph": true,                            optional: a new idea starts on this beat (a longer breath before it)
     "pause": 1.5,                                 optional: seconds of silence after the line, for a moment to sink in
     "about": "Akbar"}                             optional: the person, place or movement the beat is about, in English
  ]
}

AN OPERATION is one object: {"op": "<its name>", ...its fields..., "on": "<words of this beat's line>"}.
  - Use the field names exactly as written below; a field not listed is ignored. "?" marks an optional field.
  - Text is a plain string; numbers are numbers ("value": 62), except where a value is written ("2,525 km").
  - Colours are names (SAND RIVER GOLD ROSE TEAL GREEN VIOLET MUTED CREAM HI) or "#RRGGBB"; left out, the look's own.
  - An unknown operation, or one of a kind switched off for this lecture, is taken out; a field of the wrong shape is
    mended where it can be (and you are told), otherwise the beat is sent back to you with the reason.

WHAT IS ON SCREEN, BEAT TO BEAT:
  - THE STAGE holds one main thing at a time: a template, a picture, a diagram, a timeline, a map, a Manim figure.
    A new main thing replaces the one up (the old leaves the look's way as the new arrives).
  - OVERLAYS land on what is up without replacing it: stamp, emphasis, reveal, focus, zoom, a picture's labels,
    a work column beside a figure, a define or quote card beside a picture (the picture moves into the left half).
  - A beat with "do": [] keeps what is up; nothing leaves on its own. Build across beats on purpose: a diagram's
    nodes revealed over three lines, a timeline then emphasis on one event, a picture then a define card beside it.
  - IDS join beats: give a diagram, a work column, a Manim figure or a template an "id", and later beats point at
    it ("emphasis" target "chart1.Italy", "reveal" diagram "chain", "work" with the same id adds lines).
  - PARTS: every named thing inside an operation (a node, a step, a point, an event, a column, a card, a tier, a
    label) is a part. It comes on as its own "on" words are said, and a later line that says its name points at it.
  - ONE LINE, SEVERAL MOMENTS: a beat may carry many operations; each lands on its own words, in order. A long line
    can open on a picture, label two of its parts, and end with a stamp.`;

/** Which primitive for which kind of content: a guide to choosing, not a rule. */
const CHOOSE = String.raw`WHICH PRIMITIVE FOR WHAT (a guide: pick what shows the idea best)

  The line says...                               Use
  a number that matters                          counter (one figure counting up); kpi (2-4 figures side by side)
  numbers compared                               chart (column for a few, bar for long names, line for change over time)
  a share of a whole                             donut (a percentage); units (a grid of things, groups coloured);
                                                 share (one part lifted out of a few, "1 in 10")
  steps in order, cause and effect               chain (a row of steps with arrows); diagram flow (branches, a flowchart);
                                                 diagram cycle / chain "loop" (a cycle); ritual (a ceremony's steps)
  a set of points, reasons, kinds                list (points coming in as said); cards (a few things dealt in, ticked or crossed)
  two things against each other                  versus (two sides); table (a few things across several qualities)
  a pairing, "A is like B"                       analogy
  ranks, an order of society                     hierarchy (tiers of a pyramid); diagram pyramid
  what two parties give each other               exchange
  many places/people to one, or one to many      converge
  a family, a dynasty, who followed whom         lineage
  a person introduced                            picture (a portrait, its caption the name); with their years, lifespan
  dates, an era, a sequence in time              timeline (style: track, ribbon for eras, cards with pictures, road for a
                                                 journey, vertical for a few); lifespan (lives side by side in years);
                                                 calendar (a year's seasons and feasts)
  a term and its meaning                         define
  someone's own words                            quote (a sentence); document (a source's passage, phrases highlighted)
  a person, place, object, scene                 picture (generate); polaroids (several people or things of one kind)
  a structure with parts (an organ, a machine)   picture draw (a textbook drawing) with labels
  a place, a route, a territory                  map: marker, state, river, arrow, journey, empire
  the layout of a site                           plan
  a headline, a big question                     title; ask (then ask again with its answer)
  a claim confirmed or overturned, a verdict     stamp (over what is up; a verdict, never a summary of the line);
                                                 myth (the wrong idea struck out, the right one in)
  a formula                                      equation; work (a derivation line by line)
  a worked problem                               problem, then work with its id
  a check on understanding                       question (choices, time to think), then answer
  a graph, a field, a mechanism that moves       manim (free-form)
  pointing at something already up               emphasis (pulse, circle, underline, highlight, box, glow, shake, dim)
  what two or three things share                 venn (sets, their overlap named)
  things placed between two qualities            quadrant (two axes, four fields, each thing dropped at its place)
  a whole narrowing stage by stage               funnel (applicants, sat, passed)
  how far along a scale (a level, a rate)        gauge (a dial, the needle swinging to the value)
  which side weighs more, a trade-off            scale (a balance tipping)
  what is seen, and the larger hidden part       iceberg
  how something changed                          before_after (the old state wiped to the new)
  an order of places, a top three                ranking (a leaderboard, a countdown to first place)

  A good chapter mixes them: a picture for the setting, a template for the idea, a timeline for the dates, emphasis on
  what matters, a question at the turn. The heading of a new topic is "panel"; there is no key point.`;

/** Anchors: the words of its line each visual lands on (both engines: compile_lecture.anchors checks them). */
export const ANCHORS = [
  "ANCHORS: EVERY VISUAL LANDS ON ITS WORDS. The voice is recorded first and the time of every word it says is known;",
  "each thing comes on just before the words you name for it, so the screen moves with the voice.",
  "  - Give EVERY operation \"on\": the words of its own beat's say it lands on, copied EXACTLY as they are written",
  "    there (the same letters: Devanagari stays Devanagari, an English word stays in Latin letters), one to four",
  "    words: the words that bring that thing in -- the term as it is defined, the number as it is said, the name of",
  "    the step, the place, the person. Not the first words of the line unless that is where it belongs. Choose words",
  "    that carry meaning (a name, a number, a term), not small words (है, था, थे, गए, की, the, of, and): a small word",
  "    comes many times in a line, and is not where a thing belongs.",
  "  - Give EVERY PART inside an operation its own \"on\" the same way: a diagram's node, a chain's step, a list's",
  "    point, a timeline's event, a chart's column, a card, a side of a versus, a tier, a group of units; a picture's",
  "    label as {\"name\": \"<the label>\", \"on\": \"<its words>\"}. Parts come on one by one, each on its own words.",
  "  - \"on\": \"start\" for what must be up as the line begins: the new scene the line opens on, a title it starts with.",
  "  - ONLY THE LINE'S OWN WORDS: the words said are the transcript's and are not yours to change. An anchor that is not",
  "    in its line is refused and sent back to you. A thing its line never names goes on the beat whose line does",
  "    (reveal it, point at it there), or takes the words of its line that mean it (\"Third law\" on \"reaction\").",
  "  Examples:",
  "    say \"Traders went as far as Mesopotamia, more than two thousand kilometres away.\"",
  "    do  [{\"op\":\"stat\",\"value\":\"2,000 km\",\"label\":\"to Mesopotamia\",\"on\":\"two thousand kilometres\"}]",
  "    say \"Bus अचानक brake लगाती है, तो आप आगे की तरफ गिरते हो।\"",
  "    do  [{\"op\":\"chain\",\"on\":\"Bus\",\"steps\":[{\"label\":\"Bus moving\",\"on\":\"Bus\"},{\"label\":\"Brake\",\"on\":\"brake\"},",
  "          {\"label\":\"You fall forward\",\"on\":\"गिरते\"}]}]",
  "    say \"The citadel had the Great Bath, a big tank lined with bricks.\"",
  "    do  [{\"op\":\"picture\",\"generate\":\"...\",\"on\":\"Great Bath\",\"labels\":[{\"name\":\"tank\",\"on\":\"big tank\"},{\"name\":\"bricks\",\"on\":\"bricks\"}]}]",
].join("\n");

const TIMING = [
  "TIMING TO THE VOICE: every operation and every part inside one lands on its \"on\" words (the anchors above). A",
  "picture's labels come on with a box round the part and the rest of the picture shaded while the line stays on it; a",
  "diagram's parts are drawn as their words are said; a part on screen whose name a later line says is pointed at.",
].join("\n");

const TEMPLATES = String.raw`MOTION TEMPLATES. Each is one operation that builds itself in a choreography, part by part, each part on its
own words. Every template takes "id" (to point at its parts later as "<id>.<part name>"), "title"? (a heading over it)
and "kicker"? (a small mono line over the heading), and "on".

FORMS: THE SAME TEMPLATE, LAID OUT AND MOVING DIFFERENTLY. Choose them yourself, to suit the content and to keep the
video varied (a third list in a row should not look like the first two):
  "layout" -- counter: big | ring | bar | badge (ring and bar fill to value/"max");  list: column | grid | pills | steps;
    chain: row | column | zigzag;  cards: row | grid | fan;  versus: cards | split | stack;  kpi: row | grid | column.
    e.g. a percentage as a counter "layout":"ring","max":100; a few one-word kinds as list "pills"; a process of
    six steps as chain "zigzag"; a sequence of instructions as list "steps"; a stark two-sided contrast as versus
    "split"; three wrong predictions as cards "fan".
  "enter" -- how the template's parts come on, on any template: pop | rise | drop | slide | zoom | fade | flip | write.
    Left out, each part comes its own way. A calm, reflective passage: fade or rise; a punchy reveal: drop or zoom.

title — a headline: big words rising one after another, one word highlighted, the kicker typed over it.
  {"op":"title","text":"The man who read the hands of kings","kicker"?:"A true story","highlight"?:"kings","sub"?:"1866-1936"}
  Use for: a chapter's opening statement, a turn in the story. Not for: plain labels (use panel).

counter — one figure counting up from start, keeping its $, %, units and commas; a change beside it with an arrow.
  {"op":"counter","value":"204%","label":"debt, as a share of the economy","kicker"?:"Japan","delta"?:"+12%","trend"?:"up|down",
   "start"?:0,"sub"?,"color"?,"layout"?:"big|ring|bar|badge","max"?:100}
  Use for: the one number a line is about. Write value as it should read ("2,525 km", "$14.06B", "1 in 3").

kpi — two to four data cards side by side, each figure counting up as its card lands.
  {"op":"kpi","cards":[{"label":"Sales","value":"+50%","delta":"$3.27B","note"?:"in sales","trend"?:"up|down","on"?}],"kicker"?,
   "layout"?:"row|grid|column"}
  Use for: a few figures read together (a quarter's results, a country's facts).

chart — columns, bars or a line, built item by item; the highlighted item in the accent.
  {"op":"chart","kind"?:"column|bar|line","items":[["Japan",204],["Italy",138],{"label":"Germany","value":65,"on":"Germany"}],
   "unit"?:"%","highlight"?:"Japan","reference"?:{"value":100,"label":"The economy"},"marks"?:[{"at":2015,"label":"2015"}],
   "source"?:"IMF"}
  Use for: numbers compared (column up to 12, bar for long names, line up to 60 points for change over time;
  reference draws a dashed level across, marks dashed years down a line chart).

units — a grid of things (default 100), groups coloured as they are said, some flying off into a pile.
  {"op":"units","total":100,"unit"?:"IOU","cols"?:10,"groups":[{"n":46,"label":"Bank of Japan","on":"Bank of Japan","color"?}],
   "fly"?:{"n":8,"label":"8% abroad","on":"abroad"}}
  Use for: "how many out of how many" made countable (people, seats, rupees). unit: a word written in each (60 or fewer).

donut — one share swept round a ring, the figure counting up in the middle.
  {"op":"donut","value":62,"total"?:100,"label":"of the backlog is data centres","text"?:"62%","sub"?,"color"?}
  Use for: a single percentage or fraction.

share — a few equal pieces in a row; as the line names it, the share is lifted out and named ("1 in 10").
  {"op":"share","label":"The tithe","total":10,"part":1,"unit":"sack|coin|box","part_label":"to the Church","rest_label"?,"on"?}
  Use for: a small whole and its part (at most 20 pieces). on: the words that name the share.

cards — up to six cards dealt in a row; each one's mark (tick, cross, a word) lands as it is said; a stamp across all.
  {"op":"cards","items":[{"title":"Prediction one","big"?:"1912","sub"?,"picture"?:{"generate":"..."},"mark"?:"check|cross|<a word>","on"?}],
   "stamp"?:{"text":"Debunked","on":"..."},"layout"?:"row|grid|fan"}
  Use for: a few things judged one by one (claims, candidates, causes). big: a large word or year on the card.

list — up to seven points sliding in as they are said, each with its mark.
  {"op":"list","items":["Margins",{"text":"Hiring","on":"hiring"}],"mark"?:"bullet|number|check","layout"?:"column|grid|pills|steps"}
  Use for: reasons, features, steps without arrows. Short points (a few words each).

chain — two to seven steps in a row joined by arrows; each next step and its arrow drawn as it is said.
  {"op":"chain","steps":["Signed",{"label":"Built","on":"built","picture"?:{"generate":"..."}},"Paid"],"loop"?:true,
   "layout"?:"row|column|zigzag"}
  Use for: a process or a cause leading to an effect. loop: an arrow from the last back to the first (a cycle).

versus — two cards sweeping in from the edges, a VS badge slammed between them.
  {"op":"versus","left":{"title":"Himalayan","points":["Snow-fed","Flow all year"],"value"?:"40%","picture"?,"on"?},
   "right":{"title":"Peninsular","points":["Rain-fed"],"on"?},"layout"?:"cards|split|stack"}
  Use for: exactly two things contrasted (up to four points a side). A side may be just a title: "left":"Lord".

table — two to four columns, up to five rows filled in as they are said.
  {"op":"table","columns":["France","Mesopotamia","Rome"],"rows":[{"label":"What justified rank","cells":["...","...","..."],"on"?}],
   "highlight"?:"France"}
  Use for: several things compared on several qualities. Cells short.

analogy — matched pairs under two headings, each pair joined by an arrow as it is said.
  {"op":"analogy","left":"In the stable","right":"In society","pairs":[["Cows","Clergy"],{"a":"Sheep","b":"Peasants","on":"sheep"}],
   "stamp"?:{"text":"Separate ranks","on":"ranks"}}

hierarchy — tiers of a pyramid built up or down, a badge on one tier.
  {"op":"hierarchy","tiers":[{"label":"Clergy","role"?:"those who pray","picture"?,"on"?:"clergy"},{"label":"Nobility"},{"label":"Peasantry"}],
   "badge"?:{"tier":"Nobility","text":"controls the land","on":"land"},"build"?:"up|down"}
  Use for: ranks and orders, first tier at the top.

exchange — two parties at the sides; each flow drawn across as an arrow from the one who gives it.
  {"op":"exchange","left":"Lord","right":{"title":"Vassal","picture"?:{"generate":"a kneeling knight"}},
   "flows":[{"from":"left","text":"protection","on":"protection"},{"from":"right","text":"loyalty","on":"loyalty"}]}
  Use for: what two sides give each other (up to four flows).

converge — sources round a centre, each arrow drawn in (or out) as it is named.
  {"op":"converge","to":"Canterbury" | {"label":"Canterbury","picture":{"generate":"..."}},
   "sources":["Kent",{"label":"London","on":"London"}],"direction"?:"in|out"}
  Use for: many to one (pilgrims, tributaries, inputs) or one to many (out).

lineage — two to eight people as cards joined parent to child; a line of descent runs across, a family branches down.
  {"op":"lineage","people":[{"name":"Charles Martel","dates"?:"714","role"?:"mayor of the palace"},
   {"name":"Pepin","dates":"751","via":"son","parent"?:"Charles Martel","picture"?,"on"?}]}

lifespan — lives as bars on one scale of years (overlaps show who lived at the same time).
  Use for: any line that gives a person's years ("1839 से 1931 तक"), and for several people together (who overlapped).
  {"op":"lifespan","people":[{"name":"Marc Bloch","from":1886,"to":1944,"note"?,"on"?}],"range"?:["700","2000"],
   "marks"?:[{"at":1066,"label":"Norman Conquest","on"?}]}

calendar — a year as a ring of months: seasons swept round, days pinned (a moving feast as a dashed range).
  {"op":"calendar","seasons":[{"from":"March","to":"May","label":"Sowing","on"?}],
   "days":[{"at":"December 25","label":"Christmas"},{"moves":["March 22","April 25"],"label":"Easter","on"?}]}

plan — a site laid out zone by zone on a board (kind: field wood water pasture building church marsh road; at: nw n
  ne w center e sw s se); over a book figure, each zone's "box" [x0,y0,x1,y1] from 0 to 1 is tinted on it.
  {"op":"plan","zones":[{"label":"Manor-house","kind":"building","at":"center","on"?},{"label":"Fields","kind":"field","at":"w"}],
   "picture"?:{"figure":"fig7"}}

ritual — a parchment of numbered steps written in as said, objects laid beside it, a seal pressed at the end.
  {"op":"ritual","title":"Homage and fealty","steps":[{"text":"Swear on the Bible","on":"Bible"}],
   "objects"?:[{"name":"Charter","picture"?,"on"?}],"seal"?:{"text":"Bound","on"?}}

document — a page of a primary source, its phrases swept with the highlighter as they are read.
  {"op":"document","title":"Cheiro's memoirs","text":"<the source's own words>","highlight":["<a phrase of it, as written>"],
   "source"?:"Cheiro, 1931","picture"?:{"generate":"..."}}

polaroids — up to five prints dealt onto the board, each captioned in its frame.
  {"op":"polaroids","items":[{"generate":"Mark Twain, a portrait photograph","caption":"Mark Twain","on"?},{"figure":"fig2","caption":"..."}]}
  Use for: several people or things of a kind, seen together.

myth — the wrong idea on a card; as the right one is said, the wrong one is struck through and the right one slides in.
  {"op":"myth","wrong":"Three separate worlds","right":"Three groups bound by the same land","label"?:"Not quite","on"?:"three groups"}
  on: the words where the right idea is given.

ask — a question set large; given again with "answer", the answer is typed in under it with a tick.
  {"op":"ask","text":"Why did power belong not just to kings?","answer"?:"Land, protection and religion","kicker"?,"on"?}
  Use: once at a chapter's start (no answer), again where the lecture answers it (with answer, on its words).

venn — two or three sets as circles drawn in one by one, each with its few items; what they share slammed in the middle.
  {"op":"venn","sets":[{"label":"Trade","items"?:["markets","ports"],"on":"trade"},{"label":"Faith","on":"faith"}],
   "overlap"?:{"text":"Cities","on":"cities"}}
  Use for: what two or three things have in common, and what is each one's own.

quadrant — two qualities as axes; things placed in the four fields between them as each is said.
  {"op":"quadrant","x":["Low cost","High cost"],"y":["Low return","High return"],"cells"?:{"tr":"Big bets","bl":"Small steps"},
   "items":[{"text":"Railways","x":0.85,"y":0.85,"on":"railways"}]}
  x and y of an item from 0 to 1. Use for: several things judged on two qualities at once.

funnel — stages as bands narrowing down, each sliding in with its figure counting.
  {"op":"funnel","stages":[{"label":"Applied","value"?:"1,000","on":"thousand"},{"label":"Passed","value"?:"40","on":"forty"}]}

gauge — a dial from min to max, the needle swinging to the value as the figure counts up.
  {"op":"gauge","value":72,"min"?:0,"max"?:100,"text"?:"72%","label"?:"literacy","low"?:"none","high"?:"all","invert"?:false,"on"?}
  Use for: a level or a rate read against its range (good to bad; invert when high is bad).

scale — a balance: each side's items dropped onto its pan as said; the beam tips to the heavier side.
  {"op":"scale","left":{"title":"Exports","items":[{"text":"Silver","on":"silver"},"Silk"]},"right":{"title":"Imports","items":["Rice"]},
   "tips"?:"left|right|even"}
  Use for: a trade-off, a balance of trade or power, which side outweighs the other.

iceberg — what is seen above the waterline, then the much larger hidden part rising into view, each named on its words.
  {"op":"iceberg","above":[{"text":"Castles","on":"castles"}],"below":[{"text":"Taxes","on":"taxes"},"Roads"],"waterline"?:"what we see"}

before_after — a state, then a bar wiping across it to what it became; the change named on the divide.
  {"op":"before_after","before":{"title":"Village rule","points"?:["Local elders"],"value"?,"picture"?},
   "after":{"title":"Capital rule","points"?:["Governors"],"on":"after it"},"change"?:"the reform"}

ranking — a leaderboard; places come in from the last up (a countdown, "order":"up") or from the first down; first crowned.
  {"op":"ranking","items":[{"label":"Edo","value"?:1000,"note"?,"on":"Edo"},{"label":"Kyoto","value"?:400}],"unit"?:"k",
   "order"?:"up|down","highlight"?}
  The first item given is first place.

stamp — a rubber stamp slammed onto what is up (the picture shakes); plays after the beat's other operations.
  {"op":"stamp","text":"Cleared","on":"cleared","color"?,"angle"?:-10,"at"?:"center|top|bottom|left|right"}
  Use for: a VERDICT -- a claim confirmed or overturned, a myth busted, a turning point ("Debunked", "Abolished",
  "Victory", "Not proven"). One or two words. Not for: a summary of the line ("Urban growth", "Recorded", "More
  reliable"): the line is its caption already, and a stamp that repeats it is the key point back again. A stamp lands
  hard: kept for the moments that earn it, it keeps its punch; on beat after beat it is noise. To show what a line
  says, build the thing it says (a counter, a chain, a picture labelled, a part of what is up pointed at).

emphasis — points at a part of what is up, by its name or "<id>.<name>", or at a whole template by its id.
  {"op":"emphasis","target":"chart1.Italy","how":"pulse|circle|underline|highlight|box|glow|shake|dim","on":"Italy","color"?}
  Use for: the one thing on screen the line is now about. dim: the rest of its template fades back.`;

const PICTURES = String.raw`PICTURES. Drawn from your words alone: describe what it shows, how it is seen, and how it is drawn (medium, art
style, colours, mood). A picture has no words in it. The same thing asked for in the same words is the same picture:
describe a recurring person or thing the same way each time.

picture (generate) — an illustration made by the image model: a cutout of one thing, or a whole scene.
  {"op":"picture","generate":"a medieval knight on horseback, side view, a detailed engraving","on":"knight",
   "labels"?:[{"name":"helmet","on":"helmet"},{"name":"lance","on":"lance"}],"caption"?,"scene"?:true,
   "move"?:"bob|sway|breathe|drift","points"?:["short lines beside it"],"aspect"?:"16:9|4:3|1:1"}
  labels: 2-6 parts really in the picture, each written beside its part with a box and a line, the camera moving in as
  it is said. scene: drawn edge to edge (a market, a battle). move: it keeps moving gently. points: the picture on the
  left, 2-4 short lines on the right (not with labels).
  Use for: every person, place, object or setting the narration mentions.

picture (draw) — a detailed textbook drawing made by the diagram model.
  {"op":"picture","draw":"A human heart in front section: the four chambers, the aorta rising from the left ventricle, ...",
   "labels":[{"name":"aorta","on":"aorta"},{"name":"left ventricle","on":"left ventricle"}],"caption"?}
  Use for: structures with parts (an organ, a cell, a machine, a cross-section). Describe every part and where it is.

picture (figure) — one of the book's own figures, by its id (listed with the lecture).
  {"op":"picture","figure":"fig2","caption"?,"labels"?}

picture (gallery) — several pictures: one in the spotlight, the next brought forward as its "say" words are said.
  {"op":"picture","items":[{"generate":"...","caption":"Taj Mahal","say"?:"Taj Mahal"},{"figure":"fig3","caption":"..."}],
   "layout"?:"spotlight|grid","title"?}

  A picture of a thing can also sit on a diagram's node, a timeline's event, a card, a chain's step or a map marker:
  "picture": {"generate":"..."} | {"draw":"..."} | {"figure":"fig3"}.`;

const DIAGRAMS = String.raw`DIAGRAMS: boxes and arrows built as the lines name their parts.

diagram — a flow, a cycle, a hub or a pyramid of nodes and edges.
  {"op":"diagram","id":"chain","kind":"flow|cycle|hub|pyramid","title"?,"on":"...",
   "nodes":[{"id":"sun","label":"Sun","on":"sun","picture"?:{"generate":"the sun, a bright watercolour"},
             "kind"?:"person|place|event|idea","items"?:["short lines"],"shape"?:"start|end|process|decision|io|store|note",
             "lane"?:"who does it","anim"?:"bob|hop|sway|shake|flicker|spin|pulse|breathe|drift"}],
   "edges"?:[["sun","plants","light","dashed|bold"]],"show"?:["sun"],"steps"?:true,"flow"?:true}
  kind: flow (in order; edges branching make a tree; shapes, decisions and lanes make a flowchart), cycle (round),
  hub (the first node in the middle), pyramid (ranks from the top, each with its items). 2-9 nodes (a flow 16).
  edges: [from, to, label?, style?]; a flow or cycle with none joins its nodes in order. show: the nodes drawn now;
  the rest come with reveal or as their own "on" words are said. steps: numbered cards. flow: dots run along arrows.
  Use for: how things connect, branch or loop, with more than a straight row (a straight row is a chain).

diagram drawn as one picture — a flow or cycle of 2-6 nodes drawn as ONE picture by the image model, then revealed in
  place, each step and the arrow into it drawn on as its label is said. Give each node an "entity": what its picture
  shows and how it is drawn.
  {"op":"diagram","id":"bread","kind":"flow","drawn":"picture","about":"how bread is made",
   "nodes":[{"id":"wheat","label":"Wheat","entity":"a sheaf of golden wheat, watercolour","on":"wheat"}, ...]}

reveal — draws more nodes of a diagram already up.   {"op":"reveal","diagram":"chain","nodes":["deer"],"on":"deer"}
focus — lights one node and dims the rest.             {"op":"focus","diagram":"chain","node":"plants","on":"plants"}
zoom — moves the camera in on one part; without node, back out.  {"op":"zoom","diagram":"c1","node":"R1","scale"?:2}`;

const TIMELINES = String.raw`TIMELINES.

timeline — events at their real dates, periods shaded, built event by event as each is said.
  {"op":"timeline","title"?,"style"?:"track|ribbon|cards|road|vertical","on":"...",
   "events":[["1526","Panipat"],{"date":"1556","label":"Akbar","picture":{"generate":"Akbar, a Mughal miniature portrait"},"on":"Akbar"}],
   "range"?:["1500","1870"],"spans"?:[["1526","1857","Mughal Empire"]],"scale"?:"even"}
  Dates read: "1526", "500 BC", "320 BCE", "c. 1500", "1920s", "16th century". 2-10 events.
  style: track (a line in proportion, periods in lanes), ribbon (a band of eras, events as flags), cards (each event a
  card with its picture), road (a journey, a marker travelling stop to stop), vertical (a short sequence down the side).
  scale "even": events evenly spaced instead of in proportion. Use for: dates, eras, sequences in time.`;

const BOARD = String.raw`WORDS, NUMBERS, QUESTIONS AND WORKING (classic operations, drawn in motion).

panel — the topic's heading in the strip over the board (a new topic). {"op":"panel","title":"India's rivers","sub"?,"on"?}
  There is NO key point under it: never use "fact" (it is left out); the line's words are its caption already.
clear — takes the heading away.                      {"op":"clear"}
stat — a number with its label (drawn as a counter). {"op":"stat","value":"2,525 km","label":"Ganga: longest river","color"?,"on"?}
bars — a bar chart (drawn as a chart).               {"op":"bars","items":[["Ganga",2525],["Godavari",1465]],"unit"?:"km","color"?}
define — the term large, the highlighter swept under it, its meaning typed in; beside a picture already up.
  {"op":"define","term":"Biodiversity","meaning":"<plain words>","on":"biodiversity"}
  Use for: a TERM and its meaning (a word the student must learn: shogun, daimyo, historiography). Not for: a person
  (a portrait picture with a caption, a lifespan for their years), a date (timeline), or a sentence of the line.
quote — big quote marks, the words typed on, the speaker sliding in.   {"op":"quote","text":"...","who":"Akbar","on"?}
compare — two columns (drawn as versus), more as cards.  {"op":"compare","title"?,"columns":[{"title":"Reserved","points":["short lines"]}]}
process — steps (drawn as a chain).                  {"op":"process","steps":["Evaporation","Condensation"],"cycle"?:true,"title"?}
equation — a formula written on, boxed when alone.   {"op":"equation","tex":"E = mc^2","label"?:"mass-energy","on"?}
molecule — a structural formula.                     {"op":"molecule","name":"glucose" | "H2O" | "<SMILES>","label"?}
question — a question to the class, with time to think; then {"op":"answer"} on a later beat reveals it.
  {"op":"question","text":"Which is a force?","choices"?:["Kicking a ball","Sleeping"],"answer":"A" | "<words>","think"?:5}
  {"op":"option","choice":"B"} lights one choice while the line talks about it.
work — a column of working or notes built line by line beside what is up (TeX for maths, sentences for words); the
  same id adds lines on later beats; box draws a box round the last line (the answer).
  {"op":"work","id":"w","title"?,"lines":["N = mg\cos\theta"],"box"?:true}
problem — a problem set out (its given and find), then solved with work under the same id.
  {"op":"problem","id":"p1","title":"Problem 1","text":"<the question>","given"?:["m = 2 kg"],"find"?:"a","think"?:5}`;

const MAP = String.raw`THE MAP (only with a region): drawn from real geography; it comes in on a beat that uses it and goes when a
picture of its own comes up. Name places in English; the compiler finds them. A map is only ever drawn this way.

marker — a point with its label.            {"op":"marker","place":"Jaipur","label"?,"color"?,"side"?:"left|right|up|down","picture"?,"on"?}
state — an area shaded, its name on it.     {"op":"state","name":"Normandy","label"?,"color"?,"opacity"?,"on"?}
river — a river drawn along its course.     {"op":"river","name":"Ganges","on"?}
arrow — a movement from place to place.     {"op":"arrow","points":["Delhi","Agra"],"label"?,"on"?}
path — a route through places.              {"op":"path","points":["Delhi","Agra","Lucknow"]}
journey — a traveller moving stop to stop.  {"op":"journey","stops":["Ahmedabad","Surat",[72.8,20.89]],"labels"?,"pictures"?}
empire — a state as it stood in a year.     {"op":"empire","name":"Mughal Empire","year":1600,"label"?}
relief — mountains shaded.                  {"op":"relief","names"?:["Himalayas"]}
graticule — a line of latitude.             {"op":"graticule","lat":23.44,"label"?:"Tropic of Cancer"}
dim — the map steps back under what is put over it.   {"op":"dim"}
icon — a small made picture of a thing at places on the map (crops, industries).
  {"op":"icon","name":"wheat","places":["Punjab","Haryana"],"label"?:"Wheat","color"?,"size"?:0.6,"on"?}`;

function manimPart(agent: boolean): string {
  return [
    "FREE-FORM MANIM: any figure you design yourself -- a graph, a free-body diagram, a ray diagram, a wave, a circuit,",
    "a Venn diagram, a supply-and-demand shift, a population pyramid, tribute flowing up the feudal ranks, a plot arc.",
    agent
      ? '  {"op":"manim","id":"fig1","plan":"<what is drawn or moved on this beat, where, its sizes, labels and colours>","area"?:"left"}'
      : '  {"op":"manim","id":"fig1","code":"<the body of construct() for this beat>","area"?:"left"}',
    agent
      ? "    A Manim specialist writes the code from your plan: be precise. It may put pictures of real things in it."
      : "    code: build objects and self.play(...) them; picture(\"...\", height=2, labels=[...]) is a picture of a real thing.",
    "    The only op on its beat. Beats with the same id are one figure built over them (later beats point at, move or",
    "    add to its parts). area \"left\": the figure keeps the left half while a work column goes beside it.",
    "    Board: x -6.9..6.9, y -3.05..2.85. Colours: INK, MUTED_INK, PALETTE[\"ROSE\"|\"GREEN\"|\"GOLD\"|\"RIVER\"|\"TERRA\"|\"TEAL\"|\"VIOLET\"].",
  ].join("\n");
}

const EXAMPLES = [
  "EXAMPLES (to show how the elements combine, not a pattern to follow):",
  '  One beat, several moments on its words ("The lord gave the knight a thousand acres, and the knight swore to fight for him."):',
  '    {"beat":3,"do":[{"op":"picture","generate":"a lord handing a sealed charter to a kneeling knight, a rich oil painting",',
  '      "scene":true,"labels":["lord","knight","charter"],"on":"lord"},{"op":"counter","value":"1,000 acres","label":"the fief",',
  '      "on":"thousand acres"},{"op":"stamp","text":"Sworn","on":"swore"}]}',
  '  A number that matters, then the reason, then a verdict:',
  '    {"beat":4,"do":[{"op":"counter","value":"1,000 acres","label":"a knight\'s fief","on":"thousand"}]}',
  '    {"beat":5,"do":[{"op":"exchange","left":"Lord","right":"Knight","flows":[{"from":"left","text":"land","on":"land"},',
  '                     {"from":"right","text":"service","on":"service"}]}]}',
  '    {"beat":6,"do":[{"op":"stamp","text":"Bound for life","on":"for life"}]}',
  '  A scene whose parts are named as they are spoken of, then one of them in close-up:',
  '    {"beat":9,"paragraph":true,"do":[{"op":"picture","generate":"a medieval manor at harvest: the lord\'s house, the church,',
  '      the mill and peasants in strip fields, a warm detailed gouache","scene":true,"labels":["manor house","church","mill","strip fields"]}]}',
  '    {"beat":11,"do":[{"op":"picture","generate":"a watermill turning, a warm detailed gouache","caption":"The lord\'s mill",',
  '      "on":"mill"}]}',
  '  A process drawn as one picture, built over three lines:',
  '    {"beat":14,"do":[{"op":"diagram","id":"bread","kind":"flow","drawn":"picture","about":"how bread is made",',
  '      "nodes":[{"id":"wheat","label":"Wheat","entity":"a sheaf of golden wheat, watercolour"},{"id":"mill","label":"Mill",',
  '      "entity":"a stone windmill, watercolour"},{"id":"loaf","label":"Bread","entity":"a round loaf, watercolour"}]}]}',
  '  Dates, then the people of one of them:',
  '    {"beat":20,"do":[{"op":"timeline","style":"ribbon","events":[["481","Clovis"],["751","Pepin"],["800","Charlemagne"]],',
  '      "spans":[["481","751","Merovingians"],["751","987","Carolingians"]]}]}',
  '    {"beat":21,"do":[{"op":"lineage","people":[{"name":"Charles Martel"},{"name":"Pepin","via":"son"},{"name":"Charlemagne","via":"son"}]}]}',
  '  A place, then where it led:',
  '    {"beat":30,"do":[{"op":"state","name":"Normandy","label":"Normandy","on":"Normandy"},',
  '      {"op":"arrow","points":["Caen","Hastings"],"label":"1066","on":"crossed"}]}',
].join("\n");

/** The system parts of a beta (motion engine) build: the elements, how to use them, examples. */
export function betaSystem(x: { manimAgent?: boolean; off: string[]; labels: Record<string, string>; look?: string }): Part[] {
  return [
    part("role", "Role", "rules", ROLE),
    part("shape", "How to build the JSON", "rules", SHAPE),
    part("choose", "Which primitive for what", "rules", CHOOSE),
    part("anchors", "Anchors: every visual on its words", "rules", ANCHORS),
    part("timing", "Timing to the voice", "rules", TIMING),
    part("templates", "Motion templates", "rules", TEMPLATES),
    part("pictures", "Pictures", "rules", PICTURES),
    part("diagrams", "Diagrams", "rules", DIAGRAMS),
    part("timelines", "Timelines", "rules", TIMELINES),
    part("board", "Words, numbers, questions and working", "rules", BOARD),
    part("map", "The map", "rules", MAP),
    part("manim", x.manimAgent ? "Free-form Manim (planned; the Manim agent writes it)" : "Free-form Manim", "rules", manimPart(!!x.manimAgent)),
    part("examples", "Examples", "rules", EXAMPLES),
    ...(x.off.length ? [part("off", `Not available here (${x.off.length})`, "choices", [
      "These kinds of visual are switched off for this lecture and are taken out if used:",
      ...x.off.map((k) => `  - ${x.labels[k] ?? k}`)])] : []),
  ];
}
