"""Long videos in parts: a narration of many minutes (up to 20 or more) is cut into parts of about V3_PART_SECONDS
(150 s) at the pauses between lines, and each part is played (laid out, baked, rendered) by itself, at once with the
others, then joined. The voice is spoken once and the cast made once for the whole video, so it sounds and looks
the same throughout; the chapter bar runs over the whole video.

    parts_of(words)                 the parts: [{k, t0, t1, a, b}] (seconds; first and last word), cut on frames
    split(score, words, parts)      each part's own score: the score's head (look, cast...), its shots, and what
                                    it uses from the part before (their `ent` lines, where they were)
    write(run_dir, ...)             parts/pK/: video.score, words.json (times from the part's start), voice.wav
    env(part, ...)                  what a part's render or bake is told: no held tail but on the last, where it
                                    stands in the whole (the chapter bar)
    manifest(...)                   player/parts.json: the parts in order, their frames, the one soundtrack

A video of one part is made as before (none of this is used).
"""

from __future__ import annotations

import json
import os
import re
import wave
from pathlib import Path

PART_SECONDS = float(os.environ.get("V3_PART_SECONDS", "150"))
FPS = 30
TAIL = 3.2                      # render.TAIL: held after the last word (the last part only)


def _snap(t: float, fps: int = FPS) -> float:
    return round(t * fps) / fps


def parts_of(words: dict, target: float | None = None, fps: int = FPS) -> list[dict]:
    """The parts: a cut between two lines, in the quiet between them, nearest each multiple of the part length
    (a longer pause preferred a little). One part when the video is short."""
    target = target or PART_SECONDS
    total = float(words["seconds"])
    ws, lines = words["words"], words.get("lines") or []
    one = [{"k": 0, "t0": 0.0, "t1": total, "a": 0, "b": len(ws) - 1}]
    if total <= target * 1.6 or len(lines) < 2 or not ws:
        return one
    n = max(2, round(total / target))
    goal = total / n
    gaps = []                   # (time of the cut, the pause there, the first line after it)
    for i in range(len(lines) - 1):
        a, b = float(lines[i]["end"]), float(lines[i + 1]["start"])
        gaps.append((_snap((a + b) / 2, fps), b - a, i + 1))
    cuts, last = [], 0.0
    for j in range(1, n):
        want = j * goal
        ok = [g for g in gaps if g[0] > last + 20 and g[0] < total - 20]
        if not ok:
            break
        best = min(ok, key=lambda g: abs(g[0] - want) - 4.0 * min(g[1], 1.5))
        if cuts and best[0] <= cuts[-1][0]:
            continue
        cuts.append(best)
        last = best[0]
    if not cuts:
        return one
    out, t0, line0 = [], 0.0, 0
    for k, (t, _, line1) in enumerate(cuts + [(total, 0.0, len(lines))]):
        mine = [w["i"] for w in ws if line0 <= int(w.get("line", 0)) < line1]
        if mine:
            out.append({"k": len(out), "t0": t0, "t1": t if k < len(cuts) else total, "a": min(mine), "b": max(mine)})
        t0, line0 = t, line1
    return out


# ---------------------------------------------------------------- the score cut into parts ---------------------------

SHOT = re.compile(r"^\s*shot\s+([\w\-]+)")
ENT = re.compile(r"^\s*ent\s+([\w\-]+)")


def _blocks(lines: list[str]) -> list[tuple[str, int, int]]:
    """Each shot's lines: (name, first line (its comments over it), line after its last)."""
    starts = []
    for i, ln in enumerate(lines):
        m = SHOT.match(ln)
        if m:
            j = i
            while j > 0 and lines[j - 1].lstrip().startswith("#"):
                j -= 1
            starts.append((m.group(1), j))
    return [(name, j, starts[k + 1][1] if k + 1 < len(starts) else len(lines)) for k, (name, j) in enumerate(starts)]


def _when(line: str, words: list[dict]) -> float | None:
    """When an action line happens (its time's first part), in the whole video's seconds."""
    tok = line.split()[0] if line.split() else ""
    m = re.match(r"^w(\d+)", tok)
    if m:
        k = min(int(m.group(1)), len(words) - 1)
        return float(words[k]["start"]) if k >= 0 else None
    m = re.match(r"^t(\d*\.?\d+)", tok)
    return float(m.group(1)) if m else None


def _shift(line: str, words: list[dict]) -> str:
    """An action's `tSECONDS` times said from the word before them (`w123+0.40`): a part's words are timed from its
    own start (words.json), so these move with them, and a time before the part (the shot carried in from the part
    before) stays before it."""
    toks = line.split(None, 1)
    if not toks or not re.match(r"^[wt]\d", toks[0]):
        return line
    lead = line[: len(line) - len(line.lstrip())]

    def as_word(m):
        x = float(m.group(1))
        k = max((i for i, w in enumerate(words) if float(w["start"]) <= x), default=0)
        d = x - float(words[k]["start"])
        return f"w{k}+{d:.2f}" if d >= 0 else f"w{k}{d:.2f}"
    tok = re.sub(r"(?<![\w.])t(\d*\.?\d+)", as_word, toks[0])
    return lead + tok + (" " + toks[1] if len(toks) > 1 else "")


def split(score: str, words: list[dict], parts: list[dict]) -> list[str]:
    """Each part's score. A shot goes to the part its first action falls in. A thing a part uses that an earlier
    part made is made again at its start where it was (its `ent` line under its own shot's `shot` line), so a
    thread carried over a cut goes on."""
    lines = score.splitlines()
    blocks = _blocks(lines)
    if not blocks:
        return [score] + [""] * (len(parts) - 1)
    head = lines[: blocks[0][1]]
    owner, prev = [], 0
    for name, a, b in blocks:
        ts = [t for t in (_when(ln, words) for ln in lines[a:b] if not ln.lstrip().startswith(("#", "ent", "shot")))
              if t is not None]
        k = prev
        if ts:
            t = min(ts)
            k = max(prev, max((p["k"] for p in parts if p["t0"] - 0.3 <= t), default=0))
        owner.append(k)
        prev = k
    made: dict[str, tuple[str, str]] = {}       # name -> (its shot's `shot` line, its `ent` line)
    shot_line = {name: lines[next(i for i in range(a, b) if SHOT.match(lines[i]))] for name, a, b in blocks}
    out = []
    for p in parts:
        mine = [blk for blk, k in zip(blocks, owner) if k == p["k"]]
        body = [ln for _, a, b in mine for ln in lines[a:b]]
        # the shot on the screen as the part before ends, played again before this part starts (its times before 0
        # all done by the first frame): the part opens on what was up, and its first camera move goes from there
        before = [blk for blk, k in zip(blocks, owner) if k < p["k"]]
        lead_in = ["# (carried over from the part before: the shot that was up)"] + list(lines[before[-1][1]:before[-1][2]]) \
            if before else []
        body = lead_in + body
        own = {m.group(1) for ln in body if (m := ENT.match(ln))}
        bare = "\n".join(re.sub(r'"[^"]*"', " ", ln.split("#")[0]) for ln in body)    # (not the words in quotes)
        used = set(re.findall(r"[A-Za-z_][\w\-]*", bare))
        carried: dict[str, list[str]] = {}
        todo = [n for n in used if n in made and n not in own]
        seen = set()
        while todo:                             # what is carried, and what it stands on (`on`, `at X.place`)
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            sl, el = made[n]
            carried.setdefault(sl, []).append(el)
            for x in re.findall(r"[A-Za-z_][\w\-]*", re.sub(r'"[^"]*"', " ", el.split(None, 2)[-1] if len(el.split()) > 2 else "")):
                if x in made and x not in own and x not in seen:
                    todo.append(x)
        text = list(head)
        for sl, ents in carried.items():
            text += ["# (carried over from the part before)", sl] + ents + [""]
        text += [_shift(ln, words) for ln in body]
        out.append("\n".join(text) + "\n")
        for name, a, b in mine:
            for ln in lines[a:b]:
                m = ENT.match(ln)
                if m:
                    made[m.group(1)] = (shot_line[name], ln)
    # what follows the last shot (a closing wide shot) goes with the last part
    tail = lines[blocks[-1][2]:] if blocks[-1][2] < len(lines) else []
    if tail and out:
        out[-1] += "\n".join(_shift(ln, words) for ln in tail) + "\n"
    return out


# ---------------------------------------------------------------- a part's files -------------------------------------

def _slice_wav(src: Path, dst: Path, t0: float, t1: float | None) -> None:
    with wave.open(str(src), "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        a = max(0, int(round(t0 * rate)))
        b = n if t1 is None else min(n, int(round(t1 * rate)))
        w.setpos(min(a, n))
        data = w.readframes(max(0, b - a))
        params = w.getparams()
    with wave.open(str(dst), "wb") as o:
        o.setparams(params)
        o.writeframes(data)


def write(run_dir: Path, score: str, words: dict, parts: list[dict]) -> list[Path]:
    """parts/pK/ for each part: its score, its words (times from its start; every word kept, so `w123` is still
    the 123rd), its slice of the voice."""
    texts = split(score, words["words"], parts)
    dirs = []
    for p, text in zip(parts, texts):
        d = run_dir / "parts" / f"p{p['k']}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "video.score").write_text(text)
        last = p["k"] == parts[-1]["k"]
        ws = [{**w, "start": round(float(w["start"]) - p["t0"], 3), "end": round(float(w["end"]) - p["t0"], 3)}
              for w in words["words"]]
        lines = [{**ln, "start": round(float(ln["start"]) - p["t0"], 3), "end": round(float(ln["end"]) - p["t0"], 3)}
                 for ln in words.get("lines", [])]
        (d / "words.json").write_text(json.dumps({"seconds": round(p["t1"] - p["t0"], 4), "lines": lines, "words": ws,
                                                  "part": p}))
        if (run_dir / "voice.wav").exists():
            _slice_wav(run_dir / "voice.wav", d / "voice.wav", p["t0"], None if last else p["t1"])
        dirs.append(d)
    return dirs


def chapters(score: str, words: list[dict], seconds: float) -> list[list]:
    """The whole video's chapters: [[seconds, title]]."""
    import score as S
    try:
        sc = S.parse(score, words, seconds)
    except Exception:  # noqa: BLE001
        return []
    return [[round(a.t0, 3), a.target] for a in sc.acts if a.verb == "chapter"]


def env(p: dict, parts: list[dict], total: float, chaps: list) -> dict:
    """What a part's render or bake is told: no held tail but on the last part; its place in the whole."""
    last = p["k"] == parts[-1]["k"]
    return {"V3_TAIL": str(TAIL if last else 0.0),
            "V3_PART": json.dumps({"k": p["k"], "offset": p["t0"], "total": total + TAIL, "chapters": chaps})}


def manifest(player: Path, parts: list[dict], audio: str | None) -> dict:
    """player/parts.json: each part's folder and frames, in order, and the one soundtrack under them all."""
    out, f0 = [], 0
    info = None
    for p in parts:
        tl = json.loads((player / f"p{p['k']}" / "timeline.json").read_text())
        info = info or tl
        out.append({"dir": f"p{p['k']}/", "f0": f0, "frames": tl["frames"], "t0": p["t0"]})
        f0 += tl["frames"]
    data = {"version": 1, "fps": info["fps"], "frames": f0, "size": info["size"], "bg": info["bg"], "parts": out,
            "audio": audio}
    (player / "parts.json").write_text(json.dumps(data, indent=1))
    return data
