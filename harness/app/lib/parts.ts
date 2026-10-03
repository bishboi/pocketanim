/**
 * A lecture longer than an hour, as more than one video. A 90-minute lecture in one file was too long to watch in
 * a sitting, to build in one go, or to play in a browser tab; so a written lecture that runs past
 * PANIM_MAX_VIDEO_MINUTES (60) is cut, between chapters, into the fewest parts that each stay under it, as even as
 * the chapters allow. Each part is a lecture script of its own: the first keeps the opening, the last the recap,
 * every one the credits.
 */

type Script = Record<string, unknown> & { title?: unknown; chapters?: unknown; recap?: unknown; intro?: unknown };

export type LecturePart = { index: number; of: number; script: Script; minutes: number; title: string };

/** The longest video, in minutes, before a lecture is split (PANIM_MAX_VIDEO_MINUTES). */
export function maxVideoMinutes(): number {
  const set = Number(process.env.PANIM_MAX_VIDEO_MINUTES);
  return Number.isFinite(set) && set > 0 ? set : 60;
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
    if (k > 0) delete part.intro;               // the title card opens a later part
    if (!last) delete part.recap;               // the recap closes the lecture, in its last part
    return { index: k + 1, of: bounds.length - 1, script: part, minutes: Math.round(minutes * share * 10) / 10, title: partTitle };
  });
}
