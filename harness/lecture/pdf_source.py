"""A lecture PDF -> Markdown text and its figures, ready for a lecture script.

With DATALAB_API_KEY set, the PDF goes to Datalab's conversion API
(POST /api/v1/convert, then poll request_check_url), which returns clean
Markdown with the figures cut out as images. Without a key, pypdf extracts
the text and the embedded images page by page: rougher, but offline.

Either way the output folder holds:

    document.md     the text; each figure appears in it as [FIGURE fig3: caption]
    figures/        the images
    manifest.json   {source, pages, figures: [{id, file, caption, page}], markdown}

Results are cached by the PDF's content hash, so a second upload is instant.

    python harness/lecture/pdf_source.py lecture.pdf out_dir    # prints the manifest as JSON
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path

HOST = os.environ.get("DATALAB_HOST", "https://www.datalab.to").rstrip("/")
FIGURE_MARK = re.compile(r"\[FIGURE (fig\d+): ([^\]]*)\]")
CAPTION = re.compile(r"^\s*[*_]*\s*(fig(?:ure)?\.?\s*\d+[\w.\-]*.*?)[*_]*\s*$", re.I)


# ════════════════════════════════════════════════════════════════════════
#  Datalab
# ════════════════════════════════════════════════════════════════════════

def _multipart(fields: dict, file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: application/pdf\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _request(url: str, key: str, data: bytes | None = None, content_type: str | None = None) -> dict:
    headers = {"X-Api-Key": key, "User-Agent": "pocketanim-lecture/0.4"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode())


def datalab_convert(pdf: Path, key: str, mode: str = "balanced", timeout: float = 900) -> dict:
    """Datalab's result: {markdown, images: {name: base64}, page_count, ...}. Raises on failure."""
    body, content_type = _multipart({"output_format": "markdown", "mode": mode, "paginate": "False",
                                     "disable_image_extraction": "False", "disable_image_captions": "False"},
                                    "file", pdf.name, pdf.read_bytes())
    started = _request(f"{HOST}/api/v1/convert", key, body, content_type)
    if not started.get("success") or not started.get("request_check_url"):
        raise RuntimeError(f"Datalab refused the document: {started.get('error') or started}")
    check = started["request_check_url"]
    check = check if check.startswith("http") else f"{HOST}/{check.lstrip('/')}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _request(check, key)
        if result.get("status") == "complete":
            if not result.get("success", True):
                raise RuntimeError(f"Datalab could not convert the document: {result.get('error')}")
            return result
        if result.get("status") not in (None, "processing", "queued") and not result.get("success", True):
            raise RuntimeError(f"Datalab: {result.get('error') or result.get('status')}")
        time.sleep(2)
    raise TimeoutError("Datalab did not finish converting the document in time")


def _from_datalab(result: dict, out: Path) -> tuple[str, list[dict], int]:
    figures_dir = out / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    images = result.get("images") or {}
    saved = {}
    for name, data in images.items():
        target = figures_dir / Path(name).name
        target.write_bytes(base64.b64decode(data))
        saved[name] = target
    lines = (result.get("markdown") or "").splitlines()
    figures: list[dict] = []
    text: list[str] = []
    for index, line in enumerate(lines):
        found = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if not found:
            text.append(line)
            continue
        for alt, ref in found:
            file = saved.get(ref) or saved.get(Path(ref).name) or next(
                (p for n, p in saved.items() if Path(n).name == Path(ref).name), None)
            if file is None:
                continue
            caption = _caption_near(lines, index) or alt.strip()
            page = re.search(r"_page_(\d+)_", ref)
            fig = {"id": f"fig{len(figures) + 1}", "file": str(file), "caption": caption[:160],
                   "page": int(page.group(1)) + 1 if page else None}
            figures.append(fig)
            text.append(f"[FIGURE {fig['id']}: {fig['caption']}]")
        rest = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", line).strip()
        if rest:
            text.append(rest)
    return "\n".join(text), figures, int(result.get("page_count") or 0)


def _caption_near(lines: list[str], index: int) -> str:
    """A "Figure 3: ..." line just below (or above) an image."""
    for step in (1, 2, -1):
        j = index + step
        if 0 <= j < len(lines) and CAPTION.match(lines[j]):
            return CAPTION.match(lines[j]).group(1).strip()
    return ""


# ════════════════════════════════════════════════════════════════════════
#  pypdf, offline
# ════════════════════════════════════════════════════════════════════════

def _from_pypdf(pdf: Path, out: Path) -> tuple[str, list[dict], int]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    figures_dir = out / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    text, figures = [], []
    seen: set[str] = set()      # writers often list one image in every page's resources
    for number, page in enumerate(reader.pages, 1):
        body = page.extract_text() or ""
        captions = [m.group(1).strip() for m in map(CAPTION.match, body.splitlines()) if m]
        text.append(f"## Page {number}\n\n{body.strip()}")
        try:
            images = list(page.images)
        except Exception:  # noqa: BLE001 -- an image pypdf cannot decode is skipped, not fatal
            images = []
        for index, image in enumerate(images):
            try:
                picture = image.image
            except Exception:  # noqa: BLE001
                continue
            if picture is None or picture.width < 120 or picture.height < 80:
                continue          # rules, bullets and logos, not figures
            fingerprint = hashlib.md5(picture.tobytes()).hexdigest()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            fig_id = f"fig{len(figures) + 1}"
            target = figures_dir / f"{fig_id}.png"
            picture.convert("RGB").save(target)
            caption = captions[index] if index < len(captions) else f"Figure on page {number}"
            figures.append({"id": fig_id, "file": str(target), "caption": caption[:160], "page": number})
            text.append(f"[FIGURE {fig_id}: {caption[:160]}]")
    return "\n\n".join(text), figures, len(reader.pages)


# ════════════════════════════════════════════════════════════════════════

CACHE = Path(os.environ.get("PANIM_PDF_CACHE") or (Path(__file__).resolve().parent / ".cache" / "pdf"))


def convert(pdf: str | Path, out: str | Path) -> dict:
    """Convert once per PDF content: the work lives in CACHE/<digest>, `out` gets a copy of the manifest.

    The editor and a Forge job given the same PDF share one conversion (and
    one Datalab request).
    """
    pdf, out = Path(pdf).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    work = CACHE / digest
    cached_path = work / "manifest.json"
    if cached_path.exists():
        cached = json.loads(cached_path.read_text(encoding="utf-8"))
        # A conversion without a key is redone once a key is set: Datalab reads PDFs better.
        if not (cached.get("source") == "pypdf" and os.environ.get("DATALAB_API_KEY")):
            (out / "manifest.json").write_text(json.dumps(cached, indent=1, ensure_ascii=False), encoding="utf-8")
            return cached
    manifest = _convert(pdf, work, digest)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


def _convert(pdf: Path, out: Path, digest: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    key = os.environ.get("DATALAB_API_KEY", "").strip()
    note = None
    if key:
        try:
            markdown, figures, pages = _from_datalab(datalab_convert(pdf, key), out)
            source = "datalab"
        except Exception as error:  # noqa: BLE001 -- say so, and still give the user the text
            note = f"Datalab failed ({error}); used the offline reader instead"
            markdown, figures, pages = _from_pypdf(pdf, out)
            source = "pypdf"
    else:
        markdown, figures, pages = _from_pypdf(pdf, out)
        source = "pypdf"
        note = "No DATALAB_API_KEY: text and images read offline with pypdf (set the key for cleaner figures)"
    (out / "document.md").write_text(markdown, encoding="utf-8")
    manifest = {"digest": digest, "source": source, "pages": pages, "figures": figures,
                "markdown": str(out / "document.md"), "words": len(markdown.split()), "note": note}
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    try:
        print(json.dumps(convert(sys.argv[1], sys.argv[2]), ensure_ascii=False))
    except Exception as error:  # noqa: BLE001 -- the app shows this line
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        raise SystemExit(1)
