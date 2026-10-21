"""What a render of the video agent's scene measures about itself, as Manim plays it.

Installed before the scene runs (tools/agent_tools.py render): every play and wait is noted with when it ran and
what kinds of animation it held, and after each one the stage is looked at: the words on it (any outside the frame,
any two on top of each other) and whether anything is on it at all beyond what was there from the start. Written
as `audit.json` beside the scene when Manim exits:

    plays, seconds, kinds (animation name -> count), fade_share (FadeIn/FadeOut of all animations),
    dead (stretches over DEAD seconds with nothing playing: [start, end]),
    empty (stretches over EMPTY seconds with nothing on the stage but its first things: [start, end]),
    off_frame ([t, text]), overlaps ([t, text, text])

A free video can do anything; these are what a viewer sees as faults: a screen that sits still too long, an empty
screen, words cut off by the frame's edge, words written over words.
"""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

DEAD = 8.0          # seconds of nothing moving that a viewer notices
EMPTY = 3.0         # seconds of an empty stage
HALF_W, HALF_H = 7.11, 4.0
TEXT_TYPES = ("Text", "MarkupText", "Paragraph", "Tex", "MathTex", "SingleStringMathTex", "Title", "DecimalNumber", "Integer")
WRAPPERS = ("AnimationGroup", "Succession", "LaggedStart", "LaggedStartMap")


def install(out: Path | None = None) -> None:
    from manim import Scene

    out = out or Path(os.environ.get("PANIM_NARRATION_DIR") or ".") / "audit.json"
    state = {"plays": [], "base": None, "texts_off": {}, "overlaps": {}, "content": []}
    original = Scene.play

    def kinds_of(animations) -> list[str]:
        names: list[str] = []
        todo = list(animations)
        while todo:
            a = todo.pop(0)
            name = type(a).__name__
            if name in WRAPPERS:
                todo[:0] = list(getattr(a, "animations", []) or [])
            elif name == "_AnimationBuilder" or name == "_MethodAnimation":
                names.append(".animate")
            else:
                names.append(name)
        return names

    def text_roots(scene) -> list:
        roots, seen = [], set()
        for top in scene.mobjects:
            for m in top.get_family():
                if id(m) in seen:
                    continue
                if type(m).__name__ in TEXT_TYPES:
                    roots.append(m)
                    seen.update(id(x) for x in m.get_family())
        return roots

    def visible(m) -> bool:
        try:
            return max(float(m.get_fill_opacity()), float(m.get_stroke_opacity())) > 0.05 and m.width > 0.01
        except Exception:  # noqa: BLE001
            return True

    def label(m) -> str:
        return str(getattr(m, "text", None) or getattr(m, "tex_string", None) or type(m).__name__)[:60]

    def look(scene, t: float) -> None:
        texts = [m for m in text_roots(scene) if visible(m)]
        boxes = []
        for m in texts:
            (x0, y0, _), (x1, y1, _) = m.get_corner([-1, -1, 0]), m.get_corner([1, 1, 0])
            boxes.append((m, x0, y0, x1, y1))
            if x0 < -HALF_W or x1 > HALF_W or y0 < -HALF_H or y1 > HALF_H:
                state["texts_off"].setdefault(id(m), [round(t, 2), label(m)])
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                w = min(a[3], b[3]) - max(a[1], b[1])
                h = min(a[4], b[4]) - max(a[2], b[2])
                if w <= 0 or h <= 0:
                    continue
                small = min((a[3] - a[1]) * (a[4] - a[2]), (b[3] - b[1]) * (b[4] - b[2])) or 1e-9
                if w * h / small > 0.25:
                    key = tuple(sorted((id(a[0]), id(b[0]))))
                    state["overlaps"].setdefault(key, [round(t, 2), label(a[0]), label(b[0])])
        if state["base"] is None:
            state["base"] = {id(m) for m in scene.mobjects}
        content = [m for m in scene.mobjects if id(m) not in state["base"]]
        state["content"].append((round(t, 3), len(content)))

    def play(self, *animations, **kwargs):
        start = float(self.renderer.time)
        if state["base"] is None:
            state["base"] = {id(m) for m in self.mobjects}
        result = original(self, *animations, **kwargs)
        end = float(self.renderer.time)
        names = kinds_of(animations)
        still = all(n == "Wait" for n in names)
        state["plays"].append((round(start, 3), round(end, 3), still, [n for n in names if n != "Wait"]))
        try:
            look(self, end)
        except Exception:  # noqa: BLE001 -- the audit never stops a render
            pass
        return result

    Scene.play = play

    def write() -> None:
        plays = state["plays"]
        if not plays:
            return
        seconds = plays[-1][1]
        kinds: dict[str, int] = {}
        for *_, names in plays:
            for n in names:
                kinds[n] = kinds.get(n, 0) + 1
        total = sum(kinds.values()) or 1
        fades = kinds.get("FadeIn", 0) + kinds.get("FadeOut", 0)
        dead, last = [], 0.0
        for start, end, still, _ in plays:
            if not still:
                if start - last > DEAD:
                    dead.append([round(last, 1), round(start, 1)])
                last = end
        if seconds - last > DEAD:
            dead.append([round(last, 1), round(seconds, 1)])
        empty, since = [], None
        for t, count in state["content"]:
            if count == 0 and since is None:
                since = t
            elif count and since is not None:
                if t - since > EMPTY:
                    empty.append([round(since, 1), round(t, 1)])
                since = None
        if since is not None and seconds - since > EMPTY:
            empty.append([round(since, 1), round(seconds, 1)])
        report = {"plays": sum(1 for p in plays if not p[2]), "seconds": round(seconds, 2), "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
                  "fade_share": round(fades / total, 2), "dead": dead, "empty": empty,
                  "off_frame": sorted(state["texts_off"].values()), "overlaps": sorted(state["overlaps"].values())}
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1))

    atexit.register(write)
