/**
 * Does the browser renderer draw what the oracle draws?
 *
 * `lib/draw.ts` is a fourth implementation of this format's rasterising, after
 * Cairo, Java2D and Skia. The other three are checked against each other; this
 * checks the new one the same way, because a preview that disagrees with the
 * phone is worse than no preview.
 *
 * It renders frames headlessly through the shipped `drawFrame` and compares
 * them with `exporter/reference_render.py` at the same size.
 *
 * What this proves and what it does not: node-canvas is Cairo, and so is the
 * oracle, so an exact match here is a statement about the *drawing logic* --
 * subpath splitting, when a subpath closes, fill and stroke order, the scene
 * to pixel transform. It says nothing about how a real browser's Canvas2D
 * rasterises, exactly as `tools/verify_player.py` can say nothing about Skia.
 *
 *   node scripts/check-draw.cjs <ir.json> <build_dir> <SceneClass> [frames...]
 */

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { createCanvas, loadImage } = require("canvas");
const ts = require("typescript");

const APP = path.join(__dirname, "..");
const REPO = path.join(APP, "..", "..");
const WIDTH = 480;
const HEIGHT = 270;

function loadDraw() {
  const source = fs.readFileSync(path.join(APP, "lib", "draw.ts"), "utf8");
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const box = { exports: {} };
  new Function("exports", "require", "module", js)(box.exports, require, box);
  return box.exports.drawFrame;
}

function python() {
  const venv = path.join(REPO, ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : "python3";
}

function oracleFrame(buildDir, sceneClass, n, out) {
  const script = `
import sys
sys.path.insert(0, ${JSON.stringify(REPO)})
from dsl.interpret import load_program
from exporter.reference_render import render_frame
from PIL import Image
ir = load_program("dsl/generated/${sceneClass}.panim")
Image.fromarray(render_frame(ir, ${n}, ${WIDTH}, ${HEIGHT})).save(${JSON.stringify(out)})
`;
  execFileSync(python(), ["-c", script], { cwd: buildDir });
}

async function main() {
  const [irPath, buildDir, sceneClass, ...rest] = process.argv.slice(2);
  if (!irPath || !buildDir || !sceneClass) {
    console.error("usage: check-draw.cjs <ir.json> <build_dir> <SceneClass> [frames...]");
    return 2;
  }
  const ir = JSON.parse(fs.readFileSync(irPath, "utf8"));
  if (ir.mode !== "2d") {
    console.log(`skipped: ${sceneClass} is ${ir.mode}, which the browser does not draw`);
    return 0;
  }
  const drawFrame = loadDraw();
  const frames = rest.length
    ? rest.map(Number)
    : [0, ir.frames.length >> 2, ir.frames.length >> 1, ir.frames.length - 1];

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "panim-draw-"));
  let worst = 0;
  for (const n of frames) {
    const canvas = createCanvas(WIDTH, HEIGHT);
    drawFrame(canvas.getContext("2d"), ir.shapes, ir.frames[n] || [], WIDTH, HEIGHT);

    const oraclePath = path.join(tmp, `oracle_${n}.png`);
    oracleFrame(buildDir, sceneClass, n, oraclePath);
    const oracle = await loadImage(oraclePath);
    const ref = createCanvas(WIDTH, HEIGHT);
    ref.getContext("2d").drawImage(oracle, 0, 0);

    const a = canvas.getContext("2d").getImageData(0, 0, WIDTH, HEIGHT).data;
    const b = ref.getContext("2d").getImageData(0, 0, WIDTH, HEIGHT).data;

    let differing = 0;
    let ink = 0;
    for (let i = 0; i < a.length; i += 4) {
      const da = Math.max(
        Math.abs(a[i] - b[i]),
        Math.abs(a[i + 1] - b[i + 1]),
        Math.abs(a[i + 2] - b[i + 2]),
      );
      if (da > 24) differing++;
      if (Math.max(b[i], b[i + 1], b[i + 2]) > 24) ink++;
    }
    const pixels = (differing / (WIDTH * HEIGHT)) * 100;
    const relative = ink > 0 ? (differing / ink) * 100 : 0;
    worst = Math.max(worst, pixels);
    console.log(
      `frame ${String(n).padStart(4)}  ${pixels.toFixed(2)}% of pixels  ` +
        `${relative.toFixed(1)}% of ink  (ink ${((ink / (WIDTH * HEIGHT)) * 100).toFixed(2)}%)`,
    );
  }
  console.log(`worst ${worst.toFixed(2)}% of pixels`);
  // Edge antialiasing between two rasterisers is a fraction of a percent; area
  // disagreement is not.
  return worst > 1.0 ? 1 : 0;
}

main().then((code) => process.exit(code));
