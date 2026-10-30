"""A video as a timeline a player draws, instead of an MP4: what the renderer would draw, recorded frame by frame.

    python timeline.py video.score run_dir out_dir [--quality m]

The score is played by the renderer's own scene (render.ScoreScene: the score read, every mend, every action) with
nothing drawn; at each frame every drawn piece is looked at and what changed is kept:

    a shape (a path of cubic curves: an icon's line, a glyph of a word, a card) is kept once, and then its
        transform (an affine map of that shape), its fill and stroke colour, its stroke width, frame by frame;
        a new shape only when it changes otherwise (a morph, a word being written, a number counting);
    a picture (the paper, a flag, a made picture) is kept once as a PNG, then its corners and its opacity;
    the camera: its centre and width.

Keys are kept only where something changes, and thinned where it moves in a straight line between two of them, so
a still frame costs nothing. Text is the renderer's own glyph outlines: no fonts are needed to play it.

Writes out_dir/timeline.json (the format below) and the pictures beside it; the player (player.html) draws it at
any time t, and an MP4 can be made from the player (export.py) to compare with the renderer's.

    {"version": 1, "fps", "frames", "size": [w, h], "bg", "audio", "camera": [[f, x, y, width]...],
     "boil": {"hz", "shift", "turn"} (when outlines tremble: feel.py),
     "leaves": [{"k": "p" | "i", "z", "r", "on": [[f0, f1]...],
                 "img": "img-....png",                                   (a picture)
                 "shapes": [{"f", "p": [[closed, x0, y0, (h1x, h1y, h2x, h2y, x, y)...]...],   (a path, its base)
                             "keys": [[f, a, b, c, d, e, f2, fill r g b a, stroke r g b a, stroke width]...]}]}]}
    A key's affine (a b c d e f2) maps the shape's base points: x' = a x + c y + e, y' = b x + d y + f2 (world units,
    y up). A picture's keys are [f, ulx, uly, urx, ury, dlx, dly, opacity].
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import render as R  # noqa: E402
import score as S  # noqa: E402
from manim import ImageMobject, VMobject, tempconfig  # noqa: E402
from manim.utils.family import extract_mobject_family_members  # noqa: E402

TOL_POS = 0.0015      # world units a thinned key may be off by (about a fifth of a pixel at 720p)
TOL_COL = 0.004       # colour and opacity


def _r(v: float, k: int = 4) -> float:
    return round(float(v), k)


class Leaf:
    """One drawn piece, followed through the video."""

    def __init__(self, idx: int, m, rank: int):
        self.idx, self.m, self.rank = idx, m, rank
        self.kind = "i" if isinstance(m, ImageMobject) else "p"
        self.on: list[list[int]] = []
        self.shapes: list[dict] = []     # {"f", "base" (n x 2), "p" (subpaths), "frames": [(f, vec)]}
        self.last_vec = None
        self.last_pts = None
        self.img = None

    # -- the state of a frame: a vector (transform, colours, width) against the current shape's base ----------------
    def look_at(self, f: int, tl: "Recorder") -> None:
        m = self.m
        if self.kind == "i":
            pts = np.asarray(m.points)[:, :2]
            alpha = float(getattr(m, "stroke_opacity", 1.0))
            vec = np.array([*pts[0], *pts[1], *pts[2], alpha])
            if not self.shapes:
                self.img = tl.picture(m)
                self.shapes.append({"f": f, "frames": []})
            self._key(f, vec)
            return
        pts = np.asarray(m.points)[:, :2]
        fill = np.asarray(m.get_fill_rgbas())[0]
        stroke = np.asarray(m.get_stroke_rgbas())[0]
        width = float(m.get_stroke_width())
        style = np.array([*fill, *stroke, width])
        shape = self.shapes[-1] if self.shapes else None
        if not np.all(np.isfinite(pts)):
            if self.last_vec is not None:
                self._key(f, self.last_vec)
            return
        if self.last_pts is not None and pts.shape == self.last_pts.shape and np.array_equal(pts, self.last_pts):
            aff = self.last_vec[:6]
        else:
            aff = self._affine(shape["base"], pts) if shape is not None and shape["base"].shape == pts.shape else None
            if aff is None:                     # a new shape (first seen, morphed, partly drawn, rebuilt)
                shape = {"f": f, "base": pts.copy(), "p": self._paths(m), "frames": []}
                self.shapes.append(shape)
                aff = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
            self.last_pts = pts.copy()
        self._key(f, np.concatenate([aff, style]))

    def _key(self, f: int, vec: np.ndarray) -> None:
        if not np.all(np.isfinite(vec)):        # a piece scaled to nothing, or worse: kept as it last was
            if self.last_vec is None or self.last_vec.shape != vec.shape:
                return
            vec = self.last_vec
        _hold(self.shapes[-1]["frames"], f, vec)
        self.last_vec = vec

    @staticmethod
    def _affine(base: np.ndarray, pts: np.ndarray):
        """The affine map taking base to pts, or None when they are not one shape moved (a morph, a partial path)."""
        if len(base) < 3 or float(np.ptp(base, axis=0).max()) < 0.02:
            return None                         # a shape shrunk to a point (a grow from nothing): no map from it
        d0 = base[-1] - base[0]
        cross = np.abs((base[:, 0] - base[0, 0]) * d0[1] - (base[:, 1] - base[0, 1]) * d0[0])
        if float(np.linalg.norm(d0)) > 1e-6 and float(cross.max()) < 1e-7 * max(1.0, float(np.linalg.norm(d0))):
            # a straight line (every point on it): the turn, stretch and shift taking its ends to the new ends
            d1 = pts[-1] - pts[0]
            n0 = float(d0 @ d0)
            a, b = (d1[0] * d0[0] + d1[1] * d0[1]) / n0, (d1[1] * d0[0] - d1[0] * d0[1]) / n0
            M = np.array([[a, -b], [b, a]])
            e = pts[0] - M @ base[0]
            if np.abs(base @ M.T + e - pts).max() > 1e-4 * max(1.0, float(np.ptp(pts, axis=0).max())):
                return None
            return np.array([M[0, 0], M[1, 0], M[0, 1], M[1, 1], e[0], e[1]])
        A = np.hstack([base, np.ones((len(base), 1))])
        sol, *_ = np.linalg.lstsq(A, pts, rcond=None)
        err = np.abs(A @ sol - pts).max()
        span = max(1.0, float(np.ptp(pts, axis=0).max()))
        if err > 1e-4 * span or np.abs(sol[:2]).max() > 50:
            return None                         # not one shape moved, or a map too steep to trust
        # x' = a x + c y + e ; y' = b x + d y + f
        return np.array([sol[0, 0], sol[0, 1], sol[1, 0], sol[1, 1], sol[2, 0], sol[2, 1]])

    @staticmethod
    def _paths(m) -> list:
        out = []
        for sp in m.get_subpaths():
            sp = np.asarray(sp)[:, :2]
            if len(sp) < 4:
                continue
            closed = 1 if np.allclose(sp[0], sp[-1], atol=1e-6) else 0
            flat = [closed, _r(sp[0][0]), _r(sp[0][1])]
            for i in range(0, len(sp) - 3, 4):
                h1, h2, a1 = sp[i + 1], sp[i + 2], sp[i + 3]
                flat += [_r(h1[0]), _r(h1[1]), _r(h2[0]), _r(h2[1]), _r(a1[0]), _r(a1[1])]
            out.append(flat)
        return out

    def out(self) -> dict:
        d = {"k": self.kind, "z": int(getattr(self.m, "z_index", 0)), "r": self.rank, "on": self.on}
        if getattr(self.m, "no_boil", False):
            d["nb"] = 1                         # a map's line: the player keeps it still
        if self.kind == "i":
            d["img"] = self.img
            d["keys"] = _thin(self.shapes[0]["frames"], image=True)
            return d
        d["shapes"] = [{"f": s["f"], "p": s["p"], "keys": _thin(s["frames"])} for s in self.shapes]
        return d


def _hold(frames: list, f: int, vec: np.ndarray) -> None:
    """A frame's state added: the same as the last one (on the next frame) lengthens its hold."""
    if frames and frames[-1][0] + frames[-1][2] == f - 1 and frames[-1][1].shape == vec.shape \
            and np.array_equal(frames[-1][1], vec):
        frames[-1] = (frames[-1][0], frames[-1][1], frames[-1][2] + 1)
    else:
        frames.append((f, vec, 0))


def _thin(frames: list, image: bool = False, camera: bool = False) -> list:
    """Keys where the state changes; a hold becomes its first and last frame; straight runs keep their ends."""
    pts: list[tuple[int, np.ndarray]] = []
    for f, vec, held in frames:
        pts.append((f, vec))
        if held:
            pts.append((f + held, vec))
    if not pts:
        return []
    keep = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = i + 1
        while j + 1 < len(pts) and _straight(pts[i], pts[j + 1], pts[i + 1:j + 1], image):
            j += 1
        keep.append(pts[j])
        i = j
    out = []
    for f, v in keep:
        if camera:
            out.append([f] + [_r(x, 5) for x in v])
        elif image:
            out.append([f] + [_r(x) for x in v])
        else:
            out.append([f] + [_r(x, 5) for x in v[:6]] + [_r(x, 4) for x in v[6:14]] + [_r(v[14], 3)])
    return out


def _straight(a, b, mids, image: bool) -> bool:
    (fa, va), (fb, vb) = a, b
    if fb == fa:
        return False
    for f, v in mids:
        k = (f - fa) / (fb - fa)
        guess = va + (vb - va) * k
        d = np.abs(guess - v)
        if len(v) == 3:                                 # the camera
            if d.max() > TOL_POS:
                return False
        elif image:
            if d[:6].max() > TOL_POS or d[6] > TOL_COL:
                return False
        else:
            if d[:6].max() > TOL_POS / 3 or d[6:14].max() > TOL_COL or d[14] > 0.05:
                return False
    return True


def _unseen(m) -> bool:
    """Nothing of it shows: no fill and no line (or lines of no width)."""
    f = m.fill_rgbas[:, 3].max() if len(m.fill_rgbas) else 0.0
    if f > 0.001:
        return False
    s = m.stroke_rgbas[:, 3].max() if len(m.stroke_rgbas) else 0.0
    return s <= 0.001 or float(m.stroke_width) <= 0.0


class Recorder:
    def __init__(self, out_dir: Path):
        self.out = out_dir
        self.leaves: dict[int, Leaf] = {}
        self.order: list[Leaf] = []
        self.pictures: dict[str, str] = {}
        self.camera: list = []

    def picture(self, m) -> str:
        """A picture's pixels, kept once (its own colours and alpha, before any fading)."""
        from PIL import Image
        px = np.asarray(m.pixel_array).copy()
        if getattr(m, "orig_alpha_pixel_array", None) is not None:
            px[..., 3] = m.orig_alpha_pixel_array
        h = hashlib.sha1(px.tobytes()).hexdigest()[:16]
        if h not in self.pictures:
            name = f"img-{h}.png"
            Image.fromarray(px.astype("uint8"), "RGBA").save(self.out / name)
            self.pictures[h] = name
        return self.pictures[h]

    def frame(self, f: int, scene) -> None:
        cam = scene.camera.frame
        c = cam.get_center()
        _hold(self.camera, f, np.array([c[0], c[1], cam.width]))
        alive = set()
        for m in extract_mobject_family_members(scene.mobjects, use_z_index=True, only_those_with_points=True):
            if not ((isinstance(m, VMobject) and len(m.points)) or isinstance(m, ImageMobject)):
                continue
            leaf = self.leaves.get(id(m))
            if leaf is None or leaf.m is not m:
                # ranked in the drawing order as it first stands in the scene, seen or not yet: a card's face
                # still faded out keeps its place under the picture on it (and its shadow under the face)
                leaf = Leaf(len(self.order), m, len(self.order))
                self.leaves[id(m)] = leaf
                self.order.append(leaf)
            if isinstance(m, VMobject) and _unseen(m):
                continue                        # draws nothing (a hidden reference dot, a part not yet come on)
            if not leaf.on or leaf.on[-1][1] != f:
                leaf.on.append([f, f + 1])
            else:
                leaf.on[-1][1] = f + 1
            alive.add(id(m))
            leaf.look_at(f, self)

    def camera_keys(self) -> list:
        return _thin(self.camera, camera=True)


class BakeScene(R.ScoreScene):
    """The renderer's scene, played without drawing: each frame is recorded instead."""
    RECORDER: Recorder
    TOTAL: int = 0
    BOIL = False                                # the player draws the boil itself (the timeline's `boil`)

    def add_sound(self, *a, **k):  # noqa: D401 -- no sound while recording
        pass

    def wait(self, duration=None, *a, **k):
        self._drawing = None                    # (the renderer's drawing progress: nothing is drawn here)
        fps = self.FPS
        step = max(1, self.TOTAL // 200)
        print(f"recording {self.TOTAL} frames ({self.TOTAL / fps:.0f} s at {fps} fps)", flush=True)
        for f in range(self.TOTAL):
            if f:
                self._tick(1.0 / fps)
            self.RECORDER.frame(f, self)
            if f % step == 0 or f == self.TOTAL - 1:
                print(f"progress: {f + 1}/{self.TOTAL} frames recorded", flush=True)


def bake(score_text: str, voice_dir: Path, out_dir: Path, quality: str = "m") -> dict:
    words = json.loads((voice_dir / "words.json").read_text())
    sc = S.parse(score_text, words["words"], float(words["seconds"]))
    w, h, fps = R.RES[quality]      # the render's own rate: what an action does can depend on its steps (a number
                                    # counting while it rises), so both play the same steps; the player eases between
    total = R.frames_of(sc.end + R.TAIL, fps)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("img-*.png"):
        old.unlink()
    rec = Recorder(out_dir)
    print("playing the score (the renderer's scene, not drawn)", flush=True)
    BakeScene.SCORE, BakeScene.WORDS, BakeScene.WAV = sc, words, None
    BakeScene.FRAMES, BakeScene.SOUND, BakeScene.FPS, BakeScene.TOTAL, BakeScene.RECORDER = (0, total), False, fps, total, rec
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_rate": fps, "disable_caching": True,
                     "verbosity": "WARNING", "progress_bar": "none", "media_dir": str(out_dir / ".media")}):
        scene = BakeScene()
        scene.setup()
        scene.construct()
    shutil.rmtree(out_dir / ".media", ignore_errors=True)
    audio = "voice.wav"
    if (voice_dir / "voice.wav").exists():
        shutil.copyfile(voice_dir / "voice.wav", out_dir / "voice.wav")
        try:                                    # the voice with its small sounds and music under it (sound.py)
            import sound
            told = sound.mix(sc, voice_dir / "voice.wav", out_dir / "soundtrack.wav")
            audio = "soundtrack.wav"
            print(f"soundtrack: {told['sounds']} sound(s), music {told['music'] or 'off'}", flush=True)
        except Exception as e:  # noqa: BLE001 -- the voice alone
            print(f"soundtrack not made ({e}): the voice alone", flush=True)
    import feel
    import look
    print(f"writing timeline.json: {len(rec.order)} pieces, {len(rec.pictures)} picture(s)", flush=True)
    data = {"version": 1, "fps": fps, "frames": total, "size": [w, h], "frame_width": S.SCREEN_W,
            "bg": look.L["bg"], "audio": audio, "camera": rec.camera_keys(),
            "leaves": [leaf.out() for leaf in rec.order if leaf.shapes], "notes": sc.notes}
    if feel.texture_on(sc):                     # outlines tremble as drawn (player.html: boil)
        data["boil"] = {"hz": feel.BOIL_HZ, "shift": feel.BOIL_SHIFT, "turn": feel.BOIL_TURN}
    text = json.dumps(data, separators=(",", ":")).replace("NaN", "0")    # (never NaN in the JSON: a player cannot read it)
    (out_dir / "timeline.json").write_text(text)
    return {"leaves": len(rec.order), "frames": total, "bytes": len(text), "pictures": len(rec.pictures),
            "shapes": sum(len(l.shapes) for l in rec.order if l.kind == "p"), "notes": sc.notes}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("voice")
    ap.add_argument("out")
    ap.add_argument("--quality", default="m")
    a = ap.parse_args()
    info = bake(Path(a.score).read_text(), Path(a.voice), Path(a.out), a.quality)
    for n in info.pop("notes"):
        print("note:", n)
    print("timeline:", json.dumps(info))


if __name__ == "__main__":
    main()
