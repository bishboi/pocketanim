/**
 * Lecture PDFs: an upload is converted by harness/lecture/pdf_source.py
 * (Datalab when DATALAB_API_KEY is set, pypdf otherwise) into Markdown and
 * its figures. The Markdown becomes the lecture's content; each figure is
 * offered to the model as `{"op":"figure","id":"fig3"}`, and the compiler
 * gets the image files from here -- the model never sees a path.
 */

import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { REPO, python } from "./pocketanim";

const PREFIX = "panim-doc-";
const ID = /^[a-f0-9]{16}$/;

export type Figure = { id: string; file: string; caption: string; page?: number | null };
export type DocumentManifest = {
  id: string;
  source: "datalab" | "pypdf";
  pages: number;
  words: number;
  note?: string | null;
  figures: Figure[];
  markdown: string;
};

function folder(id: string): string {
  if (!ID.test(id)) throw new Error("not a document id");
  return path.join(tmpdir(), `${PREFIX}${id}`);
}

function convert(pdf: string, out: string): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), [path.join(REPO, "harness", "lecture", "pdf_source.py"), pdf, out], {
      cwd: REPO,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (c) => (stdout += c.toString()));
    child.stderr.on("data", (c) => (stderr += c.toString()));
    const timer = setTimeout(() => child.kill("SIGKILL"), 1_200_000);
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? -1, stdout, stderr });
    });
  });
}

/** Save an uploaded PDF and convert it. */
export async function addDocument(bytes: Uint8Array): Promise<DocumentManifest> {
  if (bytes.length < 5 || Buffer.from(bytes.slice(0, 5)).toString() !== "%PDF-") throw new Error("that is not a PDF");
  const id = randomBytes(8).toString("hex");
  const dir = folder(id);
  await mkdir(dir, { recursive: true });
  const pdf = path.join(dir, "source.pdf");
  await writeFile(pdf, bytes);
  const { stdout, stderr, code } = await convert(pdf, path.join(dir, "out"));
  const line = stdout.trim().split("\n").pop() ?? "";
  let result: Record<string, unknown> = {};
  try {
    result = JSON.parse(line);
  } catch {
    throw new Error(stderr.trim().split("\n").slice(-3).join("\n") || `the converter exited ${code}`);
  }
  if (result.error) throw new Error(String(result.error));
  return loadDocument(id);
}

export async function loadDocument(id: string): Promise<DocumentManifest> {
  const out = path.join(folder(id), "out");
  const manifest = JSON.parse(await readFile(path.join(out, "manifest.json"), "utf8"));
  return {
    id,
    source: manifest.source,
    pages: manifest.pages,
    words: manifest.words,
    note: manifest.note,
    figures: manifest.figures,
    markdown: await readFile(manifest.markdown, "utf8"),
  };
}

/** An uploaded PDF's path, for a Forge job's --source. */
export function documentPdf(id: string): string {
  const pdf = path.join(folder(id), "source.pdf");
  if (!existsSync(pdf)) throw new Error("that document is gone; upload it again");
  return pdf;
}

/** A figure's image file, for the thumbnail route. */
export async function figureFile(id: string, figure: string): Promise<string> {
  const doc = await loadDocument(id);
  const found = doc.figures.find((f) => f.id === figure);
  if (!found || !existsSync(found.file)) throw new Error("no such figure");
  return found.file;
}

/** The script's `figures` table: what the compiler resolves figure ops against. */
export function scriptFigures(doc: DocumentManifest): Record<string, { file: string; caption: string }> {
  return Object.fromEntries(doc.figures.map((f) => [f.id, { file: f.file, caption: f.caption }]));
}

/** The lines of the prompt that tell the model which figures it may show. */
export function figurePrompt(doc: DocumentManifest): string {
  if (!doc.figures.length) return "";
  return [
    "",
    `FIGURES from the uploaded document (${doc.figures.length}). Show each where the text explains it, with`,
    '{"op":"figure","id":"fig1","caption"?,"where"?:"panel"|"full"}: "panel" (default) beside the map, "full" across the',
    "frame for one beat when the detail matters. The text marks where each figure sits as [FIGURE figN: caption].",
    ...doc.figures.map((f) => `  ${f.id}: ${f.caption}${f.page ? ` (page ${f.page})` : ""}`),
  ].join("\n");
}
