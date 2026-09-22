"""Reference renderer: draw a decoded IR frame with Cairo.

This is the oracle. It exists so the format can be proven correct independently
of any Android code -- when the Kotlin renderer disagrees with this, the bug is
in the Kotlin. It also provides the golden-image harness the spec requires.

Deliberately simple and slow. Correctness only.
"""

from __future__ import annotations

import cairo
import os

import numpy as np

from .decode import DecodedInstance, DecodedIR
from .ir import CLOSED_SOLID, NORMAL_INWARD, SHADE_IN_3D, project

# Manim defaults at 16:9.
FRAME_WIDTH = 14.222222222222221
FRAME_HEIGHT = 8.0
# Manim's cairo_line_width_multiple: stroke_width is expressed in units of
# 1/100th of a scene unit.
STROKE_SCALE = 0.01


def _subpaths(points: np.ndarray):
    """Split a Manim point array into subpaths of cubic Bezier segments.

    Manim stores four points per cubic curve. A subpath continues while each
    curve starts where the previous one ended.
    """
    n_curves = len(points) // 4
    current: list[np.ndarray] = []
    for i in range(n_curves):
        curve = points[4 * i : 4 * i + 4]
        if current and not np.allclose(current[-1][3], curve[0], atol=1e-6):
            yield current
            current = []
        current.append(curve)
    if current:
        yield current


# How far a dropped point may sit from the segment that replaces it, in pixels
# of whatever the frame is being rendered at. Matches RenderOptions.forSurface
# in the player, and has to be expressed in pixels for the same reason: half a
# pixel is a promise about what a viewer can see. PANIM_LOD_ERROR_PX overrides
# it, which is how the cost of the whole idea gets measured against Manim
# rather than guessed; zero turns it off.
LOD_ERROR_PX = float(os.environ.get("PANIM_LOD_ERROR_PX", "0.5"))

LINE_TOLERANCE = 1e-3  # handles this close to the chord mean the curve is a line


def _is_line(curve: np.ndarray) -> bool:
    """Whether a cubic's handles lie on its chord, as the renderer tests it."""
    delta = curve[3] - curve[0]
    return bool(
        np.abs(curve[1][:2] - (curve[0] + delta / 3.0)[:2]).max() <= LINE_TOLERANCE
        and np.abs(curve[2][:2] - (curve[0] + delta * (2.0 / 3.0))[:2]).max() <= LINE_TOLERANCE
    )


def _emit_subpath(ctx, subpath, tolerance: float) -> None:
    """Draw one subpath, dropping points within `tolerance` of the pen.

    The same rule the player applies, and for the same reason: the exporter has
    to decimate for the tightest zoom a program reaches, so a shape carries more
    detail than it needs in the frames where all of it is on screen. A dropped
    run is held rather than discarded -- whatever ends it draws a straight
    segment to the last point, so a subpath never loses its end.
    """
    ctx.move_to(subpath[0][0][0], subpath[0][0][1])
    anchor = subpath[0][0]
    held = None
    for curve in subpath:
        end = curve[3]
        if tolerance > 0.0 and _is_line(curve):
            if float(np.hypot(*(end[:2] - anchor[:2]))) < tolerance:
                held = end
                continue
            # A straight segment supersedes the run it follows: it starts from
            # the anchor, so the held points are inside the tolerance of it and
            # are dropped rather than drawn to. Only a curve has to be caught up
            # to, because a curve must start where it was drawn from.
            ctx.line_to(end[0], end[1])
        else:
            if held is not None:
                ctx.line_to(held[0], held[1])
            ctx.curve_to(curve[1][0], curve[1][1], curve[2][0], curve[2][1], end[0], end[1])
        held = None
        anchor = end
    if held is not None:
        ctx.line_to(held[0], held[1])
    ctx.close_path()


def draw_instance(
    ctx,
    inst: DecodedInstance,
    shapes: list[np.ndarray],
    camera: np.ndarray | None = None,
    lod: float = 0.0,
) -> None:
    canonical = shapes[inst.atlas_id]
    points = canonical @ inst.transform[:, :3].T + inst.transform[:, 3]
    if camera is not None:
        points = project(points, camera)

    ctx.new_path()
    for subpath in _subpaths(points):
        _emit_subpath(ctx, subpath, lod)

    shade = 0.0
    if camera is not None and inst.flags & SHADE_IN_3D and inst.normal is not None:
        # Manim's get_shaded_rgb: light = 0.5 * dot(normal, to_sun)**3, halved
        # again when facing away. The normal and light source are carried in the
        # IR so this is derived on the device, not baked into colours.
        world = canonical @ inst.transform[:, :3].T + inst.transform[:, 3]
        centre = (world.min(axis=0) + world.max(axis=0)) / 2.0
        to_sun = camera[14:17] - centre
        norm = np.linalg.norm(to_sun)
        if norm > 1e-9:
            shade = 0.5 * float(inst.normal @ (to_sun / norm)) ** 3
            if shade < 0:
                shade *= 0.5

    fr, fg, fb, fa = (c / 255.0 for c in inst.fill)
    if fa > 0:
        ctx.set_source_rgba(
            min(max(fr + shade, 0), 1), min(max(fg + shade, 0), 1), min(max(fb + shade, 0), 1), fa
        )
        ctx.fill_preserve()

    sr, sg, sb, sa = (c / 255.0 for c in inst.stroke)
    if sa > 0 and inst.stroke_width > 0:
        ctx.set_source_rgba(
            min(max(sr + shade, 0), 1), min(max(sg + shade, 0), 1), min(max(sb + shade, 0), 1), sa
        )
        ctx.set_line_width(inst.stroke_width * STROKE_SCALE)
        ctx.stroke()
    ctx.new_path()


def render_frame(ir: DecodedIR, index: int, width: int = 1280, height: int = 720) -> np.ndarray:
    """Render one frame to an HxWx3 uint8 RGB array."""
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    ctx = cairo.Context(surface)

    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()

    # Work in scene coordinates: y up, origin centred. Line widths are then in
    # scene units, which is how Manim expresses stroke_width.
    ctx.set_matrix(
        cairo.Matrix(
            width / FRAME_WIDTH, 0,
            0, -height / FRAME_HEIGHT,
            width / 2, height / 2,
        )
    )
    # Bevel, matching the renderer. Manim joins with an arc; building one at
    # every vertex of a 22,719-verb coastline costs more on the device than any
    # other single thing, and 7.3 carries what the difference measures.
    # Round, as Manim strokes. Building an arc at every vertex was the single
    # largest cost on a coastline until playback detail cut the vertex count;
    # now it is worth one late frame of 181 and 0.17 points of fidelity margin,
    # so the join that matches Manim is the one that ships. See 7.3.
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)

    lod = LOD_ERROR_PX / (width / FRAME_WIDTH)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    camera = ir.cameras[index] if ir.cameras and index < len(ir.cameras) else None
    instances = ir.frame(index)

    if camera is not None:
        # Manim's ThreeDCamera sorts by distance to the camera every frame, so
        # draw order changes as the camera moves. The key is derived, not
        # stored: bounding-box centre rotated into camera space, z component.
        # Objects not flagged shade_in_3d sort last, matching Manim's np.inf.
        rotation = camera[5:14].reshape(3, 3)

        def depth(inst: DecodedInstance) -> float:
            if not inst.flags & SHADE_IN_3D:
                return float("inf")
            world = ir.shapes[inst.atlas_id] @ inst.transform[:, :3].T + inst.transform[:, 3]
            centre = (world.min(axis=0) + world.max(axis=0)) / 2.0
            return float(centre @ rotation.T[:, 2])

        instances = sorted(instances, key=depth)

        # A back face of a closed solid is covered by a front face of the same
        # solid, so drawing it is work whose only visible effect is to dapple
        # the antialiased seams between the faces in front of it. Rotation row
        # 2 is the camera's forward axis, and project() makes a larger value
        # mean nearer, so a face turned towards the viewer has a positive
        # component along it.
        forward = rotation[2]

        def faces_viewer(inst: DecodedInstance) -> bool:
            if not inst.flags & CLOSED_SOLID or inst.normal is None:
                return True
            outward = -inst.normal if inst.flags & NORMAL_INWARD else inst.normal
            return float(outward @ forward) > 0.0

        instances = [inst for inst in instances if faces_viewer(inst)]

    for inst in instances:
        draw_instance(ctx, inst, ir.shapes, camera, lod)

    surface.flush()
    buf = np.ndarray(
        shape=(height, surface.get_stride() // 4, 4),
        dtype=np.uint8,
        buffer=surface.get_data(),
    )
    return buf[:, :width, [2, 1, 0]].copy()  # BGRA -> RGB
