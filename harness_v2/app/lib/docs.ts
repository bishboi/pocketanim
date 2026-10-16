/**
 * A book PDF in: kept as it is (the page shows it, with each part's text highlighted), and read into Markdown by
 * v1's reader, harness/lecture/pdf_source.py (Datalab with DATALAB_API_KEY, pypdf without), unchanged.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { REPO, docDir, newId } from "./store";
import type { DocumentInfo } from "./types";

function python(): string {
  const venv = path.join(REPO, ".venv", "bin", "python");
  return existsSync(venv) ? venv : "python3";
}

export async function addDocument(name: string, bytes: Uint8Array): Promise<DocumentInfo> {
  const id = newId();
  const dir = docDir(id);
  await mkdir(dir, { recursive: true });
  const pdf = path.join(dir, "source.pdf");
  await writeFile(pdf, bytes);
  const out = path.join(dir, "out");
  const result = await new Promise<{ code: number; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(python(), [path.join(REPO, "harness", "lecture", "pdf_source.py"), pdf, out], { cwd: REPO, env: process.env });
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
  if (result.code !== 0) throw new Error(`the PDF could not be read: ${(result.stderr || result.stdout).trim().slice(-400)}`);
  const manifest = JSON.parse(await readFile(path.join(out, "manifest.json"), "utf8")) as { source: string; pages: number;
    markdown?: string };
  // The reader caches by the PDF's content and names where its Markdown is: a copy is kept with the document.
  const markdown = await readFile(manifest.markdown && existsSync(manifest.markdown) ? manifest.markdown : path.join(out, "document.md"), "utf8");
  await writeFile(path.join(out, "document.md"), markdown, "utf8");
  const info: DocumentInfo = { id, name, pages: manifest.pages, words: markdown.split(/\s+/).filter(Boolean).length,
    source: manifest.source, created: Date.now() };
  await writeFile(path.join(dir, "info.json"), JSON.stringify(info), "utf8");
  return info;
}
