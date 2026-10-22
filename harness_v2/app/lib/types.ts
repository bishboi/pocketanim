/**
 * What a run is, as the server keeps it and the page shows it. Plain data (no Node imports): the page reads it.
 */

import type { Part } from "./prompts/parts";
import type { Block } from "./source/blocks";
import type { Goal } from "./plan";
import type { TriageKind } from "./triage-kinds";

/** What code found when it read a model's reply: passed, mended by code, failed, or only noted. */
export type Check = { name: string; result: "pass" | "fixed" | "fail" | "info"; detail: string };

export type Call = {
  id: string;
  /** Which step of the flow made it: "plan", "lecture", "patch". */
  step: string;
  label: string;
  lecture?: number;
  /** The book's block the call is about (a figure described or triaged). */
  block?: string;
  model: string;
  effort?: string;
  status: "running" | "done" | "failed";
  started: number;
  ended?: number;
  attempts: { started: number; ended: number; error?: string }[];
  prompt: { system: Part[]; user: Part[] };
  tool?: unknown;
  /** The tool's arguments the reply gave (parsed), or the reply's text when it gave none. */
  output?: unknown;
  text?: string;
  usage?: { input: number; output: number; cached?: number; reasoning?: number };
  cost: number;
  /** "openrouter" for a real call, "fixture" for the offline stand-in (no key). */
  /** "openai": OpenAI's own API, for an OpenAI model when OPENAI_API_KEY is set (the video agent). */
  provider: "openrouter" | "fixture" | "openai";
  error?: string;
  checks: Check[];
  /** Pictures sent with the prompt (a figure to describe), as URLs the page can show. */
  images?: string[];
  /** "decisions": a decision model (decisions.ts), its questions in `tool`; else a chat call. */
  api?: "chat" | "decisions" | "image" | "voice";
  /** The request as sent (images cut to a placeholder), when it is not a chat request. */
  request?: unknown;
};

/** "plan": runs made before lectures were written as scripts in one call (their planner step). */
export type StepKey = "read" | "figures" | "plan" | "write";

export type Step = { key: StepKey; label: string; status: "waiting" | "running" | "done" | "failed"; started?: number;
  ended?: number; summary?: string };

/** A lecture of the series: its part of the book (block ids) and goals from the plan, and its transcript. */
export type LectureState = {
  n: number;
  title: string;
  why: string;
  blocks: string[];
  /** Learning goals: runs made before the lectures were written as scripts (new runs have none). */
  goals: Goal[];
  status: "waiting" | "writing" | "written" | "failed";
  /** The final text (cleaned, repeats out, patches in). */
  text?: string;
  /** Each goal taught, with the sentence numbers in the final text that teach it. */
  goalLines?: Record<string, number[]>;
  /** The blocks the writer (or a patch) says it taught; the rest of the lecture's blocks are missing. */
  blocksTaught?: string[];
  /** Sentences written in by a patch, with what they cover. */
  patched?: { covers: string[]; lines: number[] }[];
  dropped?: string[];
  calls: string[];
};

export type Options = {
  /** How long a lecture is meant to be: told to the planner, as context. */
  lectureMinutes: number;
  language: "auto" | "english" | "hindi" | "hinglish";
  subject: string;
  plannerModel: string;
  writerModel: string;
  /** Reads the book's figures (a model that reads images). */
  figureModel: string;
  /** The models of the steps after the transcript (lib/models.ts), as the run was started with them. */
  triageModel?: string;
  triageChatModel?: string;
  scriptModel?: string;
  scenesModel?: string;
  imageModel?: string;
  svgModel?: string;
  manimModel?: string;
  mapModel?: string;
  videoModel?: string;
  effort: "low" | "medium" | "high" | "off";
  /** The writer's reasoning (it writes each lecture as its script: longer thinking): "high" by default. */
  writerEffort?: "low" | "medium" | "high" | "off";
};

export type Run = {
  id: string;
  documentId: string;
  documentName: string;
  created: number;
  ended?: number;
  /** "interrupted": the server stopped while it ran (it can be continued); "stopped": stopped from the page. */
  status: "running" | "done" | "failed" | "stopped" | "interrupted";
  error?: string;
  options: Options;
  steps: Step[];
  /** The book as blocks (blocks.ts): what the plan and the lectures name. */
  blocks: Block[];
  skipped: { block: string; reason: string }[];
  lectures: LectureState[];
  goalStatus: Record<string, GoalStatus>;
  calls: Call[];
  log: { t: number; text: string }[];
  /** The figure triage (triage.ts): how each of the book's figures is to be shown. Runs apart from the transcript. */
  triage?: Triage;
  /** The generation (generate.ts): the figures triaged as redraws, redrawn by the image model. */
  generation?: Generation;
  /** The script (script.ts): each lecture's chapters and beats, every transcript sentence in one beat. */
  script?: ScriptState;
  /** The scenes (scenes.ts): each beat's visuals as the engine's operations, compiled, and rendered beat by beat. */
  scenes?: ScenesState;
  /** The voice: each chapter with scenes spoken, its animations timed to the words, and played with its narration. */
  voice?: VoiceState;
  /** The Lab tab: beat scripts written or picked to try an animation with the voice, apart from the lectures. */
  lab?: LabState;
  /** The video (lib/video.ts, the default flow): each chapter spoken from its transcript, its words aligned, and its
   * video built by the video agent in free Manim, played as the phone plays it. */
  video?: VideoState;
  /** Set on a run file written by an earlier version of v2 (lib/store.ts normalize): why it cannot be continued. */
  legacy?: string;
  /** Where it was imported from, when it came from an exported transcript. */
  imported?: { file: string; at: number };
};

/** How one figure is to be shown, as the triage decided it (and the user, when they chose another). */
export type FigureTriage = {
  block: string;
  status: "waiting" | "running" | "done" | "failed";
  kind?: TriageKind;
  /** The model's instruction for whoever builds or redraws it. */
  how?: string;
  /** Why this way. */
  reason?: string;
  /** Labels, values and parts that must stay exactly as in the book. */
  keep?: string[];
  /** The way the user chose instead of the model's. */
  override?: TriageKind;
  /** Who decided: a decision model (a choice with probabilities, no words) or a chat model (with its how and why). */
  engine?: TriageEngine;
  /** The decision model's probability for each way offered, and its confidence in the one chosen. */
  probabilities?: Record<string, number>;
  confidence?: number;
  /** Its confidence was under the run's threshold: to be looked at (or asked of the chat model). */
  unsure?: boolean;
  /** A rule code applied to the model's choice (a near-tie of Map and a redraw redrawn), said in words. */
  rule?: string;
  error?: string;
  calls: string[];
  at?: number;
};

export type TriageEngine = "decision" | "chat";

/** One beat: the transcript sentences said on it (by number, 1-based) and what is on screen while they are. */
/** One beat: the sentences said on it (by number in the lecture's text, 1-based), what is on screen while they are,
 * and the book's figures shown on it (any figure may be on several beats). `figure`: one figure, as older scripts had. */
export type Beat = { n: number; lines: number[]; show: string; figures?: string[]; figure?: string };

/** One chapter: a topic, with its title card and one stage (a map, or a board). */
/** `content`: the book's blocks the chapter teaches from (Datalab ids); chapters may share them. */
export type Chapter = { n: number; title: string; narration: string; map: boolean; content?: string[]; beats: Beat[] };

export type LectureScript = {
  lecture: number;
  status: "waiting" | "running" | "done" | "failed";
  chapters: Chapter[];
  /** How many sentences the transcript had when it was scripted. */
  lines?: number;
  checks?: Check[];
  error?: string;
  calls: string[];
  at?: number;
};

export type ScriptState = {
  status: "idle" | "running" | "done" | "failed" | "stopped" | "interrupted";
  model: string;
  started?: number;
  ended?: number;
  rounds: number;
  lectures: Record<string, LectureScript>;
  error?: string;
};

/** One figure's generated image: the prompt it was sent and the image made. */
export type FigureGeneration = {
  block: string;
  status: "waiting" | "running" | "done" | "failed";
  /** The way it was generated as (exact, styled). */
  kind?: TriageKind;
  /** The prompt as sent (its parts are on its call). */
  prompt?: string;
  /** How it was asked in the end: full, gentle (the full prompt blocked by moderation), blind (no reference image). */
  level?: "full" | "gentle" | "blind";
  /** An SVG's parts (its <g id>s), and the rules it still breaks when no try kept them all. */
  svgParts?: string[];
  svgProblems?: string[];
  /** A Manim figure's code (the body of construct()) and its video (the last frame is `file`). */
  code?: string;
  video?: string;
  /** A map's script, as the engine was given it. */
  mapScript?: Record<string, unknown>;
  /** Where the image is kept, and its URL for the page. */
  file?: string;
  url?: string;
  error?: string;
  calls: string[];
  at?: number;
};

export type Generation = {
  status: "idle" | "running" | "done" | "failed" | "stopped" | "interrupted";
  /** The image model (redraws). */
  model: string;
  /** The SVG model (reads the figure, writes the SVG, in one call). */
  svgModel?: string;
  /** The Manim model (reads the figure, writes its Manim code, in one call). */
  manimModel?: string;
  /** The map model (reads the book's map, writes its map script, in one call). */
  mapModel?: string;
  started?: number;
  ended?: number;
  rounds: number;
  figures: Record<string, FigureGeneration>;
  error?: string;
};

export type Triage = {
  status: "idle" | "running" | "done" | "failed" | "stopped" | "interrupted";
  /** The ways the model may choose from (the user's choice). */
  kinds: TriageKind[];
  /** Who decides: a decision model (Jev: a typed choice with probabilities), or a chat model that reads images. */
  engine?: TriageEngine;
  /** The decision model. */
  model: string;
  /** The chat model (reads images; writes how and why). */
  chatModel?: string;
  /** Under this confidence a decision model's choice is marked unsure (0-1). */
  threshold?: number;
  started?: number;
  ended?: number;
  /** How many times it was run (reset or not). */
  rounds: number;
  figures: Record<string, FigureTriage>;
  error?: string;
};

export type GoalStatus = "waiting" | "taught" | "patched" | "missing";

export type DocumentInfo = {
  id: string;
  name: string;
  pages: number;
  words: number;
  source: string;
  created: number;
};

/** A render of part of a lecture's scenes (silent, low quality, for a look): one beat in context, or a chapter. */
export type SceneRender = {
  status: "running" | "done" | "failed";
  /** The look it was rendered in. */
  style: string;
  art: string;
  /** URLs (older renders): the last frame, the beat's own clip, the whole video rendered. */
  still?: string;
  clip?: string;
  video?: string;
  /** For v1's web player: the scene's geometry (scene_ir.json) and its pictures (a base the asset name goes on). */
  ir?: string;
  assets?: string;
  fps?: number;
  frames?: number;
  /** A beat's render: the frames that are the beat [first, last] (the chapter before it is recorded too). */
  range?: [number, number];
  /** Rendered with the chapter's voice (spoken first, motion engine): the narration track the player plays as its clock. */
  audio?: string;
  /** What the exporter could not carry into the program (it plays without it). */
  blockers?: string[];
  /** AI pictures the image model could not make for it: left out of what plays. */
  missing?: MissingPicture[];
  images?: ImageReport;
  /** The AI pictures in it (the rendered beat's, or the chapter's), made or not. */
  pictures?: BeatPicture[];
  /** What the engine's check found on screen, and mended by itself. */
  issues?: string[];
  fixed?: string[];
  error?: string;
  seconds?: number;
  started?: number;
  at?: number;
};

/** A chapter's render: the video, and each beat in it (its last frame, its clip, where it is in the video). */
export type SceneChapterRender = SceneRender & { beats?: { n: number; still?: string; clip?: string; start: number; end: number; from?: number; to?: number;
  issues?: string[]; fixed?: string[] }[] };

/** One beat's visuals: the engine's operations, and what was made of them. */
export type SceneBeat = {
  n: number;
  status: "waiting" | "running" | "done" | "failed";
  ops: Record<string, unknown>[];
  /** The rest of the beat as v1's beat script has it: a paragraph's first beat, extra seconds after the line, whom
   * or what it is about (its English name). */
  paragraph?: boolean;
  pause?: number;
  about?: string;
  /** What code took out of the model's answer (a kind switched off, an op the engine does not know). */
  dropped?: string[];
  /** The compiler's errors on this beat (it does not compile), and its notes (warnings, what it mended). */
  errors?: string[];
  /** AI pictures of this beat the image model could not make: left out of the scene. */
  missing?: MissingPicture[];
  /** Every AI picture of this beat (a gallery's, the stage's, a node's...), made or not, from the last compile. */
  pictures?: BeatPicture[];
  notes?: string[];
  /** Its own visual kinds, when they differ from the run's. */
  kinds?: string[];
  /** Written (or changed) by hand. */
  edited?: boolean;
  render?: SceneRender;
  /** The Manim agent's work on this beat (manim-agent.ts), when it built its Manim figure. */
  agent?: ManimAgentState;
  calls: string[];
};

/** A picture the Manim agent made for its figure: its name in the code (image("name")), what was asked, the file. */
export type AgentImage = { name: string; what: string; kind: "cutout" | "scene"; beat: number; url?: string; file?: string; call?: string;
  status: "done" | "failed"; error?: string; cost: number; at: number };

/** One thing the agent did: a turn of the model (its words), an image made, a preview rendered, the end. */
export type AgentStep = {
  turn: number;
  /** "preview" (a render): older runs only; the agent now checks its code and renders nothing. */
  kind: "think" | "image" | "check" | "preview" | "finish" | "error";
  call?: string;
  text?: string;
  args?: Record<string, unknown>;
  /** An image's URL; a preview's last frame and video. */
  image?: string;
  still?: string;
  video?: string;
  /** A preview for v1's web player: its geometry, its pictures, the beat's frames. */
  ir?: string;
  assets?: string;
  range?: [number, number];
  errors?: string[];
  seconds?: number;
  at: number;
};

export type ManimAgentState = {
  status: "running" | "done" | "failed" | "stopped";
  model: string;
  imageModel: string;
  /** The figure's id (beats with the same id are one figure, built in order). */
  id: string;
  /** What it was asked to do (the scene writer's plan, the user's words). */
  plan?: string;
  instruction?: string;
  steps: AgentStep[];
  images: string[];
  turns: number;
  code?: string;
  area?: string;
  summary?: string;
  error?: string;
  cost: number;
  started: number;
  ended?: number;
};

/** A picture the engine asked the image model for and could not get, so it was left out of the scene (a gallery with
 * none of its pictures is left out whole): what was asked, the image model's error, the beat it was for. */
export type MissingPicture = { what: string; error?: string; beat?: number };

/** One AI picture of a beat, as the engine's compile got it: made now, made before (the cache), or not made. */
export type PictureDecision = {
  action: "reuse" | "match" | "fresh";
  choice?: string | null;
  confidence?: number | null;
  probabilities?: Record<string, number>;
  /** Below the threshold: a reuse drawn anew to match instead, a match drawn fresh. */
  unsure?: boolean;
  /** The pictures it was asked about: their words and prompt (and the chosen one's file, to show). */
  candidates: { key: string; what: string; prompt?: string; reusable?: boolean }[];
  picked?: string | null;
  pickedUrl?: string;
  model?: string;
  call?: string;
  /** Asked now (a call), or the answer kept from a compile before. */
  askedNow?: boolean;
  error?: string;
};

export type BeatPicture = {
  what: string;
  caption?: string;
  /** Where it is: "in a gallery", "shown on the stage", "beside a diagram label"... */
  role?: string;
  status: "made" | "cached" | "failed";
  url?: string;
  /** The prompt the image model was sent (the engine's, with what the picture is for), its model and cost. */
  prompt?: string;
  model?: string;
  usd?: number;
  error?: string;
  /** Whether a picture made before was used for it, as the decision model (Jev) decided: shown again (reuse), drawn
   * anew to match it (match), or none (fresh); with its probabilities, the picture it chose, and its call. */
  decision?: PictureDecision;
  beat?: number;
};

/** What the engine's image model did in a compile: pictures asked for, made now, found made already. */
export type ImageReport = { model?: string; asked: number; made: number; cached: number; failed: number };

export type SceneCompile = {
  status: "running" | "done" | "failed";
  errors: string[];
  warnings: string[];
  /** AI pictures it could not get (left out of the scene), and the image model's work. */
  missing?: MissingPicture[];
  images?: ImageReport;
  /** Pictures the image model made for it, and what each cost. */
  pictures?: { prompt: string; model?: string; usd?: number }[];
  minutes?: number;
  seconds?: number;
  at?: number;
};

export type SceneLecture = {
  lecture: number;
  status: "waiting" | "running" | "done" | "failed";
  /** What it is doing now, in words ("chapter 2 of 4", "compiling", "mending 3 beats"). */
  doing?: string;
  /** The map region of a lecture built before chapters had their own (used by a chapter without one). */
  region?: Record<string, unknown> | null;
  /** Each chapter's own map region (by chapter number): chapters are built, compiled and mended apart. */
  regions?: Record<string, Record<string, unknown> | null>;
  /** The lecture's emblem (one object for the topic) and its subject (the engine's genre.py), as v1 has them. */
  emblem?: string;
  subject?: { genre: string; label: string; guidance?: string; map?: string; kit?: string[] };
  beats: Record<string, SceneBeat>;
  /** The lecture's compile: its chapters' compiles (each compiled apart) put together. */
  compile?: SceneCompile;
  /** Each chapter's own compile, by chapter number. */
  compiles?: Record<string, SceneCompile>;
  chapters?: Record<string, SceneChapterRender>;
  /** A chapter's own visual kinds (by chapter number), when they differ from the run's; a beat's own win over them. */
  chapterKinds?: Record<string, string[]>;
  /** When the script it was built from was made (a newer script: rebuild). */
  scriptAt?: number;
  error?: string;
  calls: string[];
  at?: number;
};

export type ScenesState = {
  status: "idle" | "running" | "done" | "failed" | "stopped" | "interrupted";
  model: string;
  look: { style: string; art: string };
  /** The visual kinds switched on (visual-kinds.ts). */
  kinds: string[];
  rounds: number;
  lectures: Record<string, SceneLecture>;
  /** Renders going now. */
  renders?: number;
  /** Manim figures written by the Manim agent (with images, previews), or by the scene writer in its answer. */
  manimAgent?: boolean;
  manimModel?: string;
  /** Whether a picture made before is used again (or matched) as a decision model decides (on by default), or by
   * matching words; and that model. */
  reuseJudge?: boolean;
  reuseModel?: string;
  /** How busy the visuals are: operations a beat (left out: no limit, the default; v1 said four), and whether they
   * change a paragraph at a time (v1) or on every beat. */
  maxOps?: number;
  visualChange?: "paragraph" | "beat";
  /** The images the Manim agent made, by lecture, by name. */
  agentImages?: Record<string, Record<string, AgentImage>>;
  /** "motion": the lectures are built, compiled, rendered and spoken on the motion engine (beta:
   * engine/MOTION_ENGINE.md); left out, the current engine. */
  engine?: "motion";
  /** The motion engine's settings: its look (paper, newsroom, chalk, data, studio, sketch, archive, neon, brush, collage, textbook, chalkcolour, isometric, drafting; left out: the style's own
   * motion), energy, transition, idle motion and the timeline's style. */
  motion?: { look?: string; energy?: string; transition?: string; idle?: string; timeline?: string };
  /** On the motion engine, each chapter is spoken and its words aligned before its scenes are written, and the scene
   * writer is given each beat's length, its words by number with their times, and the quiet after it (on unless
   * false). */
  voiceFirst?: boolean;
  error?: string;
  started?: number;
  ended?: number;
};

/** The voice engine and speaker the chapters are spoken with (the engine's tts.py). */
export type VoiceSettings = {
  /** gemini (GEMINI_API_KEY), chirp (Google Cloud), eleven (ElevenLabs, times its own words), espeak (offline, free). */
  engine: "gemini" | "chirp" | "eleven" | "espeak";
  /** The speaker (Gemini: Achird, Kore, Charon...); empty: the engine's default for the look. */
  voice?: string;
  /** The teaching pace (pocket_lecture.PACES): the holds after each line and paragraph. */
  pace?: "natural" | "relaxed" | "slow";
  /** The model that times the animations to the words (the timing role). */
  timingModel?: string;
};

/** A line the chapter says, as spoken: its audio, length, cost and when each word is said. */
export type VoiceLine = {
  beat?: number;
  text: string;
  /** What the voice was given (numbers and symbols said as words). */
  spoken?: string;
  /** The voice director's marking of it for delivery (Gemini, ElevenLabs), when there is one. */
  delivery?: string;
  seconds?: number;
  url?: string;
  usd?: number | null;
  words?: { w: string; start: number; end: number }[];
  /** Where the word times came from: the voice, the aligner here (Whisper), an estimate, or why there are none. */
  wordsFrom?: string;
};

/** A beat's animations timed to its words (align_cues): each one's start (and length), or why it was not timed. */
export type VoiceCue = { beat?: number; kind: "beat" | "free"; text: string; parts: string[]; seconds?: number;
  cues?: (number | [number, number])[]; why?: string };

export type ChapterVoice = {
  status: "running" | "done" | "failed";
  /** What it is doing: compiling, speaking, aligning words, timing, rendering. */
  phase?: string;
  /** The voice it was spoken in (engine:speaker). */
  mode?: string;
  engine?: string;
  /** The look it was rendered in. */
  style?: string;
  art?: string;
  lines?: VoiceLine[];
  cues?: VoiceCue[];
  /** Which aligner timed the words (or why none could). */
  aligner?: string;
  /** What it cost: the lines spoken now, the chapter's whole voice, the voice director, the timing model. */
  cost?: { spoken: number; voice: number; director: number; timing: number; lines: number; newLines: number };
  calls?: string[];
  /** Played with its narration in v1's web player: the geometry, the pictures, the voice track. */
  ir?: string;
  assets?: string;
  audio?: string;
  fps?: number;
  frames?: number;
  /** Each beat in the narrated chapter: where it starts and ends (seconds, frames). */
  beats?: { n: number; start: number; end: number; from: number; to: number }[];
  blockers?: string[];
  /** The AI pictures its compile showed, each as the image model made it (a flow drawn as one picture whole, with
   * where each of its steps is), with what it shows, how it is used, and the prompt it was sent. */
  pictures?: { url: string; what: string; role?: string; beat?: number; prompt?: string; model?: string;
    parts?: [string, number?, number?, number?, number?][] }[];
  /** A trial: the beat script it was made from (edited by hand), and what applying it to the scenes did. */
  edited?: ChapterScript;
  applied?: { at: number; beats: number; notes: string[] };
  /** The scenes it was made from (a key of their visuals and words): other scenes now mean the voice is behind them. */
  scenesKey?: string;
  error?: string;
  started?: number;
  seconds?: number;
  at?: number;
};

export type VoiceState = {
  settings: VoiceSettings;
  /** By lecture, by chapter. */
  lectures: Record<string, Record<string, ChapterVoice>>;
  /** A chapter's beat script edited by hand on the Voice tab and tried (spoken and played) apart from its real voice. */
  trials?: Record<string, Record<string, ChapterVoice>>;
};

/** One experiment on the Lab tab: a chapter's beat script, its name, and what speaking and playing it last gave. */
export type LabItem = {
  id: string;
  name: string;
  /** The preset it started from (lib/lab-presets.ts), if any. */
  from?: string;
  /** The lecture whose figures and look it is compiled with. */
  lecture?: number;
  script: ChapterScript;
  result?: ChapterVoice;
  at: number;
};

export type LabState = { items: LabItem[] };

/** A chapter's beat script as the Voice tab edits it: what the compiler is given for it (its figures added). */
export type ChapterScript = {
  /** "motion": drawn by the motion engine (beta: engine/MOTION_ENGINE.md), in `look`, every template animated. */
  engine?: "motion";
  /** The motion engine's: its look (one of MOTION_LOOKS), energy, transition, idle, timeline style. */
  look?: string;
  energy?: string;
  transition?: string;
  idle?: string;
  timeline?: string;
  style?: string;
  art?: string;
  region?: Record<string, unknown> | null;
  emblem?: string | null;
  genre?: string | null;
  chapter: { title: string; narration?: string; map?: boolean;
    beats: { beat?: number; say: string; do: Record<string, unknown>[]; paragraph?: boolean; pause?: number; about?: string }[] };
};

/** The video step's settings (the voice's own are run.voice.settings). */
export type VideoSettings = {
  /** The video agent's model (the video role) and the image model it draws pictures with. */
  model?: string;
  imageModel?: string;
  /** Most turns a chapter's agent may take. */
  turns?: number;
  /** How hard the agent's model reasons each turn (high by default: it plans and writes a whole chapter's motion). A
   * level the model does not take falls back to high. */
  effort?: "low" | "medium" | "high" | "xhigh" | "max" | "off";
  /** lean: the agent only writes its scene (each write rendered and checked on the phone) and looks at frames; agent:
   * every tool (files, shell, renders of sections, kit previews, pictures). */
  mode?: "lean" | "agent";
  /** The look to build in: a screenshot of how the visuals look (a file), and words about it. */
  style?: string;
  styleNote?: string;
};

/** One thing the video agent did: its words, a tool it called and what came back (and any pictures it was shown). */
export type VideoStep = {
  turn: number;
  kind: "think" | "tool" | "finish" | "error";
  tool?: string;
  call?: string;
  text?: string;
  /** The model's reasoning on the turn, as the provider gave it (on the turn's "think" step). */
  reasoning?: string;
  args?: Record<string, unknown>;
  /** What the tool answered, as the agent read it. */
  result?: string;
  ok?: boolean;
  /** Pictures shown to the agent (frames, a sheet, a picture it made), as URLs. */
  images?: string[];
  video?: string;
  seconds?: number;
  /** How long the tool took (ms); a shell command's exit code; the file version a write or edit made. */
  ms?: number;
  exit?: number | null;
  version?: number;
  /** A turn's model call: its tokens, cost and how long the model took (on the turn's first step). */
  tokens?: { input: number; output: number; reasoning?: number; cached?: number };
  cost?: number;
  /** Where the turn ran (openai: OpenAI's own API; openrouter; fixture) and the reasoning level it ran at. */
  provider?: string;
  effort?: string;
  at: number;
};

/** A file as the agent left it after one of its writes or edits (kept under history/ in its workspace). */
export type AgentVersion = { v: number; path: string; turn: number; file: string; lines: number; at: number };

/** A chapter's narration: spoken from its transcript lines, every word aligned (engine/tools/chapter_voice.py). */
export type ChapterNarration = {
  status: "running" | "done" | "failed";
  at: number;
  ended?: number;
  engine?: string;
  seconds?: number;
  /** Where the word times came from: the voice, Whisper, an estimate, or a mix. */
  source?: string;
  lines?: number;
  spoken?: number;
  cost?: number;
  track?: string;
  error?: string;
  progress?: { phase: string; done: number; total: number };
};

/** The video agent's run on a chapter. */
export type ChapterAgent = {
  status: "running" | "done" | "failed" | "stopped";
  model: string;
  /** The reasoning level asked for, and the one it ran at (lower when the model did not take the one asked). */
  effort?: string;
  effortUsed?: string;
  /** Where its turns run: openai (OpenAI's own API), openrouter, or fixture (no key). */
  provider?: string;
  imageModel: string;
  note?: string;
  started: number;
  ended?: number;
  turns: number;
  cost: number;
  steps: VideoStep[];
  summary?: string;
  error?: string;
  /** The turn the model is answering now, as it streams: its words, its reasoning, the tools it is calling. */
  live?: { turn: number; started: number; text: string; reasoning: string; tools: string[] };
  /** Every version of every file it wrote, in order. */
  versions?: AgentVersion[];
  /** The whole conversation, as sent and answered, a line a message (agent-log.jsonl in its workspace). */
  log?: string;
};

/** The chapter's video as the phone plays it: the program, its geometry for the web player, its narration. */
export type ChapterBuild = {
  at: number;
  ir: string;
  assets: string;
  audio?: string;
  /** The Manim video it was checked against. */
  video?: string;
  seconds: number;
  bytes: number;
  tier: number;
  blockers: string[];
  /** The phone's frames against Manim's: how many compared and those that differ. */
  check?: { ok: boolean | null; frames: number; differ: { t: number; mean: number; differ: number }[] };
};

export type ChapterVideo = { lecture: number; chapter: number; narration?: ChapterNarration; agent?: ChapterAgent; build?: ChapterBuild };

export type VideoState = { settings: VideoSettings; chapters: Record<string, ChapterVideo> };
