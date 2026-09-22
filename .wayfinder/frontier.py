"""Show which tickets a session may take.

A markdown tracker cannot draw the frontier in a UI the way a real issue
tracker does, so it gets drawn here instead: open, unblocked, unclaimed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def parse(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    _, front, _ = text.split("---", 2)
    out: dict = {"path": path}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            value = [v.strip() for v in inner.split(",")] if inner else []
        out[key.strip()] = value
    return out


def main() -> int:
    tickets = [parse(p) for p in sorted((ROOT / "tickets").glob("*.md"))]
    closed = {t["id"] for t in tickets if t.get("state") == "closed"}
    show_all = "--all" in sys.argv

    for t in tickets:
        blockers = [b for b in t.get("blocked_by", []) if b not in closed]
        claimed = t.get("assignee") not in (None, "", "null")
        if t.get("state") == "closed":
            status = "closed"
        elif blockers:
            status = "blocked by " + ", ".join(blockers)
        elif claimed:
            status = f"claimed by {t['assignee']}"
        else:
            status = "FRONTIER"
        if show_all or status == "FRONTIER":
            label = str(t.get("labels", "")).replace("wayfinder:", "")
            print(f"  {t['id']:>3}  {label:<10} {status:<22} {t['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
