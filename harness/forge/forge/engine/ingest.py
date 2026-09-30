"""Intake: sources in, cited passages out.

Every file, URL and the brief itself become passages of a few sentences with an
id (p01, p02, ...). Facts cite passages; the script may only use facts; so every
number in the video traces back to a line of a source.
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
from pathlib import Path

from forge.util import sentences, write_json

PASSAGE_CHARS = 380    # a few sentences: small enough that one passage has one topic


def _clean_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>|</p>|</h\d>|</li>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


def read_source(source: str, base: Path) -> tuple[str, str]:
    """(title, text) of a file path or URL. Raises on anything unreadable."""
    if re.match(r"https?://", source):
        request = urllib.request.Request(source, headers={"User-Agent": "lecture-forge/0.4"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
        return source, _clean_html(raw) if "<" in raw[:2000] else raw
    path = Path(source)
    if not path.is_absolute():
        path = base / path
    if path.suffix.lower() == ".pdf":
        raise ValueError("a PDF is read with read_pdf")
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        text = _clean_html(text)
    return path.name, text


def read_pdf(source: str, base: Path, source_id: str, out: Path) -> tuple[str, str, list[dict], dict]:
    """(title, text, figures, manifest) of a PDF, via harness/lecture/pdf_source.py.

    Figure ids are prefixed with the source id (s2_fig3), in the text's
    [FIGURE ...] markers too, so two documents never collide.
    """
    import pdf_source

    path = Path(source) if Path(source).is_absolute() else base / source
    manifest = pdf_source.convert(path, out / source_id)
    text = Path(manifest["markdown"]).read_text(encoding="utf-8")
    # Figures the user removed on the upload page: excluded.json beside the PDF (the app writes it).
    removed_file = path.parent / "excluded.json"
    removed = set(json.loads(removed_file.read_text())) if removed_file.exists() else set()
    figures = []
    for fig in manifest["figures"]:
        if fig["id"] in removed:
            text = re.sub(r"\[FIGURE " + re.escape(fig["id"]) + r":[^\]]*\]\n?", "", text)
            continue
        fid = f"{source_id}_{fig['id']}"
        text = text.replace(f"[FIGURE {fig['id']}:", f"[FIGURE {fid}:")
        figures.append({**fig, "id": fid, "source": source_id})
    return path.name, text, figures, manifest


def passages_of(text: str, source_id: str, start: int) -> list[dict]:
    """Paragraphs, then sentences packed into passages of about PASSAGE_CHARS."""
    out = []
    for para in re.split(r"\n\s*\n|\r\n\s*\r\n", text):
        para = re.sub(r"^#+\s*", "", para.strip())
        if len(para) < 20:
            continue
        chunk = []
        for sentence in sentences(para):
            chunk.append(sentence)
            if sum(len(s) for s in chunk) > PASSAGE_CHARS:
                out.append(" ".join(chunk))
                chunk = []
        if chunk:
            out.append(" ".join(chunk))
    return [{"id": f"p{start + i:02d}", "source": source_id, "text": t} for i, t in enumerate(out)]


def intake(job) -> dict:
    """Build the content bundle. Unreadable sources are reported, not fatal."""
    spec = job.spec
    sources_dir = job.path("sources")
    sources_dir.mkdir(exist_ok=True)
    passages, sources, problems = [], [], []
    items = []
    if spec.get("brief"):
        items.append(("brief", "brief", spec["brief"]))
    figures = []
    for index, source in enumerate(spec.get("sources") or [], 1):
        try:
            if re.search(r"(youtube\.com/|youtu\.be/)", str(source)):
                # A reference video: its transcript, in the parts the video teaches (harness/lecture/youtube_source.py).
                import youtube_source

                manifest = youtube_source.convert(str(source), sources_dir / f"s{index}")
                title = (manifest.get("video") or {}).get("title") or str(source)
                text = Path(manifest["markdown"]).read_text(encoding="utf-8")
                if manifest.get("note"):
                    problems.append(f"{source}: {manifest['note']}")
            elif str(source).lower().endswith(".pdf"):
                title, text, found, manifest = read_pdf(source, job.dir, f"s{index}", sources_dir)
                figures += found
                if manifest.get("note"):
                    problems.append(f"{source}: {manifest['note']}")
            else:
                title, text = read_source(source, job.dir)
            items.append((f"s{index}", title, text))
        except Exception as error:  # noqa: BLE001 -- reported, and the job continues
            problems.append(f"{source}: {type(error).__name__}: {error}")
    for source_id, title, text in items:
        found = passages_of(text, source_id, len(passages) + 1)
        passages.extend(found)
        sources.append({"id": source_id, "title": title, "passages": [p["id"] for p in found]})
    for p in passages:
        (sources_dir / f"{p['id']}.txt").write_text(p["text"] + "\n", encoding="utf-8")
    bundle = {"passages": passages, "sources": sources, "problems": problems, "figures": figures,
              "words": sum(len(p["text"].split()) for p in passages)}
    write_json(job.path("bundle.json"), bundle)
    return bundle
