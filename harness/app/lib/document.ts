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
  source: "datalab" | "pypdf" | "youtube";
  pages: number;
  words: number;
  note?: string | null;
  figures: Figure[];
  /** Figures the user removed from the lecture (kept on disk, so they can be restored). */
  excluded: Figure[];
  markdown: string;
  /** A reference video: its title, channel, link, caption language and length (youtube_source.py). */
  video?: { title?: string; channel?: string; url?: string; language?: string; generated?: boolean; duration?: number };
  /** The reference video's parts, in order: where each starts and ends (seconds) and what it says. */
  parts?: { part: number; start: number; end: number; text: string }[];
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

/**
 * A YouTube video as a lecture's reference: its transcript, fetched from YouTube's captions, or pasted in when
 * YouTube refuses this network. Stored like a PDF (a manifest and a Markdown file), without figures.
 */
export async function addReference(input: { url?: string; transcript?: string; title?: string }): Promise<DocumentManifest> {
  const url = (input.url ?? "").trim();
  const transcript = (input.transcript ?? "").trim();
  if (!url && !transcript) throw new Error("give a YouTube link or paste its transcript");
  const id = randomBytes(8).toString("hex");
  const dir = folder(id);
  await mkdir(dir, { recursive: true });
  const args = [path.join(REPO, "harness", "lecture", "youtube_source.py")];
  if (transcript) {
    const file = path.join(dir, "transcript.txt");
    await writeFile(file, transcript, "utf8");
    args.push("--transcript", file);
  } else {
    args.push(url);
  }
  args.push(path.join(dir, "out"));
  if (input.title?.trim()) args.push("--title", input.title.trim());
  const { stdout, stderr, code } = await new Promise<{ code: number; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(python(), args, { cwd: REPO, env: { ...process.env, PANIM_REFERENCE_URL: url } });
    let out = "";
    let err = "";
    child.stdout.on("data", (c) => (out += c.toString()));
    child.stderr.on("data", (c) => (err += c.toString()));
    const timer = setTimeout(() => child.kill("SIGKILL"), 180_000);
    child.on("error", reject);
    child.on("close", (exit) => {
      clearTimeout(timer);
      resolve({ code: exit ?? -1, stdout: out, stderr: err });
    });
  });
  let result: Record<string, unknown> = {};
  try {
    result = JSON.parse(stdout.trim().split("\n").pop() ?? "");
  } catch {
    throw new Error(stderr.trim().split("\n").slice(-3).join("\n") || `the transcript reader exited ${code}`);
  }
  if (result.error) throw new Error(String(result.error));
  return loadDocument(id);
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

/** The figures the user removed, beside the PDF (Forge's reader looks for the same file). */
async function excludedIds(id: string): Promise<string[]> {
  try {
    const list = JSON.parse(await readFile(path.join(folder(id), "excluded.json"), "utf8"));
    return Array.isArray(list) ? list.map(String) : [];
  } catch {
    return [];
  }
}

/** Remove figures from the lecture, or (with an empty list) restore them all. */
export async function setExcluded(id: string, figures: string[]): Promise<DocumentManifest> {
  const doc = await loadDocument(id, { all: true });
  const known = new Set(doc.figures.map((f) => f.id));
  await writeFile(path.join(folder(id), "excluded.json"), JSON.stringify(figures.filter((f) => known.has(f))));
  return loadDocument(id);
}

/** A figure's marker in the Markdown: "[FIGURE fig3: caption]". */
export function figureMarker(figure: string): RegExp {
  return new RegExp(`\\[FIGURE ${figure.replace(/[^a-z0-9_]/gi, "")}:[^\\]]*\\]\\n?`, "g");
}

export async function loadDocument(id: string, options: { all?: boolean } = {}): Promise<DocumentManifest> {
  const out = path.join(folder(id), "out");
  const manifest = JSON.parse(await readFile(path.join(out, "manifest.json"), "utf8"));
  const removed = new Set(options.all ? [] : await excludedIds(id));
  let markdown = await readFile(manifest.markdown, "utf8");
  // A removed figure leaves the text too, so the model is never told it exists.
  for (const figure of removed) markdown = markdown.replace(figureMarker(figure), "");
  return {
    id,
    source: manifest.source,
    pages: manifest.pages,
    words: manifest.words,
    note: manifest.note,
    figures: (manifest.figures as Figure[]).filter((f) => !removed.has(f.id)),
    excluded: (manifest.figures as Figure[]).filter((f) => removed.has(f.id)),
    markdown,
    video: manifest.video,
    parts: manifest.parts,
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
  const doc = await loadDocument(id, { all: true });
  const found = doc.figures.find((f) => f.id === figure);
  if (!found || !existsSync(found.file)) throw new Error("no such figure");
  return found.file;
}

/** The script's `figures` table: what the compiler resolves figure ops against. */
export function scriptFigures(doc: DocumentManifest): Record<string, { file: string; caption: string }> {
  return Object.fromEntries(doc.figures.map((f) => [f.id, { file: f.file, caption: f.caption }]));
}

/** The lines of the prompt that tell the model which figures it may show. */
/** QR codes, logos and the like: images in a document that are not diagrams to teach from. */
const NOT_A_FIGURE = /\b(QR|bar ?code|logo|watermark)\b|क्यूआर/i;

export function figurePrompt(doc: DocumentManifest): string {
  const figures = doc.figures.filter((f) => !NOT_A_FIGURE.test(f.caption));
  if (!figures.length) return "";
  return [
    "",
    `FIGURES from the uploaded document (${figures.length}). Show each where the text explains it, with`,
    '{"op":"figure","id":"fig1","caption"?,"where"?:"panel"|"full"}: "panel" (default) beside the map, "full" across the',
    "frame for one beat when the detail matters. The text marks where each figure sits as [FIGURE figN: caption].",
    ...figures.map((f) => `  ${f.id}: ${f.caption}${f.page ? ` (page ${f.page})` : ""}`),
  ].join("\n");
}
