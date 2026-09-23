/**
 * The bridge to the renderer's own toolchain.
 *
 * The harness does not reimplement any of it. Export and preview are the
 * repo's Python, invoked as processes, because the exporter is the only thing
 * that can say whether a scene is faithful and the reference renderer is the
 * oracle the format is defined against.
 */

import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

/** The repo root: harness/app/lib -> harness/app -> harness -> repo. */
export const REPO = path.resolve(process.cwd(), "..", "..");

/** Prefer the repo's venv, which is where Manim lives. */
function python(): string {
  const venv = path.join(REPO, ".venv", "bin", "python");
  return existsSync(venv) ? venv : (process.env.PYTHON ?? "python3");
}

export type ExportResult = {
  scene: string;
  tier: 1 | 3 | null;
  blockers?: string[];
  program?: string | null;
  program_bytes?: number;
  assets?: string[];
  simplified?: Record<string, unknown>;
  error?: string;
};

function run(
  args: string[],
  options: { cwd?: string; binary?: boolean; timeoutMs?: number } = {},
): Promise<{ code: number; stdout: Buffer; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), args, { cwd: options.cwd ?? REPO });
    const out: Buffer[] = [];
    let err = "";
    child.stdout.on("data", (chunk) => out.push(chunk));
    child.stderr.on("data", (chunk) => (err += chunk.toString()));
    // Manim's first call in a container can be slow; a generated scene that
    // loops forever must not hold the request open for ever either.
    const timer = setTimeout(
      () => child.kill("SIGKILL"),
      options.timeoutMs ?? 180_000,
    );
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? -1, stdout: Buffer.concat(out), stderr: err });
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
  const buildDir = await mkdtemp(path.join(tmpdir(), "panim-build-"));
  const scenePath = path.join(buildDir, "scene.py");
  await writeFile(scenePath, source, "utf8");

  const { stdout, stderr, code } = await run([
    path.join(REPO, "harness", "scripts", "export_scene.py"),
    scenePath,
    sceneClass,
    buildDir,
  ]);

  const text = stdout.toString().trim();
  if (!text) {
    return {
      buildDir,
      result: {
        scene: sceneClass,
        tier: null,
        error: stderr.trim().split("\n").slice(-3).join("\n") || `exit ${code}`,
      },
    };
  }
  return { buildDir, result: JSON.parse(text.split("\n").pop()!) as ExportResult };
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
  const script = `
import io, sys
sys.path.insert(0, ${JSON.stringify(REPO)})
from dsl.interpret import load_program
from exporter.reference_render import render_frame
from PIL import Image

ir = load_program("dsl/generated/${sceneClass}.panim")
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

/** How many frames a built program has, so the scrubber knows its range. */
export async function frameCount(
  buildDir: string,
  sceneClass: string,
): Promise<number> {
  const script = `
import sys
sys.path.insert(0, ${JSON.stringify(REPO)})
from dsl.interpret import load_program
print(len(load_program("dsl/generated/${sceneClass}.panim").records))
`;
  const { stdout, code } = await run(["-c", script], { cwd: buildDir, timeoutMs: 60_000 });
  return code === 0 ? parseInt(stdout.toString().trim(), 10) || 0 : 0;
}
