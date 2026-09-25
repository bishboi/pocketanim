"""Cross-check the device's tier-1 interpreter against the Python one.

A tier-1 artefact is a program, so the device does not decode frames -- it
*computes* them. That means the interpreter is as much a part of the format as
the container is, and a drift in any verb shows up as a scene that plays
subtly differently on the phone than in the author's preview.

dsl/interpret.py is the reference; player/core is what ships. Both expand the
same program and emit the same canonical dump, compared field by field.

The bounds line is skipped: a program has no quantisation box, because its
geometry is computed rather than dequantised. That is the tier-1 advantage
stated as a missing line of output.

Usage:
    python -m tools.crosscheck_interpreter <program.panim> [program2.panim ...]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsl.interpret import load_program
from tools.crosscheck_decoders import compare

CLASSES = Path("player/build/classes")


def kotlin_dump(program: Path, frame: int) -> list[str]:
    out = subprocess.run(
        ["java", "-cp", f"{CLASSES / 'core'}:{CLASSES / 'desktop'}:{CLASSES / 'kotlin-stdlib.jar'}",
         "com.pocketanim.desktop.VerifyKt", str(program), "dump", str(frame)],
        check=True, capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line and line[0].isupper()]


def python_dump(ir, frame: int) -> list[str]:
    import numpy as np

    lines = [
        "H %d %d %d" % (ir.fps, len(ir.records), 1 if ir.cameras is not None else 0)
    ]

    # No atlas lines: the two implementations allocate atlas ids differently on
    # purpose. The reference keeps every transient reveal path it ever built;
    # the device winds them back, because holding them was most of the 98.8 MB
    # that made the eager interpreter unusable on a phone. Geometry is compared
    # per instance below instead, which is what is actually drawn.
    for index, (kind, instances) in enumerate(ir.records):
        lines.append("R %d %d %d" % (index, kind, len(instances)))

    if ir.cameras is not None:
        lines.append("C %d " % frame + " ".join("%.6f" % v for v in ir.cameras[frame]))

    instances = ir.frame(frame)
    lines.append("F %d %d" % (frame, len(instances)))
    for ordinal, inst in enumerate(instances):
        shape = ir.shapes[inst.atlas_id]
        n = len(shape)
        first = shape[0] if n else np.zeros(3)
        last = shape[-1] if n else np.zeros(3)
        mean = shape.mean(axis=0) if n else np.zeros(3)
        lines.append("G %d %d " % (ordinal, n)
                     + " ".join("%.6f" % v for v in (*first, *last, *mean)))
        parts = ["I %d %d %d %d" % (ordinal, inst.slot, n, inst.flags)]
        parts += ["%.6f" % v for v in inst.transform.reshape(-1)]
        parts += [str(v) for v in inst.fill]
        parts += [str(v) for v in inst.stroke]
        parts.append("%.6f" % inst.stroke_width)
        if inst.normal is not None:
            parts += ["%.6f" % v for v in inst.normal]
        lines.append(" ".join(parts))

    return lines


# Where in the timeline to compare. The middle alone let a nested `lag`, a
# fade's travel and a stale panel all through: each lives in a stretch the
# midpoint happened not to land in.
PROBES = (0.2, 0.5, 0.8, 1.0)


def check(program: Path) -> bool:
    ir = load_program(str(program))
    frames = sorted({min(int(len(ir.records) * f), len(ir.records) - 1) for f in PROBES})
    problems = []
    lines = 0
    for frame in frames:
        py = python_dump(ir, frame)
        kt = kotlin_dump(program, frame)
        lines += len(py)
        found = compare(py, kt)
        if found:
            problems.append(f"frame {frame}:")
            problems.extend(found)

    label = f"{program.name} (frames={len(ir.records)} shapes={len(ir.shapes)} " \
            f"camera={ir.cameras is not None} probes={','.join(map(str, frames))})"
    if problems:
        print(f"FAIL {label}")
        for problem in problems[:40]:
            print("  " + problem.replace("\n", "\n  "))
        return False
    print(f"ok   {label}: {lines} lines agree")
    return True


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        print("usage: python -m tools.crosscheck_interpreter <program.panim> ...")
        return 2
    if not (CLASSES / "core").exists():
        print("player not built -- run player/build.sh first")
        return 2

    failures = sum(0 if check(path) else 1 for path in paths)
    if failures:
        print(f"\nFAIL: {failures}/{len(paths)} program(s) disagree")
        return 1
    print(f"\nOK: both interpreters agree on all {len(paths)} program(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
