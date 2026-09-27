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

export type Compiled = { source: string | null; errors: string[]; warnings: string[]; minutes?: number };

/** A lecture runs this long unless the request names a length. */
export const DEFAULT_LECTURE_MINUTES = 8;

/** The length a request asks for: "a 12 minute lecture", "15-min", "१० मिनट". */
export function targetMinutes(text: string): number {
  const digits = text.replace(/[०-९]/g, (d) => String("०१२३४५६७८९".indexOf(d)));
  const found = digits.match(/(\d+(?:\.\d+)?)\s*-?\s*(?:min\b|mins\b|minutes?\b|मिनट)/i);
  const minutes = found ? parseFloat(found[1]) : DEFAULT_LECTURE_MINUTES;
  return Math.min(40, Math.max(1, minutes));
}

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

/**
 * Lint and compile a beat script. Errors come back as data, never thrown.
 *
 * `style` is the picked template's and overrides whatever the script says (a
 * model often leaves it out, and the compiler's default is atlas).
 * `minMinutes` makes a script that would run well short of it an error.
 */
export async function compileLecture(
  script: unknown,
  options: { style?: string; minMinutes?: number; figures?: Record<string, { file: string; caption: string }> } = {},
): Promise<Compiled> {
  const compiler = path.join(REPO, "harness", "lecture", "compile_lecture.py");
  // The figures table comes from the uploaded document, never from the model.
  const body =
    script && typeof script === "object"
      ? {
          ...script,
          ...(options.style ? { style: options.style } : {}),
          ...(options.figures ? { figures: options.figures } : {}),
        }
      : script;
  const args = [compiler, "-", "--json"];
  if (options.minMinutes) args.push("--min-minutes", String(options.minMinutes));
  const { stdout, stderr } = await runPython(args, JSON.stringify(body));
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

const FIGURE_LINE = /^\[FIGURE (fig\d+): ([^\]]*)\]$/;

/**
 * Content lines as beats. Text from a PDF breaks lines mid-sentence, so a
 * line that does not end a sentence joins the next, and the joined text is
 * cut again at sentence ends. A figure's caption line, which the figure
 * marker repeats, is dropped.
 */
function reflow(content: string): string[] {
  const raw = content
    .split(/\n/)
    .map((line) => line.trim())
    .filter((line) => !/^#+\s*page \d+$/i.test(line))
    .map((line) => line.replace(/^#+\s*/, ""));
  const captions = new Set(
    raw.map((line) => line.match(FIGURE_LINE)?.[2]?.trim().toLowerCase()).filter(Boolean) as string[],
  );
  const joined: string[] = [];
  let open = false;
  for (const line of raw) {
    if (!line) {
      open = false;
      continue;
    }
    if (captions.has(line.toLowerCase())) continue;
    const marker = FIGURE_LINE.test(line);
    if (open && !marker && joined.length) joined[joined.length - 1] += ` ${line}`;
    else joined.push(line);
    open = !marker && !/[.!?:।]$/.test(line);
  }
  // The first line is the title; the rest are cut at sentence ends.
  return joined.flatMap((line, index) =>
    index === 0 || FIGURE_LINE.test(line) ? [line] : line.split(/(?<=[.!?।])\s+(?=\S)/).filter(Boolean),
  );
}

/**
 * A beat script built from the content itself, for the offline provider.
 *
 * The first line is the title; every later line is a beat. A line that
 * carries a number shows it as a big stat, anything else as a fact; three
 * beats make a panel. The first beat shows the region on the map; after
 * that the stage carries the document's figures and the illustrations the
 * compiler draws from each beat's words.
 */
export function fixtureScript(content: string, template: Template, region: LectureRegion | null, instruction?: string): LectureScript {
  const lines = reflow(content);
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
      beats: chunk.map((line, j) => {
        const marked = line.match(FIGURE_LINE);
        if (marked) return { say: marked[2] || "Here is the figure.", do: [{ op: "figure", id: marked[1], where: "stage" }] };
        const ops: BeatOp[] = [];
        if (j === 0) ops.push({ op: "panel", title: heading });
        if (index === 0 && j === 0 && region?.state) ops.push({ op: "state", name: region.state, color: "SAND", opacity: 0.5 });
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

export const ICON_TOOL = {
  type: "function" as const,
  function: {
    name: "find_icon",
    description:
      "Search the icon library (about 25,000 icons: crops, animals, industry, weather, transport, buildings) for words. Returns the names an icon op may use; single-colour ones take the style's colours.",
    parameters: {
      type: "object",
      properties: { queries: { type: "array", items: { type: "string" }, description: "Words, e.g. [\"sugarcane\", \"coal\", \"tiger\"]" } },
      required: ["queries"],
      additionalProperties: false,
    },
  },
};

/** find_icon: the best few icon names for each word. */
export async function findIcon(queries: unknown): Promise<string> {
  const words = (Array.isArray(queries) ? queries : [queries]).map((q) => String(q).slice(0, 40)).filter(Boolean).slice(0, 12);
  if (!words.length) return "Give queries: a list of words.";
  const { stdout } = await runPython([path.join(REPO, "harness", "lecture", "icons.py"), ...words]);
  try {
    const found = JSON.parse(stdout.trim().split("\n").pop() || "{}");
    if (found.error) return String(found.error);
    return Object.entries(found as Record<string, { id: string; mono: boolean }[]>)
      .map(([q, rows]) => `${q}: ${rows.length ? rows.slice(0, 5).map((r) => `${r.id}${r.mono ? "" : " (colour)"}`).join(", ") : "nothing; try a simpler word"}`)
      .join("\n");
  } catch {
    return "The icon library is not installed (harness/scripts/fetch_icons.py).";
  }
}

export const IMAGE_TOOL = {
  type: "function" as const,
  function: {
    name: "find_image",
    description:
      "Search Wikimedia Commons for reusable photographs (public domain, CC0, CC BY, CC BY-SA only). Returns titles to use in a photo op, with what each shows.",
    parameters: {
      type: "object",
      properties: { queries: { type: "array", items: { type: "string" }, description: "Scenes, e.g. [\"sugarcane field India\", \"Dudhwa tiger\"]" } },
      required: ["queries"],
      additionalProperties: false,
    },
  },
};

/** find_image: a few reusable photos per query, as lines the model can choose from. */
export async function findImage(queries: unknown): Promise<string> {
  const words = (Array.isArray(queries) ? queries : [queries]).map((q) => String(q).slice(0, 80)).filter(Boolean).slice(0, 6);
  if (!words.length) return "Give queries: a list of scene descriptions.";
  const { stdout } = await runPython([path.join(REPO, "harness", "lecture", "images.py"), ...words]);
  try {
    const found = JSON.parse(stdout.trim() || "{}") as Record<
      string,
      { id: string; description: string; width: number; height: number; license: string }[]
    >;
    return Object.entries(found)
      .map(([q, rows]) =>
        `${q}:\n` +
        (rows.length
          ? rows.map((r) => `  ${r.id} (${r.width}x${r.height}, ${r.license}) ${r.description.slice(0, 100)}`).join("\n")
          : "  nothing reusable found (or no internet here); use an illustration instead"),
      )
      .join("\n");
  } catch {
    return "Image search is unavailable; use illustrations and icons.";
  }
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
export function lecturePrompt(template: Template, minutes = DEFAULT_LECTURE_MINUTES): string {
  const words = Math.round(minutes * 140);
  const beats = Math.round((minutes * 60) / 11);
  return [
    "You write narrated map lectures for a phone renderer, as a beat script that a compiler turns into Manim.",
    `The style is ${template.name} (engine style "${template.style}"). Do not choose colours outside it.`,
    "Call write_lecture once with the whole script. If it returns errors, fix them and call again. Then reply with one short sentence.",
    "",
    `LENGTH. The lecture must run about ${minutes} minutes: about ${words} words of narration in about ${beats} beats,`,
    `in ${Math.max(3, Math.min(10, Math.round(minutes / 2)))} or so chapters of 8-15 beats. The compiler measures the running time and`,
    "returns an error when the script is well short; then add beats and chapters with new material, never padding.",
    "",
    "A beat is one narration line (say) and the operations that go with it (do). One idea per beat, at most two caption lines",
    "(under about 180 characters, 15-30 words), at most four operations. Every number you state must be in the content you",
    "were given or be well established; say 'about' for rough figures.",
    "",
    "Script shape:",
    '{"title", "sub", "region": {"country": "India", "view": "ind"} | {"state": "Rajasthan", "country": "India"} | null,',
    ' "intro", "chapters": [{"title", "sub", "narration": "Chapter one. ...",',
    '   "beats": [{"say": "...", "do": [ops]}]}], "recap": [["Head", "short body"]], "credits": "..."}',
    "",
    "Operations (colour = palette name SAND RIVER GOLD ROSE TEAL GREEN VIOLET MUTED CREAM HI, or #RRGGBB):",
    '  {"op":"panel","title","sub"?}          clear the side panel and head it; start each topic with one',
    '  {"op":"fact","text","color"?}          a bulleted line in the panel (under 90 characters)',
    '  {"op":"stat","value","label","color"?} a big number with a label',
    '  {"op":"bars","items":[["label",n]...],"unit"?,"color"?}  a small bar chart, at most 6 bars',
    '  {"op":"clear"}                         empty the panel',
    "THE STAGE. The left half of the frame shows one picture at a time; the panel on the right holds the words.",
    "Make it immersive: most beats should change or build the picture. Use the MAP only for beats about where",
    "something is (a place, a route, a spread across a region); a chapter with no map operation has no map at all.",
    "Otherwise put a picture on the stage:",
    '  {"op":"photo","image":"File:....jpg" (from find_image) | "query":"sugarcane harvest","caption"?,"where"?:"stage"|"full"|"panel"}',
    "                                          a real photograph from Wikimedia Commons, credited automatically",
    '  {"op":"illustration","icon":"sugar-cane","items"?:[["wheat","Rabi"],["sheaf-of-rice","Kharif"]],"title"?,"color"?}',
    "                                          an illustration built from icons: one large, up to four small, labelled",
    '  {"op":"figure","id":"fig2","where":"stage"}   a diagram from the uploaded document, large',
    "Call find_image for photos (describe the scene: 'sugarcane field India', 'Ganges ghats Varanasi') and use a",
    "title it returns. A map chapter may still show a photo: it covers the map until the next map operation.",
    "Beats you leave without a picture get an automatic illustration from their words, so choose the important ones.",
    "",
    "Map operations (only with a region):",
    '  {"op":"marker","place":"Jaipur" | "lonlat":[lon,lat],"label"?,"color"?,"side"?:"left|right|up|down"}',
    '  {"op":"river","name":"Ganges","color"?}   a Natural Earth river by its English name',
    '  {"op":"state","name":"Kerala","color"?,"opacity"?}   fill one state or province',
    '  {"op":"arrow","points":[[lon,lat],...],"color"?}     a curved arrow: winds, migrations, routes',
    '  {"op":"path","points":[[lon,lat],...],"color"?}      a hand-drawn line: a ridge, a canal',
    '  {"op":"graticule","lat":23.44 | "lon":82.5,"label"?,"color"?}',
    '  {"op":"dim","opacity"?}                fade filled areas down before highlighting one',
    '  {"op":"icon","name":"sugarcane","places":["Meerut","Saharanpur"] | "place" | "lonlat","color"?,"size"?,"label"?}',
    "                                          icons on the map where something is grown, mined, made or lives",
    "Panel icon (no place): {\"op\":\"icon\",\"name\":\"wheat\",\"label\":\"Rabi: wheat\",\"color\"?} -- an icon with a short line.",
    "Call find_icon first and use the names it returns. Use icons often for crops, minerals, industries, animals",
    "and weather: a picture beside a word is what makes a map lecture memorable.",
    "",
    "A panel holds a title and about five facts; start a new panel before it fills. Use real place names; the",
    "compiler looks them up. A marker's place is a town or city in English (\"Prayagraj\", not \"प्रयागराज\");",
    "put the name in the script's own language in label. For a district, park or village the gazetteer may not",
    "know, give lonlat instead. Keep lon/lat for arrows and paths to places you are sure of.",
  ].join("\n");
}
