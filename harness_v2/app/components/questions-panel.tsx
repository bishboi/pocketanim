"use client";

/**
 * The Questions tab: hard multiple-choice questions on each chapter's video (lib/questions.ts), in English and Hindi,
 * each with where in the video its answer is taught; that moment plays here.
 */

import { useEffect, useState } from "react";
import type { ChapterQuestions, Question, QuestionText, Run } from "@/lib/types";
import { IRPlayer } from "./player";

type Act = (body: Record<string, unknown>) => Promise<boolean>;
type Lang = "both" | "en" | "hi";

const SOURCE: Record<ChapterQuestions["source"], string> = {
  voice: "times in the narrated chapter (Voice tab)",
  scenes: "times in the chapter render (Scenes tab)",
  none: "no video rendered yet: no times",
};

function clock(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function Text({ t, answer, reveal, lang }: { t: QuestionText; answer: number; reveal: boolean; lang: "en" | "hi" }) {
  return (
    <div className="space-y-1" lang={lang}>
      <p className="text-sm text-neutral-100">{t.question}</p>
      <ol className="space-y-0.5 text-sm">
        {t.options.map((o, k) => (
          <li key={k} className={`rounded px-2 py-0.5 ${reveal && k === answer ? "bg-emerald-900/60 text-emerald-100" : "text-neutral-300"}`}>
            <span className="mr-1 font-mono text-neutral-500">{"ABCD"[k]}.</span>{o}
          </li>
        ))}
      </ol>
      {reveal && t.explanation && <p className="whitespace-pre-line text-xs text-neutral-400">{t.explanation}</p>}
    </div>
  );
}

function QuestionCard({ q, i, lang, all, onPlay }: { q: Question; i: number; lang: Lang; all: boolean; onPlay?: () => void }) {
  const [reveal, setReveal] = useState(false);
  useEffect(() => setReveal(all), [all]);
  return (
    <li className="space-y-2 rounded border border-neutral-800 bg-neutral-950 p-3" data-testid="question">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="font-semibold text-neutral-200">Q{i + 1}</span>
        <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-300">{q.skill}</span>
        {q.at ? (
          <button onClick={onPlay} disabled={!onPlay} data-testid="question-at"
            className="rounded border border-amber-700 px-1.5 py-0.5 text-amber-300 hover:bg-amber-950 disabled:opacity-60"
            title={`Taught in beat${q.beats.length > 1 ? "s" : ""} ${q.beats.join(", ")}: play that moment`}>
            ▶ {clock(q.at.start)}–{clock(q.at.end)}
          </button>
        ) : <span className="text-neutral-500">beat{q.beats.length > 1 ? "s" : ""} {q.beats.join(", ")}</span>}
        <button onClick={() => setReveal(!reveal)} className="ml-auto text-neutral-400 hover:text-neutral-200">{reveal ? "hide answer" : "show answer"}</button>
      </div>
      <div className={lang === "both" ? "grid gap-3 md:grid-cols-2" : ""}>
        {lang !== "hi" && <Text t={q.en} answer={q.answer} reveal={reveal} lang="en" />}
        {lang !== "en" && <Text t={q.hi} answer={q.answer} reveal={reveal} lang="hi" />}
      </div>
    </li>
  );
}

export function QuestionsPanel({ run, defaultModel, onCall, act }: { run: Run; defaultModel: string; onCall: (id: string) => void; act: Act }) {
  const scripted = run.lectures.filter((l) => run.script?.lectures[l.n]?.status === "done");
  const [lecture, setLecture] = useState<number | undefined>(scripted[0]?.n);
  const [count, setCount] = useState(run.questions?.count ?? 8);
  const [model, setModel] = useState(run.questions?.model ?? "");
  const [lang, setLang] = useState<Lang>("both");
  const [all, setAll] = useState(false);
  const [playing, setPlaying] = useState<{ chapter: number; q: Question } | null>(null);
  useEffect(() => { if (lecture === undefined && scripted.length) setLecture(scripted[0].n); }, [scripted.length]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!scripted.length) return <p className="text-sm text-neutral-400">No lecture is scripted yet: questions are written from a chapter's narration, once it has a video.</p>;
  const ls = lecture !== undefined ? run.script?.lectures[lecture] : undefined;
  const got = (lecture !== undefined && run.questions?.lectures[lecture]) || {};
  const total = Object.values(got).reduce((k, c) => k + c.questions.length, 0);
  const cost = run.calls.filter((c) => c.step === "questions").reduce((k, c) => k + c.cost, 0);
  const generate = (chapter?: number) => act({ action: "generate", lecture, chapter, count, model });
  const download = () => {
    const blob = new Blob([JSON.stringify({ lecture, chapters: got }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `questions-lecture-${lecture}.json`;
    a.click();
  };
  const sel = "rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 text-neutral-200";
  const video = playing ? got[playing.chapter]?.video : undefined;
  return (
    <div className="space-y-4" data-testid="questions-panel">
      <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-300">
        <label className="flex items-center gap-1">Lecture
          <select className={sel} value={lecture} onChange={(e) => { setLecture(Number(e.target.value)); setPlaying(null); }}>
            {scripted.map((l) => <option key={l.n} value={l.n}>{l.n}. {l.title}</option>)}
          </select></label>
        <label className="flex items-center gap-1" title="Questions written for each chapter">Questions a chapter
          <input type="number" min={2} max={15} value={count} onChange={(e) => setCount(Number(e.target.value))} className={`${sel} w-14`} /></label>
        <label className="flex items-center gap-1">Model
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={defaultModel} className={`${sel} w-56`} /></label>
        <button onClick={() => generate()} className="rounded bg-amber-500 px-2.5 py-1 font-semibold text-black" data-testid="questions-generate">
          Write questions for every chapter</button>
        <span className="ml-auto flex items-center gap-1">
          {(["both", "en", "hi"] as Lang[]).map((l) => (
            <button key={l} onClick={() => setLang(l)} className={`rounded px-2 py-0.5 ${lang === l ? "bg-neutral-700 text-white" : "text-neutral-400"}`}>
              {l === "both" ? "Both" : l === "en" ? "English" : "हिंदी"}</button>))}
          <label className="ml-2 flex items-center gap-1"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> answers</label>
          {total > 0 && <button onClick={download} className="ml-2 rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800">Download JSON</button>}
        </span>
      </div>
      <p className="text-[11px] text-neutral-500">
        Hard, judgment-based questions (apply, analyse, evaluate, infer), four options each, in English and Hindi, written
        from each chapter&apos;s narration. The time on each is where its answer is taught in the chapter&apos;s video; press it to play that
        moment. {total} question(s) in this lecture{cost ? `, $${cost.toFixed(3)} so far` : ""}.
      </p>
      {playing && video && (
        <div className="space-y-1 rounded border border-amber-800 p-2">
          <div className="flex items-center text-xs text-amber-200">
            <span>Chapter {playing.chapter}, Q: where it is taught ({clock(playing.q.at!.start)}–{clock(playing.q.at!.end)})</span>
            <button onClick={() => setPlaying(null)} className="ml-auto text-neutral-400 hover:text-neutral-200">close</button>
          </div>
          <IRPlayer key={`${playing.q.id}`} src={video.ir} assets={video.assets} audio={video.audio} autoPlay
            range={playing.q.at!.from !== undefined && playing.q.at!.to !== undefined ? [playing.q.at!.from, playing.q.at!.to]
              : [Math.round(playing.q.at!.start * (video.fps ?? 30)), Math.round(playing.q.at!.end * (video.fps ?? 30))]} />
        </div>
      )}
      {(ls?.chapters ?? []).map((ch) => {
        const cq = got[ch.n];
        return (
          <section key={ch.n} className="space-y-2" data-testid={`questions-chapter-${ch.n}`}>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <h3 className="font-semibold text-neutral-100">Chapter {ch.n}. {ch.title}</h3>
              {cq && <span className={`text-[11px] ${cq.status === "failed" ? "text-red-300" : cq.status === "running" ? "text-sky-300" : "text-neutral-500"}`}>
                {cq.status === "running" ? "writing…" : cq.status === "failed" ? `failed: ${cq.error}` : `${cq.questions.length} question(s), ${SOURCE[cq.source]}`}</span>}
              {cq?.calls.map((id) => <button key={id} onClick={() => onCall(id)} className="text-[11px] text-sky-400 hover:underline">call</button>)}
              <button onClick={() => generate(ch.n)} disabled={cq?.status === "running"}
                className="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-50">
                {cq ? "Write again" : "Write questions"}</button>
            </div>
            {cq?.notes?.length ? <ul className="text-[11px] text-amber-300/80">{cq.notes.map((n, k) => <li key={k}>{n}</li>)}</ul> : null}
            {cq?.questions.length ? (
              <ol className="space-y-2">
                {cq.questions.map((q, i) => (
                  <QuestionCard key={q.id} q={q} i={i} lang={lang} all={all}
                    onPlay={cq.video && q.at ? () => setPlaying({ chapter: ch.n, q }) : undefined} />
                ))}
              </ol>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
