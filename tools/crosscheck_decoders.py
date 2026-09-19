"""Cross-check the Java and Python IR decoders against the same file.

The format is only portable if two independent implementations agree. Both
decoders emit the same canonical dump -- header, bounds, every atlas shape,
every record's instance count, the camera row, and every instance of a probed
frame -- and this compares them field by field, so a layout or endianness
change fails loudly rather than silently producing a differently-wrong picture
on device.

Floats are compared by tolerance, not equality, on purpose: the Java decoder
dequantises the atlas in float32 because that is what the device will do, while
Python uses float64. Everything that comes off the wire as an integer, a
float16 or a float32 must match exactly, and does.

Worth keeping in CI: the Android renderer will be the Java decoder's logic in
Kotlin, so a disagreement here is a disagreement on the phone.

Usage:
    python -m tools.crosscheck_decoders <scene.panm> [scene2.panm ...]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter.decode import load

CLASSES = Path("/tmp/panim-classes")
SOURCE = Path("client/PanimDecoder.java")

# Atlas points are dequantised at different precision on each side by design,
# so they get a looser bound -- still far below the quantisation step itself.
TOLERANCES = {"A": 1e-3}
DEFAULT_TOLERANCE = 1e-5


def compile_java() -> None:
    CLASSES.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["javac", str(SOURCE), "-d", str(CLASSES)], check=True, capture_output=True
    )


def java_dump(path: Path, frame: int) -> list[str]:
    out = subprocess.run(
        ["java", "-cp", str(CLASSES), "PanimDecoder", str(path), str(frame), "--dump"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line and line[0].isupper()]


def python_dump(path: Path, frame: int) -> list[str]:
    ir = load(path.read_bytes())
    lines = [
        "H %d %d %d %d" % (ir.fps, len(ir.records), len(ir.shapes),
                           1 if ir.cameras is not None else 0)
    ]

    import numpy as np

    lines.append("B " + " ".join("%.6f" % v for v in (*ir.lo, *ir.hi)))

    for index, shape in enumerate(ir.shapes):
        n = len(shape)
        first = shape[0] if n else np.zeros(3)
        last = shape[-1] if n else np.zeros(3)
        mean = shape.mean(axis=0) if n else np.zeros(3)
        lines.append("A %d %d " % (index, n)
                     + " ".join("%.6f" % v for v in (*first, *last, *mean)))

    for index, (kind, instances) in enumerate(ir.records):
        lines.append("R %d %d %d" % (index, kind, len(instances)))

    if ir.cameras is not None:
        lines.append("C %d " % frame + " ".join("%.6f" % v for v in ir.cameras[frame]))

    instances = ir.frame(frame)
    lines.append("F %d %d" % (frame, len(instances)))
    for ordinal, inst in enumerate(instances):
        parts = ["I %d %d %d %d" % (ordinal, inst.slot, inst.atlas_id, inst.flags)]
        parts += ["%.6f" % v for v in inst.transform.reshape(-1)]
        parts += [str(v) for v in inst.fill]
        parts += [str(v) for v in inst.stroke]
        parts.append("%.6f" % inst.stroke_width)
        if inst.normal is not None:
            parts += ["%.6f" % v for v in inst.normal]
        lines.append(" ".join(parts))

    return lines


def compare(py: list[str], java: list[str]) -> list[str]:
    """Return a human-readable list of disagreements, empty when they agree."""
    problems: list[str] = []
    if len(py) != len(java):
        problems.append(f"line count: python={len(py)} java={len(java)}")

    for index, (left, right) in enumerate(zip(py, java)):
        left_fields, right_fields = left.split(), right.split()
        if left_fields[0] != right_fields[0] or len(left_fields) != len(right_fields):
            problems.append(f"line {index}: shape differs\n  py  {left}\n  jav {right}")
            continue

        tolerance = TOLERANCES.get(left_fields[0], DEFAULT_TOLERANCE)
        for column, (a, b) in enumerate(zip(left_fields, right_fields)):
            if a == b:
                continue
            try:
                if abs(float(a) - float(b)) <= tolerance:
                    continue
            except ValueError:
                pass
            problems.append(
                f"line {index} col {column}: {a} != {b}\n  py  {left}\n  jav {right}"
            )
            break

        if len(problems) > 20:
            problems.append("... further differences suppressed")
            break

    return problems


def check(path: Path) -> bool:
    ir = load(path.read_bytes())
    # Probe mid-timeline: far enough in that keyframe replay, not just the
    # opening snapshot, has to be right.
    frame = len(ir.records) // 2
    py, java = python_dump(path, frame), java_dump(path, frame)
    problems = compare(py, java)

    label = f"{path.name} (records={len(ir.records)} shapes={len(ir.shapes)} " \
            f"camera={ir.cameras is not None} frame={frame})"
    if problems:
        print(f"FAIL {label}")
        for problem in problems:
            print("  " + problem.replace("\n", "\n  "))
        return False
    print(f"ok   {label}: {len(py)} lines agree")
    return True


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        print(__doc__.strip().splitlines()[-1])
        return 2

    compile_java()
    failures = sum(0 if check(path) else 1 for path in paths)

    if failures:
        print(f"\nFAIL: {failures}/{len(paths)} file(s) disagree")
        return 1
    print(f"\nOK: Java and Python decoders agree on all {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
