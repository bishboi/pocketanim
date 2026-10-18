/**
 * The Lab's starting points: one small chapter for each kind of animation the beat script can make
 * (engine/BEAT_SCRIPT.md), to try with the voice and change. Each is a chapter beat script as the Voice tab's editor
 * reads it (lib/voice.ts readChapterScript). check-transcript.mjs compiles every one of them.
 */

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
    id: "diagram-build", name: "Diagram built over beats", note: "A flow drawn with two nodes, the third revealed, one focused, then the camera zooms.",
    script: board("Where the surplus went", [
      { say: "Farmers grew more grain than they needed, and stored it in the granary.", do: [{ op: "diagram", id: "chain", kind: "flow", title: "Where the surplus went",
        nodes: [{ id: "fields", label: "Fields" }, { id: "granary", label: "Granary", kind: "place", items: ["grain", "seed"] }, { id: "crafts", label: "Craftsmen" }],
        edges: [["fields", "granary", "grain"], ["granary", "crafts", "food", "bold"]], show: ["fields", "granary"] }] },
      { say: "The stored food fed craftsmen, who no longer had to farm.", do: [{ op: "reveal", diagram: "chain", nodes: ["crafts"] }] },
      { say: "So the granary was the heart of the town.", do: [{ op: "focus", diagram: "chain", node: "granary" }] },
      { say: "Look closer at what it held.", do: [{ op: "zoom", diagram: "chain", node: "granary", scale: 2 }] },
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
    id: "numbers", name: "Heading, numbers and bars", note: "A heading, a key point, a big number and a bar chart.",
    script: board("India's rivers", [
      { say: "Let us look at India's longest rivers.", do: [{ op: "panel", title: "India's rivers" }, { op: "fact", text: "Most rise in the Himalaya" }] },
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
  { op: "picture (generate, labels)", say: "Here is the boiler, the chimney and the wheels.", do: { op: "picture", generate: "a steam locomotive, side view", labels: ["boiler", "chimney", "driving wheels"] } },
  { op: "picture (scene)", say: "A busy medieval market.", do: { op: "picture", generate: "a busy medieval market square", scene: true } },
  { op: "picture (draw, labels)", say: "The heart has four chambers.", do: { op: "picture", draw: "A human heart in front section: right and left atria above the right and left ventricles", labels: ["right atrium", "left ventricle"] } },
  { op: "gallery", say: "Wheat, then rice.", do: { op: "picture", items: [{ generate: "a field of wheat", caption: "Wheat" }, { generate: "a rice paddy", caption: "Rice" }] } },
  { op: "diagram (flow)", say: "Rain fills the river, which feeds the fields.", do: { op: "diagram", id: "d1", nodes: [{ id: "rain", label: "Rain" }, { id: "river", label: "River" }, { id: "fields", label: "Fields" }] } },
  { op: "diagram (hub)", say: "Trade connected cities, ports and markets.", do: { op: "diagram", id: "d2", kind: "hub", nodes: [{ id: "t", label: "Trade" }, { id: "c", label: "Cities" }, { id: "p", label: "Ports" }, { id: "m", label: "Markets" }] } },
  { op: "reveal", say: "And then the fields.", do: { op: "reveal", diagram: "d1", nodes: ["fields"] } },
  { op: "focus", say: "The river is the key.", do: { op: "focus", diagram: "d1", node: "river" } },
  { op: "zoom", say: "Look closer at the river.", do: { op: "zoom", diagram: "d1", node: "river", scale: 2 } },
  { op: "timeline", say: "From 1526 to 1857.", do: { op: "timeline", title: "The Mughals", events: [["1526", "Panipat"], ["1707", "Aurangzeb dies"], ["1857", "The revolt"]] } },
  { op: "compare", say: "Snow-fed against rain-fed.", do: { op: "compare", columns: [{ title: "Himalayan", points: ["Snow-fed"] }, { title: "Peninsular", points: ["Rain-fed"] }] } },
  { op: "define", say: "A surplus is more than a family needs.", do: { op: "define", term: "Surplus", meaning: "more than a family needs to eat" } },
  { op: "panel + fact", say: "Rivers shaped where people lived.", do: { op: "fact", text: "Rivers shaped settlement" } },
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

const M_LOOKS = ["paper", "newsroom", "chalk", "data", "studio", "sketch"] as const;

const motion = (look: string, title: string, beats: Record<string, unknown>[], extra: Record<string, unknown> = {}) =>
  ({ engine: "motion", look, region: null, ...extra, chapter: { title, narration: title, map: false, beats } });

const DEBT_CHART = { op: "chart", kicker: "Debt · % of the economy", unit: "%", highlight: "Japan", reference: { value: 100, label: "The economy" },
  items: [["Japan", 204], ["Italy", 138], ["USA", 126], ["France", 118], ["Canada", 111], ["Germany", 65]] };

const tpl = (id: string, name: string, note: string, look: string, beats: Record<string, unknown>[], extra: Record<string, unknown> = {}): LabMotionPreset =>
  ({ id: `m-${id}`, group: "Templates", name, note, script: motion(look, name, beats, extra) });

export const LAB_MOTION_PRESETS: LabMotionPreset[] = [
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
  tpl("callout", "Callout", "A word on a block of the accent pops onto what is up.", "paper", [
    { say: "Most of the bonds are held at home.", do: [{ op: "units", total: 60, unit: "IOU", groups: [{ n: 55, label: "At home" }] }] },
    { say: "Only a sliver is held abroad.", do: [{ op: "callout", text: "8% abroad", on: "abroad" }] }]),
  tpl("emphasis", "Pointing on purpose", "A part pointed at on its word: circle, underline, highlight, box, glow, shake, dim, pulse.", "paper", [
    { say: "Here are six countries.", do: [DEBT_CHART] },
    { say: "Japan stands out.", do: [{ op: "emphasis", target: "Japan", how: "circle" }] },
    { say: "Italy is next.", do: [{ op: "emphasis", target: "Italy", how: "box" }] },
    { say: "Germany is the lowest.", do: [{ op: "emphasis", target: "Germany", how: "shake" }] },
    { say: "And Japan again, alone.", do: [{ op: "emphasis", target: "Japan", how: "dim" }] }]),
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
    ["fact", "Heading and key point", { say: "Let us look at India's rivers. Most rise in the Himalaya.", do: [{ op: "panel", title: "India's rivers" }, { op: "fact", text: "Most rise in the Himalaya" }] }],
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
  ...["slide", "push", "wipe", "dissolve", "zoom", "page", "cut"].map((transition): LabMotionPreset => ({
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
  { id: "m-scene-sketch", group: "Scenes", name: "Scene: a sketchbook", note: "Sketch look: a road of stops, a list, a donut, a stamp.",
    script: motion("sketch", "Babur's road", [
      { say: "Babur marched from Kabul in 1504, to Panipat in 1526, and on to Agra.", do: [{ op: "timeline", style: "road", title: "Babur's road", events: [["1504", "Kabul"], ["1526", "Panipat"], ["1527", "Agra"]] }], paragraph: true },
      { say: "He won with three things: guns, cavalry and surprise.", do: [{ op: "list", title: "Why he won", mark: "check", items: [{ text: "Guns", on: "guns" }, { text: "Cavalry", on: "cavalry" }, { text: "Surprise", on: "surprise" }] }] },
      { say: "His army was outnumbered.", do: [{ op: "stamp", text: "Outnumbered", on: "outnumbered" }] }]) },
];

/** One motion template of each kind, to add to a motion experiment as a new beat. */
export const LAB_MOTION_SNIPPETS: { op: string; say: string; do: Record<string, unknown> }[] = [
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
  { op: "callout", say: "Only a few abroad.", do: { op: "callout", text: "8% abroad", on: "abroad" } },
  { op: "emphasis", say: "Japan stands out.", do: { op: "emphasis", target: "Japan", how: "circle" } },
  { op: "timeline (road)", say: "Kabul, Panipat, Agra.", do: { op: "timeline", style: "road", events: [["1504", "Kabul"], ["1526", "Panipat"], ["1527", "Agra"]] } },
];
