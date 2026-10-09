// The drawing pass (lib/drawings.ts) against a stand-in for OpenRouter: each draw op becomes an SVG with the part
// ids the script promised (a missing one goes back to be fixed), a problem's figure too, the original script is
// left alone, a repeat is drawn from the cache, and a picture that never draws carries why.
//   npm run check:drawings
import http from "node:http";
import assert from "node:assert/strict";
import { existsSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";

const requests = [];
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", (d) => (body += d));
  req.on("end", () => {
    const ask = JSON.parse(body);
    requests.push(ask);
    const first = ask.messages[1].content;
    const parts = /PARTS \(each a <g id>, exactly these ids\): (.*)/.exec(first)[1].split(", ");
    let text;
    const latest = ask.messages.at(-1).content;
    if (Array.isArray(latest) && latest.some((p) => p.type === "image_url")) text = "LOOKS GOOD";   // the review
    else if (/IMPOSSIBLE/.test(first)) text = "I cannot draw that.";
    else {
      // The first answer forgets the last part; the repair has them all.
      const drawn = ask.messages.length === 2 ? parts.slice(0, -1) : parts;
      const groups = drawn.map((p, i) => `<g id="${p}"><rect x="${40 + i * 120}" y="80" width="90" height="60" ` +
        `fill="SAND" stroke="INK" stroke-width="4"/><text x="${85 + i * 120}" y="170" font-size="26" fill="INK" ` +
        `text-anchor="middle">${p}</text></g>`).join("");
      const moving = /MOVES: nothing/.test(first) ? "" : `<g id="extra"><circle cx="400" cy="40" r="10" fill="GOLD">` +
        `<animateTransform attributeName="transform" type="translate" values="0 0; 40 0; 0 0" dur="2s" ` +
        `repeatCount="indefinite" additive="sum"/></circle></g>`;
      text = "```svg\n<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 800 220\">" + groups + moving + "</svg>\n```";
    }
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ choices: [{ message: { content: text } }], usage: { cost: 0.002 } }));
  });
});
await new Promise((r) => server.listen(0, r));
process.env.OPENROUTER_URL = `http://127.0.0.1:${server.address().port}/v1/chat/completions`;
const { drawScript } = await import("../lib/drawings.ts");

const repo = path.resolve(process.cwd(), "..", "..");
rmSync(path.join(repo, "harness", "lecture", ".cache", "drawings"), { recursive: true, force: true });
const script = { chapters: [{ title: "Forces", beats: [
  { say: "A block rests on a slope.", do: [{ op: "draw", id: "ramp", what: "A block on a smooth 30 degree slope",
    parts: ["wedge", "block", "mg"], show: ["wedge", "block"] }] },
  { say: "Current flows round.", do: [{ op: "draw", id: "c", what: "A cell and a bulb in a closed loop of wire",
    parts: ["cell", "bulb"], moves: "current flows round the wire" }] },
  { say: "A problem.", do: [{ op: "problem", id: "p1", text: "Find a.", figure: { op: "draw",
    what: "A block on a smooth 30 degree slope", parts: ["wedge", "block", "mg"] } }] },
  { say: "Something odd.", do: [{ op: "draw", id: "x", what: "IMPOSSIBLE thing to draw here", parts: ["a"] }] },
] }] };
const before = JSON.stringify(script);
const options = { key: "test", model: "test/model", repo, python: path.join(repo, ".venv", "bin", "python"),
  onStatus: (t) => console.log("  ", t) };
const pictures = [];
const drawn = await drawScript(script, { ...options, onPicture: (p) => pictures.push(p) });
assert.equal(JSON.stringify(script), before);                         // the model's script is not touched
const beats = drawn.chapters[0].beats;
const ramp = beats[0].do[0], circuit = beats[1].do[0], figure = beats[2].do[0].figure, odd = beats[3].do[0];
assert.ok(ramp.svg && existsSync(ramp.svg));
assert.equal(figure.svg, ramp.svg);                                   // the same picture, drawn once
assert.ok(/<g id="mg">/.test(readFileSync(ramp.svg, "utf8")));        // the forgotten part, after the repair
assert.ok(/animateTransform/.test(readFileSync(circuit.svg, "utf8")));
assert.ok(!odd.svg && odd._draw_error, "a picture that never draws says why");
assert.equal(drawn.drawn, true);
// Each picture is reported with what it cost (its own requests, $0.002 each), and that is kept with the drawing.
const fresh = pictures.filter((p) => !p.kept);
assert.ok(fresh.some((p) => p.file === ramp.svg && p.usd > 0));
assert.ok(JSON.parse(readFileSync(ramp.svg.replace(/\.svg$/, ".json"), "utf8")).usd > 0);
// Each picture that passed was shown to the model as the board renders it (a PNG), once.
const reviews = requests.filter((r) => Array.isArray(r.messages.at(-1).content));
assert.equal(reviews.length, 2);
assert.match(reviews[0].messages.at(-1).content[1].image_url.url, /^data:image\/png;base64,/);
assert.ok(reviews.every((r) => r.model === "test/model"));
const asked = requests.length;
assert.equal(requests.filter((r) => r.messages.length === 2 && /smooth 30 degree/.test(r.messages[1].content)).length, 1);
const again = await drawScript(script, options);
assert.equal(again.chapters[0].beats[0].do[0].svg, ramp.svg);
assert.equal(requests.length, asked + 3);                             // only the undrawable one is asked again (3 rounds)
server.close();
console.log("ok: pictures drawn, repaired, shared, cached; failures reported");
