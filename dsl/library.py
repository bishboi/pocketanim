"""A library-wide glyph atlas, shared across every scene.

Measured problem: a per-string text asset costs ~682 bytes per glyph, so a
library re-ships the alphabet once per caption. Deduplicating at the *glyph*
level instead means the outlines download once and every subsequent text costs
only instance records.

This is the change §3.5 of the spec called for -- the atlas is library-wide, not
per bundle -- and it is what makes text scenes viable at tier 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter.decode import load
from exporter.ir import GLYPH_TOLERANCE, REC_SNAPSHOT, Atlas, Instance, serialise

LIBRARY_PATH = Path("dsl/generated/library.atlas")


def library_path() -> Path:
    """The glyph library this build writes to: its own, or (PANIM_GLYPH_LIBRARY) the one the builds of a
    lecture's chapters share, so their text assets number the same glyphs the same way when joined."""
    import os

    shared = os.environ.get("PANIM_GLYPH_LIBRARY")
    return Path(shared) if shared else LIBRARY_PATH


class library_lock:
    """Held while a text asset reads, adds to and writes the library: builds side by side share it, and two
    adding a glyph at once would give two glyphs one number. A no-op for a build with its own library."""

    def __enter__(self):
        import os

        self.handle = None
        if os.environ.get("PANIM_GLYPH_LIBRARY"):
            import fcntl

            lock = Path(os.environ["PANIM_GLYPH_LIBRARY"] + ".lock")
            lock.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(lock, "a+")
            fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            import fcntl

            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
        return False


class GlyphLibrary:
    """Accumulating atlas keyed by glyph shape, persisted across exports."""

    def __init__(self, path: Path | None = None):
        self.path = path or library_path()
        self.atlas = Atlas()
        if self.path.exists():
            existing = load(self.path.read_bytes())
            for shape in existing.shapes:
                self.atlas.shapes.append(shape)
                self.atlas._by_count.setdefault(len(shape), []).append(
                    len(self.atlas.shapes) - 1
                )
                self.atlas._exact.setdefault((len(shape), np.round(shape - shape.mean(axis=0), 6).tobytes()),
                                             len(self.atlas.shapes) - 1)

    def resolve(self, points: np.ndarray) -> tuple[int, np.ndarray]:
        """Map a glyph onto the shared atlas, adding it only if new.

        Uses the looser GLYPH_TOLERANCE: Manim bakes size into outlines, so the
        same letter at different font sizes is only *nearly* a scaled copy. The
        difference is sub-pixel and deduplicating across it halves the atlas.
        """
        return self.atlas.resolve(points, tolerance=GLYPH_TOLERANCE)

    def save(self) -> int:
        blob = serialise(self.atlas, [], fps=30)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(blob)
        return len(blob)

    @property
    def glyph_count(self) -> int:
        return len(self.atlas.shapes)


def export_text_instances(mob, path: Path, library: GlyphLibrary) -> int:
    """Write a text asset holding only instance records.

    Geometry lives in the shared library, so this file carries references and
    transforms and nothing else -- the whole point of the change.
    """
    from exporter.export_scene import read_style

    instances: dict[int, Instance] = {}
    for index, sub in enumerate(mob.get_family()):
        points = getattr(sub, "points", None)
        if points is None or len(points) < 4:
            continue
        atlas_id, transform = library.resolve(np.asarray(points, dtype=np.float64))
        fill, stroke, width = read_style(sub)
        instances[index] = Instance(atlas_id, transform, fill, stroke, width)

    # Empty atlas: the ids point into the shared library rather than here.
    blob = serialise(Atlas(), [(REC_SNAPSHOT, instances)], fps=30)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return len(blob)


def snapshot_family(mob) -> list[tuple]:
    """Freeze a mobject's drawable family: geometry and style, nothing live.

    Baking happens when a mobject is declared, but the tolerance to bake at is
    only known once the whole animation has been recorded -- it depends on the
    tightest zoom the program reaches. Keeping the mobject instead would keep a
    thing that the animation then scales and recolours, so the second bake would
    use the geometry the scene *ended* with.
    """
    import numpy as np

    from exporter.export_scene import (
        closed_solid_centres,
        points_outward,
        read_style,
        unit_normal,
    )

    solid = closed_solid_centres(mob)
    out = []
    for sub in mob.get_family():
        if type(sub).__name__ in ("ImageMobject", "AbstractImageMobject"):
            # Not a vector. Its four corners are a placement quad, and reading
            # fill_color raises AttributeError.
            continue
        points = getattr(sub, "points", None)
        if points is None or len(points) < 4:
            continue
        array = np.array(points, dtype=np.float64)  # a copy, not a view
        fill, stroke, width = read_style(sub)
        # 3D geometry must carry its normal and shade flag, or the renderer
        # skips depth sorting and a rotating surface draws in list order.
        shaded = bool(getattr(sub, "shade_in_3d", False))
        normal = unit_normal(sub, array) if shaded else None
        # A face may be back-face culled only if it belongs to a closed solid,
        # and then only against which way is out -- the stored normal is a
        # plane fit forced into one hemisphere, so half of any sphere's point
        # inwards. Culling on those would drop the half facing the viewer.
        centre = solid.get(id(sub))
        closed = shaded and centre is not None and normal is not None
        inward = closed and not points_outward(normal, array, centre)
        out.append((array, fill, stroke, width, shaded, normal, closed, inward))
    return out


def export_standalone_asset(snapshot: list[tuple], path: Path, tolerance: float = 0.0) -> int:
    """Bake singular geometry into a self-contained asset.

    Imported artwork -- a coastline, a molecule -- is content, not program, and
    unlike glyphs it does not repeat across a library. So it carries its own
    atlas rather than polluting the shared glyph library with 200k points that
    will never be reused.

    A positive `tolerance` decimates that artwork to the detail a screen can
    resolve; see exporter/simplify.py for why that is an exporter decision and
    not a renderer one.
    """
    import numpy as np

    from exporter.ir import CLOSED_SOLID, NORMAL_INWARD, SHADE_IN_3D
    from exporter.simplify import simplify_shape

    atlas = Atlas()
    instances: dict[int, Instance] = {}
    for index, entry in enumerate(snapshot):
        array, fill, stroke, width, shaded, normal, closed, inward = entry
        if tolerance > 0.0:
            array = simplify_shape(array, tolerance)
        atlas_id, transform = atlas.resolve(np.asarray(array, dtype=np.float64))
        flags = (
            (SHADE_IN_3D if shaded else 0)
            | (CLOSED_SOLID if closed else 0)
            | (NORMAL_INWARD if inward else 0)
        )
        instances[index] = Instance(
            atlas_id, transform, fill, stroke, width, flags,
            normal if shaded else None,
        )

    blob = serialise(atlas, [(REC_SNAPSHOT, instances)], fps=30)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return len(blob)


def load_standalone_asset(path: Path):
    ir = load(path.read_bytes())
    return ir.shapes, ir.frame(0)


def load_text_asset(path: Path, library_path: Path = LIBRARY_PATH):
    """Resolve a text asset's instances against the shared glyph library."""
    shared = load(library_path.read_bytes())
    asset = load(path.read_bytes())
    return shared.shapes, asset.frame(0)
