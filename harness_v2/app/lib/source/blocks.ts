/**
 * Datalab's JSON of the book (lib/datalab.ts), read as the list of its blocks in page order. Nothing is re-parsed: a
 * block keeps Datalab's id, type and HTML. Its bounding box is kept for the page (the PDF view draws it) and left out
 * of everything a model reads.
 *
 * A group (a figure with its caption, a list, a table) is one block: its parts are not taught apart.
 */

import type { RawBlock } from "../datalab";

export type Block = {
  /** Datalab's id: "/page/3/Text/7". */
  id: string;
  /** Datalab's block_type: SectionHeader, Text, Figure, Picture, Caption, ListGroup, Table, Equation, PageHeader... */
  type: string;
  /** The block's content as Datalab gives it (HTML). */
  html: string;
  /** Its text, tags taken out (for the page and for counting). */
  text: string;
  /** 0-based page. */
  page: number;
  /** Where it is on its page, as fractions of the page's width and height: [x0, y0, x1, y1]. Never sent to a model. */
  box: [number, number, number, number];
  /** A figure's picture was cut out by Datalab (the figures step describes it). */
  image?: boolean;
  /** What a figure shows, as the figures step described it. */
  description?: string;
};

/** Blocks that are a group: kept whole. */
const GROUPS = /^(FigureGroup|PictureGroup|TableGroup|ListGroup|Table|Form|Figure|Picture|ComplexRegion)$/;

export function datalabBlocks(json: RawBlock, figures: Record<string, string> = {}): Block[] {
  const out: Block[] = [];
  const pages = (json.children ?? []).filter((c) => c.block_type === "Page");
  pages.forEach((page, p) => {
    const [px0, py0, px1, py1] = page.bbox ?? [0, 0, 1, 1];
    const w = Math.max(1e-6, px1 - px0), h = Math.max(1e-6, py1 - py0);
    const visit = (b: RawBlock) => {
      // A block with children that is not a group and has no content of its own: its children are the blocks.
      if (b.children?.length && !GROUPS.test(b.block_type) && !b.html) return b.children.forEach(visit);
      const box = b.bbox ?? [px0, py0, px1, py1];
      const ids = [b.id, ...(b.children ?? []).map((c) => c.id)];
      out.push({
        id: b.id, type: b.block_type, html: (b.html ?? "").trim(), text: plain(b.html ?? ""), page: p,
        box: [(box[0] - px0) / w, (box[1] - py0) / h, (box[2] - px0) / w, (box[3] - py0) / h],
        ...(ids.some((id) => figures[id]) ? { image: true } : {}),
      });
    };
    (page.children ?? []).forEach(visit);
  });
  return out;
}

/** The figure file of a block (its own picture or its group's). */
export function figureFile(block: Block, json: RawBlock, figures: Record<string, string>): string | undefined {
  if (figures[block.id]) return figures[block.id];
  const find = (b: RawBlock): RawBlock | undefined => (b.id === block.id ? b : (b.children ?? []).map(find).find(Boolean));
  return (find(json)?.children ?? []).map((c) => figures[c.id]).find(Boolean);
}

export function plain(html: string): string {
  return html.replace(/<(?:br|\/p|\/li|\/h\d|\/td|\/tr)[^>]*>/gi, " ").replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, "\"").replace(/&#39;/g, "'").replace(/&amp;/g, "&")
    .replace(/\s+/g, " ").trim();
}

/** A block as a model reads it: Datalab's own fields, its box and pictures left out; a figure with what it shows. */
export function forModel(b: Block): Record<string, string> {
  return { id: b.id, block_type: b.type, html: b.html, ...(b.description ? { figure_shows: b.description } : {}) };
}

/** Blocks as JSON lines, in order: what the planner and the writers read. */
export function blocksJson(blocks: Block[]): string {
  return blocks.map((b) => JSON.stringify(forModel(b))).join("\n");
}

export const bookWords = (blocks: Block[]) => blocks.reduce((n, b) => n + b.text.split(/\s+/).filter(Boolean).length, 0);

/**
 * A figure's caption: a Caption block beside it on its page (the two after it, then the two before), else a text
 * block there that reads as one ("Figure 3.2: ...", "Fig. 4 ..."), as the offline reader and some books give it.
 */
export function captionOf(blocks: Block[], block: Block): string | undefined {
  const i = blocks.indexOf(block);
  const near = [...blocks.slice(i + 1, i + 3), ...blocks.slice(Math.max(0, i - 2), i).reverse()].filter((b) => b.page === block.page);
  return (near.find((b) => kindOf(b.type) === "caption") ?? near.find((b) => /^\s*(fig(ure)?\.?)\s*\d/i.test(b.text)))?.text;
}

/** A rough sort of Datalab's types, for colours and counts on the page. */
export function kindOf(type: string): "heading" | "text" | "figure" | "table" | "caption" | "furniture" {
  if (/SectionHeader|Title/.test(type)) return "heading";
  if (/Figure|Picture/.test(type)) return "figure";
  if (/Table|Form/.test(type)) return "table";
  if (/Caption/.test(type)) return "caption";
  if (/PageHeader|PageFooter|Footnote/.test(type)) return "furniture";
  return "text";
}
