/**
 * Which harness is running: the app's version, and the git commit and branch
 * it was started from, so a screenshot says exactly what produced a video.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import pkg from "../package.json";
import { REPO } from "./pocketanim";

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

export type Resource = { id: string; label: string; ready: boolean; detail: string; install?: string };

/** The downloaded libraries and keys a lecture draws on, and how to get the missing ones. */
export function resources(): Resource[] {
  const data = path.join(REPO, "harness", "lecture", "data");
  const icons = existsSync(path.join(data, "icons", "game-icons.json"));
  const gazetteer = existsSync(path.join(data, "geonames", "cities.txt"));
  return [
    { id: "icons", label: "Icons", ready: icons,
      detail: icons ? "about 25,000 icons for illustrations" : "illustrations and icon ops are off until downloaded (53 MB)",
      install: icons ? undefined : "icons" },
    { id: "gazetteer", label: "Towns", ready: gazetteer,
      detail: gazetteer ? "GeoNames, about 150,000 towns" : "only Natural Earth's 7,300 towns until downloaded (10 MB)",
      install: gazetteer ? undefined : "gazetteer" },
    { id: "datalab", label: "Datalab", ready: Boolean(process.env.DATALAB_API_KEY),
      detail: process.env.DATALAB_API_KEY ? "PDFs converted by Datalab" : "set DATALAB_API_KEY for clean PDF figures (pypdf is used without it)" },
    { id: "photos", label: "Photos", ready: process.env.PANIM_IMAGES !== "0",
      detail: process.env.PANIM_IMAGES === "0" ? "internet photos are off (PANIM_IMAGES=0)" : "Wikimedia Commons, reusable licences only" },
  ];
}
