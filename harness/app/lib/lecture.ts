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
    beats: { say: string; pause?: number; do?: BeatOp[] }[];
  }[];
  recap?: [string, string][];
  credits?: string;
};

export type Compiled = { source: string | null; errors: string[]; warnings: string[]; minutes?: number };

/** A lecture runs this long unless the request names a length, or its content is long. */
export const DEFAULT_LECTURE_MINUTES = 10;
/** Words of source content a minute of detailed teaching covers: a chapter is taught, not read out. */
const SOURCE_WORDS_PER_MINUTE = 120;
/** Words of a book taught in a minute of lecture (explained, with examples and questions). */
const BOOK_WORDS_PER_MINUTE = 60;

/**
 * The length a request asks for: "a 12 minute lecture", "15-min", "१० मिनट". Without one, a long source (a
 * chapter) gets time to be taught in depth: about a minute for every 120 of its words, up to 30.
 */
export function targetMinutes(text: string, source = ""): number {
  const digits = text.replace(/[०-९]/g, (d) => String("०१२३४५६७८९".indexOf(d)));
  const found = digits.match(/(\d+(?:\.\d+)?)\s*-?\s*(?:min\b|mins\b|minutes?\b|मिनट)/i);
  if (found) return Math.min(90, Math.max(1, parseFloat(found[1])));
  const words = `${text}\n${source}`.split(/\s+/).filter(Boolean).length;
  if (source.trim()) {
    // A book is taught, not read: explained, with examples and questions it does not have, it runs about twice
    // as long as reading it out.
    return Math.min(60, Math.max(DEFAULT_LECTURE_MINUTES, Math.round(words / BOOK_WORDS_PER_MINUTE)));
  }
  return Math.min(30, Math.max(DEFAULT_LECTURE_MINUTES, Math.round(words / SOURCE_WORDS_PER_MINUTE)));
}

/**
 * How a lecture of this length teaches its content. The content decides the topics; the length decides the
 * depth: how many examples each statement gets and how many questions the class is asked. The same formula is
 * compile_lecture.teaching_plan (Forge uses that one).
 */
export type TeachingPlan = {
  minutes: number;
  topics: number;
  /** Examples for each important statement. */
  examples: number;
  /** Questions for the class per topic (0.5 = one every two topics). */
  questionsPerTopic: number;
  /** At least this many questions in the lecture, and beats giving an example. */
  minQuestions: number;
  minExamples: number;
  /** Long worked problems per topic (mathematics and the sciences), and at least this many in the lecture. */
  problemsPerTopic: number;
  minProblems: number;
};

export function teachingPlan(minutes: number, sourceWords = 0): TeachingPlan {
  // A source's topics are its own (about one every 350 words); a bare topic is split by the time there is.
  const topics = sourceWords > 400
    ? Math.min(15, Math.max(2, Math.round(sourceWords / 350)))
    : Math.min(12, Math.max(2, Math.round(minutes / 3)));
  const perTopic = minutes / topics;
  const examples = perTopic < 1.5 ? 1 : perTopic < 3 ? 2 : perTopic < 5 ? 3 : 4;
  const questionsPerTopic = perTopic < 2 ? 0.5 : perTopic < 4 ? 1 : perTopic < 7 ? 2 : 3;
  return {
    minutes,
    topics,
    examples,
    questionsPerTopic,
    // A short video of a long chapter cannot ask a question every topic: at most one every 2 minutes.
    minQuestions: Math.min(Math.max(1, Math.round(topics * questionsPerTopic)), Math.max(1, Math.floor(minutes / 2))),
    // About two key statements a topic, each with its examples; half of them counted, as the check reads
    // only the words an example starts with ("for example", "imagine", "जैसे"). At most one every 50 seconds.
    minExamples: Math.min(Math.max(2, Math.round(topics * 2 * examples * 0.5)), Math.max(2, Math.round(minutes * 1.2))),
    // A long problem solved step by step takes about 2 minutes, and the theory before it as long: at most one
    // problem per 4 minutes of the lecture.
    problemsPerTopic: perTopic < 2 ? 1 : perTopic < 4 ? 2 : 3,
    minProblems: Math.min(topics * (perTopic < 2 ? 1 : perTopic < 4 ? 2 : 3), Math.max(1, Math.floor(minutes / 4))),
  };
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
    /** The teaching plan for the chosen length: fewer questions or examples than it asks for is an error. */
    plan?: TeachingPlan;
    /** Mathematics or a science: the plan's long problems are required too. */
    stem?: boolean;
    /** "hinglish": the compiler checks the narration's mix and that the screen stays English. */
    language?: string;
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
          // The book's diagrams are rebuilt in Manim (document.ts figurePrompt), not shown as pictures.
          ...(options.figures && Object.keys(options.figures).length ? { rebuild_figures: true } : {}),
          ...(options.genre ? { genre: options.genre } : {}),
          ...(options.sourceText ? { source_text: options.sourceText } : {}),
          ...(options.language ? { language: options.language } : {}),
        }
      : script;
  const args = [compiler, "-", "--json"];
  if (options.minMinutes) args.push("--min-minutes", String(options.minMinutes));
  if (options.plan) {
    args.push("--min-questions", String(options.plan.minQuestions), "--min-examples", String(options.plan.minExamples));
    if (options.stem) args.push("--min-problems", String(options.plan.minProblems));
  }
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

export const ILLUSTRATION_TOOL = {
  type: "function" as const,
  function: {
    name: "find_illustration",
    description:
      "Search educational illustrations and diagrams that explain a topic, from the sources that suit the subject (OpenStax textbook figures, NASA, The Met and Smithsonian museums, Wikimedia Commons, Openverse, and an AI illustration when nothing else fits; reusable licences only): \"water cycle\", \"leaf cross section\", \"food web forest\", \"layers of soil\". Describe the topic in English, even for a Hindi lecture. Returns titles to use in an illustration op, with what each shows.",
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
export async function findIllustration(queries: unknown, genre?: string): Promise<string> {
  const words = (Array.isArray(queries) ? queries : [queries]).map((q) => String(q).slice(0, 80)).filter(Boolean).slice(0, 6);
  if (!words.length) return "Give queries: a list of topics.";
  const args = [path.join(REPO, "harness", "lecture", "images.py"), "--illustrations", ...words];
  // The subject picks the sources: textbook figures for sciences, museums for history, NASA for earth and space.
  if (genre) args.push("--genre", genre);
  const { stdout, stderr } = await runPython(args);
  const found = scriptJson<Record<string, { id: string; title: string; description: string; license: string; source?: string }[]>>(stdout);
  if (!found) return `The illustration search failed: ${stderr.trim().split("\n").slice(-3).join(" ") || "no output"}`;
  return Object.entries(found)
    .map(([q, rows]) =>
      `${q}:\n` +
      (rows.length
        ? rows.map((r) => `  ${r.id} [${r.source ?? "commons"}] (${r.license}) ${(r.description || r.title).slice(0, 100)}`).join("\n")
        : "  nothing reusable found (or no internet here); try another description, a document figure, or a process/timeline"),
    )
    .join("\n");
}

export const DRAWING_TOOL = {
  type: "function" as const,
  function: {
    name: "find_drawing",
    description:
      "Find the drawing for a thing a diagram, define, compare or icon shows (\"cow\", \"neuron\", \"burette\", " +
      "\"volcano\"). Words in English, a thing or two words each. Returns, best first: science drawings from Bioicons " +
      "(cells, organs, lab apparatus, molecules, organisms: accurate, by scientists), and hand-drawn illustrations " +
      "from open libraries (coco:... CocoMaterial: animals, plants, buildings, people, food, school, tech; arcadia:... " +
      "organisms; clip:... OpenClipart, public-domain drawings of almost anything, Indian things too: a bullock " +
      "cart, a diya, a rangoli, a tabla). Put the id that shows the thing best as the op's entity. Prefer a Bioicons drawing for science " +
      "that must be right. Nothing fits: search a simpler or broader word (\"ox\" -> \"cow\", \"granary\" -> \"barn\").",
    parameters: {
      type: "object",
      properties: { queries: { type: "array", items: { type: "string" }, description: "Things in English, e.g. [\"cow\", \"wheat\"]" } },
      required: ["queries"],
      additionalProperties: false,
    },
  },
};

/** Drawings a model may choose from for each query (icons.py --drawings), one line each. */
export async function findDrawings(queries: unknown): Promise<string> {
  const words = (Array.isArray(queries) ? queries : [queries]).map((q) => String(q).slice(0, 60)).filter(Boolean).slice(0, 12);
  if (!words.length) return "Give queries: a list of things.";
  const { stdout, stderr } = await runPython([path.join(REPO, "harness", "lecture", "icons.py"), "--drawings", ...words]);
  const found = scriptJson<Record<string, { id: string; name: string }[]>>(stdout);
  if (!found) return `The drawing search failed: ${stderr.trim().split("\n").slice(-3).join(" ") || "no output"}`;
  return Object.entries(found)
    .map(([q, rows]) => `${q}: ` + (rows.length ? rows.map((r) => `${r.id} (${r.name})`).join(", ")
      : "no drawing; leave entity out (the label carries the node) or search a simpler word"))
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
      "checked (length, questions, examples, problems) and compiled. replace_from: n rewrites from chapter n on.",
    parameters: {
      type: "object",
      properties: {
        chapters: { type: "array", items: { type: "object" }, description: "The next chapters, in the script's chapter shape." },
        recap: { type: "array", description: "The recap, with the last part: [[head, body], ...]." },
        replace_from: { type: "integer", description: "Replace chapters from this number (1-based) on, instead of adding after the last." },
        done: { type: "boolean", description: "true when this is the last part." },
      },
      required: ["chapters", "done"],
      additionalProperties: false,
    },
  },
};

/** The system prompt for a lecture template. */
/**
 * The book figures a finished script neither rebuilt in Manim (an op with "from_figure") nor showed as a photograph
 * ({"op":"figure","photo":true}).
 */
export function unbuiltFigures(script: unknown, figures: Record<string, { caption: string }>): string[] {
  const done = new Set<string>();
  const chapters = ((script as { chapters?: { beats?: { do?: Record<string, unknown>[] }[] }[] })?.chapters ?? []);
  for (const chapter of chapters) {
    for (const beat of chapter.beats ?? []) {
      for (const op of beat.do ?? []) {
        if (op?.from_figure) done.add(String(op.from_figure));
        if (op?.op === "figure" && op.photo) done.add(String(op.id));
      }
    }
  }
  return Object.entries(figures)
    .filter(([id, f]) => !done.has(id) && !/\b(QR|bar ?code|logo|watermark)\b|क्यूआर/i.test(f.caption))
    .map(([id]) => id);
}

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
    "    and Latin letters as English, so Romanised Hindi sounds wrong. The compiler rejects it.",
    "  - Keep the technical terms in English (force, mass, velocity, acceleration, friction, momentum, equilibrium,",
    "    numerator, photosynthesis) as teachers say them; do not replace them with pure Hindi words (बल, वेग,",
    "    संवेग). You may say the book's Hindi word once: \"Force, जिसे Hindi में बल कहते हैं...\".",
    "  - Say numbers and units the way they are spoken in class, units in words: \"10 newton\", \"5 meter per second",
    "    square\", \"m g sin theta\".",
    "  - Easy, friendly language: short sentences, direct address (\"आप\", \"देखो\", \"समझो\"), a question to the class",
    "    now and then (\"सोचो, ऐसा क्यों होता है?\").",
    "  - EVERYTHING ON SCREEN IS IN ENGLISH: the title, chapter titles, panel headings, key points, define cards",
    "    (term and meaning), labels in sketches, diagrams and graphs, questions and their choices, problem text,",
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
    "    figure (a preset, a sketch, a graph, a diagram) and reveal its parts as you explain them.",
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

/** Reference parts no chapter says it teaches ("from_part"), for a script that follows a reference video. */
export function uncoveredParts(script: unknown, parts: number): number[] {
  const chapters = (script as { chapters?: { from_part?: unknown }[] })?.chapters ?? [];
  const covered = new Set<number>();
  for (const c of Array.isArray(chapters) ? chapters : []) {
    const from = c?.from_part;
    for (const n of Array.isArray(from) ? from : [from]) if (Number.isFinite(Number(n))) covered.add(Number(n));
  }
  return Array.from({ length: parts }, (_, i) => i + 1).filter((n) => !covered.has(n));
}

export function lecturePrompt(
  template: Template,
  minutes = DEFAULT_LECTURE_MINUTES,
  subject?: Subject,
  plan: TeachingPlan = teachingPlan(minutes),
): string {
  // At the teaching pace (a slightly slow voice, pauses after lines and paragraphs, time to think) a minute
  // holds about 110 words.
  const words = Math.round(minutes * 110);
  const beats = Math.round((minutes * 60) / 13);
  const examples = plan.examples === 1 ? "one clear example" : `${plan.examples} different examples`;
  const asking =
    plan.questionsPerTopic < 1
      ? "after every second topic"
      : plan.questionsPerTopic === 1
        ? "after each topic"
        : `${plan.questionsPerTopic} questions after each topic`;
  return [
    "You write narrated lectures that explain a topic simply, for a phone renderer, as a beat script that a compiler turns into Manim.",
    `The style is ${template.name} (engine style "${template.style}"). Do not choose colours outside it.`,
    minutes > PARTS_OVER_MINUTES
      ? "WRITE IT IN PARTS of about 5 minutes (2-3 chapters each), so no single reply is huge: first write_lecture with " +
        '{"script": {title, sub, region, intro, chapters: [the first chapters]}, "more": true}; then add_chapters ' +
        '{"chapters": [the next chapters], "done": false} for each next part; the last add_chapters has "done": true and ' +
        "the recap. Each part is checked when it arrives (fix and resend a part that returns errors); the length, " +
        "questions, examples and problems are checked over the whole lecture at the end. Then reply with one short sentence."
      : "Call write_lecture once with the whole script. If it returns errors, fix them and call again. Then reply with one short sentence.",
    "",
    ...(subject
      ? [
          `SUBJECT. This is a ${subject.label} lecture. ${subject.guidance}`,
          `The map is used ${subject.map} in ${subject.label.toLowerCase()} lectures. Favour: ${subject.kit.join(", ")}.`,
          "",
        ]
      : []),
    "TEACH IN DEPTH, LIKE A PATIENT TEACHER IN A CLASSROOM. You are teaching the topic to a 12-year-old, slowly and",
    "warmly, not reading the book aloud and not summarising it. The content (a chapter, notes) is where you start,",
    "not the limit: explain each topic and each important statement of it fully, and add what a student needs to",
    "understand it that the book leaves out (the why, the background, how it connects to what they know). For each",
    "statement from the content, take several beats:",
    "  1. say it simply, in everyday spoken words and short sentences (under about 20 words each);",
    "  2. explain every hard word in it first (biodiversity, inertia, ecosystem): what it means in plain words, with",
    "     a define card on the stage;",
    `  3. give ${examples.toUpperCase()} from a student's daily life for it, each in a beat of its own (\"For example, when you`,
    "     push a cycle...\", \"Imagine...\", \"जैसे...\"), and a comparison when it helps (a forest is like a big shared house);",
    "  4. say WHY it is so, or what would happen if it were not;",
    "  5. say the key idea again in other words (\"So, in short: ...\"). Repeating the most important sentence once",
    "     is good teaching, not padding.",
    "Talk naturally, as a person does: \"Now, here is something interesting.\", \"Let us think about this.\", \"Have",
    "you ever noticed...?\". Never copy a sentence of the source; the compiler rejects a script that reads the book",
    "word for word. Skip what is not content: QR codes, page furniture, exercise instructions.",
    "",
    `QUESTIONS FOR THE CLASS. Ask ${asking} (at least ${plan.minQuestions} in the lecture): stop and ask the class a`,
    "question on the stage, then answer it on the next beat and explain why:",
    '  {"say":"Let us check. Which of these is a force?","do":[{"op":"question","text":"Which of these is a force?",',
    '    "choices":["Kicking a ball","Sleeping","Thinking"],"answer":"A","think"?:5}]},',
    '  {"say":"The answer is A. Kicking a ball is a push, and a push is a force.","do":[{"op":"answer"}]}',
    "  choices: 2-4 short answers, answer: the right one's letter. Or an open question with no choices (\"Why does a",
    "  rolling ball stop?\"), its answer in words: \"answer\":\"Friction slows it down.\". The video leaves think",
    "  seconds (7 by default) of silence with a timer before the answer. Ask about understanding, not memory.",
    "  A question about a drawing (\"इस diagram में सोचो, कौन सा force लग रहा है?\") goes on the beat right after the",
    "  drawing, with NO new picture in that beat: the question then sits beside the drawing, which stays on the board",
    "  through the thinking time and the answer (reveal the answer's part of it on the answer beat).",
    "",
    `DEPTH FOR THIS LENGTH. The chosen length is ${minutes} minutes for about ${plan.topics} topics, about`,
    `${(minutes / plan.topics).toFixed(1)} minutes a topic. The topics come from the content and stay the same whatever the`,
    "length; the length decides how deep each goes: how many examples, how much explanation of the why and the",
    "background, how many questions. A longer lecture goes deeper into the same topics; it does not add unrelated ones.",
    "Whatever the length, EXPLAIN EVERYTHING IN DETAIL: never state a term, a fact, a name or a number without saying",
    "what it means and why it matters, as if the student has never heard of it. Prefer three short sentences that",
    "explain to one long one that assumes.",
    "",
    ...(subject && ["mathematics", "physics", "chemistry"].includes(subject.genre)
      ? [
          `THEORY, THEN PROBLEMS (${subject.label}). Teach each concept in two parts:`,
          "  1. THEORY: build it on the board a piece at a time. Draw the situation (a preset or a sketch) and reveal its",
          "     parts as you name them; graph how the quantities vary; derive the law with work, one step a beat, saying",
          "     why each step follows; define every symbol; give everyday examples.",
          `  2. PROBLEMS: then up to ${plan.problemsPerTopic === 1 ? "one long problem" : `${plan.problemsPerTopic} long problems`} on each main concept (at least ${plan.minProblems} in the`,
          "     lecture; a small topic may have none), each harder than the last, of the kind an exam asks and that",
          "     needs a long explanation. For each: the problem op",
          "     (the full statement, given, find, its labelled figure, think: 5); read it out; say what is asked and",
          "     which idea solves it; reveal the forces or quantities on the figure one by one; write the solution with",
          "     work over many beats (a step a beat: the equation, then what it means); check the units and whether the",
          "     answer is sensible; box the answer; then say what the problem taught. A problem takes 8-15 beats.",
          "  Use numbers that work out cleanly. Say every symbol in words in the narration (\"m g sine theta\").",
          "  No photos: every picture is drawn in Manim (a scientist the lecture names may have a photo).",
          "",
        ]
      : []),
    "PAUSES. The video pauses after every line and longer at the end of each paragraph by itself. After a line that",
    "needs a moment to sink in (a key definition, a surprising fact), add \"pause\": 1-3 (extra seconds).",
    "In a Hindi lecture use simple spoken Hindi (बोलचाल की हिंदी), not heavy Sanskritised words: say 'जंगल' and",
    "'जीव-जंतु' rather than 'वनस्पतिजात' and 'प्राणिजात'; when the book's term matters, say it once and explain it,",
    "and you may add the familiar English word in brackets.",
    "",
    "PICTURES WITH A PURPOSE, NOT BOXES OF WORDS. A built diagram, a map, the document's figures, or real pictures of",
    "people and places; never icons, never a random image. process and quote are boxes of words: use them rarely.",
    "find_illustration and find_image take English descriptions even for a Hindi lecture; captions in the lecture's",
    "language.",
    "",
    `LENGTH. The lecture must run about ${minutes} minutes: about ${words} words of narration in about ${beats} beats,`,
    `in ${Math.max(3, Math.min(12, Math.round(minutes / 2.5)))} or so chapters of 10-20 beats. The compiler measures the running time`,
    "and returns an error when the script is well short; then teach in more depth: more examples, more explanation of",
    "each statement, background beyond the content, another question. Never fill with empty words.",
    "",
    "A beat is one narration line (say) and the operations that go with it (do). One idea per beat, at most two caption lines",
    "(under about 180 characters, 15-30 words), at most four operations. Every number you state must be in the content you",
    "were given or be well established; say 'about' for rough figures.",
    "",
    "Script shape:",
    '{"title", "sub", "region": {"country": "India", "view": "ind"} | {"state": "Rajasthan", "country": "India"} | null,',
    ' "intro", "chapters": [{"title", "sub", "narration": "Chapter one. ...",',
    '   "beats": [{"say": "...", "paragraph"?: true, "about"?: "Chipko movement", "pause"?: 2, "do": [ops]}]}],',
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
    "THE STAGE (the board, or the left half beside a map). Plan the stage a",
    "PARAGRAPH at a time (3-5 beats that explain one idea), never a new picture every sentence. Mark the first beat of",
    "each paragraph with \"paragraph\": true and give it the paragraph's visual; the beats after it build on that",
    "visual (reveal the next part of a diagram, focus on a node, add a marker) or simply leave it up. A paragraph may",
    "have no picture at all when the words and the panel carry it. Choose each paragraph's visual like this:",
    "  WHERE something is (a place, a route, a spread across a region) -> the MAP (map operations below). A chapter",
    "  with no map operation has no map at all.",
    "  HOW something works or connects (a process, a food chain, causes and effects, parts of a whole) -> BUILD a",
    "  DIAGRAM whose nodes are drawings of the things (entity: an English word, tree, deer, factory, farmer, which is",
    "  drawn as an illustration; or an id chosen with find_drawing: a Bioicons science drawing, or a hand-drawn",
    "  library illustration, coco:..., arcadia:... or clip:...),",
    "  shown a node or two at a time across the paragraph's beats:",
    '  {"op":"diagram","id":"chain","kind":"flow"|"cycle"|"tree"|"hub"|"categories"|"steps","title"?,',
    '   "nodes":[{"id":"sun","label":"Sun","entity":"sun"},{"id":"plants","label":"पौधे","entity":"deciduous tree"}],',
    '   "edges"?:[["sun","plants","light"]],"show"?:["sun","plants"]}   flow = in order; cycle = round; tree = from the',
    "                                          first node down; hub = the first node in the middle. Labels in the lecture's",
    "                                          language, entities in English. 2-9 nodes.",
    "  The diagram is drawn on the board as a teacher draws: each drawing's outline, then its colours. Give an entity",
    "  only for a concrete thing that can be drawn (a cow, a factory, rain); an idea gets no entity, just its words.",
    "  CATEGORIES, KINDS, TYPES OR STEPS, which need only words -> a diagram of words:",
    '  {"op":"diagram","id":"forces","kind":"categories","title":"Types of forces","nodes":[',
    '   {"id":"all","label":"Forces"},{"id":"contact","label":"Contact forces","items":["Friction","Normal","Tension"]},',
    '   {"id":"field","label":"Non-contact forces","items":["Gravity","Magnetic","Electric"]}]}',
    "   categories = the first node (the whole) above its kinds, each a coloured card listing up to 5 items;",
    '   steps = numbered cards in order: {"op":"diagram","id":"fbd","kind":"steps","nodes":[{"id":"s1","label":"Pick',
    '   the body"},{"id":"s2","label":"Draw every force on it"},{"id":"s3","label":"Choose axes"}]}. Reveal kinds or',
    "   steps a beat at a time with show and reveal, as you talk about each.",
    '  {"op":"reveal","diagram":"chain","nodes":["deer"]}   the next nodes of that diagram, with their arrows',
    '  {"op":"focus","diagram":"chain","node":"plants"}     a ring around one node while you talk about it',
    "  A HARD WORD -> {\"op\":\"define\",\"term\":\"Biodiversity\",\"meaning\":\"<plain words>\",\"entity\"?:\"butterfly\"}",
    "  TWO OR THREE KINDS OF SOMETHING -> {\"op\":\"compare\",\"title\"?,\"columns\":[{\"title\":\"Reserved\",\"entity\"?:\"tree\",",
    '   "points":["up to 4 short lines"]},...]}',
    "  A QUESTION FOR THE CLASS -> question, then answer on the next beat (see QUESTIONS FOR THE CLASS).",
    "  PEOPLE, COMMUNITIES, MOVEMENTS AND HISTORIC PLACES (and only these) -> real pictures. Several at once for a",
    "  paragraph about several: {\"op\":\"gallery\",\"title\"?,\"items\":[{\"subject\":\"Sunderlal Bahuguna\",\"caption\":\"सुंदरलाल बहुगुणा\"},",
    '   {"subject":"Chipko movement","caption":"..."},{"figure":"fig3","caption":"..."}]}   2-4 items: subject = Wikipedia\'s',
    "   picture (English name), figure = one of the document's figures, image = a title from find_image.",
    '   One of them alone: {"op":"photo","subject":"Chipko movement","caption":"चिपको आंदोलन"}.',
    "  THE DOCUMENT'S OWN FIGURES come first whenever one shows what the paragraph explains:",
    '  {"op":"figure","id":"fig2","where":"stage"} (or put several in a gallery).',
    "  SCIENCE -> molecule, equation, graph, sketch and the physics presets (DRAWN IN MANIM, below); HISTORY ->",
    "  timeline (see below). Build a picture in Manim whenever it can be built; fetch an image only when it cannot.",
    "  A TEXTBOOK DIAGRAM you cannot build (the parts of a cell, a cross-section) -> find_illustration, then",
    '  {"op":"illustration","image":"<title it returned>" | "query":"leaf cross section","caption"?}.',
    "Other stage operations:",
    '  {"op":"molecule","name":"glucose" | "H2O" | SMILES,"label"?}   a structural formula, atoms in CPK colours',
    '  {"op":"equation","tex":"6CO_2 + 6H_2O -> C_6H_{12}O_6 + 6O_2","label"?}   a law or a reaction, large',
    '  {"op":"plot","expr":"x^2/2" | "exprs":["x^2","3*x"],"x":[0,6],"x_label"?,"y_label"?,"names"?,"label"?}   graphs of x',
    '  {"op":"process","steps":["Evaporation","Condensation","Rain"],"cycle"?:true,"title"?}   steps in boxes (prefer a diagram)',
    '  {"op":"timeline","events":[["1526","Panipat"],["1556","Akbar"]],"title"?}   an era across the stage',
    '  {"op":"quote","text":"...","who":"Akbar"}   a primary source, in its own words',
    "Give a beat about a person, movement or place \"about\":\"<English name>\" (a Hindi beat especially): a paragraph",
    "left without a visual then gets their pictures automatically. Do not invent a picture for every sentence.",
    "",
    "DRAWN IN MANIM: diagrams, graphs and worked solutions, labelled, revealed a part a beat as the narration names it.",
    "Each has an id; reveal and focus take it (\"diagram\": id, \"nodes\": [part ids]); \"show\" lists the parts drawn",
    "first (default: all). Labels may use Unicode or TeX-ish m_1, v^2, \\theta (shown as m₁, v², θ).",
    '  {"op":"incline","id":"ramp","angle":30,"friction":true,"components":true,"forces":["mg","N"],"applied"?:"up",',
    '   "labels"?:{"block":"5 kg"},"show":["ground","wedge","theta","block"]}   a block on a wedge. Parts: ground, wedge,',
    "   theta, block, mg, N, f (friction), F (applied), mg_sin, mg_cos (the weight's components).",
    '  {"op":"pulley","id":"p","kind":"atwood"|"table","friction"?,"accel"?,"forces"?:["T","W","N"]}  Parts: ceiling|table,',
    "   pulley, rope, m1, m2, T1, T2, W1, W2, N, f, a1, a2.",
    '  {"op":"piston","id":"g","heat"?:true}  a gas under a piston. Parts: cylinder, gas, piston, rod, F, P, Q.',
    '  {"op":"spring","id":"s"}  Parts: wall, ground, spring, block, F, x.   {"op":"pendulum","id":"pd","angle":25}',
    "   Parts: support, rest, string, theta, swing, bob, T, mg.   {\"op\":\"projectile\",\"id\":\"pr\",\"angle\":45} Parts:",
    "   ground, path, u, ux, uy, theta, top, H, R.   {\"op\":\"circuit\",\"id\":\"c\",\"kind\":\"series\"|\"parallel\",",
    '   "resistors":["R₁","R₂"]} Parts: battery, wire, R1, R2, R3, I.   {"op":"lever","id":"l","loads":["W₁","W₂"]}',
    '   Parts: ground, fulcrum, beam, L1, L2, d1, d2.   {"op":"lens","id":"ln"} Parts: axis, lens, F1, F2, object,',
    "   ray1, ray2, image.   Every preset takes \"labels\": {part: text} to rename a label (\"mg\": \"50 N\").",
    '  {"op":"sketch","id":"tri","items":[...]}   ANY OTHER DIAGRAM, from primitives in a 10 x 6 box (x right, y up):',
    '   {"id"?,"type":"line"|"arrow","from":[x,y],"to":[x,y],"label"?,"color"?,"dashed"?}  (arrows: forces, velocities)',
    '   {"type":"rect","at":[x,y],"w","h","angle"?,"fill"?,"label"?}  {"type":"circle","at","r","fill"?,"label"?}',
    '   {"type":"polygon","points":[[x,y],...],"fill"?,"label"?}  {"type":"spring","from","to"}  {"type":"ground","from","to"}',
    '   {"type":"angle","at":vertex,"from":[x,y],"to":[x,y],"label":"θ"}  {"type":"dim","from","to","label":"4 m"}',
    '   {"type":"dot","at","label"?}  {"type":"text","at","text"}  {"type":"curve","points":[...],"dashed"?,"sharp"?}',
    "   Give every part the narration will point at an id. Colours: palette names (ROSE for forces, GREEN for",
    "   velocities, GOLD for angles, RIVER/DUNE fills). A triangle with its sides and angles, a beaker, a ray",
    "   diagram, a cell: all sketches.",
    '  {"op":"graph","id":"vt","x":[0,5],"y"?:[0,20],"x_label":"t (s)","y_label":"v (m/s)","title"?,"show":["v"],',
    '   "items":[{"id":"v","kind":"curve","expr":"4*x","label":"v = 4t"},{"id":"p","kind":"point","at":[3,12],"label":"(3, 12)"},',
    '    {"id":"A","kind":"area","expr":"4*x","x":[0,3],"label":"distance"},{"id":"tg","kind":"tangent","expr":"x^2","at":2},',
    '    {"id":"r","kind":"vline","x":2,"label":"x = 2"},{"kind":"hline","y":10},{"kind":"segment","from":[0,0],"to":[3,12]},',
    '    {"kind":"data","points":[[1,2],[2,4.1]],"line":true},{"kind":"label","at":[4,5],"text":"..."}]}',
    "   expr: a function of x (x^2, sin(x), exp(-x/2), 4*x). Reveal items one by one. Prefer graph to plot.",
    '  {"op":"work","id":"w","title"?:"Along the slope","lines":["N = mg\\cos\\theta"],"box"?:true}   A WORKED SOLUTION:',
    "   the same id adds lines under the last ones, one or two per beat, each step said in the narration. Lines are",
    "   TeX (\\frac{a}{b}, v^2, \\sqrt{2gh}, \\text{m/s}); a line with words is shown as a sentence. box rings the",
    "   answer. With a diagram or graph on the stage, the working opens beside it (the picture moves left).",
    '  {"op":"problem","id":"p1","title":"Problem 1","text":"<the full question>","given":["m = 5 kg","\\theta = 30°"],',
    '   "find":"a","think"?:5,"figure":{"op":"incline","angle":30,"show":["ground","wedge","theta","block"]}}',
    "   A LONG QUESTION: its statement across the top, its figure (a preset, sketch or graph; reveal its parts with",
    '   diagram "p1_figure", or the figure\'s own id) on the left, and its solution: {"op":"work","id":"p1",...}',
    "   on the right. think leaves seconds of silence for the class to try it first.",
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
