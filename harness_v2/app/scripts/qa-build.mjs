// The QA loop's test chapters, made as the app makes them (engine/tools/chapter_qa.py judges them): a source PDF read,
// its lectures written, each chapter spoken and aligned (voice first), its scenes written in a look; then
// each chapter's beat script saved to engine/examples/qa/<name>-L<n>-c<k>.json, as the Scenes tab compiles it.
// Uses the models and voice the environment names (OPENROUTER_API_KEY, GEMINI_API_KEY, ...); its runs are kept in
// the working directory's .data, so run it from a scratch folder, not the app's.
//   node --experimental-strip-types --import <app>/scripts/ts-resolve.mjs <app>/scripts/qa-build.mjs <source.pdf>...
//     [--minutes 4] [--language hinglish] [--look paper] [--out <dir>]
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const here = import.meta.dirname;
process.env.V2_PYTHON ??= path.resolve(here, "../../../.venv/bin/python");
process.env.V2_ENGINE ??= path.resolve(here, "../../engine");
const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const at = args.indexOf(`--${name}`);
  return at >= 0 ? args[at + 1] : fallback;
};
const valued = new Set(["--minutes", "--language", "--look", "--out"]);
const sources = args.filter((a, i) => !a.startsWith("--") && !valued.has(args[i - 1]));
const minutes = Number(opt("minutes", "4"));
const language = opt("language", "hinglish");
const look = opt("look", "paper");
const out = path.resolve(opt("out", path.resolve(here, "../../engine/examples/qa")));
mkdirSync(out, { recursive: true });

const { addDocument } = await import(path.resolve(here, "../lib/docs.ts"));
const { startRun } = await import(path.resolve(here, "../lib/run.ts"));
const { loadRun } = await import(path.resolve(here, "../lib/store.ts"));
const { scenesAction, engineScript } = await import(path.resolve(here, "../lib/scenes.ts"));
const { cleanLook } = await import(path.resolve(here, "../lib/styles.ts"));

const until = async (id, busy, minutesMost = 60) => {
  for (let i = 0; i < minutesMost * 60; i++) {
    const r = await loadRun(id);
    if (!busy(r)) return r;
    await new Promise((res) => setTimeout(res, 1000));
  }
  throw new Error(`run ${id}: still busy after ${minutesMost} minutes`);
};
const cost = (run) => run.calls.reduce((k, c) => k + (c.cost ?? 0), 0);

const made = [];
for (const source of sources) {
  const name = path.basename(source, path.extname(source));
  const t0 = Date.now();
  const doc = await addDocument(path.basename(source), new Uint8Array(readFileSync(source)));
  let run = await startRun(doc.id, { lectureMinutes: minutes, language });
  run = await until(run.id, (r) => r.status === "running");
  if (run.status !== "done") {
    console.error(`${name}: the lecture was not written: ${run.error}`);
    continue;
  }
  await scenesAction(run.id, { action: "motion", look });
  for (const lecture of run.lectures) {
    await scenesAction(run.id, { action: "build", scope: "lecture", lecture: lecture.n });
    run = await until(run.id, (r) => r.scenes?.status === "running", 120);
    const sl = run.scenes.lectures[lecture.n];
    if (sl?.status !== "done") {
      console.error(`${name} L${lecture.n}: scenes not built: ${sl?.error}`);
      continue;
    }
    for (const ch of run.script.lectures[lecture.n].chapters) {
      const script = await engineScript(run, lecture.n, cleanLook(run.scenes.look), { chapter: ch.n });
      script.qa = { source: path.basename(source), run: run.id, lecture: lecture.n, chapter: ch.n, language, look };
      const file = path.join(out, `${name}-L${lecture.n}-c${ch.n}.json`);
      writeFileSync(file, JSON.stringify(script, null, 1));
      made.push(file);
    }
  }
  console.log(`${name}: run ${run.id}, ${run.lectures.length} lecture(s), $${cost(run).toFixed(3)}, ${((Date.now() - t0) / 60000).toFixed(1)} min`);
}
console.log(JSON.stringify({ made }));
