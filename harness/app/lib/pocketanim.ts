/**
 * The bridge to the renderer's own toolchain.
 *
 * The harness does not reimplement any of it. Export and preview are the
 * repo's Python, invoked as processes, because the exporter is the only thing
 * that can say whether a scene is faithful and the reference renderer is the
 * oracle the format is defined against.
 */

import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

/**
 * Walk up from the process cwd until the repo root is obvious.
 *
 * Next can treat a parent lockfile as the workspace root, so a fixed
 * `../..` from `harness/app` is not reliable.
 */
function findRepo(start: string): string {
  let dir = start;
  for (let i = 0; i < 6; i++) {
    if (
      existsSync(path.join(dir, "dsl", "export_dsl.py")) &&
      existsSync(path.join(dir, "harness", "scripts", "export_scene.py"))
    ) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return path.resolve(start, "..", "..");
}

export const REPO = findRepo(process.cwd());

const BUILD_PREFIX = "panim-build-";

/**
 * A build directory this app made, or an error.
 *
 * The preview routes take the directory and the scene class from the query
 * string, and both used to reach Python unchecked -- the class name inside a
 * source string, so `?scene=x")...` ran whatever followed. Builds live in the
 * temp directory under one prefix; scene classes are Python identifiers.
 */
export function checkBuild(buildDir: string, sceneClass: string): { buildDir: string; sceneClass: string } {
  const resolved = path.resolve(buildDir);
  const parent = path.resolve(tmpdir());
  if (path.dirname(resolved) !== parent || !path.basename(resolved).startsWith(BUILD_PREFIX)) {
    throw new Error("not a build directory");
  }
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(sceneClass)) throw new Error("not a scene class name");
  return { buildDir: resolved, sceneClass };
}

/** Prefer the repo's venv, which is where Manim lives. */
export function python(): string {
  const fromEnv = process.env.PYTHON?.trim();
  if (fromEnv && existsSync(fromEnv)) return fromEnv;
  const venv = path.join(REPO, ".venv", "bin", "python");
  return existsSync(venv) ? venv : "python3";
}

export type Toolchain = {
  python: string;
  manim: string | null;
  latex: boolean;
  error?: string;
};

let cachedToolchain: Toolchain | null = null;

/** Whether this Python can import Manim. Failures are not cached. */
export async function toolchain(): Promise<Toolchain> {
  if (cachedToolchain?.manim) return cachedToolchain;
  const bin = python();
  const { stdout, stderr, code } = await run(
    ["-c", "import manim,shutil; print(manim.__version__); print('latex' if shutil.which('latex') else 'no-latex')"],
    { timeoutMs: 60_000, binary: bin },
  );
  const lines = stdout.toString().trim().split("\n").filter(Boolean);
  const manim = code === 0 ? lines[0] ?? null : null;
  const result: Toolchain = {
    python: bin,
    manim,
    latex: lines.includes("latex"),
    error: manim
      ? undefined
      : explainManim(
          stderr.trim().split("\n").slice(-4).join("\n") || `exit ${code}`,
        ),
  };
  if (manim) cachedToolchain = result;
  return result;
}

function explainManim(error: string): string {
  if (!/No module named ['"]manim['"]/.test(error) && !error.includes("exit")) {
    return error;
  }
  if (/No module named ['"]manim['"]/.test(error)) {
    return [
      error,
      "",
      `The harness is using ${python()}, which does not have Manim.`,
      "From the repo root, run:",
      "  harness/scripts/setup-python.sh",
    ].join("\n");
  }
  return error;
}

export type ExportResult = {
  scene: string;
  tier: 1 | 3 | null;
  blockers?: string[];
  program?: string | null;
  program_bytes?: number;
  assets?: string[];
  simplified?: Record<string, unknown>;
  container?: string;
  frames?: number;
  container_bytes?: number;
  container_error?: string;
  error?: string;
  /** A mixed narration track the scene's own add_sound calls produced. */
  narration?: { file: string; clips: number; seconds: number };
};

function quietStderr(stderr: string): string {
  return stderr
    .split("\n")
    .filter((line) => !/resource_tracker|leaked semaphore/.test(line))
    .join("\n")
    .trim();
}

function run(
  args: string[],
  options: { cwd?: string; binary?: string; timeoutMs?: number } = {},
): Promise<{ code: number; stdout: Buffer; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(options.binary ?? python(), args, {
      cwd: options.cwd ?? REPO,
      env: {
        ...process.env,
        PYTHONWARNINGS: [process.env.PYTHONWARNINGS, "ignore:resource_tracker:UserWarning"]
          .filter(Boolean)
          .join(","),
        // Narration a lecture synthesises is cached by its text across builds,
        // so an edit re-speaks only the lines that changed.
        PANIM_AUDIO_DIR: process.env.PANIM_AUDIO_DIR ?? path.join(REPO, "harness", "app", ".voice", "cache"),
      },
    });
    const out: Buffer[] = [];
    let err = "";
    let timedOut = false;
    child.stdout.on("data", (chunk) => out.push(chunk));
    child.stderr.on("data", (chunk) => (err += chunk.toString()));
    // Manim's first call in a container can be slow; a generated scene that
    // loops forever must not hold the request open for ever either.
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, options.timeoutMs ?? 180_000);
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        code: timedOut ? -1 : (code ?? -1),
        stdout: Buffer.concat(out),
        stderr: timedOut
          ? "The preview took too long and was stopped."
          : quietStderr(err),
      });
    });
  });
}

/**
 * Write the source somewhere of its own and export it.
 *
 * The build directory is the unit: the exporter writes its assets and glyph
 * atlas by relative path, so a build that lands anywhere else would pollute
 * the repo's corpus.
 */
export async function exportScene(
  source: string,
  sceneClass: string,
): Promise<{ result: ExportResult; buildDir: string }> {
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(sceneClass)) sceneClass = "GeneratedScene";
  const buildDir = await mkdtemp(path.join(tmpdir(), BUILD_PREFIX));
  const scenePath = path.join(buildDir, "scene.py");
  await writeFile(scenePath, source, "utf8");

  const { stdout, stderr, code } = await run(
    [
      path.join(REPO, "harness", "scripts", "export_scene.py"),
      scenePath,
      sceneClass,
      buildDir,
    ],
    { timeoutMs: 600_000 },
  );

  const text = stdout.toString().trim();
  if (!text) {
    return {
      buildDir,
      result: {
        scene: sceneClass,
        tier: null,
        error: explainManim(
          stderr.trim().split("\n").slice(-6).join("\n") || `exit ${code}`,
        ),
      },
    };
  }
  const result = JSON.parse(text.split("\n").pop()!) as ExportResult;
  if (result.error) result.error = explainManim(result.error);
  return { buildDir, result };
}

/**
 * One frame of a built program, as PNG bytes.
 *
 * Rendered on demand and never written down. That is the brief's "no video at
 * rest" taken literally: the only durable artifacts are the program and its
 * assets, and a preview is recomputed from them like any other frame.
 */
export async function renderFrame(
  buildDir: string,
  sceneClass: string,
  frame: number,
  width = 640,
): Promise<Buffer | { error: string }> {
  try {
    ({ buildDir, sceneClass } = checkBuild(buildDir, sceneClass));
  } catch (error) {
    return { error: (error as Error).message };
  }
  const program = JSON.stringify(`dsl/generated/${sceneClass}.panim`);
  const script = `
import io, sys
sys.path.insert(0, ${JSON.stringify(REPO)})
from pathlib import Path
from dsl.interpret import load_program
from exporter.decode import load
from exporter.reference_render import render_frame
from PIL import Image

panm = Path(${JSON.stringify(sceneClass + ".panm")})
ir = load(panm.read_bytes()) if panm.is_file() else load_program(${program})
index = max(0, min(int(${frame}), len(ir.records) - 1))
width = int(${width})
array = render_frame(ir, index, width, round(width * 9 / 16))
buffer = io.BytesIO()
Image.fromarray(array).save(buffer, format="PNG")
sys.stdout.buffer.write(buffer.getvalue())
`;
  const { stdout, stderr, code } = await run(["-c", script], {
    cwd: buildDir,
    timeoutMs: 60_000,
  });
  if (code !== 0 || stdout.length === 0) {
    return { error: stderr.trim().split("\n").slice(-3).join("\n") || `exit ${code}` };
  }
  return stdout;
}

export type SceneIR =
  | {
      mode: "2d";
      fps: number;
      /** The program's clear colour, "#RRGGBB". Absent means black. */
      background?: string;
      shapes: number[][];
      pieces: Instance[][];
      runs: [number, number[]][];
      frames: number;
      error?: undefined;
    }
  | { mode: "3d"; fps: number; frames: number; error?: undefined }
  | { mode: "frames"; fps: number; frames: number; error?: undefined }
  | { error: string };

/** [shapeIndex, a, b, c, d, e, f, fillRGBA, strokeRGBA, strokeWidth] */
export type Instance = [
  number, number, number, number, number, number, number,
  number[], number[], number,
];

/**
 * The geometry of every frame, expanded once.
 *
 * The browser plays a scene rather than asking for a picture of it, so the
 * interpretation stays in Python -- Manim's animation semantics are the part
 * this repo spent a corpus proving -- and only the rasterising crosses over.
 */
export async function sceneIR(
  buildDir: string,
  sceneClass: string,
): Promise<SceneIR> {
  try {
    ({ buildDir, sceneClass } = checkBuild(buildDir, sceneClass));
  } catch (error) {
    return { error: (error as Error).message };
  }
  const { stdout, stderr, code } = await run(
    [path.join(REPO, "harness", "scripts", "scene_ir.py"), buildDir, sceneClass],
    { timeoutMs: 300_000 },
  );
  const text = stdout.toString().trim();
  if (!text) {
    return { error: stderr.trim().split("\n").slice(-3).join("\n") || `exit ${code}` };
  }
  const summary = JSON.parse(text.split("\n").pop()!) as {
    error?: string;
    mode?: SceneIR extends { mode: infer M } ? M : never;
    fps?: number;
    frames?: number;
    geometry?: boolean;
  };
  if (summary.error) return { error: summary.error };
  if (summary.geometry) {
    const geometry = await readFile(path.join(buildDir, "scene_ir.json"), "utf8");
    return JSON.parse(geometry) as SceneIR;
  }
  if (summary.mode === "3d" || summary.mode === "frames") {
    return { mode: summary.mode, fps: summary.fps ?? 15, frames: summary.frames ?? 0 };
  }
  return { error: "the scene geometry could not be loaded" };
}

/** How many frames a built program has, so the scrubber knows its range. */
export async function frameCount(
  buildDir: string,
  sceneClass: string,
): Promise<number> {
  ({ buildDir, sceneClass } = checkBuild(buildDir, sceneClass));
  const program = JSON.stringify(`dsl/generated/${sceneClass}.panim`);
  const script = `
import sys
sys.path.insert(0, ${JSON.stringify(REPO)})
from dsl.interpret import load_program
print(len(load_program(${program}).records))
`;
  const { stdout, code } = await run(["-c", script], { cwd: buildDir, timeoutMs: 60_000 });
  return code === 0 ? parseInt(stdout.toString().trim(), 10) || 0 : 0;
}

/**
 * Pack a build as a phone library and zip it.
 *
 * The same layout the APK ships (tools/build_library), so the player opens it
 * as it opens its own: unzip and `adb push` it to the app's files directory.
 * Narration the scene produced travels with it.
 */
export async function bundleLibrary(
  buildDir: string,
  sceneClass: string,
): Promise<{ zip: string } | { error: string }> {
  try {
    ({ buildDir, sceneClass } = checkBuild(buildDir, sceneClass));
  } catch (error) {
    return { error: (error as Error).message };
  }
  const out = path.join(buildDir, "library");
  const packed = await run(
    ["-m", "tools.build_library", "--source", path.join(buildDir, "dsl", "generated"), "--out", out],
    { timeoutMs: 300_000 },
  );
  if (packed.code !== 0) {
    return { error: packed.stderr.trim().split("\n").slice(-4).join("\n") || `exit ${packed.code}` };
  }
  const zipped = await run(
    ["-c", "import shutil, sys; print(shutil.make_archive(sys.argv[1], 'zip', sys.argv[2], 'library'))",
     path.join(buildDir, `${sceneClass}-library`), buildDir],
    { timeoutMs: 120_000 },
  );
  const zip = zipped.stdout.toString().trim().split("\n").pop() ?? "";
  if (zipped.code !== 0 || !zip) return { error: zipped.stderr || "could not zip the library" };
  return { zip };
}
