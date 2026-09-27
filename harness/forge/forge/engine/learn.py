"""Learning a style or a template from an example.

learn-style: an example video or image -> a draft style pack. Frames are
sampled, the palette is clustered, and each colour is given the semantic role
it most plausibly plays (the most common dark is the background, the reddest
saturated colour is `enemy`, the bluest is `friendly`, and so on). The pack
extends the released style whose background is closest, is marked draft, and
is meant to be looked at and corrected before anyone renders with it.

learn-template: an example outline (markdown headings with notes, or a
transcript with chapter headings) -> a draft template whose arc has one slot
per heading, its share from the section's length, its keywords from the
words that section uses most.
"""

from __future__ import annotations

import colorsys
import re
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

from forge import registry
from forge.util import STYLES, TEMPLATES, write_yaml

STOP = set("""a an the and or but of in on at to for from by with as is are was were be been being it its this that
these those he she they them his her their we our you your i not no so than then there here which who whom what when
where why how all any each more most other some such only own same too very can will just into over under about after
before during between also one two three had has have do does did""".split())


def _frames(path: Path, count: int = 12) -> list[np.ndarray]:
    from PIL import Image

    if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return [np.asarray(Image.open(path).convert("RGB").resize((160, 90)))]
    from forge.engine.qa import duration

    length = duration(path) or 10.0
    out = []
    folder = path.parent / f".{path.stem}_frames"
    folder.mkdir(exist_ok=True)
    for i in range(count):
        target = folder / f"f{i:02d}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{length * (i + 0.5) / count:.2f}", "-i",
                        str(path), "-frames:v", "1", "-vf", "scale=160:90", str(target)], timeout=120)
        if target.exists():
            out.append(np.asarray(Image.open(target).convert("RGB")))
            target.unlink()
    folder.rmdir()
    return out


def _kmeans(pixels: np.ndarray, k: int, rounds: int = 20) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    centres = pixels[rng.choice(len(pixels), size=k, replace=False)].astype(float)
    for _ in range(rounds):
        labels = np.argmin(((pixels[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            members = pixels[labels == j]
            if len(members):
                centres[j] = members.mean(0)
    counts = np.bincount(labels, minlength=k)
    return centres, counts


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(round(c)) for c in rgb))


def extract_palette(path, k: int = 10) -> list[dict]:
    """extract.palette: the example's colours, most common first, with hue, lightness, saturation."""
    frames = _frames(Path(path))
    if not frames:
        raise ValueError(f"no frames could be read from {path}")
    pixels = np.concatenate([f.reshape(-1, 3) for f in frames]).astype(float)
    if len(pixels) > 40000:
        pixels = pixels[np.random.default_rng(1).choice(len(pixels), 40000, replace=False)]
    centres, counts = _kmeans(pixels, k)
    out = []
    for rgb, n in sorted(zip(centres, counts), key=lambda row: -row[1]):
        h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        out.append({"hex": _hex(rgb), "share": round(float(n) / len(pixels), 4), "hue": round(float(h) * 360, 1),
                    "light": round(float(l), 3), "sat": round(float(s), 3)})
    return out


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _pick(colours, hue: float, taken: set, fallback: str) -> str:
    live = [c for c in colours if c["sat"] > 0.25 and 0.2 < c["light"] < 0.85 and c["hex"] not in taken]
    if not live:
        return fallback
    best = min(live, key=lambda c: _hue_distance(c["hue"], hue) - c["sat"] * 20)
    if _hue_distance(best["hue"], hue) > 50:
        return fallback
    taken.add(best["hex"])
    return best["hex"]


def _rgb(hex_: str) -> np.ndarray:
    return np.array([int(hex_[i:i + 2], 16) for i in (1, 3, 5)], float)


def learn_style(example, name: str, label: str | None = None) -> dict:
    colours = extract_palette(example)
    bg = colours[0]
    dark = bg["light"] < 0.5
    taken = {bg["hex"]}
    ink = max(colours, key=lambda c: abs(c["light"] - bg["light"]))["hex"]
    taken.add(ink)
    rest = [c for c in colours if c["hex"] not in taken]
    panel = min(rest, key=lambda c: abs(c["light"] - bg["light"]) + (0 if c["sat"] < 0.3 else 1))["hex"] if rest else bg["hex"]
    ink_light = next(c["light"] for c in colours if c["hex"] == ink)
    greys = [c for c in rest if c["sat"] < 0.35 and c["hex"] != panel]
    muted = min(greys, key=lambda c: abs(c["light"] - (bg["light"] + ink_light) / 2))["hex"] if greys else ink
    roles = {
        "ink": ink, "muted": muted,
        "enemy": _pick(colours, 5, taken, "#C8413B"),
        "friendly": _pick(colours, 215, taken, "#4F8FD1"),
        "ally": _pick(colours, 110, taken, "#7FA650"),
        "accent": _pick(colours, 42, taken, "#C9A227"),
        "water": _pick(colours, 195, taken, "#3E6F8E"),
    }
    roles["highlight"] = roles["accent"]
    roles["neutral"] = muted
    roles["land"] = panel
    # The released style whose background is nearest is the parent.
    parents = []
    for sid, spec in registry.styles().items():
        if spec.get("status") == "draft":
            continue
        resolved = registry.resolve_style(sid)
        their_bg = (resolved.get("theme") or {}).get("bg")
        if their_bg:
            parents.append((float(np.linalg.norm(_rgb(their_bg) - _rgb(bg["hex"]))), sid))
    parent = min(parents)[1] if parents else "atlas"
    spec = {
        "id": name, "version": "0.1.0", "status": "draft", "label": label or name.replace("_", " ").title(),
        "description": f"Draft learned from {Path(example).name}. Check every role before release.",
        "extends": parent, "roles": roles, "ops": ["*"], "scripts": ["Latn"],
        "theme": {"bg": bg["hex"], "panel": panel, "cap_bg": bg["hex"] if dark else ink,
                  "cap_fg": ink if dark else bg["hex"], "title_col": roles["accent"], "land": panel,
                  "pal": {"SAND": roles["accent"], "CREAM": ink, "MUTED": muted, "GOLD": roles["highlight"],
                          "RIVER": roles["water"], "ROSE": roles["enemy"], "GREEN": roles["ally"]}},
        "learned": {"from": str(example), "palette": colours},
    }
    folder = STYLES / name
    write_yaml(folder / "style.yaml", spec)
    (folder / "writing.md").write_text(
        f"# {spec['label']} -- writing\n\nDraft. Inherits the tone of `{parent}`; write what this style's narrator "
        "sounds like here before releasing it.\n", encoding="utf-8")
    return {"id": name, "extends": parent, "roles": roles, "file": str(folder / "style.yaml"),
            "status": "draft", "palette": colours}


def learn_template(example, name: str, label: str | None = None) -> dict:
    text = Path(example).read_text(encoding="utf-8", errors="replace")
    sections = []
    for block in re.split(r"(?m)^(?=#{1,3}\s)|^(?=Chapter\s+\w+[:.])", text):
        block = block.strip()
        if not block:
            continue
        head, _, body = block.partition("\n")
        title = re.sub(r"^#+\s*|^Chapter\s+\w+[:.]\s*", "", head).strip()
        if title:
            sections.append((title, body))
    if len(sections) < 2:
        raise ValueError("the example needs at least two headed sections (markdown # headings or 'Chapter N:')")
    total = sum(len(body.split()) for _, body in sections) or 1
    slots = []
    for index, (title, body) in enumerate(sections):
        counts = Counter(w for w in re.findall(r"[a-z]{4,}", body.lower()) if w not in STOP)
        sid = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:24] or f"s{index + 1}"
        required = ["title"] if index == 0 else (["recap"] if re.search(r"recap|summary|conclusion", title, re.I)
                                                 else [])
        slots.append({"id": sid, "title": title, "purpose": (body.strip().split(".")[0] or title)[:120],
                      "share": round(max(len(body.split()), 1) / total, 3), "required": required,
                      "keywords": [w for w, _ in counts.most_common(10)]})
    folder = TEMPLATES / name
    write_yaml(folder / "template.yaml", {
        "id": name, "version": "0.1.0", "status": "draft", "label": label or name.replace("_", " ").title(),
        "description": f"Draft learned from {Path(example).name}.", "requires_ops": ["panel", "fact"],
        "requires_roles": ["ink", "accent"], "compatible_styles": ["*"],
        "target_minutes": {"min": 2, "default": 8, "max": 30}, "words_per_minute": 145,
        "beat_words": {"min": 8, "max": 40},
        "layouts": {"map_panel": {"map": True, "panel": True}, "panel": {"map": False, "panel": True}},
        "default_layout": "map_panel"})
    write_yaml(folder / "arc.yaml", {"slots": slots})
    (folder / "patterns").mkdir(exist_ok=True)
    (folder / "prompts").mkdir(exist_ok=True)
    for role in ("planner", "writer"):
        (folder / "prompts" / f"{role}.md").write_text(
            f"# {role.title()} notes for {name}\n\nDraft. Follow the arc in order; one idea per beat.\n",
            encoding="utf-8")
    return {"id": name, "slots": [s["id"] for s in slots], "file": str(folder / "template.yaml"), "status": "draft"}
