"use client";

import type { GoalStatus, PlanView } from "@/lib/storyplan";

/**
 * A book lecture's plan as it was made before writing (lib/learningmap.ts, lib/storyplan.ts): each video's story
 * (its big question, running example, arc, opening and closing), each section's part in it (where it picks up,
 * what it hands on, its guess-first question, the book's questions it asks), and the learning goals each section
 * teaches with where each stands (the coverage check). It fills in live while the lecture is written.
 */

const STATUS: Record<GoalStatus, { label: string; tone: string }> = {
  waiting: { label: "not written yet", tone: "border-neutral-700 text-neutral-400" },
  taught: { label: "taught", tone: "border-emerald-700 bg-emerald-950/60 text-emerald-300" },
  patched: { label: "written in after", tone: "border-amber-700 bg-amber-950/60 text-amber-300" },
  missing: { label: "missing", tone: "border-red-700 bg-red-950/60 text-red-300" },
};

const KINDS: Record<string, string> = { heading: "heading", term: "term", aside: "box", figure: "figure" };

export function LecturePlan({ plan }: { plan: PlanView }) {
  const { coverage } = plan;
  const done = coverage.taught + coverage.patched;
  const goalsOf = (n: number) => plan.goals.filter((g) => g.section === n);
  const inVideos = new Set(plan.videos.flatMap((v) => v.sections.map((s) => s.section)));
  const loose = plan.sections.filter((n) => !inVideos.has(n) && goalsOf(n).length);
  return (
    <details open className="rounded border border-neutral-800 bg-neutral-950 text-xs" data-testid="lecture-plan">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm text-neutral-200">
        Lecture plan
        <span className="text-xs text-neutral-500">
          {" "}· {plan.goals.length} learning goals{plan.videos.length ? ` · ${plan.videos.length} video${plan.videos.length > 1 ? "s" : ""}` : ""}
          {" "}· coverage {done} of {coverage.planned}
          {coverage.patched ? ` (${coverage.patched} written in after)` : ""}
          {coverage.missing ? `, ${coverage.missing} missing` : ""}
        </span>
        <button type="button" className="ml-3 text-xs text-neutral-400 underline-offset-2 hover:underline"
          onClick={(e) => {
            e.preventDefault();
            const url = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = "lecture-plan.json";
            link.click();
            URL.revokeObjectURL(url);
          }}>
          download
        </button>
      </summary>
      <div className="flex flex-col gap-3 px-3 pb-3">
        {plan.videos.map((video) => (
          <section key={video.index} className="rounded border border-neutral-800 bg-neutral-900 p-3" data-testid="plan-video">
            <p className="text-[10px] uppercase tracking-wide text-neutral-500">Video {video.index} of {video.of}</p>
            <p className="mt-1 text-sm font-semibold text-neutral-100">{video.bigQuestion}</p>
            <dl className="mt-2 grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1 text-neutral-300">
              {video.runningExample && (<><dt className="text-neutral-500">Running example</dt><dd>{video.runningExample}</dd></>)}
              {video.arc && (<><dt className="text-neutral-500">Arc</dt><dd>{video.arc}</dd></>)}
              {video.opening && (<><dt className="text-neutral-500">Opens with</dt><dd>{video.opening}</dd></>)}
            </dl>
            <ol className="mt-3 flex flex-col gap-2">
              {video.sections.map((s) => (
                <li key={s.section} className="rounded border border-neutral-800 bg-neutral-950 p-2">
                  <p className="text-neutral-200"><span className="font-semibold">Section {s.section}</span>
                    {s.opensFrom && <span className="text-neutral-400"> · picks up from “{s.opensFrom}”</span>}
                  </p>
                  {s.guessFirst && <p className="mt-1 text-sky-300">Guess first: {s.guessFirst}</p>}
                  <Goals goals={goalsOf(s.section)} />
                  {s.questions.length > 0 && (
                    <div className="mt-1 text-neutral-400">
                      <span className="text-neutral-500">Book questions asked here:</span>
                      <ul className="ml-4 list-disc">{s.questions.map((q) => <li key={q}>{q}</li>)}</ul>
                    </div>
                  )}
                  {s.handsOn && <p className="mt-1 text-neutral-400">Ends on: “{s.handsOn}”</p>}
                </li>
              ))}
            </ol>
            {video.closing && <p className="mt-2 text-neutral-300"><span className="text-neutral-500">Closes with: </span>{video.closing}</p>}
          </section>
        ))}
        {loose.map((n) => (
          <section key={n} className="rounded border border-neutral-800 bg-neutral-900 p-2">
            <p className="font-semibold text-neutral-200">Section {n}</p>
            <Goals goals={goalsOf(n)} />
          </section>
        ))}
      </div>
    </details>
  );
}

function Goals({ goals }: { goals: PlanView["goals"] }) {
  if (!goals.length) return null;
  return (
    <ul className="mt-2 flex flex-col gap-1.5">
      {goals.map((g) => (
        <li key={g.id} className="flex flex-col gap-0.5" data-testid="plan-goal">
          <div className="flex items-start gap-2">
            <span className={`shrink-0 rounded border px-1.5 py-px text-[10px] ${STATUS[g.status].tone}`}>{STATUS[g.status].label}</span>
            <span className="text-neutral-100">{g.goal}{g.added ? <span className="text-neutral-500"> (added for items the map left out)</span> : null}</span>
          </div>
          {g.items.length > 0 && (
            <div className="ml-1 flex flex-wrap gap-1">
              {g.items.map((item, k) => (
                <span key={k} className="rounded bg-neutral-800 px-1.5 py-px text-[10px] text-neutral-300">
                  <span className="text-neutral-500">{KINDS[item.kind] ?? item.kind}:</span> {item.text}
                </span>
              ))}
            </div>
          )}
          {(g.misconception || g.hook) && (
            <p className="ml-1 text-neutral-500">
              {g.misconception && <>Wrong idea to clear up: <span className="text-neutral-400">{g.misconception}</span></>}
              {g.misconception && g.hook ? " · " : ""}
              {g.hook && <>Hook: <span className="text-neutral-400">{g.hook}</span></>}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
