// Where a generation's or a build's time went, from its timing log (lib/timing.ts, harness/app/.logs).
//   node scripts/timing-report.mjs              the newest log
//   node scripts/timing-report.mjs <file>       that log
//   node scripts/timing-report.mjs build        the newest build log (gen: the newest generation log)
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const dir = process.env.PANIM_TIMING_DIR || path.join(process.cwd(), ".logs");
const arg = process.argv[2];
let file = arg && !["build", "gen"].includes(arg) ? arg : null;
if (!file) {
  const logs = readdirSync(dir).filter((f) => f.endsWith(".jsonl") && (!arg || f.includes(`-${arg}-`)))
    .map((f) => path.join(dir, f)).sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  if (!logs.length) {
    console.log(`no timing logs in ${dir}`);
    process.exit(1);
  }
  file = logs[0];
}
const events = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const clock = (s) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`);
const wall = (list) => {
  const spans = list.map((e) => [e.start, e.end]).sort((a, b) => a[0] - b[0]);
  let total = 0;
  let [from, to] = [0, 0];
  for (const [a, b] of spans) {
    if (a > to) {
      total += to - from;
      [from, to] = [a, b];
    } else to = Math.max(to, b);
  }
  return (total + to - from) / 1000;
};
const table = (rows, heads) => {
  const widths = heads.map((h, i) => Math.max(h.length, ...rows.map((r) => String(r[i]).length)));
  const line = (r) => r.map((c, i) => String(c).padEnd(widths[i])).join("  ");
  console.log(line(heads));
  for (const r of rows) console.log(line(r));
};

const start = Math.min(...events.map((e) => e.start));
const end = Math.max(...events.map((e) => e.end));
console.log(`${file}\n${events.length} steps over ${clock((end - start) / 1000)}\n`);

// Each kind: how many, the clock it covered (overlaps once), the sum of all its steps, the longest.
const kinds = new Map();
for (const e of events) kinds.set(e.kind, [...(kinds.get(e.kind) ?? []), e]);
table([...kinds].map(([kind, list]) => ({ kind, list, wall: wall(list) })).filter((k) => k.wall > 0)
  .sort((a, b) => b.wall - a.wall).map(({ kind, list, wall: w }) => [kind, list.length, clock(w),
    clock(list.reduce((t, e) => t + e.seconds, 0)), clock(Math.max(...list.map((e) => e.seconds)))]),
["kind", "steps", "on the clock", "summed", "longest"]);

// Sections: the model's time on each (transcript, chapters, lost tries), the slowest first.
const bySection = new Map();
for (const e of events) {
  if (e.section === undefined) continue;
  const row = bySection.get(e.section) ?? { transcript: 0, script: 0, stalled: 0, tries: 0 };
  if (e.kind in row) row[e.kind] += e.seconds;
  if (e.kind === "script") row.tries += 1;
  bySection.set(e.section, row);
}
if (bySection.size) {
  console.log("\nslowest sections (model time):");
  table([...bySection].sort((a, b) => (b[1].script + b[1].transcript + b[1].stalled) - (a[1].script + a[1].transcript + a[1].stalled))
    .slice(0, 10).map(([n, r]) => [n, clock(r.transcript), clock(r.script), r.tries, clock(r.stalled)]),
  ["section", "transcript", "chapters", "chapter tries", "lost to stalls"]);
}

// Pictures: requests by model, their average and longest, failures.
const pictures = events.filter((e) => e.kind === "picture-request" || e.kind === "picture-check");
if (pictures.length) {
  const byModel = new Map();
  for (const e of pictures) byModel.set(`${e.kind} ${e.model}`, [...(byModel.get(`${e.kind} ${e.model}`) ?? []), e]);
  console.log("\npicture requests:");
  table([...byModel].map(([k, list]) => [k, list.length, clock(list.reduce((t, e) => t + e.seconds, 0) / list.length),
    clock(Math.max(...list.map((e) => e.seconds))), list.filter((e) => e.error).length]),
  ["kind and model", "requests", "average", "longest", "failed"]);
}

// Narration: requests, refusals for the per-minute quota, seconds waiting them out.
for (const s of events.filter((e) => e.kind === "tts-summary")) {
  console.log(`\nnarration: ${s.requests} requests to ${s.engine}, ${s.threads} at a time, batches of up to ${s.batch_lines} lines; ` +
    `${s.rate_limited} hit the rate limit, ${clock(s.seconds_waiting_out_limits)} spent waiting it out; ` +
    `a request took ${s.average_request_seconds} s on average` + (s.batches ? `; batches ${JSON.stringify(s.batches)}` : ""));
}

console.log("\nslowest steps:");
for (const e of [...events].filter((e) => e.seconds > 0).sort((a, b) => b.seconds - a.seconds).slice(0, 20)) {
  const detail = Object.entries(e).filter(([k]) => !["kind", "start", "end", "seconds"].includes(k))
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ").slice(0, 160);
  console.log(`  ${clock(e.seconds).padStart(10)}  ${e.kind.padEnd(16)} ${detail}`);
}
