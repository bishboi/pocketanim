"""A YouTube video as a lecture's reference: its transcript, split into the parts the video teaches in order.

    python youtube_source.py "https://www.youtube.com/watch?v=VIDEO" out/            # fetch the transcript
    python youtube_source.py --transcript transcript.txt out/ [--title "..."]          # a transcript pasted in

It writes the same manifest as pdf_source.py (manifest.json, document.md), with "source": "youtube", no figures
(the lecture draws its own diagrams), and the video's parts: where each starts and ends and what it says. The
lecture follows those parts in order, so the generated video has the reference video's structure.

The transcript comes from YouTube's captions (youtube-transcript-api): hand-made ones first, then automatic
ones, Hindi and English preferred. YouTube refuses requests from many cloud servers and some networks; then
paste the transcript instead (on YouTube: ... > Show transcript, select all, copy). Timestamps like "2:15" in a
pasted transcript are kept.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

CACHE = Path(os.environ.get("PANIM_PDF_CACHE") or (Path(__file__).resolve().parent / ".cache" / "pdf"))
LANGUAGES = ("hi", "en", "en-IN", "hi-IN", "en-US", "en-GB")
PART_SECONDS = 150          # a part of the reference video: about two and a half minutes of it
ID_PATTERN = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/|/v/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")


def video_id(url: str) -> str:
    match = ID_PATTERN.search(url.strip())
    if not match:
        raise ValueError(f"not a YouTube link: {url!r}")
    return match.group(1) or match.group(2)


def _metadata(vid: str) -> dict:
    """The video's title and channel, from YouTube's oEmbed (no key needed). Empty when it cannot be reached."""
    try:
        import requests

        answer = requests.get("https://www.youtube.com/oembed",
                              params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"}, timeout=20)
        if answer.ok:
            data = answer.json()
            return {"title": data.get("title"), "channel": data.get("author_name")}
    except Exception:  # noqa: BLE001 -- the title is a nicety
        pass
    return {}


def fetch_transcript(vid: str) -> tuple[list[dict], str, bool]:
    """[{text, start, duration}], its language code, and whether YouTube generated it."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as error:
        raise RuntimeError("youtube-transcript-api is not installed: rerun harness/scripts/setup-python.sh") from error

    api = YouTubeTranscriptApi()
    try:
        available = api.list(vid)
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(_why(error)) from error
    chosen = None
    for finder in ("find_manually_created_transcript", "find_generated_transcript"):
        try:
            chosen = getattr(available, finder)(list(LANGUAGES))
            break
        except Exception:  # noqa: BLE001 -- none in these languages of this kind
            continue
    if chosen is None:
        chosen = next(iter(available), None)
    if chosen is None:
        raise RuntimeError("this video has no captions to read; paste its transcript instead")
    try:
        fetched = chosen.fetch()
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(_why(error)) from error
    snippets = [{"text": s.text, "start": float(s.start), "duration": float(s.duration)} for s in fetched]
    return snippets, chosen.language_code, bool(chosen.is_generated)


def _why(error: Exception) -> str:
    name = type(error).__name__
    if name in ("IpBlocked", "RequestBlocked"):
        return ("YouTube refused the request from this network (it blocks many servers and VPNs). Paste the "
                "transcript instead: on YouTube open ... > Show transcript, select it all and copy.")
    if name == "TranscriptsDisabled":
        return "captions are turned off for this video; paste a transcript instead"
    if name in ("VideoUnavailable", "VideoUnplayable", "AgeRestricted"):
        return f"YouTube says the video cannot be read ({name}); try another, or paste its transcript"
    return f"{name}: {error}".split("\n")[0][:300]


STAMP = re.compile(r"^\s*\(?(\d{1,2}(?::\d{2}){1,2})\)?\s*[-–:]?\s*(.*)$")


# A caption tool's line: "* `00:00:04.400`[words](https://...)" (Tactiq), "[00:01:02] words", "00:04.400 words".
MARKDOWN_LINE = re.compile(r"^\s*[-*•]?\s*`?\[?(\d{1,2}(?::\d{2}){1,2}(?:[.,]\d+)?)\]?`?\s*\[?(.*?)\]?(?:\(https?://[^)]*\))?\s*$")
# What automatic captions of a class video are full of and a lecture never says: channel promotion, music tags.
JUNK = re.compile(r"सब्सक्राइब|सबस्क्राइब|subscribe|बेल आइकॉन|bell icon|like (?:and|&) share|\[(?:संगीत|music|applause)\]",
                  re.I)


def _seconds(stamp: str) -> float:
    whole, _, fraction = stamp.replace(",", ".").partition(".")
    parts = [int(p) for p in whole.split(":")]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts))) + (float(f"0.{fraction}") if fraction else 0.0)


def parse_pasted(text: str) -> list[dict]:
    """A pasted transcript as snippets. Lines starting with a timestamp (2:15, 1:02:03, `00:00:04.400` as caption
    tools export it) keep it; plain text is timed by its words at about 2.5 words a second. Channel promotion
    ("subscribe", the bell icon) and [music] tags are dropped."""
    snippets: list[dict] = []
    clock = 0.0
    pending: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        marked = MARKDOWN_LINE.match(line) if re.search(r"\d:\d\d", line[:20]) else None
        if marked and marked.group(2).strip():
            clock = _seconds(marked.group(1))
            words = JUNK.sub(" ", marked.group(2)).strip()
            if words and not re.fullmatch(r"[\W\d]*", words):
                snippets.append({"text": words, "start": clock, "duration": 0.0})
            continue
        line = JUNK.sub(" ", line).strip()
        if not line:
            continue
        stamp = STAMP.match(line)
        if stamp and re.fullmatch(r"\d{1,2}(?::\d{2}){1,2}", stamp.group(1)):
            parts = [int(p) for p in stamp.group(1).split(":")]
            seconds = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
            clock = float(seconds)
            rest = stamp.group(2).strip()
            if rest:
                snippets.append({"text": rest, "start": clock, "duration": 0.0})
            else:
                pending = ""          # YouTube's copy puts the time on its own line, the words on the next
            continue
        if pending is not None:
            snippets.append({"text": line, "start": clock, "duration": 0.0})
            pending = None
            continue
        start = snippets[-1]["start"] + max(1.0, len(snippets[-1]["text"].split()) / 2.5) if snippets else clock
        snippets.append({"text": line, "start": start, "duration": 0.0})
    for a, b in zip(snippets, snippets[1:]):
        a["duration"] = max(0.5, b["start"] - a["start"])
    if snippets:
        snippets[-1]["duration"] = max(1.0, len(snippets[-1]["text"].split()) / 2.5)
    return snippets


def _clean(text: str) -> str:
    text = re.sub(r"\[(?:music|applause|laughter|संगीत|तालियाँ)[^\]]*\]", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def parts_of(snippets: list[dict], target: float = PART_SECONDS) -> list[dict]:
    """The transcript cut into parts of about `target` seconds, at a pause or a sentence end near that length."""
    parts: list[dict] = []
    current: list[dict] = []
    for index, snip in enumerate(snippets):
        text = _clean(snip["text"])
        if not text:
            continue
        current.append({**snip, "text": text})
        span = current[-1]["start"] + current[-1]["duration"] - current[0]["start"]
        following = snippets[index + 1] if index + 1 < len(snippets) else None
        gap = following["start"] - (snip["start"] + snip["duration"]) if following else 0.0
        ends_sentence = bool(re.search(r"[.?!।]$", text))
        if span >= target * 1.4 or (span >= target * 0.7 and (gap > 1.2 or ends_sentence)):
            parts.append(current)
            current = []
    if current:
        if parts and current[-1]["start"] + current[-1]["duration"] - current[0]["start"] < target * 0.35:
            parts[-1].extend(current)            # a short tail joins the part before it
        else:
            parts.append(current)
    out = []
    for number, chunk in enumerate(parts, 1):
        start = chunk[0]["start"]
        end = chunk[-1]["start"] + chunk[-1]["duration"]
        out.append({"part": number, "start": round(start, 1), "end": round(end, 1),
                    "text": " ".join(c["text"] for c in chunk)})
    return out


def clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else \
        f"{seconds // 60}:{seconds % 60:02d}"


def markdown_of(meta: dict, parts: list[dict]) -> str:
    head = [f"# {meta.get('title') or 'Reference video'}"]
    if meta.get("channel"):
        head.append(f"Channel: {meta['channel']}")
    if meta.get("url"):
        head.append(f"Video: {meta['url']}")
    head.append(f"Transcript: {meta.get('language') or '?'}"
                f"{' (automatic captions: expect misheard words)' if meta.get('generated') else ''}")
    body = [f"## Part {p['part']} ({clock(p['start'])}–{clock(p['end'])})\n\n{p['text']}" for p in parts]
    return "\n\n".join(["\n".join(head), *body]) + "\n"


def convert(source: str, out: str | Path, pasted: str | None = None, title: str | None = None) -> dict:
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if pasted is not None:
        digest = "tx" + hashlib.sha256(pasted.encode("utf-8")).hexdigest()[:14]
        meta = {"title": title or "Pasted transcript", "url": source or None, "language": None, "generated": False}
        snippets = parse_pasted(pasted)
    else:
        vid = video_id(source)
        digest = "yt" + vid
        cached = CACHE / digest / "manifest.json"
        if cached.exists():
            manifest = json.loads(cached.read_text(encoding="utf-8"))
            (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
            return manifest
        snippets, language, generated = fetch_transcript(vid)
        meta = {**_metadata(vid), "url": f"https://www.youtube.com/watch?v={vid}", "id": vid, "language": language,
                "generated": generated}
        if title:
            meta["title"] = title
    if not snippets:
        raise RuntimeError("the transcript is empty")
    parts = parts_of(snippets)
    work = CACHE / digest
    work.mkdir(parents=True, exist_ok=True)
    markdown = markdown_of(meta, parts)
    (work / "document.md").write_text(markdown, encoding="utf-8")
    duration = parts[-1]["end"] if parts else 0.0
    manifest = {"digest": digest, "source": "youtube", "pages": 0, "figures": [], "markdown": str(work / "document.md"),
                "words": len(markdown.split()), "video": {**meta, "duration": round(duration, 1)}, "parts": parts,
                "note": ("automatic captions: the model is told to expect misheard words" if meta.get("generated")
                         else None)}
    (work / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> int:
    args = sys.argv[1:]
    title = None
    if "--title" in args:
        i = args.index("--title")
        title = args[i + 1]
        del args[i:i + 2]
    try:
        if args and args[0] == "--transcript" and len(args) == 3:
            text = Path(args[1]).read_text(encoding="utf-8")
            url = os.environ.get("PANIM_REFERENCE_URL", "")
            result = convert(url, args[2], pasted=text, title=title)
        elif len(args) == 2:
            result = convert(args[0], args[1], title=title)
        else:
            print(__doc__)
            return 2
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001 -- the app shows this line
        print(json.dumps({"error": str(error) if isinstance(error, (RuntimeError, ValueError))
                          else f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
