"""Maps from real data: countries from Natural Earth, places found by name (cities, historic names such as Edo or
Constantinople, sites), states as they stood in a year (historical borders), routes, pins and labels. Drawn in
the look: vox has beige land on paper with spaced capital names; blueprint has outlined land on the grid with a
graticule.

    m = Map("east asia")                              # or Map(bounds=(lon0, lat0, lon1, lat1)), REGIONS
    self.play(m.appear())
    self.play(m.shade("Japan"))                       # one country filled in the accent colour
    k = m.pin("Kyoto", label="Kyoto"); self.play(k.appear())
    r = m.route(["Venice", "Constantinople", "Samarkand", "Beijing"]); self.play(r.appear(run=4))
    s = m.empire("Song", 1100); self.play(s.appear())  # the Song state's extent around 1100
    self.play(self.cam_to(m.view("Japan", "Korea")))  # the camera frames those
    m.point(135.7, 35.0)                              # a (lon, lat) on the map as it now stands
"""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, PI, RIGHT, UP, AnimationGroup, Circle, Create, DashedVMobject, Dot, FadeIn,
                   LaggedStart, Line, Polygon, Rectangle, VGroup, VMobject)

from .base import Piece
from .look import L
from .text import label, text

ENGINE = Path(__file__).resolve().parents[2]

REGIONS = {
    "world": (-170, -56, 180, 78), "east asia": (95, 17, 148, 50), "china": (72, 17, 136, 54),
    "japan": (127, 29, 147, 46), "korea": (124, 33, 131, 43.5), "india": (66, 6, 98, 37),
    "south asia": (60, 4, 100, 38), "southeast asia": (92, -11, 142, 28), "middle east": (24, 12, 64, 42),
    "europe": (-12, 34, 42, 71), "mediterranean": (-10, 29, 40, 47), "africa": (-20, -36, 53, 38),
    "eurasia": (-12, 0, 150, 62), "silk road": (8, 18, 128, 56), "europe to china": (-12, 12, 145, 58),
    "north america": (-170, 12, -50, 72), "south america": (-85, -57, -32, 14), "americas": (-170, -56, -30, 72),
    "atlantic": (-100, -40, 25, 65), "indian ocean": (30, -45, 120, 28), "pacific": (100, -50, 290, 60),
    "russia": (25, 40, 180, 78), "central asia": (45, 30, 90, 56), "australia": (110, -45, 156, -9),
}


def _engine():
    if str(ENGINE) not in sys.path:
        sys.path.insert(0, str(ENGINE))


@lru_cache(None)
def _country_records(res: str):
    import cartopy.io.shapereader as shp
    path = shp.natural_earth(resolution=res, category="cultural", name="admin_0_countries")
    out = []
    for rec in shp.Reader(path).records():
        a = rec.attributes
        names = {str(a.get(k) or "") for k in ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "SOVEREIGNT", "ABBREV")}
        out.append((str(a.get("NAME")), {n.lower() for n in names if n}, rec.geometry))
    return out


def _polys(geom):
    from shapely.geometry import MultiPolygon, Polygon as SPoly, GeometryCollection
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, SPoly):
        return [geom]
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        return [g for part in geom.geoms for g in _polys(part)]
    return []


class Map(Piece):
    enter_kind = "shape"

    def __init__(self, region: str | None = "east asia", bounds=None, width: float = 13.0, height: float = 7.2,
                 countries=None, detail: str = "auto", names: bool = False, graticule: bool | None = None,
                 frame: bool | None = None, year: int | None = None):
        """A map of `region` (REGIONS) or `bounds` (lon0, lat0, lon1, lat1), fitted into width x height units and
        centred at the origin. `countries`: only these drawn (default all). `names`: label the countries. `year`:
        draw the states as they stood then (historical borders) instead of today's countries."""
        super().__init__()
        look = L()
        self.look = look
        b = bounds or REGIONS[region.lower()]
        self.bounds = tuple(float(v) for v in b)
        lon0, lat0, lon1, lat1 = self.bounds
        self.k = math.cos(math.radians((lat0 + lat1) / 2))
        span_x, span_y = (lon1 - lon0) * self.k, lat1 - lat0
        self.scale_ = min(width / span_x, height / span_y)
        self.centre = ((lon0 + lon1) / 2, (lat0 + lat1) / 2)
        res = "10m" if detail == "high" or (detail == "auto" and lon1 - lon0 < 30) else "50m"
        self.res = res
        # Where the map's own coordinates go: three hidden dots carried along when the map is moved or scaled.
        self._ref = VGroup(Dot(ORIGIN, radius=0.001), Dot(RIGHT, radius=0.001), Dot(UP, radius=0.001)).set_opacity(0)
        self.add(self._ref)

        w, h = span_x * self.scale_, span_y * self.scale_
        sea = Rectangle(width=w, height=h, stroke_width=0 if look.name == "vox" else 1.5, stroke_color=look.muted,
                        fill_color=look.water, fill_opacity=1 if look.name == "vox" else 0.0)
        self.add(sea)
        self.name_part("sea", sea)
        self.countries: dict[str, VGroup] = {}
        self._geoms: dict[str, object] = {}
        land = VGroup()
        if year is not None:
            self._draw_year(year, land)
        else:
            self._draw_countries(countries, land)
        self.add(land)
        self.name_part("land", land)
        if graticule if graticule is not None else look.name == "blueprint":
            g = self._graticule()
            self.add(g)
            self.name_part("graticule", g)
        if frame if frame is not None else look.name == "blueprint":
            border = Rectangle(width=w, height=h, stroke_color=look.ink, stroke_width=2, fill_opacity=0)
            self.add(border)
            self.name_part("frame", border)
        self.labels = VGroup()
        if names:
            self._name_countries()
            self.add(self.labels)
        self.name_part("labels", self.labels)

    # ---- coordinates
    def _local(self, lon: float, lat: float) -> np.ndarray:
        return np.array([(lon - self.centre[0]) * self.k * self.scale_, (lat - self.centre[1]) * self.scale_, 0.0])

    def point(self, lon: float, lat: float) -> np.ndarray:
        """Where (lon, lat) is on the map as it now stands (after any move or scale)."""
        loc = self._local(lon, lat)
        o, x, y = (d.get_center() for d in self._ref)
        return o + loc[0] * (x - o) + loc[1] * (y - o)

    def lonlat(self, name: str) -> tuple[float, float]:
        """(lon, lat) of a place by name (cities, historic names, sites, seas, peaks), preferring one on this map."""
        _engine()
        import pocket_lecture as pl
        lon0, lat0, lon1, lat1 = self.bounds
        return pl.place(name, bounds=(lon0, lat0, lon1, lat1))

    def place_point(self, name_or_lonlat) -> np.ndarray:
        """A place on the map, by name or (lon, lat)."""
        if isinstance(name_or_lonlat, str):
            return self.point(*self.lonlat(name_or_lonlat))
        return self.point(*name_or_lonlat)

    def _poly(self, ring, **style) -> Polygon:
        pts = [self._local(x, y) for x, y in list(ring.coords)[:-1]]
        return Polygon(*pts, **style)

    def _shape_mob(self, geom, fill, edge, width, opacity) -> VGroup:
        from shapely.geometry import box
        lon0, lat0, lon1, lat1 = self.bounds
        clip = box(lon0, lat0, lon1, lat1)
        span = max(lon1 - lon0, lat1 - lat0)
        g = VGroup()
        if not geom.is_valid:
            geom = geom.buffer(0)                  # some historical borders cross themselves
        try:
            geom = geom.intersection(clip)
        except Exception:
            geom = geom.buffer(0).intersection(clip)
        for p in _polys(geom):
            if p.area < (span ** 2) * 2e-6:
                continue
            p = p.simplify(span / 900, preserve_topology=True)
            if p.is_empty or len(p.exterior.coords) < 4:
                continue
            g.add(self._poly(p.exterior, stroke_color=edge, stroke_width=width, fill_color=fill, fill_opacity=opacity))
        return g

    def _draw_countries(self, wanted, land: VGroup):
        from shapely.geometry import box
        look = self.look
        lon0, lat0, lon1, lat1 = self.bounds
        clip = box(lon0 - 2, lat0 - 2, lon1 + 2, lat1 + 2)
        want = {w.lower() for w in wanted} if wanted else None
        for name, aliases, geom in _country_records(self.res):
            if want and not (aliases & want):
                continue
            if geom is None or not geom.intersects(clip):
                continue
            mob = self._shape_mob(geom, look.land, look.land_edge, 1.2 if look.name == "vox" else 1.6, look.land_opacity)
            if len(mob):
                self.countries[name] = mob
                self._geoms[name] = geom
                land.add(mob)

    def _draw_year(self, year: int, land: VGroup):
        _engine()
        import historical
        from shapely.geometry import box
        look = self.look
        lon0, lat0, lon1, lat1 = self.bounds
        clip = box(lon0 - 2, lat0 - 2, lon1 + 2, lat1 + 2)
        for props, geom in historical._features(historical.nearest(year)):
            name = props.get("NAME")
            if not name or not geom.is_valid and not geom.buffer(0).is_valid:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            if not geom.intersects(clip):
                continue
            mob = self._shape_mob(geom, look.land, look.land_edge, 1.2, look.land_opacity)
            if len(mob):
                self.countries[str(name)] = mob
                self._geoms[str(name)] = geom
                land.add(mob)

    def _graticule(self, step: float | None = None) -> VGroup:
        look = self.look
        lon0, lat0, lon1, lat1 = self.bounds
        step = step or (5 if max(lon1 - lon0, lat1 - lat0) <= 40 else 10 if max(lon1 - lon0, lat1 - lat0) <= 90 else 30)
        g = VGroup()
        for lon in np.arange(math.ceil(lon0 / step) * step, lon1 + 1e-6, step):
            g.add(DashedVMobject(Line(self._local(lon, lat0), self._local(lon, lat1)), num_dashes=40, dashed_ratio=0.4)
                  .set_stroke(look.faint if look.name == "vox" else look.muted, width=1, opacity=0.7))
        for lat in np.arange(math.ceil(lat0 / step) * step, lat1 + 1e-6, step):
            g.add(DashedVMobject(Line(self._local(lon0, lat), self._local(lon1, lat)), num_dashes=60, dashed_ratio=0.4)
                  .set_stroke(look.faint if look.name == "vox" else look.muted, width=1, opacity=0.7))
        return g

    # ---- countries
    def country(self, name: str) -> VGroup:
        """A country's shapes (by its name, long name or abbreviation)."""
        key = self._key(name)
        return self.countries[key]

    def _key(self, name: str) -> str:
        n = name.lower()
        for k in self.countries:
            if k.lower() == n:
                return k
        for k, aliases, _ in _country_records(self.res):
            if n in aliases and k in self.countries:
                return k
        for k in self.countries:
            if n in k.lower():
                return k
        raise KeyError(f"{name!r} is not on this map; it has: {', '.join(sorted(self.countries))[:600]}")

    def shade(self, name: str, color: str | None = None, opacity: float = 1.0, run: float = 0.8):
        """An animation filling a country with `color` (the accent by default)."""
        mob = self.country(name)
        return mob.animate(run_time=run).set_fill(color or self.look.accent, opacity=opacity)

    def dim(self, keep=(), opacity: float = 0.35, run: float = 0.8):
        """An animation fading every country but those in `keep`."""
        keep_keys = {self._key(k) for k in keep}
        return AnimationGroup(*(mob.animate(run_time=run).set_opacity(opacity) for n, mob in self.countries.items()
                                if n not in keep_keys))

    def outline(self, name: str, color: str | None = None, width: float | None = None) -> Piece:
        """A country's border traced in `color` (appear() draws it round)."""
        mob = self.country(name)
        out = Piece(*(p.copy().set_fill(opacity=0).set_stroke(color or self.look.accent, width=width or self.look.stroke)
                      for p in mob))
        out.entering("draw")
        out.enter_kind = "line"
        return out

    def _rep_point(self, geom):
        from shapely.geometry import box
        lon0, lat0, lon1, lat1 = self.bounds
        part = geom.intersection(box(lon0, lat0, lon1, lat1))
        polys = _polys(part)
        if not polys:
            return None
        big = max(polys, key=lambda p: p.area)
        p = big.representative_point()
        return p.x, p.y

    def country_label(self, name: str, size: float | None = None, color: str | None = None):
        """A country's name at its middle (vox: spaced capitals; blueprint: mono capitals)."""
        key = self._key(name)
        ll = self._rep_point(self._geoms[key])
        if ll is None:
            raise KeyError(f"{name!r} is not inside the map's bounds")
        words = key.upper()
        if self.look.name == "vox":
            words = " ".join(words)
        lab = text(words, size=size or 20, role="body" if self.look.name == "vox" else "mono",
                   color=color or self.look.ink, weight=True)
        if color is None:
            lab.set_opacity(0.55)
        lab.move_to(self.point(*ll))
        return lab

    def _name_countries(self, min_share: float = 0.012):
        """Labels for the countries big enough on this map to hold one, the biggest first, none overlapping another
        or off the map."""
        from shapely.geometry import box
        from .layout import overlaps
        lon0, lat0, lon1, lat1 = self.bounds
        view = box(lon0, lat0, lon1, lat1)
        sized = []
        for n, g in self._geoms.items():
            try:
                a = g.intersection(view).area / view.area
            except Exception:
                continue
            if a >= min_share:
                sized.append((a, n))
        sea = self.part("sea")
        for a, n in sorted(sized, reverse=True):
            try:
                lab = self.country_label(n, size=16 + 10 * min(1.0, a * 4))
            except Exception:
                continue
            inside = (lab.get_left()[0] > sea.get_left()[0] + 0.1 and lab.get_right()[0] < sea.get_right()[0] - 0.1
                      and lab.get_bottom()[1] > sea.get_bottom()[1] + 0.1 and lab.get_top()[1] < sea.get_top()[1] - 0.1)
            if inside and not any(overlaps([lab, o], gap=0.12) for o in self.labels):
                self.labels.add(lab)

    def view(self, *names, pad: float = 0.5) -> Rectangle:
        """An invisible box round countries and/or places (by name): give it to cam_to to frame them."""
        pts = []
        for n in names:
            try:
                mob = self.country(n)
                pts += [mob.get_corner(UP + LEFT), mob.get_corner(DOWN + RIGHT)]
            except KeyError:
                pts.append(self.place_point(n))
        pts = np.array(pts)
        lo, hi = pts.min(axis=0) - pad, pts.max(axis=0) + pad
        r = Rectangle(width=hi[0] - lo[0], height=hi[1] - lo[1]).move_to((lo + hi) / 2)
        return r.set_opacity(0)

    # ---- things on the map
    def pin(self, where, label_text: str | None = None, color: str | None = None, side=RIGHT, size: float = 22,
            ring: bool = True) -> Piece:
        """A place marked: a dot (with a ring) and its label beside it. `where`: a name or (lon, lat); the label is the
        name unless given ("" for none)."""
        look = self.look
        c = color or look.accent
        p = self.place_point(where)
        dot = Dot(p, radius=0.08, color=c).set_stroke(look.bg, width=3, background=True)
        g = Piece()
        if ring:
            g.add(Circle(radius=0.17, stroke_color=look.bg, stroke_width=6).move_to(p),
                  Circle(radius=0.17, stroke_color=c, stroke_width=2.5).move_to(p))
        g.add(dot)
        g.name_part("dot", dot)
        words = label_text if label_text is not None else (where if isinstance(where, str) else "")
        if words:
            lab = label(words, size=size, color=look.ink, role="body" if look.name == "vox" else "mono")
            lab.next_to(dot, np.array(side, dtype=float), buff=0.15)
            g.add(lab)
            g.name_part("label", lab)
        g.entering("pop")
        return g

    def route(self, stops, color: str | None = None, curve: float = 0.12, width: float | None = None,
              dashed: bool | None = None, dots: bool = True, arrow_end: bool = True) -> Piece:
        """A journey through `stops` (names or (lon, lat)), drawn as a smooth curve. appear() draws it from the start;
        .travel(run) also sends a marker along it."""
        look = self.look
        c = color or look.accent
        pts = [self.place_point(s) for s in stops]
        path_pts = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            d = b - a
            n = np.array([-d[1], d[0], 0])
            mid = (a + b) / 2 + n * curve
            path_pts += [mid, b]
        line = VMobject(stroke_color=c, stroke_width=width or look.stroke * 1.1)
        line.set_points_smoothly(path_pts)
        dashed = look.dashed_lines if dashed is None else dashed
        route = Route()
        shown = DashedVMobject(line, num_dashes=max(12, int(line.get_arc_length() / 0.22)), dashed_ratio=0.62) if dashed else line
        route.add(shown)
        route.name_part("line", shown)
        route.path = line
        if dots:
            ds = VGroup(*(Dot(p, radius=0.07, color=c).set_stroke(look.bg, width=3, background=True) for p in pts))
            route.add(ds)
            route.name_part("stops", ds)
        if arrow_end and len(pts) > 1:
            from manim import ArrowTriangleFilledTip
            end = line.point_from_proportion(1)
            before = line.point_from_proportion(0.985)
            ang = np.arctan2(*(end - before)[1::-1])
            tip = ArrowTriangleFilledTip(color=c, width=0.22, length=0.22).rotate(ang).move_to(end)
            route.add(tip)
            route.name_part("tip", tip)
        return route

    def empire(self, name: str, year: int, color: str | None = None, opacity: float = 0.55,
               outline: bool = True) -> Piece:
        """A state's extent as it stood in `year` (historical borders: "Song", "Ming Chinese Empire", "Mughal
        Empire", "Tokugawa Shogunate"...), shaded over the map."""
        _engine()
        import historical
        found = historical.empire(name, year)
        if not found:
            raise KeyError(f"no state {name!r} on the map of {historical.nearest(year)}; it has: "
                           f"{', '.join(historical.names(year))[:800]}")
        geom, real, y = found
        c = color or self.look.accent
        mob = self._shape_mob(geom, c, c if outline else c, 2.5 if outline else 0, opacity)
        p = Piece(mob)
        p.name_part("shape", mob)
        p.state_name, p.year = real, y
        p.entering("fade")
        return p

    def area(self, lonlats, color: str | None = None, opacity: float = 0.45) -> Piece:
        """A region drawn from (lon, lat) corners (a sea lane, a province, a zone of influence)."""
        c = color or self.look.accent
        poly = Polygon(*[self.point(lo, la) for lo, la in lonlats], stroke_color=c, stroke_width=2.5, fill_color=c,
                       fill_opacity=opacity)
        p = Piece(poly)
        p.entering("fade")
        return p

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 1.6
        land = self.part("land")
        parts = [FadeIn(self.part("sea"), run_time=run * 0.4)]
        if self.look.name == "blueprint":
            from manim import DrawBorderThenFill
            parts.append(LaggedStart(*(DrawBorderThenFill(m, run_time=run) for m in land), lag_ratio=0.02))
        else:
            parts.append(LaggedStart(*(FadeIn(m, scale=0.98, run_time=run * 0.6) for m in land), lag_ratio=0.03))
        extra = [p for p in ("graticule", "frame") if p in self.parts]
        parts += [FadeIn(self.part(p), run_time=run * 0.5) for p in extra]
        if len(self.labels):
            parts.append(FadeIn(self.labels, run_time=run * 0.5))
        return owned(self, AnimationGroup(*parts))


class Route(Piece):
    enter_kind = "line"

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 2.5
        from .motion import later
        anims = [Create(self.part("line"), run_time=run, rate_func=lambda t: t)]
        if "stops" in self.parts:
            stops = self.part("stops")
            n = len(stops)
            for i, d in enumerate(stops):
                anims.append(later(FadeIn(d, scale=0.3, run_time=0.25), run * i / max(1, n - 1) - (0.25 if i else 0)))
        if "tip" in self.parts:
            anims.append(later(FadeIn(self.part("tip"), run_time=0.15), run - 0.15))
        return owned(self, AnimationGroup(*anims))

    def travel(self, run: float = 3.0, marker=None, color: str | None = None):
        """The route drawn while a marker (a dot, or any mobject such as an icon) moves along it."""
        from manim import MoveAlongPath
        from .motion import owned
        m = marker or Dot(radius=0.12, color=color or L().ink)
        m.move_to(self.path.point_from_proportion(0))
        return AnimationGroup(self.appear(run=run), MoveAlongPath(m, self.path, run_time=run, rate_func=lambda t: t))
