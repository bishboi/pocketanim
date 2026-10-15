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
      scenes/<name>.json    one scene's manifest (with its chapters: [{number, title, frame}])
      scenes/<name>.panim   the program            (tier 1)
      scenes/<name>.panm    sampled frames         (tier 3 fallback)
      assets.pack           baked geometry: every shape, the compact version 2 container (tools/panm_compact.py),
                            one after another, indexed by id in library.json's "asset_pack" (PANIM_ASSET_PACK=0:
                            assets/<digest>.panm, one file each)
      images/<digest>.webp  raster pictures a program's `image` lines draw, shared: WebP, at most 1024x576
                            (PANIM_IMAGE_HEIGHT, PANIM_IMAGE_QUALITY); the program's lines point at them
      audio/<name>.ogg      narration, fetched on demand (§5.3): Opus, mono, 8 kbit/s
                            (audio/<name>.wav when ffmpeg cannot encode it)

Usage:
    python -m tools.build_library [--out library] [--source dsl/generated]

--source packs another export -- a harness build's dsl/generated -- instead of
the corpus. A scene's narration is `<source>/<name>.narration.wav`, which the
harness exporter writes when the scene narrates itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROGRAMS = Path("dsl/generated")
CONTAINERS = Path("corpus/ir")
ASSETS = PROGRAMS / "assets"
GLYPHS = PROGRAMS / "library.atlas"

ASSET_REF = re.compile(r"\basset=([0-9a-f]+)")
IMAGE_REF = re.compile(r"^image\s+\S+.*?\bsrc=(\S+)", re.M)

# Skia rasterises a path on the CPU once it exceeds kMaxGPUPathRendererVerbs.
# The limit is per *path*, not per frame, and a path here is one atlas shape:
# four points per cubic, plus a move and a close per subpath.
SKIA_GPU_VERB_LIMIT = 16_384


def compress_narration(source: Path, stem: Path) -> Path:
    """The narration as the phone gets it: Opus in Ogg, mono, PANIM_NARRATION_KBPS (8) kbit/s.

    The exporter mixes it as WAV, which is 300 MB for an hour of speech; Opus at 24 kbit/s is about 11 MB, and
    speech at that rate is clear. Android plays Ogg Opus from version 10, the player's minimum, through the same
    MediaExtractor/MediaCodec path it used for the WAV, and the decoder drops Opus's pre-skip, so the voice stays
    on its frames. Without an ffmpeg that has an Opus encoder the WAV is shipped as before.
    """
    # Speech in Opus stays intelligible at 8 kbit/s (its narrowband voice mode): a lecture's voice is the
    # biggest asset, and half of 16 is worth the duller sound. PANIM_NARRATION_KBPS=16 for the clearer one.
    kbps = os.environ.get("PANIM_NARRATION_KBPS", "8")
    target = stem.with_suffix(".ogg")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        for codec in (["-c:a", "libopus", "-application", "voip", "-vbr", "on"],
                      # ffmpeg's own Opus encoder, where it was built without libopus: 48 kHz only.
                      ["-c:a", "opus", "-strict", "-2", "-ar", "48000"]):
            done = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(source), "-ac", "1", *codec,
                                   "-b:a", f"{kbps}k", str(target)], capture_output=True, text=True)
            if done.returncode == 0 and target.exists() and target.stat().st_size > 0:
                return target
        target.unlink(missing_ok=True)
        print(f"narration of {source.name} could not be encoded as Opus; shipping the WAV", file=sys.stderr)
    plain = stem.with_suffix(".wav")
    shutil.copy(source, plain)
    return plain


def phone_picture(source: Path, out_dir: Path) -> tuple[str, int, int]:
    """A picture as the phone gets it: WebP (PANIM_IMAGE_QUALITY, 65), no taller than PANIM_IMAGE_HEIGHT (576) nor
    wider than its 16:9 width (1024), alpha kept. The exporter writes its pictures as plain PNG from their pixels
    -- a 1344x756 photo was 2.6 MB, near its raw size -- and the zip cannot shrink a PNG. Returns (file name,
    width, height). A picture PIL cannot read is copied as it is."""
    from PIL import Image

    height = int(os.environ.get("PANIM_IMAGE_HEIGHT", "576"))
    quality = int(os.environ.get("PANIM_IMAGE_QUALITY", "65"))
    try:
        with Image.open(source) as img:
            img.load()
            mode = "RGBA" if "A" in img.getbands() or img.info.get("transparency") is not None else "RGB"
            picture = img.convert(mode)
    except Exception:  # noqa: BLE001
        shutil.copy(source, out_dir / source.name)
        with Image.open(source) as img:
            return source.name, img.width, img.height
    scale = min(1.0, height / max(picture.height, 1), (height * 16 / 9) / max(picture.width, 1))
    if scale < 1.0:
        picture = picture.resize((max(1, round(picture.width * scale)), max(1, round(picture.height * scale))),
                                 Image.LANCZOS)
    if mode == "RGBA" and picture.getchannel("A").getextrema()[0] == 255:
        picture = picture.convert("RGB")          # an alpha channel with nothing see-through in it
    name = f"{source.stem}.webp"
    picture.save(out_dir / name, "WEBP", quality=quality, method=6)
    return name, picture.width, picture.height


def phone_program(text: str, out_dir: Path, done: dict) -> str:
    """The program with its `image` lines pointing at the phone's pictures (phone_picture), made once each."""

    def swap(found: re.Match) -> str:
        line = found.group(0)
        src = re.search(r"\bsrc=(\S+)", line).group(1)
        if src not in done:
            source = PROGRAMS / "images" / src
            done[src] = phone_picture(source, out_dir) if source.exists() else (src, None, None)
        name, width, height = done[src]
        line = re.sub(r"\bsrc=\S+", f"src={name}", line)
        if width:
            line = re.sub(r"\bpx=\d+,\d+", f"px={width},{height}", line)
        return line

    return re.sub(r"^image\s.*$", swap, text, flags=re.M)


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
        # Pictures are files the scene cannot play without, like its assets: the phone fetches them with the rest.
        entry["assets"] += [f"images/{i}" for i in sorted(set(IMAGE_REF.findall(text)))]
        entry["needs_glyph_atlas"] = uses_glyphs
        entry["frames"] = frame_count(program)
    if container is not None:
        entry.setdefault("tier", 3)
        entry["container"] = f"scenes/{name}.panm"
        entry["container_bytes"] = container.stat().st_size

    # Every byte the device must hold before this scene will play offline.
    payload = entry.get("program_bytes", 0) if program else entry.get("container_bytes", 0)
    for ref in entry.get("assets", []):
        payload += _source_of(ref).stat().st_size
    entry["playable_bytes"] = payload
    return entry


PACKED: Path | None = None     # the library being written: its pictures are the phone's (phone_picture)


def _source_of(ref: str) -> Path:
    """Where a manifest path (assets/<id>.panm, images/<name>) is: a picture in the library being written (made for
    the phone), an asset in the export being packed."""
    if ref.startswith("images/"):
        made = PACKED / ref if PACKED is not None else None
        return made if made is not None and made.exists() else PROGRAMS / "images" / Path(ref).name
    return ASSETS / Path(ref).name


def frame_count(program: Path) -> int | None:
    """How long the scene runs: the number of frames the interpreter expands.

    This used to be summed from the timeline by hand, which had to re-learn
    every verb's argument order -- `spin` ends in its axis, not its duration,
    and a `par` or `lag` header owns the steps that follow it -- and got each
    new one wrong. Expanding the program is exact by construction.
    """
    import os

    from dsl.interpret import load_program

    # The interpreter finds assets under dsl/generated/assets relative to the
    # working directory, so it runs from the export's own root.
    root = PROGRAMS.resolve().parent.parent
    previous = Path.cwd()
    os.chdir(root)
    try:
        return len(load_program(str(program.resolve())).records)
    finally:
        os.chdir(previous)


def main() -> int:
    global PROGRAMS, ASSETS, GLYPHS, CONTAINERS
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="library")
    ap.add_argument("--source", default=None, help="an export's dsl/generated directory (default: the corpus)")
    args = ap.parse_args()
    if args.source:
        PROGRAMS = Path(args.source)
        ASSETS = PROGRAMS / "assets"
        GLYPHS = PROGRAMS / "library.atlas"
        CONTAINERS = PROGRAMS / "containers"

    out = Path(args.out)
    for sub in ("scenes", "assets", "images", "audio"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    global PACKED
    PACKED = out
    pictures: dict = {}

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

        if program:
            # The phone's copy of the program, its pictures made for the phone; the manifest describes that copy.
            packed = out / "scenes" / f"{name}.panim"
            packed.write_text(phone_program(program.read_text(), out / "images", pictures))
            program = packed
        entry = scene_manifest(name, program, container)
        if program:
            wanted_assets.update(entry["assets"])
        if container:
            shutil.copy(container, out / "scenes" / f"{name}.panm")

        # Where each chapter begins, for the player's chapter list and the marks on its seek bar.
        chapters = PROGRAMS / f"{name}.chapters.json"
        if chapters.exists():
            entry["chapters"] = json.loads(chapters.read_text())

        narration = PROGRAMS / f"{name}.narration.wav"
        if narration.exists():
            track = compress_narration(narration, out / "audio" / name)
            entry["audio"] = f"audio/{track.name}"
            entry["audio_bytes"] = track.stat().st_size

        (out / "scenes" / f"{name}.json").write_text(json.dumps(entry, indent=2) + "\n")
        scenes.append(entry)

    # Only the assets something actually references. The exporter leaves behind
    # assets from superseded runs, and shipping those would quietly inflate
    # every device's cache.
    from tools.panm_compact import encode

    compact = os.environ.get("PANIM_COMPACT_ASSETS", "1") != "0"
    asset_records = []
    for asset in sorted(wanted_assets):
        source = _source_of(asset)
        target = out / asset
        if asset.startswith("assets/") and compact:
            # The compact container (version 2): the same shapes in about half the bytes, zipped.
            data = source.read_bytes()
            try:
                small = encode(data)
            except Exception as error:  # noqa: BLE001 -- an asset it cannot read ships as it is
                print(f"{asset}: kept as version 1 ({type(error).__name__}: {error})", file=sys.stderr)
                small = data
            target.write_bytes(small if len(small) < len(data) else data)
        elif source.resolve() != target.resolve():
            shutil.copy(source, target)
        asset_records.append({
            "path": asset,
            "bytes": target.stat().st_size,
            "sha256_16": digest_of(target),
        })

    # All the scenes' shapes in one file (assets.pack) with an index, in the order the programs first use them:
    # zipped file by file, each of hundreds of small shapes was compressed alone; in one stream, shapes that repeat
    # each other (a label's glyph run, a map's coast at another zoom) compress against one another. The phone reads
    # a shape as its slice of the pack (Library.kt).
    pack = None
    if os.environ.get("PANIM_ASSET_PACK", "1") != "0":
        order: list[str] = []
        for entry in scenes:
            program = out / entry["program"] if entry.get("program") else None
            for ident in (ASSET_REF.findall(program.read_text()) if program and program.exists() else []):
                ref = f"assets/{ident}.panm"
                if ref in wanted_assets and ref not in order:
                    order.append(ref)
        order += sorted(a for a in wanted_assets if a.startswith("assets/") and a not in order)
        if order:
            blob, index = bytearray(), {}
            for ref in order:
                data = (out / ref).read_bytes()
                index[Path(ref).stem] = [len(blob), len(data)]
                blob += data
            (out / "assets.pack").write_bytes(bytes(blob))
            for ref in order:
                (out / ref).unlink()
            pack = {"path": "assets.pack", "bytes": len(blob), "sha256_16": digest_of(out / "assets.pack"),
                    "index": index}
            asset_records = [r for r in asset_records if not r["path"].startswith("assets/")]
            asset_records.append({k: pack[k] for k in ("path", "bytes", "sha256_16")})
            for entry in scenes:
                refs = entry.get("assets", [])
                if any(r.startswith("assets/") for r in refs):
                    entry["assets"] = ["assets.pack"] + [r for r in refs if not r.startswith("assets/")]

    # What each scene needs before it plays, counted again from the files as packed (compact assets, the phone's
    # pictures), and its manifest written again with it.
    for entry in scenes:
        payload = entry.get("program_bytes", 0) if entry.get("program") else entry.get("container_bytes", 0)
        payload += sum((out / ref).stat().st_size for ref in entry.get("assets", []) if (out / ref).exists())
        entry["playable_bytes"] = payload
        (out / "scenes" / f"{entry['name']}.json").write_text(json.dumps(entry, indent=2) + "\n")

    # Being close to the cliff matters as much as crossing it: a path just
    # under the limit crosses it with one more zoom level of detail, and the
    # symptom is a scene that silently rasterises on the CPU on every device.
    near_limit = []
    for asset in sorted(a for a in wanted_assets if a.startswith("assets/")):
        for index, verbs in oversized_shapes(_source_of(asset)):
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
    if pack is not None:
        manifest["asset_pack"] = pack
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
