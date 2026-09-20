"""Package exported scenes into a library the device can sync against.

Caching all IR (§5.3) only works if the device can find out what exists and
what it is already holding. That is this: one manifest for the library, one per
scene, and content-addressed assets shared across every scene that uses them.

The layout is deliberately boring -- a directory of files with hashes in the
names -- because the sync algorithm should be "fetch the paths I do not have",
not a protocol.

    library/
      library.json          every scene, its tier, its bytes, its asset ids
      library.atlas         the shared glyph atlas (§3.5)
      scenes/<name>.json    one scene's manifest
      scenes/<name>.panim   the program            (tier 1)
      scenes/<name>.panm    sampled frames         (tier 3 fallback)
      assets/<digest>.panm  baked geometry, shared
      audio/<name>.m4a      narration, fetched on demand (§5.3)

Usage:
    python -m tools.build_library [--out library]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROGRAMS = Path("dsl/generated")
CONTAINERS = Path("corpus/ir")
ASSETS = PROGRAMS / "assets"
GLYPHS = PROGRAMS / "library.atlas"

ASSET_REF = re.compile(r"\basset=([0-9a-f]+)")

# Skia rasterises a path on the CPU once it exceeds kMaxGPUPathRendererVerbs.
# The limit is per *path*, not per frame, and a path here is one atlas shape:
# four points per cubic, plus a move and a close per subpath.
SKIA_GPU_VERB_LIMIT = 16_384


def verb_count(points_len: int) -> int:
    """Path verbs for a baked shape, as the renderer will emit them.

    One cubic per four points, plus roughly one move and one close per subpath.
    Subpath count is not known without walking the geometry, so this is the
    cubic count -- a lower bound, which is the conservative direction for a
    warning about being *under* a limit.
    """
    return points_len // 4


def oversized_shapes(asset: Path) -> list[tuple[int, int]]:
    """Shapes in this asset at or near the software-fallback cliff."""
    from exporter.decode import load

    ir = load(asset.read_bytes())
    out = []
    for index, shape in enumerate(ir.shapes):
        verbs = verb_count(len(shape))
        if verbs > SKIA_GPU_VERB_LIMIT // 2:
            out.append((index, verbs))
    return out


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def certified_tier(name: str) -> tuple[int, list[str]] | None:
    """The exporter's verdict, or None if it never rendered one.

    A program file on disk is not evidence that the program is faithful: a
    stale one from before a blocker was discovered shipped a scene missing 2.5
    seconds and 15% of its pixels. The exporter writes this sidecar precisely
    so presence cannot be mistaken for correctness.
    """
    sidecar = PROGRAMS / f"{name}.tier.json"
    if not sidecar.exists():
        return None
    data = json.loads(sidecar.read_text())
    return data["tier"], data.get("blockers", [])


def scene_manifest(name: str, program: Path | None, container: Path | None) -> dict:
    """Describe one scene, including everything it needs before it can play."""
    entry: dict = {"name": name}

    if program is not None:
        text = program.read_text()
        # The asset ids a program references are the ids in its declarations --
        # recovered by reading it rather than tracked separately, so a manifest
        # cannot drift from the program it describes.
        assets = sorted(set(ASSET_REF.findall(text)))
        uses_glyphs = any(line.startswith("text ") for line in text.splitlines())
        entry["tier"] = 1
        entry["program"] = f"scenes/{name}.panim"
        entry["program_bytes"] = len(text.encode())
        entry["assets"] = [f"assets/{a}.panm" for a in assets]
        entry["needs_glyph_atlas"] = uses_glyphs
        entry["frames"] = frame_count(program)
    if container is not None:
        entry.setdefault("tier", 3)
        entry["container"] = f"scenes/{name}.panm"
        entry["container_bytes"] = container.stat().st_size

    # Every byte the device must hold before this scene will play offline.
    payload = entry.get("program_bytes", 0) if program else entry.get("container_bytes", 0)
    for ref in entry.get("assets", []):
        payload += (ASSETS / Path(ref).name).stat().st_size
    entry["playable_bytes"] = payload
    return entry


def frame_count(program: Path) -> int | None:
    """How long the scene runs, from the program rather than by expanding it."""
    from dsl.interpret import parse

    scene = parse(program.read_text())
    fps = scene["fps"]
    total = 0
    opened = False
    for step in scene["timeline"]:
        if step[0] == "show":
            continue
        if not opened:
            opened = True
            total += 1  # Manim's opening frame at t=0
        seconds = step[-1] if step[0] in ("move", "spin", "wait") else None
        if seconds is None:
            seconds = next((v for v in reversed(step) if isinstance(v, float)), 0.0)
        total += int(seconds * fps)
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="library")
    args = ap.parse_args()

    out = Path(args.out)
    for sub in ("scenes", "assets", "audio"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    names = sorted({p.stem for p in PROGRAMS.glob("*.panim")} |
                   {p.stem for p in CONTAINERS.glob("*.panm")})

    scenes = []
    wanted_assets: set[str] = set()
    uncertified: list[str] = []
    skipped: list[str] = []
    for name in names:
        program = PROGRAMS / f"{name}.panim"
        container = CONTAINERS / f"{name}.panm"
        program = program if program.exists() else None
        container = container if container.exists() else None

        verdict = certified_tier(name)
        if verdict is None and program is not None:
            uncertified.append(name)
            program = None
        elif verdict is not None and verdict[0] != 1:
            # Blocked scenes fall back to sampled frames, whatever is on disk.
            program = None

        if program is None and container is None:
            skipped.append(name)
            continue

        entry = scene_manifest(name, program, container)
        if program:
            shutil.copy(program, out / "scenes" / f"{name}.panim")
            wanted_assets.update(Path(a).name for a in entry["assets"])
        if container:
            shutil.copy(container, out / "scenes" / f"{name}.panm")

        (out / "scenes" / f"{name}.json").write_text(json.dumps(entry, indent=2) + "\n")
        scenes.append(entry)

    # Only the assets something actually references. The exporter leaves behind
    # assets from superseded runs, and shipping those would quietly inflate
    # every device's cache.
    asset_records = []
    for asset in sorted(wanted_assets):
        source = ASSETS / asset
        shutil.copy(source, out / "assets" / asset)
        asset_records.append({
            "path": f"assets/{asset}",
            "bytes": source.stat().st_size,
            "sha256_16": digest_of(source),
        })

    # Being close to the cliff matters as much as crossing it: a path just
    # under the limit crosses it with one more zoom level of detail, and the
    # symptom is a scene that silently rasterises on the CPU on every device.
    near_limit = []
    for asset in sorted(wanted_assets):
        for index, verbs in oversized_shapes(ASSETS / asset):
            near_limit.append((asset, index, verbs))

    glyphs = None
    if GLYPHS.exists():
        shutil.copy(GLYPHS, out / "library.atlas")
        glyphs = {
            "path": "library.atlas",
            "bytes": GLYPHS.stat().st_size,
            "sha256_16": digest_of(GLYPHS),
        }

    manifest = {
        "version": 1,
        "glyph_atlas": glyphs,
        "assets": asset_records,
        "scenes": scenes,
    }
    (out / "library.json").write_text(json.dumps(manifest, indent=2) + "\n")

    shared = sum(a["bytes"] for a in asset_records)
    programs = sum(s.get("program_bytes", 0) for s in scenes)
    containers = sum(s.get("container_bytes", 0) for s in scenes)

    print(f"scenes            {len(scenes)}")
    print(f"tier 1            {sum(1 for s in scenes if s['tier'] == 1)}")
    print(f"programs          {programs:,} B")
    print(f"shared assets     {shared:,} B across {len(asset_records)} files")
    print(f"glyph atlas       {glyphs['bytes']:,} B" if glyphs else "glyph atlas       absent")
    print(f"tier-3 fallbacks  {containers:,} B")
    print(f"library total     {programs + shared + (glyphs['bytes'] if glyphs else 0):,} B"
          f"  (without tier-3 fallbacks)")

    if near_limit:
        print()
        for asset, index, verbs in sorted(near_limit, key=lambda r: -r[2]):
            over = "OVER" if verbs > SKIA_GPU_VERB_LIMIT else "at"
            share = verbs / SKIA_GPU_VERB_LIMIT
            print(f"NOTE: {asset} shape {index} is {verbs:,} verbs "
                  f"({share:.0%} of Skia's GPU limit, {over} the cliff) -- "
                  f"a path past {SKIA_GPU_VERB_LIMIT:,} rasterises on the CPU")

    if uncertified:
        print(f"\nWARNING: no exporter verdict for {', '.join(uncertified)} -- "
              f"shipped as tier 3. Run: python -m dsl.export_dsl <scene> <Class> --write")
    if skipped:
        print(f"WARNING: nothing to ship for {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
