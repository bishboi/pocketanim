/**
 * Each artifact's manual, for the choreography call (lib/director.ts): the section of the engine's own documentation
 * that tells of the operation or template (engine/BEAT_SCRIPT.md, engine/MOTION_ENGINE.md), cut out as it is written
 * there. The documents are checked against what the compilers read (`npm run check`), so a manual says what the
 * engine draws. On the motion engine a classic operation's manual also gives its row of MOTION_ENGINE.md §4 (how it
 * is redrawn in motion).
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { engineDir } from "./maps";
import { MOTION_KIND } from "./visual-kinds";

type Sections = Map<string, string[]>;

/** The older names of a picture (BEAT_SCRIPT.md §5.2): told as the picture's manual. */
const PICTURE = new Set(["picture", "illustration", "photo", "figure", "draw", "gallery"]);
/** The longest a manual is, so a scene's call stays small. */
const MOST = 3200;

let docs: { beat: Sections; motion: Sections; motionRows: Map<string, string> } | undefined;

/** A document's sections by the operation each heading names (its first `code`), every heading of that name kept. */
function sections(text: string): Sections {
  const out: Sections = new Map();
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = /^#{3,4} `([a-z_]+)`/.exec(lines[i]);
    if (!m) continue;
    let j = i + 1;
    while (j < lines.length && !/^#{1,4} /.test(lines[j]) && lines[j].trim() !== "---") j++;
    const list = out.get(m[1]) ?? [];
    list.push(lines.slice(i, j).join("\n").trim());
    out.set(m[1], list);
  }
  return out;
}

function load() {
  if (docs) return docs;
  const read = (name: string) => readFileSync(path.join(engineDir(), name), "utf8");
  const motionText = read("MOTION_ENGINE.md");
  const motionRows = new Map<string, string>();
  for (const line of motionText.split("\n")) {
    const m = /^\| `([a-z_]+)`[^|]*\|/.exec(line);
    if (m && !motionRows.has(m[1])) motionRows.set(m[1], line);
  }
  docs = { beat: sections(read("BEAT_SCRIPT.md")), motion: sections(motionText), motionRows };
  return docs;
}

/** The manual of one operation or template, as its engine's documentation tells it; "" when it has none. */
export function manualFor(op: string, engine: "current" | "motion"): string {
  const d = load();
  const name = PICTURE.has(op) ? "picture" : op;
  const template = engine === "motion" && MOTION_KIND.ops.includes(name);
  const own = (template ? d.motion.get(name) : d.beat.get(name)) ?? [];
  const row = engine === "motion" && !template ? d.motionRows.get(name) : undefined;
  const text = [...own, ...(row ? [`In motion: ${row}`] : [])].join("\n\n");
  return text.length > MOST ? `${text.slice(0, MOST)}\n...` : text;
}
