"""The animations timed to the voice, after it is made: a lecture's timing slots (`cues=`) filled in by a model.

The lecture is written and compiled with no times in it: a beat is a line and the animations that go with it
(`self.beat("line", anim, anim, ...)`), a free-form block is a line and code with plays in it
(`self.free(key, "line", code)`). Once the voice has said every line (scripts/prespeak.py) it is known when each
word is said (ElevenLabs' timestamps, or the line's words aligned to its audio by a small local model for any other
voice: local_align.py, pocket_lecture.line_words). Here a chat model reads each beat's words with
their times and the animations that go with it, and says when each animation starts and how long it takes, so a
part lights up as its name is said and a reveal lands on the words that bring it. The times are checked
(pocket_lecture.Lecture._cue_plan keeps them in order and inside the line) and written into the scene as
`cues=[[start, seconds], ...]` on each beat and `cues=[start, ...]` on each free block, so the build that follows,
and any build of that scene after, plays them. A beat with no words timed, or that the model gave nothing usable
for, is left as it was: its animations play together as its line begins.

PANIM_ALIGN=off turns it off; PANIM_ALIGN_MODEL picks the model (else OPENROUTER_MODEL).
"""

from __future__ import annotations

import ast
import json
import re
from concurrent.futures import ThreadPoolExecutor

import llm
from chirp import _env

CHUNK = 25              # beats a request
PARALLEL = 4

SYSTEM = """You time the animations of a narrated video lecture to its narration, after the voice was \
recorded. For each beat you get the teacher's line, the time (in seconds from the line's start) each word is \
said, the line's length, and the animations that go with the line, in the order they must start (as the code \
that makes them, with a label).

Give each animation a start and a duration so the picture follows the voice:
- Start an animation 0.15 to 0.3 s BEFORE the first word that names, introduces or describes what it shows (a \
diagram part's label, a place, a term being defined, the step of a working). A highlight or focus on a part goes \
on the part's name. A whole new picture, diagram, map or card that the line is about starts at 0.
- When the line never names what an animation shows, start it where the idea it shows is being said, or at 0.
- Never start an animation before one listed above it; start times only stay the same or grow down the list.
- Durations: a focus, highlight or indicate 0.5 to 0.9 s; a label, reveal, arrow or one item 0.6 to 1.2 s; a new \
diagram, picture, card or equation 1.0 to 2.0 s; a camera move 1.0 to 2.0 s. An animation should finish before \
the next one starts; it is cut short if it does not.
- Starts lie inside the line (0 to its length minus 0.3 s).

For a FREE block (Manim code written for the beat), give only a start for each of its plays, in order, the same \
way: each play starts on the words it goes with; a play that builds the figure the line is about starts at 0.

Reply with JSON only: {"beats": [{"id": <id>, "cues": [[start, duration], ...]} for an ordinary beat, \
{"id": <id>, "starts": [start, ...]} for a free block]}, one entry for every beat you were given, one cue or \
start per animation or play, in order."""


# ---------------- reading the scene ----------------

def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def _describe(source: str, node: ast.AST) -> str:
    """An animation's code, shortened: self.safe(lambda: X, "chapter 1 beat 4 focus") becomes `focus: X`."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "safe" \
            and node.args and isinstance(node.args[0], ast.Lambda):
        label = _literal(node.args[1]) if len(node.args) > 1 else None
        inner = ast.get_source_segment(source, node.args[0].body) or ""
        text = f"{str(label).split(' ')[-1]}: {inner}" if label else inner
    else:
        text = ast.get_source_segment(source, node) or ""
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= 400 else text[:400] + "…"


def _plays(code: str) -> list[str] | None:
    """A free block's plays, in order, when they are all at its top level (a play in a loop or a function happens
    a number of times known only when it runs: the block is then not timed)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    top = [s for s in tree.body if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
           and isinstance(s.value.func, ast.Attribute) and s.value.func.attr == "play"]
    every = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr in ("play", "wait")]
    if len(top) != sum(1 for n in every if n.func.attr == "play"):
        return None
    out = []
    for statement in top:
        segment = re.sub(r"\s+", " ", ast.get_source_segment(code, statement) or "")
        out.append(segment if len(segment) <= 240 else segment[:240] + "…")
    return out


def beats(source: str) -> list[dict]:
    """The scene's beats that can be timed, in order: {"call", "kind": "beat"|"free", "text", "parts"}."""
    out = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"):
            continue
        if any(isinstance(a, ast.Starred) for a in node.args):
            continue
        if node.func.attr == "beat" and len(node.args) >= 2:
            text = _literal(node.args[0])
            if isinstance(text, str):
                out.append({"call": node, "kind": "beat", "text": text,
                            "parts": [_describe(source, a) for a in node.args[1:]]})
        elif node.func.attr == "free" and len(node.args) >= 3:
            text, code = _literal(node.args[1]), _literal(node.args[2])
            plays = _plays(code) if isinstance(code, str) else None
            if isinstance(text, str) and plays:
                out.append({"call": node, "kind": "free", "text": text, "parts": plays})
    out.sort(key=lambda b: (b["call"].lineno, b["call"].col_offset))
    return out


# ---------------- asking ----------------

def _item(index: int, beat: dict, words: list[dict], seconds: float) -> str:
    said = " ".join(f"{w['start']:.2f}:{w['w']}" for w in words)
    parts = "\n".join(f"  {k + 1}. {p}" for k, p in enumerate(beat["parts"]))
    kind = "FREE block, its plays" if beat["kind"] == "free" else "animations"
    return f"id {index}\nline ({seconds:.2f} s): {beat['text']}\nwords: {said}\n{kind}:\n{parts}"


def check(beat: dict, entry: dict, seconds: float) -> list | None:
    """The model's times for a beat, kept inside the line and in order; None when they will not do."""
    count = len(beat["parts"])
    raw = entry.get("starts") if beat["kind"] == "free" else entry.get("cues")
    if not isinstance(raw, list) or len(raw) != count:
        return None
    latest = max(0.0, seconds - 0.3)
    out, floor = [], 0.0
    for value in raw:
        try:
            if beat["kind"] == "free":
                start, run = float(value), None
            else:
                start, run = float(value[0]), float(value[1])
        except (TypeError, ValueError, IndexError):
            return None
        start = round(min(max(start, floor, 0.0), latest), 2)
        floor = start
        out.append(start if run is None else [start, round(min(max(run, 0.3), 4.0), 2)])
    return out


def align(source: str, words_of, seconds_of) -> tuple[str, dict]:
    """(the scene with cues written in, a report). `words_of(text)` and `seconds_of(text)` say when each word of a
    line is said and how long it is (None when unknown).

    The report says what happened, for the build's log and the page: {"beats" (that could be timed), "timed"
    (with their words known), "aligned" (given cues), "usd", "model", "errors" (the model's failures, as said),
    "untimed" (a few lines with no words, and why), "lines" (every beat: its line, its parts, its first words
    with their times, and the cues it got or why not)}."""
    found = beats(source)
    todo = []
    # The words' times, several lines at once: a voice that does not time its words has them aligned here first
    # (local_align.py), a fraction of a second a line.
    with ThreadPoolExecutor(max_workers=4) as pool:
        timed = list(pool.map(lambda b: (words_of(b["text"]), seconds_of(b["text"])), found))
    lines: list[dict] = []
    for beat, (said, seconds) in zip(found, timed):
        record = {"kind": beat["kind"], "line": beat["text"][:120], "parts": beat["parts"],
                  "seconds": seconds, "words": [f"{w['start']:.2f}:{w['w']}" for w in (said or [])[:12]]}
        lines.append(record)
        beat["record"] = record
        if said and seconds:
            todo.append((beat, said, seconds))
        else:
            record["why"] = "the line is not spoken yet" if not seconds else "no word times for the line"
    report = {"beats": len(found), "timed": len(todo), "aligned": 0, "usd": 0.0, "model": None, "errors": [],
              "lines": lines}
    if not todo:
        return source, report
    if not llm.configured():
        report["errors"].append("no key for the timing model (OPENROUTER_API_KEY or OPENAI_API_KEY)")
        return source, report
    model = llm.model("PANIM_ALIGN_MODEL")
    report["model"] = model
    chunks = [todo[i:i + CHUNK] for i in range(0, len(todo), CHUNK)]

    def ask(chunk):
        user = "\n\n".join(_item(k, beat, said, seconds) for k, (beat, said, seconds) in enumerate(chunk))
        try:
            reply, usd = llm.chat_json(model, SYSTEM, user)
        except RuntimeError as error:
            for beat, _, _ in chunk:
                beat["record"]["why"] = f"the timing model failed: {str(error)[:160]}"
            return [], 0.0, str(error)
        timed = []
        for entry in reply.get("beats") or []:
            try:
                k = int(entry.get("id"))
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= k < len(chunk):
                cues = check(chunk[k][0], entry, chunk[k][2])
                if cues is not None:
                    timed.append((chunk[k][0], cues))
                    chunk[k][0]["record"]["cues"] = cues
                else:
                    chunk[k][0]["record"]["why"] = f"the model's times did not fit: {json.dumps(entry)[:160]}"
        for beat, _, _ in chunk:
            if "cues" not in beat["record"]:
                beat["record"].setdefault("why", "the model gave this beat no times")
        return timed, usd, None

    edits = []
    with ThreadPoolExecutor(max_workers=min(PARALLEL, len(chunks))) as pool:
        for timed, usd, error in pool.map(ask, chunks):
            report["usd"] += usd
            edits.extend(timed)
            if error and error not in report["errors"]:
                report["errors"].append(error)
    report["aligned"] = len(edits)
    report["usd"] = round(report["usd"], 6)
    return write_cues(source, edits), report


# ---------------- writing the times in ----------------

def _offset(lines: list[str], starts: list[int], lineno: int, col: int) -> int:
    """A character index in the source from ast's (line, UTF-8 byte column)."""
    return starts[lineno - 1] + len(lines[lineno - 1].encode("utf-8")[:col].decode("utf-8", "ignore"))


def write_cues(source: str, edits: list) -> str:
    """The source with `cues=...` set on each call in `edits` ([(beat, cues)]): replaced where it was set."""
    lines = source.splitlines(keepends=True)
    starts, at = [], 0
    for line in lines:
        starts.append(at)
        at += len(line)
    spans = []
    for beat, cues in edits:
        call = beat["call"]
        text = json.dumps(cues)
        old = next((k for k in call.keywords if k.arg == "cues"), None)
        if old is not None:
            a = _offset(lines, starts, old.value.lineno, old.value.col_offset)
            b = _offset(lines, starts, old.value.end_lineno, old.value.end_col_offset)
            spans.append((a, b, text))
        else:
            end = _offset(lines, starts, call.end_lineno, call.end_col_offset) - 1      # the closing ")"
            before = source[:end].rstrip()
            spans.append((end, end, f"cues={text}" if before.endswith(",") else f", cues={text}"))
    for a, b, text in sorted(spans, reverse=True):
        source = source[:a] + text + source[b:]
    return source


def enabled(engine: str) -> bool:
    return (_env("PANIM_ALIGN") or "on").strip().lower() not in ("off", "0", "no")
