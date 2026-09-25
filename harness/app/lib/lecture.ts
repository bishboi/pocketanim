/**
 * Lecture templates: the model writes a beat script, not Manim.
 *
 * harness/lecture/compile_lecture.py turns a JSON script -- narration plus a
 * few operations per beat -- into a scene on the pocket_lecture engine. That
 * is the guide's cheap path: a 15-minute lecture is 10-15k output tokens of
 * script instead of the whole engine re-derived as code, and the compiler's
 * linter catches the layout mistakes before anything renders.
 */

import { spawn } from "node:child_process";
import path from "node:path";
import { REPO, python } from "./pocketanim";
import type { Template } from "./templates";

export type LectureRegion = { country?: string; state?: string; view?: string };

export type BeatOp = { op: string; [key: string]: unknown };
export type LectureScript = {
  title?: string;
  sub?: string;
  style?: string;
  region?: LectureRegion | null;
  intro?: string;
  chapters: {
    title: string;
    sub?: string;
    narration: string;
    map?: boolean;
    beats: { say: string; do?: BeatOp[] }[];
  }[];
  recap?: [string, string][];
  credits?: string;
};

export type Compiled = { source: string | null; errors: string[]; warnings: string[] };

function runPython(args: string[], input?: string): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), args, { cwd: REPO });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk.toString()));
    child.stderr.on("data", (chunk) => (stderr += chunk.toString()));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr }));
    if (input !== undefined) child.stdin.write(input);
    child.stdin.end();
  });
}

/** Lint and compile a beat script. Errors come back as data, never thrown. */
export async function compileLecture(script: unknown): Promise<Compiled> {
  const compiler = path.join(REPO, "harness", "lecture", "compile_lecture.py");
  const { stdout, stderr } = await runPython([compiler, "-", "--json"], JSON.stringify(script));
  try {
    return JSON.parse(stdout.trim().split("\n").pop() || "") as Compiled;
  } catch {
    return { source: null, errors: [stderr.trim().slice(-600) || "the compiler returned nothing"], warnings: [] };
  }
}

/** The country or state the content is about, if it names one. */
export async function resolveRegion(text: string): Promise<LectureRegion | null> {
  const script = path.join(REPO, "harness", "lecture", "resolve_region.py");
  const { stdout } = await runPython([script, text.slice(0, 4000)]);
  try {
    return (JSON.parse(stdout.trim().split("\n").pop() || "{}").region as LectureRegion) ?? null;
  } catch {
    return null;
  }
}

// Longer units first: alternation takes the first that matches, and "m"
// ahead of "million" turned 3.287 million into "3.287 m".
const NUMBER = /(≈\s*|about\s+)?\d[\d,.]*\s*(million km²|billion|million|lakh|km²|km|mm|%|°[CNE]?|m\b)?/;

const VERB = /\s(is|are|was|were|lies|lie|covers|cover|brings|bring|has|have|flows|flow|forms|form|makes|make|runs|run|holds|hold|falls|fall|rises|rise|became|becomes)\s/i;
const PRONOUN = /^(it|they|this|these|that|those|he|she|we|there)$/i;

/** A chapter heading from a sentence: its subject, when it has a short one. */
function headingOf(line: string, fallback: string): string {
  const clause = line.replace(/[,:;(].*$/, "");
  const cut = clause.search(VERB);
  const subject = (cut > 0 ? clause.slice(0, cut) : clause.split(/\s+/).slice(0, 4).join(" ")).trim();
  const words = subject.replace(/^(the|a|an)\s+/i, "").split(/\s+/);
  if (!subject || words.length > 5 || PRONOUN.test(subject)) return fallback;
  return words.map((w) => (w[0] ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

/**
 * A beat script built from the content itself, for the offline provider.
 *
 * The first line is the title; every later line is a beat. A line that
 * carries a number shows it as a big stat, anything else as a fact; three
 * beats make a panel. With a region the lecture draws its map.
 */
export function fixtureScript(content: string, template: Template, region: LectureRegion | null, instruction?: string): LectureScript {
  const lines = content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const title = (lines[0] || "Untitled").slice(0, 60);
  const body = lines.slice(1).length ? lines.slice(1) : [title];
  const chunks: string[][] = [];
  for (let i = 0; i < body.length; i += 3) chunks.push(body.slice(i, i + 3));

  const short = (text: string, n = 60) => (text.length <= n ? text : `${text.slice(0, n - 1).trim()}…`);
  const chapters = chunks.map((chunk, index) => {
    const heading = short(headingOf(chunk[0], `Part ${index + 1}`), 28);
    return {
      title: heading,
      sub: title,
      narration: `Chapter ${index + 1}. ${heading}.`,
      map: Boolean(region),
      beats: chunk.map((line, j) => {
        const ops: BeatOp[] = [];
        if (j === 0) ops.push({ op: "panel", title: heading });
        const found = line.match(NUMBER);
        if (found && found[0].trim().length > 1) {
          ops.push({ op: "stat", value: found[0].trim(), label: short(line, 70) });
        } else {
          ops.push({ op: "fact", text: short(line, 90) });
        }
        return { say: line.length > 184 ? `${line.slice(0, 180)}…` : line, do: ops };
      }),
    };
  });
  const script: LectureScript = {
    title,
    sub: instruction ? short(instruction, 60) : "",
    style: template.style ?? "atlas",
    region,
    intro: `${title}.`,
    chapters,
    credits: region ? "Map data: Natural Earth · Projections: Cartopy · Animation: Manim" : undefined,
  };
  return script;
}

export const LECTURE_TOOL = {
  type: "function" as const,
  function: {
    name: "write_lecture",
    description:
      "Write the whole lecture as a beat script. It is compiled into the Manim scene; errors and layout warnings come back and you call again with a fixed script. Prefer this over write_scene for a lecture template.",
    parameters: {
      type: "object",
      properties: {
        script: {
          type: "object",
          description: "The beat script: title, sub, region, intro, chapters[{title, sub, narration, map, beats[{say, do[ops]}]}], recap, credits.",
        },
      },
      required: ["script"],
      additionalProperties: false,
    },
  },
};

/** The system prompt for a lecture template. */
export function lecturePrompt(template: Template): string {
  return [
    "You write narrated map lectures for a phone renderer, as a beat script that a compiler turns into Manim.",
    `The style is ${template.name} (engine style "${template.style}"). Do not choose colours outside it.`,
    "Call write_lecture once with the whole script. If it returns errors, fix them and call again. Then reply with one short sentence.",
    "",
    "A beat is one narration line (say) and the operations that go with it (do). One idea per beat, at most two caption lines",
    "(under about 180 characters), at most four operations. 10-20 beats per chapter, 3-8 chapters for a long lecture,",
    "fewer for a short idea. Every number you state must be in the content you were given; say 'about' for rough figures.",
    "",
    "Script shape:",
    '{"title", "sub", "region": {"country": "India", "view": "ind"} | {"state": "Rajasthan", "country": "India"} | null,',
    ' "intro", "chapters": [{"title", "sub", "narration": "Chapter one. ...", "map": true,',
    '   "beats": [{"say": "...", "do": [ops]}]}], "recap": [["Head", "short body"]], "credits": "..."}',
    "",
    "Operations (colour = palette name SAND RIVER GOLD ROSE TEAL GREEN VIOLET MUTED CREAM HI, or #RRGGBB):",
    '  {"op":"panel","title","sub"?}          clear the side panel and head it; start each topic with one',
    '  {"op":"fact","text","color"?}          a bulleted line in the panel (under 90 characters)',
    '  {"op":"stat","value","label","color"?} a big number with a label',
    '  {"op":"bars","items":[["label",n]...],"unit"?,"color"?}  a small bar chart, at most 6 bars',
    '  {"op":"clear"}                         empty the panel',
    "Map operations (only with a region):",
    '  {"op":"marker","place":"Jaipur" | "lonlat":[lon,lat],"label"?,"color"?,"side"?:"left|right|up|down"}',
    '  {"op":"river","name":"Ganges","color"?}   a Natural Earth river by its English name',
    '  {"op":"state","name":"Kerala","color"?,"opacity"?}   fill one state or province',
    '  {"op":"arrow","points":[[lon,lat],...],"color"?}     a curved arrow: winds, migrations, routes',
    '  {"op":"path","points":[[lon,lat],...],"color"?}      a hand-drawn line: a ridge, a canal',
    '  {"op":"graticule","lat":23.44 | "lon":82.5,"label"?,"color"?}',
    '  {"op":"dim","opacity"?}                fade filled areas down before highlighting one',
    "",
    "A panel holds a title and about five facts; start a new panel before it fills. Use real place names; the",
    "compiler looks them up. Keep lon/lat for arrows and paths to places you are sure of.",
  ].join("\n");
}
