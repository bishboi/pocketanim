/**
 * Which harness is running: the app's version, and the git commit and branch
 * it was started from, so a screenshot says exactly what produced a video.
 */

import { execFileSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
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

/**
 * What a lecture is spoken with. Google Chirp 3 HD is the only narration voice: "chirp" when it is set up,
 * "silent" when PANIM_VOICE=silent asks for no narration, "none" when neither (a lecture build then stops).
 */
export function voiceEngine(): "chirp" | "silent" | "none" {
  if (process.env.PANIM_VOICE === "silent") return "silent";
  return chirpConfigured() ? "chirp" : "none";
}

/** Why a lecture cannot be narrated here, or null when it can. */
export function voiceProblem(): string | null {
  return voiceEngine() === "none"
    ? "Narration is spoken by Google Chirp 3 HD, and no Google credentials are set. Sign in with " +
      "`gcloud auth application-default login` (then `gcloud auth application-default set-quota-project <PROJECT_ID>`), " +
      "or set GOOGLE_APPLICATION_CREDENTIALS to a service-account key, or GOOGLE_TTS_API_KEY where the project " +
      "allows keys (harness/SETUP.md); restart the app. PANIM_VOICE=silent builds without narration."
    : null;
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

export type Resource = { id: string; label: string; ready: boolean; detail: string; install?: string };

/** The downloaded libraries and keys a lecture draws on, and how to get the missing ones. */
export function resources(): Resource[] {
  const data = path.join(REPO, "harness", "lecture", "data");
  const gazetteer = existsSync(path.join(data, "geonames", "cities.txt"));
  const voice = voiceEngine();
  const openstax = existsSync(path.join(REPO, "harness", "lecture", "data", "illustrations", "openstax-physics", "index.json"));
  return [
    { id: "voice", label: "Voice", ready: voice === "chirp",
      detail: voice === "chirp" ? "Google Chirp 3 HD"
        : voice === "silent" ? "none: PANIM_VOICE=silent builds lectures without narration"
        : "NOT SET UP: lectures will not build. Sign in with gcloud, or set a service account or key (harness/SETUP.md)" },
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
