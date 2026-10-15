"""Where a lecture's bytes go: each phone library's size by kind of asset, and how far each kind would shrink.

For every lecture given (a build's folder, its library/ folder, or a saved library.zip), the files are sorted into
kinds and measured:

    narration     audio/*.ogg|.wav           the voice track (streamed beside the zip)
    images        images/*                   photos, figures, drawings the program's `image` lines draw
    geometry      assets/*.panm              baked shapes (maps, glyph runs, drawings, clips), split further into
                                               points (x, y), points (z: always 0 in a 2D lecture), per-frame
                                               instances (transform, colours, width) and headers
    program       scenes/*.panim             the program text, split by verb (geom, image, fade, xform, clip, ...)
    glyph atlas   library.atlas              the shared glyph shapes
    sampled       scenes/*.panm              a tier-3 fallback, when a scene has one
    manifests     *.json                     library.json and per-scene manifests

Each kind is reported raw and deflated (what library.zip stores), and with what an obvious change would save:
images re-encoded as WebP (quality 80, and at most 1280 px wide), geometry without z and with deflate, the program
deflated. A table per lecture, then one for all of them together.

Usage:
    python -m tools.panim_sizes <build dir | library dir | library.zip> ...
    python -m tools.panim_sizes --latest 12 [--match "early societies"]   # the newest builds in the temp folder
    ... [--json sizes.json] [--csv sizes.csv]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import struct
import sys
import tempfile
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path

KINDS = ("narration", "images", "geometry", "program", "glyph atlas", "sampled", "manifests", "other")
HEADER = "<4sHHHII6f"


def _deflated(data: bytes) -> int:
    return len(zlib.compress(data, 6))


class Library:
    """A lecture's phone library, from a folder or a zip: its files as (relative path, bytes)."""

    def __init__(self, source: Path):
        self.source = source
        self.files: dict[str, bytes] = {}
        if source.is_file() and source.suffix == ".zip":
            with zipfile.ZipFile(source) as z:
                for name in z.namelist():
                    if not name.endswith("/"):
                        self.files[name.split("/", 1)[1] if name.startswith("library/") else name] = z.read(name)
            audio = source.parent / "audio"
            for f in audio.glob("*") if audio.is_dir() else []:
                self.files[f"audio/{f.name}"] = f.read_bytes()
            return
        if (source / "library" / "library.json").is_file():
            root = source / "library"
        elif (source / "dsl" / "generated").is_dir():
            # A build not packed for the phone yet (packing happens on Save): its export, read as the library
            # would hold it -- programs as scenes, the narration as audio.
            gen = source / "dsl" / "generated"
            for f in gen.glob("*.panim"):
                self.files[f"scenes/{f.name}"] = f.read_bytes()
            for f in gen.glob("*.narration.*"):
                self.files[f"audio/{f.name}"] = f.read_bytes()
            for folder in ("assets", "images"):
                for f in (gen / folder).glob("*") if (gen / folder).is_dir() else []:
                    if f.is_file():
                        self.files[f"{folder}/{f.name}"] = f.read_bytes()
            if (gen / "library.atlas").is_file():
                self.files["library.atlas"] = (gen / "library.atlas").read_bytes()
            for f in source.glob("*.py"):
                self.files[f"source/{f.name}"] = f.read_bytes()
            return
        else:
            root = source
        for f in root.rglob("*"):
            if f.is_file() and not f.name.endswith(".zip"):
                self.files[str(f.relative_to(root)).replace("\\", "/")] = f.read_bytes()

    @property
    def title(self) -> str:
        for rel, data in self.files.items():
            if rel.startswith("source/"):
                found = re.search(r'^"""(.+?):', data.decode("utf-8", "ignore"))
                if found:
                    return found.group(1).strip()
        for rel, data in self.files.items():
            if rel.startswith("scenes/") and rel.endswith(".json"):
                try:
                    meta = json.loads(data)
                except ValueError:
                    continue
                chapters = meta.get("chapters") or []
                if meta.get("title"):
                    return str(meta["title"])
                if chapters:
                    return " / ".join(str(c.get("title", "")) for c in chapters[:2])
        return self.source.name

    def text(self) -> str:
        return " ".join(d.decode("utf-8", "ignore") for r, d in self.files.items()
                        if r.endswith((".json", ".panim", ".py")))


def kind_of(rel: str) -> str:
    if rel.startswith("source/"):
        return "skip"
    if rel.startswith("audio/"):
        return "narration"
    if rel.startswith("images/"):
        return "images"
    if rel.startswith("assets/") and rel.endswith(".panm"):
        return "geometry"
    if rel.endswith(".panim"):
        return "program"
    if rel.endswith(".atlas"):
        return "glyph atlas"
    if rel.startswith("scenes/") and rel.endswith(".panm"):
        return "sampled"
    if rel.endswith(".json"):
        return "manifests"
    return "other"


def _compact_parts(blob: bytes, offset: int, flags: int, n_records: int, n_atlas: int, out: dict) -> dict:
    """geometry_parts for the compact container (tools/panm_compact.py): its points are varints, x/y (and z when
    the scene is not flat) interleaved, so their bytes are counted together under "points xy" (or "points z" for
    the share of a 3D scene's z)."""
    axes = 2 if flags & 2 else 3

    def varint(at: int) -> int:
        while blob[at] & 0x80:
            at += 1
        return at + 1

    def count_at(at: int) -> tuple[int, int]:
        value = shift = 0
        while True:
            byte = blob[at]
            at += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value, at
            shift += 7

    for _ in range(n_atlas):
        count, start = count_at(offset)
        out["headers"] += start - offset
        at = start
        for _ in range(count * axes):
            at = varint(at)
        spent = at - start
        out["points xy"] += spent * 2 // axes if axes == 3 else spent
        out["points z"] += spent - spent * 2 // axes if axes == 3 else 0
        out["points"] += count
        offset = at
    out["shapes"] = n_atlas
    out["frames"] = n_records
    out["instances"] = max(len(blob) - offset, 0)
    return out


def geometry_parts(blob: bytes) -> dict:
    """A baked asset's bytes by part: x/y points, z points, frame instances, headers (the container's layout,
    exporter/decode.py)."""
    out = {"points xy": 0, "points z": 0, "instances": 0, "headers": 0, "points": 0, "shapes": 0, "frames": 0}
    try:
        size = struct.calcsize(HEADER)
        _magic, version, flags, _fps, n_records, n_atlas, *_ = struct.unpack(HEADER, blob[:size])
        offset = size
        out["headers"] += size
        if flags & 1:
            offset += n_records * 4 * 17
        if version == 2:
            return _compact_parts(blob, offset, flags, n_records, n_atlas, out)
        for _ in range(n_atlas):
            (count,) = struct.unpack_from("<I", blob, offset)
            offset += 4 + count * 6
            out["headers"] += 4
            out["points xy"] += count * 4
            out["points z"] += count * 2
            out["points"] += count
        out["shapes"] = n_atlas
        out["frames"] = n_records
        records_bytes = len(blob) - offset
        out["instances"] = max(records_bytes, 0)
    except (struct.error, ValueError):
        out["headers"] = len(blob)
    return out


def audio_seconds(name: str, data: bytes) -> float | None:
    """How long a narration file plays: an Ogg (Opus/Vorbis) stream from its last page's granule position, a WAV
    from its header; None for other kinds."""
    try:
        if data[:4] == b"OggS":
            last = data.rfind(b"OggS")
            granule = struct.unpack_from("<q", data, last + 6)[0]
            head = data[:200]
            rate = 48000 if b"OpusHead" in head else struct.unpack_from("<I", data, head.find(b"vorbis") + 11)[0]
            return granule / rate if granule > 0 else None
        if data[:4] == b"RIFF":
            import wave

            with wave.open(io.BytesIO(data)) as w:
                return w.getnframes() / float(w.getframerate())
    except Exception:  # noqa: BLE001 -- a file it cannot read: no length
        return None
    return None


def clock(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else \
        f"{seconds // 60}:{seconds % 60:02d}"


def program_parts(text: str) -> dict:
    out: dict[str, int] = defaultdict(int)
    for line in text.splitlines(keepends=True):
        word = line.strip().split(" ", 1)[0] if line.strip() else "(blank)"
        out[word if re.fullmatch(r"[a-z_]+", word or "") else "(other)"] += len(line.encode())
    return dict(out)


def image_saving(data: bytes) -> tuple[int, int, str]:
    """(as WebP q80, as WebP q80 at most 1280 px wide, pixel size) of a picture; its own size when PIL cannot."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img.load()
            dims = f"{img.width}x{img.height}"
            mode = "RGBA" if "A" in img.getbands() else "RGB"
            a = io.BytesIO()
            img.convert(mode).save(a, "WEBP", quality=80, method=4)
            small = img.convert(mode)
            if small.width > 1280:
                small = small.resize((1280, round(small.height * 1280 / small.width)))
            b = io.BytesIO()
            small.save(b, "WEBP", quality=80, method=4)
            return len(a.getvalue()), len(b.getvalue()), dims
    except Exception:  # noqa: BLE001 -- not a picture PIL reads: reported as it is
        return len(data), len(data), "?"


def measure(lib: Library) -> dict:
    kinds = {k: {"files": 0, "bytes": 0, "deflated": 0} for k in KINDS}
    geometry = defaultdict(int)
    program: dict[str, int] = defaultdict(int)
    images = {"webp": 0, "webp_1280": 0, "largest": []}
    narration_ext: dict[str, int] = defaultdict(int)
    for rel, data in lib.files.items():
        kind = kind_of(rel)
        if kind == "skip":
            continue
        row = kinds[kind]
        row["files"] += 1
        row["bytes"] += len(data)
        row["deflated"] += _deflated(data)
        if kind == "geometry":
            for part, value in geometry_parts(data).items():
                geometry[part] += value
            no_z = len(data) - geometry_parts(data)["points z"]
            geometry["deflated without z"] += _deflated(data) * no_z // max(len(data), 1)
        elif kind == "program":
            for verb, value in program_parts(data.decode("utf-8", "ignore")).items():
                program[verb] += value
        elif kind == "images":
            webp, webp_small, dims = image_saving(data)
            images["webp"] += webp
            images["webp_1280"] += webp_small
            images["largest"].append((len(data), rel, dims))
        elif kind == "narration":
            narration_ext[Path(rel).suffix] += len(data)
            seconds = audio_seconds(rel, data)
            if seconds:
                narration_ext["seconds"] = narration_ext.get("seconds", 0) + seconds
    images["largest"] = sorted(images["largest"], reverse=True)[:5]
    total = sum(r["bytes"] for r in kinds.values())
    return {"title": lib.title, "source": str(lib.source), "total": total,
            "zip": sum(r["deflated"] for k, r in kinds.items() if k != "narration"),
            "kinds": kinds, "geometry": dict(geometry), "program": dict(program), "images": images,
            "narration": dict(narration_ext)}


def mb(n: float) -> str:
    return f"{n / 1048576:7.2f} MB" if n >= 104858 else f"{n / 1024:7.1f} KB"


def report(rows: list[dict], out=sys.stdout) -> None:
    def table(title: str, kinds: dict, total: int) -> None:
        print(f"\n{title}", file=out)
        print(f"  {'kind':<12} {'files':>6} {'size':>11} {'share':>6} {'deflated':>11}", file=out)
        for kind in KINDS:
            r = kinds[kind]
            if r["files"]:
                print(f"  {kind:<12} {r['files']:>6} {mb(r['bytes']):>11} {100 * r['bytes'] / max(total, 1):5.1f}% "
                      f"{mb(r['deflated']):>11}", file=out)
        print(f"  {'total':<12} {sum(r['files'] for r in kinds.values()):>6} {mb(total):>11}", file=out)

    for row in rows:
        seconds = row["narration"].get("seconds")
        length = f"  [{clock(seconds)}]" if seconds else ""
        table(f"{row['title']}{length}  ({row['source']})", row["kinds"], row["total"])
    all_kinds = {k: {"files": 0, "bytes": 0, "deflated": 0} for k in KINDS}
    geometry: dict[str, int] = defaultdict(int)
    program: dict[str, int] = defaultdict(int)
    webp = webp_small = 0
    for row in rows:
        for k, r in row["kinds"].items():
            for f in ("files", "bytes", "deflated"):
                all_kinds[k][f] += r[f]
        for k, v in row["geometry"].items():
            geometry[k] += v
        for k, v in row["program"].items():
            program[k] += v
        webp += row["images"]["webp"]
        webp_small += row["images"]["webp_1280"]
    total = sum(r["bytes"] for r in all_kinds.values())
    table(f"ALL {len(rows)} LECTURES", all_kinds, total)
    if rows:
        print(f"\n  per lecture: {mb(total / len(rows))} on average; the zip (all but narration) "
              f"{mb(sum(r['zip'] for r in rows) / len(rows))}", file=out)
        timed = [r["narration"]["seconds"] for r in rows if r["narration"].get("seconds")]
        if timed:
            spent = sum(timed)
            print(f"  playing time: {clock(spent)} in all ({len(timed)} of {len(rows)} lectures timed), "
                  f"{clock(spent / len(timed))} on average; {mb(total / len(rows) / (spent / len(timed) / 60))} "
                  "per minute", file=out)
    g = all_kinds["geometry"]
    if g["bytes"]:
        print("\nGEOMETRY (assets/*.panm)", file=out)
        for part in ("points xy", "points z", "instances", "headers"):
            print(f"  {part:<12} {mb(geometry.get(part, 0)):>11} {100 * geometry.get(part, 0) / g['bytes']:5.1f}%",
                  file=out)
        print(f"  {geometry.get('shapes', 0)} shapes, {geometry.get('points', 0):,} points, "
              f"{geometry.get('frames', 0):,} frame records", file=out)
        print(f"  without z: {mb(g['bytes'] - geometry.get('points z', 0))}; deflated without z: "
              f"{mb(geometry.get('deflated without z', 0))}", file=out)
    p = all_kinds["program"]
    if p["bytes"]:
        print("\nPROGRAM TEXT (scenes/*.panim) by verb", file=out)
        for verb, size in sorted(program.items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {verb:<12} {mb(size):>11} {100 * size / p['bytes']:5.1f}%", file=out)
        print(f"  deflated: {mb(p['deflated'])} ({100 * p['deflated'] / p['bytes']:.0f}% of the text)", file=out)
    i = all_kinds["images"]
    if i["bytes"]:
        print("\nIMAGES", file=out)
        print(f"  as they are {mb(i['bytes'])}; as WebP q80 {mb(webp)}; WebP q80 at most 1280 px {mb(webp_small)}",
              file=out)
        biggest = sorted((x for row in rows for x in row["images"]["largest"]), reverse=True)[:8]
        for size, rel, dims in biggest:
            print(f"  {mb(size):>11}  {dims:>10}  {rel}", file=out)


def all_builds() -> list[Path]:
    """The app's builds in the temp folder, newest first (packed for the phone or not)."""
    return sorted((p for p in Path(tempfile.gettempdir()).glob("panim-build-*")
                   if (p / "library").is_dir() or (p / "dsl" / "generated").is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def latest_builds(count: int, match: str | None) -> list[Path]:
    out = []
    for build in all_builds():
        if match and match.lower() not in Library(build).text().lower():
            continue
        out.append(build)
        if len(out) >= count:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sources", nargs="*", type=Path)
    ap.add_argument("--latest", type=int, help="the newest N builds in the temp folder")
    ap.add_argument("--match", help="with --latest: only builds whose titles or chapters mention this")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args(argv)
    sources = list(args.sources) + (latest_builds(args.latest, args.match) if args.latest else [])
    if not sources:
        builds = all_builds()
        print(f"No lecture to measure. The temp folder ({tempfile.gettempdir()}) has {len(builds)} build(s)"
              + (f"; none mention {args.match!r}." if args.match and builds else "."), file=sys.stderr)
        for build in builds[:20]:
            print(f"  {build}  {Library(build).title}", file=sys.stderr)
        if builds:
            print("Run again with no --match, a word from one of those titles, or the folders themselves.",
                  file=sys.stderr)
        return 1
    rows = [measure(Library(s)) for s in sources]
    report(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, default=str))
    if args.csv:
        with args.csv.open("w") as f:
            f.write("lecture,kind,files,bytes,deflated\n")
            for row in rows:
                for kind, r in row["kinds"].items():
                    if r["files"]:
                        f.write(f"\"{row['title']}\",{kind},{r['files']},{r['bytes']},{r['deflated']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
