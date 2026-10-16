/**
 * A picture made to fit what a model takes. Decision models refuse some pictures outright ("Invalid image
 * dimensions": a tiny crop, a very long strip, a huge scan), so every picture sent to one is first made safe:
 *   - no side over MAX_SIDE (scaled down), no side under MIN_SIDE (scaled up),
 *   - no longer than MAX_RATIO to 1 (padded with white to that shape, the picture centred),
 *   - transparency flattened onto white; sent as PNG.
 * What was done is said, so the call shows it.
 */

import sharp from "sharp";

const MAX_SIDE = Number(process.env.V2_IMAGE_MAX_SIDE) || 1568;
const MIN_SIDE = Number(process.env.V2_IMAGE_MIN_SIDE) || 64;
const MAX_RATIO = Number(process.env.V2_IMAGE_MAX_RATIO) || 4;

export type Fitted = { url: string; width: number; height: number; from: { width: number; height: number }; changed: string[] };

export async function fitImage(dataUrl: string): Promise<Fitted> {
  const m = /^data:image\/[\w+.-]+;base64,([\s\S]*)$/.exec(dataUrl);
  const input = Buffer.from(m ? m[1] : dataUrl, "base64");
  const meta = await sharp(input).metadata();
  const from = { width: meta.width ?? 0, height: meta.height ?? 0 };
  if (!from.width || !from.height) throw new Error("the picture could not be read (no width or height)");
  const changed: string[] = [];
  let w = from.width, h = from.height;
  // Too large: scaled down so its longer side fits. Too small: scaled up so its shorter side does.
  const down = Math.min(1, MAX_SIDE / Math.max(w, h));
  const up = Math.max(1, MIN_SIDE / Math.min(w * down, h * down));
  const scale = down * up;
  if (scale !== 1) {
    w = Math.max(1, Math.round(w * scale));
    h = Math.max(1, Math.round(h * scale));
    changed.push(scale < 1 ? `scaled down to ${w}×${h}` : `scaled up to ${w}×${h}`);
  }
  let image = sharp(input).flatten({ background: "#ffffff" }).resize(w, h, { fit: "fill" });
  // Too long a strip: padded with white to MAX_RATIO to 1 (then held under MAX_SIDE again).
  if (Math.max(w, h) / Math.min(w, h) > MAX_RATIO) {
    const W = w >= h ? w : Math.ceil(h / MAX_RATIO);
    const H = w >= h ? Math.ceil(w / MAX_RATIO) : h;
    image = sharp(await image.png().toBuffer()).extend({
      top: Math.floor((H - h) / 2), bottom: Math.ceil((H - h) / 2), left: Math.floor((W - w) / 2), right: Math.ceil((W - w) / 2),
      background: "#ffffff",
    });
    changed.push(`padded to ${W}×${H} (no longer than ${MAX_RATIO}:1)`);
    w = W;
    h = H;
  }
  const out = await image.png().toBuffer();
  return { url: `data:image/png;base64,${out.toString("base64")}`, width: w, height: h, from, changed };
}
