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
import os from "node:os";
import path from "node:path";
import { REPO, python } from "./pocketanim";
import type { Template } from "./templates";

export type LectureRegion = { country?: string; state?: string; view?: string; area?: string };

export type BeatOp = { op: string; [key: string]: unknown };
export type LectureScript = {
  title?: string;
  sub?: string;
  style?: string;
  /** How its pictures are drawn (lib/artstyles.ts, artstyle.py); "auto" or left out: the template's own. */
  art?: string;
  region?: LectureRegion | null;
  intro?: string;
  chapters: {
    title: string;
    sub?: string;
    narration: string;
    map?: boolean;
    beats: { say: string; pause?: number; do?: BeatOp[] }[];
  }[];
  recap?: [string, string][];
  credits?: string;
};

/** warnings: what the writer should fix; fixed: what the compiler mended by itself ("fixed: ...", for the log only). */
/** A web or library picture a compiled lecture shows, with its context (compile_lecture.pictures_used). */
export type CompiledPicture = { file: string; kind: "photo" | "illustration"; description: string; role: string;
  found_by?: Record<string, unknown>; source?: Record<string, unknown>; context?: Record<string, unknown> };
/** A picture the image model made while a script compiled (genimage.MADE), and what it cost. */
export type GeneratedPicture = { path: string; what: string; prompt: string; model: string; usd?: number; made?: boolean };
export type Prefetch = { pictures?: number; made?: number; failed?: number; error?: string | null; seconds?: number;
  slowest?: number };
/** The status line for a compile's pictures made at once: how many came back and how many failed, or null when
 * there were none (or they were all found made already, in under a second). Every one failing is said as that,
 * with the image model's reason, never as pictures made. */
export function picturesStatus(prefetch: Prefetch | undefined, parallel = process.env.PANIM_IMAGE_PARALLEL || 6): string | null {
  const asked = prefetch?.pictures ?? 0;
  if (!asked || (prefetch?.seconds ?? 0) < 1) return null;
  // An older compiler said only how many it asked for.
  const made = prefetch?.made ?? asked;
  const failed = prefetch?.failed ?? asked - made;
  const why = prefetch?.error ? ` (${prefetch.error.slice(0, 200)})` : "";
  const time = `in ${prefetch?.seconds} s (the slowest ${prefetch?.slowest} s; ${parallel} at a time)`;
  if (!made) return `Pictures: all ${asked} failed ${time}${why}.`;
  return `Pictures: ${made} of ${asked} made at once ${time}` +
    (failed ? `; ${failed} failed${why}.` : ".");
}

export type Compiled = { source: string | null; errors: string[]; warnings: string[]; fixed?: string[]; minutes?: number;
  pictures?: CompiledPicture[]; generated?: GeneratedPicture[]; images?: ImageReport;
  /** When the image models and the Manim checks were at work in this compile ([start, end], ms since the epoch). */
  image_spans?: [number, number][]; probe_spans?: [number, number][];
  /** The pictures this compile asked for at once before writing the code: how many, how many came back made and
   * how many failed (with the first reason), how long, the slowest (s). */
  prefetch?: Prefetch;
  /** Where the compile's time went (seconds), and each model request it made (genimage.CALLS). */
  phases?: Record<string, number>;
  calls?: { for: string; who: string; model: string; route: string; start: number; end: number; error?: string }[] };
/** What a compile asked of the image model (genimage.py report): pictures asked for, made now, found made, failed. */
export type ImageReport = { model: string; proxy?: string | null; asked: number; cached: number; made: number;
  failed: { what: string; model: string; error: string }[] };

/** A lecture runs this long unless the request names a length, or its content is long. */
export const DEFAULT_LECTURE_MINUTES = 10;
/** Words of source content a minute of detailed teaching covers: a chapter is taught, not read out. */
const SOURCE_WORDS_PER_MINUTE = 120;
/** Words of a book taught in a minute of lecture (explained, with examples and questions). */
// A book taught at about its own length: explained once, with an example and a question where they help, a page of
// text is a page of teaching (60 made every lecture twice the book, most of it saying things again).
const BOOK_WORDS_PER_MINUTE = 100;

/**
 * The length a request asks for: "a 12 minute lecture", "15-min", "१० मिनट". Without one, a long source (a
 * chapter) gets time to be taught in depth: about a minute for every 120 of its words, up to 30.
 */
export function targetMinutes(text: string, source = ""): number {
  const digits = text.replace(/[०-९]/g, (d) => String("०१२३४५६७८९".indexOf(d)));
  const found = digits.match(/(\d+(?:\.\d+)?)\s*-?\s*(?:min\b|mins\b|minutes?\b|मिनट)/i);
  if (found) return Math.max(1, parseFloat(found[1]));
  const words = `${text}\n${source}`.split(/\s+/).filter(Boolean).length;
  if (source.trim()) {
    // A book is taught, not read: explained, with examples and questions it does not have, it runs about twice
    // as long as reading it out.
    // As long as the book needs: as many micro-lectures of 25-30 min as that makes (topics.ts).
    return Math.max(DEFAULT_LECTURE_MINUTES, Math.round(words / BOOK_WORDS_PER_MINUTE));
  }
  return Math.min(30, Math.max(DEFAULT_LECTURE_MINUTES, Math.round(words / SOURCE_WORDS_PER_MINUTE)));
}

/** How long one compile may run (PANIM_COMPILE_TIMEOUT_SECONDS): one that hangs is stopped and reported. */
const COMPILE_TIMEOUT_MS = Math.max(60, Number(process.env.PANIM_COMPILE_TIMEOUT_SECONDS) || 600) * 1000;

/**
 * Compiles at once (PANIM_COMPILE_PARALLEL; default a quarter of the cores, at least 2). Each runs the script's Manim
 * blocks in up to PANIM_MANIM_CHECK_PARALLEL (4) probe processes: ten sections checked at once ran forty Manim
 * processes together, every compile slowed past its time limit, and the lecture seemed to hang. The rest wait.
 */
const COMPILE_PARALLEL = Math.max(1, Number(process.env.PANIM_COMPILE_PARALLEL) ||
  Math.max(2, Math.floor((os.cpus()?.length || 4) / 4)));
let compilesRunning = 0;
const compileQueue: (() => void)[] = [];
async function inCompileSlot<T>(run: () => Promise<T>): Promise<T> {
  if (compilesRunning >= COMPILE_PARALLEL) await new Promise<void>((resolve) => compileQueue.push(resolve));
  compilesRunning += 1;
  try {
    return await run();
  } finally {
    compilesRunning -= 1;
    compileQueue.shift()?.();
  }
}

function runPython(args: string[], input?: string, timeoutMs?: number, env?: Record<string, string>): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), args, { cwd: REPO, ...(env ? { env: { ...process.env, ...env } } : {}) });
    let stdout = "";
    let stderr = "";
    const timer = timeoutMs ? setTimeout(() => {
      stderr += `\nthe compiler took longer than ${Math.round(timeoutMs / 1000)} s and was stopped`;
      child.kill("SIGKILL");
    }, timeoutMs) : undefined;
    child.stdout.on("data", (chunk) => (stdout += chunk.toString()));
    child.stderr.on("data", (chunk) => (stderr += chunk.toString()));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? -1, stdout, stderr });
    });
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
    figures?: Record<string, { file: string; caption: string }>;
    genre?: string;
    language?: string;
    /** The art style the pictures are drawn in (lib/artstyles.ts); left out or "auto", the template's own. */
    art?: string;
    /** Told of the pictures the image model made during this compile (genimage.py), to bill and show them. */
    onGenerated?: (made: GeneratedPicture[]) => void;
    /** Told what the script asked of the image model and what failed, so the log says why pictures are missing. */
    onImages?: (report: ImageReport) => void;
    /** Told when the compile ran, and when within it the image models were at work (for the lecture's timing). */
    onTime?: (span: [number, number], images: [number, number][], prefetch?: Compiled["prefetch"], more?: Compiled) => void;
    /** Told when this compile gets its turn (PANIM_COMPILE_PARALLEL) and starts. */
    onStart?: () => void;
    /** Checked without making its pictures (they are made apart, makePictures): a section's check does not wait
     * on the image models, nor hold its writing slot while they work. */
    withoutPictures?: boolean;
  } = {},
): Promise<Compiled> {
  const compiler = path.join(REPO, "harness", "lecture", "compile_lecture.py");
  const body = compileBody(script, options);
  const args = [compiler, "-", "--json"];
  const began = Date.now();
  const { stdout, stderr } = await inCompileSlot(() => (options.onStart?.(), runPython(args, JSON.stringify(body), COMPILE_TIMEOUT_MS,
    options.withoutPictures ? { PANIM_IMAGES: "0" } : undefined)));
  try {
    const compiled = scriptJson<Compiled>(stdout);
    if (!compiled) throw new Error("no JSON");
    options.onTime?.([began, Date.now()], compiled.image_spans ?? [], compiled.prefetch, compiled);
    if (compiled.generated?.length) options.onGenerated?.(compiled.generated);
    if (compiled.images && !options.withoutPictures) options.onImages?.(compiled.images);
    const warnings = compiled.warnings ?? [];
    return { ...compiled, warnings: warnings.filter((w) => !w.startsWith("fixed: ")),
      fixed: warnings.filter((w) => w.startsWith("fixed: ")) };
  } catch {
    return { source: null, errors: [stderr.trim().slice(-600) || "the compiler returned nothing"], warnings: [] };
  }
}

/** The pictures a script asks for, made into the cache (several at once) without compiling it
 * (compile_lecture.py --pictures-only): a section's pictures, made in the background while the lecture is written.
 * Never throws: a picture that cannot be made is asked for again, and reported, by the compile that needs it. */
export async function makePictures(script: unknown, options: NonNullable<Parameters<typeof compileLecture>[1]> = {}): Promise<void> {
  const compiler = path.join(REPO, "harness", "lecture", "compile_lecture.py");
  const began = Date.now();
  try {
    const { stdout } = await runPython([compiler, "-", "--pictures-only"], JSON.stringify(compileBody(script, options)),
      COMPILE_TIMEOUT_MS);
    const made = scriptJson<Compiled>(stdout);
    if (!made) return;
    // The image models' time only: no compile ran ([began, began] adds nothing to the compile row).
    options.onTime?.([began, began], made.image_spans ?? [], made.prefetch, made);
    if (made.generated?.length) options.onGenerated?.(made.generated);
  } catch {
    // made, or not, by the compile that needs them
  }
}

function compileBody(script: unknown, options: NonNullable<Parameters<typeof compileLecture>[1]> = {}): unknown {
  // The figures table comes from the uploaded document, never from the model.
  return script && typeof script === "object"
      ? {
          ...(script as Record<string, unknown>),
          // How to teach is the writer's: the compiler checks only what the video needs to be drawn.
          teaching_rules: false,
          ...(options.style ? { style: options.style } : {}),
          ...(options.art && options.art !== "auto" ? { art: options.art } : {}),
          ...(options.figures ? { figures: options.figures } : {}),
          // The book's diagrams are redrawn by the diagram model (figures.ts) or rebuilt in Manim, never shown as the scan.
          ...(options.figures && Object.keys(options.figures).length ? { rebuild_figures: true } : {}),
          ...(options.genre ? { genre: options.genre } : {}),
          ...(options.language ? { language: options.language } : {}),
        }
      : script;
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
/** The subjects the page offers; "auto" lets the content decide (genre.py). */
export const SUBJECTS = ["mathematics", "physics", "chemistry", "biology", "history", "geography", "economics", "general"];

export async function classifySubject(text: string, chosen?: string): Promise<Subject> {
  const script = path.join(REPO, "harness", "lecture", "genre.py");
  const { stdout } = chosen && SUBJECTS.includes(chosen)
    ? await runPython([script, "--genre", chosen])
    : await runPython([script], text.slice(0, 20000));
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

export const LECTURE_TOOL = {
  type: "function" as const,
  function: {
    name: "write_lecture",
    description:
      "Write the whole lecture as a beat script. It is compiled into the Manim scene; errors and layout warnings come back and you call again with a fixed script.",
    parameters: {
      type: "object",
      properties: {
        script: {
          type: "object",
          description: "The beat script: title, sub, region, emblem, intro, chapters[{title, sub, narration, map, beats[{say, do[ops]}]}], recap, credits.",
        },
        more: {
          type: "boolean",
          description: "true when this is only the first part of a long lecture (its opening chapters): add_chapters brings the rest.",
        },
      },
      required: ["script"],
      additionalProperties: false,
    },
  },
};

/** Lectures longer than this are written a part at a time: write_lecture (more: true), then add_chapters. */
export const PARTS_OVER_MINUTES = 10;

export const ADD_CHAPTERS_TOOL = {
  type: "function" as const,
  function: {
    name: "add_chapters",
    description:
      "Add the next part of a long lecture begun with write_lecture (more: true): its next chapters, about 5 minutes. " +
      "Each part is checked when it arrives. done: true on the last part (with the recap): then the whole lecture is " +
      "checked (length, questions, examples, problems) and compiled. replace_from: n rewrites from chapter n on " +
      "(with replace_to: m, only chapters n to m).",
    parameters: {
      type: "object",
      properties: {
        chapters: { type: "array", items: { type: "object" }, description: "The next chapters, in the script's chapter shape." },
        recap: { type: "array", description: "The recap, with the last part: [[head, body], ...]." },
        replace_from: { type: "integer", description: "Replace chapters from this number (1-based) on, instead of adding after the last." },
        replace_to: { type: "integer", description: "With replace_from: replace only chapters replace_from..replace_to (1-based, inclusive), keeping those after; replace_from - 1 inserts before chapter replace_from." },
        done: { type: "boolean", description: "true when this is the last part." },
      },
      required: ["chapters", "done"],
      additionalProperties: false,
    },
  },
};

/** The system prompt for a lecture template. */
/** The narration languages the page offers; "auto" follows the content's. */
export const LANGUAGES = ["auto", "english", "hindi", "hinglish"] as const;
export type Language = (typeof LANGUAGES)[number];

/** How the lecture speaks and what it writes on screen, for a chosen language (nothing for "auto"). */
export function languagePrompt(language: Language | undefined): string {
  if (language === "english") {
    return ["", "LANGUAGE: ENGLISH. Narration and everything on screen in simple English, whatever the content's language.", ""].join("\n");
  }
  if (language === "hindi") {
    return ["", "LANGUAGE: HINDI. Narration and everything on screen in simple spoken Hindi (Devanagari), whatever the",
      "content's language; a technical term may be followed once by its English word in brackets.", ""].join("\n");
  }
  if (language !== "hinglish") return "";
  return [
    "",
    "LANGUAGE: HINGLISH, the way a good Indian teacher explains in a class video. The subject is in English; it is",
    "explained in easy spoken Hindi.",
    "  - Every \"say\" line (and each chapter's \"narration\" and the \"intro\") is Hinglish: the sentence's grammar and",
    "    connecting words in simple Hindi WRITTEN IN DEVANAGARI (है, तो, मतलब, यानी, जैसे, देखो, चलो, अब सोचो), and the",
    "    subject's terms and everyday English words in English, in Latin letters:",
    "      \"Force मतलब एक push या pull है।\"  \"जब net force zero होता है, तो acceleration भी zero होता है।\"",
    "      \"Example लो: bus अचानक brake लगाती है, तो आप आगे की तरफ गिरते हो। क्यों? Inertia की वजह से।\"",
    "  - NEVER write Hindi in Latin letters (not \"matlab\", \"hota hai\", \"dekho\"): the voice reads Devanagari as Hindi",
    "    and Latin letters as English, so Romanised Hindi sounds wrong.",
    "  - Keep the technical terms in English (force, mass, velocity, acceleration, friction, momentum, equilibrium,",
    "    numerator, photosynthesis) as teachers say them; do not replace them with pure Hindi words (बल, वेग,",
    "    संवेग). You may say the book's Hindi word once: \"Force, जिसे Hindi में बल कहते हैं...\".",
    "  - Say numbers and units the way they are spoken in class, units in words: \"10 newton\", \"5 meter per second",
    "    square\", \"m g sin theta\".",
    "  - EVERYTHING ON SCREEN IS IN ENGLISH: the title, chapter titles, panel headings, key points, define cards",
    "    (term and meaning), labels in diagrams and drawings, questions and their choices, problem text,",
    "    given and find, working, and the recap. Only the narration (the captions) is Hinglish.",
    "",
  ].join("\n");
}

/** A reference video's parts, as the model sees them, and the rules for following its structure. */
export function referencePrompt(ref: {
  video?: { title?: string; channel?: string; duration?: number; generated?: boolean };
  parts?: { part: number; start: number; end: number; text: string }[];
}): string {
  const parts = ref.parts ?? [];
  if (!parts.length) return "";
  const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  // A long video's transcript is shortened evenly, part by part, rather than cut off at the end.
  const budget = 70000;
  const total = parts.reduce((n, p) => n + p.text.length, 0);
  const share = total > budget ? budget / total : 1;
  const v = ref.video ?? {};
  return [
    "",
    `REFERENCE VIDEO. This lecture remakes a video${v.title ? ` ("${v.title}"${v.channel ? `, ${v.channel}` : ""})` : ""}` +
      `${v.duration ? ` of ${clock(v.duration)}` : ""}. Its transcript is below, in ${parts.length} parts, in the order it teaches.`,
    "Follow its structure:",
    "  - The same topics in the same order. Every part is taught, by one chapter or more (a short part may share a",
    "    chapter with the next); give each chapter \"from_part\": the number of the part it teaches. No topic the",
    "    video does not cover; more depth, examples and explanation on its topics are welcome.",
    "  - Its examples, analogies, questions and solved problems, each one taught again in your own words and with",
    "    its picture: when it solves a numerical, solve the same numerical with the same numbers, step by step with",
    "    work lines; when it draws or describes a figure (a block on an incline, a pulley, a graph), build that",
    "    figure (a manim drawing or a diagram) and reveal its parts as you explain them.",
    "  - Its way of teaching: where it asks the viewers something, put a question on the stage; where it recaps, recap.",
    "  - Never copy its sentences: explain each idea again, as clearly as it does or more.",
    ...(v.generated ? ["  - These are YouTube's automatic captions: they mishear words (\"enersia\" for inertia, \"new ton\"). Read",
      "    through them to what was meant."] : []),
    "",
    ...parts.map((p) => {
      const text = share < 1 ? `${p.text.slice(0, Math.max(400, Math.floor(p.text.length * share)))} …` : p.text;
      return `PART ${p.part} (${clock(p.start)}-${clock(p.end)}): ${text}`;
    }),
    "",
  ].join("\n");
}

/** The model that writes the free-form Manim blocks (PANIM_MANIM_MODEL). When set, the script writer only plans
 * each block ("plan"), and this model writes its code (lib/manimcoder.ts); when not, the writer writes the code. */
export function manimModel(): string | undefined {
  return process.env.PANIM_MANIM_MODEL?.trim() || undefined;
}

/**
 * The small built drawings there once were (the physics presets, sketch, graph, plot, motion, trace, sweep, the
 * simulations and the counter): free-form Manim draws every such picture now. A script that still uses one has it
 * turned into a manim op (manimcoder.ts freeDrawings), or left out by the compiler.
 */
export const FREE_DRAWN_OPS = ["incline", "pulley", "piston", "spring", "pendulum", "projectile", "circuit", "lever", "lens",
  "sketch", "graph", "plot", "motion", "trace", "sweep", "sim", "counter"];

/** The writer's section on drawings: free-form Manim draws them all. */
const FREE_DRAWINGS_HEAD: string[] = [
  "ANY FIGURE YOU DESIGN YOURSELF, IN ANY SUBJECT, IS FREE-FORM MANIM (below): a graph, a free-body diagram,",
  "apparatus, a circuit, a construction, a wave, a titration, a cell dividing, a Punnett square -- and as much a",
  "history, geography, economics or language figure: tribute flowing up the feudal ranks, a river's long profile,",
  "a population pyramid changing over decades, a trade balance tipping, prices chasing wages, a story's plot arc,",
  "a sentence taken apart into its parts. Anything with its own geometry, or that moves. Plan (or write) it",
  "yourself, built over the beats that explain it, every part labelled, moving where the narration describes",
  "motion. Whether a paragraph is a manim figure, a diagram, a timeline, a map or a picture is your choice.",
  "",
  "WORKED SOLUTIONS AND PROBLEMS:",
  '  {"op":"work","id":"w","title"?:"Along the slope","lines":["N = mg\\cos\\theta"],"box"?:true}   A WORKED SOLUTION:',
  "   the same id adds lines under the last ones, one or two per beat, each step said in the narration. Lines are",
  "   TeX (\\frac{a}{b}, v^2, \\sqrt{2gh}, \\text{m/s}); a line with words is shown as a sentence. box rings the",
  "   answer. A working about a figure (a derivation from a ray diagram, a solution from a free-body diagram) goes",
  '   beside it: give the figure "area": "left" and its beats can point at the figure while the working goes on.',
  '  {"op":"problem","id":"p1","title":"Problem 1","text":"<the full question>","given":["m = 5 kg","\\theta = 30°"],',
  '   "find":"a","think"?:5}   A LONG QUESTION: its statement across the top and its solution beside it',
  '   ({"op":"work","id":"p1",...}). Its figure is a free-form manim drawing on the beats before it. think leaves',
  "   seconds of silence for the class to try it first.",
  "",
];

/** How free-form Manim is written: the writer's own rules, or the Manim model's (lib/manimcoder.ts). */
export const MANIM_RULES: string[] = [
    'FREE-FORM MANIM, in any subject: a figure you design yourself, whenever it teaches better than the other kinds',
    "(a banked road with a car, a ray diagram, a derivation whose terms move into the next line; equally a feudal",
    "pyramid with tribute flowing up, a river's long profile, a supply and demand shift, a story's plot arc):",
    '  {"op":"manim","id":"pulley1","code":"wedge = Polygon(...)\\nself.play(Create(wedge))"}   the ONLY op on its beat.',
    "   Never a map in it (no outline of a place, no lon/lat): maps are the map operations'.",
    '   "area": "left" on a figure (its first beat decides) when it is explained ALONGSIDE something: a derivation',
    "   or solution, notes or reasoning built line by line ({\"op\":\"work\"}), a question, a definition. The figure is drawn in the",
    "   board's left half (x from -6.9 to -0.4) and what goes beside it fills the right half; neither moves, so the",
    "   figure's later beats can point at, label, highlight or add to it while the working beside it stays and goes",
    "   on (the line that uses an angle, and the angle ringed on the figure). Without it, a figure has the whole",
    "   board, and a working beside it shrinks it into the left half until the figure's next beat. Whether a",
    "   figure and its working share the board is your choice, for the learning.",
    "   code is the body of Manim's construct() for this beat: build objects and self.play(...) them. Beats with the",
    "   same id share their variables, in order: build the figure on one beat, then on the next ones Indicate a part,",
    "   draw its forces with GrowArrow, TransformFromCopy a body into its free-body diagram, Write an equation and",
    "   move it with .animate.next_to(...). Its animations happen while the beat's sentence is said: give each beat",
    "   only what its sentence describes (about as long as the sentence), and the next step to the next beat.",
    "   Rules (the compiler runs each block before accepting it, and refuses one that breaks them, with the reason):",
    "   - Names: everything Manim exports (Polygon, Line, Arrow, Circle, Square, Rectangle, Arc, Dot, DashedLine,",
    "     MathTex, Text, VGroup, SurroundingRectangle, Create, Write, FadeIn, FadeOut, GrowArrow, Indicate,",
    "     TransformFromCopy, ReplacementTransform, TransformMatchingShapes, LaggedStart, UP, DOWN, LEFT, RIGHT, PI...)",
    "     and np. No imports, no classes, no while loops, no self.camera / self.mobjects / self.clear: only",
    "     self.play, self.wait, self.add and self.remove.",
    '   - Pictures: picture("a steam locomotive, side view", height=2) is a picture of a real thing made for the',
    "     lecture by the illustration model, in its style, as a cutout with no background and no words in it (width=",
    "     caps its width). Place, move and scale it like any mobject, label its parts with arrows and Text beside it,",
    "     bring it in with FadeIn (not Create or Write: it is an image). Write the description in the call itself, in",
    "     English. Never a map.",
    "   - The board: x from -6.9 to 6.9, y from -3.05 to 2.85 (a title strip above, the caption below); nothing",
    "     outside it. Lay it out yourself: the figure on one side, its working on the other, text never on a line.",
    '   - A figure with "area": "left": everything within x from -6.9 to -0.4 (the right half is the working\'s).',
    "   - Colours: INK for lines and text (the style's ink: it shows on dark and light boards), MUTED_INK for faint",
    '     parts, and PALETTE["ROSE"] (forces), PALETTE["GREEN"] (velocity, normal), PALETTE["GOLD"] (angles,',
    '     answers), PALETTE["RIVER"], PALETTE["TERRA"], PALETTE["TEAL"], PALETTE["VIOLET"] for bodies and highlights.',
    "     Text(..., font_size=24-32) for words; MathTex for every symbol and equation.",
    "   - Animations the phone plays: Create, Write, FadeIn/FadeOut (shift= is fine), GrowArrow, DrawBorderThenFill,",
    "     Indicate, Transform, TransformFromCopy, ReplacementTransform, TransformMatchingShapes, LaggedStart,",
    "     .animate with shift, move_to, next_to, to_edge, scale, rotate, set_color, set_opacity; default rate_func.",
    "     Continuous motion works too: add_updater (always_redraw, a ValueTracker driving a DecimalNumber or a",
    "     curve) and MoveAlongPath; the phone gets it as frames of moving shapes. Remove updaters when done.",
    "   - Clean up after yourself within an id: FadeOut what the next step no longer needs. The next picture or the",
    "     chapter's end takes the rest away.",
    "   Every graph, apparatus, maths or science drawing and every moving process is a manim block: there are no",
    "   presets, sketches, graphs or sims. Point at its parts on later beats of the same id (Indicate, a ring, a",
    "   colour) as the narration names them.",
    "   QUALITY: every manim picture is judged against a fine textbook diagram, and the compiler sends back one that",
    "   does not read cleanly (words under font size 20, two labels overlapping, a line running through a label):",
    "   - Plan it before writing: what goes where on the board, the main subject large (use most of the 13.8 x 5.9",
    "     board), its labels beside what they name with room to spare, nothing crammed into a corner.",
    "   - True geometry and science: angles at the angle they are, forces from the point they act on, rays obeying",
    "     the laws, values and units on everything the lesson names; proportions believable.",
    "   - Words: Text font_size 24-32, MathTex for symbols and equations, each label next_to its part with buff",
    "     0.15-0.3, never on a line; the same size for labels of the same kind.",
    "   - Colour with meaning: INK for lines and words, one PALETTE colour per kind of thing (forces ROSE, motion",
    "     GREEN, highlights GOLD), fills at fill_opacity 0.2-0.6 so lines and words stay readable.",
    "   - Built as it is said: the frame first, then each part on the beat that names it, then what it shows.",
    "   DIAGRAMS FREE MANIM BUILDS WELL that no other op draws (worked examples of each: harness/lecture/manim_catalog.py),",
    "   built over the beats as a teacher builds them on a board, frame first, then parts, then what it shows:",
    "   MATHS: Venn diagram (circles, the overlap filled with Intersection); number line with an interval (NumberLine,",
    "     open and closed ends); unit circle (cos and sin as lengths, the angle swept with a ValueTracker); squares on a",
    "     right triangle (Pythagoras); area model of a product; fraction bars; probability tree; mapping diagram",
    "     (function arrows between two ovals); vector addition head to tail; linear transformation of the plane",
    "     (NumberPlane + ApplyMatrix); area under a curve (Axes.get_riemann_rectangles, then thinner); pie chart",
    "     (AnnularSector slices and a key); slope triangle (rise over run); bar model for a word problem.",
    "   PHYSICS: free-body diagram in a real setting (a car on a banked road); ray diagram for a lens or mirror;",
    "     electric field lines between charges; transverse wave (wavelength, amplitude); circuit diagram with symbols",
    "     and current arrows; energy level diagram with a transition; projectile with velocity components.",
    "   CHEMISTRY: shell (Bohr) model; reaction energy profile (activation energy, enthalpy change); part of the",
    "     periodic table coloured by type.",
    "   BIOLOGY: Punnett square; pedigree chart; food web (a network of who eats whom).",
    "   ECONOMICS, GEOGRAPHY, HISTORY: supply and demand (a curve shifting); climate graph (rain bars, temperature",
    "     line); two-by-two matrix; cause-and-effect fishbone; flow (Sankey) diagram; parallel timelines (swimlanes).",
    "   COMPUTING: binary search tree (a search lit node by node); array and linked list; stack push and pop; logic",
    "     gate with its truth table; weighted graph with its shortest path.",
];

/** The writer's part when another model writes the Manim (PANIM_MANIM_MODEL): what to draw, not the code. */
export const MANIM_PLAN: string[] = [
  'FREE-FORM MANIM, in any subject: a figure you design yourself, whenever it teaches better than the other kinds',
  "(a banked road with a car, a ray diagram, a derivation whose terms move into the next line, a Venn diagram, a",
  "Punnett square; equally a feudal pyramid with tribute flowing up, a river's long profile, a supply and demand",
  "shift, a story's plot arc, a sentence taken apart into its parts...):",
  '  {"op":"manim","id":"pulley1","plan":"..."}   the ONLY op on its beat. A Manim specialist writes the code from',
  "   your plan, so the plan is precise: on this beat, what is drawn or moved, where on the board (left, right,",
  "   centre), its sizes, angles and values, every label's words, colours with meaning (forces, motion,",
  "   highlights), and which earlier parts it points at or changes. Beats with the same id are one figure built",
  "   over several beats: plan the frame first, then each part on the beat that names it, then what it shows.",
  "   The figure may hold pictures of real things (a steam locomotive, a farmer, a cell under a microscope): name",
  "   each in the plan (\"a picture of ...\") and the specialist puts the illustration model's picture there.",
  '   A book figure rebuilt this way is marked "from_figure" (its picture goes to the specialist). Never a map.',
  '   "area": "left" on a figure (its first beat decides) when it is explained ALONGSIDE something: a derivation',
  "   or solution, notes or reasoning built line by line ({\"op\":\"work\"}), a question, a definition. The figure is drawn in the",
  "   board's left half (x from -6.9 to -0.4) and what goes beside it fills the right half; neither moves, so the",
  "   figure's later beats can point at, label, highlight or add to it while the working beside it stays and goes",
  "   on (the line that uses an angle, and the angle ringed on the figure). Without it, a figure has the whole",
  "   board, and a working beside it shrinks it into the left half until the figure's next beat. Whether a",
  "   figure and its working share the board is your choice, for the learning.",
  "   Every graph, apparatus, maths or science drawing and every moving process is planned this way: there are",
  "   no presets, sketches, graphs or sims. Its later beats point at the parts the narration names.",
];

export function lecturePrompt(
  template: Template,
  minutes = DEFAULT_LECTURE_MINUTES,
  subject?: Subject,
): string {
  return [
    "You write narrated lectures that explain a topic simply, for a phone renderer, as a beat script that a compiler turns into Manim.",
    `The style is ${template.name} (engine style "${template.style}"). Do not choose colours outside it.`,
    minutes > PARTS_OVER_MINUTES
      ? "WRITE IT IN PARTS of about 5 minutes (2-3 chapters each), so no single reply is huge: first write_lecture with " +
        '{"script": {title, sub, region, intro, chapters: [the first chapters]}, "more": true}; then add_chapters ' +
        '{"chapters": [the next chapters], "done": false} for each next part; the last add_chapters has "done": true and ' +
        "the recap. Each part is checked when it arrives (fix and resend a part that returns errors). Then reply with " +
        "one short sentence."
      : "Call write_lecture once with the whole script. If it returns errors, fix them and call again. Then reply with one short sentence.",
    "",
    ...(subject
      ? [
          `SUBJECT. This is a ${subject.label} lecture. ${subject.guidance}`,
          `The map is used ${subject.map} in ${subject.label.toLowerCase()} lectures. Often useful in them: ${subject.kit.join(", ")} (any kind below may be used).`,
          "",
        ]
      : []),
    "WHAT MATTERS: the quality of the learning, and everything in the source covered. How to teach and how to show",
    "it are yours to decide; nothing about your style, the number of questions or examples, or the length is",
    "counted. When the lecture comes with a transcript (below), it is the teaching, said line for line: your work is",
    "the pictures that make each line understood, chosen and paced as you judge best.",
    "",
    "A QUESTION FOR THE CLASS, when you put one on the stage (then its answer on a later beat):",
    '  {"say":"Which of these is a force?","do":[{"op":"question","text":"Which of these is a force?",',
    '    "choices":["Kicking a ball","Sleeping","Thinking"],"answer":"A","think"?:5}]},',
    '  {"say":"The answer is A. ...","do":[{"op":"answer"}]}',
    "  choices: 2-5 short answers, answer: the right one's letter; or an open question with no choices and its answer in",
    '  words. The video leaves think seconds (7 by default) of silence with a timer before the answer. {"op":"option",',
    '  "choice":"B"} marks one choice while it is talked about: a wrong one crossed out, the right one ringed.',
    "",
    "PAUSES. The video pauses after every line and longer at the end of each paragraph by itself. After a line that",
    "needs a moment to sink in (a key definition, a surprising fact), add \"pause\": 1-3 (extra seconds).",
    "",
    "EVERY PICTURE IS MADE ONE OF THREE WAYS, and which way is your judgement, picture by picture, for the learning:",
    "  1. BUILT IN MANIM: diagrams, timelines, equations, molecules, the map, and free-form manim for every other",
    "     drawing: whatever the board's own shapes build exactly -- and built in full detail: every label,",
    "     value, arrow and angle, the real geometry and proportions, revealed a part at a time.",
    '  2. A DETAILED DIAGRAM MADE BY THE DIAGRAM MODEL ({"draw": "<the picture in words>", "labels": [...]}): a',
    "     labelled textbook drawing the board's shapes cannot build exactly (a cell, a cross-section, an organ, a",
    "     machine), made for the lecture by an image model that draws exact diagrams (DETAILED DIAGRAMS, below).",
    '  3. MADE BY THE ILLUSTRATION MODEL ({"generate": "<what it shows, in English>"}): a picture of a real thing the class',
    "     should see -- a person, a place, an animal, a plant, an object, a scene -- made as a CUTOUT with no border",
    "     and no background, in the lecture's style, so it sits on the board like a sticker. Say what it is and how it",
    '     is seen ("a steam locomotive, side view", "a honey bee on a flower, close up"). It is made richly detailed',
    "     and brought onto the board whole. It has no words in it; to name its parts, give \"labels\" (up to 6",
    '     short names in the lecture\'s language, parts that are really in it): {"op":"picture","generate":"a medieval',
    '     knight in armour on horseback, side view","labels":["helmet","lance","shield","chain mail"]}: each is written',
    "     beside the picture with a line to its part.",
    "     ONE PICTURE PER THING: the same person, place or thing shown again (Charlemagne in three chapters) is asked",
    '     for in the very same "generate" words each time, and the picture already made is used again.',
    "  Only teaching and learning content is shown: never the book's furniture (QR codes, logos, scan boxes, page",
    "  headers), even when the transcript or a figure mentions one.",
    "  Nothing is searched for on the web, and there are no icons or emoji. Never a random image; every picture",
    "  shows what is being said. process and quote are boxes of words: use them rarely. Captions in the lecture's",
    "  language.",
    "",
    "A beat is one narration line (say) and the operations that go with it (do). One idea per beat, at most two caption lines",
    "(under about 180 characters, 15-30 words), at most four operations. Every number you state must be in the content you",
    "were given or be well established; say 'about' for rough figures.",
    "",
    "Script shape:",
    '{"title", "sub", "region": {"country": "India", "view": "ind"} | {"state": "Rajasthan", "country": "India"} |',
    '   {"area": "World" | a continent ("Asia", "Europe", "Africa") | a world region ("South Asia", "Middle East",',
    '   "Western Europe", "Southern Africa", "Indian subcontinent")} | null,  (an area\'s "state" op fills a country)',
    ' "intro", "chapters": [{"title", "sub", "narration": "Chapter one. ...",',
    '   "beats": [{"say": "...", "paragraph"?: true, "pause"?: 2, "do": [ops]}]}],',
    ' "recap": [["Head", "short body"]], "credits": "..."}',
    "",
    "Operations (colour = palette name SAND RIVER GOLD ROSE TEAL GREEN VIOLET MUTED CREAM HI, or #RRGGBB):",
    '  {"op":"panel","title","sub"?}          the topic heading; start each topic with one',
    '  {"op":"fact","text","color"?}          ONE key point, a few words (under 60 characters); it replaces the last',
    '  {"op":"stat","value","label","color"?} a key number with a label, in the same place',
    '  {"op":"bars","items":[["label",n]...],"unit"?,"color"?}  a bar chart, at most 8 bars',
    '  {"op":"clear"}                         clear the heading and key point',
    "LITTLE TEXT ON SCREEN. A chapter without a map is taught on a BOARD: the whole frame is the picture, and the words",
    "on screen are only the topic heading and one key point over it. With a map, the map takes the left and a side",
    "panel holds at most 3 short points under its title (the compiler rejects more). The narration carries the",
    "explanation; the screen shows pictures, diagrams, graphs and working, not paragraphs.",
    "CHOOSING THE VISUAL. Pick each paragraph's visual by WHAT IT SHOWS, using the maker that draws that best (no kind",
    "is preferred for its own sake; let the visuals be as varied as the content):",
    "  - A real, complex STRUCTURE of a living thing or a real object -- an organ (heart, kidney, nephron, eye, brain),",
    "    a cell and its organelles, a flower or a leaf in section, a skeleton, realistic lab apparatus, a machine's",
    "    insides, a landform in section (a volcano, a river's meander) -> a DETAILED DIAGRAM by the diagram model",
    '    ({"op":"picture","draw":...,"labels":[...]}), labelled as a textbook draws it. NEVER free-form Manim: Manim',
    "    reduces these to blobs and boxes (the compiler refuses a biology structure in Manim).",
    "  - Anything EXACT, MATHEMATICAL OR MOVING -- a graph of a function or of data, axes and curves, a number line,",
    "    geometry and constructions, vectors and forces, a free-body or ray diagram, a circuit, a wave, an orbit,",
    "    particles moving (diffusion, a gas), a balance, a derivation whose terms move -> FREE-FORM MANIM. Never the",
    "    diagram model: it draws axes and values by eye (the compiler refuses a graph asked of it).",
    "  - HOW THINGS CONNECT, when the connections are the lesson (a process in steps, a cycle, a hierarchy, causes",
    "    and effects) -> a DIAGRAM of boxes and arrows (below).",
    "  - WHERE -> the MAP. WHEN, several dated events -> a TIMELINE. A real PERSON, PLACE OR THING the class should",
    "    see -> a PICTURE (generated). The book's own figure of it -> that FIGURE first.",
    "  - Two or three things side by side -> COMPARE. A term -> DEFINE. A key number -> STAT; a few quantities ->",
    "    BARS, many or changing over time -> a Manim chart. A law or a reaction -> EQUATION; a molecule's structure",
    "    -> MOLECULE. A check of understanding -> a QUESTION.",
    "  A figure can mix makers: a Manim figure may hold a generated picture (picture(), below), and a diagram's node",
    "  a picture or a detailed drawing.",
    "THE STAGE (the board, or the left half beside a map). Plan the stage a",
    "PARAGRAPH at a time (3-5 beats that explain one idea), never a new picture every sentence. Mark the first beat of",
    "each paragraph with \"paragraph\": true and give it the paragraph's visual; the beats after it build on that",
    "visual (reveal the next part of a diagram, focus on a node, add a marker) or simply leave it up. A picture stays",
    "up until the next one, so a paragraph without its own keeps the last. EVERY CHAPTER OPENS WITH A PICTURE on its",
    "first beat: the board is empty until one is put up (the compiler refuses a science or mathematics chapter whose",
    "first three beats show nothing). The kinds of visual:",
    "  WHERE something is (a place, a route, a spread across a region) -> the MAP (map operations below). A chapter",
    "  with no map operation has no map at all. The map is the ONLY way to show geography: it is drawn from Natural",
    "  Earth's data through Cartopy, true to the coastline. NEVER put a map, a country's outline, borders, a",
    "  continent or a route across land or sea in a draw, a manim block or a generated picture: the compiler refuses",
    "  it. An empire's or a kingdom's extent: fill its states (state) on the map, or trace it with path and arrow.",
    "  A DIAGRAM: boxes joined by arrows, its nodes the things, each with a picture where seeing it helps (PICTURES",
    "  BESIDE WORDS), shown a node or two at a time across the paragraph's beats:",
    '  {"op":"diagram","id":"chain","kind":"flow"|"cycle"|"hub"|"pyramid","steps"?:true,"title"?,',
    '   "nodes":[{"id":"sun","label":"Sun","picture":{"generate":"the sun"}},{"id":"plants","label":"पौधे"}],',
    '   "edges"?:[["sun","plants","light"]],"show"?:["sun","plants"]}   THREE KINDS. flow takes its layout from its',
    "                                          edges: none or a chain = in order; edges that only branch downwards = a",
    "                                          hierarchy; branches, joins, loops, shapes or lanes = a flowchart. cycle =",
    "                                          round; hub = the first node in the middle. \"steps\": true numbers a",
    "                                          chain's cards. Labels in the lecture's language, pictures in English.",
    "                                          2-9 nodes (a flow: up to 16; a hierarchy: up to 20).",
    '  MEANING IN A DIAGRAM: a node may say what it is, "kind": "person" | "place" | "event" | "idea" (a portrait',
    "  card, a pin, a dated tag, a soft card); an edge's 4th item says what the arrow means and so how it is drawn:",
    '  "gives" (plain), "owes" / "promises" / "duty" (dashed), "power" / "rules" (bold); a key to them is drawn',
    '  under the diagram. RANKS (the three orders, feudal ranks, a food pyramid) -> "kind":"pyramid": nodes from the',
    '  top rank down, each with "items" (what they do). Show a diagram part by part: it is built as the lines name',
    "  its parts, and a focus dims the rest while one part is talked about.",
    "  PICTURES BESIDE WORDS: a diagram's node, a timeline's event and a map marker's label may carry a picture,",
    '  "picture": one of {"generate":"Mahatma Gandhi, an illustrated portrait"} (made by the image model, a cutout),',
    '  {"draw":"A steam engine, side view"} (a detailed diagram by the diagram model) or {"figure":"fig3"} (one of the book\'s',
    "  figures): the three ways above, your choice for each. Use them where seeing the",
    "  thing teaches it (each kind of rock, the leaders on a timeline, the crop grown at each place), not on every",
    "  box. They are laid out so no picture or word covers another.",
    "  HIERARCHIES (a whole, its kinds, their kinds: kinds of rock, the classification of living things, branches of",
    "  government, types of UML diagram): a flow with edges [parent, child], as deep as",
    "  the subject goes. It is drawn as a textbook draws one: the main thing at the top, its subcategories in a row",
    "  under it, each centred over its own subcategories, and so on down, joined by right-angled connectors with an",
    "  open triangle at the parent (\"is a kind of\"); long lists of leaves are stacked in columns so it stays big.",
    "  Reveal it a level at a time.",
    '  FLOWCHARTS: a process that branches, decides, joins or loops back is a "flow" whose edges say so; it is',
    "  drawn as a flowchart, laid out in ranks that follow the flow, crossings kept few, loops drawn round",
    "  the outside, each arrow curving from its own place on a box. Each node may have:",
    '   "shape": "start" | "end" (pills), "process" (box, the default), "decision" (diamond: a yes/no question,',
    '   label ending "?", its edges labelled "Yes"/"No" or the cases), "io" (what goes in or comes out: data, a',
    '   reading, a product), "store" (a drum: blood, a tank, a database, a reservoir), "note" (a remark);',
    '   "lane": who or where does it ("Lok Sabha", "Liver", "Customer"): lanes become bands, one per name.',
    '   Edges are [from, to, label?, style?], style "dashed" (optional, indirect, feedback) or "bold" (the main',
    '   path). Use one for a decision procedure (an algorithm, a diagnosis, a legal process), a process with',
    '   feedback (thermostat, homeostasis, the nitrogen cycle\'s branches), or who-does-what (a supply chain, a',
    "   bill becoming law). Reveal it a branch at a time so the class follows each path.",
    "  The diagram is drawn on the board as a teacher draws. A concrete thing gets a picture (a cow, a factory, rain);",
    "  an idea gets none, just its words. A flow or cycle has dots running along its arrows, the way the process goes",
    '  ("flow": false turns them off; "flow": true adds them to a tree or hub): the class sees it happening.',
    "  A diagram may be of words only (categories, kinds, steps):",
    '  {"op":"diagram","id":"forces","kind":"flow","title":"Types of forces","nodes":[',
    '   {"id":"all","label":"Forces"},{"id":"contact","label":"Contact forces","items":["Friction","Normal","Tension"]},',
    '   {"id":"field","label":"Non-contact forces","items":["Gravity","Magnetic","Electric"]}],',
    '   "edges":[["all","contact"],["all","field"]]}   the whole above its kinds, each a card listing up to 5 items;',
    '   numbered steps in order: {"op":"diagram","id":"fbd","kind":"flow","steps":true,"nodes":[{"id":"s1","label":"Pick',
    '   the body"},{"id":"s2","label":"Draw every force on it"},{"id":"s3","label":"Choose axes"}]}. Reveal kinds or',
    "   steps a beat at a time with show and reveal, as you talk about each.",
    '  {"op":"reveal","diagram":"chain","nodes":["deer"]}   the next nodes of that diagram, with their arrows',
    '  {"op":"focus","diagram":"chain","node":"plants"}     a ring around one node while you talk about it',
    "  A HARD WORD -> {\"op\":\"define\",\"term\":\"Biodiversity\",\"meaning\":\"<plain words>\"}",
    "  TWO OR THREE KINDS OF SOMETHING -> {\"op\":\"compare\",\"title\"?,\"columns\":[{\"title\":\"Reserved\",",
    '   "points":["up to 4 short lines"]},...]}',
    "  A QUESTION FOR THE CLASS -> question, then answer on the next beat (see QUESTIONS FOR THE CLASS).",
    "  ONE OP FOR ANY PICTURE ON THE STAGE: {\"op\":\"picture\", one of \"generate\" | \"draw\" | \"figure\",",
    "  \"caption\"?}: the same keys as PICTURES BESIDE WORDS. ONE picture at a time, never several side by side.",
    "  A PERSON, A PLACE, A LIVING THING OR AN OBJECT THE CLASS SHOULD SEE -> a picture the image model makes:",
    '  {"op":"picture","generate":"Sunderlal Bahuguna, an elderly Indian environmentalist hugging a tree, illustrated",',
    '  "caption":"सुंदरलाल बहुगुणा"}. A paragraph about several things -> ONE scene with all of them in it, each',
    '  labelled where it is: {"op":"picture","generate":"a medieval village: a priest at the church door, a lord on',
    '  horseback, peasants ploughing a field","scene":true,"labels":["Priest","Lord","Peasants"]} (up to 6 labels,',
    "  each a short name of something drawn in it).",
    '  A SETTING, AN EVENT, A WAY OF LIFE (a Mughal court, a village market, the Battle of Panipat, a monsoon field)',
    '  -> a whole scene instead of a cutout: {"op":"picture","generate":"...","scene":true}: drawn edge to edge with',
    "  its ground, sky and the people in it, across the stage. Cutouts for one person or thing; scenes for a place",
    "  and what happens in it. A person in several pictures (a portrait, then on horseback) is drawn alike in each:",
    "  name them the same way every time and the first picture of them is matched.",
    '  "move"?: "bob" (a boat on water), "sway" (a flag, a tree in wind), "breathe" (a heart, a lung), "drift" (a',
    "  ship or caravan moving on): the picture moves gently once drawn. Only where moving is what the thing does.",
    '  "points"?: ["2-4 short lines"] -> the split layout: the picture large on the left, the few things to take away',
    "  from it on the right (a person and what they did, a tool and what it was for). Not with labels.",
    '  THE LECTURE\'S EMBLEM: "emblem": "<one simple object that stands for the whole topic>" at the top of the script',
    '  ("a golden crown" for feudalism, "a spinning wheel" for the freedom struggle, "a steam engine" for the',
    "  Industrial Revolution): shown on the title, every chapter card and beside the chapter's name. The same words in",
    "  every part of a series.",
    "  THE DOCUMENT'S OWN FIGURES come first whenever one shows what the paragraph explains:",
    '  {"op":"picture","figure":"fig2"} (one figure a beat).',
    "  A FIGURE OF YOUR OWN DESIGN, in any subject -> FREE-FORM MANIM (below); a molecule or a law -> molecule or",
    "  equation; dates -> a timeline (below).",
    "  A TEXTBOOK DIAGRAM you cannot build exactly (the parts of a cell, a cross-section) -> a detailed diagram made",
    "  by the diagram model (DETAILED DIAGRAMS, below).",
    "EXPLAINED SIDE BY SIDE, in any subject: whenever the class should keep looking at a picture while it is",
    "  reasoned about, give it a column that builds up beside it, a line or two a beat as the narration says them:",
    '  {"op":"work","id":"n","title"?:"What each part does","lines":["Palisade cells: packed with chloroplasts."],',
    '  "box"?:true}. The lines are TeX for maths, or plain sentences for words. Beside any picture on the stage: a',
    "  diagram (its parts still revealed and focused while the column grows), a picture, a figure, a timeline. A",
    "  picture is moved into the left half and the column takes the right; a wide one (a timeline, a long chain)",
    "  keeps the board's width along the top, the column below it. For: a derivation or a solution from its",
    "  figure, the steps of a process beside its flowchart, causes or consequences beside a chain of events, what",
    "  each part does beside a labelled structure, why each date matters beside a timeline, notes on a source",
    "  beside its picture. The same id adds lines under the last; box rings the conclusion. Choose it when seeing",
    "  the picture and the reasoning together teaches better than either alone; otherwise keep the board simple.",
    "Other stage operations:",
    '  {"op":"molecule","name":"glucose" | "H2O" | SMILES,"label"?}   a structural formula, atoms in CPK colours.',
    "   ONLY where the narration explains that structure (its bonds, shape, groups, isomers), and once a chapter: a",
    "   substance only named is said, not drawn. The compiler leaves out a molecule on a beat that explains no",
    "   structure, and one already on the board in the chapter.",
    '  {"op":"equation","tex":"6CO_2 + 6H_2O -> C_6H_{12}O_6 + 6O_2","label"?}   a law or a reaction, large',
    '  {"op":"process","steps":["Evaporation","Condensation","Rain"],"cycle"?:true,"title"?}   steps in boxes',
    '  {"op":"timeline","events":[["1526","Panipat"],["1556","Akbar"]],"title"?}   an era across the stage, still',
    '   an event may carry a picture: ["1930","Dandi March",{"generate":"Gandhi walking with marchers to the sea, illustrated"}] (see PICTURES BESIDE WORDS)',
    '  {"op":"quote","text":"...","who":"Akbar"}   a primary source, in its own words',
    "Give a beat about a person, movement or place \"about\":\"<English name>\" (a Hindi beat especially): a paragraph",
    "left without a visual then gets their pictures automatically. Do not invent a picture for every sentence.",
    "",
    ...FREE_DRAWINGS_HEAD,
    "CONCEPT MAPS AND CHAINS (diagram ops): a concept map that grows is a diagram kind hub, the big idea in the middle,",
    "   each connected idea revealed as it is taught, its edges labelled with how they connect ([\"force\", \"pressure\",",
    "   \"per unit area\"]); at a chapter's end it is the one-screen summary. A cause-and-effect chain is a diagram kind",
    "   flow whose edges say \"leads to\" or why ([\"deforestation\", \"soil erosion\", \"roots no longer hold it\"]).",
    "",
    "CAMERA: {\"op\":\"zoom\",\"diagram\":\"c1\",\"node\":\"R1\",\"scale\"?:2}  moves in on one part of the picture on the",
    "   stage (it grows about that part and comes to the middle); {\"op\":\"zoom\",\"diagram\":\"c1\"} moves back out.",
    "   For: a detail of a bigger figure (one resistor, one force on a body, one organelle).",
    "",
    ...(manimModel() ? MANIM_PLAN : MANIM_RULES),
    "",
    "DETAILED DIAGRAMS, for a detailed structure or real object",
    "that Manim would reduce to boxes and lines -- a cell and its organelles, an organ (the",
    "heart, a nephron, the eye, a neuron, a flower in section), a cross-section, real lab apparatus or a machine",
    "(a distillation set-up, an electric motor, a generator). It is made for you by the diagram",
    "model (an image model that draws exact, detailed textbook diagrams) in the lecture's style, from your words:",
    '  {"op":"draw","id":"heart","what":"A human heart in front section: right and left atria above the right and',
    "   left ventricles; the thick wall of the left ventricle; the vena cava into the right atrium, the pulmonary",
    "   artery out of the right ventricle, the aorta out of the left ventricle; the valves between atria and",
    '   ventricles.","labels":["right atrium","left atrium","right ventricle","left ventricle","aorta","vena cava"],',
    '   "caption"?}',
    "  what: everything on the picture, in English, precisely: each part, each arrow with where it starts and where",
    "  it points, numbers and units. The picture itself has no words.",
    "  labels: up to 6 parts to name, in the lecture's language, each a part really in the picture: the board writes",
    "  each beside the picture with a line to its part.",
    "  It is shown whole: no reveal or focus of its parts (say them in order; the labels are there). Never one for",
    "  what a diagram or a free-form manim drawing shows well: those are built in Manim.",
    "",
    "Map operations (only with a region):",
    '  {"op":"marker","place":"Jaipur" | "lonlat":[lon,lat],"label"?,"color"?,"side"?:"left|right|up|down","picture"?}',
    "     picture: what is there, shown above the label (PICTURES BESIDE WORDS); labels never cover one another.",
    "     A marker is for a POINT: a town, a city, a battlefield, a temple, a port.",
    '  {"op":"river","name":"Ganges","color"?}   a Natural Earth river by its English name',
    '  {"op":"state","name":"Normandy","label"?,"color"?,"opacity"?}   SHADE AN AREA, its name written on it: a state',
    "     or province, a country (\"England\", \"Spain\"), a region or a continent. A country or a region is the land",
    "     it covers, never a dot: a marker naming one big enough to see is shaded instead. Use a different colour",
    "     for each area that is compared (England and France at war: two colours).",
    '  {"op":"arrow","points":["Delhi","Agra",...],"color"?,"label"?}  a curved arrow: winds, migrations, routes;',
    "     label: what moves (\"spices\", \"the Aryans\", \"SW monsoon\"): it rides the arrow as it is drawn",
    '  {"op":"empire","name":"Mughal Empire","year":1600,"label"?,"color"?}  a state as it stood in that year, filled',
    "     with its border (historical maps, 2000 BC to 2010): kingdoms and empires, never today's borders for the past.",
    "     Use the state's usual English name (Maurya Empire, Delhi Sultanate, Ottoman Empire, Maratha Confederacy).",
    '  {"op":"relief","names"?:["Himalayas","Western Ghats"],"label"?:false}  the mountains and plateaus in view,',
    "     shaded with hill marks and named; names: only these. When the land's shape is the point (why rivers run",
    "     east, why the monsoon stops at the Ghats, a pass an army took).",
    '  {"op":"path","points":["Haridwar","Prayagraj"],"color"?}  a hand-drawn line: a ridge, a canal',
    "     points are place names (looked up) or [lon, lat] for a spot with no name (the open sea, a desert).",
    '  {"op":"journey","stops":["Ahmedabad","Surat",[72.8,20.89]],"labels"?:["Sabarmati","Surat","Dandi"],"color"?,',
    '   "pictures"?:[null,null,{"draw":"Gandhi picking up salt"}]}   (a stop\'s picture: generate, draw or figure)',
    "     a journey drawn as it happens over the line: a traveller moves stop to stop, the route behind it, each stop",
    "     named as it is reached (the Dandi March, Vasco da Gama's voyage, the Silk Road, the monsoon winds). A stop the",
    "     map may not know (a village) goes as [lon, lat] with its name in labels. A short route (one state) wants the",
    '     region narrowed to that state, {"state": "Gujarat", "country": "India"}, or its stops crowd into a dot.',
    '  {"op":"graticule","lat":23.44 | "lon":82.5,"label"?,"color"?}',
    '  {"op":"dim","opacity"?}                fade filled areas down before highlighting one',
    "Where something is grown, mined, made or lives: a marker at each place with a label (\"Sugarcane\"), then an",
    "illustration or photo of the thing itself on the stage.",
    "",
    "A panel holds a title and about five facts; start a new panel before it fills. ALWAYS NAME PLACES; never guess",
    "coordinates: the compiler looks names up in real gazetteers (towns, historic sites such as Lothal, Plassey,",
    "Dandi), and a guessed [lon, lat] is usually tens of kilometres off. A marker's place is its name in English",
    "(\"Prayagraj\", not \"प्रयागराज\"); put the name in the script's own language in label. A site the gazetteer",
    "does not know goes by the modern town it is in. Give lonlat only for a spot with no name (a point at sea).",
  ].join("\n");
}
