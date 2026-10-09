/**
 * A long lecture as more than one video. A lecture written as a series of micro-lectures (topics.ts) is cut where
 * its topics meet (splitByTopics): each part a 20-30 minute lecture of its own. One without a plan (no transcript)
 * that runs past PANIM_MAX_VIDEO_MINUTES (30) is cut, between chapters, into the fewest parts that each stay under
 * it, as even as the chapters allow (splitLecture). Each part is a lecture script of its own.
 */

import { maxVideos, microMinutes } from "./topics";

type Script = Record<string, unknown> & { title?: unknown; chapters?: unknown; recap?: unknown; intro?: unknown };

export type LecturePart = { index: number; of: number; script: Script; minutes: number; title: string };

/**
 * The longest video, in minutes, before a lecture without a topic plan is split (PANIM_MAX_VIDEO_MINUTES): the
 * top of a micro-lecture's range (topics.ts), 30 by default.
 */
export function maxVideoMinutes(): number {
  const set = Number(process.env.PANIM_MAX_VIDEO_MINUTES);
  return Number.isFinite(set) && set > 0 ? set : microMinutes().max;
}

type PlannedTopic = { index?: unknown; title?: unknown; sections?: unknown; recap?: unknown };

/**
 * A lecture written as a series of micro-lectures (topics.ts: script.topics, each topic's sections and recap), cut
 * where its topics meet: each chapter goes with the topic of the transcript section it speaks. Each part is a
 * lecture of its own: its title card names its topic and its place in the series, its opening is the one its
 * first section was written with, and it ends on its own recap. [] when the script has no plan of two or more.
 */
export function splitByTopics(script: Script, minutes: number): LecturePart[] {
  const plan = (Array.isArray(script.topics) ? script.topics : []) as PlannedTopic[];
  const chapters = Array.isArray(script.chapters) ? script.chapters : [];
  if (plan.length < 2 || chapters.length < 2) return [];
  const topicOf = new Map<number, number>();
  plan.forEach((t, k) => (Array.isArray(t.sections) ? t.sections : []).forEach((n) => topicOf.set(Number(n), k)));
  // Each chapter's topic, never going back: a chapter without a section stays with the one before it.
  const groups: unknown[][] = plan.map(() => []);
  let at = 0;
  for (const chapter of chapters) {
    const k = topicOf.get(Number((chapter as { section?: unknown })?.section));
    if (k !== undefined && k >= at) at = k;
    groups[at].push(chapter);
  }
  const kept = plan.map((t, k) => ({ topic: t, chapters: groups[k] })).filter((g) => g.chapters.length);
  if (kept.length < 2) return [];
  const series = String(script.title ?? "Lecture");
  const total = chapters.map(words).reduce((a, b) => a + b, 0);
  return kept.map((group, k) => {
    const last = k === kept.length - 1;
    const part = topicPart({ ...script, chapters: group.chapters }, group.topic, k, kept.length, series,
      last ? script.recap : null);
    const share = group.chapters.map(words).reduce((a, b) => a + b, 0) / total;
    return {
      index: k + 1,
      of: kept.length,
      script: part.script,
      minutes: Math.round(minutes * share * 10) / 10,
      title: part.title,
    };
  });
}

/**
 * One micro-lecture of a series as a lecture of its own: `script` with that topic's chapters, its title card naming
 * the topic and its place in the series, and its own recap (`fallbackRecap` when the topic has none). Shared by the
 * final cut (splitByTopics) and the early build of a topic written before the rest (model.ts), so the two agree.
 */
export function topicPart(script: Script, topic: PlannedTopic, k: number, count: number, series: string,
  fallbackRecap: unknown): { script: Script; title: string } {
  const number = k + 1;
  const name = String(topic.title ?? "").trim() || `Part ${number}`;
  const part: Script = { ...script, title: name, sub: `${series} · Lecture ${number} of ${count}` };
  delete part.topics;
  // The first lecture keeps the series' own opening line; each later one is introduced by its title (its first
  // section's transcript does the rest).
  if (k > 0) part.intro = `${name}.`;
  const recap = topic.recap ?? fallbackRecap;
  if (Array.isArray(recap) && recap.length) part.recap = recap;
  else delete part.recap;
  return { script: part, title: `Lecture ${number}: ${name}` };
}

type Beat = { do?: Record<string, unknown>[] } & Record<string, unknown>;
type Chapter = { title?: unknown; beats?: Beat[] } & Record<string, unknown>;

/** Ids a beat's ops draw (a diagram, a sketch, a problem...), and ids they point back at (reveal, focus, work...). */
function opIds(beat: Beat): { made: string[]; used: string[] } {
  const made: string[] = [];
  const used: string[] = [];
  for (const op of beat.do ?? []) {
    if (!op || typeof op !== "object") continue;
    if (["reveal", "focus", "option", "answer", "work", "step", "annotate", "move", "highlight"].includes(String(op.op))) {
      for (const k of ["diagram", "id", "problem", "figure", "target"]) if (op[k]) used.push(String(op[k]));
      if (op.op === "answer" || op.op === "option") used.push("?question");
    } else {
      if (op.id) made.push(String(op.id));
      if (op.op === "question") made.push("?question");
    }
  }
  return { made, used };
}

/**
 * Chapters longer than `most` words cut into pieces at beats where nothing after the cut points back at a picture
 * drawn before it (a reveal of an earlier diagram, the answer to an earlier question): each piece a chapter of its
 * own, the later ones titled "(continued)". A chapter with no such place stays whole.
 */
export function expandChapters(chapters: unknown[], most: number): unknown[] {
  const out: unknown[] = [];
  for (const raw of chapters) {
    const chapter = raw as Chapter;
    const beats = Array.isArray(chapter?.beats) ? chapter.beats : [];
    if (words(chapter) <= most * 1.25 || beats.length < 4) {
      out.push(chapter);
      continue;
    }
    const ids = beats.map(opIds);
    // A cut before beat k is safe when no beat from k on uses an id made before k.
    const safe = (k: number) => {
      const before = new Set(ids.slice(0, k).flatMap((x) => x.made));
      return !ids.slice(k).some((x) => x.used.some((u) => before.has(u)));
    };
    const size = (b: Beat) => String(b?.say ?? "").split(/\s+/).filter(Boolean).length || 10;
    const pieces: Beat[][] = [];
    let current: Beat[] = [];
    let taken = 0;
    beats.forEach((beat, k) => {
      if (current.length >= 2 && taken >= most && safe(k)) {
        pieces.push(current);
        current = [];
        taken = 0;
      }
      current.push(beat);
      taken += size(beat);
    });
    if (current.length) pieces.push(current);
    pieces.forEach((piece, k) => {
      const part: Chapter = { ...chapter, beats: piece };
      if (k > 0) {
        part.title = `${String(chapter.title ?? "")} (continued)`.trim();
        delete part.narration;           // its title card is enough; the narration opened the first piece
      }
      out.push(part);
    });
  }
  return out;
}

/**
 * Parts kept to the length of a video: one longer than `limit` (a topic that came out long) is cut again, between
 * chapters or inside a long one; then, past maxVideos, the two shortest neighbours are joined until it fits. The
 * parts are numbered again, in order.
 */
export function boundParts(parts: LecturePart[], limit = maxVideoMinutes()): LecturePart[] {
  let out: LecturePart[] = parts.flatMap((part) => {
    const smaller = part.minutes > limit * 1.1 ? splitLecture(part.script, part.minutes, limit) : [];
    if (smaller.length < 2) return [part];
    return smaller.map((s, k) => ({ ...s, title: `${part.title} (${k + 1} of ${smaller.length})`,
      script: { ...s.script, title: String(part.script.title ?? part.title) } }));
  });
  while (out.length > maxVideos()) {
    let best = 0;
    for (let i = 1; i < out.length - 1; i++) {
      if (out[i].minutes + out[i + 1].minutes < out[best].minutes + out[best + 1].minutes) best = i;
    }
    out = [...out.slice(0, best), joinParts(out[best], out[best + 1]), ...out.slice(best + 2)];
  }
  return out.map((p, k) => ({ ...p, index: k + 1, of: out.length }));
}

/** Two neighbouring parts as one: the first's opening, both's chapters, the second's recap. */
export function joinParts(a: LecturePart, b: LecturePart): LecturePart {
  const chapters = [...((a.script.chapters as unknown[]) ?? []), ...((b.script.chapters as unknown[]) ?? [])];
  const script: Script = { ...a.script, chapters };
  if (b.script.recap) script.recap = b.script.recap;
  else delete script.recap;
  return { ...a, script, minutes: Math.round((a.minutes + b.minutes) * 10) / 10 };
}

function words(chapter: unknown): number {
  const c = chapter as { narration?: unknown; beats?: { say?: unknown }[] };
  const said = [String(c?.narration ?? ""), ...(c?.beats ?? []).map((b) => String(b?.say ?? ""))].join(" ");
  return Math.max(1, said.split(/\s+/).filter(Boolean).length);
}

/**
 * The parts of a lecture of `minutes` (the compiler's estimate), or [] when it fits in one video. Chapters stay
 * whole and in order; each chapter's share of the time follows its share of the narration.
 */
export function splitLecture(script: Script, minutes: number, limit = maxVideoMinutes()): LecturePart[] {
  if (!(minutes > limit)) return [];
  const wanted = Math.min(maxVideos(), Math.ceil(minutes / limit));
  // Fewer chapters than videos, or a chapter longer than a video: long chapters are cut between beats first.
  const whole = Array.isArray(script.chapters) ? script.chapters : [];
  const sizesWhole = whole.map(words);
  const allWords = Math.max(1, sizesWhole.reduce((a, b) => a + b, 0));
  // Pieces of about half a video: fine enough for the cut below to make the videos even.
  const chapters = expandChapters(whole, (allWords / wanted) * 0.45);
  if (chapters.length < 2) return [];
  const count = Math.min(chapters.length, wanted);
  const sizes = chapters.map(words);
  const total = sizes.reduce((a, b) => a + b, 0);
  // Cut where the running total passes each even share, so the parts come out as close in length as the chapters
  // allow; every part keeps at least one chapter.
  const cuts: number[] = [];
  let run = 0;
  for (let i = 0; i < chapters.length - 1 && cuts.length < count - 1; i++) {
    run += sizes[i];
    const share = (total * (cuts.length + 1)) / count;
    const next = run + sizes[i + 1];
    const left = chapters.length - 1 - i;
    if (run >= share || Math.abs(next - share) > Math.abs(run - share) || left <= count - 1 - cuts.length) {
      cuts.push(i + 1);
    }
  }
  const bounds = [0, ...cuts, chapters.length];
  const title = String(script.title ?? "Lecture");
  return bounds.slice(0, -1).map((start, k) => {
    const slice = chapters.slice(start, bounds[k + 1]);
    const share = slice.map(words).reduce((a, b) => a + b, 0) / total;
    const last = k === bounds.length - 2;
    const partTitle = `${title} · Part ${k + 1} of ${bounds.length - 1}`;
    const part: Script = { ...script, title: partTitle, chapters: slice };
    delete part.topics;
    if (k > 0) delete part.intro;               // the title card opens a later part
    if (!last) delete part.recap;               // the recap closes the lecture, in its last part
    return { index: k + 1, of: bounds.length - 1, script: part, minutes: Math.round(minutes * share * 10) / 10, title: partTitle };
  });
}
