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
    flags: int = 0  # bit 0: shade_in_3d, i.e. participates in depth sorting
    normal: np.ndarray | None = None  # unit normal, only when shaded

    def key(self):
        return (
            self.atlas_id,
            np.round(self.transform, 5).tobytes(),
            self.fill,
            self.stroke,
            round(self.stroke_width, 2),
            self.flags,
            None if self.normal is None else np.round(self.normal, 3).tobytes(),
        )


def quantise(points: np.ndarray, lo: np.ndarray, span: np.ndarray) -> np.ndarray:
    """Map scene coordinates onto a uint16 grid over the scene bounds."""
    normalised = (points - lo) / span
    return np.clip(normalised * 65535.0, 0, 65535).astype("<u2")


FLAG_CAMERA = 1 << 0
SHADE_IN_3D = 1 << 0  # per-instance flag

# Per-frame camera state: frame_center(3), focal_distance, zoom, rotation(9),
# light_source(3). The light moves with the scene, so it is part of the track.
CAMERA_FLOATS = 17


def project(points: np.ndarray, camera: np.ndarray) -> np.ndarray:
    """Apply a captured camera to world-space points.

    Replicates ThreeDCamera.project_points. The device does this per frame,
    which is why the IR carries 3D vertices and a camera track rather than
    flattened 2D output -- a camera move then costs 14 floats, not new geometry.
    """
    centre = camera[0:3]
    focal, zoom = float(camera[3]), float(camera[4])
    rotation = camera[5:14].reshape(3, 3)

    out = (points - centre) @ rotation.T
    zs = out[:, 2]
    denominator = focal - zs
    factor = np.where(denominator < 0, 1e6, focal / np.where(denominator == 0, 1e-9, denominator))
    out = out.copy()
    out[:, 0] *= factor * zoom
    out[:, 1] *= factor * zoom
    return out


def serialise(
    atlas: Atlas,
    records: list[tuple[int, dict[int, Instance]]],
    fps: int,
    cameras: list[np.ndarray] | None = None,
) -> bytes:
    """Pack atlas, optional camera track, and timeline into the binary IR."""
    if atlas.shapes:
        stacked = np.vstack(atlas.shapes)
        lo, hi = stacked.min(axis=0), stacked.max(axis=0)
    else:
        lo = hi = np.zeros(3)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)

    flags = FLAG_CAMERA if cameras else 0

    out = bytearray()
    out += struct.pack(
        "<4sHHHII6f",
        MAGIC, VERSION, flags, fps, len(records), len(atlas.shapes),
        *lo.astype(float), *hi.astype(float),
    )

    if cameras:
        for cam in cameras:
            out += np.asarray(cam, dtype="<f4").tobytes()

    for shape in atlas.shapes:
        out += struct.pack("<I", len(shape))
        out += quantise(shape, lo, span).tobytes()

    for kind, instances in records:
        out += struct.pack("<BI", kind, len(instances))
        # Insertion order is scene traversal order, which is Manim's painter
        # order. Sorting by slot here would silently reorder overlapping shapes.
        for slot, inst in instances.items():
            out += struct.pack("<IIB", slot, inst.atlas_id, inst.flags)
            # Linear part in float16, translation in float32. The linear part is
            # a small dimensionless multiplier where half precision is ample;
            # translation is in scene units, where float16's ~0.4px resolution
            # at 720p would be visible.
            out += inst.transform[:, :3].astype("<f2").tobytes()
            out += inst.transform[:, 3].astype("<f4").tobytes()
            out += bytes(inst.fill) + bytes(inst.stroke)
            out += struct.pack("<H", int(min(inst.stroke_width * 64, 65535)))
            if inst.flags & SHADE_IN_3D:
                normal = inst.normal if inst.normal is not None else np.array([0.0, 0.0, 1.0])
                out += np.asarray(normal, dtype="<f2").tobytes()

    return bytes(out)
