// The lectures already built, drawn again by the motion engine (beta: engine/MOTION_ENGINE.md), beside what they
// made, never over it: each lecture's beat script (as the Scenes tab compiles it) is compiled on the motion engine
// into .data/runs/<run>/scenes/motion/<look>/L<n>/ (script.json, scene.py, report.json). The runs, their scenes and
// everything rendered before are only read.
//   node --experimental-strip-types --import ./scripts/ts-resolve.mjs scripts/motion-rerun.mjs [run id...] [--look paper]
import { mkdirSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const here = import.meta.dirname;
process.env.V2_PYTHON ??= path.resolve(here, "../../../.venv/bin/python");
process.env.V2_ENGINE ??= path.resolve(here, "../../engine");
const args = process.argv.slice(2);
const lookAt = args.indexOf("--look");
const look = lookAt >= 0 ? args[lookAt + 1] : undefined;
const wanted = args.filter((a, i) => !a.startsWith("--") && i !== lookAt + 1);

const { loadRun } = await import(path.resolve(here, "../lib/store.ts"));
const { engineScript, compile, scenesDir } = await import(path.resolve(here, "../lib/scenes.ts"));
const { cleanLook } = await import(path.resolve(here, "../lib/styles.ts"));

const ids = wanted.length ? wanted : readdirSync(path.resolve(".data", "runs")).filter((f) => f.endsWith(".json")).map((f) => f.slice(0, -5));
const rows = [];
for (const id of ids) {
  const run = await loadRun(id);
  if (!run?.scenes?.lectures) continue;
  for (const [key, sl] of Object.entries(run.scenes.lectures)) {
    const n = Number(key);
    const built = Object.values(sl.beats ?? {}).filter((b) => b?.ops?.length).length;
    if (!built || !run.script?.lectures?.[n]) continue;
    const script = await engineScript(run, n, cleanLook(run.scenes.look));
    // Only the chapters whose beats are built: the rest have nothing to draw yet.
    script.chapters = script.chapters.filter((c) => c.beats.some((b) => b.do?.length));
    Object.assign(script, { engine: "motion", ...(look ? { look } : {}) });
    const dir = path.join(scenesDir(run.id), "motion", look ?? "own", `L${n}`);
    mkdirSync(dir, { recursive: true });
    writeFileSync(path.join(dir, "script.json"), JSON.stringify(script, null, 2));
    const out = await compile(run, script, dir, n);
    if (out.source) writeFileSync(path.join(dir, "scene.py"), out.source);
    const row = { run: id, lecture: n, title: run.lectures.find((l) => l.n === n)?.title, chapters: script.chapters.length,
      beats: script.chapters.reduce((k, c) => k + c.beats.length, 0), ok: !!out.source && !out.errors.length,
      errors: out.errors, warnings: out.warnings.filter((w) => !/no reusable illustration/.test(w)), dir };
    writeFileSync(path.join(dir, "report.json"), JSON.stringify(row, null, 2));
    rows.push(row);
    console.log(`${row.ok ? "ok  " : "FAIL"} ${id} L${n} "${row.title}": ${row.chapters} chapters, ${row.beats} beats` +
      `${row.errors.length ? `; errors: ${row.errors.join(" | ").slice(0, 300)}` : ""}${row.warnings.length ? `; ${row.warnings.length} notes` : ""}`);
  }
}
console.log(`${rows.filter((r) => r.ok).length} of ${rows.length} lectures compile on the motion engine${look ? ` (look: ${look})` : ""}`);
