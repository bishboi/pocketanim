/**
 * Which harness is running: the app's version, and the git commit and branch
 * it was started from, so a screenshot says exactly what produced a video.
 */

import { execFileSync, spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import pkg from "../package.json";
import { REPO, python } from "./pocketanim";

export type VersionInfo = { version: string; commit: string | null; branch: string | null; dirty: boolean; date: string | null };

function git(args: string[]): string | null {
  try {
    return execFileSync("git", args, { cwd: REPO, encoding: "utf8", timeout: 5000 }).trim() || null;
  } catch {
    return null;
  }
}

/** Read on each call: a `git pull` under a running dev server shows up without a restart. */
export function versionInfo(): VersionInfo {
  return {
    version: pkg.version,
    commit: git(["rev-parse", "--short", "HEAD"]),
    branch: git(["rev-parse", "--abbrev-ref", "HEAD"]),
    dirty: Boolean(git(["status", "--porcelain", "--untracked-files=no"])),
    date: git(["log", "-1", "--format=%cs"]),
  };
}


/** Google's Chirp 3 HD can speak here: an API key, or service-account credentials (harness/lecture/chirp.py). */
export function chirpConfigured(): boolean {
  // OAuth first, as harness/lecture/chirp.py: a service account, or the login `gcloud auth application-default
  // login` writes. Some projects refuse API keys for Text-to-Speech.
  const file = process.env.GOOGLE_APPLICATION_CREDENTIALS;
  if (file) return existsSync(file) || !!(process.env.GOOGLE_TTS_API_KEY || process.env.GOOGLE_API_KEY);
  const gcloud = process.env.CLOUDSDK_CONFIG
    ?? (process.platform === "win32" ? path.join(process.env.APPDATA ?? "", "gcloud") : path.join(os.homedir(), ".config", "gcloud"));
  if (existsSync(path.join(gcloud, "application_default_credentials.json"))) return true;
  return !!(process.env.GOOGLE_TTS_API_KEY || process.env.GOOGLE_API_KEY);
}

/** A Gemini API key is set: Gemini 3.8 Flash TTS can speak here (harness/lecture/gemini_tts.py). */
export function geminiConfigured(): boolean {
  return !!(process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY);
}

/**
 * What a lecture is spoken with: "gemini" (Gemini 3.8 Flash TTS, the narration voice), "chirp" (Google Chirp 3 HD,
 * with PANIM_TTS=chirp), "silent" when PANIM_VOICE=silent asks for no narration, "none" when the chosen voice is
 * not set up (a lecture build then stops).
 */
export function voiceEngine(): "gemini" | "chirp" | "silent" | "none" {
  if (process.env.PANIM_VOICE === "silent") return "silent";
  if ((process.env.PANIM_TTS ?? "").toLowerCase() === "chirp") return chirpConfigured() ? "chirp" : "none";
  return geminiConfigured() ? "gemini" : "none";
}

/** The voice's name, for the page. */
export function voiceName(): string {
  return (process.env.PANIM_TTS ?? "").toLowerCase() === "chirp" ? "Google Chirp 3 HD"
    : `Gemini ${process.env.PANIM_TTS_MODEL ?? "gemini-3.8-flash-tts"}`.replace("Gemini gemini-", "Gemini ");
}

/** Why a lecture cannot be narrated here, or null when it can. */
export function voiceProblem(): string | null {
  if (voiceEngine() !== "none") return null;
  return (process.env.PANIM_TTS ?? "").toLowerCase() === "chirp"
    ? "Narration is spoken by Google Chirp 3 HD (PANIM_TTS=chirp), and no Google credentials are set. Sign in with " +
      "`gcloud auth application-default login`, or set GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_TTS_API_KEY " +
      "(harness/SETUP.md); restart the app. PANIM_VOICE=silent builds without narration."
    : "Narration is spoken by Gemini 3.8 Flash TTS, and no Gemini API key is set. Put GEMINI_API_KEY=<a key from " +
      "aistudio.google.com/apikey> in harness/app/.env.local and restart the app (harness/SETUP.md). " +
      "PANIM_VOICE=silent builds without narration.";
}

const fetching = new Map<string, Promise<boolean>>();

/** Run a download script once (concurrent callers share it); true when `ready` holds afterwards. */
function fetchOnce(script: string, ready: () => boolean, args: string[] = []): Promise<boolean> {
  if (ready()) return Promise.resolve(true);
  let running = fetching.get(script);
  if (!running) {
    running = new Promise<boolean>((resolve) => {
      const child = spawn(python(), [path.join(REPO, "harness", "scripts", script), ...args], { cwd: REPO });
      child.on("close", () => resolve(ready()));
      child.on("error", () => resolve(false));
    }).finally(() => fetching.delete(script));
    fetching.set(script, running);
  }
  return running;
}

// The SVG drawings a diagram's nodes use (a tree, a deer, a factory): colour emoji sets and silhouettes.
const SYMBOL_SETS = ["fluent-emoji-flat", "twemoji", "noto", "openmoji", "game-icons"];

export function symbolsReady(): boolean {
  return SYMBOL_SETS.every((set) => existsSync(path.join(REPO, "harness", "lecture", "data", "icons", `${set}.json`)));
}

/** The diagram drawings, downloaded once when missing; without them diagram nodes show their labels only. */
export function ensureSymbols(): Promise<boolean> {
  return fetchOnce("fetch_icons.py", symbolsReady, ["--missing"]);
}

/**
 * The folders LaTeX's programs may be in: PATH, then where TinyTeX, MacTeX and TeX Live install
 * (harness/lecture/nolatex.py TEX_HOMES finds the same ones when a render runs).
 */
function texFolders(): string[] {
  const home = os.homedir();
  const folders = (process.env.PATH ?? "").split(path.delimiter).filter(Boolean);
  const under = (dir: string) => {
    try {
      return readdirSync(dir).map((name) => path.join(dir, name));
    } catch {
      return [];
    }
  };
  folders.push(...under(path.join(home, "Library", "TinyTeX", "bin")), ...under(path.join(home, ".TinyTeX", "bin")),
    "/Library/TeX/texbin", ...under("/usr/local/texlive").flatMap((year) => under(path.join(year, "bin"))),
    "/opt/homebrew/bin", "/usr/local/bin");
  return folders;
}

/** Which of LaTeX's programs are installed: equations are typeset with them, and drawn as text without. */
export function latexStatus(): { latex: boolean; xelatex: boolean; missing: string[]; where: string | null } {
  const folders = texFolders();
  const find = (program: string) => folders.find((dir) => existsSync(path.join(dir, program))) ?? null;
  const found = { latex: find("latex"), dvisvgm: find("dvisvgm"), xelatex: find("xelatex") };
  const missing = Object.entries(found).filter(([, dir]) => !dir).map(([name]) => name);
  const where = found.latex ? found.latex.replace(os.homedir(), "~") : null;
  return { latex: !!found.latex && !!found.dvisvgm, xelatex: !!found.xelatex && !!found.dvisvgm, missing, where };
}

export type Resource = { id: string; label: string; ready: boolean; detail: string; install?: string };

/** The downloaded libraries and keys a lecture draws on, and how to get the missing ones. */
export function resources(): Resource[] {
  const data = path.join(REPO, "harness", "lecture", "data");
  const gazetteer = existsSync(path.join(data, "geonames", "cities.txt"));
  const voice = voiceEngine();
  const openstax = existsSync(path.join(REPO, "harness", "lecture", "data", "illustrations", "openstax-physics", "index.json"));
  const tex = latexStatus();
  return [
    { id: "voice", label: "Voice", ready: voice === "gemini" || voice === "chirp",
      detail: voice === "gemini" || voice === "chirp" ? voiceName()
        : voice === "silent" ? "none: PANIM_VOICE=silent builds lectures without narration"
        : `NOT SET UP: lectures will not build. ${voiceProblem()}` },
    { id: "latex", label: "LaTeX", ready: tex.latex,
      detail: tex.latex
        ? `equations typeset by LaTeX (${tex.where})${tex.xelatex ? "; Hindi in formulas by XeLaTeX" : " (xelatex missing: Hindi in formulas is drawn as text)"}`
        : tex.where
          ? `found ${tex.where} but ${tex.missing.join(" and ")} missing: equations are drawn as plain text. Download adds it`
          : "NOT INSTALLED: equations are drawn as plain text. Download installs TinyTeX (about 250 MB, a few minutes)",
      install: tex.latex && tex.xelatex ? undefined : "latex" },
    { id: "illustrations", label: "Illustrations", ready: process.env.PANIM_IMAGES !== "0",
      detail: process.env.PANIM_IMAGES === "0" ? "internet pictures are off (PANIM_IMAGES=0): no illustrations"
        : `NASA, The Met, Smithsonian, Wikimedia Commons, Openverse${process.env.OPENROUTER_API_KEY && process.env.PANIM_AI_ILLUSTRATIONS !== "0" ? ", AI when nothing fits" : ""}` },
    { id: "symbols", label: "Diagram drawings", ready: symbolsReady(),
      detail: symbolsReady() ? "SVG drawings for diagram nodes" : "diagram nodes show labels only until downloaded (about 75 MB; fetched on the next lecture)",
      install: symbolsReady() ? undefined : "icons" },
    { id: "openstax", label: "Textbook figures", ready: openstax,
      detail: openstax ? `OpenStax figures indexed${process.env.PANIM_ALLOW_NC === "1" ? " (non-commercial books allowed)" : ""}`
        : "OpenStax textbook figures not indexed yet (a few MB)", install: openstax ? undefined : "openstax" },
    { id: "gazetteer", label: "Towns", ready: gazetteer,
      detail: gazetteer ? "GeoNames, about 150,000 towns" : "only Natural Earth's 7,300 towns until downloaded (10 MB)",
      install: gazetteer ? undefined : "gazetteer" },
    { id: "datalab", label: "Datalab", ready: Boolean(process.env.DATALAB_API_KEY),
      detail: process.env.DATALAB_API_KEY ? "PDFs converted by Datalab" : "set DATALAB_API_KEY for clean PDF figures (pypdf is used without it)" },
    { id: "photos", label: "Photos", ready: process.env.PANIM_IMAGES !== "0",
      detail: process.env.PANIM_IMAGES === "0" ? "internet photos are off (PANIM_IMAGES=0)" : "Wikimedia Commons, reusable licences only" },
  ];
}
