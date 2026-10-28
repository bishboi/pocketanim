"""The keys and settings from files, so they need not be exported by hand: harness_v3/.env.local, harness_v3/.env,
then harness_v2/app/.env.local (the keys v2 already has). A variable already set in the environment wins, then the
first file that sets it. Lines are `NAME=value` (`export NAME=value`, quotes and `# comments` allowed).

Imported first by server.py and pipeline.py (before anything reads os.environ). Only the files' names are ever
printed, never their values; the files are git-ignored.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / ".env.local", ROOT / ".env", ROOT.parent / "harness_v2" / "app" / ".env.local"]


def _value(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        q = raw[0]
        end = raw.find(q, 1)
        return raw[1:end] if end > 0 else raw[1:]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def load() -> list[str]:
    """Sets what the files give and the environment lacks; the files read."""
    read = []
    for f in FILES:
        if not f.is_file():
            continue
        read.append(str(f.relative_to(ROOT.parent)))
        for line in f.read_text(errors="replace").splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)", line)
            if not m or line.lstrip().startswith("#"):
                continue
            name, value = m.group(1), _value(m.group(2))
            if value and not os.environ.get(name, "").strip():
                os.environ[name] = value
    return read


LOADED = load()
