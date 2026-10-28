"""Runs: a video made from a narration, step by step, every step and every model call kept with its time and cost.

A run lives in harness_v3/runs/<id>/: run.json (its settings, steps and calls), narration.txt, voice.wav,
words.json, storyboard.json, video.score, video.mp4, and the critic's frames. The steps, in order:

    voice       the narration spoken and every word timed (voice.py; no model call, no cost)
    storyboard  one model call: the narration cut into shots
    score       one model call a shot, all at once (or a score given by hand: no call)
    assets      the pictures the score asks for, made by the image model (assets.py) and kept
    render      the score played on one clock (render.py)
    critic      frames judged by a vision model (optional)

Each call is recorded: its step, label, model, prompt (system and user), answer, tokens, cost (OpenRouter's own
figure for it, in US dollars), and how long it took. A step can be run again from where it is: a run picks up from
that step (the steps after it are run again too).
"""

from __future__ import annotations

import base64
import signal
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = ROOT / "runs"
sys.path.insert(0, str(HERE))

import assets  # noqa: E402
import prompts  # noqa: E402

STEPS = ["voice", "storyboard", "score", "assets", "render", "critic"]
# The model each kind of call uses, unless a run says otherwise: V3_MODEL_<STEP>, else V3_MODEL. The score step is
# where a stronger model shows most (it places and moves everything); the image model makes the pictures.
MODEL_STEPS = ("storyboard", "score", "critic", "image")


def step_models(given: dict | None = None) -> dict:
    """{step: model} for a new run: what the run was given, else the env's per-step choice, else the default."""
    given = given or {}
    out = {}
    for st in MODEL_STEPS:
        env = os.environ.get("V3_IMAGE_MODEL" if st == "image" else f"V3_MODEL_{st.upper()}", "").strip()
        if st == "critic":
            env = env or os.environ.get("V3_MODEL_VISION", "").strip()
        out[st] = (given.get(st) or "").strip() or env or (assets.DEFAULT_MODEL if st == "image" else "")
    return out
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
_stop: set[str] = set()                      # runs asked to stop (they stop at the next check)
_procs: dict[str, subprocess.Popen] = {}     # a run's voice or render, killed when it is stopped


class Stopped(Exception):
    """The run was stopped by hand."""


def _check(rid: str | None) -> None:
    if rid and rid in _stop:
        raise Stopped("stopped by hand")


def _proc(rid: str, cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """A step's program, killed when its run is stopped (as subprocess.run, output captured)."""
    # Its own process group: a stop kills it and what it started (a render's chunks).
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
                         env={**os.environ, **(env or {})})
    _procs[rid] = p
    try:
        while True:
            try:
                out, err = p.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if rid in _stop:
                    _kill(p)
                    p.communicate()
                    raise Stopped("stopped by hand") from None
    finally:
        _procs.pop(rid, None)
    _check(rid)                                  # killed by stop() itself
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


# ---------------------------------------------------------------- the run on disk --------------------------------------

def run_dir(rid: str) -> Path:
    if not re.fullmatch(r"[\w-]+", rid):
        raise ValueError("bad run id")
    return RUNS / rid


def load(rid: str) -> dict:
    return json.loads((run_dir(rid) / "run.json").read_text())


_mut = threading.RLock()   # a run's record, written by its step and by the shot calls running at once


def save(run: dict) -> None:
    with _mut:
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
                        "speed": float(settings.get("speed") or 1.22), "pause": float(settings.get("pause") or 0.85),
                        "models": step_models(settings.get("models")),
                        "look": settings.get("look") or os.environ.get("V3_LOOK") or "editorial"},
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
    _check(run.get("id"))
    st = run["settings"]
    model = (st.get("models") or {}).get(step) or st["model"]
    call = {"id": uuid.uuid4().hex[:8], "step": step, "label": label, "model": model, "system": system, "user": user,
            "images": len(images or []), "started": time.time(), "status": "running"}
    with _mut:
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
        with _mut:
            call.update({"output": text, "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
                         "reasoning_tokens": thought, "finish": choice.get("finish_reason"), "cost": usage.get("cost"),
                         "status": "done"})
        if not text:
            raise RuntimeError(f"{model} gave no answer (finish: {choice.get('finish_reason')}"
                               + (f"; {thought} tokens spent reasoning" if thought else "")
                               + "): try again, another model, or V3_REASONING=low/none")
        return text
    except Exception as e:
        with _mut:
            call.update({"status": "failed", "error": str(e)[:500]})
        raise
    finally:
        with _mut:
            call["ended"] = time.time()
            call["seconds"] = round(call["ended"] - call["started"], 2)
            save(run)


# ---------------------------------------------------------------- the steps --------------------------------------------

def _voice(run: dict) -> None:
    d = run_dir(run["id"])
    s = run["settings"]
    p = _proc(run["id"], [sys.executable, str(HERE / "voice.py"), str(d / "narration.txt"), str(d), "--voice", s["voice"],
                          "--speed", str(s["speed"]), "--pause", str(s["pause"])])
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
    # A storyboard that was answered but could not be read before (and so never kept) is read again: no new call.
    last = next((c for c in reversed(run["calls"]) if c["step"] == "storyboard" and c.get("output")), None)
    if last and not (d / "storyboard.json").exists() and prompts.parse_storyboard(last["output"], len(words)):
        text = last["output"]
        run["steps"]["storyboard"]["notes"] = ["the last answer read again (no new call)"]
    else:
        system, user = prompts.storyboard_prompt(words)
        text = chat(run, "storyboard", "Storyboard", system, user, max_tokens=900)
    shots = prompts.parse_storyboard(text, len(words))
    if not shots:
        raise RuntimeError(f"the storyboard had no shot lines (name | words wA-wB | plan): {text[:300]}")
    (d / "storyboard.json").write_text(json.dumps(shots, indent=1))
    run["steps"]["storyboard"]["notes"] = run["steps"]["storyboard"].get("notes", []) + [f"{len(shots)} shots"]


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
    todo = [k for k in range(len(shots)) if only is None or k == only]
    # The shots are written at once (V3_SCORE_JOBS calls in flight): each is told the plan of the shot before it,
    # not its score, so none waits for another. A name two shots both make is two things (score.parse).
    jobs = max(1, int(os.environ.get("V3_SCORE_JOBS", "6")))
    with ThreadPoolExecutor(max_workers=min(jobs, len(todo) or 1)) as pool:
        made = {k: pool.submit(_score_shot, run, shots, k, words, shots[k - 1]["plan"] if k else "") for k in todo}
        for k, f in made.items():
            parts[k] = f.result()
    (d / "shots.json").write_text(json.dumps(parts, indent=1))
    look = run["settings"].get("look") or "editorial"
    (d / "video.score").write_text(f"look {look}\n\n" + "\n\n".join(p for p in parts if p) + "\n")
    run["steps"]["score"]["notes"] = [f"{len(todo)} shot(s) scored, {min(jobs, len(todo) or 1)} at once"]


def _assets(run: dict) -> None:
    """The pictures the score asks for (assets.py), made at once (V3_IMAGE_JOBS) and kept; each call recorded with
    its cost. One that cannot be made is drawn as a placeholder and said here; the render goes on."""
    import look
    d = run_dir(run["id"])
    text = (d / "video.score").read_text()
    model = (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL
    wants = [(k, p, lk if lk in look.LOOKS else "paper") for k, p, lk in assets.wants(text)]
    todo = [w for w in wants if not assets.path_for(w[0], w[1], w[2], model).exists()]
    notes = [f"{len(wants)} picture(s) asked for, {len(wants) - len(todo)} kept from before"]
    if not todo:
        run["steps"]["assets"]["notes"] = notes
        return

    def make(item):
        kind, prompt, lk = item
        _check(run["id"])
        call = {"id": uuid.uuid4().hex[:8], "step": "assets", "label": f"{kind}: {prompt[:60]}", "model": model,
                "system": "(image)", "user": assets.prompt_for(kind, prompt, lk), "images": 0, "started": time.time(),
                "status": "running"}
        with _mut:
            run["calls"].append(call)
            save(run)
        try:
            path, usage = assets.generate(kind, prompt, lk, model)
            with _mut:
                call.update({"status": "done", "output": path.name, "cost": usage.get("cost"),
                             "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens")})
            return None
        except Exception as e:  # noqa: BLE001 -- a picture that cannot be made: a placeholder, said
            with _mut:
                call.update({"status": "failed", "error": str(e)[:500]})
            return f"{kind} \"{prompt[:50]}\": {str(e)[:160]}"
        finally:
            with _mut:
                call["ended"] = time.time()
                call["seconds"] = round(call["ended"] - call["started"], 2)
                save(run)

    jobs = max(1, int(os.environ.get("V3_IMAGE_JOBS", "4")))
    with ThreadPoolExecutor(max_workers=min(jobs, len(todo))) as pool:
        failed = [f for f in pool.map(make, todo) if f]
    notes.append(f"{len(todo) - len(failed)} made with {model}")
    notes += [f"not made (a placeholder is drawn): {f}" for f in failed]
    run["steps"]["assets"]["notes"] = notes


def _render(run: dict) -> None:
    d = run_dir(run["id"])
    started = time.time()
    p = _proc(run["id"], [sys.executable, str(HERE / "render.py"), str(d / "video.score"), str(d), str(d / "video.mp4"),
                          "--quality", run["settings"]["quality"]],
              # the pictures are found by the image model they were made with
              env={"V3_IMAGE_MODEL": (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL})
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


RUNNERS = {"voice": _voice, "storyboard": _storyboard, "score": _score, "assets": _assets, "render": _render,
           "critic": _critic}


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
        while not _slots.acquire(timeout=0.5):    # waiting its turn; a stop ends the wait
            if rid in _stop:
                run["status"] = "stopped"
                for s in STEPS[STEPS.index(start):]:
                    run["steps"][s] = {"status": "stopped"}
                save(run)
                _stop.discard(rid)
                _busy.discard(rid)
                return
        run = load(rid)
        run["status"] = "running"
        try:
            for s in STEPS[STEPS.index(start):]:
                step = run["steps"][s]
                if rid in _stop:
                    step["status"] = "stopped"
                    run["status"] = "stopped"
                    continue
                step.update({"status": "running", "started": time.time()})
                save(run)
                try:
                    if s == "score" and shot is not None and s == start:
                        _score(run, only=shot)
                    else:
                        RUNNERS[s](run)
                    step["status"] = "done"
                except Stopped:
                    step["status"] = "stopped"
                    run["status"] = "stopped"
                    continue
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
            if run["status"] != "stopped":
                run["status"] = "done"
        finally:
            save(run)
            _slots.release()
            _stop.discard(rid)
            _busy.discard(rid)


def stop(rid: str) -> bool:
    """Stop a run: it ends at once if it is waiting its turn, its voice or render is killed, and a model call in
    flight is let finish (its cost is kept) but nothing after it runs. False when it was not running."""
    if rid not in _busy:
        return False
    _stop.add(rid)
    p = _procs.get(rid)
    if p and p.poll() is None:
        _kill(p)
    return True


def _kill(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, AttributeError):
        p.kill()


def stop_all() -> list[str]:
    return [rid for rid in list(_busy) if stop(rid)]


def recover() -> list[str]:
    """Runs the server was making when it stopped (left "running" or "queued") are marked stopped, so they can be
    run again from a step."""
    out = []
    for p in RUNS.glob("*/run.json"):
        try:
            run = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        if run.get("status") in ("running", "queued", "new") and run["id"] not in _busy:
            run["status"] = "stopped"
            for st in run["steps"].values():
                if st.get("status") in ("running", "waiting"):
                    st["status"] = "stopped"
            for c in run.get("calls", []):
                if c.get("status") == "running":
                    c.update({"status": "failed", "error": "the server stopped during this call"})
            save(run)
            out.append(run["id"])
    return out


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
