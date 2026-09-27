/**
 * Rasterising a pocketanim frame onto a 2D canvas.
 *
 * Separate from the React component on purpose: this is the part that has to
 * agree with `exporter/reference_render.py`, so it has to be runnable without
 * a browser to check that it does.
 */

import type { Instance } from "./pocketanim";

// Manim's frame, in scene units. Everything the renderer draws is expressed in
// these and scaled to the canvas, which is why a preview at any size is the
// same picture.
const FRAME_WIDTH = 14.222222222222221;
const FRAME_HEIGHT = 8.0;
// Manim's stroke_width is in hundredths of a scene unit.
const STROKE_SCALE = 0.01;

function rgba(c: number[]): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${(c[3] ?? 255) / 255})`;
}

/**
 * Draw one instance.
 *
 * Mirrors exporter/reference_render.py, which is the oracle the format is
 * defined against. Two rules carry more weight than they look:
 *
 * - A subpath breaks where a cubic does not start where the last one ended.
 * - A subpath is closed **only when its ends actually meet**. Closing
 *   unconditionally draws a chord across a half-finished Create, which is
 *   exactly the defect docs/SPEC.md §11 records finding this way.
 */
function drawInstance(
  ctx: CanvasRenderingContext2D,
  shape: number[],
  inst: Instance,
  scaleX: number,
  scaleY: number,
  width: number,
  height: number,
) {
  const [, a, b, c, d, e, f, fill, stroke, strokeWidth] = inst;

  // Scene point -> canvas pixel, with the instance affine applied first.
  const px = (x: number, y: number): [number, number] => {
    const sx = a * x + b * y + e;
    const sy = c * x + d * y + f;
    return [sx * scaleX + width / 2, -sy * scaleY + height / 2];
  };

  const curves = Math.floor(shape.length / 8); // 4 points x 2 floats
  if (curves === 0) return;

  // Built on the context rather than into a path object: the oracle does the
  // same (fill_preserve, then stroke on the same path), and it keeps this file
  // runnable outside a browser, which is how it gets checked at all.
  ctx.beginPath();
  let open = false;
  let startX = 0;
  let startY = 0;
  let endX = 0;
  let endY = 0;

  for (let i = 0; i < curves; i++) {
    const o = i * 8;
    if (open) {
      const prev = o - 8 + 6;
      const joined =
        Math.abs(shape[prev] - shape[o]) <= 1e-6 &&
        Math.abs(shape[prev + 1] - shape[o + 1]) <= 1e-6;
      if (!joined) {
        if (Math.abs(endX - startX) <= 1e-6 && Math.abs(endY - startY) <= 1e-6) {
          ctx.closePath();
        }
        open = false;
      }
    }
    if (!open) {
      const [mx, my] = px(shape[o], shape[o + 1]);
      ctx.moveTo(mx, my);
      startX = shape[o];
      startY = shape[o + 1];
      open = true;
    }
    const [x1, y1] = px(shape[o + 2], shape[o + 3]);
    const [x2, y2] = px(shape[o + 4], shape[o + 5]);
    const [x3, y3] = px(shape[o + 6], shape[o + 7]);
    ctx.bezierCurveTo(x1, y1, x2, y2, x3, y3);
    endX = shape[o + 6];
    endY = shape[o + 7];
  }
  if (open && Math.abs(endX - startX) <= 1e-6 && Math.abs(endY - startY) <= 1e-6) {
    ctx.closePath();
  }

  if ((fill[3] ?? 0) > 0) {
    ctx.fillStyle = rgba(fill);
    ctx.fill();
  }
  if ((stroke[3] ?? 0) > 0 && strokeWidth > 0) {
    ctx.strokeStyle = rgba(stroke);
    // Stroke width is a scene unit too, so it scales with the canvas.
    ctx.lineWidth = strokeWidth * STROKE_SCALE * scaleX;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
  }
}


/** Draw one frame of a 2d program, background included. */
export function drawFrame(
  ctx: CanvasRenderingContext2D,
  shapes: number[][],
  instances: Instance[],
  width: number,
  height: number,
  background = "#000000",
) {
  // The program's own clear colour. A paper or whiteboard style on black is
  // a different picture.
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width, height);
  const scaleX = width / FRAME_WIDTH;
  const scaleY = height / FRAME_HEIGHT;
  for (const inst of instances) {
    const shape = shapes[inst[0]];
    if (shape) drawInstance(ctx, shape, inst, scaleX, scaleY, width, height);
  }
}

export { FRAME_WIDTH, FRAME_HEIGHT, drawInstance };
