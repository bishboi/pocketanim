// The free-form Manim blocks written by their own model (lib/manimcoder.ts) against a stand-in OpenRouter: every
// figure at once, one request each with all its beats; the plan leaves the op once its code is in; a script asked
// again asks nothing; a refused block goes back with the reason; a figure the model cannot write is left out.
//   node --experimental-strip-types --import ./scripts/ts-resolve.mjs scripts/check-manim.mjs
import http from "node:http";
import assert from "node:assert/strict";

const asked = [];
let busy = 0;
let most = 0;
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", (d) => (body += d));
  req.on("end", async () => {
    const request = JSON.parse(body);
    const text = request.messages[1].content[0].text;
    asked.push({ model: request.model, text, system: request.messages[0].content });
    busy += 1;
    most = Math.max(most, busy);
    await new Promise((r) => setTimeout(r, 150));
    busy -= 1;
    const beats = (text.match(/^Beat \d+ says/gm) ?? []).length;
    const id = /figure's id: (\w+)/.exec(text)[1];
    const blocks = id === "broken" ? ["only one"].concat([]).slice(0, beats - 1)
      : Array.from({ length: beats }, (_, k) => `${text.includes("refused") ? "fixed" : "made"}_${id}_${k} = Dot()`);
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify({ blocks }) } }],
      usage: { cost: 0.002, prompt_tokens: 100, completion_tokens: 50 } }));
  });
});
await new Promise((r) => server.listen(0, r));
process.env.OPENROUTER_URL = `http://127.0.0.1:${server.address().port}/v1/chat/completions`;
const { fillManim, repairManim, needsManim } = await import("../lib/manimcoder.ts");

const script = () => ({ chapters: [{ beats: [
  { say: "A block rests on a wedge.", do: [{ op: "manim", id: "wedge", plan: "a wedge at 30 degrees, a block on it" }] },
  { say: "Its weight acts down.", do: [{ op: "manim", id: "wedge", plan: "a ROSE arrow down from the block, mg" }] },
  { say: "Light bends at the lens.", do: [{ op: "manim", id: "lens", plan: "a convex lens, three rays" }] },
  { say: "A figure it cannot write.", do: [{ op: "manim", id: "broken", plan: "something" }] },
] }] });
let spent = 0;
const options = { key: "k", model: "test/manim-coder", style: "lab", onCost: (usd) => (spent += usd) };
const first = script();
assert.ok(needsManim(first));
const result = await fillManim(first, options);
const beats = first.chapters[0].beats;
assert.equal(beats[0].do[0].code, "made_wedge_0 = Dot()");
assert.equal(beats[1].do[0].code, "made_wedge_1 = Dot()");                 // one request for both beats of a figure
assert.equal(beats[2].do[0].code, "made_lens_0 = Dot()");
assert.ok(!("plan" in beats[0].do[0]));                                      // the plan leaves once the code is in
assert.deepEqual(beats[3].do, []);                                            // left out after two tries
assert.deepEqual(result.dropped, ["broken"]);
assert.equal(asked.filter((a) => a.text.includes("id: wedge")).length, 1);
assert.ok(asked[0].text.includes("a ROSE arrow down from the block") && asked[0].system.includes("board: x from -6.9"));
assert.ok(most > 1, "figures are written at once");
assert.ok(!needsManim(first));
// The same plans again (a copy of the script): written from what was written, nothing asked.
const before = asked.length;
const again = script();
await fillManim(again, options);
assert.equal(asked.length - before + 0, 2);                                   // only the broken one is asked again
assert.equal(again.chapters[0].beats[2].do[0].code, "made_lens_0 = Dot()");
// A refused block goes back to the Manim model with the reason and its plan, not to the section.
const fixed = await repairManim(first, ["chapter 1 beat 2: the manim block 'wedge' failed: NameError: mg"], options);
assert.equal(fixed, 1);
const repair = asked[asked.length - 1].text;
assert.ok(repair.includes("NameError: mg") && repair.includes("made_wedge_1") && repair.includes("ROSE arrow"));
assert.equal(first.chapters[0].beats[1].do[0].code, "fixed_wedge_1 = Dot()");
assert.ok(spent > 0);
server.close();
console.log("ok: Manim figures written by their own model, at once, repaired with the reason, left out when they cannot be");
