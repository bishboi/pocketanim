"""The QA loop's whole test set judged at once: every chapter script in a folder (engine/examples/qa by default) built
and checked by chapter_qa.py, a few at a time, and one table of what passed and what failed.

    .venv/bin/python harness_v2/engine/tools/qa_suite.py [<folder or script.json>...] [--out DIR] [--jobs 3]
        [--voice fake|real] [--only NAME]

Writes <out>/summary.json ({"passed", "failed", "chapters": [{"name", "ok", "fail", "warn", "dir"}]}) and prints the
table; exits 1 when any chapter fails. Each chapter's own report, frames and sheet are in <out>/<name>/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ENGINE = TOOLS.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--out", default=None)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--voice", choices=("fake", "real"), default="fake")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    paths = [Path(p) for p in args.paths] or [ENGINE / "examples" / "qa"]
    scripts = sorted(f for p in paths for f in ([p] if p.is_file() else p.glob("*.json")))
    if args.only:
        scripts = [s for s in scripts if args.only in s.stem]
    out = Path(args.out or "qa-out").resolve()
    out.mkdir(parents=True, exist_ok=True)

    def one(script: Path) -> dict:
        folder = out / script.stem
        r = subprocess.run([sys.executable, str(TOOLS / "chapter_qa.py"), str(script.resolve()), str(folder),
                            "--voice", args.voice], capture_output=True, text=True)
        try:
            report = json.loads((folder / "report.json").read_text())
        except (OSError, ValueError):
            report = {"ok": False, "fail": [f"chapter_qa crashed: {r.stderr.strip()[-400:]}"], "warn": []}
        return {"name": script.stem, "ok": bool(report.get("ok")), "fail": report.get("fail") or [],
                "warn": report.get("warn") or [], "dir": str(folder)}

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(one, scripts))
    summary = {"passed": sum(r["ok"] for r in rows), "failed": sum(not r["ok"] for r in rows), "chapters": rows}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    for r in rows:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']}  ({len(r['fail'])} fail, {len(r['warn'])} warn)")
        for f in r["fail"][:6]:
            print(f"      - {f}")
    print(json.dumps({"passed": summary["passed"], "failed": summary["failed"], "out": str(out)}))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
