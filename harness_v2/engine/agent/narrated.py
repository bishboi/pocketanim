"""The narration, for a scene the video agent writes: when each line and word is said, and the voice itself.

Not a library of pictures or animations: the agent draws everything itself, in plain Manim. This only tells the
scene the time, so what it draws lands on the words:

    from narrated import NarratedScene

    class Chapter(NarratedScene):
        def construct(self):
            self.wait_until(self.word(0, "Japan"))     # hold until "Japan" in line 0 is said
            self.play(FadeIn(japan))
            ...
            self.wait_until_end()                      # hold to the end of the narration

`timing.json` beside the scene (tools/chapter_voice.py) holds every line with its start and end and every word with
its own, in seconds on the chapter's track; the track (`chapter.wav`) is added as the scene's sound at its start, so
the Manim video and the phone's program both carry the voice. With no timing file the scene still runs, silent,
each line timed by its length (0.42 s a word).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from manim import Scene

HERE = Path(os.environ.get("PANIM_NARRATION_DIR") or Path.cwd())
# A section render (the agent's render tool, from/to): the plays before FROM run without drawing a frame, the scene
# stops at TO; the clock is the chapter's all the same. Where the video starts is written to .render_window.
FROM = float(os.environ.get("PANIM_RENDER_FROM") or 0)
TO = float(os.environ.get("PANIM_RENDER_TO") or 0)


def _norm(word: str) -> str:
    """A word as compared: lower case, accents off Latin letters (an Indian script's signs kept), no punctuation."""
    out = []
    for ch in unicodedata.normalize("NFKD", word.lower()):
        if unicodedata.category(ch) == "Mn" and ord(ch) < 0x0900:
            continue
        if ch.isalnum() or unicodedata.category(ch) in ("Mn", "Mc"):
            out.append(ch)
    return "".join(out)


def load(folder: Path = HERE) -> dict:
    """The chapter's timing: {"seconds", "lines": [{"n", "text", "start", "end", "words": [{"w", "start", "end"}]}]}."""
    path = folder / "timing.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("lines"):
            return data
    lines = []
    script = folder / "lines.json"
    texts = json.loads(script.read_text(encoding="utf-8"))["lines"] if script.is_file() else []
    clock = 0.0
    for n, text in enumerate(texts):
        words = text.split()
        row = {"n": n, "text": text, "start": clock, "words": []}
        for w in words:
            row["words"].append({"w": w, "start": clock, "end": clock + 0.42})
            clock += 0.42
        row["end"] = clock
        clock += 0.3
        lines.append(row)
    return {"seconds": clock, "lines": lines, "track": None}


class NarratedScene(Scene):
    """A Manim scene played to the chapter's narration: its voice as the scene's sound, its times to wait for."""

    timing: dict = {}

    def setup(self):
        super().setup()
        self.timing = load()
        self._window_started = False
        track = self.timing.get("track")
        if track and (HERE / track).is_file() and not FROM:
            self.add_sound(str(HERE / track))

    def play(self, *animations, **kwargs):
        if FROM or TO:
            if TO and self.now >= TO:
                from manim.utils.exceptions import EndSceneEarlyException

                raise EndSceneEarlyException()
            before = bool(FROM) and self.now < FROM
            self.renderer._original_skipping_status = before
            if not before and not self._window_started:
                self._window_started = True
                (HERE / ".render_window").write_text(f"{self.now:.3f}")
        return super().play(*animations, **kwargs)

    def wait(self, duration=1.0, *args, **kwargs):
        # A hold across a section's start is split there, so the section's video starts where it was asked to.
        if FROM and self.now < FROM < self.now + float(duration) - 1e-6:
            first = FROM - self.now
            super().wait(first, *args, **kwargs)
            return super().wait(float(duration) - first, *args, **kwargs)
        return super().wait(duration, *args, **kwargs)

    # ---- the time
    @property
    def now(self) -> float:
        """Seconds into the chapter (the scene's clock: what has played so far)."""
        return float(self.renderer.time)

    @property
    def lines(self) -> list[dict]:
        return self.timing["lines"]

    @property
    def length(self) -> float:
        """The whole narration, in seconds."""
        return float(self.timing.get("seconds") or (self.lines[-1]["end"] if self.lines else 0.0))

    def line(self, n: int) -> dict:
        """Line n (0-based): {"n", "text", "start", "end", "words"}."""
        return self.lines[n]

    def word(self, n: int, word: str, occurrence: int = 0, edge: str = "start") -> float:
        """When `word` is said in line n (its `occurrence`-th time there; a word is matched by its start, case and
        accents aside, so "japan" finds "Japan's"); the line's start when it is not in the line."""
        target = _norm(word)
        seen = 0
        for w in self.line(n)["words"]:
            if _norm(w["w"]).startswith(target) and target:
                if seen == occurrence:
                    return float(w[edge])
                seen += 1
        return float(self.line(n)["start"])

    def phrase(self, n: int, words: str) -> float:
        """When a run of words begins in line n ("string of islands"); the line's start when it is not there."""
        want = [_norm(w) for w in re.split(r"\s+", words.strip()) if _norm(w)]
        said = self.line(n)["words"]
        for k in range(len(said) - len(want) + 1):
            if all(_norm(said[k + j]["w"]).startswith(want[j]) for j in range(len(want))):
                return float(said[k]["start"])
        return float(self.line(n)["start"])

    # ---- holding for it
    def wait_until(self, t: float, lead: float = 0.0) -> None:
        """Hold until `lead` seconds before time t (nothing if that has passed)."""
        due = float(t) - lead
        if due > self.now + 1 / 60:
            self.wait(due - self.now)

    def wait_until_end(self) -> None:
        """Hold to the end of the narration."""
        self.wait_until(self.length)
