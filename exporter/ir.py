"""Scene IR: format definition, atlas, and binary serialisation.

The format's central idea is that **every drawn shape is an instance**:
an atlas reference plus an affine transform plus style. Two things fall out
of that single representation, and they are the two largest measured levers:

  * Repeated glyphs collapse to one atlas entry (~50x on text).
  * An animated pan/zoom/grow becomes a changing transform over unchanged
    geometry, instead of rewritten points (~275x on the Cartopy scene).

Layout (little-endian):

    header    magic "PANM", version, fps, counts, scene bounds
    atlas     per shape: point count, then points as quantised uint16 x3
    timeline  per record: SNAPSHOT (every instance) or KEYFRAME (changed only)

Keyframes carry absolute values rather than deltas, so applying them is an
overwrite and never accumulates error. Seeking is: load the preceding
snapshot, apply keyframes up to t.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = b"PANM"
VERSION = 1

REC_SNAPSHOT = 0
REC_KEYFRAME = 1

# Residual below which a point cloud is considered an affine image of another.
# In scene units; the 16-bit quantisation grid is far finer than this.
AFFINE_TOLERANCE = 1e-4


def fit_affine(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Least-squares affine taking src -> dst, with its max residual.

    Returns (3x4 matrix, residual) or None if the shapes are incompatible.
    """
    if src.shape != dst.shape or len(src) < 4:
        return None
    homo = np.hstack([src, np.ones((len(src), 1))])  # N x 4
    matrix, *_ = np.linalg.lstsq(homo, dst, rcond=None)  # 4 x 3
    residual = float(np.abs(homo @ matrix - dst).max())
    return matrix.T, residual


@dataclass
class Atlas:
    """Canonical geometry, deduplicated by affine equivalence."""

    shapes: list[np.ndarray] = field(default_factory=list)
    _by_count: dict[int, list[int]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    affine_hits: int = 0

    def resolve(self, points: np.ndarray, hint: int | None = None) -> tuple[int, np.ndarray]:
        """Map points to (atlas_id, transform), adding a new entry if needed.

        `hint` is the atlas id this mobject used last frame. Checking it first
        is what makes an animated transform cheap: the geometry is already
        there and only the matrix changes.
        """
        if hint is not None and hint < len(self.shapes):
            fit = fit_affine(self.shapes[hint], points)
            if fit and fit[1] < AFFINE_TOLERANCE:
                self.hits += 1
                self.affine_hits += 1
                return hint, fit[0]

        for candidate in self._by_count.get(len(points), []):
            fit = fit_affine(self.shapes[candidate], points)
            if fit and fit[1] < AFFINE_TOLERANCE:
                self.hits += 1
                return candidate, fit[0]

        canonical = points - points.mean(axis=0)
        atlas_id = len(self.shapes)
        self.shapes.append(canonical)
        self._by_count.setdefault(len(points), []).append(atlas_id)
        self.misses += 1

        fit = fit_affine(canonical, points)
        return atlas_id, fit[0] if fit else np.eye(3, 4)


@dataclass
class Instance:
    atlas_id: int
    transform: np.ndarray  # 3x4
    fill: tuple[int, int, int, int]
    stroke: tuple[int, int, int, int]
    stroke_width: float

    def key(self):
        return (
            self.atlas_id,
            np.round(self.transform, 5).tobytes(),
            self.fill,
            self.stroke,
            round(self.stroke_width, 2),
        )


def quantise(points: np.ndarray, lo: np.ndarray, span: np.ndarray) -> np.ndarray:
    """Map scene coordinates onto a uint16 grid over the scene bounds."""
    normalised = (points - lo) / span
    return np.clip(normalised * 65535.0, 0, 65535).astype("<u2")


def serialise(atlas: Atlas, records: list[tuple[int, dict[int, Instance]]], fps: int) -> bytes:
    """Pack atlas and timeline into the binary IR."""
    if atlas.shapes:
        stacked = np.vstack(atlas.shapes)
        lo, hi = stacked.min(axis=0), stacked.max(axis=0)
    else:
        lo = hi = np.zeros(3)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)

    out = bytearray()
    out += struct.pack(
        "<4sHHHII6f",
        MAGIC, VERSION, 0, fps, len(records), len(atlas.shapes),
        *lo.astype(float), *hi.astype(float),
    )

    for shape in atlas.shapes:
        out += struct.pack("<I", len(shape))
        out += quantise(shape, lo, span).tobytes()

    for kind, instances in records:
        out += struct.pack("<BI", kind, len(instances))
        for slot, inst in sorted(instances.items()):
            out += struct.pack("<II", slot, inst.atlas_id)
            out += inst.transform.astype("<f4").tobytes()
            out += bytes(inst.fill) + bytes(inst.stroke)
            out += struct.pack("<H", int(min(inst.stroke_width * 64, 65535)))

    return bytes(out)
