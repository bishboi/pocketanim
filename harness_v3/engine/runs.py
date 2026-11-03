"""Runs: a video made from a narration, step by step, every step and every model call kept with its time and cost.

A run lives in harness_v3/runs/<id>/: run.json (its settings, steps and calls), narration.txt, voice.wav,
words.json, storyboard.json, video.score, video.mp4, and the critic's frames. The steps, in order:

    voice       the narration spoken and every word timed (voice.py; no model call, no cost)
    storyboard  one model call: the narration cut into shots
    score       one model call a shot, all at once (or a score given by hand: no call)
    assets      the pictures the score asks for, made by the image model (assets.py) and kept
    timeline    the video as a timeline the player draws (timeline.py; player/): watched with no MP4
    render      the MP4 (render.py): only when the run asks for one (slow), or run by hand
    render      the score played on one clock (render.py)
    critic      frames judged by a vision model (optional)

A long narration (more than about 4 minutes) is made in parts (parts.py): one voice, one cast call, a storyboard
call a part, then its layout, timeline and render a part at a time (V3_PART_JOBS at once), joined by the player
(player/parts.json) and by the MP4.

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
import library  # noqa: E402
import parts as PT  # noqa: E402
import prompts  # noqa: E402
import score as S  # noqa: E402

STEPS = ["voice", "storyboard", "score", "assets", "layout", "timeline", "render", "critic"]
# (the director's pass, _director, is no longer a step: it rewrote every shot; the score step checks and fixes its
# own shots instead)
# The MP4 (Manim) is slow and the Player needs none: it is made only when a run asks for it (`mp4`, V3_RENDER_MP4),
# or when its render step is run by hand.
RENDER_MP4 = os.environ.get("V3_RENDER_MP4", "0").strip().lower() in ("1", "true", "yes", "on")
# The model each kind of call uses, unless a run says otherwise: V3_MODEL_<STEP>, else V3_MODEL. The score step is
# where a stronger model shows most (it places and moves everything); the image model makes the pictures.
MODEL_STEPS = ("storyboard", "score", "critic", "image", "image_small", "image_labeled")
# The image models' settings in the environment (blank small/labelled: the image model).
IMAGE_ENV = {"image": "V3_IMAGE_MODEL", "image_small": "V3_IMAGE_MODEL_SMALL", "image_labeled": "V3_IMAGE_MODEL_LABELED"}


def step_models(given: dict | None = None) -> dict:
    """{step: model} for a new run: what the run was given, else the env's per-step choice, else the default."""
    given = given or {}
    out = {}
    for st in MODEL_STEPS:
        env = os.environ.get(IMAGE_ENV.get(st, f"V3_MODEL_{st.upper()}"), "").strip()
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
_procs: dict[str, set] = {}     # a run's voice, renders or bakes (a long video's parts at once), killed when stopped


class Stopped(Exception):
    """The run was stopped by hand."""


def _check(rid: str | None) -> None:
    if rid and rid in _stop:
        raise Stopped("stopped by hand")


def _proc(rid: str, cmd: list[str], env: dict | None = None, on_line=None) -> subprocess.CompletedProcess:
    """A step's program, killed when its run is stopped (as subprocess.run, output captured). Its output is read as
    it comes, each line given to `on_line` (progress and log)."""
    # Its own process group: a stop kills it and what it started (a render's chunks).
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
                         bufsize=1, env={**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})})
    _procs.setdefault(rid, set()).add(p)
    out: list[str] = []
    err: list[str] = []

    def pump(stream, buf):
        for line in iter(stream.readline, ""):
            buf.append(line)
            if on_line:
                try:
                    on_line(line.rstrip("\n"))
                except Exception:  # noqa: BLE001 -- a progress line that cannot be read is let be
                    pass
        stream.close()

    readers = [threading.Thread(target=pump, args=(p.stdout, out), daemon=True),
               threading.Thread(target=pump, args=(p.stderr, err), daemon=True)]
    for t in readers:
        t.start()
    try:
        while p.poll() is None:
            time.sleep(0.3)
            if rid in _stop:
                _kill(p)
                p.wait()
                raise Stopped("stopped by hand")
        for t in readers:
            t.join(timeout=5)
    finally:
        _procs.get(rid, set()).discard(p)
    _check(rid)                                  # killed by stop() itself
    return subprocess.CompletedProcess(cmd, p.returncode, "".join(out), "".join(err))


PROGRESS = re.compile(r"^progress: (\d+)/(\d+)\s*(.*)$")
NOISE = re.compile(r"^\s*$|Manim Community|^\s*(INFO|WARNING)\s|scene_file_writer|^\s+[\w'{}:,\-]+\s*$|Some options were not")


def follow(run: dict, box: dict):
    """An `on_line` for _proc: progress lines become box["progress"] {done, total, what, eta}, the rest the last
    lines of box["log"]; the run is saved now and then, so the page shows it moving."""
    state = {"saved": 0.0, "t0": None, "d0": 0}

    def on_line(line: str) -> None:
        m = PROGRESS.match(line)
        with _mut:
            if m:
                done, total = int(m.group(1)), int(m.group(2))
                now = time.time()
                if state["t0"] is None or done < state["d0"]:
                    state["t0"], state["d0"] = now, done
                rate = (done - state["d0"]) / max(1e-6, now - state["t0"])
                eta = (total - done) / rate if rate > 0 and done > state["d0"] else None
                box["progress"] = {"done": done, "total": total, "what": m.group(3) or "frames",
                                   "eta": round(eta) if eta is not None else None}
            elif not NOISE.search(line):
                log = box.setdefault("log", [])
                log.append(line[:300])
                del log[:-40]
            if time.time() - state["saved"] > 0.8:
                state["saved"] = time.time()
                save(run)
    return on_line


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
                   {"seconds": (r.get("words") or {}).get("seconds"),
                    "language": (r.get("settings") or {}).get("language") or "en"})
    return out


LANGUAGES = {"en": "English", "hinglish": "Hinglish"}     # hinglish: everyday Hindi in Roman letters, English words in it


def default_voice() -> str:
    """Gemini TTS (V3_TTS_VOICE, Kore) when a Gemini key is set, else the offline Piper voice."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini:" + (os.environ.get("V3_TTS_VOICE") or "Kore")
    return "en_US-ryan-high"


def create(title: str, narration: str, settings: dict) -> dict:
    rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    run = {"id": rid, "title": title.strip() or narration.strip().split("\n")[0][:60], "created": time.time(),
           "status": "new",
           "settings": {"model": settings.get("model") or DEFAULT_MODEL, "voice": settings.get("voice") or default_voice(),
                        "language": settings.get("language") if settings.get("language") in LANGUAGES else "en",
                        "quality": settings.get("quality") or "m", "critic": bool(settings.get("critic")),
                        "speed": float(settings.get("speed") or 1.22), "pause": float(settings.get("pause") or 0.85),
                        "models": step_models(settings.get("models")),
                        "look": settings.get("look") or os.environ.get("V3_LOOK") or "editorial",
                        "mp4": bool(settings["mp4"]) if settings.get("mp4") is not None else RENDER_MP4},
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
         max_tokens: int = 1800, saver=None, model: str | None = None) -> str:
    """One OpenRouter call, recorded on the run (its prompt, answer, tokens, cost, time). A book's calls are kept on
    the book (`saver` writes it)."""
    save = saver or globals()["save"]
    _check(run.get("id"))
    st = run["settings"]
    model = model or (st.get("models") or {}).get(step) or st["model"]
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
                          "--speed", str(s["speed"]), "--pause", str(s["pause"]), "--language", s.get("language") or "en"],
              on_line=follow(run, run["steps"]["voice"]))
    if p.returncode != 0:
        raise RuntimeError(_tail(p))
    words = json.loads((d / "words.json").read_text())
    run["words"] = {"seconds": words["seconds"], "count": len(words["words"])}
    run["steps"]["voice"]["notes"] = [f"{len(words['lines'])} lines, {len(words['words'])} words, {words['seconds']:.1f} s"]
    ps = _parts(run, fresh=True)
    if len(ps) > 1:
        run["steps"]["voice"]["notes"].append(
            f"a long video: {len(ps)} parts of about {words['seconds'] / len(ps) / 60:.1f} min, each laid out and "
            "baked by itself (at once), then joined")


def _parts(run: dict, fresh: bool = False) -> list[dict]:
    """The run's parts (parts.py): one for a short video; a long one cut at pauses into parts of V3_PART_SECONDS."""
    d = run_dir(run["id"])
    p = d / "parts.json"
    if p.exists() and not fresh:
        return json.loads(p.read_text())
    words = json.loads((d / "words.json").read_text())
    ps = PT.parts_of(words)
    p.write_text(json.dumps(ps, indent=1))
    return ps


def _words(run: dict) -> list[dict]:
    return json.loads((run_dir(run["id"]) / "words.json").read_text())["words"]


def _storyboard(run: dict) -> None:
    d = run_dir(run["id"])
    if run["settings"].get("given_score"):
        run["steps"]["storyboard"]["notes"] = ["a score was given by hand: no storyboard"]
        return
    words = _words(run)
    if len(_parts(run)) > 1:
        return _storyboard_long(run)
    # A storyboard that was answered but could not be read before (and so never kept) is read again: no new call.
    last = next((c for c in reversed(run["calls"]) if c["step"] == "storyboard" and c.get("output")), None)
    if last and not (d / "storyboard.json").exists() and prompts.parse_storyboard(last["output"], len(words)):
        text = last["output"]
        run["steps"]["storyboard"]["notes"] = ["the last answer read again (no new call)"]
    else:
        system, user = prompts.storyboard_prompt(words, language=_lang(run))
        text = chat(run, "storyboard", "Storyboard", system, user, max_tokens=1300)
    shots = prompts.parse_storyboard(text, len(words))
    if not shots:
        raise RuntimeError(f"the storyboard had no shot lines (name | words wA-wB | plan): {text[:300]}")
    (d / "storyboard.json").write_text(json.dumps(shots, indent=1))
    cast = prompts.parse_cast(text)             # the characters seen in two shots or more, each made once
    (d / "cast.score").write_text("\n".join(cast) + ("\n" if cast else ""))
    if cast:
        run["steps"]["storyboard"]["notes"] = run["steps"]["storyboard"].get("notes", []) + [
            f"cast: {', '.join(c.split()[1] for c in cast)}"]
    run["steps"]["storyboard"]["notes"] = run["steps"]["storyboard"].get("notes", []) + [f"{len(shots)} shots"]


def _storyboard_long(run: dict) -> None:
    """A long video's storyboard: its cast once (one call over the whole narration), then each part's shots (one
    call a part, all at once), told what came just before and who the cast are; the shots joined in order, each
    name kept unique."""
    d = run_dir(run["id"])
    words = _words(run)
    ps = _parts(run)
    system, user = prompts.cast_prompt(words, _lang(run))
    text = chat(run, "storyboard", "Cast (the whole video)", system, user, max_tokens=900)
    cast = prompts.parse_cast(text)
    (d / "cast.score").write_text("\n".join(cast) + ("\n" if cast else ""))
    minutes = float(words[-1]["end"]) / 60

    def one(p):
        mine = [w for w in words if p["a"] <= w["i"] <= p["b"]]
        before = " ".join(w["w"] for w in words[max(0, p["a"] - 40):p["a"]])
        info = {"k": p["k"], "n": len(ps), "minutes": minutes, "seconds": p["t1"] - p["t0"]}
        system, user = prompts.storyboard_prompt(mine, info, cast, before, _lang(run))
        out = chat(run, "storyboard", f"Storyboard: part {p['k'] + 1} of {len(ps)}", system, user,
                   max_tokens=400 + int(14 * (p["t1"] - p["t0"])))
        shots = prompts.parse_storyboard(out, len(words))
        if not shots:
            raise RuntimeError(f"part {p['k'] + 1}'s storyboard had no shot lines: {out[:300]}")
        return shots
    jobs = max(1, int(os.environ.get("V3_SCORE_JOBS", "6")))
    with ThreadPoolExecutor(max_workers=min(jobs, len(ps))) as pool:
        made = list(pool.map(one, ps))
    shots, names = [], set()
    for p, part_shots in zip(ps, made):
        # each part's shots inside its own words, covering them all, in order
        part_shots = [x for x in part_shots if x["b"] >= p["a"] and x["a"] <= p["b"]]
        for x in part_shots:
            x["a"], x["b"] = max(x["a"], p["a"]), min(x["b"], p["b"])
        part_shots.sort(key=lambda x: x["a"])
        if part_shots:
            part_shots[0]["a"] = p["a"]
            part_shots[-1]["b"] = p["b"]
        for x in part_shots:
            while x["name"] in names:
                x["name"] = f"{x['name']}_{p['k'] + 1}"
            names.add(x["name"])
            x["part"] = p["k"]
            shots.append(x)
    (d / "storyboard.json").write_text(json.dumps(shots, indent=1))
    run["steps"]["storyboard"]["notes"] = [f"{len(shots)} shots in {len(ps)} parts"] + (
        [f"cast: {', '.join(c.split()[1] for c in cast)}"] if cast else [])


def _lang(run: dict) -> str:
    return run["settings"].get("language") or "en"


def _chapter_lines(words: list[dict]) -> str:
    """`wN chapter "TITLE"` for each chapter the narration marks (`# Title`), on its first word."""
    out = []
    for w in words:
        if w.get("chapter"):
            out.append(f'w{w["i"]} chapter "{str(w["chapter"]).replace(chr(34), chr(39))}"')
    return "\n".join(out) + ("\n" if out else "")


def _cast(run: dict) -> list[str]:
    p = run_dir(run["id"]) / "cast.score"
    return [ln for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []


def _score_shot(run: dict, shots: list[dict], k: int, words: list[dict], before: str) -> str:
    s = shots[k]
    at = ((k % 3) * SHOT_STEP, -(k // 3) * 11.0)
    mine = [w for w in words if s["a"] <= w["i"] <= s["b"]]
    system, user = prompts.score_prompt(s["plan"], mine, at, before, _cast(run), _lang(run), before)
    text = chat(run, "score", f"Score: shot {k + 1} ({s['name']})", system, user)
    text = re.sub(r"^```\w*|```$", "", text.strip(), flags=re.M).strip()
    if not re.search(r"^\s*shot\s", text, re.M):
        text = f"shot {s['name']} at {at[0]:g},{at[1]:g}\n" + text
    name = re.sub(r"\W+", "_", s["name"]).strip("_") or f"shot{k + 1}"
    if re.search(r"^\s*shot\s+(at|zoom)\b", text, re.M):
        # `shot at X,Y` (no name): the storyboard's, and a camera sent `at X,Y` goes to it
        text = re.sub(r"^(\s*shot\s+)(at|zoom)\b", rf"\g<1>{name} \2", text, flags=re.M)
        text = re.sub(r"^(\S+\s+cam\s+)at\s+-?[\d.]+,-?[\d.]+", rf"\g<1>{name}", text, flags=re.M)
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
    fixed = _check_shots(run, shots, parts, words, todo)
    (d / "shots.json").write_text(json.dumps(parts, indent=1))
    look = run["settings"].get("look") or "editorial"
    cast = "\n".join(_cast(run))
    body = "\n\n".join(p for p in parts if p)
    chaps = _chapter_lines(words)
    if chaps:                                   # the narration's own chapters (`# Title` lines), not the model's
        body = re.sub(r"(?m)^\S+\s+chapter\s.*\n?", "", body)
    (d / "video.score").write_text(f"look {look}\n" + (cast + "\n" if cast else "") + chaps + "\n" + body + "\n")
    run["steps"]["score"]["notes"] = [f"{len(todo)} shot(s) scored, {min(jobs, len(todo) or 1)} at once"] + fixed


def _shot_problems(parts: list, k: int, words: list[dict], cast: set[str]) -> list[str]:
    """What is wrong with shot k as written, that its writer can fix: a line the engine cannot read, a thing used
    that no shot so far makes, no camera move on its first word, a stretch of more than 3.5 s with nothing
    happening, too many things, long words on the screen."""
    block = parts[k] or ""
    out = []
    made = set(cast)
    for p in parts[:k + 1]:
        made |= set(re.findall(r"(?m)^\s*ent\s+([\w\-]+)", p or ""))
    acts = []
    for ln in block.splitlines():
        t = ln.split("#")[0].split()
        if len(t) < 2 or not re.match(r"^[wt]\d", t[0]):
            continue
        if t[1] not in S.KNOWN_VERBS:
            out.append(f"`{' '.join(t)[:60]}`: there is no verb `{t[1]}`")
            continue
        m = re.match(r"^w(\d+)", t[0])
        when = float(words[min(int(m.group(1)), len(words) - 1)]["start"]) if m else (
            float(re.match(r"^t(\d*\.?\d+)", t[0]).group(1)) if re.match(r"^t(\d*\.?\d+)", t[0]) else None)
        acts.append((when, t[1], t[2] if len(t) > 2 else ""))
        if t[1] not in ("cam", "chapter") and len(t) > 2:
            for name in t[2].split(","):
                base = re.sub(r"\[.*$", "", name).split(".", 1)[0]
                if base and base not in made:
                    out.append(f"`{' '.join(t)[:60]}`: nothing named `{base}` is made (give it an `ent` line in this "
                               "shot, or use the name the shot before gives it)")
    if not acts:
        return ["no actions at all"]
    acts.sort(key=lambda a: a[0] if a[0] is not None else 0)
    if acts[0][1] != "cam":
        out.append("its first action is not the camera: start with `wA cam SHOT` on its first word")
    span = [w for w in words if w["i"] in {int(x) for x in re.findall(r"\bw(\d+)", block)}]
    times = [a[0] for a in acts if a[0] is not None]
    if span and times:
        edge = sorted(set(times + [float(span[-1]["end"])]))
        for x, y in zip(edge, edge[1:]):
            if y - x > 3.5:
                near = [w for w in words if x < float(w["start"]) < y]
                if near:
                    out.append(f"nothing happens for {y - x:.1f} s (from w{near[0]['i']} to w{near[-1]['i']}): land an "
                               "action on a word in between (a move, a mark, a count, the camera)")
    ents = re.findall(r"(?m)^\s*ent\s+([\w\-]+)\s+(\w+)\s*(\"[^\"]*\")?", block)
    if len(ents) > 9:
        out.append(f"{len(ents)} things in one shot: keep it to about six to eight, and take out what the story has left")
    for name, kind, words_ in ents:
        if kind in ("text", "tag", "label", "title", "card") and words_ and len(words_.strip('"').split()) > 5:
            out.append(f"`{name}` writes {len(words_.strip(chr(34)).split())} words on the screen: 1-4")
    return out


def _check_shots(run: dict, shots: list, parts: list, words: list[dict], todo: list[int]) -> list[str]:
    """Each shot just written checked (_shot_problems) with the whole score in view; one with problems written again,
    once, told exactly what is wrong and shown the shot before as it was written (all at once). The new one is kept
    only when it has fewer problems."""
    if os.environ.get("V3_SCORE_CHECK", "1").strip() == "0":
        return []
    cast = {c.split()[1] for c in _cast(run) if len(c.split()) > 1}
    bad = {k: _shot_problems(parts, k, words, cast) for k in todo if parts[k]}
    bad = {k: v for k, v in bad.items() if v}
    if not bad:
        return ["every shot checked: nothing to fix"]

    def fix(k: int):
        s = shots[k]
        at = ((k % 3) * SHOT_STEP, -(k // 3) * 11.0)
        mine = [w for w in words if s["a"] <= w["i"] <= s["b"]]
        before = shots[k - 1]["plan"] if k else ""
        system, user = prompts.score_prompt(s["plan"], mine, at, before, _cast(run), _lang(run), before)
        user += ("\n\nTHE SHOT BEFORE, AS WRITTEN (what it makes is up as this shot starts, unless it takes it out):\n"
                 + (parts[k - 1] or "(none)" if k else "(this is the first shot)")
                 + f"\n\nYOUR SHOT AS WRITTEN:\n{parts[k]}\n\nITS PROBLEMS:\n" + "\n".join(f"- {p}" for p in bad[k])
                 + "\n\nWrite the shot's lines again with these fixed; keep everything else as it is.")
        try:
            out = chat(run, "score", f"Score fix: shot {k + 1} ({s['name']})", system, user)
        except Exception:  # noqa: BLE001 -- kept as it was
            return k, None
        out = re.sub(r"^```\w*|```$", "", out.strip(), flags=re.M).strip()
        if not re.search(r"^\s*shot\s", out, re.M):
            return k, None
        head = "\n".join(ln for ln in (parts[k] or "").splitlines() if ln.startswith("# ----"))
        return k, (head + "\n" + out).strip()
    jobs = max(1, int(os.environ.get("V3_SCORE_JOBS", "6")))
    with ThreadPoolExecutor(max_workers=min(jobs, len(bad))) as pool:
        tried = list(pool.map(fix, sorted(bad)))
    kept = 0
    for k, new in tried:
        if not new:
            continue
        trial = list(parts)
        trial[k] = new
        if len(_shot_problems(trial, k, words, cast)) < len(bad[k]):
            parts[k] = new
            kept += 1
    left = sum(len(_shot_problems(parts, k, words, cast)) for k in bad)
    return [f"{len(bad)} shot(s) had problems ({sum(len(v) for v in bad.values())}); {kept} rewritten, "
            f"{left} problem(s) left for the layout check"] + [f"shot {k + 1}: {v[0]}" for k, v in list(bad.items())[:8]]


def _director(run: dict) -> None:
    """The director's pass (V3_DIRECTOR=0: none): the shots read together, about V3_DIRECTOR_SHOTS (6) at a time
    (all the windows at once), and rewritten for continuity, a clean stage, pacing and variety. A shot comes back
    only if it reads at least as well as it was (no line more left out); else it stays as it was."""
    d = run_dir(run["id"])
    box = run["steps"]["director"]
    if os.environ.get("V3_DIRECTOR", "1").strip() == "0":
        box["notes"] = ["off (V3_DIRECTOR=0)"]
        return
    if run["settings"].get("given_score"):
        box["notes"] = ["a score was given by hand: left as it is"]
        return
    text = (d / "video.score").read_text()
    (d / "video.before-director.score").write_text(text)
    words_all = json.loads((d / "words.json").read_text())
    words, secs = words_all["words"], float(words_all["seconds"])
    lines = text.splitlines()
    blocks = _shot_blocks(text)
    order = sorted(blocks, key=lambda n: blocks[n][0])
    size = max(2, int(os.environ.get("V3_DIRECTOR_SHOTS", "6")))
    windows = [order[i:i + size] for i in range(0, len(order), size)]


    def one(w: list[str]) -> dict[str, str]:
        a, b = blocks[w[0]][0], blocks[w[-1]][1]
        body = "\n".join(lines[a:b])
        prev = order.index(w[0]) - 1
        before = "\n".join(lines[blocks[order[prev]][0]:blocks[order[prev]][1]]) if prev >= 0 else ""
        used = [int(x) for x in re.findall(r"\bw(\d+)", body)]
        mine = [x for x in words if used and min(used) <= x["i"] <= max(used)]
        system, user = prompts.director_prompt(body, before, mine, _cast(run), _lang(run))
        try:
            out = chat(run, "director", f"Director: {w[0]} .. {w[-1]}", system, user,
                       max_tokens=900 * len(w) + 600, model=(run["settings"].get("models") or {}).get("score") or None)
        except Exception:  # noqa: BLE001 -- the shots stay as they were
            return {}
        out = re.sub(r"^```\w*|```$", "", out.strip(), flags=re.M).strip()
        got = _shot_blocks(out)
        olines = out.splitlines()
        return {n: "\n".join(olines[got[n][0]:got[n][1]]) for n in w if n in got}
    jobs = max(1, int(os.environ.get("V3_SCORE_JOBS", "6")))
    with ThreadPoolExecutor(max_workers=min(jobs, max(1, len(windows)))) as pool:
        made = {}
        for r in pool.map(one, windows):
            made.update(r)
    kept, taken = 0, []
    for shot in sorted(made, key=lambda n: -blocks[n][0]):      # from the last, so the line numbers hold
        a, b = blocks[shot]
        head = []                                   # the comment lines over the shot kept
        for ln in lines[a:b]:
            if not ln.lstrip().startswith("#"):
                break
            head.append(ln)
        new = lines[:a] + head + [ln for ln in made[shot].splitlines() if not ln.lstrip().startswith("# ----")] + [""] + lines[b:]
        trial = "\n".join(new)
        try:
            ok = re.search(rf"^\s*shot\s+{re.escape(shot)}\b", made[shot], re.M) and \
                S.parse(trial, words, secs).notes.__len__() <= S.parse("\n".join(lines), words, secs).notes.__len__()
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            lines = new
            taken.append(shot)
        else:
            kept += 1
    (d / "video.score").write_text("\n".join(lines) + "\n")
    box["notes"] = [f"{len(taken)} of {len(order)} shot(s) rewritten in {len(windows)} pass(es); "
                    f"{len(order) - len(taken)} kept as they were ({kept} because the rewrite read worse, "
                    f"{len(order) - len(taken) - kept} not given back)"]


def _assets(run: dict) -> None:
    """The pictures the score asks for (assets.py), made at once (V3_IMAGE_JOBS) and kept; each call recorded with
    its cost. One that cannot be made is drawn as a placeholder and said here; the render goes on."""
    import look
    d = run_dir(run["id"])
    text = (d / "video.score").read_text()
    models = image_models(run)
    model = models["image"]
    labelled = assets.labelled_pictures(text)

    def model_for(kind: str, prompt: str) -> str:
        """Labelled pictures the labelled model; small cut-out things the small model; the rest the image model."""
        if (kind, prompt) in labelled:
            return models["image_labeled"]
        return models["image_small"] if kind == "pic" else model
    wants = [(k, p, lk if lk in look.LOOKS else "paper") for k, p, lk in assets.wants(text)]
    # (pictures kept under the old keys, a model's own file each, are moved to the keys now: nothing is made again)
    todo = [w for w in wants if not assets.adopt(w[0], w[1], w[2], [model_for(w[0], w[1]), *models.values(),
                                                                         assets.DEFAULT_MODEL])]
    notes = [f"{len(wants)} picture(s) asked for, {len(wants) - len(todo)} kept from before"]
    if not assets.SEARCH and any(assets.is_archive(w[1]) for w in todo):
        notes.append("image search is off (V3_IMAGE_SEARCH=0): pictures asked for from the archive are made")

    if library.ON and todo:                     # the illustration library first: only what it lacks is made
        took = library.take_inbox()
        if took:
            notes.append(f"{len(took)} picture(s) taken into the library from its inbox")
        found, lib_notes = _from_library(run, [w for w in todo if (w[0], w[1]) not in labelled
                                               and not (assets.is_archive(w[1]) and assets.SEARCH)])
        todo = [w for w in todo if w not in found]
        notes += lib_notes

    said = _better_words(run, text, todo) if todo else {}

    def record(label: str, user: str, model: str = model) -> dict:
        call = {"id": uuid.uuid4().hex[:8], "step": "assets", "label": label, "model": model, "system": "(image)",
                "user": user, "images": 0, "started": time.time(), "status": "running"}
        with _mut:
            run["calls"].append(call)
            save(run)
        return call

    def done(call: dict, **kw) -> None:
        with _mut:
            call.update(kw)
            call["ended"] = time.time()
            call["seconds"] = round(call["ended"] - call["started"], 2)
            save(run)

    def make(item):
        kind, prompt, lk = item
        _check(run["id"])
        if assets.is_archive(prompt) and assets.SEARCH:
            return _from_archive(run, kind, prompt)
        words = said.get((kind, prompt)) or (assets.archive_query(prompt) if assets.is_archive(prompt) else None)
        mine = model_for(kind, prompt)
        call = record(f"{kind}: {prompt[:60]}", assets.prompt_for(kind, words or prompt, lk), mine)
        try:
            path, usage = assets.generate(kind, prompt, lk, mine, words)
            done(call, status="done", output=path.name, cost=usage.get("cost"), tokens_in=usage.get("prompt_tokens"),
                 tokens_out=usage.get("completion_tokens"))
            return None
        except Exception as e:  # noqa: BLE001 -- a picture that cannot be made: a placeholder, said
            done(call, status="failed", error=str(e)[:500])
            return f"{kind} \"{prompt[:50]}\": {str(e)[:160]}"

    def make_sheet(chunk):
        """Small objects on one sheet, cut apart; one not cut cleanly is made on its own."""
        _check(run["id"])
        lk = chunk[0][2]
        pairs = [(p, said.get(("pic", p)) or (assets.archive_query(p) if assets.is_archive(p) else p)) for _, p, _ in chunk]
        prompt = assets.sheet_prompt([w for _, w in pairs], lk)[0]
        call = record(f"pic sheet ({len(chunk)}): " + "; ".join(p[:24] for p, _ in pairs), prompt, models["image_small"])
        try:
            made, missed, usage = assets.generate_sheet(pairs, lk, models["image_small"])
            done(call, status="done", output=f"{len(made)} of {len(chunk)} cut from one sheet", cost=usage.get("cost"),
                 tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"))
        except Exception as e:  # noqa: BLE001 -- the sheet failed: each made on its own
            done(call, status="failed", error=str(e)[:500])
            missed = [p for p, _ in pairs]
        sheets.append((len(chunk), len(chunk) - len(missed)))
        return [f for f in (make(("pic", p, lk)) for p in missed) if f]

    # Small objects go on sheets (V3_IMAGE_SHEET a sheet, of one look); scenes, archive pictures and a lone object
    # are made one by one.
    sheets: list[tuple[int, int]] = []
    small = [w for w in todo if w[0] == "pic" and (w[0], w[1]) not in labelled
             and not (assets.is_archive(w[1]) and assets.SEARCH)] if assets.SHEET > 1 else []
    single = [w for w in todo if w not in small]
    chunks = []
    for lk in dict.fromkeys(w[2] for w in small):
        mine = [w for w in small if w[2] == lk]
        chunks += [mine[i:i + assets.SHEET] for i in range(0, len(mine), assets.SHEET)]
    single += [c[0] for c in chunks if len(c) == 1]
    chunks = [c for c in chunks if len(c) > 1]
    jobs = max(1, int(os.environ.get("V3_IMAGE_JOBS", "4")))
    if todo:
        with ThreadPoolExecutor(max_workers=min(jobs, len(single) + len(chunks))) as pool:
            futs = [pool.submit(make_sheet, c) for c in chunks] + [pool.submit(make, w) for w in single]
            got = [f.result() for f in futs]
        failed = [f for g in got for f in ([g] if isinstance(g, str) else g or [])]
        names = {"image": "pictures", "image_small": "small things", "image_labeled": "labelled"}
        notes.append(f"{len(todo) - len(failed)} made (" + ", ".join(f"{names[k]}: {v}" for k, v in models.items()) + ")")
        if sheets:
            notes.append(f"{sum(n for n, _ in sheets)} small object(s) asked for on {len(sheets)} sheet(s); "
                         f"{sum(k for _, k in sheets)} cut cleanly, the rest made one by one")
        notes += [f"not made (a placeholder is drawn): {f}" for f in failed]
        made_now = [w for w in todo if w[0] == "pic" and assets.path_for(w[0], w[1], w[2]).exists()]
        notes += _check_pictures(run, made_now, said, model_for)
        if library.ON:                          # what was made kept in the library, for the next video
            for kind, prompt, lk in todo:
                p = assets.path_for(kind, prompt, lk)
                if p.exists():
                    try:
                        library.add(p, prompt, kind, tags=library._words(said.get((kind, prompt)) or "")[:24],
                                    source="made", license="made for this harness", finished=True)
                    except Exception:  # noqa: BLE001
                        pass
    notes += _find_parts(run, text, model)
    run["steps"]["assets"]["notes"] = notes


CHECK = """You check the pictures of an educational video before it is made. You see one picture, a cut-out drawing,
and the words it was made from. Answer `yes` if it shows that thing plainly as ONE whole object or person, cleanly cut
out, with no words, letters or numbers in it; else `no: WHAT IS WRONG` in a few words (the wrong thing, several things,
cut off, text in it, a panel or background behind it, unreadable)."""


def _check_pictures(run: dict, items: list, said: dict, model_for) -> list[str]:
    """Each cut-out made now looked at by a vision model (V3_IMAGE_CHECK=0: not): one that is wrong is made again,
    once, told what was wrong."""
    if not items or os.environ.get("V3_IMAGE_CHECK", "1").strip() == "0":
        return []
    vision = (run["settings"].get("models") or {}).get("critic") or run["settings"]["model"]

    def one(item):
        kind, prompt, lk = item
        p = assets.path_for(kind, prompt, lk)
        try:
            from PIL import Image
            import io as _io
            im = Image.open(p).convert("RGBA")
            im.thumbnail((384, 384))
            bg = Image.new("RGBA", im.size, (240, 236, 226, 255))
            bg.alpha_composite(im)
            buf = _io.BytesIO()
            bg.convert("RGB").save(buf, "JPEG", quality=85)
            url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            verdict = chat(run, "assets", f"check: {prompt[:50]}", CHECK, f"THE WORDS: {said.get((kind, prompt)) or prompt}",
                           images=[url], max_tokens=60, model=vision).strip()
        except Exception:  # noqa: BLE001 -- not checked: kept as it is
            return None
        if not verdict.lower().startswith("no"):
            return None
        wrong = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict[2:].strip()
        words = (said.get((kind, prompt)) or prompt) + f" (the last try was wrong: {wrong[:120]}; draw it right)"
        try:
            assets.generate(kind, prompt, lk, model_for(kind, prompt), words)
            return f"remade {kind} \"{prompt[:40]}\": {wrong[:80]}"
        except Exception as e:  # noqa: BLE001
            return f"kept {kind} \"{prompt[:40]}\" though it looked wrong ({wrong[:60]}): remaking failed: {str(e)[:80]}"
    jobs = max(1, int(os.environ.get("V3_IMAGE_JOBS", "4")))
    with ThreadPoolExecutor(max_workers=min(jobs, len(items))) as pool:
        out = [r for r in pool.map(one, items) if r]
    return [f"{len(items)} cut-out(s) checked by eye; {len(out)} remade"] + out[:12]


def _from_library(run: dict, items: list) -> tuple[list, list[str]]:
    """Pictures found in the illustration library (and on Pixabay, with PIXABAY_API_KEY) instead of made: for each,
    the closest candidates by their words, and the vision model chooses the one that truly shows it, or none.
    Returns the items found and notes."""
    from PIL import Image
    import io as _io
    vision = (run["settings"].get("models") or {}).get("critic") or run["settings"]["model"]
    found, notes = [], []

    def thumb(c) -> str:
        if "file" in c:
            return assets.data_url(library.path(c), 320)
        im = assets._open(assets._get(c["url"])).convert("RGBA")
        im.thumbnail((320, 320))
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        buf = _io.BytesIO()
        bg.convert("RGB").save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    def one(item):
        kind, prompt, lk = item
        if kind not in ("pic", "photo"):
            return None
        words = assets.archive_query(prompt) if assets.is_archive(prompt) else prompt
        cands = library.search(words, kind, 4) + library.outside(words, kind, 4)
        if not cands:
            return None
        try:
            shown = cands[:8]
            images = [thumb(c) for c in shown]
            system, user = library.choose_prompt(words, len(shown))
            said = chat(run, "assets", f"library: {words[:50]}", system, user, images=images, max_tokens=20,
                        model=vision)
        except Exception:  # noqa: BLE001 -- no choice: made by the image model
            return None
        m = re.search(r"\d+", said)
        if not m or not (1 <= int(m.group()) <= len(shown)) or said.strip().lower().startswith("none"):
            return None
        pick = shown[int(m.group()) - 1]
        try:
            if "file" in pick:
                row = pick
                img = Image.open(library.path(row))
            else:                               # from Pixabay: kept in the library too
                img = assets._open(assets._get(pick["large"]))
                row = library.add(img, f"{words} | {pick['title']}", kind, pick["tags"], pick.get("source", "outside"),
                                  pick.get("license", ""), pick.get("user", ""), pick.get("page", ""))
                if not pick.get("free", True):          # (a licence that asks for its author: said under it)
                    out_ = assets.path_for(kind, prompt, lk)
                    out_.parent.mkdir(parents=True, exist_ok=True)
                    out_.with_suffix(".credit.json").write_text(json.dumps(
                        {"artist": pick.get("user", ""), "license": pick.get("license", ""), "page": pick.get("page", ""),
                         "needs_credit": True}))
            out = assets.path_for(kind, prompt, lk)
            out.parent.mkdir(parents=True, exist_ok=True)
            if row.get("finished"):
                shutil.copyfile(library.path(row), out)
            elif kind == "pic" and assets._plain_ground(img):
                assets.cutout(img).save(out)
            else:
                assets.framed(img.convert("RGB")).save(out)
            return item, f"{kind} \"{prompt[:40]}\" from the library ({row['source']}: {row['title'][:40]})"
        except Exception as e:  # noqa: BLE001
            return None
    jobs = max(1, int(os.environ.get("V3_IMAGE_JOBS", "4")))
    import shutil
    with ThreadPoolExecutor(max_workers=min(jobs, max(1, len(items)))) as pool:
        for r in pool.map(one, items):
            if r:
                found.append(r[0])
                notes.append(r[1])
    head = [f"{len(found)} of {len(items)} picture(s) taken from the illustration library (the rest made)"] if items else []
    return found, head + notes[:15]


def image_models(run: dict) -> dict:
    """The run's three image models: {"image", "image_small", "image_labeled"} (a blank one: the image model)."""
    m = run["settings"].get("models") or {}
    main = m.get("image") or assets.DEFAULT_MODEL
    return {"image": main, "image_small": m.get("image_small") or assets.SMALL_MODEL or main,
            "image_labeled": m.get("image_labeled") or assets.LABELED_MODEL or main}


def _better_words(run: dict, text: str, todo: list) -> dict:
    """One call (the score's model) rewrites each picture's few words into the exact picture wanted, from the
    narration and its shot's plan: {(kind, the score's words): the image model's words}. V3_IMAGE_REFINE=0: off."""
    if os.environ.get("V3_IMAGE_REFINE", "1") == "0":
        return {}
    items = [(k, p) for k, p, _ in todo if not (assets.is_archive(p) and assets.SEARCH)]
    if not items:
        return {}
    plans = assets.shots_of(text)
    narration = (run_dir(run["id"]) / "narration.txt").read_text() if (run_dir(run["id"]) / "narration.txt").exists() else ""
    system, user = assets.refine_prompt([(k, p, plans.get((k, p), "")) for k, p in items], narration)
    st = run["settings"]
    try:
        answer = chat(run, "assets", f"better picture prompts ({len(items)})", system, user,
                      max_tokens=120 * len(items) + 200, model=(st.get("models") or {}).get("score") or st["model"])
    except Exception as e:  # noqa: BLE001 -- the score's own words are used
        run["steps"]["assets"].setdefault("notes", []).append(f"picture prompts not rewritten: {str(e)[:120]}")
        return {}
    got = assets.read_refined(answer, len(items))
    return {items[i]: w for i, w in got.items()}


def _from_archive(run: dict, kind: str, prompt: str) -> str | None:
    """A picture from Wikimedia Commons: the candidates for its words, the best chosen by the vision model from small
    copies of them (the first when there is no choice to make), fetched and kept with its credit. None found: the
    image model makes it from the same words. Returns a note when it is drawn as a placeholder."""
    query = assets.archive_query(prompt)
    vision = (run["settings"].get("models") or {}).get("critic") or run["settings"]["model"]
    try:
        cands = assets.commons_candidates(query)
    except Exception as e:  # noqa: BLE001
        cands = []
        run["steps"]["assets"].setdefault("notes", []).append(f"archive search for \"{query[:40]}\": {str(e)[:100]}")
    if not cands:
        try:
            path, usage = assets.generate(kind, query, run["settings"].get("look") or "editorial",
                                          (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL)
            import shutil
            shutil.copyfile(path, assets.path_for(kind, prompt, "", ""))   # kept as the archive's answer
            return None
        except Exception as e:  # noqa: BLE001
            return f"archive \"{query[:50]}\": nothing found, and not made: {str(e)[:120]}"
    pick = cands[0]
    if len(cands) > 1:
        try:
            shown = cands[:6]
            images = ["data:image/jpeg;base64," + base64.b64encode(assets._get(assets.small(c["url"]))).decode()
                      for c in shown]
            system, user = assets.choose_prompt(query, len(shown))
            said = chat(run, "assets", f"choose archive picture: {query[:40]}", system, user, images=images,
                        max_tokens=50, model=vision)
            m = re.search(r"\d+", said)
            if m and 1 <= int(m.group()) <= len(shown):
                pick = shown[int(m.group()) - 1]
        except Exception:  # noqa: BLE001 -- no choice made: the archive's first answer
            pass
    try:
        assets.from_commons(kind, prompt, pick)
    except Exception as e:  # noqa: BLE001
        return f"archive \"{query[:50]}\": {str(e)[:120]}"
    with _mut:
        run.setdefault("credits", [])
        run["credits"].append({k: pick.get(k) for k in ("title", "page", "license", "artist")})
        save(run)
    return None


def _find_parts(run: dict, text: str, image_model: str) -> list[str]:
    """Where the parts a score names on its pictures (`labels`) are: a vision model looks at each picture once and
    says, kept beside the picture; a part it cannot find is drawn where the score's default puts it."""
    import look
    notes = []
    vision = (run["settings"].get("models") or {}).get("critic") or run["settings"]["model"]
    for kind, prompt, lk, names in assets.labelled(text):
        p = assets.path_for(kind, prompt, lk if lk in look.LOOKS else "paper")
        if not p.exists():
            continue
        import kit
        have = json.loads(p.with_suffix(".spots.json").read_text()) if p.with_suffix(".spots.json").exists() else {}
        missing = [n for n in names if kit.key(n) not in have]
        if not missing:
            continue
        system, user = assets.find_prompt(missing)
        try:
            said = chat(run, "assets", f"find parts: {prompt[:40]}", system, user, images=[assets.data_url(p)],
                        max_tokens=400, model=vision)
        except Exception as e:  # noqa: BLE001 -- not found: the labels go where the score's defaults put them
            notes.append(f"could not find the parts of \"{prompt[:40]}\": {str(e)[:120]}")
            continue
        found = assets.read_spots(said, missing)
        assets.keep_spots(p, {kit.key(n): found.get(kit.key(n)) for n in missing})
        lost = [n for n in missing if not found.get(kit.key(n))]
        notes.append(f"parts of \"{prompt[:40]}\" found by {vision}: {len(missing) - len(lost)}/{len(missing)}"
                     + (f" (not seen: {', '.join(lost)})" if lost else ""))
    return notes


def _render(run: dict) -> None:
    d = run_dir(run["id"])
    started = time.time()
    if len(_parts(run)) > 1:
        return _render_long(run, started)
    p = _proc(run["id"], [sys.executable, str(HERE / "render.py"), str(d / "video.score"), str(d), str(d / "video.mp4"),
                          "--quality", run["settings"]["quality"]],
              # the pictures are found by the image model they were made with
              env={"V3_IMAGE_MODEL": (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL},
              on_line=follow(run, run["steps"]["render"]))
    if p.returncode != 0:
        raise RuntimeError(_tail(p))
    notes = [l[6:] for l in p.stdout.splitlines() if l.startswith("note: ")]
    notes += [l for l in p.stderr.splitlines() if l.startswith("score line")]
    run["steps"]["render"]["notes"] = notes[:40] or [f"rendered in {time.time() - started:.0f} s"]
    run["video"] = f"video.mp4?v={int(time.time())}"


def _tail(p: subprocess.CompletedProcess) -> str:
    """A failed program's own words: its error, without the progress lines."""
    lines = [l for l in (p.stderr or p.stdout).splitlines() if not PROGRESS.match(l)]
    return "\n".join(lines)[-1500:]


PART_JOBS = max(1, int(os.environ.get("V3_PART_JOBS", "3")))   # a long video's parts baked at once


def _part_dirs(run: dict) -> list[Path]:
    """A long video's parts written out from its score as it is now (parts/pK: score, words, voice)."""
    d = run_dir(run["id"])
    return PT.write(d, (d / "video.score").read_text(), json.loads((d / "words.json").read_text()), _parts(run))


def _part_env(run: dict) -> list[dict]:
    d = run_dir(run["id"])
    ps = _parts(run)
    words = json.loads((d / "words.json").read_text())
    chaps = PT.chapters((d / "video.score").read_text(), words["words"], float(words["seconds"]))
    return [PT.env(p, ps, float(words["seconds"]), chaps) for p in ps]


def _check_layout(run: dict) -> dict:
    """layout.py on the run's score: the problems by shot, with every thing's real size (a long video's parts
    each checked by itself, at once, and their reports joined)."""
    d = run_dir(run["id"])
    if len(_parts(run)) > 1:
        dirs = _part_dirs(run)

        def one(pd: Path) -> dict:
            text = (pd / "video.score").read_text()
            lines = text.splitlines()
            carried = {name for name, (a, b) in _shot_blocks(text).items()
                       if any("carried over" in ln for ln in lines[a:b] if ln.lstrip().startswith("#"))}
            rep_ = _check_layout_at(run, pd / "video.score", pd)
            rep_["problems"] = {k: v for k, v in rep_["problems"].items() if k not in carried}
            rep_["sizes"] = {k: v for k, v in rep_["sizes"].items() if k not in carried}
            return rep_
        with ThreadPoolExecutor(max_workers=min(PART_JOBS, len(dirs))) as pool:
            reps = list(pool.map(one, dirs))
        out = {"count": 0, "problems": {}, "sizes": {}, "notes": []}
        for r in reps:
            for k, v in r["problems"].items():
                have = out["problems"].setdefault(k, [])
                have += [x for x in v if x not in have]
            for k, v in r["sizes"].items():
                out["sizes"].setdefault(k, v)
            out["notes"] += r.get("notes", [])
        out["count"] = sum(len(v) for v in out["problems"].values())
        return out
    return _check_layout_at(run, d / "video.score", d)


def _check_layout_at(run: dict, score: Path, d: Path) -> dict:
    p = _proc(run["id"], [sys.executable, str(HERE / "layout.py"), str(score), str(d)])
    if p.returncode != 0:
        raise RuntimeError(_tail(p))
    line = next((l for l in p.stdout.splitlines() if l.startswith("layout: ")), None)
    if line is None:
        raise RuntimeError("the layout check said nothing: " + _tail(p))
    return json.loads(line[8:])


def _shot_blocks(text: str) -> dict[str, tuple[int, int]]:
    """Each shot's lines in a score: {name: (first line, line after its last)}, the comment lines over it included."""
    lines = text.splitlines()
    starts = []
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*shot\s+([\w\-]+)", ln)
        if m:
            j = i
            while j > 0 and lines[j - 1].lstrip().startswith("#"):
                j -= 1
            starts.append((m.group(1), j, i))
    out = {}
    for k, (name, j, i) in enumerate(starts):
        end = starts[k + 1][1] if k + 1 < len(starts) else len(lines)
        while end > i + 1:
            last = lines[end - 1].strip()
            # (blank lines after it, and the video's closing wide shot after the last, are not the shot's)
            if last == "" or (k + 1 == len(starts) and re.match(r"^\S+\s+cam\s+wide\b", last)):
                end -= 1
            else:
                break
        out[name] = (j, end)
    return out


def _layout(run: dict) -> None:
    """The layout check (layout.py): the score's things built with their real sizes, and what covers what, runs off
    the screen or is empty said by shot. A shot with problems goes back to the score's model once with them and the
    real sizes (V3_LAYOUT_FIX rounds, default 2; 0: only checked), and is checked again. A score given by hand is
    only checked: what to change is said here."""
    d = run_dir(run["id"])
    rep = _check_layout(run)
    notes = [f"{rep['count']} layout problem(s) in {len(rep['problems'])} shot(s)" if rep["count"] else "no layout problems"]
    rounds = int(os.environ.get("V3_LAYOUT_FIX", "2"))
    can = bool(os.environ.get("OPENROUTER_API_KEY")) and not run["settings"].get("given_score")
    if rep["count"] and (not can or rounds <= 0):
        notes += [f"{shot}: {p}" for shot, ps in rep["problems"].items() for p in ps][:30]
        if run["settings"].get("given_score"):
            notes.append("the score was given by hand: fix these in it (or let the score step write it)")
    words = _words(run)
    st = run["settings"]
    for rnd in range(rounds if can else 0):
        if not rep["count"]:
            break
        text = (d / "video.score").read_text()
        if rnd == 0:
            (d / "video.before-layout.score").write_text(text)
        blocks = _shot_blocks(text)
        lines = text.splitlines()
        todo = [shot for shot in rep["problems"] if shot in blocks][:int(os.environ.get("V3_LAYOUT_SHOTS", "40"))]

        def fix(shot: str) -> tuple[str, str | None]:
            a, b = blocks[shot]
            body = "\n".join(lines[a:b])
            used = [int(x) for x in re.findall(r"\bw(\d+)", body)]
            mine = [w for w in words if used and min(used) <= w["i"] <= max(used)]
            system, user = prompts.repair_prompt(body, rep["problems"][shot], rep["sizes"].get(shot, []), mine,
                                                 _cast(run), _lang(run))
            try:
                out = chat(run, "layout", f"Layout fix: {shot}", system, user,
                           model=(st.get("models") or {}).get("score") or st["model"])
            except Exception as e:  # noqa: BLE001 -- the shot stays as it was
                return shot, None
            out = re.sub(r"^```\w*|```$", "", out.strip(), flags=re.M).strip()
            if not re.search(rf"^\s*shot\s+{re.escape(shot)}\b", out, re.M):
                return shot, None                       # not the shot asked for: kept as it was
            head = []                                   # the comment lines over the shot are kept
            for ln in lines[a:b]:
                if not ln.lstrip().startswith("#"):
                    break
                head.append(ln)
            return shot, "\n".join(head + [out])
        jobs = max(1, int(os.environ.get("V3_SCORE_JOBS", "6")))
        with ThreadPoolExecutor(max_workers=min(jobs, max(1, len(todo)))) as pool:
            fixed = dict(pool.map(fix, todo))
        # the new shots in place of the old (from the last, so the line numbers hold)
        for shot in sorted((s_ for s_ in fixed if fixed[s_]), key=lambda s_: -blocks[s_][0]):
            a, b = blocks[shot]
            new = lines[:a] + fixed[shot].splitlines() + [""] + lines[b:]
            trial = S.parse("\n".join(new), words, float(json.loads((d / "words.json").read_text())["seconds"]))
            if shot in trial.shots and any(e.shot == shot for e in trial.ents.values()):
                lines = new
        (d / "video.score").write_text("\n".join(lines) + "\n")
        made = [k for k in fixed if fixed[k]]
        # pictures a fixed shot asks for anew are made (the rest are kept)
        before = run["steps"]["assets"].get("notes", [])
        _assets(run)
        run["steps"]["assets"]["notes"] = before
        rep = _check_layout(run)
        notes.append(f"round {rnd + 1}: {len(made)} shot(s) rewritten ({', '.join(made)}); "
                     f"{rep['count']} problem(s) left")
    if can and rep["count"]:
        notes += [f"{shot}: {p}" for shot, ps in rep["problems"].items() for p in ps][:20]
    run["steps"]["layout"]["notes"] = notes


def _render_long(run: dict, started: float) -> None:
    """A long video's MP4: each part rendered by itself (each in its own chunks at once), the parts joined, and the
    whole video's one soundtrack laid under them."""
    d = run_dir(run["id"])
    dirs, envs = _part_dirs(run), _part_env(run)
    notes = []
    for k, (pd, env) in enumerate(zip(dirs, envs)):
        run["steps"]["render"]["log"] = [f"part {k + 1} of {len(dirs)}"]
        p = _proc(run["id"], [sys.executable, str(HERE / "render.py"), str(pd / "video.score"), str(pd),
                              str(pd / "video.mp4"), "--quality", run["settings"]["quality"]],
                  env={**env, "V3_IMAGE_MODEL": (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL},
                  on_line=follow(run, run["steps"]["render"]))
        if p.returncode != 0:
            raise RuntimeError(f"part {k + 1}: " + _tail(p))
        notes += [f"part {k + 1}: {l}" for l in p.stderr.splitlines() if l.startswith("score line")]
    audio = _whole_soundtrack(run, d / "soundtrack.wav")
    lst = d / "parts" / "join.txt"
    lst.write_text("".join(f"file '{pd / 'video.mp4'}'\n" for pd in dirs))
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
    cmd += (["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest"]
            if audio else ["-c", "copy"])
    subprocess.run(cmd + [str(d / "video.mp4")], check=True)
    run["steps"]["render"]["notes"] = notes[:40] or [f"{len(dirs)} parts rendered and joined in "
                                                     f"{time.time() - started:.0f} s"]
    run["video"] = f"video.mp4?v={int(time.time())}"


def _whole_soundtrack(run: dict, out: Path) -> Path | None:
    """The whole video's soundtrack (the voice, its small sounds, the music under it all): one, so nothing starts
    again at a part's seam."""
    d = run_dir(run["id"])
    try:
        import sound
        words = json.loads((d / "words.json").read_text())
        sc = S.parse((d / "video.score").read_text(), words["words"], float(words["seconds"]))
        sound.mix(sc, d / "voice.wav", out)
        return out
    except Exception as e:  # noqa: BLE001 -- the voice alone
        print(f"soundtrack not made ({e}): the voice alone", flush=True)
        return d / "voice.wav" if (d / "voice.wav").exists() else None


def _timeline_long(run: dict) -> None:
    """A long video's timeline: each part baked by itself (V3_PART_JOBS at once) into player/pK/, and
    player/parts.json saying how they follow each other over the one soundtrack."""
    import shutil
    d = run_dir(run["id"])
    player = d / "player"
    player.mkdir(exist_ok=True)
    (player / "timeline.json").unlink(missing_ok=True)      # (a short video's, from before: the player reads parts)
    dirs, envs = _part_dirs(run), _part_env(run)
    box = run["steps"]["timeline"]
    done = {}

    def one(k: int) -> dict:
        pd, env = dirs[k], envs[k]
        out = player / f"p{k}"
        p = _proc(run["id"], [sys.executable, str(HERE / "timeline.py"), str(pd / "video.score"), str(pd), str(out),
                              "--quality", run["settings"]["quality"]],
                  env={**env, "V3_IMAGE_MODEL": (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL})
        if p.returncode != 0:
            raise RuntimeError(f"part {k + 1}: " + _tail(p))
        for f in ("voice.wav", "soundtrack.wav"):       # the whole video's soundtrack plays under all the parts
            (out / f).unlink(missing_ok=True)
        info = next((json.loads(l[9:]) for l in p.stdout.splitlines() if l.startswith("timeline:")), {})
        with _mut:
            done[k] = info
            box["progress"] = {"done": len(done), "total": len(dirs), "what": "parts baked", "eta": None}
        save(run)
        return info
    with ThreadPoolExecutor(max_workers=min(PART_JOBS, len(dirs))) as pool:
        infos = list(pool.map(one, range(len(dirs))))
    for old in player.glob("p*"):                           # parts of an earlier cut that are no more
        if old.is_dir() and old.name[1:].isdigit() and int(old.name[1:]) >= len(dirs):
            shutil.rmtree(old, ignore_errors=True)
    audio = _whole_soundtrack(run, player / "soundtrack.wav")
    PT.manifest(player, _parts(run), audio.name if audio and audio.parent == player else None)
    mb = sum(i.get("bytes", 0) for i in infos) / 1e6
    box["notes"] = [f"{len(dirs)} parts, {sum(i.get('leaves', 0) for i in infos)} pieces, "
                    f"{sum(i.get('pictures', 0) for i in infos)} picture(s), {mb:.1f} MB (played by the Player tab)"]


def youtube_chapters(run: dict) -> str:
    """The video's chapters as YouTube reads them from a description (`0:00 Title`, the first at 0:00), from the
    score's `chapter` lines; written to chapters.txt. Empty with fewer than two."""
    d = run_dir(run["id"])
    try:
        words = json.loads((d / "words.json").read_text())
        sc = S.parse((d / "video.score").read_text(), words["words"], float(words["seconds"]))
    except Exception:  # noqa: BLE001
        return ""
    chaps = sorted({round(a.t0): a.target for a in sc.acts if a.verb == "chapter"}.items())
    if len(chaps) < 2:
        return ""

    def mmss(t):
        t = max(0, int(t))
        return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"
    rows, last = [], -99
    for k, (t, title) in enumerate(chaps):
        t = 0 if k == 0 else t
        if t - last < 10:                       # (YouTube wants each at least 10 s)
            continue
        rows.append(f"{mmss(t)} {title}")
        last = t
    text = "\n".join(rows) + "\n" if len(rows) >= 2 else ""
    (d / "chapters.txt").write_text(text)
    return text


def _timeline(run: dict) -> None:
    """The video as a timeline for the player (player/timeline.json, its pictures, the voice)."""
    d = run_dir(run["id"])
    youtube_chapters(run)
    if len(_parts(run)) > 1:
        return _timeline_long(run)
    (d / "player" / "parts.json").unlink(missing_ok=True)   # (a long video's, from before)
    p = _proc(run["id"], [sys.executable, str(HERE / "timeline.py"), str(d / "video.score"), str(d), str(d / "player"),
                          "--quality", run["settings"]["quality"]],
              env={"V3_IMAGE_MODEL": (run["settings"].get("models") or {}).get("image") or assets.DEFAULT_MODEL},
              on_line=follow(run, run["steps"]["timeline"]))
    if p.returncode != 0:
        raise RuntimeError(_tail(p))
    info = next((json.loads(l[9:]) for l in p.stdout.splitlines() if l.startswith("timeline:")), {})
    run["steps"]["timeline"]["notes"] = [f"{info.get('leaves', '?')} pieces, {info.get('pictures', 0)} picture(s), "
                                         f"{info.get('bytes', 0) / 1e6:.1f} MB (played by the Player tab)"]


def export(rid: str) -> None:
    """An MP4 made from the player (export.py), compared with the render's frame by frame; the report kept on the
    run (run["export"]), its side-by-side frames beside it."""
    if rid in _busy:
        raise RuntimeError("this run is busy: wait for it")
    d = run_dir(rid)
    if not ((d / "player" / "timeline.json").exists() or (d / "player" / "parts.json").exists()):
        raise RuntimeError("no timeline yet: run the timeline step first")
    _busy.add(rid)

    def work():
        run = load(rid)
        run["export"] = {"status": "queued"}
        save(run)
        got = _slots.acquire(timeout=None)
        run = load(rid)
        ex = run["export"] = {"status": "running", "started": time.time()}
        save(run)
        try:
            cmd = [sys.executable, str(HERE / "export.py"), str(d / "player"), str(d / "player.mp4"), "--quality",
                   run["settings"]["quality"]]
            if (d / "video.mp4").exists():
                cmd += ["--compare", str(d / "video.mp4"), "--report", str(d / "compare.json")]
            p = _proc(rid, cmd, on_line=follow(run, ex))
            if p.returncode != 0:
                raise RuntimeError((p.stderr or p.stdout)[-1500:])
            ex["status"] = "done"
            if (d / "compare.json").exists():
                ex["report"] = json.loads((d / "compare.json").read_text())
        except Stopped:
            ex["status"] = "stopped"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            ex.update({"status": "failed", "error": str(e)[:1500]})
        finally:
            ex["ended"] = time.time()
            ex["seconds"] = round(ex["ended"] - ex["started"], 1)
            save(run)
            if got:
                _slots.release()
            _stop.discard(rid)
            _busy.discard(rid)
    threading.Thread(target=work, daemon=True).start()


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
    shots = {t: d / f"critic-{t:.1f}.jpg" for t in times}
    if not (d / "video.mp4").exists():                  # no MP4: the frames from the player
        import export
        export.stills(d / "player", shots, width=640)
    for t in times:
        f = shots[t]
        if (d / "video.mp4").exists():
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(d / "video.mp4"),
                            "-frames:v", "1", "-vf", "scale=640:-1", str(f)], check=True)
        images.append("data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode())
        near = [w["w"] for w in words if abs(float(w["start"]) - t) < 1.5]
        said.append(f"t{t:.1f}: \"{' '.join(near)}\"")
    verdict = chat(run, "critic", "Critic", prompts.CRITIC, "FRAMES, in order:\n" + "\n".join(said), images=images,
                   max_tokens=500)
    run["steps"]["critic"]["notes"] = [l for l in verdict.splitlines() if l.strip()][:20]


RUNNERS = {"voice": _voice, "storyboard": _storyboard, "score": _score, "director": _director, "assets": _assets,
           "layout": _layout,
           "render": _render,
           "timeline": _timeline, "critic": _critic}


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
                    elif s == "render" and start != "render" and not run["settings"].get("mp4"):
                        step["notes"] = ["no MP4 for this run: the Player plays the timeline (run this step to make "
                                         "one with Manim)"]
                        step["skipped"] = True
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
    for p in list(_procs.get(rid, ())):
        if p.poll() is None:
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
        elif (run.get("export") or {}).get("status") in ("queued", "running") and run["id"] not in _busy:
            run["export"]["status"] = "stopped"
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


def set_settings(rid: str, changes: dict) -> dict:
    """A run's language or voice changed (then made again from the voice step, by the caller)."""
    if rid in _busy:
        raise RuntimeError("this run is busy: stop it or wait for it")
    with _mut:
        run = load(rid)
        if changes.get("language") is not None:
            if changes["language"] not in LANGUAGES:
                raise ValueError(f"no language {changes['language']!r}")
            run["settings"]["language"] = changes["language"]
        if changes.get("voice"):
            run["settings"]["voice"] = str(changes["voice"])
        save(run)
    return run["settings"]


def set_score(rid: str, text: str) -> None:
    """A score changed by hand: kept, and played again from it: its new pictures, the timeline (the Player), the MP4
    when the run makes one (running the score step again writes a new one over it)."""
    (run_dir(rid) / "video.score").write_text(text)
    run = load(rid)
    run["edited"] = time.time()
    save(run)
    start(rid, "assets")
