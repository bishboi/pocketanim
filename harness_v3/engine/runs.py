"""Runs: a video made from a narration, step by step, every step and every model call kept with its time and cost.

A run lives in harness_v3/runs/<id>/: run.json (its settings, steps and calls), narration.txt, voice.wav,
words.json, storyboard.json, video.score, video.mp4, and the critic's frames. The steps, in order:

    voice       the narration spoken and every word timed (voice.py; no model call, no cost)
    storyboard  one model call: the narration cut into shots
    score       one model call a shot, in order (or a score given by hand: no call)
    render      the score played on one clock (render.py)
    critic      frames judged by a vision model (optional)

Each call is recorded: its step, label, model, prompt (system and user), answer, tokens, cost (OpenRouter's own
figure for it, in US dollars), and how long it took. A step can be run again from where it is: a run picks up from
that step (the steps after it are run again too).
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = ROOT / "runs"
sys.path.insert(0, str(HERE))

import prompts  # noqa: E402

STEPS = ["voice", "storyboard", "score", "render", "critic"]
DEFAULT_MODEL = os.environ.get("V3_MODEL", "anthropic/claude-haiku-4.5")
SHOT_STEP = 18.0
# Room for a reasoning model's thinking on top of each call's answer (only the tokens used are paid for), and how
# hard it thinks: V3_REASONING=minimal|low|medium|high, or none to send nothing.
ROOM = int(os.environ.get("V3_ROOM", "8000"))
REASONING = os.environ.get("V3_REASONING", "low").strip().lower()
_locks: dict[str, threading.Lock] = {}
_busy: set[str] = set()
# How many runs make their video at once (the rest wait, "queued"): voice and render are heavy.
_slots = threading.Semaphore(int(os.environ.get("V3_PARALLEL", "1")))


# ---------------------------------------------------------------- the run on disk --------------------------------------

def run_dir(rid: str) -> Path:
    if not re.fullmatch(r"[\w-]+", rid):
        raise ValueError("bad run id")
    return RUNS / rid


def load(rid: str) -> dict:
    return json.loads((run_dir(rid) / "run.json").read_text())


def save(run: dict) -> None:
    d = run_dir(run["id"])
    d.mkdir(parents=True, exist_ok=True)
    run["cost"] = round(sum(c.get("cost") or 0 for c in run["calls"]), 6)
    run["tokens"] = sum((c.get("tokens_in") or 0) + (c.get("tokens_out") or 0) for c in run["calls"])
    tmp = d / "run.json.tmp"
    tmp.write_text(json.dumps(run, indent=1))
    tmp.replace(d / "run.json")


def listing() -> list[dict]:
    out = []
    for p in sorted(RUNS.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            r = json.loads(p.read_text())
        except Exception:  # noqa: BLE001 -- a run being written
            continue
        out.append({k: r.get(k) for k in ("id", "title", "created", "cost", "tokens", "status")} |
                   {"seconds": (r.get("words") or {}).get("seconds")})
    return out


def create(title: str, narration: str, settings: dict) -> dict:
    rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    run = {"id": rid, "title": title.strip() or narration.strip().split("\n")[0][:60], "created": time.time(),
           "status": "new",
           "settings": {"model": settings.get("model") or DEFAULT_MODEL, "voice": settings.get("voice") or "en_US-ryan-high",
                        "quality": settings.get("quality") or "m", "critic": bool(settings.get("critic")),
                        "speed": float(settings.get("speed") or 1.22), "pause": float(settings.get("pause") or 0.85)},
           "steps": {s: {"status": "waiting"} for s in STEPS}, "calls": [], "cost": 0.0, "tokens": 0}
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "narration.txt").write_text(narration.strip() + "\n")
    if settings.get("book"):
        run["settings"]["book"] = settings["book"]
    if settings.get("score"):
        (d / "given.score").write_text(settings["score"])
        run["settings"]["given_score"] = True
    save(run)
    return run


# ---------------------------------------------------------------- model calls ------------------------------------------

def chat(run: dict, step: str, label: str, system: str, user: str, images: list[str] | None = None,
         max_tokens: int = 1800, saver=None) -> str:
    """One OpenRouter call, recorded on the run (its prompt, answer, tokens, cost, time). A book's calls are kept on
    the book (`saver` writes it)."""
    save = saver or globals()["save"]
    model = run["settings"]["model"]
    call = {"id": uuid.uuid4().hex[:8], "step": step, "label": label, "model": model, "system": system, "user": user,
            "images": len(images or []), "started": time.time(), "status": "running"}
    run["calls"].append(call)
    save(run)
    key = os.environ.get("OPENROUTER_API_KEY")
    try:
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set: set the key and run this step again")
        content = [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": i}} for i in images or []]
        body = {"model": model, "max_tokens": max_tokens + ROOM, "temperature": 0.4, "usage": {"include": True},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": content if images else user}]}
        if REASONING != "none":  # a reasoning model thinks briefly (ignored by the others)
            body["reasoning"] = {"effort": REASONING, "exclude": True}
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "harness-v3/1.0", "HTTP-Referer": "https://github.com/bishboi/pocketanim",
                                          "X-Title": "harness v3"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            said = e.read()[:600].decode(errors="replace")
            try:
                said = json.loads(said).get("error", {}).get("message") or said
            except Exception:  # noqa: BLE001 -- not JSON: said as it came
                pass
            raise RuntimeError(f"OpenRouter refused the call ({e.code}): {said}") from e
        if out.get("error"):
            raise RuntimeError(f"OpenRouter: {out['error'].get('message') or out['error']}")
        usage = out.get("usage") or {}
        choice = (out.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content") or "").strip()
        thought = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        call.update({"output": text, "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
                     "reasoning_tokens": thought, "finish": choice.get("finish_reason"), "cost": usage.get("cost"),
                     "status": "done"})
        if not text:
            raise RuntimeError(f"{model} gave no answer (finish: {choice.get('finish_reason')}"
                               + (f"; {thought} tokens spent reasoning" if thought else "")
                               + "): try again, another model, or V3_REASONING=low/none")
        return text
    except Exception as e:
        call.update({"status": "failed", "error": str(e)[:500]})
        raise
    finally:
        call["ended"] = time.time()
        call["seconds"] = round(call["ended"] - call["started"], 2)
        save(run)


# ---------------------------------------------------------------- the steps --------------------------------------------

def _voice(run: dict) -> None:
    d = run_dir(run["id"])
    s = run["settings"]
    p = subprocess.run([sys.executable, str(HERE / "voice.py"), str(d / "narration.txt"), str(d), "--voice", s["voice"],
                        "--speed", str(s["speed"]), "--pause", str(s["pause"])], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-1500:])
    words = json.loads((d / "words.json").read_text())
    run["words"] = {"seconds": words["seconds"], "count": len(words["words"])}
    run["steps"]["voice"]["notes"] = [f"{len(words['lines'])} lines, {len(words['words'])} words, {words['seconds']:.1f} s"]


def _words(run: dict) -> list[dict]:
    return json.loads((run_dir(run["id"]) / "words.json").read_text())["words"]


def _storyboard(run: dict) -> None:
    d = run_dir(run["id"])
    if run["settings"].get("given_score"):
        run["steps"]["storyboard"]["notes"] = ["a score was given by hand: no storyboard"]
        return
    words = _words(run)
    system, user = prompts.storyboard_prompt(words)
    text = chat(run, "storyboard", "Storyboard", system, user, max_tokens=900)
    shots = []
    for line in text.splitlines():
        m = re.search(r"SHOT\s+(\S+)\s*\|\s*words\s*w(\d+)\s*-\s*w(\d+)\s*\|(.*)", line, re.I)
        if m:
            shots.append({"name": re.sub(r"\W", "", m.group(1)) or f"s{len(shots)}", "a": int(m.group(2)),
                          "b": int(m.group(3)), "plan": m.group(4).strip()})
    if not shots:
        raise RuntimeError(f"the storyboard had no SHOT lines: {text[:300]}")
    (d / "storyboard.json").write_text(json.dumps(shots, indent=1))
    run["steps"]["storyboard"]["notes"] = [f"{len(shots)} shots"]


def _score_shot(run: dict, shots: list[dict], k: int, words: list[dict], before: str) -> str:
    s = shots[k]
    at = ((k % 3) * SHOT_STEP, -(k // 3) * 11.0)
    mine = [w for w in words if s["a"] <= w["i"] <= s["b"]]
    system, user = prompts.score_prompt(s["plan"], mine, at, before)
    text = chat(run, "score", f"Score: shot {k + 1} ({s['name']})", system, user)
    text = re.sub(r"^```\w*|```$", "", text.strip(), flags=re.M).strip()
    if not re.search(r"^\s*shot\s", text, re.M):
        text = f"shot {s['name']} at {at[0]:g},{at[1]:g}\n" + text
    return f"# ---- {s['name']}: {s['plan'][:90]}\n{text}"


def _score(run: dict, only: int | None = None) -> None:
    d = run_dir(run["id"])
    if run["settings"].get("given_score"):
        (d / "video.score").write_text((d / "given.score").read_text())
        run["steps"]["score"]["notes"] = ["the score given by hand"]
        return
    shots = json.loads((d / "storyboard.json").read_text())
    words = _words(run)
    parts = json.loads((d / "shots.json").read_text()) if only is not None and (d / "shots.json").exists() else [None] * len(shots)
    before = ""
    for k in range(len(shots)):
        if only is None or k == only:
            parts[k] = _score_shot(run, shots, k, words, before)
            (d / "shots.json").write_text(json.dumps(parts, indent=1))
        before = " ".join(re.findall(r"^\s*ent\s+(\S+)", parts[k] or "", re.M))
    (d / "video.score").write_text("look paper\n\n" + "\n\n".join(p for p in parts if p) + "\n")
    run["steps"]["score"]["notes"] = [f"{len(shots)} shots scored"]


def _render(run: dict) -> None:
    d = run_dir(run["id"])
    started = time.time()
    p = subprocess.run([sys.executable, str(HERE / "render.py"), str(d / "video.score"), str(d), str(d / "video.mp4"),
                        "--quality", run["settings"]["quality"]], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-1500:])
    notes = [l[6:] for l in p.stdout.splitlines() if l.startswith("note: ")]
    notes += [l for l in p.stderr.splitlines() if l.startswith("score line")]
    run["steps"]["render"]["notes"] = notes[:40] or [f"rendered in {time.time() - started:.0f} s"]
    run["video"] = f"video.mp4?v={int(time.time())}"


def _critic(run: dict) -> None:
    if not run["settings"].get("critic"):
        run["steps"]["critic"]["notes"] = ["off for this run"]
        return
    d = run_dir(run["id"])
    words = _words(run)
    text = (d / "video.score").read_text()
    times = sorted({float(words[int(m)]["start"]) + 0.5 for m in re.findall(r"^w(\d+)", text, re.M)
                    if int(m) < len(words)})[::3][:12]
    images, said = [], []
    for t in times:
        f = d / f"critic-{t:.1f}.jpg"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(d / "video.mp4"),
                        "-frames:v", "1", "-vf", "scale=640:-1", str(f)], check=True)
        images.append("data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode())
        near = [w["w"] for w in words if abs(float(w["start"]) - t) < 1.5]
        said.append(f"t{t:.1f}: \"{' '.join(near)}\"")
    verdict = chat(run, "critic", "Critic", prompts.CRITIC, "FRAMES, in order:\n" + "\n".join(said), images=images,
                   max_tokens=500)
    run["steps"]["critic"]["notes"] = [l for l in verdict.splitlines() if l.strip()][:20]


RUNNERS = {"voice": _voice, "storyboard": _storyboard, "score": _score, "render": _render, "critic": _critic}


def go(rid: str, start: str = "voice", shot: int | None = None) -> None:
    """Run the steps from `start` on (in this thread). Each step's status, times and notes are kept."""
    lock = _locks.setdefault(rid, threading.Lock())
    with lock:
        _busy.add(rid)
        run = load(rid)
        run["status"] = "queued"
        for s in STEPS[STEPS.index(start):]:
            run["steps"][s] = {"status": "waiting"}
        save(run)
        _slots.acquire()
        run = load(rid)
        run["status"] = "running"
        try:
            for s in STEPS[STEPS.index(start):]:
                step = run["steps"][s]
                step.update({"status": "running", "started": time.time()})
                save(run)
                try:
                    if s == "score" and shot is not None and s == start:
                        _score(run, only=shot)
                    else:
                        RUNNERS[s](run)
                    step["status"] = "done"
                except Exception as e:  # noqa: BLE001 -- the step failed: said, and the run stops there
                    step.update({"status": "failed", "error": str(e)[:1500]})
                    traceback.print_exc()
                    run["status"] = "failed"
                    return
                finally:
                    step["ended"] = time.time()
                    step["seconds"] = round(step["ended"] - step["started"], 1)
                    step["cost"] = round(sum(c.get("cost") or 0 for c in run["calls"] if c["step"] == s
                                             and c["started"] >= step["started"]), 6)
                    save(run)
            run["status"] = "done"
        finally:
            save(run)
            _slots.release()
            _busy.discard(rid)


def start(rid: str, step: str = "voice", shot: int | None = None) -> None:
    if rid in _busy:
        raise RuntimeError("this run is busy: wait for it")
    if step not in STEPS:
        raise ValueError(f"no step {step!r}")
    _busy.add(rid)
    threading.Thread(target=go, args=(rid, step, shot), daemon=True).start()


def set_score(rid: str, text: str) -> None:
    """A score changed by hand: kept, and the run rendered again from it (running the score step again writes a
    new one over it)."""
    (run_dir(rid) / "video.score").write_text(text)
    run = load(rid)
    run["edited"] = time.time()
    save(run)
    start(rid, "render")
