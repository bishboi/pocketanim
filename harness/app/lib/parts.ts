/**
 * A long lecture as more than one video. A lecture written as a series of micro-lectures (topics.ts) is cut where
 * its topics meet (splitByTopics): each part a 20-30 minute lecture of its own. One without a plan (no transcript)
 * that runs past PANIM_MAX_VIDEO_MINUTES (30) is cut, between chapters, into the fewest parts that each stay under
 * it, as even as the chapters allow (splitLecture). Each part is a lecture script of its own.
 */

import { microMinutes } from "./topics";

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
  const chapters = Array.isArray(script.chapters) ? script.chapters : [];
  if (!(minutes > limit) || chapters.length < 2) return [];
  const count = Math.min(chapters.length, Math.ceil(minutes / limit));
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
