"""Books: a PDF uploaded, read, and scripted into short videos, each one made as a run (runs.py).

A book lives in harness_v3/books/<id>/: source.pdf, pages.json (each page's text) and book.json (its title, pages,
sections, scripts and calls). The steps:

    read     the PDF read by Datalab (datalab.py; DATALAB_API_KEY): each page's text, and the sections from its
             headings (else every few pages). Datalab's result is kept (datalab.json) and cached by the PDF's hash.
    script   one model call: the pages chosen (a section, or a page range) written as a few short videos, each a
             title and its narration (prompts.SCRIPT). A book may have several scripts (other pages, other notes).
    build    each video (or all of them) made as a run from its narration: voice, storyboard, score, render, critic.

The script's calls are kept on the book with their tokens and cost; its videos' runs keep theirs, and the book adds
them up.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

import datalab
import prompts
import runs

BOOKS = runs.ROOT / "books"
# Short videos by default, to try things quickly; V3_LONG_VIDEOS=1: each script one long video of V3_VIDEO_MINUTES.
LONG = os.environ.get("V3_LONG_VIDEOS", "0").strip().lower() in ("1", "true", "yes", "on")
MAX_CHARS = 100000  # the pages a script call reads (about 25k tokens: enough for a 20-minute video)
_busy: set[str] = set()
_lock = threading.Lock()


def book_dir(bid: str) -> Path:
    if not re.fullmatch(r"[\w-]+", bid):
        raise ValueError("bad book id")
    return BOOKS / bid


def load(bid: str) -> dict:
    return json.loads((book_dir(bid) / "book.json").read_text())


def save(book: dict) -> None:
    d = book_dir(book["id"])
    book["cost"] = round(sum(c.get("cost") or 0 for c in book["calls"]), 6)
    book["tokens"] = sum((c.get("tokens_in") or 0) + (c.get("tokens_out") or 0) for c in book["calls"])
    tmp = d / "book.json.tmp"
    tmp.write_text(json.dumps(book, indent=1))
    tmp.replace(d / "book.json")


def pages(bid: str) -> list[str]:
    return json.loads((book_dir(bid) / "pages.json").read_text())


def listing() -> list[dict]:
    out = []
    for p in sorted(BOOKS.glob("*/book.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            b = json.loads(p.read_text())
        except Exception:  # noqa: BLE001 -- a book being written
            continue
        made = videos_cost(b)
        rc = (b.get("read") or {}).get("cost") or 0
        out.append({k: b.get(k) for k in ("id", "title", "created", "pages")} |
                   {"cost": round((b.get("cost") or 0) + rc + made["cost"], 6), "script_cost": (b.get("cost") or 0) + rc, "tokens": (b.get("tokens") or 0) + made["tokens"],
                    "videos": made["count"], "status": "running" if b["id"] in _busy else b.get("status", "done")})
    return out


def videos_cost(book: dict) -> dict:
    """The runs made from this book's videos: how many, and their cost and tokens."""
    cost, tokens, count = 0.0, 0, 0
    for sc in book.get("scripts", []):
        for v in sc.get("videos", []):
            if v.get("run"):
                try:
                    r = runs.load(v["run"])
                except FileNotFoundError:
                    continue
                cost += r.get("cost") or 0
                tokens += r.get("tokens") or 0
                count += 1
    return {"cost": round(cost, 6), "tokens": tokens, "count": count}


# ---------------------------------------------------------------- read ------------------------------------------------

def add(name: str, data: bytes) -> dict:
    """The PDF kept, and read by Datalab in a thread (the book is "reading" till then)."""
    if not data.startswith(b"%PDF"):
        raise ValueError("that is not a PDF")
    if not os.environ.get("DATALAB_API_KEY", "").strip():
        raise ValueError("DATALAB_API_KEY is not set: the PDF is read by Datalab")
    bid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    d = book_dir(bid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.pdf").write_bytes(data)
    book = {"id": bid, "title": re.sub(r"\.pdf$", "", name, flags=re.I).replace("_", " ").strip() or "Untitled",
            "name": name, "created": time.time(), "pages": 0, "status": "reading", "sections": [], "scripts": [],
            "calls": [], "cost": 0.0, "tokens": 0, "read": {"status": "running", "started": time.time(), "notes": []}}
    save(book)
    threading.Thread(target=_read, args=(bid,), daemon=True).start()
    return book


def reread(bid: str) -> None:
    """A read that failed (or any read) started again from the kept PDF."""
    with _lock:
        book = load(bid)
        if book.get("status") == "reading":
            raise RuntimeError("the PDF is being read: wait for it")
        book["status"] = "reading"
        book["read"] = {"status": "running", "started": time.time(), "notes": []}
        save(book)
    threading.Thread(target=_read, args=(bid,), daemon=True).start()


def _read(bid: str) -> None:
    d = book_dir(bid)
    notes: list[str] = []
    read: dict = {}
    try:
        result, cached = datalab.convert((d / "source.pdf").read_bytes())
        (d / "datalab.json").write_text(json.dumps(result.get("json")))
        texts, heads, title = datalab.pages_and_heads(result["json"])
        (d / "pages.json").write_text(json.dumps(texts))
        n = len(texts)
        sections = _sections(heads, n)
        chars = sum(len(t) for t in texts)
        cents = (result.get("cost_breakdown") or {}).get("final_cost_cents")
        notes.append(f"{n} pages, {chars} characters, {len(sections)} sections"
                     + (" (from its headings)" if heads else " (no headings: every few pages)"))
        notes.append("Datalab's earlier result for this PDF (no new conversion)" if cached
                     else f"converted by Datalab ({os.environ.get('DATALAB_MODE') or 'balanced'} mode)")
        read = {"status": "done", "notes": notes, "cost": 0.0 if cached or cents is None else round(cents / 100, 4)}
        with _lock:
            book = load(bid)
            book.update({"pages": n, "sections": sections, "status": "done"})
            if title and book["title"] == re.sub(r"\.pdf$", "", book["name"], flags=re.I).replace("_", " ").strip():
                book["title"] = title[:120]
            book["read"] = book["read"] | read
            _finish_read(book)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        with _lock:
            book = load(bid)
            book["status"] = "failed"
            book["read"] |= {"status": "failed", "error": str(e)[:1500]}
            _finish_read(book)


def _finish_read(book: dict) -> None:
    r = book["read"]
    r["ended"] = time.time()
    r["seconds"] = round(r["ended"] - r["started"], 1)
    save(book)


def _sections(heads: list[dict], n: int) -> list[dict]:
    """The book's sections from its headings' top two levels (each runs to the page the next one starts on); every
    few pages when it has none."""
    if heads:
        top = min(h["level"] for h in heads)
        heads = [h for h in heads if h["level"] <= top + 1]
        out = []
        for k, h in enumerate(heads):
            nxt = next((x["page"] for x in heads[k + 1:] if x["level"] <= h["level"]), n)
            out.append({"title": h["title"], "level": h["level"] - top, "from": h["page"], "to": max(h["page"], nxt)})
        return out
    step = 4 if n > 8 else max(1, n)
    return [{"title": f"Pages {a}-{min(n, a + step - 1)}", "level": 0, "from": a, "to": min(n, a + step - 1)}
            for a in range(1, n + 1, step)]


# ---------------------------------------------------------------- script ----------------------------------------------

def pages_text(bid: str, a: int, b: int) -> str:
    texts = pages(bid)
    a, b = max(1, a), min(len(texts), b)
    out = "\n\n".join(f"[page {k}]\n{texts[k - 1]}" for k in range(a, b + 1))
    return out[:MAX_CHARS]


def script(bid: str, a: int, b: int, settings: dict) -> str:
    """Start a script of pages a-b (in a thread); its id."""
    with _lock:
        if bid in _busy:
            raise RuntimeError("this book is busy writing a script: wait for it")
        book = load(bid)
        if book.get("status") != "done":
            raise RuntimeError("the PDF is not read yet")
        a, b = max(1, int(a)), min(book["pages"], int(b))
        if a > b:
            raise ValueError("the pages are empty")
        sid = uuid.uuid4().hex[:6]
        sec = next((s["title"] for s in book["sections"] if s["from"] == a and s["to"] == b), "")
        book["scripts"].append({"id": sid, "from": a, "to": b, "title": sec or f"Pages {a}-{b}",
                                "settings": {"model": settings.get("model") or os.environ.get("V3_MODEL_SCRIPT") or runs.DEFAULT_MODEL,
                                             # short videos to try things quickly (videos x seconds, from the
                                             # page); V3_LONG_VIDEOS=1: one long video (prompts.VIDEO_MINUTES)
                                             "videos": 1 if LONG else max(1, min(12, int(settings.get("videos") or 3))),
                                             "seconds": int(prompts.VIDEO_MINUTES * 60) if LONG
                                             else max(15, min(300, int(settings.get("seconds") or 40))),
                                             "long": LONG,
                                             "notes": str(settings.get("notes") or ""),
                                             "language": settings.get("language") if settings.get("language") in runs.LANGUAGES else "en"},
                                "status": "running", "started": time.time(), "videos": []})
        save(book)
        _busy.add(bid)
    threading.Thread(target=_script, args=(bid, sid), daemon=True).start()
    return sid


def _keep(bid: str, sc: dict, calls: list[dict]) -> None:
    """This script and its calls written into the book as it is now (videos may be built meanwhile)."""
    with _lock:
        book = load(bid)
        mine = {c["id"] for c in calls}
        book["calls"] = [c for c in book["calls"] if c["id"] not in mine] + calls
        book["scripts"] = [sc if s["id"] == sc["id"] else s for s in book["scripts"]]
        save(book)


def _script(bid: str, sid: str) -> None:
    sc = next(s for s in load(bid)["scripts"] if s["id"] == sid)
    st = sc["settings"]
    calls: list[dict] = []
    try:
        if not st.get("long"):                  # a few short videos, one call (the quick way to try things)
            system, user = prompts.script_prompt(pages_text(bid, sc["from"], sc["to"]), st["videos"], st["seconds"],
                                                 st["notes"], st.get("language"))
            rec = {"settings": {"model": st["model"]}, "calls": calls}
            text = runs.chat(rec, "script", f"pages {sc['from']}-{sc['to']}", system, user,
                             max_tokens=min(32000, max(4000, int(st["videos"] * st["seconds"] * 4.2) + 600)),
                             saver=lambda _: _keep(bid, sc, calls))
            videos = prompts.parse_script(text)
            if not videos:
                raise RuntimeError("the answer had no `VIDEO:` parts: " + text[:300])
            sc["videos"] = [v | {"run": None} for v in videos]
            sc["status"] = "done"
            return
        # One long video, in two steps (a single call writes far less than it is asked for): its chapters planned,
        # then each chapter written by itself, all at once, each told its length and what comes either side.
        pages_ = pages_text(bid, sc["from"], sc["to"])
        rec = {"settings": {"model": st["model"]}, "calls": calls}
        lock = threading.Lock()

        def keep(_):
            with lock:
                _keep(bid, sc, calls)
        system, user = prompts.outline_prompt(pages_, st["notes"], st.get("language"), st["seconds"] / 60)
        text = runs.chat(rec, "script", f"pages {sc['from']}-{sc['to']}: the chapters", system, user, max_tokens=2500,
                         saver=keep)
        title, chapters = prompts.parse_outline(text)
        if not chapters:
            raise RuntimeError("the plan had no `CHAPTER:` lines: " + text[:300])

        def write(k):
            system, user = prompts.chapter_prompt(pages_, title, chapters, k, st["notes"], st.get("language"))
            words = int(chapters[k]["minutes"] * prompts.WORDS_A_MINUTE)
            out = runs.chat(rec, "script", f"chapter {k + 1}: {chapters[k]['title']}", system, user,
                            max_tokens=int(words * 2.6) + 400, saver=keep)
            # (list marks a model adds taken off; a character's `@name:` and a `{cue}` kept)
            lines = [ln.strip() if ln.lstrip().startswith(("@", "{")) else re.sub(r"^[\s*\-•>#\d.)]*", "", ln).strip()
                     for ln in out.splitlines()]
            return [ln for ln in lines if ln and not ln.lower().startswith(("chapter", "title:", "```"))]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(chapters))) as pool:
            parts = list(pool.map(write, range(len(chapters))))
        # each chapter marked (`# Title`: not spoken; the score's chapter bar and cards, the video's chapter list)
        narration = "\n".join(f"# {c['title']}\n" + "\n".join(part) for c, part in zip(chapters, parts))
        sc["chapters"] = [{**c, "words": len(" ".join(p).split())} for c, p in zip(chapters, parts)]
        sc["videos"] = [{"title": title or sc["title"], "narration": narration, "run": None}]
        sc["status"] = "done"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        sc.update({"status": "failed", "error": str(e)[:1500]})
    finally:
        sc["ended"] = time.time()
        sc["seconds"] = round(sc["ended"] - sc["started"], 1)
        sc["cost"] = round(sum(c.get("cost") or 0 for c in calls), 6)
        _keep(bid, sc, calls)
        _busy.discard(bid)


def set_video(bid: str, sid: str, k: int, title: str, narration: str) -> None:
    """A video's title or narration changed by hand (before it is built, or to build it again)."""
    with _lock:
        book = load(bid)
        v = next(s for s in book["scripts"] if s["id"] == sid)["videos"][k]
        v.update({"title": title.strip() or v["title"], "narration": narration.strip()})
        save(book)


def delete_script(bid: str, sid: str) -> None:
    with _lock:
        book = load(bid)
        book["scripts"] = [s for s in book["scripts"] if s["id"] != sid]
        save(book)


# ---------------------------------------------------------------- build -----------------------------------------------

def build(bid: str, sid: str, which: int | None, settings: dict) -> list[str]:
    """Video `which` of the script (every video not yet built, when None) made as runs; their ids. Runs wait their
    turn (runs.V3_PARALLEL at once)."""
    with _lock:
        book = load(bid)
        sc = next(s for s in book["scripts"] if s["id"] == sid)
        ks = [which] if which is not None else [k for k, v in enumerate(sc["videos"]) if not v.get("run")]
        made = []
        for k in ks:
            v = sc["videos"][k]
            run = runs.create(f"{book['title']} · {v['title']}", v["narration"],
                              {"language": sc["settings"].get("language") or "en"} | settings | {"book": {"id": bid, "title": book["title"], "script": sid, "video": k,
                                                   "pages": f"{sc['from']}-{sc['to']}"}})
            v["run"] = run["id"]
            v.setdefault("runs", []).append(run["id"])
            made.append(run["id"])
        save(book)
    for rid in made:
        runs.start(rid, "voice")
    return made


def view(bid: str) -> dict:
    """The book with every video's run (status, cost, tokens, length) beside it."""
    book = load(bid)
    for sc in book["scripts"]:
        for v in sc["videos"]:
            if v.get("run"):
                try:
                    r = runs.load(v["run"])
                    v["run_info"] = {"status": r.get("status"), "cost": r.get("cost"), "tokens": r.get("tokens"),
                                     "seconds": (r.get("words") or {}).get("seconds"),
                                     "video": (runs.run_dir(r["id"]) / "video.mp4").exists(),
                                     "steps": {k: s.get("status") for k, s in r["steps"].items()}}
                except FileNotFoundError:
                    v["run_info"] = None
    made = videos_cost(book)
    rc = (book.get("read") or {}).get("cost") or 0
    return {"book": book, "busy": bid in _busy, "videos": made,
            "total": {"cost": round((book.get("cost") or 0) + rc + made["cost"], 6),
                      "tokens": (book.get("tokens") or 0) + made["tokens"]}}


def recover() -> list[str]:
    """Books the server was reading or scripting when it stopped: the read failed (read it again), the script
    failed (write it again)."""
    out = []
    for p in BOOKS.glob("*/book.json"):
        try:
            book = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        hit = False
        if book.get("status") == "reading":
            book["status"] = "failed"
            book["read"] |= {"status": "failed", "error": "the server stopped while it was reading: read it again"}
            hit = True
        for sc in book.get("scripts", []):
            if sc.get("status") == "running":
                sc.update({"status": "failed", "error": "the server stopped while it was writing: write it again"})
                hit = True
        for c in book.get("calls", []):
            if c.get("status") == "running":
                c.update({"status": "failed", "error": "the server stopped during this call"})
        if hit:
            save(book)
            out.append(book["id"])
    return out
