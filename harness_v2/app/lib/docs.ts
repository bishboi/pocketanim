/**
 * A book PDF in: kept as it is (the page shows it, each block's box drawn on it), and read by Datalab into its JSON
 * (lib/datalab.ts): the book from here on. Figures Datalab cut out are kept beside it, by block id.
 */

import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { convertPdf, refreshFigures, type FigureReport } from "./datalab";
import { datalabBlocks, figureFile, type Block } from "./source/blocks";
import { docDir, documentBook, newId } from "./store";
import type { DocumentInfo } from "./types";

const scanning = ((globalThis as unknown as { __v2scan?: Map<string, Promise<unknown>> }).__v2scan ??= new Map());

/**
 * A book with its figures' pictures, searched again once if it was uploaded before the search found every place
 * a picture can be (no figure-report.json, or one without the PDF cut-outs): no Datalab call, no cost.
 */
export async function bookOf(id: string): Promise<Awaited<ReturnType<typeof documentBook>> & { report?: FigureReport }> {
  const dir = docDir(id);
  const reportFile = path.join(dir, "figure-report.json");
  let report = existsSync(reportFile) ? JSON.parse(await readFile(reportFile, "utf8")) as FigureReport : undefined;
  if (!report || report.cut === undefined) {
    if (!scanning.has(id)) scanning.set(id, refreshFigures(dir).finally(() => scanning.delete(id)));
    report = (await scanning.get(id)) as FigureReport | undefined ?? report;
  }
  return { ...(await documentBook(id)), report };
}

/** A run's blocks marked again by whether a picture is now found for them; how many changed. */
export function markPictures(blocks: Block[], book: Awaited<ReturnType<typeof documentBook>>): number {
  let changed = 0;
  for (const b of blocks) {
    const has = !!figureFile(b, book.json, book.figures);
    if (has !== !!b.image) {
      changed += 1;
      if (has) b.image = true;
      else delete b.image;
    }
  }
  return changed;
}

export async function addDocument(name: string, bytes: Uint8Array): Promise<DocumentInfo> {
  const id = newId();
  const dir = docDir(id);
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "source.pdf"), bytes);
  const book = await convertPdf(bytes, dir);
  await writeFile(path.join(dir, "book.json"), JSON.stringify(book.json), "utf8");
  await writeFile(path.join(dir, "figures.json"), JSON.stringify(book.figures), "utf8");
  const blocks = datalabBlocks(book.json, book.figures);
  const info: DocumentInfo = { id, name, pages: book.pages, words: blocks.reduce((n, b) => n + b.text.split(/\s+/).filter(Boolean).length, 0),
    source: book.source, created: Date.now() };
  await writeFile(path.join(dir, "info.json"), JSON.stringify(info), "utf8");
  return info;
}
