/**
 * The templates as the scene writer and the director are told them (engine/MOTION_ENGINE.md §3): each template, its
 * fields, its forms and entrances, and how to choose how things move; and the anchors (every visual on its words).
 * Told when the "templates" kind is on (prompts/scenes.ts).
 */

/** Anchors: the words of its line each visual lands on (compile_lecture.anchors checks them). */
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

export const TEMPLATES_TEXT = String.raw`TEMPLATES. Each is one operation that builds itself in a choreography, part by part, each part on its
own words. Every template takes "id" (to point at its parts later as "<id>.<part name>"), "title"? (a heading over it)
and "kicker"? (a small mono line over the heading), and "on".

FORMS: THE SAME TEMPLATE, LAID OUT AND MOVING DIFFERENTLY. Choose them yourself, to suit the content and to keep the
video varied (a third list in a row should not look like the first two):
  "layout" -- counter: big | ring | bar | badge (ring and bar fill to value/"max");  list: column | grid | pills | steps;
    chain: row | column | zigzag;  cards: row | grid | fan;  versus: cards | split | stack;  kpi: row | grid | column.
    e.g. a percentage as a counter "layout":"ring","max":100; a few one-word kinds as list "pills"; a process of
    six steps as chain "zigzag"; a sequence of instructions as list "steps"; a stark two-sided contrast as versus
    "split"; three wrong predictions as cards "fan".
  "enter" -- how the template's parts come on, on any template (see MOVING WITH INTENT for when to use which):
    pop | rise | drop | slide | zoom | fade | flip | write | unfold | typewrite | ink | stamp | spin | iris.
    Left out, each part comes its own way. A calm, reflective passage: fade, rise or ink; a punchy reveal: drop, zoom,
    stamp or iris; a document or a record: typewrite or unfold.

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
  The left side comes on with the template; the right sweeps in (and the VS slams down) on its own "on", so give the
  right side the words where the line turns to it. A point may be {"text":"...","on":"..."} to come on as said.

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

HISTORY AND STORYTELLING:

cause_web — the event on the right; its causes slide in on the left, each joined by an arrow as thick as its weight.
  {"op":"cause_web","effect":{"text":"The revolt","on"?:"revolt"},"causes":[{"text":"Debt","weight":3,"on":"debt"},
   {"text":"Drought","weight":2,"on":"drought"},{"text":"A weak king","weight":1,"on":"weak king"}]}
  Use for: "why did it happen" with two to six causes. weight 1-3: how much each mattered (the line's own emphasis).

portrait_card — a person as a trading card turned in: picture, name banner, dates, role; facts dealt beside it.
  {"op":"portrait_card","name":"Tokugawa Ieyasu","dates"?:"1543 - 1616","role"?:"First shogun",
   "picture":{"generate":"Tokugawa Ieyasu, an Edo-period ink portrait, seated in court robes"},
   "facts"?:[{"text":"Founded the shogunate","on":"founded"},{"text":"Moved power to Edo","on":"Edo"}]}
  Use for: the first time a key person comes in (up to three facts). Later mentions: a picture or emphasis.

source_vs_reality — a source's claim quoted on a page; what the evidence shows slides in beside it; a verdict stamped.
  {"op":"source_vs_reality","source":{"text":"The city burned for a month","by"?:"A court chronicle"},
   "reality":{"text":"Records show the fire lasted three days","on":"in fact"},"verdict"?:"Exaggerated"}
  Use for: historiography -- what a chronicle, a legend or a propagandist said, set against what is known.

population_pyramid — age groups as bars both ways from a spine, growing out from the youngest up.
  {"op":"population_pyramid","unit"?:"% of people","left_label"?:"Men","right_label"?:"Women",
   "groups":[{"label":"60+","left":3,"right":4},{"label":"20-59","left":20,"right":21},{"label":"0-19","left":24,"right":23}]}
  groups: the oldest first (2-10). Use for: a society's shape by age (young, ageing, a lost generation).

migration_flow — regions as discs; each flow an arc as wide as the number who moved, drawn as it is said.
  {"op":"migration_flow","regions":["Villages","Edo","Osaka"],"unit"?:"people",
   "flows":[{"from":"Villages","to":"Edo","value":5000,"on":"Edo"},{"from":"Edo","to":"Osaka","value":1200,"label"?:"1,200","on":"Osaka"}]}
  Use for: who moved where and how many, between groups or regions (no map needed). For a route on a map: map_story.

quote_reveal — a famous line set large in a serif, its words lighting up one by one as it is spoken; the speaker beside.
  {"op":"quote_reveal","text":"The strong do what they can, and the weak suffer what they must.","who":"Thucydides",
   "highlight"?:["strong","weak"],"picture"?:{"generate":"a marble bust of Thucydides, soft museum light"}}
  Use for: a sentence worth hearing whole (a motto, a famous line). text: the words as the narration says them.

newspaper — a front page spun onto the board: masthead, date, the headline slammed on, a sub-headline, a picture.
  {"op":"newspaper","paper":"The Edo Herald","date"?:"8 July 1853","headline":"Black ships in the bay",
   "sub"?:"American warships anchor off Uraga","picture"?:{"generate":"black steam warships in a bay, an old engraving"}}
  Use for: the moment news broke (a war declared, a treaty signed, a discovery). Headline short (2-6 words).

letter — a letter on a sheet, its words written on in a hand as the line reads them, signed at the end.
  {"op":"letter","to"?:"Mother","date"?:"1853","text":"The ships are here. Nobody knows what they want.","sign"?:"Kenji"}
  Use for: a private voice -- a letter, a diary entry, a soldier's note. Short (one to three sentences).

countdown — a big flip display: each year or count flips in over the last as said; then the event lands with a thud.
  {"op":"countdown","steps":[{"text":"1850","on":"Eighteen fifty"},{"text":"1852","on":"fifty two"},{"text":"1853","on":"fifty three"}],
   "event":{"text":"The ships arrive","on":"ships arrived"}}
  Use for: tension before a turning point; years leading to a war, days to a deadline (2-6 steps).

NUMBERS AND EXPLANATIONS:

race_bars — bars for each rival at each date; at each next date the bars stretch and re-sort, the date rolling over.
  {"op":"race_bars","unit"?:"k","frames":[{"at":"1700","values":{"Edo":300,"Kyoto":350,"Osaka":280}},
   {"at":"1750","values":{"Edo":800,"Kyoto":380,"Osaka":320},"on":"1750"},{"at":"1800","values":{"Edo":1100,"Kyoto":370,"Osaka":380},"on":"1800"}]}
  Use for: who led when, and who overtook whom (2-8 dates, the same names in each). The first frame is drawn at once.

waterfall — a start, then each gain stepping up in green and each loss down in red, then the total.
  {"op":"waterfall","start":{"label":"Revenue","value":100},"steps":[{"label":"Taxes","value":40,"on":"taxes"},
   {"label":"Wars","value":-60,"on":"wars"}],"total"?:"Left","unit"?:"m"}
  Use for: how a budget, a population or an army got from one figure to another. value: +n gained, -n lost.

stacked_area — shares of a whole stacked over years, each layer swept in as it is named.
  {"op":"stacked_area","years":[1700,1750,1800,1850],"series":[{"label":"Farming","values":[70,62,55,45]},
   {"label":"Crafts","values":[20,24,27,30],"on":"crafts"},{"label":"Trade","values":[10,14,18,25],"on":"trade"}],"unit"?:"%"}
  Use for: a mix changing over time (jobs, faiths, sources of income). One value per year in each series.

slope — then and now on two posts; each thing a line rising (green) or falling (red), drawn as it is said.
  {"op":"slope","left_label":"1700","right_label":"1800","items":[{"label":"Rice","from":40,"to":90,"on":"rice"},
   {"label":"Silk","from":80,"to":50,"on":"silk"}],"unit"?}
  Use for: what rose and what fell between two moments (up to seven things).

dot_compare — grids of dots side by side, each one's share filling in as it is said, "1 in 4" under it.
  {"op":"dot_compare","groups":[{"label":"Towns","part":25,"total":100,"text"?:"1 in 4","on":"towns"},
   {"label":"Villages","part":5,"total":100,"text"?:"1 in 20","on":"villages"}]}
  Use for: rates compared so they are felt (literacy, deaths, voters). 2-4 groups; total 100 or less.

split_number — a big total over a bar; the bar breaks into its parts, each block sized to its share.
  {"op":"split_number","value":"3,000,000","label"?:"koku of revenue","parts":[{"label":"Rice","value":2000000,"on":"rice"},
   {"label":"Silk","value":600000,"on":"silk"},{"label":"Salt","value":400000,"on":"salt"}],"unit"?}
  Use for: a total and what it is made of (a budget, an army, a harvest). Up to six parts.

zoom_in — a picture; on its words a box is drawn round one part and the view pushes in on it, a label beside it.
  {"op":"zoom_in","picture":{"generate":"a Japanese castle with its main gate, a detailed woodblock print"},
   "box"?:[0.6,0.5,0.9,0.85],"label"?:"The gate","note"?:"Where the guards stood","on":"gate"}
  box: [x0, y0, x1, y1] from 0 to 1 across and down the picture (left out: its middle). Use for: one detail that
  matters in a scene, a map or a source (a seal on a document, a figure in a painting).

layers — slabs stacked at an angle, the top first; each lifted apart and named as it is said.
  {"op":"layers","layers":[{"label":"Shogun","on":"shogun"},{"label":"Daimyo","note"?:"lords","on":"daimyo"},
   {"label":"Samurai","on":"samurai"},{"label":"Farmers","on":"farmers"}]}
  Use for: things in layers (earth's strata, a city's history built on itself, a society's levels). 2-6 layers.

cycle_wheel — steps round a ring with arrows, a word in the middle; a pointer travels round to each as it is said.
  {"op":"cycle_wheel","center"?:"The rice year","steps":[{"label":"Plant","on":"plant"},{"label":"Grow","on":"grow"},
   {"label":"Harvest","on":"harvest"},{"label":"Store","on":"store"}]}
  Use for: a cycle that repeats (seasons, a water cycle, rise and fall of dynasties). 3-8 steps.

checklist — a claim at the top; each test under it ticked or crossed as it is said; the verdict stamped.
  {"op":"checklist","claim":"The Meiji Restoration was a revolution","criteria":[{"text":"New rulers","met":true,"on":"rulers"},
   {"text":"Class system ended","met":true,"on":"class system"},{"text":"Land redistributed","met":false,"on":"land"}],"verdict"?:"Partly"}
  Use for: "was it really X?" judged point by point. met: true (tick) or false (cross).

pros_cons — FOR and AGAINST: each point dropped into its column as said; a bar leans to the stronger side.
  {"op":"pros_cons","pros":[{"text":"Trade","on":"trade"},{"text":"New ideas","on":"ideas"}],
   "cons":[{"text":"Unequal treaties","on":"unequal"}],"lean"?:"pros|cons|even","verdict"?:"Mixed blessing"}
  Use for: weighing a decision, a policy, an era's legacy (up to five a side).

mind_map — an idea in the middle; branches grow out on curved stems as each is said, smaller ideas budding off them.
  {"op":"mind_map","center":"Modernisation","branches":[{"label":"Schools","on":"schools","children"?:["universal","western subjects"]},
   {"label":"Railways","on":"railways"},{"label":"Army","on":"army","children"?:["conscription"]}]}
  Use for: an idea and what it spread into (a reform's parts, a movement's influences). Up to 8 branches.

stamp — a rubber stamp slammed onto what is up (the picture shakes); plays after the beat's other operations.
  {"op":"stamp","text":"Cleared","on":"cleared","color"?,"angle"?:-10,"at"?:"center|top|bottom|left|right"}
  Use for: a VERDICT -- a claim confirmed or overturned, a myth busted, a turning point ("Debunked", "Abolished",
  "Victory", "Not proven"). One or two words. Not for: a summary of the line ("Urban growth", "Recorded", "More
  reliable"): the line is its caption already, and a stamp that repeats it is the key point back again. A stamp lands
  hard: kept for the moments that earn it, it keeps its punch; on beat after beat it is noise. To show what a line
  says, build the thing it says (a counter, a chain, a picture labelled, a part of what is up pointed at).

emphasis — points at a part of what is up, by its name or "<id>.<name>", or at a whole template by its id.
  {"op":"emphasis","target":"chart1.Italy","how":"<see below>","on":"Italy","color"?}
  Use for: the one thing on screen the line is now about. how:
    pulse (a beat of attention, the default)   circle (a ring drawn round by hand)   underline   highlight (the marker)
    box (a frame)   glow   shake (alarm, a failure)   dim (the rest of its template fades back)
    spotlight (the other parts fade far back: "this one, not the others")   rack (as a camera's focus racks: the
    others fade and shrink, this one stays sharp)   magnify (a hand lens over it: "look closer")   wiggle (playful,
    a small surprise)   bounce (a hop: "and this one too")   wash (its colour washed to the accent: it changes side,
    it wins)   strike (a line struck through: wrong, abolished, crossed off)   sweep (a bar swept under it: the key word)`;

export const INTENT = String.raw`MOVING WITH INTENT: how each thing moves is part of what it says. Choose it on purpose.

  "enter" on a template -- how its parts arrive:
    pop (light, friendly: a list of kinds)          rise (calm, steady: explanation)    fade (quiet, reflective)
    drop (weight, a fact landing)                   slide (one after another: a sequence)  zoom (a reveal, scale)
    flip (cards turned over, a reversal)            write (drawn by hand: diagrams, sketches)
    unfold (a map, a plan, a document opened out)   typewrite (a record, a telegram, a report)
    ink (old texts, art, memory: it bleeds in)      stamp (decrees, verdicts, official acts: slammed down)
    spin (a coin, a wheel of fortune, a twist)      iris (opening on a scene, a new chapter, a flashback)
  Vary it: a run of beats on the same entrance looks mechanical. Match the content: a treaty may unfold, a decree stamp,
  a memory ink in, a twist spin. Templates with their own choreography (newspaper spins, countdown flips, letter
  writes) are already shaped; give them "enter" only to change that.

  "emphasis" -- point at what is up, on the word, instead of drawing it again. A chart up, then "Japan was first":
  spotlight Japan. A wrong prediction among cards: strike it. "Look at the gate": magnify, or a zoom_in.

  A picture's camera ("move" on a picture): kenburns (a slow push in and drift, as a documentary films a painting or
  an old photo), pan (carried slowly across a wide scene: a battlefield, a skyline), pullback (opens close and pulls
  back to reveal the whole: "and all around him..."), or a gentle bob | sway | breathe | drift. A long beat on one
  painting or photograph should have a camera move; a cutout of one object floats on its own.

  The look, the transition between pictures and the idle motion of the whole video are set for the run (not by
  you): whatever they are, design with them -- the look's colours and fonts are applied to everything you make.`;

