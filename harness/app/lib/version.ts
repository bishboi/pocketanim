/**
 * Which harness is running: the app's version, and the git commit and branch
 * it was started from, so a screenshot says exactly what produced a video.
 */

import { execFileSync, spawn } from "node:child_process";
import { existsSync, statSync } from "node:fs";
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

function which(binary: string): boolean {
  try {
    execFileSync("which", [binary], { stdio: "ignore", timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}

/** What a lecture is spoken with: Kokoro, espeak-ng, or nothing (a silent video). */
export function voiceEngine(): "kokoro" | "espeak" | "none" {
  const models = path.join(REPO, "harness", "models");
  const weights = ["kokoro-v1.0.onnx", "voices-v1.0.bin"].every((f) => {
    try {
      return statSync(path.join(models, f)).size > 1_000_000;
    } catch {
      return false;
    }
  });
  if (weights) {
    try {
      execFileSync(python(), ["-c", "import kokoro_onnx, soundfile"], { stdio: "ignore", timeout: 20000 });
      return "kokoro";
    } catch {
      // the weights without the package: fall through
    }
  }
  return which("espeak-ng") || which("espeak") ? "espeak" : "none";
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

/**
 * Kokoro-82M, downloaded (and kokoro-onnx installed) if it is missing, so a
 * lecture is voiced by it rather than by espeak-ng. False when it could not be
 * fetched (offline), and espeak-ng speaks instead.
 */
export function ensureKokoro(): Promise<boolean> {
  return fetchOnce("fetch_voice.py", () => voiceEngine() === "kokoro");
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
    { id: "voice", label: "Voice", ready: voice === "kokoro",
      detail: voice === "kokoro" ? "Kokoro-82M" : voice === "espeak"
        ? "espeak-ng only (robotic); download Kokoro-82M (350 MB); it is also fetched on the next lecture build"
        : "NONE: lecture videos will be silent. Download Kokoro-82M (350 MB)",
      install: voice === "kokoro" ? undefined : "voice" },
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
