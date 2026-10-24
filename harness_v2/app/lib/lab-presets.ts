/**
 * The Lab's starting points: one small chapter for each kind of animation the beat script can make
 * (engine/BEAT_SCRIPT.md), to try with the voice and change. Each is a chapter beat script as the Voice tab's editor
 * reads it (lib/voice.ts readChapterScript). check-transcript.mjs compiles every one of them.
 */

import { MOTION_IDLES, MOTION_LOOKS, MOTION_TRANSITIONS } from "./prompts/scenes-motion";

export type LabPreset = { id: string; name: string; note: string; script: Record<string, unknown> };

const board = (title: string, beats: Record<string, unknown>[], extra: Record<string, unknown> = {}) =>
  ({ region: null, ...extra, chapter: { title, narration: title, map: false, beats } });

export const LAB_PRESETS: LabPreset[] = [
  {
    id: "picture-labels", name: "Picture with labels", note: "An AI picture; each label comes on, then is pointed at, as its name is said.",
    script: board("The steam engine", [
      { say: "This is a steam locomotive.", do: [{ op: "picture", generate: "a steam locomotive, side view", labels: ["boiler", "chimney", "driving wheels"], caption: "A steam locomotive" }] },
      { say: "Coal burns under the boiler, and smoke leaves by the chimney.", do: [] },
      { say: "The steam pushes pistons that turn the driving wheels.", do: [] },
    ]),
  },
  {
    id: "picture-steps", name: "Picture explained label by label", note: "A strict chapter: one label shown at first (with a note), the other held back and shown on a later line, lit and held over a line, then hidden; the light lifted.",
    script: { region: null, chapter: { title: "The flood plain", narration: "The flood plain", map: false, strict: true, beats: [
      { say: "When the river floods, the water spreads over the plain.", paragraph: true, do: [{ op: "picture", generate: "a river bank after a flood, dark wet silt, early fields",
        labels: ["water", "soil"], hold: ["soil"], notes: { water: "the yearly flood" }, on: "w2" }] },
      { say: "When it goes back, it leaves rich black soil behind.", do: [{ op: "label", part: "soil", on: "w7" }, { op: "shade", part: "soil", hold: true, on: "w8" }] },
      { say: "Farmers sowed their seed in that soil, year after year.", do: [{ op: "unlabel", part: "water", on: "w2" }] },
      { say: "And the whole plain fed the first towns.", do: [{ op: "unshade", on: "w2" }] },
    ] } },
  },
  {
    id: "diagram-build", name: "Diagram built over beats", note: "A flow drawn with two nodes, the third revealed, one focused, then the camera zooms.",
    script: board("Where the surplus went", [
      { say: "Farmers grew more grain than they needed, and stored it in the granary.", do: [{ op: "diagram", id: "chain", kind: "flow", title: "Where the surplus went",
        nodes: [{ id: "fields", label: "Fields" }, { id: "granary", label: "Granary", kind: "place", items: ["grain", "seed"] }, { id: "crafts", label: "Craftsmen" }],
        edges: [["fields", "granary", "grain"], ["granary", "crafts", "food", "bold"]], show: ["fields", "granary"] }] },
      { say: "The stored food fed craftsmen, who no longer had to farm.", do: [{ op: "reveal", diagram: "chain", nodes: ["crafts"] }] },
      { say: "So the granary was the heart of the town.", do: [{ op: "focus", diagram: "chain", node: "granary" }] },
      { say: "Look again at what it held.", do: [{ op: "point", target: "Granary" }] },
    ]),
  },
  {
    id: "cycle", name: "Cycle", note: "Nodes round a circle, dots running the way it turns.",
    script: board("The water cycle", [
      { say: "Water evaporates, condenses into clouds, falls as rain, and collects again.", do: [{ op: "diagram", id: "water", kind: "cycle", title: "The water cycle",
        nodes: [{ id: "evap", label: "Evaporation" }, { id: "cond", label: "Condensation" }, { id: "rain", label: "Rain" }, { id: "collect", label: "Collection" }] }] },
      { say: "Condensation is where clouds form.", do: [{ op: "focus", diagram: "water", node: "cond" }] },
    ]),
  },
  {
    id: "picture-flow", name: "Flow drawn as one picture", note: "The image model draws the whole flow as one picture; each step and arrow is drawn on in that picture, where it is, as it is said.",
    script: board("From wheat to bread", [
      { say: "Bread begins with wheat, harvested in the field.", do: [{ op: "diagram", id: "bread", kind: "flow", drawn: "picture", about: "how bread is made", title: "From wheat to bread",
        nodes: [{ id: "wheat", label: "Wheat", entity: "a sheaf of golden wheat" }, { id: "mill", label: "Mill", entity: "a stone windmill" },
          { id: "flour", label: "Flour", entity: "a sack of flour" }, { id: "loaf", label: "Bread", entity: "a round loaf of bread" }],
        edges: [["wheat", "mill", "harvested"], ["mill", "flour", "ground"], ["flour", "loaf", "baked"]] }] },
      { say: "The grain goes to the mill, where it is ground into flour.", do: [] },
      { say: "And the baker turns the flour into a loaf of bread.", do: [] },
    ]),
  },
  {
    id: "timeline", name: "Timeline with periods", note: "Events in proportion to their dates, a range, and shaded periods.",
    script: board("The Mughals", [
      { say: "The Mughal empire began at Panipat in 1526 and lasted until the revolt of 1857.", do: [{ op: "timeline", title: "The Mughals", range: ["1500", "1870"],
        events: [["1526", "Panipat"], ["1556", "Akbar crowned"], ["1707", "Aurangzeb dies"], ["1857", "The revolt"]],
        spans: [["1526", "1857", "Mughal Empire"], ["1556", "1605", "Akbar"], ["1757", "1857", "Company rule"]] }] },
      { say: "Akbar's reign was its height.", do: [] },
    ]),
  },
  {
    id: "compare", name: "Compare and define", note: "Two columns side by side, then a definition card.",
    script: board("Two kinds of river", [
      { say: "Himalayan rivers are snow-fed and flow all year; peninsular rivers are rain-fed and seasonal.", do: [{ op: "compare", title: "Two kinds of river",
        columns: [{ title: "Himalayan", points: ["Snow-fed", "Flow all year"] }, { title: "Peninsular", points: ["Rain-fed", "Seasonal"] }] }] },
      { say: "A perennial river is one that flows all year.", do: [{ op: "define", term: "Perennial", meaning: "flowing all through the year" }] },
    ]),
  },
  {
    id: "numbers", name: "Heading, numbers and bars", note: "A heading, a big number and a bar chart.",
    script: board("India's rivers", [
      { say: "Let us look at India's longest rivers.", do: [{ op: "panel", title: "India's rivers", on: "longest rivers" }] },
      { say: "The Ganga runs two thousand five hundred and twenty five kilometres.", do: [{ op: "stat", value: "2,525 km", label: "Ganga: longest river" }] },
      { say: "Compare it with the Godavari and the Krishna.", do: [{ op: "bars", title: "Length (km)", items: [["Ganga", 2525], ["Godavari", 1465], ["Krishna", 1400]] }] },
    ]),
  },
  {
    id: "working", name: "Equation and working", note: "A law, large; then a working built line by line, its answer boxed.",
    script: board("Friction on a slope", [
      { say: "Newton's second law says force is mass times acceleration.", do: [{ op: "equation", tex: "F = ma", label: "Newton's second law" }] },
      { say: "On a slope, the normal force is m g cos theta.", do: [{ op: "work", id: "w", title: "Along the slope", lines: ["N = mg\\cos\\theta"] }] },
      { say: "Friction is mu times the normal force.", do: [{ op: "work", id: "w", lines: ["f = \\mu N"], box: true }] },
    ]),
  },
  {
    id: "timeline-work", name: "Timeline with a working below", note: "A timeline moves to the top at its size when a column of lines arrives.",
    script: board("Marc Bloch", [
      { say: "Marc Bloch lived from 1886 to 1944.", do: [{ op: "timeline", title: "Marc Bloch 1886-1944", events: [["1886", "Born"], ["1944", "Died"]] }] },
      { say: "He asked new questions of history.", do: [{ op: "work", id: "q", title: "Bloch's questions", lines: ["Geography → human history", "Shared attitudes + collective behaviour"] }] },
    ]),
  },
  {
    id: "map", name: "Map: places, a river, an arrow", note: "A map of India; a marker, a river and an arrow, each pointed at as it is said.",
    script: { region: { country: "India" }, chapter: { title: "Along the Ganga", narration: "Along the Ganga", map: true, beats: [
      { say: "The Ganga flows across the northern plains.", do: [{ op: "river", name: "Ganges" }] },
      { say: "Varanasi sits on its banks.", do: [{ op: "marker", place: "Varanasi", label: "Varanasi" }] },
      { say: "Trade moved downstream from Delhi to Patna.", do: [{ op: "arrow", points: ["Delhi", "Patna"], label: "trade" }] },
    ] } },
  },
];

/** One operation of each kind, to add to an experiment as a new beat (the Lab's "Add a beat with"). */
export const LAB_SNIPPETS: { op: string; say: string; do: Record<string, unknown> }[] = [
  { op: "diagram (drawn as one picture)", say: "Wheat goes to the mill, and the mill's flour becomes bread.", do: { op: "diagram", id: "bread", kind: "flow", drawn: "picture", about: "how bread is made", nodes: [{ id: "wheat", label: "Wheat", entity: "a sheaf of golden wheat, a warm watercolour" }, { id: "mill", label: "Mill", entity: "a stone windmill, a warm watercolour" }, { id: "loaf", label: "Bread", entity: "a round loaf of bread, a warm watercolour" }], edges: [["wheat", "mill", "harvested"], ["mill", "loaf", "ground and baked"]] } },
  { op: "picture (generate, labels)", say: "Here is the boiler, the chimney and the wheels.", do: { op: "picture", generate: "a steam locomotive, side view", labels: ["boiler", "chimney", "driving wheels"] } },
  { op: "picture (scene)", say: "A busy medieval market.", do: { op: "picture", generate: "a busy medieval market square", scene: true } },
  { op: "picture (draw, labels)", say: "The heart has four chambers.", do: { op: "picture", draw: "A human heart in front section: right and left atria above the right and left ventricles", labels: ["right atrium", "left ventricle"] } },
  { op: "gallery", say: "Wheat, then rice.", do: { op: "picture", items: [{ generate: "a field of wheat", caption: "Wheat" }, { generate: "a rice paddy", caption: "Rice" }] } },
  { op: "diagram (flow)", say: "Rain fills the river, which feeds the fields.", do: { op: "diagram", id: "d1", nodes: [{ id: "rain", label: "Rain" }, { id: "river", label: "River" }, { id: "fields", label: "Fields" }] } },
  { op: "diagram (hub)", say: "Trade connected cities, ports and markets.", do: { op: "diagram", id: "d2", kind: "hub", nodes: [{ id: "t", label: "Trade" }, { id: "c", label: "Cities" }, { id: "p", label: "Ports" }, { id: "m", label: "Markets" }] } },
  { op: "reveal", say: "And then the fields.", do: { op: "reveal", diagram: "d1", nodes: ["fields"] } },
  { op: "focus", say: "The river is the key.", do: { op: "focus", diagram: "d1", node: "river" } },
  { op: "point", say: "Look again at the river.", do: { op: "point", target: "River" } },
  { op: "shade", say: "Look at the soil.", do: { op: "shade", part: "soil" } },
  { op: "label", say: "And there is the soil.", do: { op: "label", part: "soil" } },
  { op: "unlabel", say: "Leave the water aside.", do: { op: "unlabel", part: "water" } },
  { op: "unshade", say: "Now the whole bank again.", do: { op: "unshade" } },
  { op: "unfocus", say: "Now the whole chain.", do: { op: "unfocus", diagram: "d1" } },
  { op: "timeline", say: "From 1526 to 1857.", do: { op: "timeline", title: "The Mughals", events: [["1526", "Panipat"], ["1707", "Aurangzeb dies"], ["1857", "The revolt"]] } },
  { op: "compare", say: "Snow-fed against rain-fed.", do: { op: "compare", columns: [{ title: "Himalayan", points: ["Snow-fed"] }, { title: "Peninsular", points: ["Rain-fed"] }] } },
  { op: "define", say: "A surplus is more than a family needs.", do: { op: "define", term: "Surplus", meaning: "more than a family needs to eat" } },
  { op: "panel", say: "Rivers shaped where people lived.", do: { op: "panel", title: "Rivers and settlement", on: "Rivers" } },
  { op: "stat", say: "The Ganga runs 2,525 kilometres.", do: { op: "stat", value: "2,525 km", label: "Ganga" } },
  { op: "bars", say: "Compare the three rivers.", do: { op: "bars", items: [["Ganga", 2525], ["Godavari", 1465], ["Krishna", 1400]] } },
  { op: "equation", say: "Force is mass times acceleration.", do: { op: "equation", tex: "F = ma", label: "Newton's second law" } },
  { op: "work", say: "The normal force is m g cos theta.", do: { op: "work", id: "w", lines: ["N = mg\\cos\\theta"] } },
  { op: "clear", say: "Let us start afresh.", do: { op: "clear" } },
];

// ---------------------------------------------------------------- the motion engine (beta) ----------------------------
// engine/MOTION_ENGINE.md: every classic operation in motion, the motion templates, six looks, transitions, energies
// and the timeline's five styles. Each preset is one small chapter on the motion engine (`"engine": "motion"`).

export type LabMotionPreset = LabPreset & { group: string };

const M_LOOKS = MOTION_LOOKS;

const motion = (look: string, title: string, beats: Record<string, unknown>[], extra: Record<string, unknown> = {}) =>
  ({ engine: "motion", look, region: null, ...extra, chapter: { title, narration: title, map: !!extra.region, beats } });

const DEBT_CHART = { op: "chart", kicker: "Debt · % of the economy", unit: "%", highlight: "Japan", reference: { value: 100, label: "The economy" },
  items: [["Japan", 204], ["Italy", 138], ["USA", 126], ["France", 118], ["Canada", 111], ["Germany", 65]] };

const tpl = (id: string, name: string, note: string, look: string, beats: Record<string, unknown>[], extra: Record<string, unknown> = {}): LabMotionPreset =>
  ({ id: `m-${id}`, group: "Templates", name, note, script: motion(look, name, beats, extra) });

export const LAB_MOTION_PRESETS: LabMotionPreset[] = [
  tpl("picture-flow", "Flow drawn as one picture", "The image model draws the whole cycle as one picture; each step (the arrow into it first) is drawn on in that picture, where it is, as it is said.", "paper", [
    { say: "Water in the sea warms in the sun and rises as vapour.", do: [{ op: "diagram", id: "water", kind: "cycle", drawn: "picture", about: "the water cycle", title: "The water cycle",
      nodes: [{ id: "sea", label: "Sea", entity: "blue sea waves, a flat bold editorial illustration" }, { id: "vapour", label: "Vapour", entity: "rising wisps of warm vapour, a flat bold editorial illustration" },
        { id: "cloud", label: "Cloud", entity: "a heavy grey rain cloud, a flat bold editorial illustration" }, { id: "rain", label: "Rain", entity: "falling rain drops, a flat bold editorial illustration" },
        { id: "river", label: "River", entity: "a winding river through hills, a flat bold editorial illustration" }] }] },
    { say: "The vapour gathers into a cloud, and the cloud lets fall its rain.", do: [] },
    { say: "The river carries the rain back to the sea, and the cycle begins again.", do: [] }]),
  // ---- templates, one each (and their options)
  tpl("counter", "Counter", "A figure counts up, its kicker typed, its change popping beside it.", "paper", [
    { say: "Japan owes more than twice the size of its whole economy.", do: [{ op: "counter", value: "204%", label: "Japan's debt, as a share of its economy", kicker: "Debt · % of GDP", delta: "+12%" }] },
    { say: "Interest on it costs ninety billion dollars a year.", do: [{ op: "counter", value: "$90B", label: "a year in interest", delta: "-3%", trend: "down" }] }]),
  tpl("columns", "Column chart", "Baseline drawn, columns rise one by one, values pop, a reference line drawn; each column lit as it is named.", "paper", [
    { say: "Compare Japan with Italy, the United States, France, Canada and Germany.", do: [DEBT_CHART] },
    { say: "Only Germany is under the line.", do: [{ op: "emphasis", target: "Germany", how: "circle" }] }]),
  tpl("bars", "Bar chart", "Bars sweep out along their tracks, values at their ends; the highlighted one in the accent.", "data", [
    { say: "Data centres lead, then hospitals, then factories and schools.", do: [{ op: "chart", kind: "bar", kicker: "Backlog by sector ($B)", highlight: "Data centres",
      items: [["Data centres", 8.7], ["Hospitals", 2.1], ["Factories", 1.8], ["Schools", 1.1]] }] }]),
  tpl("line", "Line chart", "Axes, then the line drawn left to right with a dot riding its end; a dashed mark at 2015.", "data", [
    { say: "The index climbed for a century, and shot up after 2015.", do: [{ op: "chart", kind: "line", kicker: "S&P 500 index", marks: [{ at: 2015, label: "2015" }],
      items: [["1925", 10], ["1945", 14], ["1965", 85], ["1985", 180], ["2005", 1200], ["2015", 2000], ["2025", 5800]] }] }]),
  tpl("units", "Grid of units", "A hundred units pop in a wave; a group coloured as it is said; eight fly off to the side.", "paper", [
    { say: "Of Japan's bonds, the Bank of Japan holds nearly half, and only eight percent are abroad.", do: [{ op: "units", total: 100, kicker: "Japan's government bonds", unit: "IOU",
      groups: [{ n: 46, label: "Bank of Japan", on: "Bank of Japan" }], fly: { n: 8, label: "8% abroad", on: "abroad" } }] }]),
  tpl("cards", "Cards dealt", "Cards dealt in turned a little; ticks, crosses and stamps land on their words; a big stamp across them.", "newsroom", [
    { say: "Three predictions came true, one failed, and one was never tested.", do: [{ op: "cards", stamp: { text: "Debunked", on: "tested" }, items: [
      { title: "Prediction one", big: "1912", mark: "check", on: "three" }, { title: "Prediction two", big: "1914", mark: "check" },
      { title: "Prediction three", big: "1916", mark: "cross", on: "failed" }, { title: "Prediction four", big: "1920", mark: "untested", on: "never tested" }] }] }]),
  tpl("stamp", "Stamp", "A stamp slams onto what is up, with a thud and a shake.", "paper", [
    { say: "Japan's debt is the largest of any rich country.", do: [DEBT_CHART] },
    { say: "Yet every bond auction cleared.", do: [{ op: "stamp", text: "Cleared", on: "cleared" }] }]),
  tpl("kpi", "Data cards", "Cards dealt in, each figure counting as it lands, changes with arrows.", "data", [
    { say: "Sales rose fifty percent, and profit per share ninety two percent.", do: [{ op: "kpi", kicker: "Last quarter", cards: [
      { label: "Sales", value: "+50%", delta: "$3.27B", note: "in sales" }, { label: "Profit per share", value: "+92%", delta: "$12.53", note: "a share" },
      { label: "Backlog", value: "$14.06B", delta: "+73%", note: "work already signed" }] }] }]),
  tpl("chain", "Chain of steps", "Steps join one by one as they are said, arrows drawn to each; a loop back at the end.", "studio", [
    { say: "An order is signed, built, billed and finally paid.", do: [{ op: "chain", title: "How a dollar of backlog moves", loop: true,
      steps: [{ label: "Signed" }, { label: "Built", on: "built" }, { label: "Billed", on: "billed" }, { label: "Paid", on: "paid" }] }] }]),
  tpl("list", "List, ticked", "Points slide in as they are said, each ticked.", "studio", [
    { say: "Three things to watch: margins, hiring, and the next report.", do: [{ op: "list", title: "What to watch", mark: "check",
      items: [{ text: "Margins" }, { text: "Hiring", on: "hiring" }, { text: "The next report", on: "next report" }] }] },
    { say: "In order: first the report, then the call, then the guidance.", do: [{ op: "list", title: "The day", mark: "number",
      items: [{ text: "The report", on: "first" }, { text: "The call", on: "call" }, { text: "The guidance", on: "guidance" }] }] }]),
  tpl("versus", "Versus", "Two cards sweep in from the sides, a VS badge slams between them.", "newsroom", [
    { say: "Snow-fed rivers flow all year; rain-fed rivers run dry.", do: [{ op: "versus", title: "Two kinds of river",
      left: { title: "Himalayan", points: ["Snow-fed", "Flow all year"] }, right: { title: "Peninsular", points: ["Rain-fed", "Seasonal"] } }] }]),
  tpl("donut", "Donut", "The track drawn, the share swept round it, the figure counting in the middle.", "data", [
    { say: "About sixty two percent of the backlog is data centres.", do: [{ op: "donut", value: 62, label: "of the backlog is data centres", sub: "Q2 filing" }] }]),
  tpl("document", "Document, highlighted", "A page drops in; each phrase swept with the highlighter as it is said.", "newsroom", [
    { say: "In his memoirs, he says he learned it from a certain sect of Brahmins, who called it Samudrika.", do: [{ op: "document", title: "Cheiro's memoirs",
      text: "While there I came in contact with a certain sect of Brahmins, descendants of those who, thousands of years before the Christian era, had evolved by study a science called Samudrika.",
      highlight: ["a certain sect of Brahmins", "Samudrika"], picture: { generate: "a Victorian gentleman, sepia studio portrait photograph" } }] }]),
  tpl("polaroids", "Polaroids", "Prints dealt onto the board, turned a little, overlapping; each lifted as it is named.", "chalk", [
    { say: "His clients included Mark Twain, Oscar Wilde and Lord Kitchener.", do: [{ op: "polaroids", items: [
      { generate: "Mark Twain, a portrait photograph", caption: "Mark Twain" }, { generate: "Oscar Wilde, a portrait photograph", caption: "Oscar Wilde" },
      { generate: "Lord Kitchener in uniform, a portrait photograph", caption: "Kitchener" }] }] }]),
  tpl("title", "Headline", "Big words rise one after another, one marked with the highlighter, a kicker typed over them.", "newsroom", [
    { say: "This is the story of the man who read the hands of kings.", do: [{ op: "title", kicker: "A true story", text: "The man who read the hands of kings", highlight: "kings" }] }]),
  tpl("emphasis", "Pointing on purpose", "A part pointed at on its word: circle, underline, highlight, box, glow, shake, dim, pulse.", "paper", [
    { say: "Here are six countries.", do: [DEBT_CHART] },
    { say: "Japan stands out.", do: [{ op: "emphasis", target: "Japan", how: "circle" }] },
    { say: "Italy is next.", do: [{ op: "emphasis", target: "Italy", how: "box" }] },
    { say: "Germany is the lowest.", do: [{ op: "emphasis", target: "Germany", how: "shake" }] },
    { say: "And Japan again, alone.", do: [{ op: "emphasis", target: "Japan", how: "dim" }] }]),
  // ---- the shapes of a history, a society or an argument (engine/motion_more.py)
  tpl("hierarchy", "Hierarchy", "Tiers of a pyramid rise from the bottom as each is named, roles beside them; a badge slams on one.", "sketch", [
    { say: "Some pray, others fight, and still others work: the clergy, the nobility and the peasantry.", do: [{ op: "hierarchy", title: "The three orders",
      tiers: [{ label: "Clergy", role: "those who pray", on: "clergy" }, { label: "Nobility", role: "those who fight", on: "nobility" }, { label: "Peasantry", role: "those who work", on: "peasantry" }],
      badge: { tier: "Nobility", text: "controls the land", on: "fight" } }] }]),
  tpl("exchange", "Exchange", "Two parties sweep in; what each gives the other is drawn across as an arrow on its words.", "paper", [
    { say: "The lord gives protection, and the vassal gives loyalty in return.", do: [{ op: "exchange", title: "A mutual promise", left: "Lord", right: "Vassal",
      flows: [{ from: "left", text: "protection", on: "protection" }, { from: "right", text: "loyalty", on: "loyalty" }] }] }]),
  tpl("plan", "Site plan", "A board laid out zone by zone: buildings, strips of field, woods, pasture, water, each named as said.", "sketch", [
    { say: "The manor-house and church stand together, with fields in strips, woodland, the common pasture and a stream.", do: [{ op: "plan", title: "A manorial estate",
      zones: [{ label: "Manor-house", kind: "building", at: "center" }, { label: "Church", kind: "church", at: "n" }, { label: "Fields", kind: "field", at: "w", on: "fields" },
        { label: "Woodland", kind: "wood", at: "ne" }, { label: "Common pasture", kind: "pasture", at: "s", on: "pasture" }, { label: "Stream", kind: "water", at: "e", on: "stream" }] }] }]),
  tpl("lineage", "Lineage", "A dynasty joined generation by generation, each link named.", "newsroom", [
    { say: "Charles Martel was mayor of the palace; his son Pepin became king, and Pepin's son Charlemagne succeeded him.", do: [{ op: "lineage", title: "A dynasty",
      people: [{ name: "Charles Martel", dates: "714", role: "mayor of the palace" }, { name: "Pepin", dates: "751", role: "king", via: "son" },
        { name: "Charlemagne", dates: "768", role: "emperor, 800", via: "son" }] }] }]),
  tpl("lifespan", "Lifespans", "Lives swept as bars on one scale of years; a dashed mark at an event.", "paper", [
    { say: "Charlemagne lived from 742 to 814, Hildegard from 1098 to 1179, and Marc Bloch from 1886 to 1944.", do: [{ op: "lifespan", title: "Lives",
      people: [{ name: "Charlemagne", from: 742, to: 814 }, { name: "Hildegard of Bingen", from: 1098, to: 1179, on: "Hildegard" }, { name: "Marc Bloch", from: 1886, to: 1944, on: "Marc Bloch" }],
      marks: [{ at: 1066, label: "Norman Conquest" }] }] }]),
  tpl("analogy", "Analogy", "Matched pairs slide in and join, A is to B; a stamp across them.", "sketch", [
    { say: "Cows, donkeys and sheep are kept apart, and so, she said, are clergy, nobles and peasants.", do: [{ op: "analogy", title: "Hildegard's comparison", left: "In the stable", right: "In society",
      pairs: [["Cows", "Clergy"], ["Donkeys", "Nobles"], { a: "Sheep", b: "Peasants", on: "sheep" }], stamp: { text: "Separate ranks", on: "peasants" } }] }]),
  tpl("myth", "Myth corrected", "The wrong idea struck through and stamped; the right one slides in with a tick.", "studio", [
    { say: "Do not picture three separate worlds. Picture three groups connected by the same land.", do: [{ op: "myth", wrong: "Three separate worlds", right: "Three groups connected by the same land", on: "three groups" }] }]),
  tpl("ritual", "Ritual", "A ceremony on parchment: steps written in, objects laid out, a seal pressed.", "paper", [
    { say: "Vows were taken on the Bible in a church, and the vassal received a charter, a staff, or a clod of earth.", do: [{ op: "ritual", title: "Homage and fealty",
      steps: [{ text: "Kneel before the lord", on: "vows" }, { text: "Swear on the Bible", on: "Bible" }, { text: "Receive the land", on: "received" }],
      objects: [{ name: "Charter", on: "charter" }, { name: "Staff", on: "staff" }, { name: "Clod of earth", on: "clod" }], seal: { text: "Bound", on: "earth" } }] }]),
  tpl("share", "Share of a whole", "Ten sacks in a row; one coloured, lifted out and named; 1 in 10 beside it.", "paper", [
    { say: "The Church claimed a tenth of what peasants produced: out of ten equal shares, one went to the Church.", do: [{ op: "share", label: "The tithe", total: 10, part: 1,
      part_label: "to the Church", rest_label: "kept by the family", on: "one went" }] }]),
  tpl("calendar", "Calendar", "A ring of months: seasons swept round it, days pinned on it, a movable date dashed.", "studio", [
    { say: "Christmas falls on the twenty-fifth of December, while Easter moves each spring, after the sowing.", do: [{ op: "calendar", title: "The village year",
      seasons: [{ from: "March", to: "May", label: "Sowing", on: "sowing" }, { from: "August", to: "September", label: "Harvest" }],
      days: [{ at: "December 25", label: "Christmas", on: "Christmas" }, { moves: ["March 22", "April 25"], label: "Easter", on: "Easter" }] }] }]),
  tpl("converge", "Converge", "Places round one centre, each joined to it by an arrow as it is named.", "newsroom", [
    { say: "From every shire of England, from Kent, Essex, Sussex and London, travellers make their way to Canterbury.", do: [{ op: "converge", title: "Pilgrimage", to: "Canterbury",
      sources: ["Kent", "Essex", "Sussex", "London", "Surrey"] }] }]),
  tpl("table", "Table", "Column headings pop in; each row filled in as it is said; one column highlighted.", "data", [
    { say: "Compare France, Mesopotamia and Rome: what justified rank, and which resources supported it.", do: [{ op: "table", title: "Hierarchies compared", columns: ["France", "Mesopotamia", "Rome"], highlight: "France",
      rows: [{ label: "What justified rank", cells: ["Three orders", "Temple and palace", "Law and citizenship"], on: "justified" },
        { label: "Resources", cells: ["Land", "Temple estates", "Wealth and slaves"], on: "resources" }] }] }]),
  tpl("ask", "Question and answer", "The central question set large; its answer typed under it with a tick.", "sketch", [
    { say: "That is our question today: why did power belong not just to kings, but to nobles and churchmen?", do: [{ op: "ask", text: "Why did power belong not just to kings?" }] },
    { say: "We can now answer it: land, protection and religion made several centres of power.", do: [{ op: "ask", text: "Why did power belong not just to kings?",
      answer: "Land, protection and religion made several centres of power", on: "land, protection" }] }]),
  // ---- what overlaps, sits between, narrows, measures, weighs, hides, changes or ranks (motion_forms.py)
  tpl("venn", "Venn", "Two or three sets drawn in one by one; what they share slammed in the middle.", "paper", [
    { say: "Trade brought markets and ports, faith brought temples and pilgrims, and both made the cities.", do: [{ op: "venn", title: "Two forces",
      sets: [{ label: "Trade", items: ["markets", "ports"], on: "Trade" }, { label: "Faith", items: ["temples", "pilgrims"], on: "faith" }], overlap: { text: "Cities", on: "cities" } }] }]),
  tpl("quadrant", "Quadrant", "Two qualities as axes; each thing dropped in its field as it is said.", "data", [
    { say: "Railways cost much and returned much, canals cost little and returned little, and roads sat between.", do: [{ op: "quadrant", title: "Cost against return",
      x: ["Low cost", "High cost"], y: ["Low return", "High return"], cells: { tr: "Big bets", bl: "Small steps" },
      items: [{ text: "Railways", x: 0.85, y: 0.85, on: "Railways" }, { text: "Canals", x: 0.2, y: 0.25, on: "canals" }, { text: "Roads", x: 0.5, y: 0.55, on: "roads" }] }] }]),
  tpl("funnel", "Funnel", "Stages narrowing down, each sliding in with its figure counting.", "newsroom", [
    { say: "Of a thousand who applied, three hundred sat the exam, and only forty passed.", do: [{ op: "funnel", title: "The exam",
      stages: [{ label: "Applied", value: "1,000", on: "thousand" }, { label: "Sat the exam", value: "300", on: "three hundred" }, { label: "Passed", value: "40", on: "forty" }] }] }]),
  tpl("gauge", "Gauge", "A dial; the needle swings to the value as the figure counts up.", "studio", [
    { say: "By the end of the period, literacy had reached seventy two percent.", do: [{ op: "gauge", value: 72, max: 100, text: "72%", label: "literacy", low: "none", high: "all", on: "seventy" }] }]),
  tpl("scale", "Scale", "A balance: each side's items dropped onto its pan; the beam tips to the heavier side.", "paper", [
    { say: "On one side sat silver and silk; on the other, only rice; and the silver side weighed more.", do: [{ op: "scale", title: "What weighed more",
      left: { title: "Exports", items: [{ text: "Silver", on: "silver" }, { text: "Silk", on: "silk" }] }, right: { title: "Imports", items: [{ text: "Rice", on: "rice" }] } }] }]),
  tpl("iceberg", "Iceberg", "What is seen above the waterline, then the larger hidden part rising into view.", "chalk", [
    { say: "We see the castles; but below lie the taxes, the roads, and the rice that paid for it all.", do: [{ op: "iceberg", waterline: "what we see",
      above: [{ text: "Castles", on: "castles" }], below: [{ text: "Taxes", on: "taxes" }, { text: "Roads", on: "roads" }, { text: "Rice", on: "rice" }] }] }]),
  tpl("before-after", "Before and after", "The old state; a bar wipes across to the new one; the change named on the divide.", "paper", [
    { say: "Before the reform, the villages ruled themselves; after it, the capital decided.", do: [{ op: "before_after", change: "the reform",
      before: { title: "Village rule", points: ["Local elders", "Local tax"] }, after: { title: "Capital rule", points: ["Governors", "One tax"], on: "after it" } }] }]),
  tpl("ranking", "Ranking", "A leaderboard counting down to first place, which is crowned.", "data", [
    { say: "Osaka was third, Kyoto second, and Edo the largest city of all.", do: [{ op: "ranking", title: "Largest cities", unit: "k",
      items: [{ label: "Edo", value: 1000, on: "Edo" }, { label: "Kyoto", value: 400, on: "Kyoto" }, { label: "Osaka", value: 350, on: "Osaka" }] }] }]),
  // ---- history and storytelling, numbers and explanations (motion_story.py, motion_explain.py)
  tpl("cause-web", "Web of causes", "Causes slide in on the left, each arrow into the event as thick as its weight.", "archive", [
    {"say": "Debt, drought and a weak king all fed the revolt.", "do": [{"op": "cause_web", "effect": {"text": "The revolt"}, "causes": [{"text": "Debt", "weight": 3, "on": "Debt"}, {"text": "Drought", "weight": 2, "on": "drought"}, {"text": "A weak king", "weight": 1, "on": "weak king"}]}]}]),
  tpl("portrait-card", "Portrait card", "A person as a trading card turned in; facts dealt beside it.", "archive", [
    {"say": "Tokugawa Ieyasu, born 1543, founded the shogunate and moved power to Edo.", "do": [{"op": "portrait_card", "name": "Tokugawa Ieyasu", "dates": "1543 - 1616", "role": "First shogun", "picture": {"generate": "portrait of a samurai lord"}, "facts": [{"text": "Founded the shogunate", "on": "founded"}, {"text": "Moved power to Edo", "on": "Edo"}]}]}]),
  tpl("source-vs-reality", "Source against reality", "A chronicle's claim quoted; the evidence slides in; a verdict stamped.", "archive", [
    {"say": "The chronicle says the city burned for a month; in fact the records show three days.", "do": [{"op": "source_vs_reality", "source": {"text": "The city burned for a month", "by": "A court chronicle"}, "reality": {"text": "Records show the fire lasted three days", "on": "in fact"}, "verdict": "Exaggerated"}]}]),
  tpl("population-pyramid", "Population pyramid", "Age groups as bars both ways, growing out from the youngest up.", "textbook", [
    {"say": "Most people were young; few lived past sixty.", "do": [{"op": "population_pyramid", "groups": [{"label": "60+", "left": 3, "right": 4}, {"label": "40-59", "left": 8, "right": 9}, {"label": "20-39", "left": 15, "right": 14}, {"label": "0-19", "left": 24, "right": 23}], "unit": "% of people"}]}]),
  tpl("migration-flow", "Migration flow", "Regions as discs; each flow an arc as wide as the number who moved.", "isometric", [
    {"say": "Thousands left the villages for Edo, and some went on to Osaka.", "do": [{"op": "migration_flow", "regions": ["Villages", "Edo", "Osaka"], "flows": [{"from": "Villages", "to": "Edo", "value": 5000, "on": "Edo"}, {"from": "Edo", "to": "Osaka", "value": 1200, "on": "Osaka"}]}]}]),
  tpl("quote-reveal", "Quote revealed", "A famous line set large, its words lighting up as spoken.", "brush", [
    {"say": "He wrote: the strong do what they can, and the weak suffer what they must.", "do": [{"op": "quote_reveal", "text": "The strong do what they can, and the weak suffer what they must.", "who": "Thucydides", "highlight": ["strong", "weak"], "picture": {"generate": "bust of a Greek historian"}}]}]),
  tpl("newspaper", "Front page", "A newspaper spun in, the headline slammed on.", "archive", [
    {"say": "The next morning every paper said the same thing.", "do": [{"op": "newspaper", "paper": "The Edo Herald", "date": "8 July 1853", "headline": "Black ships in the bay", "sub": "American warships anchor off Uraga", "picture": {"generate": "black steamships"}}]}]),
  tpl("letter", "Letter", "A letter written on in a hand, then signed.", "brush", [
    {"say": "His letter home was short.", "do": [{"op": "letter", "to": "Mother", "date": "1853", "text": "The ships are here. Nobody knows what they want. Do not worry.", "sign": "Kenji"}]}]),
  tpl("countdown", "Countdown", "Years flip in one over another; then the event lands.", "neon", [
    {"say": "Eighteen fifty, fifty two, fifty three: and then the ships arrived.", "do": [{"op": "countdown", "steps": [{"text": "1850", "on": "Eighteen fifty"}, {"text": "1852", "on": "fifty two"}, {"text": "1853", "on": "fifty three"}], "event": {"text": "The ships arrive", "on": "ships arrived"}}]}]),
  tpl("race-bars", "Racing bars", "Bars stretch and re-sort at each date, the date rolling over.", "data", [
    {"say": "In 1700 Kyoto led; by 1750 Edo had passed it; by 1800 Edo was far ahead.", "do": [{"op": "race_bars", "unit": "k", "frames": [{"at": "1700", "values": {"Edo": 300, "Kyoto": 350, "Osaka": 280}}, {"at": "1750", "values": {"Edo": 800, "Kyoto": 380, "Osaka": 320}, "on": "1750"}, {"at": "1800", "values": {"Edo": 1100, "Kyoto": 370, "Osaka": 380}, "on": "1800"}]}]}]),
  tpl("waterfall", "Waterfall", "Gains step up in green, losses down in red, to the total.", "textbook", [
    {"say": "From a hundred, taxes added forty, wars took sixty, trade added thirty.", "do": [{"op": "waterfall", "start": {"label": "Start", "value": 100}, "steps": [{"label": "Taxes", "value": 40, "on": "taxes"}, {"label": "Wars", "value": -60, "on": "wars"}, {"label": "Trade", "value": 30, "on": "trade"}], "total": "End"}]}]),
  tpl("stacked-area", "Stacked area", "Shares of a whole over the years, layer by layer.", "textbook", [
    {"say": "Farming shrank as trade and crafts grew.", "do": [{"op": "stacked_area", "years": [1700, 1750, 1800, 1850], "series": [{"label": "Farming", "values": [70, 62, 55, 45]}, {"label": "Crafts", "values": [20, 24, 27, 30], "on": "crafts"}, {"label": "Trade", "values": [10, 14, 18, 25], "on": "trade"}]}]}]),
  tpl("slope", "Slope", "Then and now on two posts; rising green, falling red.", "studio", [
    {"say": "Rice prices rose while silk fell.", "do": [{"op": "slope", "left_label": "1700", "right_label": "1800", "items": [{"label": "Rice", "from": 40, "to": 90, "on": "Rice"}, {"label": "Silk", "from": 80, "to": 50, "on": "silk"}]}]}]),
  tpl("dot-compare", "Dot grids", "\"1 in 4\" against \"1 in 20\": grids of dots filling in.", "isometric", [
    {"say": "One in four could read in the towns, one in twenty in the villages.", "do": [{"op": "dot_compare", "groups": [{"label": "Towns", "part": 25, "total": 100, "text": "1 in 4", "on": "towns"}, {"label": "Villages", "part": 5, "total": 100, "text": "1 in 20", "on": "villages"}]}]}]),
  tpl("split-number", "Number split", "A total's bar breaks into its parts.", "collage", [
    {"say": "Of three million koku, rice was two million, the rest silk and salt.", "do": [{"op": "split_number", "value": "3,000,000", "label": "koku of revenue", "parts": [{"label": "Rice", "value": 2000000, "on": "rice"}, {"label": "Silk", "value": 600000, "on": "silk"}, {"label": "Salt", "value": 400000, "on": "salt"}]}]}]),
  tpl("zoom-in", "Zoom into a picture", "A box drawn on one part; the view pushes in on it.", "archive", [
    {"say": "Look closely at the gate in the corner.", "do": [{"op": "zoom_in", "picture": {"generate": "a castle with a gate"}, "box": [0.6, 0.5, 0.9, 0.85], "label": "The gate", "note": "Where the guards stood", "on": "gate"}]}]),
  tpl("layers", "Layers", "Slabs lifted apart one by one, each named.", "drafting", [
    {"say": "Society had layers: the shogun, the daimyo, the samurai and the farmers.", "do": [{"op": "layers", "layers": [{"label": "Shogun", "on": "shogun"}, {"label": "Daimyo", "on": "daimyo"}, {"label": "Samurai", "on": "samurai"}, {"label": "Farmers", "on": "farmers"}]}]}]),
  tpl("cycle-wheel", "Cycle wheel", "A pointer travels round the cycle, lighting each step.", "chalkcolour", [
    {"say": "Plant, grow, harvest, store, and plant again.", "do": [{"op": "cycle_wheel", "center": "The rice year", "steps": [{"label": "Plant", "on": "Plant"}, {"label": "Grow", "on": "grow"}, {"label": "Harvest", "on": "harvest"}, {"label": "Store", "on": "store"}]}]}]),
  tpl("checklist", "Checklist", "A claim tested: ticks and crosses, then a verdict.", "textbook", [
    {"say": "Was it a revolution? It changed rulers, yes; it changed the class system, yes; but it did not change land ownership.", "do": [{"op": "checklist", "claim": "The Meiji Restoration was a revolution", "criteria": [{"text": "New rulers", "met": true, "on": "rulers"}, {"text": "Class system ended", "met": true, "on": "class system"}, {"text": "Land redistributed", "met": false, "on": "land ownership"}], "verdict": "Partly"}]}]),
  tpl("pros-cons", "Pros and cons", "Points dropped into FOR and AGAINST; a bar leans to the stronger.", "collage", [
    {"say": "Opening the ports brought trade and ideas, but also unequal treaties.", "do": [{"op": "pros_cons", "pros": [{"text": "Trade", "on": "trade"}, {"text": "New ideas", "on": "ideas"}], "cons": [{"text": "Unequal treaties", "on": "unequal"}], "verdict": "Mixed blessing"}]}]),
  tpl("mind-map", "Mind map", "Branches grow out round an idea, smaller ideas budding off them.", "chalkcolour", [
    {"say": "Modernisation meant new schools, railways and an army.", "do": [{"op": "mind_map", "center": "Modernisation", "branches": [{"label": "Schools", "on": "schools", "children": ["universal", "western subjects"]}, {"label": "Railways", "on": "railways"}, {"label": "Army", "on": "army", "children": ["conscription"]}]}]}]),
  tpl("map-story", "Story on the map", "A march told on the map: each stop named with its date.", "paper", [
    {"say": "From Kagoshima to Kyoto to Edo, the rebels marched.", "do": [{"op": "map_story", "stops": [{"place": "Kagoshima", "date": "1867"}, {"place": "Kyoto", "date": "1868"}, {"place": "Tokyo", "label": "Edo", "date": "1868"}]}]}], { region: { country: "Japan" } }),
  // ---- how things move: entrances, emphases, a picture's camera, idle motion
  { id: "m-entrances", group: "Animations", name: "Entrances (enter)", note: "The same cards coming on each way: unfold, typewrite, ink, stamp, spin, iris.",
    script: motion("neon", "Entrances", ["unfold", "typewrite", "ink", "stamp", "spin", "iris"].map((enter) => (
      { say: `Rice, silk and tea, coming on with ${enter}.`, do: [{ op: "cards", enter, items: [{ title: "Rice", big: "1", on: "Rice" }, { title: "Silk", big: "2", on: "silk" }, { title: "Tea", big: "3", on: "tea" }] }] }))) },
  { id: "m-emphases", group: "Animations", name: "Emphases (emphasis how)", note: "One chart, a column pointed at each way: spotlight, rack, magnify, wiggle, bounce, wash, strike, sweep.",
    script: motion("studio", "Emphases", [
      { say: "Japan, Italy and Germany compared.", do: [{ op: "chart", id: "c1", items: [["Japan", 204], ["Italy", 138], ["Germany", 65]] }] },
      ...["spotlight", "rack", "magnify", "wiggle", "bounce", "wash", "strike", "sweep"].map((how) => (
        { say: `Now Japan, with ${how}.`, do: [{ op: "emphasis", target: "c1.Japan", how, on: "Japan" }] }))]) },
  { id: "m-cameras", group: "Animations", name: "A picture's camera (move)", note: "A painting filmed three ways: kenburns, pan, pullback.",
    script: motion("archive", "Cameras", ["kenburns", "pan", "pullback"].map((move) => (
      { say: `The harbour at Nagasaki, filmed with ${move}.`, do: [{ op: "picture", generate: "the harbour at Nagasaki with Dutch ships, a detailed Edo-period painting", scene: true, move, on: "harbour" }] }))) },
  ...MOTION_IDLES.map((idle): LabMotionPreset => ({
    id: `m-idle-${idle}`, group: "Idle motion", name: `Idle: ${idle}`, note: `What is up keeps moving with ${idle} while the voice goes on.`,
    script: motion("studio", `Idle: ${idle}`, [
      { say: "Sixty two percent of the backlog is data centres, and it keeps growing every month.", do: [{ op: "donut", value: 62, label: "data centres" }] },
      { say: "Signed, built and paid, one after another, all year round.", do: [{ op: "chain", steps: ["Signed", "Built", "Paid"] }] }], { idle }) })),
  // ---- the same template in other forms (layout) and other ways of coming on (enter)
  tpl("counter-forms", "Counter: ring, bar, badge", "One figure in a ring filled to its share, over a filling bar, and on a seal.", "paper", [
    { say: "Sixty percent of the land was farmed.", do: [{ op: "counter", value: "60%", max: 100, label: "of the land farmed", layout: "ring", on: "Sixty" }] },
    { say: "Forty percent could read.", do: [{ op: "counter", value: "40%", max: 100, label: "could read", layout: "bar", on: "Forty" }] },
    { say: "There were two hundred and fifty domains in all.", do: [{ op: "counter", value: "250", label: "domains", layout: "badge", on: "two hundred" }] }]),
  tpl("list-forms", "List: grid, pills, steps", "The same points as tiles, as coloured chips, and as a staircase.", "studio", [
    { say: "Rice, silk, tea and salt were the main goods.", do: [{ op: "list", title: "Main goods", layout: "grid", items: [{ text: "Rice", on: "Rice" }, { text: "Silk", on: "silk" }, { text: "Tea", on: "tea" }, { text: "Salt", on: "salt" }] }] },
    { say: "Merchants, farmers, artisans and samurai.", do: [{ op: "list", layout: "pills", enter: "drop", items: [{ text: "Merchants", on: "Merchants" }, { text: "Farmers", on: "farmers" }, { text: "Artisans", on: "artisans" }, { text: "Samurai", on: "samurai" }] }] },
    { say: "First survey the land, then fix the tax, then collect it.", do: [{ op: "list", layout: "steps", items: [{ text: "Survey the land", on: "survey" }, { text: "Fix the tax", on: "fix" }, { text: "Collect it", on: "collect" }] }] }]),
  tpl("chain-forms", "Chain: column, zigzag", "Steps down a column, and a cycle snaking along two rows.", "paper", [
    { say: "Rice was grown, taxed, stored, then sold.", do: [{ op: "chain", layout: "column", steps: [{ label: "Grown", on: "grown" }, { label: "Taxed", on: "taxed" }, { label: "Stored", on: "stored" }, { label: "Sold", on: "sold" }] }] },
    { say: "Seed, sprout, plant, harvest, store, and seed again.", do: [{ op: "chain", layout: "zigzag", loop: true, enter: "zoom",
      steps: [{ label: "Seed", on: "Seed" }, { label: "Sprout", on: "sprout" }, { label: "Plant", on: "plant" }, { label: "Harvest", on: "harvest" }, { label: "Store", on: "store" }] }] }]),
  tpl("cards-forms", "Cards: fan, grid", "Cards spread as a hand, and dealt in two rows.", "newsroom", [
    { say: "Three predictions, and each one was wrong.", do: [{ op: "cards", layout: "fan", items: [{ title: "Collapse", big: "1", mark: "cross", on: "Three" }, { title: "Revolt", big: "2", mark: "cross", on: "predictions" }, { title: "Famine", big: "3", mark: "cross", on: "wrong" }] }] },
    { say: "Four rulers, four styles of rule.", do: [{ op: "cards", layout: "grid", items: ["Ieyasu", "Hidetada", "Iemitsu", "Ietsuna"] }] }]),
  tpl("versus-forms", "Versus: split, stack", "The stage cut in two coloured halves; and one side over the other.", "paper", [
    { say: "The north against the south.", do: [{ op: "versus", layout: "split", left: { title: "North", value: "60%", points: ["Wheat", "Cold"] }, right: { title: "South", value: "40%", points: ["Rice", "Warm"], on: "south" } }] },
    { say: "The old trade against the new.", do: [{ op: "versus", layout: "stack", left: { title: "Old trade", points: ["Silk in"] }, right: { title: "New trade", points: ["Silk out"] } }] }]),
  tpl("kpi-forms", "Data cards: column, grid", "Figures as wide strips, and two by two.", "data", [
    { say: "Exports rose, imports fell, and the balance turned.", do: [{ op: "kpi", layout: "column", cards: [{ label: "Exports", value: "+40%", delta: "+12%", on: "Exports" },
      { label: "Imports", value: "-15%", delta: "-5%", trend: "down", on: "imports" }, { label: "Balance", value: "$3.2B", note: "surplus", on: "balance" }] }] },
    { say: "Four figures tell the story.", do: [{ op: "kpi", layout: "grid", cards: [{ label: "Towns", value: "6" }, { label: "Domains", value: "250" }, { label: "Ports", value: "4" }, { label: "Roads", value: "5" }] }] }]),
  // ---- the timeline, in its five styles
  ...(["track", "ribbon", "cards", "road", "vertical"] as const).map((style): LabMotionPreset => ({
    id: `m-timeline-${style}`, group: "Timelines", name: `Timeline: ${style}`,
    note: { track: "The classic timeline in motion: track drawn, each event dropping in as it is said, the lit line running on to it.",
      ribbon: "A band of eras sweeping in block by block, the events planted above as flags.",
      cards: "Events as cards hung from a line, dealt in as they are said.",
      road: "A winding road; a marker travels to each stop as it is said, its sign springing up.",
      vertical: "A line down the side; a dot slides down to each event as it comes." }[style],
    script: motion(style === "road" ? "sketch" : style === "vertical" ? "chalk" : "paper", `The Mughals (${style})`, [
      { say: "The empire began at Panipat in 1526; Akbar was crowned in 1556; Aurangzeb died in 1707; the revolt came in 1857.",
        do: [{ op: "timeline", style, title: "The Mughals", events: [["1526", "Panipat"], ["1556", "Akbar crowned"], ["1707", "Aurangzeb dies"], ["1857", "The revolt"]],
          spans: [["1526", "1707", "Height"], ["1707", "1857", "Decline"]] }] },
      { say: "Akbar's reign was its height.", do: [] }]),
  })),
  // ---- the classic operations, in motion
  ...([
    ["stat", "A stat, counting", { say: "The Ganga runs two thousand five hundred and twenty five kilometres.", do: [{ op: "stat", value: "2,525 km", label: "Ganga: longest river" }] }],
    ["bars", "Bars, as columns", { say: "Compare the Ganga with the Godavari and the Krishna.", do: [{ op: "bars", items: [["Ganga", 2525], ["Godavari", 1465], ["Krishna", 1400]] }] }],
    ["compare", "Compare, as a versus", { say: "Himalayan rivers are snow-fed; peninsular rivers are rain-fed.", do: [{ op: "compare", title: "Two kinds of river",
      columns: [{ title: "Himalayan", points: ["Snow-fed", "Flow all year"] }, { title: "Peninsular", points: ["Rain-fed", "Seasonal"] }] }] }],
    ["define", "Define, highlighted", { say: "A perennial river is one that flows all year.", do: [{ op: "define", term: "Perennial", meaning: "flowing all through the year" }] }],
    ["quote", "Quote, typed", { say: "As Nehru wrote of the Ganga.", do: [{ op: "quote", text: "The Ganga is the river of India, beloved of her people.", who: "Jawaharlal Nehru" }] }],
    ["equation", "Equation, boxed", { say: "Force is mass times acceleration.", do: [{ op: "equation", tex: "F = ma", label: "Newton's second law" }] }],
    ["process", "Process, as a chain", { say: "Water evaporates, condenses, falls as rain and collects.", do: [{ op: "process", title: "The water cycle", cycle: true, steps: ["Evaporation", "Condensation", "Rain", "Collection"] }] }],
    ["panel", "Heading", { say: "Let us look at India's rivers. Most rise in the Himalaya.", do: [{ op: "panel", title: "India's rivers", on: "India's rivers" }] }],
    ["picture", "Picture, dressed", { say: "This is a steam locomotive: its boiler, its chimney, its wheels.", do: [{ op: "picture", generate: "a steam locomotive, side view", labels: ["boiler", "chimney", "driving wheels"] }] }],
    ["diagram", "Diagram, in the look", { say: "Fields fed the granary, and the granary fed the craftsmen.", do: [{ op: "diagram", id: "d", kind: "flow", title: "Where the surplus went",
      nodes: [{ id: "f", label: "Fields" }, { id: "g", label: "Granary" }, { id: "c", label: "Craftsmen" }] }] }],
  ] as [string, string, Record<string, unknown>][]).map(([id, name, beat]): LabMotionPreset => ({
    id: `m-classic-${id}`, group: "Classic operations, in motion", name, note: `The beat script's ${id} operation, drawn and animated by the motion engine.`,
    script: motion("chalk", name, [beat]) })),
  // ---- the looks, side by side: the same three beats in each
  ...M_LOOKS.map((look): LabMotionPreset => ({
    id: `m-look-${look}`, group: "Looks", name: `Look: ${look}`, note: `A counter, a chart and a stamp in the ${look} look (its colours, fonts, board, cards, motion and transition).`,
    script: motion(look, `The ${look} look`, [
      { say: "Japan owes more than twice the size of its economy.", do: [{ op: "counter", value: "204%", label: "debt, as a share of the economy", kicker: "Japan" }] },
      { say: "That is more than Italy, the United States or Germany.", do: [{ ...DEBT_CHART, items: DEBT_CHART.items.filter(([c]) => ["Japan", "Italy", "USA", "Germany"].includes(c as string)) }] },
      { say: "Yet its bonds still sell.", do: [{ op: "stamp", text: "Sold out", on: "sell" }] }]) })),
  // ---- transitions and energies: one picture giving way to the next
  ...MOTION_TRANSITIONS.map((transition): LabMotionPreset => ({
    id: `m-transition-${transition}`, group: "Transitions", name: `Transition: ${transition}`, note: `Three pictures, each giving way to the next with a ${transition}.`,
    script: motion("studio", `Transition: ${transition}`, [
      { say: "First, the number.", do: [{ op: "counter", value: "62%", label: "of the backlog" }] },
      { say: "Then where it comes from.", do: [{ op: "donut", value: 62, label: "data centres" }] },
      { say: "Then how it moves.", do: [{ op: "chain", steps: ["Signed", "Built", "Paid"] }] }], { transition }) })),
  ...["calm", "lively", "punchy"].map((energy): LabMotionPreset => ({
    id: `m-energy-${energy}`, group: "Energies", name: `Energy: ${energy}`, note: `The same chart and list moving at the ${energy} pace.`,
    script: motion("paper", `Energy: ${energy}`, [
      { say: "Six countries, one stands out.", do: [DEBT_CHART] },
      { say: "Watch margins, hiring and the report.", do: [{ op: "list", mark: "check", items: ["Margins", "Hiring", "The report"] }] }], { energy }) })),
  // ---- whole scenes, in the manner of the references
  { id: "m-scene-economy", group: "Scenes", name: "Scene: an economics explainer", note: "Paper look: a counter, a chart, a grid of bonds, a stamp, a list.",
    script: motion("paper", "Japan's debt", [
      { say: "Japan owes more than twice the size of its whole economy.", do: [{ op: "counter", value: "204%", kicker: "Debt · % of GDP", label: "the largest of any rich country" }], paragraph: true },
      { say: "Compare it with Italy, the United States, France, Canada and Germany.", do: [DEBT_CHART] },
      { say: "Who holds it? The Bank of Japan holds nearly half, and only eight percent is abroad.", do: [{ op: "units", total: 100, kicker: "Japan's government bonds", unit: "IOU",
        groups: [{ n: 46, label: "Bank of Japan", on: "Bank of Japan" }], fly: { n: 8, label: "8% abroad", on: "abroad" } }], paragraph: true },
      { say: "So every auction still clears.", do: [{ op: "stamp", text: "Cleared", on: "clears" }] },
      { say: "Three things could change that: rates, the yen, and an ageing country.", do: [{ op: "list", title: "What could change it", mark: "number",
        items: [{ text: "Rates", on: "rates" }, { text: "The yen", on: "yen" }, { text: "An ageing country", on: "ageing" }] }], paragraph: true }]) },
  { id: "m-scene-history", group: "Scenes", name: "Scene: a history documentary", note: "Newsroom look: a headline, a highlighted memoir, prints, a timeline, cards stamped.",
    script: motion("newsroom", "The palm reader", [
      { say: "This is the story of the man who read the hands of kings.", do: [{ op: "title", kicker: "A true story", text: "The man who read the hands of kings", highlight: "kings" }], paragraph: true },
      { say: "In his memoirs, he says he learned it from a certain sect of Brahmins.", do: [{ op: "document", title: "Cheiro's memoirs",
        text: "While there I came in contact with a certain sect of Brahmins, descendants of those who had evolved by study a science called Samudrika.", highlight: ["a certain sect of Brahmins"] }] },
      { say: "He lived from 1866 to 1936, reading palms in London from 1890.", do: [{ op: "timeline", style: "cards", title: "Cheiro", events: [["1866", "Born in Ireland"], ["1890", "London"], ["1936", "Dies in Hollywood"]] }], paragraph: true },
      { say: "Three predictions came true, one failed.", do: [{ op: "cards", items: [{ title: "One", big: "1912", mark: "check" }, { title: "Two", big: "1914", mark: "check" },
        { title: "Three", big: "1916", mark: "check" }, { title: "Four", big: "1920", mark: "cross", on: "failed" }], stamp: { text: "Unproven", on: "failed" } }] }]) },
  { id: "m-scene-science", group: "Scenes", name: "Scene: a science lesson", note: "Chalk look: a definition, a chain, an equation, a donut, a vertical timeline.",
    script: motion("chalk", "The water cycle", [
      { say: "Evaporation is water turning to vapour.", do: [{ op: "define", term: "Evaporation", meaning: "water turning into vapour as it warms" }], paragraph: true },
      { say: "It evaporates, condenses, falls as rain and collects again.", do: [{ op: "chain", title: "The water cycle", loop: true,
        steps: [{ label: "Evaporates" }, { label: "Condenses", on: "condenses" }, { label: "Rains", on: "rain" }, { label: "Collects", on: "collects" }] }] },
      { say: "Ninety seven percent of Earth's water is in the oceans.", do: [{ op: "donut", value: 97, label: "of Earth's water is in the oceans" }], paragraph: true },
      { say: "Heat needed: mass times specific heat times the change in temperature.", do: [{ op: "equation", tex: "Q = mc\\Delta T", label: "Heat" }] }]) },
  { id: "m-scene-finance", group: "Scenes", name: "Scene: a finance breakdown", note: "Data look: data cards, a line chart, a bar chart, a versus.",
    script: motion("data", "A strong quarter", [
      { say: "Sales rose fifty percent, and profit per share ninety two percent.", do: [{ op: "kpi", kicker: "Last quarter", cards: [
        { label: "Sales", value: "+50%", delta: "$3.27B" }, { label: "Profit per share", value: "+92%", delta: "$12.53" }] }], paragraph: true },
      { say: "The stock climbed all year, and faster after the summer.", do: [{ op: "chart", kind: "line", kicker: "Share price", marks: [{ at: 7, label: "Summer" }],
        items: [["1", 120], ["2", 128], ["3", 125], ["4", 140], ["5", 150], ["6", 158], ["7", 170], ["8", 196], ["9", 215], ["10", 240]] }] },
      { say: "Before and after: the backlog went from eight to fourteen billion.", do: [{ op: "versus", left: { title: "A year ago", value: "$8.1B" }, right: { title: "Now", value: "$14.1B" } }], paragraph: true }]) },
  { id: "m-scene-medieval", group: "Scenes", name: "Scene: a medieval society", note: "Sketch look: a question, three orders, an exchange, a manor's plan, a ritual, a tithe.",
    script: motion("sketch", "Scene: a medieval society", [
      { say: "Why did power belong not just to kings, but also to nobles and churchmen?", do: [{ op: "ask", text: "Why did power belong not just to kings?" }] },
      { say: "Some pray, others fight, and still others work.", do: [{ op: "hierarchy", tiers: [{ label: "Clergy", role: "pray", on: "pray" }, { label: "Nobility", role: "fight", on: "fight" }, { label: "Peasantry", role: "work", on: "work" }] }] },
      { say: "The lord gives protection; the vassal gives loyalty.", do: [{ op: "exchange", left: "Lord", right: "Vassal", flows: [{ from: "left", text: "protection", on: "protection" }, { from: "right", text: "loyalty", on: "loyalty" }] }] },
      { say: "The estate held a manor-house, a church, fields in strips and woodland.", do: [{ op: "plan", zones: [{ label: "Manor-house", kind: "building", at: "center" }, { label: "Church", kind: "church", at: "n" }, { label: "Fields", kind: "field", at: "w", on: "fields" }, { label: "Woodland", kind: "wood", at: "e", on: "woodland" }] }] },
      { say: "Vows were sworn on the Bible, and a clod of earth stood for the land.", do: [{ op: "ritual", title: "Homage", steps: [{ text: "Swear on the Bible", on: "Bible" }], objects: [{ name: "Clod of earth", on: "clod" }], seal: { text: "Bound", on: "land" } }] },
      { say: "And one share in ten went to the Church.", do: [{ op: "share", label: "The tithe", total: 10, part: 1, part_label: "to the Church", on: "one share" }] }]) },
  { id: "m-scene-sketch", group: "Scenes", name: "Scene: a sketchbook", note: "Sketch look: a road of stops, a list, a donut, a stamp.",
    script: motion("sketch", "Babur's road", [
      { say: "Babur marched from Kabul in 1504, to Panipat in 1526, and on to Agra.", do: [{ op: "timeline", style: "road", title: "Babur's road", events: [["1504", "Kabul"], ["1526", "Panipat"], ["1527", "Agra"]] }], paragraph: true },
      { say: "He won with three things: guns, cavalry and surprise.", do: [{ op: "list", title: "Why he won", mark: "check", items: [{ text: "Guns", on: "guns" }, { text: "Cavalry", on: "cavalry" }, { text: "Surprise", on: "surprise" }] }] },
      { say: "His army was outnumbered.", do: [{ op: "stamp", text: "Outnumbered", on: "outnumbered" }] }]) },
];

/** One motion template of each kind, to add to a motion experiment as a new beat. */
export const LAB_MOTION_SNIPPETS: { op: string; say: string; do: Record<string, unknown> }[] = [
  { op: "diagram (drawn as one picture)", say: "Wheat goes to the mill, and the mill's flour becomes bread.", do: { op: "diagram", id: "bread", kind: "flow", drawn: "picture", about: "how bread is made", nodes: [{ id: "wheat", label: "Wheat", entity: "a sheaf of golden wheat, a warm watercolour" }, { id: "mill", label: "Mill", entity: "a stone windmill, a warm watercolour" }, { id: "loaf", label: "Bread", entity: "a round loaf of bread, a warm watercolour" }], edges: [["wheat", "mill", "harvested"], ["mill", "loaf", "ground and baked"]] } },
  { op: "counter", say: "Debt is two hundred and four percent.", do: { op: "counter", value: "204%", label: "of the economy", delta: "+12%" } },
  { op: "chart (column)", say: "Japan, Italy and Germany.", do: { op: "chart", items: [["Japan", 204], ["Italy", 138], ["Germany", 65]], unit: "%", highlight: "Japan", reference: { value: 100, label: "The economy" } } },
  { op: "chart (bar)", say: "Data centres lead.", do: { op: "chart", kind: "bar", items: [["Data centres", 8.7], ["Hospitals", 2.1]] } },
  { op: "chart (line)", say: "It climbed.", do: { op: "chart", kind: "line", items: [["2019", 10], ["2021", 14], ["2023", 30], ["2025", 58]] } },
  { op: "units", say: "Nearly half at home, a few abroad.", do: { op: "units", total: 60, unit: "IOU", groups: [{ n: 28, label: "At home", on: "home" }], fly: { n: 5, label: "Abroad", on: "abroad" } } },
  { op: "cards", say: "Two came true, one failed.", do: { op: "cards", items: [{ title: "One", big: "1912", mark: "check" }, { title: "Two", big: "1914", mark: "check" }, { title: "Three", big: "1916", mark: "cross", on: "failed" }] } },
  { op: "stamp", say: "It was cleared.", do: { op: "stamp", text: "Cleared", on: "cleared" } },
  { op: "kpi", say: "Sales up, profit up.", do: { op: "kpi", cards: [{ label: "Sales", value: "+50%" }, { label: "Profit", value: "+92%" }] } },
  { op: "chain", say: "Signed, built, paid.", do: { op: "chain", steps: ["Signed", "Built", "Paid"] } },
  { op: "list", say: "Margins, hiring, the report.", do: { op: "list", mark: "check", items: ["Margins", "Hiring", "The report"] } },
  { op: "versus", say: "Snow-fed against rain-fed.", do: { op: "versus", left: { title: "Snow-fed" }, right: { title: "Rain-fed" } } },
  { op: "donut", say: "Sixty two percent.", do: { op: "donut", value: 62, label: "data centres" } },
  { op: "document", say: "He met a certain sect of Brahmins.", do: { op: "document", text: "While there I came in contact with a certain sect of Brahmins.", highlight: ["a certain sect of Brahmins"] } },
  { op: "title", say: "The man who read the hands of kings.", do: { op: "title", kicker: "A true story", text: "The man who read the hands of kings", highlight: "kings" } },
  { op: "emphasis", say: "Japan stands out.", do: { op: "emphasis", target: "Japan", how: "circle" } },
  { op: "timeline (road)", say: "Kabul, Panipat, Agra.", do: { op: "timeline", style: "road", events: [["1504", "Kabul"], ["1526", "Panipat"], ["1527", "Agra"]] } },
  { op: "hierarchy", say: "Clergy, nobility, peasantry.", do: { op: "hierarchy", tiers: ["Clergy", "Nobility", "Peasantry"] } },
  { op: "exchange", say: "Protection for loyalty.", do: { op: "exchange", left: "Lord", right: "Vassal", flows: [{ from: "left", text: "protection" }, { from: "right", text: "loyalty" }] } },
  { op: "plan", say: "Houses, fields and woods.", do: { op: "plan", zones: [{ label: "Houses", kind: "building" }, { label: "Fields", kind: "field" }, { label: "Woods", kind: "wood" }] } },
  { op: "lineage", say: "Pepin, then Charlemagne.", do: { op: "lineage", people: [{ name: "Pepin" }, { name: "Charlemagne", via: "son" }] } },
  { op: "lifespan", say: "Marc Bloch, 1886 to 1944.", do: { op: "lifespan", people: [{ name: "Marc Bloch", from: 1886, to: 1944 }] } },
  { op: "analogy", say: "Cows are to clergy as sheep are to peasants.", do: { op: "analogy", pairs: [["Cows", "Clergy"], ["Sheep", "Peasants"]] } },
  { op: "myth", say: "Not separate worlds, but connected groups.", do: { op: "myth", wrong: "Separate worlds", right: "Connected groups" } },
  { op: "ritual", say: "Kneel, then swear.", do: { op: "ritual", title: "The oath", steps: ["Kneel", "Swear"], seal: "Bound" } },
  { op: "share", say: "One in ten went to the Church.", do: { op: "share", total: 10, part: 1, part_label: "to the Church" } },
  { op: "calendar", say: "Christmas, in December.", do: { op: "calendar", days: [{ at: "December 25", label: "Christmas" }] } },
  { op: "converge", say: "Kent and Essex to Canterbury.", do: { op: "converge", to: "Canterbury", sources: ["Kent", "Essex"] } },
  { op: "table", say: "France and Rome compared.", do: { op: "table", columns: ["France", "Rome"], rows: [{ label: "Rank", cells: ["Orders", "Law"] }] } },
  { op: "ask", say: "Who held power, and why?", do: { op: "ask", text: "Who held power, and why?" } },
  { op: "venn", say: "Trade and faith made the cities.", do: { op: "venn", sets: ["Trade", "Faith"], overlap: "Cities" } },
  { op: "quadrant", say: "Railways cost much and returned much.", do: { op: "quadrant", x: ["Low cost", "High cost"], y: ["Low return", "High return"], items: [{ text: "Railways", x: 0.85, y: 0.85 }] } },
  { op: "funnel", say: "Applied, sat, passed.", do: { op: "funnel", stages: ["Applied", "Sat", "Passed"] } },
  { op: "gauge", say: "Seventy two percent.", do: { op: "gauge", value: 72, text: "72%", label: "literacy" } },
  { op: "scale", say: "Silver outweighed rice.", do: { op: "scale", left: { title: "Silver", items: ["Silver"] }, right: { title: "Rice", items: [] }, tips: "left" } },
  { op: "iceberg", say: "Castles above, taxes below.", do: { op: "iceberg", above: ["Castles"], below: ["Taxes", "Roads"] } },
  { op: "before_after", say: "Villages before, the capital after.", do: { op: "before_after", before: "Village rule", after: "Capital rule", change: "the reform" } },
  { op: "ranking", say: "Edo, Kyoto, Osaka.", do: { op: "ranking", items: ["Edo", "Kyoto", "Osaka"] } },
  { op: "counter (ring)", say: "Sixty percent.", do: { op: "counter", value: "60%", max: 100, layout: "ring" } },
  { op: "list (pills)", say: "Merchants and farmers.", do: { op: "list", layout: "pills", enter: "drop", items: ["Merchants", "Farmers"] } },
  { op: "versus (split)", say: "North against south.", do: { op: "versus", layout: "split", left: "North", right: "South" } },
  { op: "cause_web", say: "Debt and drought fed the revolt.", do: {"op": "cause_web", "effect": "The revolt", "causes": [{"text": "Debt", "weight": 3}, {"text": "Drought", "weight": 2}]} },
  { op: "portrait_card", say: "Ieyasu, the first shogun.", do: {"op": "portrait_card", "name": "Tokugawa Ieyasu", "dates": "1543 - 1616", "role": "First shogun"} },
  { op: "source_vs_reality", say: "A month, says the chronicle; three days, say the records.", do: {"op": "source_vs_reality", "source": {"text": "It burned for a month", "by": "A chronicle"}, "reality": {"text": "Three days"}, "verdict": "Exaggerated"} },
  { op: "population_pyramid", say: "Mostly young.", do: {"op": "population_pyramid", "groups": [{"label": "40+", "left": 8, "right": 9}, {"label": "0-39", "left": 40, "right": 38}]} },
  { op: "migration_flow", say: "Villages to Edo.", do: {"op": "migration_flow", "regions": ["Villages", "Edo"], "flows": [{"from": "Villages", "to": "Edo", "value": 5000}]} },
  { op: "quote_reveal", say: "Knowledge is power.", do: {"op": "quote_reveal", "text": "Knowledge is power.", "who": "Francis Bacon", "highlight": ["power"]} },
  { op: "newspaper", say: "The ships arrived.", do: {"op": "newspaper", "paper": "The Edo Herald", "date": "1853", "headline": "Black ships in the bay"} },
  { op: "letter", say: "He wrote home.", do: {"op": "letter", "to": "Mother", "text": "The ships are here.", "sign": "Kenji"} },
  { op: "countdown", say: "1852, 1853, and then the ships.", do: {"op": "countdown", "steps": ["1852", "1853"], "event": "The ships arrive"} },
  { op: "race_bars", say: "Edo overtook Kyoto.", do: {"op": "race_bars", "frames": [{"at": "1700", "values": {"Edo": 300, "Kyoto": 350}}, {"at": "1800", "values": {"Edo": 1100, "Kyoto": 370}}]} },
  { op: "waterfall", say: "Taxes up, wars down.", do: {"op": "waterfall", "start": 100, "steps": [{"label": "Taxes", "value": 40}, {"label": "Wars", "value": -60}], "total": "End"} },
  { op: "stacked_area", say: "Farming shrank, trade grew.", do: {"op": "stacked_area", "years": [1700, 1800], "series": [{"label": "Farming", "values": [70, 50]}, {"label": "Trade", "values": [30, 50]}]} },
  { op: "slope", say: "Rice rose, silk fell.", do: {"op": "slope", "left_label": "1700", "right_label": "1800", "items": [{"label": "Rice", "from": 40, "to": 90}, {"label": "Silk", "from": 80, "to": 50}]} },
  { op: "dot_compare", say: "One in four, one in twenty.", do: {"op": "dot_compare", "groups": [{"label": "Towns", "part": 25, "total": 100}, {"label": "Villages", "part": 5, "total": 100}]} },
  { op: "split_number", say: "Rice and silk.", do: {"op": "split_number", "value": "300", "parts": [{"label": "Rice", "value": 200}, {"label": "Silk", "value": 100}]} },
  { op: "zoom_in", say: "Look at the gate.", do: {"op": "zoom_in", "picture": {"generate": "a castle with a gate, a woodblock print"}, "box": [0.6, 0.5, 0.9, 0.85], "label": "The gate", "on": "gate"} },
  { op: "layers", say: "Shogun, daimyo, farmers.", do: {"op": "layers", "layers": ["Shogun", "Daimyo", "Farmers"]} },
  { op: "cycle_wheel", say: "Plant, grow, harvest.", do: {"op": "cycle_wheel", "center": "The rice year", "steps": ["Plant", "Grow", "Harvest"]} },
  { op: "checklist", say: "New rulers, but no land reform.", do: {"op": "checklist", "claim": "A revolution?", "criteria": [{"text": "New rulers", "met": true}, {"text": "Land reform", "met": false}], "verdict": "Partly"} },
  { op: "pros_cons", say: "Trade for, treaties against.", do: {"op": "pros_cons", "pros": ["Trade"], "cons": ["Unequal treaties"], "verdict": "Mixed"} },
  { op: "mind_map", say: "Schools, railways, an army.", do: {"op": "mind_map", "center": "Modernisation", "branches": ["Schools", "Railways", "Army"]} },
  { op: "cards (enter: unfold)", say: "Rice and silk.", do: {"op": "cards", "enter": "unfold", "items": ["Rice", "Silk"]} },
  { op: "emphasis (spotlight)", say: "Japan stands out.", do: {"op": "emphasis", "target": "Japan", "how": "spotlight"} },
];
