"""Paths, hashing and file helpers shared by every stage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

FORGE = Path(__file__).resolve().parents[1]          # harness/forge
REPO = FORGE.parents[1]                               # repository root
LECTURE = REPO / "harness" / "lecture"               # the pocket_lecture engine
STYLES = FORGE / "styles"
TEMPLATES = FORGE / "templates"
REGIONS = FORGE / "regions"
OPS_FILE = FORGE / "forge" / "ops.json"
REGISTRY_FILE = FORGE / "registry.json"
JOBS = Path(os.environ.get("FORGE_JOBS") or (FORGE / "jobs"))
CACHE = Path(os.environ.get("FORGE_CACHE") or (FORGE / "cache"))

for path in (str(REPO), str(LECTURE)):
    if path not in sys.path:
        sys.path.insert(0, path)


def read_yaml(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    return yaml.safe_load(path.read_text(encoding="utf-8")) or ({} if default is None else default)


def write_yaml(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(*parts) -> str:
    """A content hash of anything JSON can say. The cache key of every artefact."""
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, (bytes, bytearray)):
            h.update(part)
        elif isinstance(part, Path):
            h.update(part.read_bytes() if part.is_file() else str(part).encode())
        else:
            h.update(json.dumps(part, sort_keys=True, ensure_ascii=False, default=str).encode())
        h.update(b"\x00")
    return h.hexdigest()[:16]


def deep_merge(base: dict, over: dict) -> dict:
    """`over` wins, recursively for mappings. Lists are replaced, not merged."""
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping abbreviations and decimals whole."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text)
    out = []
    for part in parts:
        if out and re.search(r"\b(?:c|ca|Mr|Mrs|Dr|St|Gen|Col|Lt|Capt|approx|e\.g|i\.e|vs|No)\.$", out[-1]):
            out[-1] += " " + part
        else:
            out.append(part.strip())
    return [s for s in out if s]


NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w])")


def numbers_in(text: str) -> set[str]:
    """The numbers a text states, normalised: 3,000 and 3000 are one number."""
    return {m.group(1).replace(",", "").rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1).replace(",", "")
            for m in NUMBER_RE.finditer(text or "")}
