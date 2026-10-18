/**
 * The Lab's examples, all on the beta engine (engine/BETA_ENGINE.md): slides of boxes, each thing animated on the
 * words that bring it. Grouped as the Lab lists them: one example for each entrance, emphasis, exit and timing rule,
 * one for each layout and each kind of element, and whole scenes as a lesson would have them (in several looks).
 * Each is a chapter as the Lab's editor reads it (lib/voice.ts readChapterScript); check-transcript.mjs compiles
 * every one and requires no warnings, so each element, part and word named is really there.
 */

export type LabPreset = { id: string; group: string; name: string; note: string; script: Record<string, unknown> };

type Beat = Record<string, unknown>;
const chapter = (title: string, beats: Beat[], style?: string) =>
  ({ engine: "beta", ...(style ? { style } : {}), region: null, chapter: { title, narration: title, map: false, beats } });
const ex = (group: string, id: string, name: string, note: string, title: string, beats: Beat[], style?: string): LabPreset =>
  ({ id, group, name, note, script: chapter(title, beats, style) });

export const LAB_GROUPS = ["Entrances", "Emphasis", "Exits and moves", "Timing", "Layouts", "Elements", "Scenes"] as const;

const E = "Entrances";
const M = "Emphasis";
const X = "Exits and moves";
const W = "Timing";
const L = "Layouts";
const K = "Elements";
const S = "Scenes";

export const LAB_EXAMPLES: LabPreset[] = [
  // ---------------- entrances: one each ----------------
  ex(E, "in-fade", "Fade", "Things fade in, each on its word.", "Fade", [
    { say: "First the sun, then the rain, then the harvest.", layout: "three-col",
      elements: [{ id: "a", text: "Sun", style: "heading", slot: "left" }, { id: "b", text: "Rain", style: "heading", slot: "middle" }, { id: "c", text: "Harvest", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "fade", on: "sun" }, { id: "b", in: "fade", on: "rain" }, { id: "c", in: "fade", on: "harvest" }] }]),
  ex(E, "in-slide", "Slide from each side", "From the left, the right, above and below.", "Slide", [
    { say: "Traders came from the west, from the east, from the north and from the south.", layout: "grid-2x2",
      elements: [{ id: "w", text: "West", style: "heading", slot: "tl" }, { id: "e", text: "East", style: "heading", slot: "tr" },
        { id: "n", text: "North", style: "heading", slot: "bl" }, { id: "s", text: "South", style: "heading", slot: "br" }],
      animate: [{ id: "w", in: "slide", from: "left", on: "west" }, { id: "e", in: "slide", from: "right", on: "east" },
        { id: "n", in: "slide", from: "up", on: "north" }, { id: "s", in: "slide", from: "down", on: "south" }] }]),
  ex(E, "in-rise-drop", "Rise and drop", "One rises from below, one drops from above.", "Rise and drop", [
    { say: "Warm air rises, and cold air sinks.", layout: "left-right",
      elements: [{ id: "w", text: "Warm air ↑", style: "heading", slot: "left" }, { id: "c", text: "Cold air ↓", style: "heading", slot: "right" }],
      animate: [{ id: "w", in: "rise", on: "warm" }, { id: "c", in: "drop", on: "cold" }] }]),
  ex(E, "in-pop", "Pop", "Grows in with a small overshoot: good for numbers and key words.", "Pop", [
    { say: "Three things matter: water, soil and sun.", layout: "three-col",
      elements: [{ id: "a", shape: "circle", text: "Water", slot: "left" }, { id: "b", shape: "circle", text: "Soil", slot: "middle" }, { id: "c", shape: "circle", text: "Sun", slot: "right" }],
      animate: [{ id: "a", in: "pop", on: "water" }, { id: "b", in: "pop", on: "soil" }, { id: "c", in: "pop", on: "sun" }] }]),
  ex(E, "in-grow", "Grow", "Grows from small: a picture or a big idea arriving.", "Grow", [
    { say: "Everything begins with a single seed.", layout: "center",
      elements: [{ id: "i", icon: "seed", label: "a seed", slot: "main" }],
      animate: [{ id: "i", in: "grow", on: "seed" }] }]),
  ex(E, "in-type", "Typewriter", "A sentence typed in letter by letter.", "Typewriter", [
    { say: "Write this down: knowledge is power.", layout: "center",
      elements: [{ id: "q", text: "Knowledge is power.", style: "title", slot: "main" }],
      animate: [{ id: "q", in: "type", on: "knowledge" }] }]),
  ex(E, "in-write", "Write", "Written in as by hand: titles and equations.", "Write", [
    { say: "Einstein's famous equation: energy equals mass times the speed of light squared.", layout: "title-body",
      elements: [{ id: "h", text: "Mass and energy", style: "heading", slot: "title" }, { id: "e", equation: "E = mc^2", slot: "body" }],
      animate: [{ id: "h", in: "write" }, { id: "e", in: "write", on: "energy" }] }]),
  ex(E, "in-draw", "Draw", "Outlines drawn, then filled: shapes and arrows.", "Draw", [
    { say: "Draw a box for the input, an arrow, and a box for the output.", layout: "left-right",
      elements: [{ id: "a", shape: "box", text: "Input", slot: "left" }, { id: "b", shape: "box", text: "Output", slot: "right" }, { id: "ab", arrow: { from: "a", to: "b" } }],
      animate: [{ id: "a", in: "draw", on: "input" }, { id: "ab", in: "draw", on: "arrow" }, { id: "b", in: "draw", on: "output" }] }]),
  ex(E, "in-stagger", "Stagger", "A list's items one after another, in one step.", "Stagger", [
    { say: "The water cycle has four stages.", layout: "full",
      elements: [{ id: "l", list: ["Evaporation", "Condensation", "Precipitation", "Collection"], numbered: true, slot: "main" }],
      animate: [{ id: "l", in: "stagger", on: "four stages" }] }]),
  ex(E, "in-appear", "Appear", "At once, with no motion: a quiet change.", "Appear", [
    { say: "Here is the answer.", layout: "center",
      elements: [{ id: "a", number: { value: "42", label: "the answer" }, slot: "main" }],
      animate: [{ id: "a", in: "appear", on: "answer" }] }]),

  // ---------------- emphasis: one each ----------------
  ex(M, "em-highlight", "Highlight", "A box round one item while it is talked about.", "Highlight", [
    { say: "Of these, the second is the most important.", layout: "full",
      elements: [{ id: "l", list: ["Saving", "Investing", "Spending"], slot: "main" }],
      animate: [{ id: "l", in: "stagger" }, { id: "l.1", emphasis: "highlight", on: "second" }] }]),
  ex(M, "em-circle", "Circle", "A ring round a number.", "Circle", [
    { say: "Look at this number: almost half.", layout: "center",
      elements: [{ id: "n", number: { value: "48%", label: "of the forest lost" }, slot: "main" }],
      animate: [{ id: "n", in: "fade" }, { id: "n", emphasis: "circle", on: "half" }] }]),
  ex(M, "em-underline", "Underline", "A line under the words that matter.", "Underline", [
    { say: "The key idea is that energy is never lost.", layout: "center",
      elements: [{ id: "t", text: "Energy is never lost, only changed.", style: "title", slot: "main" }],
      animate: [{ id: "t", in: "fade" }, { id: "t", emphasis: "underline", on: "never lost" }] }]),
  ex(M, "em-pulse", "Pulse", "A quick swell and colour.", "Pulse", [
    { say: "Notice the heart of the system.", layout: "three-col",
      elements: [{ id: "a", shape: "box", text: "Lungs", slot: "left" }, { id: "b", shape: "circle", text: "Heart", slot: "middle" }, { id: "c", shape: "box", text: "Body", slot: "right" }],
      animate: [{ id: "a", in: "fade" }, { id: "b", in: "fade", with: "a" }, { id: "c", in: "fade", with: "a" }, { id: "b", emphasis: "pulse", on: "heart" }] }]),
  ex(M, "em-flash", "Flash", "A burst of lines: a moment of discovery.", "Flash", [
    { say: "And then, eureka!", layout: "center",
      elements: [{ id: "t", text: "Eureka!", style: "title", slot: "main" }],
      animate: [{ id: "t", in: "pop" }, { id: "t", emphasis: "flash", on: "eureka" }] }]),
  ex(M, "em-color", "Colour change", "Turns a colour to mark a change of state.", "Colour", [
    { say: "The water heats up and turns to steam.", layout: "center",
      elements: [{ id: "s", shape: "circle", text: "Water", slot: "main" }],
      animate: [{ id: "s", in: "fade" }, { id: "s", emphasis: "color", color: "ROSE", on: "heats" }] }]),
  ex(M, "em-dim", "Dim the others", "Everything else fades back.", "Dim the others", [
    { say: "Three kingdoms rose, but only one lasted: Magadha.", layout: "three-col",
      elements: [{ id: "a", text: "Kosala", style: "heading", slot: "left" }, { id: "b", text: "Magadha", style: "heading", slot: "middle" }, { id: "c", text: "Vatsa", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "fade" }, { id: "b", in: "fade", with: "a" }, { id: "c", in: "fade", with: "a" }, { id: "b", emphasis: "dim-others", on: "magadha" }] }]),
  ex(M, "em-focus", "Focus", "Dims the rest and boxes the one.", "Focus", [
    { say: "Of the planets, Earth is the only one with liquid water.", layout: "three-col",
      elements: [{ id: "a", shape: "circle", text: "Venus", slot: "left" }, { id: "b", shape: "circle", text: "Earth", slot: "middle" }, { id: "c", shape: "circle", text: "Mars", slot: "right" }],
      animate: [{ id: "a", in: "pop" }, { id: "b", in: "pop" }, { id: "c", in: "pop" }, { id: "b", emphasis: "focus", on: "earth" }] }]),
  ex(M, "em-enlarge", "Enlarge", "Swells and settles back.", "Enlarge", [
    { say: "Prices went up, sharply.", layout: "center",
      elements: [{ id: "n", number: { value: "+300%", label: "price of grain" }, slot: "main" }],
      animate: [{ id: "n", in: "fade" }, { id: "n", emphasis: "enlarge", on: "sharply" }] }]),
  ex(M, "em-many", "Several in one line", "Highlight, underline and circle as the words come.", "Several marks", [
    { say: "Supply falls, demand rises, and so the price goes up.", layout: "full",
      elements: [{ id: "l", list: ["Supply falls", "Demand rises", "Price goes up"], slot: "main" }],
      animate: [{ id: "l", in: "stagger" }, { id: "l.0", emphasis: "underline", on: "supply" }, { id: "l.1", emphasis: "underline", on: "demand" }, { id: "l.2", emphasis: "circle", on: "price" }] }]),

  // ---------------- exits and moves ----------------
  ex(X, "out-all", "Four ways to leave", "Fade, slide away, shrink, unwrite.", "Exits", [
    { say: "Four ideas are on the board.", layout: "grid-2x2",
      elements: [{ id: "a", text: "Fade", style: "heading", slot: "tl" }, { id: "b", text: "Slide", style: "heading", slot: "tr" }, { id: "c", text: "Shrink", style: "heading", slot: "bl" }, { id: "d", text: "Unwrite", style: "heading", slot: "br" }],
      animate: [{ id: "a", in: "fade" }, { id: "b", in: "fade", with: "a" }, { id: "c", in: "fade", with: "a" }, { id: "d", in: "fade", with: "a" }] },
    { say: "One fades, one slides away, one shrinks, and one is unwritten.",
      animate: [{ id: "a", out: "fade", on: "fades" }, { id: "b", out: "slide", to: "right", on: "slides" }, { id: "c", out: "shrink", on: "shrinks" }, { id: "d", out: "unwrite", on: "unwritten" }] }]),
  ex(X, "move-slot", "Move to another slot", "A picture of an idea moves aside to make room.", "Move", [
    { say: "Here is the cell.", layout: "left-right",
      elements: [{ id: "c", shape: "circle", text: "Cell", slot: "left" }],
      animate: [{ id: "c", in: "pop", on: "cell" }] },
    { say: "Now it moves to the right, and its parts come in.",
      elements: [{ id: "l", list: ["Nucleus", "Membrane", "Cytoplasm"], slot: "left" }],
      animate: [{ id: "c", move: "right", on: "moves" }, { id: "l", in: "stagger", on: "parts" }] }]),
  ex(X, "clear", "Clear the board", "Everything leaves at the start of the line.", "Clear", [
    { say: "Here are our notes.", layout: "full",
      elements: [{ id: "l", list: ["Point one", "Point two", "Point three"], slot: "main" }],
      animate: [{ id: "l", in: "stagger" }] },
    { say: "Let us clear the board and start afresh.", clear: true }]),
  ex(X, "slides", "Slide after slide", "A new layout clears the old slide by itself.", "Slides", [
    { say: "First slide: the question.", layout: "center",
      elements: [{ id: "q", text: "Why do seasons change?", style: "title", slot: "main" }], animate: [{ id: "q", in: "type" }] },
    { say: "Second slide: two answers side by side.", layout: "left-right",
      elements: [{ id: "a", text: "Distance from the sun?", style: "body", slot: "left" }, { id: "b", text: "The tilt of the earth!", style: "callout", slot: "right" }],
      animate: [{ id: "a", in: "slide", from: "left", on: "two answers" }, { id: "b", in: "pop", after: "a" }] },
    { say: "Third slide: the answer.", layout: "center",
      elements: [{ id: "c", text: "The tilt of the earth's axis.", style: "title", slot: "main" }], animate: [{ id: "c", in: "write", on: "answer" }] }]),

  // ---------------- timing ----------------
  ex(W, "t-on", "On words", "Each item lands on its own word.", "On words", [
    { say: "Iron, copper, and gold were the metals of the age.", layout: "three-col",
      elements: [{ id: "a", text: "Iron", style: "heading", slot: "left" }, { id: "b", text: "Copper", style: "heading", slot: "middle" }, { id: "c", text: "Gold", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "pop", on: "iron" }, { id: "b", in: "pop", on: "copper" }, { id: "c", in: "pop", on: "gold" }] }]),
  ex(W, "t-with", "Together (with)", "Two things start at the same moment.", "Together", [
    { say: "Action and reaction are equal and opposite.", layout: "left-right",
      elements: [{ id: "a", text: "Action →", style: "heading", slot: "left" }, { id: "b", text: "← Reaction", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "slide", from: "left", on: "action" }, { id: "b", in: "slide", from: "right", with: "a" }] }]),
  ex(W, "t-after", "One after another (after, delay)", "Each waits for the one before, with a pause.", "After", [
    { say: "Step by step: plan, then build, then test.", layout: "three-col",
      elements: [{ id: "a", shape: "pill", text: "Plan", slot: "left" }, { id: "b", shape: "pill", text: "Build", slot: "middle" }, { id: "c", shape: "pill", text: "Test", slot: "right" }],
      animate: [{ id: "a", in: "pop" }, { id: "b", in: "pop", after: "a", delay: 0.4 }, { id: "c", in: "pop", after: "b", delay: 0.4 }] }]),
  ex(W, "t-dur", "Slow and fast (dur)", "The same entrance, quick and slow.", "Duration", [
    { say: "A quick change, and a slow one.", layout: "left-right",
      elements: [{ id: "a", text: "Quick", style: "heading", slot: "left" }, { id: "b", text: "Slow", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "rise", on: "quick", dur: 0.3 }, { id: "b", in: "rise", on: "slow", dur: 2.5 }] }]),

  // ---------------- layouts: one each ----------------
  ex(L, "l-full", "full", "One slot: the whole board.", "full", [
    { say: "One idea fills the whole board.", layout: "full", elements: [{ id: "t", text: "One idea, the whole board", style: "title", slot: "main" }], animate: [{ id: "t", in: "fade" }] }]),
  ex(L, "l-center", "center", "The middle of the board, with room round it.", "center", [
    { say: "A quote sits in the centre.", layout: "center", elements: [{ id: "t", text: "Be the change you wish to see.", style: "quote", slot: "main" }], animate: [{ id: "t", in: "type" }] }]),
  ex(L, "l-left-right", "left-right", "Two halves.", "left-right", [
    { say: "On the left the problem, on the right the solution.", layout: "left-right",
      elements: [{ id: "a", text: "Problem", style: "heading", slot: "left" }, { id: "b", text: "Solution", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "slide", from: "left", on: "problem" }, { id: "b", in: "slide", from: "right", on: "solution" }] }]),
  ex(L, "l-wide-left", "wide-left", "A big left side (62%) and a narrow right.", "wide-left", [
    { say: "A large picture on the left, notes on the right.", layout: "wide-left",
      elements: [{ id: "a", shape: "box", text: "A large picture", slot: "left" }, { id: "b", list: ["Note one", "Note two"], slot: "right" }],
      animate: [{ id: "a", in: "grow", on: "picture" }, { id: "b", in: "stagger", on: "notes" }] }]),
  ex(L, "l-wide-right", "wide-right", "A narrow left and a big right side.", "wide-right", [
    { say: "A short label on the left, a large chart on the right.", layout: "wide-right",
      elements: [{ id: "a", text: "Rainfall (cm)", style: "label", slot: "left" }, { id: "b", bars: { items: [["June", 15], ["July", 30], ["August", 25]] }, slot: "right" }],
      animate: [{ id: "a", in: "fade", on: "label" }, { id: "b", in: "stagger", on: "chart" }] }]),
  ex(L, "l-top-bottom", "top-bottom", "A band across the top, more below.", "top-bottom", [
    { say: "A timeline across the top, and what it means below.", layout: "top-bottom",
      elements: [{ id: "t", timeline: { events: [["1757", "Plassey"], ["1857", "Revolt"], ["1947", "Independence"]] }, slot: "top" },
        { id: "b", text: "Two hundred years of change", style: "heading", slot: "bottom" }],
      animate: [{ id: "t", in: "fade", on: "timeline" }, { id: "b", in: "rise", on: "means" }] }]),
  ex(L, "l-title-body", "title-body", "A title band and a body.", "title-body", [
    { say: "A title on top, and the body below it.", layout: "title-body",
      elements: [{ id: "h", text: "The title", style: "heading", slot: "title" }, { id: "b", list: ["The body's first point", "Its second point"], slot: "body" }],
      animate: [{ id: "h", in: "write", on: "title" }, { id: "b", in: "stagger", on: "body" }] }]),
  ex(L, "l-title-left-right", "title-left-right", "A title over two columns.", "title-left-right", [
    { say: "A title over two columns: before and after.", layout: "title-left-right",
      elements: [{ id: "h", text: "Before and after", style: "heading", slot: "title" }, { id: "a", text: "Before", style: "label", slot: "left" }, { id: "b", text: "After", style: "label", slot: "right" }],
      animate: [{ id: "h", in: "write" }, { id: "a", in: "fade", on: "before" }, { id: "b", in: "fade", on: "after" }] }]),
  ex(L, "l-three-col", "three-col", "Three equal columns.", "three-col", [
    { say: "Three columns: past, present and future.", layout: "three-col",
      elements: [{ id: "a", text: "Past", style: "heading", slot: "left" }, { id: "b", text: "Present", style: "heading", slot: "middle" }, { id: "c", text: "Future", style: "heading", slot: "right" }],
      animate: [{ id: "a", in: "rise", on: "past" }, { id: "b", in: "rise", on: "present" }, { id: "c", in: "rise", on: "future" }] }]),
  ex(L, "l-grid", "grid-2x2", "Four quarters.", "grid-2x2", [
    { say: "Four quarters: spring, summer, autumn and winter.", layout: "grid-2x2",
      elements: [{ id: "a", text: "Spring", style: "heading", slot: "tl" }, { id: "b", text: "Summer", style: "heading", slot: "tr" }, { id: "c", text: "Autumn", style: "heading", slot: "bl" }, { id: "d", text: "Winter", style: "heading", slot: "br" }],
      animate: [{ id: "a", in: "pop", on: "spring" }, { id: "b", in: "pop", on: "summer" }, { id: "c", in: "pop", on: "autumn" }, { id: "d", in: "pop", on: "winter" }] }]),
  ex(L, "l-focus-side", "focus-side", "A big main area (70%) and a side strip.", "focus-side", [
    { say: "The main thing large, and a side note.", layout: "focus-side",
      elements: [{ id: "a", shape: "circle", text: "The main thing", slot: "main" }, { id: "b", text: "A side note", style: "caption", slot: "side" }],
      animate: [{ id: "a", in: "grow", on: "main" }, { id: "b", in: "fade", on: "side note" }] }]),
  ex(L, "l-box", "Own box", "An element in its own box, over the slots: [x, y, w, h].", "Own box", [
    { say: "A picture of the idea, and a note in the corner.", layout: "full",
      elements: [{ id: "a", shape: "box", text: "The idea", slot: "main" }, { id: "n", text: "Note: see page 12", style: "callout", box: [0.62, 0.78, 0.36, 0.18] }],
      animate: [{ id: "a", in: "grow", on: "idea" }, { id: "n", in: "pop", on: "note" }] }]),
  ex(L, "l-stack", "Stacked in one slot", "Several elements in one slot stack down it.", "Stacked", [
    { say: "A heading, a number and a sentence, one under another.", layout: "center",
      elements: [{ id: "h", text: "Literacy", style: "heading", slot: "main" }, { id: "n", number: { value: "77%", label: "of adults can read" }, slot: "main" }, { id: "t", text: "Up from 18% in 1951.", style: "body", slot: "main" }],
      animate: [{ id: "h", in: "fade", on: "heading" }, { id: "n", in: "pop", on: "number" }, { id: "t", in: "type", on: "sentence" }] }]),

  // ---------------- elements: one each ----------------
  ex(K, "k-text", "Text styles", "title, heading, body, callout, caption, quote, label.", "Text styles", [
    { say: "Seven styles of text, from a title to a label.", layout: "full",
      elements: [{ id: "a", text: "A title", style: "title", slot: "main" }, { id: "b", text: "A heading", style: "heading", slot: "main" },
        { id: "c", text: "Body text for sentences", style: "body", slot: "main" }, { id: "d", text: "A callout", style: "callout", slot: "main" },
        { id: "e", text: "a caption under something", style: "caption", slot: "main" }],
      animate: [{ id: "a", in: "fade" }, { id: "b", in: "fade", after: "a" }, { id: "c", in: "fade", after: "b" }, { id: "d", in: "pop", after: "c" }, { id: "e", in: "fade", after: "d" }] },
    { say: "A quote, and a label.", layout: "left-right",
      elements: [{ id: "q", text: "Words in a quote", style: "quote", slot: "left" }, { id: "l", text: "A LABEL", style: "label", slot: "right" }],
      animate: [{ id: "q", in: "type", on: "quote" }, { id: "l", in: "fade", on: "label" }] }]),
  ex(K, "k-list", "Lists", "Bulleted and numbered; items by number (l.0, l.1).", "Lists", [
    { say: "A bulleted list and a numbered list.", layout: "left-right",
      elements: [{ id: "a", list: ["Apples", "Oranges", "Mangoes"], slot: "left" }, { id: "b", list: ["Wash", "Peel", "Eat"], numbered: true, slot: "right" }],
      animate: [{ id: "a.0", in: "slide", from: "left", on: "bulleted" }, { id: "a.1", in: "slide", from: "left", after: "a.0" }, { id: "a.2", in: "slide", from: "left", after: "a.1" },
        { id: "b", in: "stagger", on: "numbered" }] }]),
  ex(K, "k-image", "Image with labels", "Made by the image model; each label is a part (pic.boiler).", "A labelled picture", [
    { say: "A steam locomotive: the boiler, the chimney and the driving wheels.", layout: "wide-left",
      elements: [{ id: "pic", image: { generate: "a steam locomotive, side view", labels: ["boiler", "chimney", "driving wheels"] }, slot: "left" },
        { id: "t", text: "Steam locomotive", style: "heading", slot: "right" }],
      animate: [{ id: "pic", in: "grow" }, { id: "t", in: "write", with: "pic" }, { id: "pic.boiler", emphasis: "highlight", on: "boiler" },
        { id: "pic.chimney", emphasis: "circle", on: "chimney" }, { id: "pic.driving-wheels", emphasis: "highlight", on: "driving wheels" }] }]),
  ex(K, "k-scene", "Image as a scene", "A whole scene drawn edge to edge.", "A scene", [
    { say: "A busy market in a medieval town.", layout: "full",
      elements: [{ id: "s", image: { generate: "a busy medieval market square with stalls and people", scene: true }, slot: "main" }],
      animate: [{ id: "s", in: "fade", on: "market" }] }]),
  ex(K, "k-icon", "Icons", "Small drawings of things, with labels.", "Icons", [
    { say: "A farmer needs a plough, seeds and water.", layout: "three-col",
      elements: [{ id: "a", icon: "plough", label: "plough", slot: "left" }, { id: "b", icon: "seeds", label: "seeds", slot: "middle" }, { id: "c", icon: "water bucket", label: "water", slot: "right" }],
      animate: [{ id: "a", in: "drop", on: "plough" }, { id: "b", in: "drop", on: "seeds" }, { id: "c", in: "drop", on: "water" }] }]),
  ex(K, "k-number", "Numbers", "Big values with a label.", "Numbers", [
    { say: "India has 1.4 billion people in 28 states.", layout: "left-right",
      elements: [{ id: "a", number: { value: "1.4 bn", label: "people" }, slot: "left" }, { id: "b", number: { value: "28", label: "states" }, slot: "right" }],
      animate: [{ id: "a", in: "pop", on: "1.4 billion" }, { id: "b", in: "pop", on: "28" }] }]),
  ex(K, "k-shapes", "Shapes", "Box, circle and pill, with words inside.", "Shapes", [
    { say: "A box, a circle and a pill.", layout: "three-col",
      elements: [{ id: "a", shape: "box", text: "Box", slot: "left" }, { id: "b", shape: "circle", text: "Circle", slot: "middle" }, { id: "c", shape: "pill", text: "Pill", slot: "right" }],
      animate: [{ id: "a", in: "draw", on: "box" }, { id: "b", in: "draw", on: "circle" }, { id: "c", in: "draw", on: "pill" }] }]),
  ex(K, "k-equation", "Equations", "TeX, written in; with a label.", "Equations", [
    { say: "The area of a circle is pi r squared.", layout: "center",
      elements: [{ id: "e", equation: "A = \\pi r^2", label: "area of a circle", slot: "main" }],
      animate: [{ id: "e", in: "write", on: "area" }, { id: "e", emphasis: "underline", on: "pi r squared" }] }]),
  ex(K, "k-bars", "Bar chart", "Bars in proportion; each bar a part (b.0).", "Bar chart", [
    { say: "Rice, wheat and maize: rice leads.", layout: "full",
      elements: [{ id: "b", bars: { title: "Harvest (million tonnes)", items: [["Rice", 130], ["Wheat", 110], ["Maize", 35]] }, slot: "main" }],
      animate: [{ id: "b.0", in: "slide", from: "left", on: "rice" }, { id: "b.1", in: "slide", from: "left", on: "wheat" }, { id: "b.2", in: "slide", from: "left", on: "maize" }, { id: "b.0", emphasis: "highlight", on: "leads" }] }]),
  ex(K, "k-arrows", "Arrows", "Arrows join elements, with a label.", "Arrows", [
    { say: "Sunlight feeds the plant, and the plant feeds the cow.", layout: "three-col",
      elements: [{ id: "a", icon: "sun", label: "sunlight", slot: "left" }, { id: "b", icon: "plant", label: "plant", slot: "middle" }, { id: "c", icon: "cow", label: "cow", slot: "right" },
        { id: "ab", arrow: { from: "a", to: "b", label: "energy" } }, { id: "bc", arrow: { from: "b", to: "c", label: "food" } }],
      animate: [{ id: "a", in: "fade", on: "sunlight" }, { id: "ab", in: "draw", on: "feeds" }, { id: "b", in: "fade", on: "plant" }, { id: "bc", in: "draw", on: "and" }, { id: "c", in: "fade", on: "cow" }] }]),
  ex(K, "k-timeline", "Timeline", "Dates in proportion, a range and shaded periods.", "Timeline", [
    { say: "The Mughals ruled from 1526 to 1857.", layout: "full",
      elements: [{ id: "t", timeline: { title: "The Mughals", range: ["1500", "1870"], events: [["1526", "Panipat"], ["1556", "Akbar"], ["1707", "Aurangzeb dies"], ["1857", "Revolt"]],
        spans: [["1526", "1857", "Mughal Empire"], ["1757", "1857", "Company rule"]] }, slot: "main" }],
      animate: [{ id: "t", in: "fade", on: "mughals" }] }]),

  // ---------------- whole scenes ----------------
  ex(S, "s-history", "History: a life and its work", "A timeline, then the person's ideas.", "Marc Bloch", [
    { say: "Marc Bloch lived from 1886 to 1944.", layout: "top-bottom",
      elements: [{ id: "tl", timeline: { title: "Marc Bloch, 1886-1944", events: [["1886", "Born"], ["1929", "Annales founded"], ["1944", "Died"]] }, slot: "top" },
        { id: "q", list: ["Geography shapes history", "Ordinary lives matter", "Shared attitudes"], slot: "bottom" }],
      animate: [{ id: "tl", in: "fade" }] },
    { say: "He taught that geography shapes history, that ordinary lives matter, and that attitudes are shared.",
      animate: [{ id: "q.0", in: "slide", from: "left", on: "geography" }, { id: "q.1", in: "slide", from: "left", on: "ordinary" }, { id: "q.2", in: "slide", from: "left", on: "attitudes" }] }], "parchment"),
  ex(S, "s-biology", "Biology: the heart", "A labelled diagram, its parts pointed at in turn.", "The heart", [
    { say: "The heart has four chambers. Blood leaves the left ventricle through the aorta.", layout: "wide-left",
      elements: [{ id: "h", image: { generate: "a human heart in front section", labels: ["left ventricle", "right atrium", "aorta"] }, slot: "left" },
        { id: "t", text: "The heart", style: "heading", slot: "right" }, { id: "n", number: { value: "4", label: "chambers" }, slot: "right" }],
      animate: [{ id: "h", in: "grow" }, { id: "t", in: "write", with: "h" }, { id: "n", in: "pop", on: "four chambers" },
        { id: "h.left-ventricle", emphasis: "highlight", on: "left ventricle" }, { id: "h.aorta", emphasis: "circle", on: "aorta" }] }], "lab"),
  ex(S, "s-physics", "Physics: a law and its use", "The law written in, then its steps.", "Newton's second law", [
    { say: "Newton's second law: force is mass times acceleration.", layout: "title-body",
      elements: [{ id: "h", text: "Newton's second law", style: "heading", slot: "title" }, { id: "e", equation: "F = ma", label: "force = mass × acceleration", slot: "body" }],
      animate: [{ id: "h", in: "rise" }, { id: "e", in: "write", on: "force" }, { id: "e", emphasis: "underline", on: "acceleration" }] },
    { say: "A two kilogram ball pushed at three metres per second squared needs six newtons.", layout: "wide-right",
      elements: [{ id: "e2", equation: "F = 2 \\times 3", slot: "left" }, { id: "r", number: { value: "6 N", label: "the force needed" }, slot: "right" }],
      animate: [{ id: "e2", in: "write", on: "two kilogram" }, { id: "r", in: "pop", on: "six newtons" }, { id: "r", emphasis: "flash", after: "r" }] }], "blueprint"),
  ex(S, "s-chemistry", "Chemistry: a reaction", "Reactants, an arrow, products.", "Photosynthesis", [
    { say: "Carbon dioxide and water, with sunlight, make glucose and oxygen.", layout: "left-right",
      elements: [{ id: "a", list: ["Carbon dioxide", "Water"], slot: "left" }, { id: "b", list: ["Glucose", "Oxygen"], slot: "right" }, { id: "ab", arrow: { from: "a", to: "b", label: "sunlight" } }],
      animate: [{ id: "a.0", in: "fade", on: "carbon dioxide" }, { id: "a.1", in: "fade", on: "water" }, { id: "ab", in: "draw", on: "sunlight" },
        { id: "b.0", in: "pop", on: "glucose" }, { id: "b.1", in: "pop", on: "oxygen" }] }], "whiteboard"),
  ex(S, "s-geography", "Geography: a data story", "Numbers, then a chart, then the point.", "India's rivers", [
    { say: "The Ganga runs 2,525 kilometres and drains a quarter of the country.", layout: "grid-2x2",
      elements: [{ id: "n1", number: { value: "2,525 km", label: "length of the Ganga" }, slot: "tl" }, { id: "n2", number: { value: "26%", label: "of India drained" }, slot: "tr" },
        { id: "b", bars: { title: "Length (km)", items: [["Ganga", 2525], ["Godavari", 1465], ["Krishna", 1400]] }, box: [0.1, 0.52, 0.8, 0.46] }],
      animate: [{ id: "n1", in: "pop", on: "2,525" }, { id: "n2", in: "pop", on: "quarter" }] },
    { say: "Compare it with the Godavari and the Krishna: the Ganga is far the longest.",
      animate: [{ id: "b.0", in: "slide", from: "left" }, { id: "b.1", in: "slide", from: "left", on: "godavari" }, { id: "b.2", in: "slide", from: "left", on: "krishna" }, { id: "b.0", emphasis: "highlight", on: "longest" }] }], "atlas"),
  ex(S, "s-economics", "Economics: cause and effect", "A chain of boxes, each arrow on its word.", "Inflation", [
    { say: "More money chasing the same goods pushes prices up, and wages lag behind.", layout: "three-col",
      elements: [{ id: "a", shape: "box", text: "More money", slot: "left" }, { id: "b", shape: "box", text: "Prices rise", slot: "middle" }, { id: "c", shape: "box", text: "Wages lag", slot: "right" },
        { id: "ab", arrow: { from: "a", to: "b" } }, { id: "bc", arrow: { from: "b", to: "c" } }],
      animate: [{ id: "a", in: "pop", on: "more money" }, { id: "ab", in: "draw", on: "pushes" }, { id: "b", in: "pop", on: "prices" }, { id: "bc", in: "draw", on: "and" }, { id: "c", in: "pop", on: "wages" }] },
    { say: "So the real cost falls on the workers.", animate: [{ id: "c", emphasis: "focus", on: "workers" }] }], "vox"),
  ex(S, "s-vocab", "A new word", "The word, its meaning, an example.", "Surplus", [
    { say: "A new word: surplus. It means more than you need.", layout: "title-body",
      elements: [{ id: "w", text: "Surplus", style: "title", slot: "title" }, { id: "m", text: "more than you need", style: "callout", slot: "body" }, { id: "e", text: "A farmer with extra grain to sell has a surplus.", style: "caption", slot: "body" }],
      animate: [{ id: "w", in: "type", on: "surplus" }, { id: "m", in: "pop", on: "means" }, { id: "e", in: "fade", after: "m", delay: 0.5 }] }], "chalkboard"),
  ex(S, "s-quiz", "A question with options", "The question, the options, then the answer.", "Quick question", [
    { say: "Which gas do plants take in? Oxygen, carbon dioxide, or nitrogen?", layout: "title-body",
      elements: [{ id: "q", text: "Which gas do plants take in?", style: "heading", slot: "title" }, { id: "o", list: ["Oxygen", "Carbon dioxide", "Nitrogen"], numbered: true, slot: "body" }],
      animate: [{ id: "q", in: "type" }, { id: "o.0", in: "slide", from: "left", on: "oxygen" }, { id: "o.1", in: "slide", from: "left", on: "carbon dioxide" }, { id: "o.2", in: "slide", from: "left", on: "nitrogen" }], pause: 2 },
    { say: "The answer is carbon dioxide.", animate: [{ id: "o.1", emphasis: "focus", on: "carbon dioxide" }] }], "cardboard"),
  ex(S, "s-compare", "Compare two sides", "Pros and cons in two columns.", "Cities: pros and cons", [
    { say: "Cities offer jobs and schools, but bring crowding and pollution.", layout: "title-left-right",
      elements: [{ id: "h", text: "Life in cities", style: "heading", slot: "title" }, { id: "pl", text: "Good", style: "label", slot: "left" }, { id: "p", list: ["Jobs", "Schools"], slot: "left" },
        { id: "cl", text: "Bad", style: "label", slot: "right" }, { id: "c", list: ["Crowding", "Pollution"], slot: "right" }],
      animate: [{ id: "h", in: "write" }, { id: "pl", in: "fade", with: "h" }, { id: "cl", in: "fade", with: "h" },
        { id: "p.0", in: "rise", on: "jobs" }, { id: "p.1", in: "rise", on: "schools" }, { id: "c.0", in: "rise", on: "crowding" }, { id: "c.1", in: "rise", on: "pollution" }] }], "whiteboard"),
  ex(S, "s-process", "A process in steps", "Numbered steps, each on its word, the last one marked.", "Making paper", [
    { say: "To make paper: pulp the wood, press it flat, then dry the sheets.", layout: "wide-right",
      elements: [{ id: "i", icon: "paper roll", label: "paper", slot: "left" }, { id: "s", list: ["Pulp the wood", "Press it flat", "Dry the sheets"], numbered: true, slot: "right" }],
      animate: [{ id: "i", in: "grow", on: "paper" }, { id: "s.0", in: "slide", from: "right", on: "pulp" }, { id: "s.1", in: "slide", from: "right", on: "press" }, { id: "s.2", in: "slide", from: "right", on: "dry" }] }], "cardboard"),
  ex(S, "s-quote", "A quote and who said it", "Typed in the centre, the source in its own box.", "A historian's craft", [
    { say: "Bloch wrote that history is the science of men in time.", layout: "center",
      elements: [{ id: "q", text: "History is the science of men in time.", style: "quote", slot: "main" }, { id: "c", text: "Marc Bloch, 1944", style: "callout", box: [0.55, 0.74, 0.4, 0.2] }],
      animate: [{ id: "q", in: "type", on: "history" }, { id: "c", in: "pop", after: "q" }] }], "parchment"),
  ex(S, "s-recap", "A recap", "Four key points in a grid, each on its word.", "Recap", [
    { say: "To sum up: rivers gave water, surplus grew, towns rose, and trade spread.", layout: "grid-2x2",
      elements: [{ id: "a", text: "Rivers gave water", style: "heading", slot: "tl" }, { id: "b", text: "Surplus grew", style: "heading", slot: "tr" },
        { id: "c", text: "Towns rose", style: "heading", slot: "bl" }, { id: "d", text: "Trade spread", style: "heading", slot: "br" }],
      animate: [{ id: "a", in: "pop", on: "rivers" }, { id: "b", in: "pop", on: "surplus" }, { id: "c", in: "pop", on: "towns" }, { id: "d", in: "pop", on: "trade" }] }], "chalkboard"),
  ex(S, "s-space", "Space: scale", "Big numbers and a comparison.", "The solar system", [
    { say: "The sun is 109 times wider than the earth, and light from it takes eight minutes to reach us.", layout: "left-right",
      elements: [{ id: "a", number: { value: "109×", label: "wider than the earth" }, slot: "left" }, { id: "b", number: { value: "8 min", label: "for sunlight to reach us" }, slot: "right" }],
      animate: [{ id: "a", in: "grow", on: "109" }, { id: "b", in: "pop", on: "eight minutes" }] },
    { say: "Picture the planets in order from the sun.", layout: "full",
      elements: [{ id: "p", list: ["Mercury", "Venus", "Earth", "Mars"], numbered: true, slot: "main" }],
      animate: [{ id: "p", in: "stagger", on: "planets" }, { id: "p.2", emphasis: "highlight", after: "p" }] }], "cosmos"),
  ex(S, "s-before-after", "Before and after", "Two states with an arrow, the change marked.", "The Green Revolution", [
    { say: "Before the Green Revolution, India imported grain; after it, India fed itself.", layout: "left-right",
      elements: [{ id: "a", text: "Before: imports", style: "heading", slot: "left" }, { id: "b", text: "After: self-sufficient", style: "heading", slot: "right" }, { id: "ab", arrow: { from: "a", to: "b", label: "1960s" } }],
      animate: [{ id: "a", in: "slide", from: "left", on: "before" }, { id: "ab", in: "draw", on: "green revolution" }, { id: "b", in: "slide", from: "right", on: "after" }, { id: "b", emphasis: "color", color: "GREEN", on: "fed" }] }], "atlas"),
];

/** One element of each kind with its animation, to add to an experiment as a new beat ("Add a beat with"). */
export const LAB_SNIPPETS: { op: string; beat: Record<string, unknown> }[] = [
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
