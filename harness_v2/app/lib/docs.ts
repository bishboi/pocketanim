/**
 * A book PDF in: kept as it is (the page shows it, each block's box drawn on it), and read by Datalab into its JSON
 * (lib/datalab.ts): the book from here on. Figures Datalab cut out are kept beside it, by block id.
 */

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { convertPdf } from "./datalab";
import { datalabBlocks } from "./source/blocks";
import { docDir, newId } from "./store";
import type { DocumentInfo } from "./types";

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
