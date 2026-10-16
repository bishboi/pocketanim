// The planned transcript (lib/learningmap.ts, lib/storyplan.ts, lib/coverage.ts), without a model:
//  - the book's items are found by code, and the learning map places every one (a left-out item gets a goal);
//  - a goal whose items lie in two sections is taught in each, from its own text;
//  - the story plan places every book question once, and a section's request carries its plan and goals;
//  - the coverage check keeps only a section's own reported goals, and a patch lands after the named sentence.
//   npm run check:story
import assert from "node:assert/strict";

const { bookSections, sectionRequest, transcriptPrompt, withoutExercises } = await import("../lib/transcript.ts");
const { sourceItems, readLearningMap } = await import("../lib/learningmap.ts");
const { readStoryPlan, sectionPlanText } = await import("../lib/storyplan.ts");
const { goalsTaught, insertAfterLine } = await import("../lib/coverage.ts");
const { linesOf } = await import("../lib/lines.ts");

const book = [
  "# From Villages to Cities", "",
  "## The River Valleys", "",
  "The first farmers settled near the **Indus**. The floods left rich **silt**. ".repeat(12), "",
  "[FIGURE fig1: The Indus valley]", "",
  "Do you know?", "The Nile flood came at the same time every year.", "",
  "## The First Cities", "",
  "Cities such as **Harappa** had drains and a **granary**. ".repeat(14), "",
  "Activity", "Draw a plan of your street.", "",
  "## Exercises", "",
  "1. Why did farmers settle near rivers?",
  "2. Which of these was found in Harappa?", "(a) Iron (b) Drains (c) Coins (d) Paper",
].join("\n");
const sections = bookSections(book, 10);
assert.ok(sections.length >= 2, `two sections at least (${sections.length})`);
const items = sourceItems(sections);
const kinds = new Set(items.map((i) => i.kind));
for (const kind of ["heading", "term", "aside", "figure"]) assert.ok(kinds.has(kind), `an item of kind ${kind}`);
assert.ok(items.some((i) => i.kind === "aside" && /Nile flood/.test(i.text)), "a box without a bold term is an item");
assert.ok(!items.some((i) => /Exercises/.test(i.text)), "the exercise heading is not an item");

// The map: a goal spanning two sections is split; an item left out gets a goal of its own.
const last = items[items.length - 1];
const spread = items.filter((i) => i !== last && i.section !== items[0].section).slice(0, 1);
const raw = { goals: [
  { goal: "Explain why farmers settled by rivers", items: [items[0].id, items[1].id, ...spread.map((i) => i.id)], misconception: "rivers were only dangerous", hook: "the monsoon", difficulty: 2 },
  ...items.slice(2).filter((i) => i !== last && !spread.includes(i)).map((i) => ({ goal: `Know ${i.text}`, items: [i.id, "i999"], misconception: "", hook: "", difficulty: 1 })),
] };
const map = readLearningMap(raw, items, sections);
const placed = map.goals.flatMap((g) => g.items);
assert.equal(new Set(placed).size, items.length, "every item placed exactly once");
assert.equal(placed.length, items.length);
assert.ok(map.goals.some((g) => g.added && g.items.includes(last.id)), "the left-out item has a goal of its own");
assert.equal(map.added, 1);
for (const g of map.goals) {
  for (const id of g.items) assert.equal(items.find((i) => i.id === id).section, g.section, `${g.id} is taught where its items are`);
}
if (spread.length) assert.ok(map.goals.some((g) => /\(continued\)$/.test(g.goal)), "a goal over two sections is split");
assert.deepEqual(map.goals.map((g) => g.id), map.goals.map((_, k) => `g${k + 1}`), "ids in teaching order");

// The plan: every question placed once; one the reply left out stays where the book prints it.
const qs = sections.flatMap((s) => s.questions ?? []);
assert.ok(qs.length >= 2, "the book's questions are found");
const video = { index: 1, of: 1, sections };
const plan = readStoryPlan({ big_question: "Why did rivers make cities?", running_example: "a farmer", arc: "flood, surplus, city",
  opening: "the flood", closing: "the answer", sections: sections.map((s, i) => ({ section: s.n, opens_from: `from ${s.n}`,
    hands_on: `to ${s.n}`, guess_first: `guess ${s.n}?`, questions: i === 0 ? [qs[0].id, qs[0].id, "q99"] : [] })) }, video, qs);
const asked = plan.sections.flatMap((s) => s.questions);
assert.deepEqual([...asked].sort(), qs.map((q) => q.id).sort(), "every question placed once");
assert.equal(plan.sections[0].questions[0], qs[0].id);
assert.equal(readStoryPlan({ sections: [] }, video, qs), null, "no big question, no plan");

// A section's request: its plan and its goals, not the long list of everything in its part.
const n = sections[0].n;
const text = sectionPlanText(plan, n, map.goals, map);
const request = sectionRequest(sections[0], sections.length, [], undefined, sections, text);
assert.match(request, /Big question: Why did rivers make cities\?/);
assert.match(request, /It OPENS the video/);
assert.match(request, /goals_taught/);
assert.doesNotMatch(request, /WHAT THIS PART COVERS/);
assert.match(request, new RegExp(`The book's questions you ask[^\\n]*${qs[0].id}`), "a section is told its own book questions");
const quiet = plan.sections.find((x) => !x.questions.length);
if (quiet) assert.match(sectionPlanText(plan, quiet.section, map.goals, map).join("\n"), /ask none of the book's questions/);
// A planned section does not see the exercise list (it gets only its own questions, listed).
assert.equal(withoutExercises("## A\ntext\n## Exercises\n1. Why?\n## B\nmore"), "## A\ntext\n## B\nmore");
const lastSection = sections[sections.length - 1];
assert.doesNotMatch(sectionRequest(lastSection, sections.length, [], undefined, sections, ["plan"]), /## Exercises|^1\. Why did farmers/m);
const unplanned = sectionRequest(sections[0], sections.length, [], undefined, sections);
assert.match(unplanned, /WHAT THIS PART COVERS/, "an unplanned request keeps its list");

// The prompts: the planned telling rules and examples, or the old ones.
const promptOf = (planned) => transcriptPrompt({ sections, minutes: 10, language: "hinglish", languageRules: "", hasReference: false,
  content: "", planned });
assert.match(promptOf(true), /HOW A GREAT TEACHER TELLS IT/);
assert.match(promptOf(true), /WHAT IT SOUNDS LIKE/);
assert.doesNotMatch(promptOf(true), /Nothing checks this after you/);
assert.match(promptOf(false), /Nothing checks this after you/);

// The coverage check: only the section's own goals, each naming a sentence it has.
assert.deepEqual(goalsTaught([{ goal: "g1", lines: [2] }, { goal: "g9", lines: [1] }, { goal: "g2", lines: [40] }, { goal: "g3", lines: [1] }],
  ["g1", "g2", "g3"], 5).sort(), ["g1", "g3"]);
const body = "One. Two is here. Three.\n\nFour ends it?";
const lines = linesOf(body);
assert.equal(insertAfterLine(body, lines, 2, "Added."), "One. Two is here. Added. Three.\n\nFour ends it?");
assert.equal(insertAfterLine(body, lines, 0, "Added."), "One. Added. Two is here. Three.\n\nFour ends it?");
assert.equal(insertAfterLine(body, [], 3, "Added."), "One. Two is here. Three.\n\nAdded.\n\nFour ends it?");
console.log(`ok: ${items.length} items, ${map.goals.length} goals, ${qs.length} questions placed; requests and coverage checked`);
