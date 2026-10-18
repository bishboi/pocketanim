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
