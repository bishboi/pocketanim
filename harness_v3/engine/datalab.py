"""A PDF read by Datalab's convert API, as harness_v2 reads it (lib/datalab.ts): output_format=json, which gives
every block of every page with its type (SectionHeader, Text, ListGroup, Table, Caption, Picture, PageHeader...)
and its content as HTML. The key is DATALAB_API_KEY (DATALAB_HOST, DATALAB_MODE as in v2). There is no reader
without it: a PDF's own text layer has too many faults (columns, headers, hyphens, scans).

A result is cached by the PDF's hash in harness_v3/.cache/datalab/, so a PDF is converted (and paid for) once.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from html.parser import HTMLParser
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "datalab"
SKIP = {"PageHeader", "PageFooter"}


def _host() -> str:
    return (os.environ.get("DATALAB_HOST") or "https://www.datalab.to").rstrip("/")


def _get(url: str, key: str | None) -> dict:
    req = urllib.request.Request(url, headers={"X-Api-Key": key} if key else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def convert(pdf: bytes) -> tuple[dict, bool]:
    """Datalab's result for the PDF ({json, images, page_count, ...}) and whether it came from the cache."""
    key = os.environ.get("DATALAB_API_KEY", "").strip()
    cache = CACHE / (hashlib.sha256(pdf).hexdigest()[:20] + ".json")
    if cache.exists():
        return json.loads(cache.read_text()), True
    if not key:
        raise RuntimeError("DATALAB_API_KEY is not set: the PDF is read by Datalab")
    fields = {"output_format": "json", "mode": os.environ.get("DATALAB_MODE") or "balanced",
              "disable_image_extraction": "false"}
    bound = uuid.uuid4().hex
    body = b"".join(f'--{bound}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in fields.items())
    body += (f'--{bound}\r\nContent-Disposition: form-data; name="file"; filename="book.pdf"\r\n'
             f"Content-Type: application/pdf\r\n\r\n").encode() + pdf + f"\r\n--{bound}--\r\n".encode()
    req = urllib.request.Request(f"{_host()}/api/v1/convert", data=body, method="POST",
                                 headers={"X-Api-Key": key, "Content-Type": f"multipart/form-data; boundary={bound}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            start = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Datalab refused the PDF ({e.code}): {e.read()[:300].decode(errors='replace')}") from e
    check = start.get("request_check_url")
    if not check:
        raise RuntimeError(f"Datalab refused the PDF: {start.get('error') or start}")
    if not check.startswith("http"):
        check = f"{_host()}/{check.lstrip('/')}"
    deadline = time.time() + 20 * 60
    while time.time() < deadline:
        time.sleep(2.5)
        result = _get(check, key)
        if result.get("success") is False or result.get("status") == "failed":
            raise RuntimeError(f"Datalab could not convert the PDF: {result.get('error') or 'failed'}")
        if result.get("status") != "complete":
            continue
        if isinstance(result.get("result_url"), str):
            full = _get(result["result_url"], None)
            for k, v in result.items():  # the downloaded result wins; the status reply fills what it lacks
                if full.get(k) in (None, {}, "") and v not in (None, {}, ""):
                    full[k] = v
            result = full
        if isinstance(result.get("json"), str):
            result["json"] = json.loads(result["json"])
        if not result.get("json"):
            raise RuntimeError("Datalab's result had no JSON")
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result))
        return result, False
    raise RuntimeError("Datalab did not finish converting the PDF in 20 minutes")


class _Text(HTMLParser):
    """A block's HTML as plain text: paragraphs and list items on lines of their own, table cells apart."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "div"):
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")
        if tag in ("td", "th"):
            self.out.append(" | ")

    def handle_data(self, data):
        self.out.append(data)


def text_of(html: str) -> str:
    p = _Text()
    p.feed(re.sub(r"<content-ref[^>]*>(</content-ref>)?", "", html or ""))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", "".join(p.out))).strip()


def _page_of(block_id: str, default: int) -> int:
    m = re.match(r"/page/(\d+)/", block_id or "")
    return int(m.group(1)) + 1 if m else default


def pages_and_heads(doc: dict) -> tuple[list[str], list[dict], str]:
    """Each page's text (headings as `# ...`, pictures as `[picture: caption]`), the headings ({title, level, page}),
    and a title (the first top heading)."""
    pages = [c for c in doc.get("children") or [] if c.get("block_type") == "Page"] or [doc]
    texts: list[str] = []
    heads: list[dict] = []

    def walk(b: dict, page: int, out: list[str]) -> None:
        kind = b.get("block_type") or ""
        if kind in SKIP:
            return
        kids = b.get("children") or []
        if kind == "SectionHeader":
            m = re.search(r"<h(\d)", b.get("html") or "")
            title = text_of(b.get("html") or "")
            if title:
                heads.append({"title": title[:140], "level": int(m.group(1)) if m else 2, "page": page})
                out.append("# " + title)
            return
        if kind in ("Picture", "Figure") and not kids:
            out.append("[picture]")
            return
        if kids and (kind not in ("Table", "ListGroup") or not text_of(b.get("html") or "")):
            for k in kids:
                walk(k, page, out)
            return
        t = text_of(b.get("html") or "")
        if t:
            out.append(t)

    for n, page in enumerate(pages, 1):
        out: list[str] = []
        for b in page.get("children") or []:
            walk(b, _page_of(b.get("id", ""), n), out)
        texts.append("\n".join(out))
    top = min((h["level"] for h in heads), default=0)
    title = next((h["title"] for h in heads if h["level"] == top and h["page"] <= 2), "")
    return texts, heads, title
