/**
 * A figure drawn in Manim, rendered: the Manim model's code (the body of construct()) is put in a scene on v1's
 * default board (its colour, INK, MUTED_INK and PALETTE, as v1's lecture engine gives them) and rendered with the
 * repo's Manim (.venv, harness/scripts/setup-python.sh): its last frame as a PNG and the whole as a short MP4.
 *
 * The code is a model's, run on this machine, so code checks it first, as v1's compiler did: no imports, no file,
 * OS or process access, no exec/eval, no dunder names, no while loops, no camera or mobject surgery. It then runs in
 * its own process, in its own folder, with a time limit.
 */

import { detachedForAbort, killOnAbort } from "./abort";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { BOARD_BG, PALETTE } from "./prompts/svg";
import { REPO } from "./store";

const TIMEOUT_MS = Math.max(20, Number(process.env.V2_MANIM_TIMEOUT_SECONDS) || 120) * 1000;

/** What a block may not contain: v1's rules (lecture.ts MANIM_RULES), and anything that reaches outside Manim. */
const BANNED: [RegExp, string][] = [
  [/^\s*(import|from)\s/m, "imports (everything Manim exports and np are there already)"],
  [/\b(open|exec|eval|compile|__import__|globals|locals|getattr|setattr|delattr|vars|input|breakpoint)\s*\(/, "open/exec/eval and the like"],
  [/\b(os|sys|subprocess|shutil|pathlib|socket|requests|urllib|importlib|builtins)\s*\./, "OS, file or network access"],
  [/__\w+__/, "dunder names"],
  [/^\s*while\b/m, "while loops"],
  [/^\s*class\s/m, "classes"],
  [/self\.(camera|mobjects|clear|renderer)\b/, "self.camera / self.mobjects / self.clear"],
];

export function checkManim(code: string): string[] {
  const problems = BANNED.filter(([re]) => re.test(code)).map(([, why]) => `not allowed: ${why}`);
  if (!/self\.(play|add)\s*\(/.test(code)) problems.push("nothing is drawn: no self.play or self.add");
  if (code.length > 40_000) problems.push("over 40 KB of code");
  return problems;
}

/** The scene the code runs in: v1's board, its ink and palette, picture() unavailable (no illustration model here). */
export function sceneSource(code: string): string {
  const palette = Object.entries(PALETTE).map(([k, v]) => `"${k}": "${v}"`).join(", ");
  const body = code.replace(/\t/g, "    ").split("\n").map((l) => `        ${l}`).join("\n");
  return [
    "from manim import *",
    "import numpy as np",
    `config.background_color = "${BOARD_BG}"`,
    `INK = "${PALETTE.INK}"`,
    `MUTED_INK = "${PALETTE.MUTED}"`,
    `PALETTE = {${palette}}`,
    "",
    "def picture(*args, **kwargs):",
    '    raise RuntimeError("picture() is not available here: draw it with shapes")',
    "",
    "class Figure(Scene):",
    "    def construct(self):",
    body,
    "        self.wait(1)",
    "",
  ].join("\n");
}

/** The Python that runs Manim: V2_PYTHON, else the repo's .venv (looked for upward from here, as v1 does), else python3. */
export function pythonPath(): string {
  if (process.env.V2_PYTHON) return process.env.V2_PYTHON;
  for (let dir = REPO, up = 0; up < 4; dir = path.dirname(dir), up++) {
    const venv = path.join(dir, ".venv", "bin", "python");
    if (existsSync(venv)) return venv;
  }
  return "python3";
}

export function runPython(args: string[], cwd: string, env: Record<string, string> = {}, input?: string, timeout = TIMEOUT_MS):
  Promise<{ code: number | null; out: string; stdout: string }> {
  return new Promise((resolve) => {
    const child = spawn(pythonPath(), args, { cwd, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...env }, detached: detachedForAbort() });
    let stdout = "";
    child.stdout.on("data", (d) => (stdout += d));
    if (input !== undefined) child.stdin.end(input);
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      out += `\nstopped: over ${timeout / 1000} s`;
    }, timeout);
    // A stopped job kills it (and the renders and encoders it started).
    const unwatch = killOnAbort(child, () => (out += "\nstopped"));
    child.on("close", (code) => {
      clearTimeout(timer);
      unwatch();
      resolve({ code, out, stdout });
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      unwatch();
      resolve({ code: -1, out: String(error), stdout });
    });
  });
}

export async function find(dir: string, ext: string): Promise<string | undefined> {
  if (!existsSync(dir)) return undefined;
  for (const e of await readdir(dir, { withFileTypes: true, recursive: true })) {
    if (e.isFile() && e.name.endsWith(ext) && !e.name.includes("partial")) return path.join(e.parentPath ?? (e as unknown as { path: string }).path, e.name);
  }
  return undefined;
}

/** The last error lines of a failed render: what goes back to the model. */
export function errorOf(out: string): string {
  const lines = out.split("\n").map((l) => l.replace(/\x1b\[[0-9;]*m/g, "").trimEnd()).filter(Boolean);
  const at = lines.findIndex((l) => /Traceback|Error/.test(l));
  return (at >= 0 ? lines.slice(at) : lines.slice(-12)).slice(-14).join("\n").slice(0, 1500);
}

export type Rendered = { png?: string; mp4?: string; error?: string; seconds: number };

/** The code rendered in `dir`: its last frame (PNG) and its video (MP4), or why not. */
export async function renderManim(code: string, dir: string): Promise<Rendered> {
  const problems = checkManim(code);
  if (problems.length) return { error: problems.join("; "), seconds: 0 };
  return renderScene(sceneSource(code), "Figure", dir);
}

/**
 * A scene's source rendered in `dir` (a fresh folder): its last frame first (a broken scene fails fast, its error
 * said), then its video. `env` is added to the render's environment (v1's engine on PYTHONPATH, silent voice).
 */
export async function renderScene(source: string, scene: string, dir: string, env: Record<string, string> = {}): Promise<Rendered> {
  const began = Date.now();
  await rm(dir, { recursive: true, force: true });
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "figure.py"), source, "utf8");
  const base = ["-m", "manim", "render", "-ql", "--disable_caching", "--media_dir", "media", "figure.py", scene];
  const run = (args: string[], cwd: string) => runPython(args, cwd, env);
  const still = await run([...base.slice(0, 4), "-s", ...base.slice(4)], dir);
  const png = await find(path.join(dir, "media", "images"), ".png");
  if (still.code !== 0 || !png) {
    const why = errorOf(still.out);
    return { error: /No module named ['"]?manim/.test(still.out)
      ? "Manim is not installed for this Python: run harness/scripts/setup-python.sh (it makes .venv with Manim)" : why || "the render failed",
      seconds: (Date.now() - began) / 1000 };
  }
  const movie = await run(base, dir);
  const mp4 = movie.code === 0 ? await find(path.join(dir, "media", "videos"), ".mp4") : undefined;
  return { png, mp4, seconds: (Date.now() - began) / 1000, ...(mp4 ? {} : { error: `the video did not render: ${errorOf(movie.out)}` }) };
}
