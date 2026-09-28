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
  options: {
    style?: string;
    minMinutes?: number;
    figures?: Record<string, { file: string; caption: string }>;
    genre?: string;
    /** The content the lecture is written from: the compiler flags lines read out of it word for word. */
    sourceText?: string;
  } = {},
): Promise<Compiled> {
  const compiler = path.join(REPO, "harness", "lecture", "compile_lecture.py");
  // The figures table comes from the uploaded document, never from the model.
  const body =
    script && typeof script === "object"
      ? {
          ...script,
          ...(options.style ? { style: options.style } : {}),
          ...(options.figures ? { figures: options.figures } : {}),
          ...(options.genre ? { genre: options.genre } : {}),
          ...(options.sourceText ? { source_text: options.sourceText } : {}),
        }
      : script;
  const args = [compiler, "-", "--json"];
  if (options.minMinutes) args.push("--min-minutes", String(options.minMinutes));
  const { stdout, stderr } = await runPython(args, JSON.stringify(body));
  try {
    const compiled = scriptJson<Compiled>(stdout);
    if (!compiled) throw new Error("no JSON");
    return compiled;
  } catch {
    return { source: null, errors: [stderr.trim().slice(-600) || "the compiler returned nothing"], warnings: [] };
  }
}

export type Subject = {
  genre: string;
  label: string;
  style: string;
  map: "often" | "sometimes" | "rarely" | "never";
  kit: string[];
  guidance: string;
  why: string[];
};

/** The content's subject and its kit (harness/lecture/genre.py): style, map policy, pictures to prefer. */
export async function classifySubject(text: string): Promise<Subject> {
  const { stdout } = await runPython([path.join(REPO, "harness", "lecture", "genre.py")], text.slice(0, 20000));
  try {
    const subject = scriptJson<Subject>(stdout);
    if (!subject) throw new Error("no JSON");
    return subject;
  } catch {
    return { genre: "general", label: "General", style: "vox", map: "sometimes", kit: [], guidance: "", why: [] };
  }
}

/** The country or state the content is about, if it names one. */
export async function resolveRegion(text: string): Promise<LectureRegion | null> {
  const script = path.join(REPO, "harness", "lecture", "resolve_region.py");
  const { stdout } = await runPython([script, text.slice(0, 4000)]);
  try {
    return scriptJson<{ region?: LectureRegion }>(stdout)?.region ?? null;
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

export const ILLUSTRATION_TOOL = {
  type: "function" as const,
  function: {
    name: "find_illustration",
    description:
      "Search educational illustrations and diagrams (Wikimedia Commons drawings and diagrams, Openverse illustrations; reusable licences only) that explain a topic: \"water cycle\", \"leaf cross section\", \"food web forest\", \"layers of soil\". Describe the topic in English, even for a Hindi lecture. Returns titles to use in an illustration op, with what each shows.",
    parameters: {
      type: "object",
      properties: { queries: { type: "array", items: { type: "string" }, description: "Topics in English, e.g. [\"water cycle\", \"photosynthesis diagram\"]" } },
      required: ["queries"],
      additionalProperties: false,
    },
  },
};

/**
 * The JSON a script printed: the whole output, or else its last line that parses
 * (a script may log before its answer, and may print its answer across lines).
 */
export function scriptJson<T = unknown>(stdout: string): T | null {
  const text = stdout.trim();
  try {
    return JSON.parse(text) as T;
  } catch {
    // fall through: look for a one-line answer after other output
  }
  for (const line of text.split("\n").reverse()) {
    try {
      return JSON.parse(line) as T;
    } catch {
      // not this line
    }
  }
  return null;
}

/** find_illustration: a few educational illustrations or diagrams per topic, as lines the model can choose from. */
export async function findIllustration(queries: unknown): Promise<string> {
  const words = (Array.isArray(queries) ? queries : [queries]).map((q) => String(q).slice(0, 80)).filter(Boolean).slice(0, 6);
  if (!words.length) return "Give queries: a list of topics.";
  const { stdout, stderr } = await runPython([path.join(REPO, "harness", "lecture", "images.py"), "--illustrations", ...words]);
  const found = scriptJson<Record<string, { id: string; title: string; description: string; license: string }[]>>(stdout);
  if (!found) return `The illustration search failed: ${stderr.trim().split("\n").slice(-3).join(" ") || "no output"}`;
  return Object.entries(found)
    .map(([q, rows]) =>
      `${q}:\n` +
      (rows.length
        ? rows.map((r) => `  ${r.id} (${r.license}) ${(r.description || r.title).slice(0, 100)}`).join("\n")
        : "  nothing reusable found (or no internet here); try another description, a document figure, or a process/timeline"),
    )
    .join("\n");
}

export const IMAGE_TOOL = {
  type: "function" as const,
  function: {
    name: "find_image",
    description:
      "Find reusable photographs (public domain, CC0, CC BY, CC BY-SA only). For a person, movement, event, monument or place give its name (English, as Wikipedia titles it): Wikipedia's picture of it comes first. For a scene, describe it. Returns titles to use in a photo op, with what each shows.",
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
      { id: string; description: string; width: number; height: number; license: string; source?: string; subject?: string }[]
    >;
    return Object.entries(found)
      .map(([q, rows]) =>
        `${q}:\n` +
        (rows.length
          ? rows.map((r) => `  ${r.id} (${r.width}x${r.height}, ${r.license})${r.source === "wikipedia" ? ` [Wikipedia's picture of ${r.subject}]` : ""} ${r.description.slice(0, 100)}`).join("\n")
          : "  nothing reusable found (or no internet here); use an illustration instead"),
      )
      .join("\n");
  } catch {
    return "Image search is unavailable; use document figures and illustrations.";
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
export function lecturePrompt(template: Template, minutes = DEFAULT_LECTURE_MINUTES, subject?: Subject): string {
  const words = Math.round(minutes * 140);
  const beats = Math.round((minutes * 60) / 11);
  return [
    "You write narrated lectures that explain a topic simply, for a phone renderer, as a beat script that a compiler turns into Manim.",
    `The style is ${template.name} (engine style "${template.style}"). Do not choose colours outside it.`,
    "Call write_lecture once with the whole script. If it returns errors, fix them and call again. Then reply with one short sentence.",
    "",
    ...(subject
      ? [
          `SUBJECT. This is a ${subject.label} lecture. ${subject.guidance}`,
          `The map is used ${subject.map} in ${subject.label.toLowerCase()} lectures. Favour: ${subject.kit.join(", ")}.`,
          "",
        ]
      : []),
    "EXPLAIN SIMPLY. You are a teacher explaining the book to a 12-year-old, not reading it aloud. The source may",
    "be written in difficult, formal language; your narration must not be. For every idea:",
    "  - say it in everyday spoken words and short sentences (under about 20 words each);",
    "  - when a hard term must be used (biodiversity, ecosystem, primary producer), first say what it means in plain words,",
    "    then use it; give an example or comparison from daily life (a forest is like a big shared house...);",
    "  - never copy a sentence of the source; the compiler rejects a script that reads the book word for word;",
    "  - it is fine to take more beats to explain one hard idea well. Explaining clearly matters more than covering",
    "    every line. Skip what is not content: QR codes, page furniture, exercise instructions.",
    "In a Hindi lecture use simple spoken Hindi (बोलचाल की हिंदी), not heavy Sanskritised words: say 'जंगल' and",
    "'जीव-जंतु' rather than 'वनस्पतिजात' and 'प्राणिजात'; when the book's term matters, say it once and explain it,",
    "and you may add the familiar English word in brackets.",
    "",
    "PICTURES, NOT BOXES OF WORDS. The stage should nearly always show a picture: an educational illustration or",
    "diagram, a photo, a document figure, a molecule or a graph. Never icons. process and quote are boxes of words: use",
    "process only for a real sequence of steps (at most two per chapter) and quote rarely. find_illustration and",
    "find_image take English descriptions even for a Hindi lecture; give captions in the lecture's language.",
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
    '   "beats": [{"say": "...", "about"?: "Chipko movement", "picture"?: "forest food web diagram", "do": [ops]}]}],',
    ' "recap": [["Head", "short body"]], "credits": "..."}',
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
    '  {"op":"photo","image":"File:....jpg" (from find_image) | "subject":"Sunderlal Bahuguna" | "query":"sugarcane harvest","caption"?,"where"?:"stage"|"full"|"panel"}',
    "                                          a real photograph, credited automatically; subject = Wikipedia's picture of a person,",
    "                                          movement, event, monument or place (its English name)",
    '  {"op":"illustration","image":"File:....svg" (from find_illustration) | "query":"water cycle diagram","caption"?}',
    "                                          an educational illustration or diagram that explains the idea (labelled",
    "                                          drawings from Wikimedia Commons and Openverse), credited automatically",
    '  {"op":"figure","id":"fig2","where":"stage"}   a diagram from the uploaded document, large',
    '  {"op":"molecule","name":"glucose" | "H2O" | SMILES,"label"?}   a structural formula, atoms in CPK colours',
    '  {"op":"equation","tex":"6CO_2 + 6H_2O -> C_6H_{12}O_6 + 6O_2","label"?}   a law or a reaction, large',
    '  {"op":"plot","expr":"x^2/2" | "exprs":["x^2","3*x"],"x":[0,6],"x_label"?,"y_label"?,"names"?,"label"?}   graphs of x',
    '  {"op":"process","steps":["Evaporation","Condensation","Rain"],"cycle"?:true,"title"?}   steps joined by arrows',
    '  {"op":"timeline","events":[["1526","Panipat"],["1556","Akbar"]],"title"?}   an era across the stage',
    '  {"op":"quote","text":"...","who":"Akbar"}   a primary source, in its own words',
    "Call find_image for photos (describe the scene: 'sugarcane field India', 'Ganges ghats Varanasi') and use a",
    "title it returns. A map chapter may still show a photo: it covers the map until the next map operation.",
    "Beats you leave without a picture get an automatic illustration searched from their \"picture\" (give each beat",
    "one: \"picture\":\"soil layers diagram\", in English) or their English words, so choose the important ones yourself.",
    "PEOPLE, MOVEMENTS AND PLACES. Whenever a beat is about a particular person (Sunderlal Bahuguna, Akbar), movement",
    "(Chipko movement), event (Battle of Plassey), monument (Taj Mahal) or historic place and the document has no figure",
    "of it, show its picture: {\"op\":\"photo\",\"subject\":\"Chipko movement\",\"caption\":\"चिपको आंदोलन\"}. Use the English",
    "name Wikipedia titles it by, and the caption in the lecture's language. A document figure of it comes first.",
    "Give such a beat \"about\":\"<English name>\" too (a Hindi beat especially): a beat you leave without a picture",
    "then gets that picture automatically.",
    "",
    "Map operations (only with a region):",
    '  {"op":"marker","place":"Jaipur" | "lonlat":[lon,lat],"label"?,"color"?,"side"?:"left|right|up|down"}',
    '  {"op":"river","name":"Ganges","color"?}   a Natural Earth river by its English name',
    '  {"op":"state","name":"Kerala","color"?,"opacity"?}   fill one state or province',
    '  {"op":"arrow","points":[[lon,lat],...],"color"?}     a curved arrow: winds, migrations, routes',
    '  {"op":"path","points":[[lon,lat],...],"color"?}      a hand-drawn line: a ridge, a canal',
    '  {"op":"graticule","lat":23.44 | "lon":82.5,"label"?,"color"?}',
    '  {"op":"dim","opacity"?}                fade filled areas down before highlighting one',
    "Where something is grown, mined, made or lives: a marker at each place with a label (\"Sugarcane\"), then an",
    "illustration or photo of the thing itself on the stage.",
    "",
    "A panel holds a title and about five facts; start a new panel before it fills. Use real place names; the",
    "compiler looks them up. A marker's place is a town or city in English (\"Prayagraj\", not \"प्रयागराज\");",
    "put the name in the script's own language in label. For a district, park or village the gazetteer may not",
    "know, give lonlat instead. Keep lon/lat for arrows and paths to places you are sure of.",
  ].join("\n");
}
