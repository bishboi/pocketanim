"""v2's own: whether a picture asked for now is one made before, decided by a decision model (Jev, on OpenRouter's
Decisions API) instead of by matching words (genimage._reusable, reference_for).

The model is given the picture asked for (its words, what it is for, how it is drawn) and the pictures made before
that could be it (each one's words and the prompt it was drawn from), and answers one Choice question:

    reuse_<k>   picture k shows exactly what is asked: show it again as it is
    match_<k>   picture k shows the same person, place or thing, but this picture needs another view, pose, moment
                or scene: draw a new one that matches it (picture k is sent to the image model as its reference)
    fresh       none of them: draw it from nothing

The shortlist is code's: pictures in the same style, look and model (a reuse also of the same shape, cutout or
scene, and with every part this one labels) that share a content word with the request, the closest first
(PANIM_PICTURE_JUDGE_CANDIDATES, 8). With none, nothing is asked: it is drawn fresh.

Each answer is kept (.cache/images/judge-<key>.json, by the request and the shortlist), so a compile done again asks
nothing. What was decided in this process is in DECIDED (genimage.report "judged"): the request, the shortlist, the
answer with its probabilities, what was done, what it cost.

Settings: PANIM_PICTURE_JUDGE (the decision model; unset: the old matching by words), PANIM_PICTURE_JUDGE_SURE
(0.6: a reuse below it draws a matching picture instead, a match below it draws fresh), PANIM_PICTURE_JUDGE_FAKE=1
(a stand-in answer, no call: the checks), OPENROUTER_API_KEY, OPENROUTER_DECISIONS_URL.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from chirp import _env

URL = "https://openrouter.ai/api/alpha/decisions"
DECIDED: dict[str, dict] = {}
_lock = threading.Lock()


def model() -> str | None:
    return (_env("PANIM_PICTURE_JUDGE") or "").strip() or None


def enabled() -> bool:
    return bool(model()) and (_fake() or bool(_env("OPENROUTER_API_KEY")))


def _fake() -> bool:
    return os.environ.get("PANIM_PICTURE_JUDGE_FAKE") == "1"


def sure() -> float:
    try:
        return float(_env("PANIM_PICTURE_JUDGE_SURE") or 0.6)
    except ValueError:
        return 0.6


def _candidate_text(k: int, row: dict, reusable: bool) -> str:
    shape = "a whole scene" if row.get("scene") else "a cutout (the subject alone)"
    labels = ", ".join(str(p) for p in row.get("parts") or [])
    return (f"PICTURE {k} ({shape}{', labelled: ' + labels if labels else ''}"
            f"{'' if reusable else '; another shape or labels: it can only be MATCHED, not shown again'}):\n"
            f"  asked for: {str(row.get('what') or '')[:600]}\n"
            f"  drawn from the prompt: {str(row.get('prompt') or '')[:1200]}")


def _ask(state: list[str], criteria: dict[str, str]) -> tuple[dict, float]:
    body = {"model": model(), "state": state, "questions": {"use": {
        "type": "choice",
        "instructions": "A picture is needed for a video lecture. Decide whether one of the pictures made before can be "
                        "used for it: shown again as it is (it shows exactly what is needed), matched (it shows the "
                        "same person, place or thing, and the new picture must look like it, in another view, pose, "
                        "moment or scene), or none (draw a new picture from nothing). Show a picture again only when "
                        "it truly shows what is asked now; a different person, building or moment is never the same "
                        "picture, even in the same words of style.",
        "criteria": criteria}}}
    request = urllib.request.Request(_env("OPENROUTER_DECISIONS_URL") or URL, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {_env('OPENROUTER_API_KEY')}",
                                              "Content-Type": "application/json", "X-Title": "pocketanim harness v2"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as reply:
                data = json.loads(reply.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(str((data["error"] or {}).get("message") or data["error"])[:300])
            usage = data.get("usage") or {}
            return data, float(usage.get("cost") or 0.0)
        except urllib.error.HTTPError as error:
            last = RuntimeError(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}")
            if error.code in (400, 401, 403, 404, 422):
                break
        except Exception as error:  # noqa: BLE001 -- a dropped connection: asked again, then drawn fresh
            last = error
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last) if last else "no answer")


def _answer(reply: dict) -> dict:
    """The answer to "use", wherever the reply puts it (the API is alpha: read loosely, as app/lib/decisions.ts)."""
    for place in (reply, reply.get("answers"), reply.get("decisions"), reply.get("results"), reply.get("data")):
        if isinstance(place, dict) and isinstance(place.get("use"), dict):
            return place["use"]
    return {}


def _read(answer: dict, options: list[str]) -> tuple[str | None, dict, float | None]:
    probabilities: dict[str, float] = {}
    raw = next((answer.get(k) for k in ("probabilities", "probs", "distribution", "criteria", "options", "scores")
                if answer.get(k) is not None), None)
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                key = str(item.get("option") or item.get("key") or item.get("label") or item.get("value") or "")
                try:
                    probabilities[key] = float(item.get("probability", item.get("p", item.get("score"))))
                except (TypeError, ValueError):
                    pass
    elif isinstance(raw, dict):
        for key, value in raw.items():
            try:
                probabilities[str(key)] = float(value)
            except (TypeError, ValueError):
                pass
    choice = next((str(answer[k]) for k in ("choice", "selected", "answer", "option", "value")
                   if answer.get(k) is not None and str(answer[k]) in options), None)
    if not choice and probabilities:
        choice = max(probabilities, key=probabilities.get)
    try:
        confidence = float(answer["confidence"])
    except (KeyError, TypeError, ValueError):
        confidence = probabilities.get(choice) if choice else None
    return (choice if choice in options else None), probabilities, confidence


def _picked_key(record: dict) -> str | None:
    """The file key of the picture an answer chose (reuse_k, match_k), or None (fresh, or no answer)."""
    choice = str(record.get("choice") or "")
    if "_" not in choice:
        return None
    k = choice.split("_", 1)[1]
    candidates = record.get("candidates") or []
    return candidates[int(k)]["key"] if k.isdigit() and int(k) < len(candidates) else None


def _stand_in(what: str, shortlist: list[tuple[dict, bool]], same_thing, names) -> tuple[str, dict, float]:
    """The checks' answer (no call): shown again when it is the same request, matched when it names the same
    person or place, else fresh."""
    for k, (row, reusable) in enumerate(shortlist):
        if reusable and same_thing(what, str(row["what"])) >= 0.9:
            return f"reuse_{k}", {f"reuse_{k}": 0.9, "fresh": 0.1}, 0.9
    for k, (row, _) in enumerate(shortlist):
        if names(what) & names(str(row["what"])):
            return f"match_{k}", {f"match_{k}": 0.8, "fresh": 0.2}, 0.8
    return "fresh", {"fresh": 0.85}, 0.85


def _kept_path(cache_dir, what: str, how: str):
    return cache_dir / f"judge-{hashlib.sha256(json.dumps([model(), what, how]).encode()).hexdigest()[:20]}.json"


def recall(what: str, how: str, cache_dir) -> None:
    """A picture found made already (its own file): the answer that made it, kept, is reported again (DECIDED), so the
    page still says how it came to be. Nothing is asked."""
    try:
        record = json.loads(_kept_path(cache_dir, what, how).read_text())
    except (OSError, ValueError):
        return
    record.update(asked_now=False, usd=0.0)
    record.setdefault("action", "fresh")
    with _lock:
        DECIDED.setdefault(what, record)


def decide(what: str, purpose: str, how: str, shortlist: list[tuple[dict, bool]], cache_dir, same_thing, names,
           find) -> dict:
    """{"action": "reuse"|"match"|"fresh", "row": the picture chosen (reuse, match), and the record kept in DECIDED}.
    `shortlist`: [(a picture made before, whether it can be shown again as it is)]; `find(key)`: a picture made
    before by its file's name. An answer is kept by the request (not the shortlist, which grows as pictures are
    made): asked again only when the picture it chose is gone."""
    keys = [str(row["png"].stem) for row, _ in shortlist]
    kept = _kept_path(cache_dir, what, how)
    record = None
    try:
        record = json.loads(kept.read_text())
        record["asked_now"] = False
        record["usd"] = 0.0
        picked = _picked_key(record)
        found = find(picked) if picked else None
        if picked and found is None:
            record = None                       # the picture it chose is gone: asked again
        elif picked:
            k = int(str(record["choice"]).split("_", 1)[1])
            shortlist = [(found if i == k else ({"png": Path(c["key"]), **c}), c.get("reusable", False))
                         for i, c in enumerate(record["candidates"])]
        else:
            shortlist = []
    except (OSError, ValueError, KeyError, IndexError):
        record = None
    if record is None:
        options = [f"reuse_{k}" for k, (_, ok) in enumerate(shortlist) if ok] + \
                  [f"match_{k}" for k in range(len(shortlist))] + ["fresh"]
        criteria = {f"reuse_{k}": f"Show PICTURE {k} again as it is: it shows exactly what is asked now"
                    for k, (_, ok) in enumerate(shortlist) if ok}
        criteria.update({f"match_{k}": f"Draw a new picture that matches PICTURE {k}: the same person, place or thing, "
                         "in the view, pose, moment or scene asked now" for k in range(len(shortlist))})
        criteria["fresh"] = "None of them: draw a new picture from nothing"
        state = [f"THE PICTURE NEEDED NOW:\n  asked for: {what[:800]}\n  how it is drawn: {how}"
                 + (f"\n  what it is for: {purpose[:600]}" if purpose else "")]
        state += [_candidate_text(k, row, ok) for k, (row, ok) in enumerate(shortlist)]
        record = {"what": what, "model": model(), "candidates": [
            {"key": keys[k], "what": str(row.get("what") or "")[:300], "prompt": str(row.get("prompt") or "")[:600],
             "reusable": ok} for k, (row, ok) in enumerate(shortlist)], "state": state, "criteria": criteria,
            "asked_now": True, "usd": 0.0}
        began = time.time()
        try:
            if _fake():
                choice, probabilities, confidence = _stand_in(what, shortlist, same_thing, names)
                record["fake"] = True
            else:
                reply, usd = _ask(state, criteria)
                record["usd"] = usd
                choice, probabilities, confidence = _read(_answer(reply), options)
                record["raw"] = reply
        except Exception as error:  # noqa: BLE001 -- unanswered: drawn fresh, and said
            choice, probabilities, confidence = None, {}, None
            record["error"] = str(error)[:300]
        record.update(choice=choice, probabilities=probabilities, confidence=confidence,
                      seconds=round(time.time() - began, 2))
        if not record.get("error"):
            cache_dir.mkdir(parents=True, exist_ok=True)
            kept.write_text(json.dumps({k: v for k, v in record.items() if k not in ("asked_now", "usd")}))
    choice, confidence = record.get("choice"), record.get("confidence")
    action, chosen = "fresh", None
    if not shortlist:
        choice = None
    if choice and choice != "fresh":
        kind, k = choice.split("_", 1)
        chosen = shortlist[int(k)][0] if k.isdigit() and int(k) < len(shortlist) else None
        action = kind if chosen is not None else "fresh"
        if action != "fresh" and confidence is not None and confidence < sure():
            # Unsure: a reuse is drawn anew to match the picture (still alike), a match is drawn fresh.
            action = "match" if action == "reuse" else "fresh"
            record["unsure"] = True
            chosen = chosen if action == "match" else None
    record["action"] = action
    record["picked"] = str(chosen["png"].stem) if chosen is not None else None
    if record.get("asked_now") and not record.get("error"):
        kept.write_text(json.dumps({k: v for k, v in record.items() if k not in ("asked_now", "usd", "raw")}))
    with _lock:
        if record.get("asked_now") or what not in DECIDED:
            DECIDED[what] = {k: v for k, v in record.items() if k != "raw"}
    return {"action": action, "row": chosen, "record": record}
