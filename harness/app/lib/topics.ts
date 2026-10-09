/**
 * A long lecture as a series of micro-lectures, one per topic: videos of 20-30 minutes (PANIM_MICRO_MINUTES, 25 by
 * default), each watched on its own. An hour-long video cut where the minutes ran out ended one part mid-topic and
 * began the next with no opening and no recap; a topic is the unit a student sits down to learn.
 *
 * The plan is made from the transcript's sections before a word is written, so each micro-lecture is written as
 * one (transcript.ts): its first section opens it (what it covers, what came before, what the student will be able
 * to do) and its last closes it (the key points, questions to check yourself, what comes next). The video's
 * chapters keep their section, so the finished lecture is cut exactly at those boundaries (parts.ts), each part
 * with its own title, opening and recap.
 */

import type { Section } from "./transcript";

export type Topic = {
  /** 1-based, in order. */
  index: number;
  of: number;
  /** The transcript sections it is made of, in order. */
  sections: number[];
  minutes: number;
  /** The book's heading where the topic starts, or the first section's title once written. */
  title: string;
};

/** The length a micro-lecture aims for, and the range it may take (PANIM_MICRO_MINUTES; 25 gives 20-30). */
export function microMinutes(): { target: number; min: number; max: number } {
  const set = Number(process.env.PANIM_MICRO_MINUTES);
  const target = Number.isFinite(set) && set >= 5 ? set : 25;
  return { target, min: Math.max(3, target - 5), max: target + 5 };
}

/** The most videos one lecture is made as (PANIM_MAX_VIDEOS, 15): a whole book in micro-lectures of 20-30 min. */
export function maxVideos(): number {
  const set = Number(process.env.PANIM_MAX_VIDEOS);
  return Number.isFinite(set) && set >= 1 ? Math.round(set) : 15;
}

/** The longest lecture, in minutes, that maxVideos micro-lectures hold at their target length. */
export function maxSeriesMinutes(): number {
  return maxVideos() * microMinutes().target;
}

/** What opening and closing a micro-lecture adds to its sections' teaching (model.ts gives each 150 words more). */
export const OPEN_CLOSE_MINUTES = 3;

/** The first markdown heading in a section's book text, cleaned, or "". */
function headingOf(section: Section): string {
  const found = /^#{1,6}\s+(.+)$/m.exec(section.source ?? "");
  if (!found) return "";
  return found[1].replace(/[*_`]/g, "").replace(/\s+/g, " ").trim().slice(0, 80);
}

/** Whether a section begins at one of the book's headings: the natural place for a new lecture to start. */
function startsAtHeading(section: Section): boolean {
  return /^\s*#{1,6}\s+\S/.test(section.source ?? "");
}

/**
 * The sections grouped into micro-lectures, in order, as even as the sections allow and each within the range
 * where it can be. One topic when the whole lecture fits in one video. A section of only the book's questions stays
 * with the teaching before it; a cut prefers a section that starts at a book heading.
 */
export function planTopics(sections: Section[], range = microMinutes()): Topic[] {
  const total = sections.reduce((n, s) => n + s.minutes, 0);
  if (!sections.length) return [];
  if (total <= range.max || sections.length < 2) {
    return [{ index: 1, of: 1, sections: sections.map((s) => s.n), minutes: total, title: headingOf(sections[0]) }];
  }
  // As many lectures as keep each, with its own opening and close (OPEN_CLOSE_MINUTES), inside the range and
  // nearest the target; when none fits, the fewest that stay under its top.
  const length = (count: number) => total / count + OPEN_CLOSE_MINUTES;
  let count = 0;
  const most = Math.min(sections.length, maxVideos());
  for (let k = 2; k <= most; k++) {
    const fits = length(k) <= range.max && length(k) >= range.min;
    if (fits && (!count || Math.abs(length(k) - range.target) < Math.abs(length(count) - range.target))) count = k;
  }
  if (!count) {
    count = 2;
    while (count < most && length(count) > range.max) count++;
  }
  // Where each cut may go (before section i), and what the running total is there.
  const before: number[] = [];
  let run = 0;
  for (const s of sections) {
    before.push(run);
    run += s.minutes;
  }
  const cuts: number[] = [];
  let from = 1;
  for (let k = 1; k < count; k++) {
    const want = (total * k) / count;
    let best = -1;
    let bestCost = Infinity;
    // Leave at least one section for every lecture still to come.
    for (let i = from; i <= sections.length - (count - k); i++) {
      if (sections[i].questionsOnly) continue;
      const cost = Math.abs(before[i] - want) - (startsAtHeading(sections[i]) ? range.target * 0.12 : 0);
      if (cost < bestCost) {
        bestCost = cost;
        best = i;
      }
    }
    if (best < 0) break;
    cuts.push(best);
    from = best + 1;
  }
  const bounds = [0, ...cuts, sections.length];
  const groups = bounds.slice(0, -1).map((start, k) => sections.slice(start, bounds[k + 1]));
  return groups.map((group, k) => ({
    index: k + 1,
    of: groups.length,
    sections: group.map((s) => s.n),
    minutes: Math.round(group.reduce((n, s) => n + s.minutes, 0) * 10) / 10,
    title: headingOf(group[0]),
  }));
}

/** The topic a section belongs to, or undefined (one topic, or no plan). */
export function topicOf(topics: Topic[], n: number): Topic | undefined {
  return topics.length > 1 ? topics.find((t) => t.sections.includes(n)) : undefined;
}

/** A topic's place in its series, for the prompts: "lecture 2 of 4, "Work and energy"". */
export function topicLabel(topic: Topic): string {
  return `micro-lecture ${topic.index} of ${topic.of}${topic.title ? `, "${topic.title}"` : ""}`;
}
