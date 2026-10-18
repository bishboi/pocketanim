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

// ---------------- the beta engine (engine/BETA_ENGINE.md) ----------------
// Slides of boxes: a beat's `layout` starts a slide, its `elements` go in the layout's slots (or their own `box`),
// and `animate` says how each comes on, is pointed at, leaves or moves, `on` the words that bring it.

const beta = (title: string, beats: Record<string, unknown>[]) =>
  ({ engine: "beta", region: null, chapter: { title, narration: title, map: false, beats } });

export const LAB_BETA_PRESETS: LabPreset[] = [
  {
    id: "beta-picture", name: "Beta: labelled picture and points", note: "A picture on the left, its parts pointed at on their words; a title and points on the right.",
    script: beta("The steam engine", [
      { say: "This is a steam locomotive. Coal burns under the boiler, and smoke leaves by the chimney.", layout: "wide-left",
        elements: [{ id: "pic", image: { generate: "a steam locomotive, side view", labels: ["boiler", "chimney"] }, slot: "left" },
          { id: "t", text: "The steam engine", style: "title", slot: "right" },
          { id: "pts", list: ["Coal burns", "Water boils", "Steam drives the pistons"], slot: "right" }],
        animate: [{ id: "pic", in: "grow" }, { id: "t", in: "write", on: "steam locomotive" }, { id: "pts.0", in: "slide", from: "right", on: "coal" },
          { id: "pic.boiler", emphasis: "highlight", on: "boiler" }, { id: "pic.chimney", emphasis: "circle", on: "chimney" }] },
      { say: "The steam pushes pistons that turn the wheels.",
        animate: [{ id: "pts.1", in: "slide", from: "right", on: "steam" }, { id: "pts.2", in: "slide", from: "right", on: "pistons" }, { id: "pts.2", emphasis: "underline", on: "wheels" }] },
    ]),
  },
  {
    id: "beta-process", name: "Beta: a process with arrows", note: "Three boxes joined by arrows, each popping in on its word; then one focused.",
    script: beta("From coal to motion", [
      { say: "Coal heats water into steam, and the steam makes motion.", layout: "three-col",
        elements: [{ id: "a", shape: "box", text: "Coal", slot: "left" }, { id: "b", shape: "circle", text: "Steam", slot: "middle" },
          { id: "c", shape: "pill", text: "Motion", slot: "right" }, { id: "ab", arrow: { from: "a", to: "b", label: "heat" } }, { id: "bc", arrow: { from: "b", to: "c" } }],
        animate: [{ id: "a", in: "pop", on: "coal" }, { id: "ab", in: "draw", on: "heats" }, { id: "b", in: "pop", on: "steam" },
          { id: "bc", in: "draw", on: "makes" }, { id: "c", in: "slide", from: "right", on: "motion" }] },
      { say: "Steam is the key to all of it.", animate: [{ id: "b", emphasis: "focus", on: "steam" }, { id: "b", emphasis: "enlarge", on: "key" }] },
    ]),
  },
  {
    id: "beta-compare", name: "Beta: compare two kinds", note: "A heading over two columns; each side's points come on as they are named.",
    script: beta("Two kinds of river", [
      { say: "India has two kinds of river: Himalayan and peninsular.", layout: "title-left-right",
        elements: [{ id: "h", text: "Two kinds of river", style: "heading", slot: "title" },
          { id: "hl", text: "Himalayan", style: "label", slot: "left" }, { id: "hp", list: ["Snow-fed", "Flow all year"], slot: "left" },
          { id: "pl", text: "Peninsular", style: "label", slot: "right" }, { id: "pp", list: ["Rain-fed", "Seasonal"], slot: "right" }],
        animate: [{ id: "h", in: "type" }, { id: "hl", in: "slide", from: "left", on: "himalayan" }, { id: "pl", in: "slide", from: "right", on: "peninsular" }] },
      { say: "Himalayan rivers are snow-fed and flow all year; peninsular rivers are rain-fed and seasonal.",
        animate: [{ id: "hp", in: "stagger", on: "snow-fed" }, { id: "pp", in: "stagger", on: "rain-fed" }, { id: "hp.1", emphasis: "highlight", on: "all year" }] },
    ]),
  },
  {
    id: "beta-numbers", name: "Beta: numbers and a chart", note: "Two big numbers in a grid, then bars coming in one by one.",
    script: beta("India's rivers", [
      { say: "The Ganga runs 2,525 kilometres and drains a quarter of the country.", layout: "grid-2x2",
        elements: [{ id: "n1", number: { value: "2,525 km", label: "length of the Ganga" }, slot: "tl" },
          { id: "n2", number: { value: "26%", label: "of India drained" }, slot: "tr" },
          { id: "b", bars: { title: "Length (km)", items: [["Ganga", 2525], ["Godavari", 1465], ["Krishna", 1400]] }, box: [0.1, 0.52, 0.8, 0.46] }],
        animate: [{ id: "n1", in: "pop", on: "2,525" }, { id: "n2", in: "pop", on: "quarter" }] },
      { say: "Compare it with the Godavari and the Krishna.",
        animate: [{ id: "b.0", in: "slide", from: "left" }, { id: "b.1", in: "slide", from: "left", on: "godavari" }, { id: "b.2", in: "slide", from: "left", on: "krishna" }, { id: "b.0", emphasis: "highlight", after: "b.2" }] },
    ]),
  },
  {
    id: "beta-law", name: "Beta: a law, then its steps", note: "An equation written in, underlined on its words, then a numbered list.",
    script: beta("Newton's second law", [
      { say: "Newton's second law: force is mass times acceleration.", layout: "title-body",
        elements: [{ id: "h", text: "Newton's second law", style: "heading", slot: "title" },
          { id: "e", equation: "F = ma", label: "force = mass × acceleration", slot: "body" }],
        animate: [{ id: "h", in: "rise" }, { id: "e", in: "write", on: "force" }, { id: "e", emphasis: "underline", on: "acceleration" }] },
      { say: "To use it: find the mass, find the acceleration, and multiply.", layout: "wide-right",
        elements: [{ id: "e2", equation: "F = ma", slot: "left" }, { id: "s", list: ["Find the mass", "Find the acceleration", "Multiply"], numbered: true, slot: "right" }],
        animate: [{ id: "e2", in: "fade" }, { id: "s.0", in: "slide", from: "right", on: "mass" }, { id: "s.1", in: "slide", from: "right", on: "acceleration" }, { id: "s.2", in: "pop", on: "multiply" }] },
    ]),
  },
  {
    id: "beta-timeline", name: "Beta: a timeline over a working", note: "A timeline across the top, its own size; points below it.",
    script: beta("Marc Bloch", [
      { say: "Marc Bloch lived from 1886 to 1944.", layout: "top-bottom",
        elements: [{ id: "tl", timeline: { title: "Marc Bloch 1886-1944", events: [["1886", "Born"], ["1944", "Died"]] }, slot: "top" },
          { id: "q", list: ["Geography → human history", "Shared attitudes + collective behaviour"], slot: "bottom" }],
        animate: [{ id: "tl", in: "fade" }] },
      { say: "He asked new questions: from geography to human history, and about shared attitudes.",
        animate: [{ id: "q.0", in: "slide", from: "left", on: "geography" }, { id: "q.1", in: "slide", from: "left", on: "shared attitudes" }] },
    ]),
  },
  {
    id: "beta-quote", name: "Beta: a quote and a callout", note: "A quote typed in the centre, then a callout pops in its own box.",
    script: beta("A historian's craft", [
      { say: "Bloch wrote that history is the science of men in time.", layout: "center",
        elements: [{ id: "q", text: "History is the science of men in time.", style: "quote", slot: "main" },
          { id: "c", text: "Marc Bloch, 1944", style: "callout", box: [0.55, 0.72, 0.4, 0.2] }],
        animate: [{ id: "q", in: "type", on: "history" }, { id: "c", in: "pop", after: "q" }] },
    ]),
  },
];

/** One beta element of each kind with its animation, to add to a beta experiment as a new slide. */
export const LAB_BETA_SNIPPETS: { op: string; beat: Record<string, unknown> }[] = [
  { op: "text: title, typed", beat: { say: "Here is the idea.", layout: "center", elements: [{ id: "t1", text: "The big idea", style: "title", slot: "main" }], animate: [{ id: "t1", in: "type" }] } },
  { op: "list: points sliding in on their words", beat: { say: "First rain, then rivers, then fields.", layout: "full",
    elements: [{ id: "l1", list: ["Rain", "Rivers", "Fields"], slot: "main" }], animate: [{ id: "l1.0", in: "slide", from: "left", on: "rain" }, { id: "l1.1", in: "slide", from: "left", on: "rivers" }, { id: "l1.2", in: "slide", from: "left", on: "fields" }] } },
  { op: "image with labels, highlighted", beat: { say: "Here the heart's left ventricle pumps the blood.", layout: "wide-left",
    elements: [{ id: "i1", image: { generate: "a human heart, front section", labels: ["left ventricle", "aorta"] }, slot: "left" }],
    animate: [{ id: "i1", in: "grow" }, { id: "i1.left-ventricle", emphasis: "highlight", on: "left ventricle" }] } },
  { op: "shapes joined by an arrow", beat: { say: "Cause leads to effect.", layout: "left-right",
    elements: [{ id: "s1", shape: "box", text: "Cause", slot: "left" }, { id: "s2", shape: "box", text: "Effect", slot: "right" }, { id: "a1", arrow: { from: "s1", to: "s2", label: "leads to" } }],
    animate: [{ id: "s1", in: "pop", on: "cause" }, { id: "a1", in: "draw", on: "leads" }, { id: "s2", in: "pop", on: "effect" }] } },
  { op: "number, popping", beat: { say: "Seventy percent of the planet is water.", layout: "center", elements: [{ id: "n1", number: { value: "70%", label: "of the planet is water" }, slot: "main" }], animate: [{ id: "n1", in: "pop", on: "seventy" }] } },
  { op: "bars, one by one", beat: { say: "Wheat, then rice, then maize.", layout: "full",
    elements: [{ id: "b1", bars: { items: [["Wheat", 110], ["Rice", 130], ["Maize", 35]] }, slot: "main" }], animate: [{ id: "b1", in: "stagger" }] } },
  { op: "equation, written and underlined", beat: { say: "Energy is mass times the speed of light squared.", layout: "center",
    elements: [{ id: "e1", equation: "E = mc^2", slot: "main" }], animate: [{ id: "e1", in: "write", on: "energy" }, { id: "e1", emphasis: "underline", on: "squared" }] } },
  { op: "timeline", beat: { say: "From 1526 to 1857.", layout: "full", elements: [{ id: "tl1", timeline: { events: [["1526", "Panipat"], ["1707", "Aurangzeb dies"], ["1857", "The revolt"]] }, slot: "main" }], animate: [{ id: "tl1", in: "fade" }] } },
  { op: "icon with a label", beat: { say: "Think of a seed.", layout: "center", elements: [{ id: "ic1", icon: "seed", label: "a seed", slot: "main" }], animate: [{ id: "ic1", in: "drop", on: "seed" }] } },
  { op: "callout in its own box", beat: { say: "Remember this.", elements: [{ id: "co1", text: "Remember this!", style: "callout", box: [0.6, 0.75, 0.38, 0.2] }], animate: [{ id: "co1", in: "pop", on: "remember" }] } },
  { op: "clear the board", beat: { say: "Let us start afresh.", clear: true } },
];
