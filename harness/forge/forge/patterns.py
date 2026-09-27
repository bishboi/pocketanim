"""Beat patterns: reusable sequences with slots.

A writer that uses a pattern returns slot values and narration lines; the
pattern expands them to operations. So the model never invents structure the
template already knows, and it spends tokens only on words.

    {"pattern": "decisive_charge",
     "slots": {"attacker": "mir_madan", "target": "company", "outcome": "repulsed"},
     "lines": {"setup": "...", "charge": "...", "result": "..."}}
"""

from __future__ import annotations

import copy
import re

TOKEN = re.compile(r"\{([^{}]+)\}")


def _value(expr: str, slots: dict):
    expr = expr.strip()
    ternary = re.fullmatch(r"(\w+)\s*==\s*(\w+)\s*\?\s*(\w+)\s*:\s*(\w+)", expr)
    if ternary:
        name, wanted, yes, no = ternary.groups()
        return yes if str(slots.get(name)) == wanted else no
    return slots.get(expr, "{" + expr + "}")


def _fill(value, slots: dict):
    if isinstance(value, str):
        whole = TOKEN.fullmatch(value)
        if whole:
            return _value(whole.group(1), slots)      # keep lists and numbers whole
        return TOKEN.sub(lambda m: str(_value(m.group(1), slots)), value)
    if isinstance(value, list):
        return [_fill(v, slots) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, slots) for k, v in value.items()}
    return value


def expand(beat: dict, patterns: dict) -> list[dict]:
    """A pattern beat as plain beats; any other beat unchanged."""
    if "pattern" not in beat:
        return [beat]
    pattern = patterns.get(beat["pattern"])
    if pattern is None:
        raise KeyError(f"unknown pattern {beat['pattern']!r}")
    slots = dict(beat.get("slots") or {})
    lines = dict(beat.get("lines") or {})
    out = []
    for step in copy.deepcopy(pattern.get("beats", [])):
        say = step.get("say", "")
        key = TOKEN.fullmatch(say.strip())
        text = lines.get(key.group(1)) if key else _fill(say, {**slots, **lines})
        if not text:
            text = lines.get("line") or ""
        out.append({"say": text, "do": _fill(step.get("do", []), slots), "pattern": beat["pattern"]})
    return out


def expand_chapter(script: dict, patterns: dict) -> dict:
    beats = []
    for beat in script.get("beats", []):
        beats.extend(expand(beat, patterns))
    for index, beat in enumerate(beats, 1):
        beat["id"] = f"b{index:02d}"
    return {**script, "beats": beats}
