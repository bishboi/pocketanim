"""The pre-render quality gates, as code.

Each gate first applies its deterministic fixes -- merge a short beat, split a
long one, drop an operation that names a place no one can find, swap a glyph
the font lacks, open a new panel before one overflows -- and then reports what
is still wrong. What is left is repaired cheapest-first by the orchestrator: a
targeted model repair of the one beat, a chapter retry, then a person.

An error is {"gate", "chapter", "beat", "message", "repairable"}.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache

from forge import region, registry
from forge.util import NUMBER_RE, numbers_in, words

# Characters a font may lack, and what to draw instead.
SUBSTITUTES = {"≈": "~", "→": "->", "←": "<-", "²": "2", "³": "3", "—": "-", "–": "-", "’": "'", "‘": "'",
               "“": '"', "”": '"', "…": "...", "·": "-", "′": "'", "°": " deg"}
PANEL_ROOM = 5.2
CAPTION_CHARS = 184


def _err(gate, chapter, beat, message, repairable=False):
    return {"gate": gate, "chapter": chapter, "beat": beat, "message": message, "repairable": repairable}


def _texts(op: dict) -> list[str]:
    """The words an operation puts on screen."""
    out = []
    for key in ("title", "sub", "text", "value", "label"):
        if isinstance(op.get(key), str):
            out.append(op[key])
    for key in ("items", "events"):
        for row in op.get(key) or []:
            out.extend(str(x) for x in row)
    for key in ("left", "right"):
        if isinstance(op.get(key), (list, tuple)):
            out.extend(str(x) for x in op[key])
    for node in op.get("nodes") or []:
        out.append(node if isinstance(node, str) else str(node[0]))
    for edge in op.get("edges") or []:
        if len(edge) > 2:
            out.append(str(edge[2]))
    return out


# ════════════════════════════════════════════════════════════════════════
#  Schema
# ════════════════════════════════════════════════════════════════════════

def _resolvable(place, job) -> bool:
    if isinstance(place, (list, tuple)) and len(place) == 2:
        return all(isinstance(v, (int, float)) for v in place)
    if not isinstance(place, str):
        return False
    rid = job.spec.get("region_id")
    if rid:
        pack = region.load(rid)
        if place in (pack.get("anchors") or {}) or place in ((pack.get("features") or {}).get("paths") or {}):
            return True
        units = {u["id"] for u in ((pack.get("battlefield") or {}).get("units") or [])}
        if place in units:
            return True
    return region.lookup(place, rid) is not None


def schema_errors(script: dict, chapter: dict, job) -> list[dict]:
    ops = registry.ops()
    errors = []
    placed = set()
    pack = region.load(job.spec["region_id"]) if job.spec.get("region_id") else {}
    known_units = {u["id"] for u in ((pack.get("battlefield") or {}).get("units") or [])}
    diagrams: dict = {}          # the chapter's diagrams, for its reveal and focus operations
    for index, beat in enumerate(script.get("beats", [])):
        bid = beat.get("id", f"b{index + 1:02d}")
        if not isinstance(beat.get("say"), str) or not beat["say"].strip():
            errors.append(_err("schema", chapter["id"], bid, "beat has no narration", True))
        for op in beat.get("do", []):
            name = op.get("op")
            spec = ops.get(name)
            if spec is None:
                errors.append(_err("schema", chapter["id"], bid, f"unknown operation {name!r}", True))
                continue
            for field in spec["required"]:
                if op.get(field) in (None, "", []):
                    if not (name == "unit" and field == "id" and op.get("id")):
                        errors.append(_err("schema", chapter["id"], bid, f"{name} needs {field}", True))
            if spec.get("map") and not job.spec.get("region_id"):
                errors.append(_err("schema", chapter["id"], bid, f"{name} needs a map, and the job has no region", True))
            if name == "unit":
                if op.get("id") not in known_units and not op.get("at"):
                    errors.append(_err("schema", chapter["id"], bid, f"unit {op.get('id')!r} has no position", True))
                placed.add(op.get("id"))
            for field in ("unit", "from"):
                if name in ("move", "charge", "rout", "volley") and field in op and op[field] not in placed:
                    errors.append(_err("schema", chapter["id"], bid,
                                       f"{name} names unit {op[field]!r} before it is placed", True))
            for field in ("place", "to", "at", "target"):
                value = op.get(field)
                if value is not None and field in spec["required"] | spec.get("optional", {}).keys() \
                        and value not in placed and not _resolvable(value, job):
                    errors.append(_err("schema", chapter["id"], bid, f"{name}: cannot find {value!r} on the map", True))
            if name in ("route", "path"):
                points = op.get("points")
                if isinstance(points, str):
                    if not _resolvable(points, job):
                        errors.append(_err("schema", chapter["id"], bid, f"{name}: no feature {points!r}", True))
                elif not points or any(not _resolvable(p, job) for p in points):
                    errors.append(_err("schema", chapter["id"], bid, f"{name}: a point cannot be found", True))
            if name == "icon":
                # Lectures use no icons: compile draws this as a marker (with places) or a fact line.
                for spot in op.get("places") or []:
                    if not _resolvable(spot, job):
                        errors.append(_err("schema", chapter["id"], bid, f"icon: cannot find {spot!r} on the map", True))
            if name in ("gallery", "diagram", "reveal", "focus", "define", "question", "sketch", "graph", "problem",
                        "work", "incline", "pulley", "piston", "spring", "pendulum", "projectile", "circuit", "lever",
                        "lens", "sim", "counter") or (name == "compare" and op.get("columns")):
                import sys as _sys

                from forge.util import LECTURE
                if str(LECTURE) not in _sys.path:
                    _sys.path.insert(0, str(LECTURE))
                from compile_lecture import _build_problem

                figures = {f["id"]: f for f in (job.read("bundle.json") or {}).get("figures", [])}
                problem = _build_problem(op, diagrams, figures)
                if problem:
                    errors.append(_err("schema", chapter["id"], bid, problem, True))
            if name == "compare" and not op.get("columns") and not (op.get("left") and op.get("right")):
                errors.append(_err("schema", chapter["id"], bid, "compare needs columns (stage) or left and right (panel)", True))
            if name in ("molecule", "equation", "plot", "process", "quote"):
                import sys as _sys

                from forge.util import LECTURE
                if str(LECTURE) not in _sys.path:
                    _sys.path.insert(0, str(LECTURE))
                from compile_lecture import _kit_problem

                problem = _kit_problem(op)
                if problem:
                    errors.append(_err("schema", chapter["id"], bid, problem, True))
            if name == "photo" and not (op.get("image") or op.get("query") or op.get("subject")):
                errors.append(_err("schema", chapter["id"], bid, "photo needs image, subject or query", True))
            if name == "illustration" and not (op.get("query") or op.get("image") or op.get("icon")):
                errors.append(_err("schema", chapter["id"], bid,
                                   "illustration needs query (what it shows, in English) or image", True))
            if name == "figure":
                known = {f["id"] for f in (job.read("bundle.json") or {}).get("figures", [])}
                if op.get("id") not in known:
                    errors.append(_err("schema", chapter["id"], bid, f"no figure {op.get('id')!r} in the sources", True))
            if name == "clock" and not re.fullmatch(r"\d{1,2}:\d{2}", str(op.get("time", ""))):
                errors.append(_err("schema", chapter["id"], bid, f"clock time {op.get('time')!r} is not HH:MM", True))
    return errors


def schema_gate(job, template, style, chapter, script, facts):
    """Word budgets are fixed by merging and splitting; bad operations are dropped."""
    budget = template.get("beat_words", {"min": 8, "max": 40})
    beats = script.get("beats", [])
    # Merge a too-short beat into the next, carrying its operations.
    merged = []
    for beat in beats:
        # A question keeps its own beat: merged into the next, its answer would show before the time to think.
        asks = any(op.get("op") == "question" for op in (merged[-1]["do"] if merged else []) + beat["do"])
        if merged and not asks and words(merged[-1]["say"]) < budget["min"] and len(merged[-1]["do"]) + len(beat["do"]) <= 6:
            merged[-1] = {**merged[-1], "say": f"{merged[-1]['say']} {beat['say']}", "do": merged[-1]["do"] + beat["do"]}
        else:
            merged.append(dict(beat))
    # Split a too-long beat at a sentence or clause boundary.
    out = []
    for beat in merged:
        if words(beat["say"]) > budget["max"]:
            parts = re.split(r"(?<=[.;:])\s+|(?<=,)\s+(?=\w+\s)", beat["say"])
            first, rest = [], []
            for part in parts:
                (first if words(" ".join(first + [part])) <= budget["max"] and not rest else rest).append(part)
            if first and rest:
                out.append({**beat, "say": " ".join(first)})
                out.append({"say": " ".join(rest), "do": [], "sources": beat.get("sources", [])})
                continue
        out.append(beat)
    for index, beat in enumerate(out, 1):
        beat["id"] = f"b{index:02d}"
    script["beats"] = out
    errors = schema_errors(script, chapter, job)
    # Drop the operations the errors name; the narration stands.
    bad = {(e["beat"], e["message"]) for e in errors if e["message"] != "beat has no narration"}
    if bad:
        for beat in script["beats"]:
            keep = []
            for op in beat["do"]:
                probe = {"beats": [{"id": beat["id"], "say": beat["say"], "do": [op]}]}
                placed_before = [o for b in script["beats"] for o in b["do"] if o.get("op") == "unit"]
                probe["beats"].insert(0, {"id": "_", "say": "x", "do": placed_before})
                if any(e["beat"] == beat["id"] for e in schema_errors(probe, chapter, job)):
                    job.log(f"{chapter['id']}.{beat['id']}: dropped {op.get('op')} ({op})")
                    continue
                keep.append(op)
            beat["do"] = keep
        errors = schema_errors(script, chapter, job)
    return script, errors


# ════════════════════════════════════════════════════════════════════════
#  Facts
# ════════════════════════════════════════════════════════════════════════

def facts_gate(job, template, style, chapter, script, facts):
    """Every number or date said or shown must be in the fact sheet."""
    allowed = set(facts.get("numbers", [])) | {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}
    times = set(facts.get("times", []))
    errors = []
    for beat in script.get("beats", []):
        keep = []
        for op in beat.get("do", []):
            if op.get("op") == "clock" and op.get("time") not in times:
                job.log(f"{chapter['id']}.{beat['id']}: dropped clock {op.get('time')} (not in the sources)")
                continue
            shown = numbers_in(" ".join(_texts(op))) - allowed
            if shown:
                job.log(f"{chapter['id']}.{beat['id']}: dropped {op['op']} showing {sorted(shown)} (not in facts)")
                continue
            keep.append(op)
        beat["do"] = keep
        said = numbers_in(beat["say"]) - allowed
        if said:
            errors.append(_err("facts", chapter["id"], beat["id"],
                               f"narration states {sorted(said)}, which no fact supports", True))
    return script, errors


# ════════════════════════════════════════════════════════════════════════
#  Template fit
# ════════════════════════════════════════════════════════════════════════

BATTLE_OPS = {"move", "charge", "rout", "volley", "clock"}


def template_gate(job, template, style, chapter, script, facts):
    from forge.workers import fill_required

    bundle = job.read("bundle.json")
    missing = fill_required(job, template, chapter, script, bundle, facts)
    errors = [_err("template", chapter["id"], None, f"slot {chapter['slot']} needs {m}, and the sources give none")
              for m in missing]
    phases = sum(1 for b in script.get("beats", []) if any(o["op"] in BATTLE_OPS for o in b["do"]))
    if chapter.get("min_phases") and phases < chapter["min_phases"]:
        errors.append(_err("template", chapter["id"], None,
                           f"the battle has {phases} phases; the template asks for {chapter['min_phases']}"))
    return script, errors


# ════════════════════════════════════════════════════════════════════════
#  Glyphs
# ════════════════════════════════════════════════════════════════════════

@lru_cache(None)
def _font_chars(family: str) -> frozenset | None:
    """The characters a font covers, via fontconfig and fontTools; None if unknown."""
    if not shutil.which("fc-match"):
        return None
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", family], capture_output=True, text=True, timeout=10).stdout
        from fontTools.ttLib import TTFont

        font = TTFont(path, fontNumber=0, lazy=True)
        return frozenset(chr(c) for table in font["cmap"].tables if table.isUnicode() for c in table.cmap)
    except Exception:  # noqa: BLE001 -- unknown coverage is not a failure
        return None


def style_fonts(style: dict) -> list[str]:
    import pocket_lecture as pl

    theme = registry.engine_theme(style)
    base = pl.THEMES.get(theme["base"], pl.THEMES["atlas"])
    return sorted({theme.get("sans") or base["sans"], theme.get("serif") or base["serif"]})


def glyph_gate(job, template, style, chapter, script, facts):
    """Swap characters the style's fonts lack; report what has no swap."""
    fonts = [f for f in style_fonts(style) if _font_chars(f) is not None]
    covered = None
    for family in fonts:
        chars = _font_chars(family)
        covered = chars if covered is None else covered & chars
    errors = []
    if covered is None:
        return script, errors

    def fix(text: str, where: str):
        out = []
        for ch in text:
            if ch in covered or ch.isspace():
                out.append(ch)
            elif ch in SUBSTITUTES:
                out.append(SUBSTITUTES[ch])
            else:
                errors.append(_err("glyphs", chapter["id"], where, f"no font covers {ch!r} (U+{ord(ch):04X})"))
                out.append(ch)
        return "".join(out)

    for beat in script.get("beats", []):
        beat["say_caption"] = fix(beat["say"], beat["id"])
        for op in beat["do"]:
            for key in ("title", "sub", "text", "value", "label"):
                if isinstance(op.get(key), str):
                    op[key] = fix(op[key], beat["id"])
    return script, errors


# ════════════════════════════════════════════════════════════════════════
#  Layout and motion
# ════════════════════════════════════════════════════════════════════════

def _panel_height(op: dict) -> float:
    kind = op.get("op")
    if kind == "icon":
        return 0.0 if op.get("places") else 0.87
    if kind in ("figure", "photo"):
        return 3.2 if op.get("where") == "panel" else 0.0
    return {"panel": 1.3 if op.get("sub") else 0.95, "stat": 1.05, "compare": 1.2, "timeline": 1.6,
            "network": 3.3}.get(kind, (max(1, -(-len(str(op.get("text", ""))) // 36)) * 0.33 + 0.22) if kind == "fact"
                                else len(op.get("items") or []) * 0.42 + 0.3 if kind == "bars" else 0.0)


def layout_gate(job, template, style, chapter, script, facts):
    """Captions within two lines; a panel that would overflow starts again."""
    errors = []
    beats = script.get("beats", [])
    out = []
    for beat in beats:
        if len(beat["say"]) > CAPTION_CHARS:
            cut = beat["say"][:CAPTION_CHARS].rfind(". ")
            cut = cut if cut > 40 else beat["say"][:CAPTION_CHARS].rfind(", ")
            if cut > 40:
                out.append({**beat, "say": beat["say"][:cut + 1].strip()})
                out.append({"say": beat["say"][cut + 1:].strip(), "do": [], "sources": beat.get("sources", [])})
                continue
            errors.append(_err("layout", chapter["id"], beat["id"], "caption runs past two lines", True))
        out.append(beat)
    # A new panel is opened at the start of a beat, never between two of its
    # items: the engine clears the old panel first and then brings the beat's
    # items in, so an item before the panel op would be cleared with it.
    used, title = 0.0, chapter["title"]
    for beat in out:
        heads = [o for o in beat["do"] if o["op"] in ("panel", "clear")]
        items = [o for o in beat["do"] if o["op"] not in ("panel", "clear")]
        if heads:
            title = heads[-1].get("title", title)
            used = _panel_height(heads[-1]) if heads[-1]["op"] == "panel" else 0.0
        need = sum(_panel_height(o) for o in items)
        if not heads and need and used + need > PANEL_ROOM:
            heads = [{"op": "panel", "title": title}]
            used = _panel_height(heads[0])
        beat["do"] = heads[-1:] + items
        used += need
    for index, beat in enumerate(out, 1):
        beat["id"] = f"b{index:02d}"
    script["beats"] = out
    return script, errors


MOVERS = {"move", "charge", "rout", "highlight"}


def motion_gate(job, template, style, chapter, script, facts):
    """One animation per object per beat; later ones move to the next beat."""
    beats = script.get("beats", [])
    errors = []
    for index, beat in enumerate(beats):
        seen, keep, carry = set(), [], []
        clocks = [o for o in beat["do"] if o["op"] == "clock"]
        for op in beat["do"]:
            if op["op"] == "clock" and op is not clocks[-1]:
                continue
            target = op.get("unit") or (op.get("target") if op["op"] == "highlight" else None)
            if op["op"] in MOVERS and target:
                if target in seen:
                    carry.append(op)
                    continue
                seen.add(target)
            keep.append(op)
        beat["do"] = keep
        if carry:
            if index + 1 < len(beats):
                beats[index + 1]["do"] = carry + beats[index + 1]["do"]
            else:
                errors.append(_err("motion", chapter["id"], beat["id"],
                                   f"{len(carry)} animation(s) on one object in the last beat were dropped"))
        # Placing the units is one move: the whole order of battle fades in together.
        count = sum(1 for o in beat["do"] if o["op"] != "unit") + (1 if any(o["op"] == "unit" for o in beat["do"]) else 0)
        if count > 6:
            errors.append(_err("motion", chapter["id"], beat["id"], f"{count} operations in one beat", True))
    return script, errors


GATES = [("schema", schema_gate), ("facts", facts_gate), ("template", template_gate),
         ("glyphs", glyph_gate), ("layout", layout_gate), ("motion", motion_gate)]


def run_all(job, template, style, chapter, script, facts):
    errors = []
    for _name, gate in GATES:
        script, found = gate(job, template, style, chapter, script, facts)
        errors.extend(found)
    return script, errors


def numbers_shown(script: dict) -> set[str]:
    return {n for b in script.get("beats", []) for op in b.get("do", []) for n in numbers_in(" ".join(_texts(op)))}


__all__ = ["GATES", "run_all", "schema_errors", "NUMBER_RE"]
