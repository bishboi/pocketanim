/**
 * What the scene writer is told when the Scenes tab builds on the motion engine (beta: engine/MOTION_ENGINE.md), in
 * its own part after v1's instructions (which stay word for word): the motion engine draws every operation v1 tells
 * of, in motion, and adds its templates; each operation may land on its words ("on").
 */

import { part, type Part } from "./parts";

export const MOTION_LOOKS = ["paper", "newsroom", "chalk", "data", "studio", "sketch"] as const;

export function motionPart(x: { look?: string; timeline?: string }): Part {
  return part("motion", "The motion engine (beta): its templates and moments", "rules", [
    "THE MOTION ENGINE (BETA). This lecture is drawn by the motion engine, as a modern explainer video is: every operation",
    "above still works (drawn in motion), and these templates are added. Each builds itself part by part, each part on",
    "the words that name it, in the lecture's look" + (x.look ? ` (${x.look})` : "") + ". Prefer a template to a plain",
    "operation where one fits: a number counts up, a chart builds, a grid fills, a claim gets stamped.",
    "",
    "ON ITS WORDS: any operation may carry \"on\": \"<words of its line>\" -- it starts as those words are said. Inside",
    "a template, items carry their own \"on\" (a column, a group of units, a step, a card's mark, a list's point); an",
    "item without one lands when the line says its own name, or in its turn. Use the line's exact words.",
    "",
    "THE TEMPLATES (op and its fields; ? optional):",
    '  title     {"op":"title","text":"The man who read the hands of kings","kicker"?:"A true story","highlight"?:"kings","sub"?}',
    "            a chapter's or a section's opening headline: big words rising, one highlighted.",
    '  counter   {"op":"counter","value":"204%","label":"Japan\'s debt, as a share of its economy","kicker"?,"delta"?:"+12%","trend"?:"up|down"}',
    "            one key number, counting up (keeps \"$\", \"%\", \"km\", commas). Better than stat for a number that matters.",
    '  chart     {"op":"chart","kind"?:"column|bar|line","items":[["Japan",204],["Italy",138]],"unit"?:"%","highlight"?:"Japan",',
    '            "reference"?:{"value":100,"label":"The economy"},"marks"?:[{"at":2015,"label":"2015"}],"kicker"?,"title"?,"source"?}',
    "            quantities compared (column, up to 12; bar for long names); change over time (line, x labels as years).",
    '  units     {"op":"units","total":100,"unit"?:"IOU","groups":[{"n":46,"label":"Bank of Japan","on":"Bank of Japan"}],',
    '            "fly"?:{"n":8,"label":"8% abroad","on":"abroad"},"kicker"?}   a share of a whole, as a grid of things.',
    '  donut     {"op":"donut","value":62,"label":"of the backlog is data centres","total"?:100}   one share, swept round a ring.',
    '  kpi       {"op":"kpi","cards":[{"label":"Sales","value":"+50%","delta":"$3.27B","note"?}],"kicker"?}   2-4 figures side by side.',
    '  cards     {"op":"cards","items":[{"title":"1912","big"?:"✓","sub"?,"picture"?:{"generate":"..."},"mark"?:"check|cross|<a word>","on"?}],',
    '            "stamp"?:{"text":"Debunked","on":"..."}}   2-6 things dealt in a row; claims ticked, crossed or stamped.',
    '  stamp     {"op":"stamp","text":"Cleared","on":"cleared"}   slammed onto what is up: a verdict, a status.',
    '  callout   {"op":"callout","text":"8% abroad","on":"abroad"}   a short tag popped onto what is up.',
    '  chain     {"op":"chain","steps":["Signed",{"label":"Built","on":"built"},"Paid"],"loop"?:true,"title"?}   steps in order, each on its words.',
    '  list      {"op":"list","items":["Margins",{"text":"Hiring","on":"hiring"}],"mark"?:"bullet|number|check","title"?}   2-7 short points, each as said.',
    '  versus    {"op":"versus","left":{"title":"Himalayan","points":["Snow-fed"],"value"?},"right":{"title":"Peninsular","points":["Rain-fed"]}}',
    '  document  {"op":"document","title":"Cheiro\'s memoirs","text":"<the source\'s own words>","highlight":["<a phrase of it>"],"picture"?:{"generate":"..."}}',
    "            a primary source, its key phrases highlighted as the line says them.",
    '  polaroids {"op":"polaroids","items":[{"generate":"Mark Twain, a portrait photograph","caption":"Mark Twain"}]}   people or places, as prints.',
    '  emphasis  {"op":"emphasis","target":"Japan","how":"pulse|circle|underline|highlight|box|glow|shake|dim","on":"Japan"}',
    "            point at a part of what is up (a column, a card, a step, an event) by its name, on a later beat.",
    `  timeline  as above, with "style":"track|ribbon|cards|road|vertical" (default ${x.timeline ?? "track"}): ribbon for eras,`,
    "            cards for a few events with pictures, road for a journey, vertical for a short sequence.",
    "",
    "DESIGNING IN MOTION:",
    "  - One idea on screen at a time, built over its beats: put the template up on the paragraph's first beat, then",
    "    point at its parts (emphasis), stamp it, or call out on the beats that talk about them.",
    "  - Numbers are shown, not just said: a counter for one number, a chart for several, units or a donut for a share.",
    "  - Few words on screen: labels of a word or three; the narration says the rest.",
    "  - Every template's parts land on their words: give \"on\" with the line's exact words where it says them.",
  ]);
}
