"""Cartopy coastlines: dense, singular, non-repeating vector content.

The scene the standing tension was written about. A coastline is the worst case
for a vector IR: tens of thousands of points, appearing once, so the glyph-atlas
deduplication that rescues text does nothing here. This is what the raster
fallback exists for, and this scene exists to measure whether it is needed.

Natural Earth 50m physical coastline, via cartopy's bundled downloader.
"""

from manim import *
import cartopy.io.shapereader as shpreader

RESOLUTION = "50m"
LON_SCALE = 6.0 / 180.0  # map +/-180 lon onto +/-6 Manim units
LAT_SCALE = 3.2 / 90.0


def line_coords(geom):
    """Yield coordinate arrays from LineString or MultiLineString."""
    if hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield np.asarray(part.coords)
    else:
        yield np.asarray(geom.coords)


def build_coastline():
    fn = shpreader.natural_earth(
        resolution=RESOLUTION, category="physical", name="coastline"
    )
    group = VGroup()
    for geom in shpreader.Reader(fn).geometries():
        for coords in line_coords(geom):
            if len(coords) < 2:
                continue
            pts = [
                np.array([lon * LON_SCALE, lat * LAT_SCALE, 0.0])
                for lon, lat in coords[:, :2]
            ]
            line = VMobject(stroke_width=1.2, stroke_color=BLUE_C)
            line.set_points_as_corners(pts)
            group.add(line)
    return group


class CartopyMap(Scene):
    def construct(self):
        title = Text("Natural Earth coastline", font_size=28).to_edge(UP)
        coast = build_coastline()

        self.add(title)
        # FadeIn rather than Create: stroke-wise creation of 236k points is
        # pathological in Manim and is not what this scene is measuring.
        self.play(FadeIn(coast), run_time=1.5)
        self.wait(0.5)

        # Zoom in: the case that decides raster resolution, since a raster layer
        # must be exported at the tightest zoom the camera track reaches.
        self.play(
            coast.animate.scale(3.0).shift(LEFT * 2 + DOWN * 1),
            run_time=3,
        )
        self.wait(1)
