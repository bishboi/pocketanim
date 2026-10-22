"""The default look's reference frames for the video agent (style-vox.jpg): six stills in the manner of a Vox explainer,
drawn here in Manim (no frames from anyone's videos), one for each move such a video makes:

    Map        a region in muted tones, the one country in red, a cut-paper callout on a leader line, a dotted route
    Collage    a halftone archival-style photo cut out with a torn border and tape, on dark card, circled in red
    Data       one big number, a bar chart with the bar that matters in red, a source line
    Document   a typed page, a sentence highlighted, a word circled, the line pulled out and enlarged
    Timeline   dated stops on a line, the card for the one that matters lifted and coloured
    Flow       things and the flows between them, labelled on the arrows

    python harness_v2/engine/agent/style_frames.py     # renders the six and writes style-vox.jpg beside this file

Fonts: Oswald (headlines), Playfair Display (kickers), Source Sans 3 (labels), IBM Plex Mono (the typed page).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from manim import *  # noqa: F403
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
TEX = HERE / ".style_textures"

PAPER, INK, RED, YELLOW, MUTED = "#EFE6D4", "#1F1E1C", "#E23B2E", "#FFD23F", "#8C8273"
LAND, LAND_EDGE, CARD, TEAL, NAVY = "#D9CDB3", "#B7AA8E", "#FBF8F1", "#2E7D7A", "#1C2B3A"
HEAD, SERIF, SANS, MONO = "Oswald", "Playfair Display", "Source Sans 3", "IBM Plex Mono"


# ---------------------------------------------------------------- textures (made once, beside this file)

def _paper(path: Path, base=(239, 230, 212), dark=False) -> Path:
    if path.exists():
        return path
    rng = np.random.default_rng(7 if not dark else 11)
    w, h = 1600, 900
    im = np.ones((h, w, 3)) * np.array(base, dtype=float)
    im += rng.normal(0, 5 if not dark else 4, (h, w, 1))
    # Fibres: faint strokes.
    fib = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(fib)
    for _ in range(900 if not dark else 500):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        a = rng.uniform(0, np.pi)
        ln = rng.uniform(6, 30)
        d.line([(x, y), (x + ln * np.cos(a), y + ln * np.sin(a))], fill=int(rng.uniform(20, 60)), width=1)
    fib = np.asarray(fib.filter(ImageFilter.GaussianBlur(0.6)), dtype=float)[..., None] / 255.0
    im -= fib * (18 if not dark else -14)
    # Vignette.
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    im *= (1 - 0.16 * np.clip(r - 0.35, 0, 1) ** 1.6)[..., None]
    Image.fromarray(np.clip(im, 0, 255).astype("uint8")).save(path)
    return path


def _halftone_photo(path: Path) -> Path:
    """An archival-looking photo: a harbour with a steamship, drawn, then halftoned in sepia with a torn white border."""
    if path.exists():
        return path
    w, h = 900, 620
    pic = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(pic)
    for y in range(h):                                   # sky to sea
        d.line([(0, y), (w, y)], fill=int(205 - 70 * (y / h) ** 1.4))
    d.rectangle([0, 400, w, h], fill=95)                 # water
    for k in range(40):
        y = 410 + k * 5
        d.line([(0, y), (w, y)], fill=110 if k % 2 else 80)
    d.polygon([(0, 400), (180, 330), (320, 360), (470, 300), (620, 350), (900, 320), (900, 400)], fill=120)   # hills
    d.polygon([(250, 470), (640, 470), (600, 520), (290, 520)], fill=25)                                       # hull
    d.rectangle([330, 420, 560, 470], fill=45)                                                                 # deck
    d.rectangle([420, 330, 450, 420], fill=30)                                                                 # funnel
    for x in (360, 520):
        d.line([(x, 250), (x, 470)], fill=20, width=6)                                                         # masts
        d.line([(x - 50, 300), (x + 50, 300)], fill=20, width=4)
    d.ellipse([400, 250, 470, 320], fill=150)                                                                  # smoke
    d.ellipse([430, 200, 520, 280], fill=165)
    d.polygon([(40, 520), (120, 520), (110, 540), (50, 540)], fill=30)                                         # a boat
    pic = pic.filter(ImageFilter.GaussianBlur(2))
    a = np.asarray(pic, dtype=float) / 255.0
    # Halftone dots on a 7 px grid.
    cell = 7
    out = Image.new("L", (w, h), 245)
    od = ImageDraw.Draw(out)
    for cy in range(0, h, cell):
        for cx in range(0, w, cell):
            v = a[min(h - 1, cy + cell // 2), min(w - 1, cx + cell // 2)]
            rad = (1 - v) * cell * 0.72
            if rad > 0.3:
                od.ellipse([cx + cell / 2 - rad, cy + cell / 2 - rad, cx + cell / 2 + rad, cy + cell / 2 + rad], fill=40)
    sep = np.asarray(out, dtype=float)[..., None] / 255.0
    rgb = (sep * np.array([238, 225, 196]) + (1 - sep) * np.array([62, 46, 32])).astype("uint8")
    photo = Image.fromarray(rgb)
    # Torn white border.
    border = 34
    full = Image.new("RGBA", (w + 2 * border, h + 2 * border), (0, 0, 0, 0))
    mask = Image.new("L", full.size, 0)
    md = ImageDraw.Draw(mask)
    rng = np.random.default_rng(3)
    pts = []
    W, H = full.size
    for x in np.linspace(0, W, 60):
        pts.append((x, rng.uniform(0, 9)))
    for y in np.linspace(0, H, 44):
        pts.append((W - rng.uniform(0, 9), y))
    for x in np.linspace(W, 0, 60):
        pts.append((x, H - rng.uniform(0, 9)))
    for y in np.linspace(H, 0, 44):
        pts.append((rng.uniform(0, 9), y))
    md.polygon(pts, fill=255)
    paper = Image.new("RGBA", full.size, (246, 241, 230, 255))
    paper.paste(photo, (border, border))
    full.paste(paper, (0, 0), mask)
    full.save(path)
    return path


def _bg(name: str, dark=False, base=None):
    p = _paper(TEX / f"{name}.png", base or ((48, 46, 44) if dark else (239, 230, 212)), dark)
    return ImageMobject(str(p)).set(width=14.25, height=8.02).set_z_index(-100)


# ---------------------------------------------------------------- pieces

def head(text, size=60, color=INK, mark=YELLOW):
    words = Text(text, font=HEAD, weight=BOLD, font_size=size, color=color)
    bar = Rectangle(width=words.width + 0.34, height=words.height * 0.52, fill_color=mark, fill_opacity=1, stroke_width=0)
    bar.move_to(words.get_bottom() + UP * words.height * 0.3)
    return VGroup(bar, words)


def kicker(text, color=RED, size=28):
    return Text(text, font=SERIF, slant=ITALIC, font_size=size, color=color)


def tag(text, size=26, fill=CARD, color=INK, sub=None):
    words = Text(text, font=SANS, weight=BOLD, font_size=size, color=color)
    body = VGroup(words)
    if sub:
        body.add(Text(sub, font=SANS, font_size=size * 0.72, color=MUTED).next_to(words, DOWN, buff=0.08, aligned_edge=LEFT))
    box = Rectangle(width=body.width + 0.36, height=body.height + 0.26, fill_color=fill, fill_opacity=1, stroke_color=INK, stroke_width=2)
    box.move_to(body)
    shadow = box.copy().set_fill(INK, 1).set_stroke(width=0).shift(RIGHT * 0.07 + DOWN * 0.07)
    return VGroup(shadow, box, body)


def leader(card, point, side=LEFT):
    end = card.get_edge_center(side)
    return VGroup(Line(end, point, color=INK, stroke_width=2.2), Dot(point, radius=0.06, color=INK))


def source(text):
    return Text(text, font=SANS, font_size=17, color=MUTED).to_corner(DL, buff=0.35)


def hand_circle(mob, color=RED, pad=0.18, width=5):
    w, h = mob.width / 2 + pad, mob.height / 2 + pad
    t = np.linspace(0.15, 2 * np.pi + 0.55, 120)
    pts = [mob.get_center() + np.array([w * np.cos(a) * (1 + 0.03 * np.sin(5 * a)), h * np.sin(a) * (1 + 0.05 * np.cos(3 * a)), 0]) for a in t]
    return VMobject(stroke_color=color, stroke_width=width).set_points_smoothly(pts)


def countries(names, box=(60, 0, 175, 70)):
    import cartopy.io.shapereader as shp
    from shapely.geometry import box as sbox

    out = {}
    reader = shp.Reader(shp.natural_earth(resolution="50m", category="cultural", name="admin_0_countries"))
    for rec in reader.records():
        n = rec.attributes["ADMIN"]
        if n not in names:
            continue
        g = rec.geometry.intersection(sbox(*box)).simplify(0.06, preserve_topology=True)
        parts = list(g.geoms) if hasattr(g, "geoms") else [g]
        out[n] = [list(p.exterior.coords) for p in parts if p.geom_type == "Polygon" and p.area > 0.02]
    return out


class Proj:
    def __init__(self, lon0, lat0, scale, shift=ORIGIN):
        self.lon0, self.lat0, self.s, self.shift = lon0, lat0, scale, np.array(shift)

    def __call__(self, lon, lat):
        k = np.cos(np.radians(self.lat0))
        return np.array([(lon - self.lon0) * k * self.s, (lat - self.lat0) * self.s, 0]) + self.shift


def shape(ring, proj, fill, edge=LAND_EDGE, width=1.2):
    return Polygon(*[proj(x, y) for x, y in ring], fill_color=fill, fill_opacity=1, stroke_color=edge, stroke_width=width)


# ---------------------------------------------------------------- frames

class FrameMap(Scene):
    def construct(self):
        self.add(_bg("paper"))
        names = ["China", "Japan", "South Korea", "North Korea", "Mongolia", "Russia", "Taiwan", "Philippines", "Vietnam", "Laos",
                 "Myanmar", "Thailand", "India", "Kazakhstan", "Nepal", "Bhutan", "Bangladesh", "Cambodia"]
        geo = countries(names)
        proj = Proj(128, 37, 0.21, shift=RIGHT * 1.0 + DOWN * 0.4)
        others = VGroup(*[shape(r, proj, LAND) for n, rs in geo.items() if n != "Japan" for r in rs])
        japan = VGroup(*[shape(r, proj, RED, INK, 1.4) for r in geo["Japan"]])
        self.add(others, japan)
        for name, lon, lat in (("CHINA", 108, 33), ("KOREA", 127.6, 38.6), ("RUSSIA", 133, 49.5)):
            self.add(Text(name, font=HEAD, font_size=26 if name != "CHINA" else 40, color=MUTED).move_to(proj(lon, lat)))
        card = tag("JAPAN", 30, sub="33 million people, 1853").move_to(RIGHT * 5.0 + UP * 1.2)
        self.add(leader(card, proj(139.5, 36.5)), card)
        start = proj(156, 27)
        end = proj(140.2, 35.1)
        route = DashedVMobject(ArcBetweenPoints(start, end, angle=-0.6, color=INK, stroke_width=3), num_dashes=22)
        arrow = Arrow(end + RIGHT * 0.35 + DOWN * 0.18, end, buff=0, color=INK, stroke_width=3, max_tip_length_to_length_ratio=0.6)
        self.add(route, arrow)
        self.add(tag("Perry's ships, 1853", 22, fill=YELLOW).next_to(start, DOWN, buff=0.12).shift(LEFT * 0.6))
        self.add(head("THE OPENING OF JAPAN", 58).to_corner(UL, buff=0.5))
        self.add(kicker("Edo Bay, July 1853").next_to(self.mobjects[-1], DOWN, buff=0.18, aligned_edge=LEFT))
        self.add(source("Map: Natural Earth. Borders are today's."))


class FrameCollage(Scene):
    def construct(self):
        self.add(_bg("card", dark=True))
        photo = ImageMobject(str(_halftone_photo(TEX / "harbour.png"))).set(height=4.7).rotate(-0.06).move_to(LEFT * 1.6 + DOWN * 0.45)
        shadow = Rectangle(width=photo.width * 0.97, height=photo.height * 0.96, fill_color=BLACK, fill_opacity=0.45, stroke_width=0)
        shadow.rotate(-0.06).move_to(photo).shift(RIGHT * 0.12 + DOWN * 0.12)
        tape = Rectangle(width=1.5, height=0.42, fill_color="#E8DDBE", fill_opacity=0.85, stroke_width=0).rotate(0.25).move_to(photo.get_corner(UL) + RIGHT * 0.5 + DOWN * 0.12)
        tape2 = tape.copy().rotate(-0.5).move_to(photo.get_corner(UR) + LEFT * 0.5 + DOWN * 0.1)
        self.add(shadow, photo, tape, tape2)
        ship = Circle(radius=0.01).move_to(photo.get_center() + RIGHT * 0.05 + DOWN * 0.55)
        ring = hand_circle(Rectangle(width=2.0, height=1.25).move_to(ship), width=6)
        self.add(ring)
        note = Text("the 'black ships'", font=SERIF, slant=ITALIC, font_size=30, color=YELLOW).move_to(RIGHT * 3.6 + DOWN * 1.6)
        self.add(note, CurvedArrow(note.get_left() + LEFT * 0.1, ring.get_right() + RIGHT * 0.05, angle=-0.6, color=YELLOW, stroke_width=4))
        title = Text("A CLOSED COUNTRY", font=HEAD, weight=BOLD, font_size=64, color=CARD).to_corner(UR, buff=0.55).shift(DOWN * 0.15)
        self.add(title, Line(title.get_corner(DL) + DOWN * 0.12, title.get_corner(DR) + DOWN * 0.12, color=RED, stroke_width=8))
        self.add(Text("for more than 200 years", font=SERIF, slant=ITALIC, font_size=30, color="#CFC6B4").next_to(title, DOWN, buff=0.35, aligned_edge=RIGHT))
        self.add(tag("Edo, 1860s", 22).next_to(photo, DOWN, buff=0.2, aligned_edge=LEFT).shift(RIGHT * 0.3))


class FrameData(Scene):
    def construct(self):
        self.add(_bg("paper"))
        big = Text("73%", font=HEAD, weight=BOLD, font_size=150, color=RED).to_edge(LEFT, buff=0.8).shift(UP * 0.6)
        self.add(big)
        cap = Text("of Japan is\nmountains or hills", font=SANS, weight=BOLD, font_size=34, color=INK, line_spacing=0.8).next_to(big, DOWN, buff=0.15, aligned_edge=LEFT)
        self.add(cap)
        vals = [("Japan", 73), ("Korea", 70), ("Italy", 35), ("France", 28), ("UK", 15)]
        base = DOWN * 2.4 + RIGHT * 1.2
        axis = Line(base + LEFT * 0.2, base + RIGHT * 5.4, color=INK, stroke_width=2)
        self.add(axis)
        for k, (n, v) in enumerate(vals):
            x = base + RIGHT * (0.5 + k * 1.1)
            bar = Rectangle(width=0.72, height=v / 16, fill_color=RED if k == 0 else "#BFB4A0", fill_opacity=1, stroke_width=0)
            bar.move_to(x + UP * bar.height / 2)
            self.add(bar, Text(n, font=SANS, font_size=22, color=INK).next_to(x, DOWN, buff=0.15),
                     Text(f"{v}%", font=HEAD, font_size=26, color=RED if k == 0 else MUTED).next_to(bar, UP, buff=0.1))
        self.add(head("STEEP COUNTRY", 46).to_corner(UR, buff=0.55))
        self.add(source("Share of land area in mountains or hills. Illustrative figures for this style frame."))


class FrameDocument(Scene):
    def construct(self):
        self.add(_bg("paper", base=(216, 205, 182)))
        page = Rectangle(width=6.2, height=7.8, fill_color="#FBF7EC", fill_opacity=1, stroke_width=0)
        lines = ["TREATY OF PEACE AND AMITY", "", "Article I. There shall be a perfect,", "permanent and universal peace...",
                 "", "Article II. The port of Simoda", "and the port of Hakodade are", "granted by the Japanese as ports",
                 "for the reception of American ships,", "where they can be supplied with", "wood, water, provisions and coal.",
                 "", "Article III. Whenever ships of the", "United States are thrown or wrecked..."]
        top = page.get_top() + DOWN * 0.75
        rows = VGroup()
        for k, text in enumerate(lines):
            if not text:
                continue
            row = Text(text, font=MONO, font_size=18, color="#2B2A27", weight=BOLD if k == 0 else NORMAL)
            row.move_to(top + DOWN * 0.42 * k, aligned_edge=LEFT).set_x(page.get_left()[0] + 0.5 + row.width / 2)
            row.key = k
            rows.add(row)
        marked = [r for r in rows if 5 <= r.key <= 8]
        hl = VGroup(*[Rectangle(width=r.width + 0.12, height=0.34, fill_color=YELLOW, fill_opacity=0.6, stroke_width=0).move_to(r) for r in marked])
        circled = next(r for r in rows if r.key == 5)
        ring = hand_circle(Rectangle(width=1.9, height=0.3).move_to(circled.get_right() + LEFT * 0.95), width=4)
        sheet = Group(page, hl, rows, ring).rotate(0.035).move_to(LEFT * 2.6 + DOWN * 0.1)
        shade = page.copy().set_fill(BLACK, 0.25).shift(RIGHT * 0.12 + DOWN * 0.12)
        self.add(shade, sheet)
        pull = VGroup(Text("“the port of Simoda", font=SERIF, slant=ITALIC, font_size=38, color=INK),
                      Text("and the port of Hakodade", font=SERIF, slant=ITALIC, font_size=38, color=INK),
                      Text("are granted...”", font=SERIF, slant=ITALIC, font_size=38, color=INK)).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        card = Rectangle(width=pull.width + 0.6, height=pull.height + 0.6, fill_color=CARD, fill_opacity=1, stroke_color=INK, stroke_width=2).move_to(pull)
        grp = VGroup(card.copy().set_fill(INK, 1).set_stroke(width=0).shift(RIGHT * 0.08 + DOWN * 0.08), card, pull).move_to(RIGHT * 3.75 + UP * 1.4)
        self.add(Line(hl[1].get_right() + RIGHT * 0.05, grp.get_left(), color=RED, stroke_width=3), grp)
        self.add(kicker("Convention of Kanagawa, 1854", size=30).next_to(grp, DOWN, buff=0.35, aligned_edge=LEFT))
        self.add(head("TWO PORTS OPEN", 44).next_to(grp, DOWN, buff=1.3, aligned_edge=LEFT))


class FrameTimeline(Scene):
    def construct(self):
        self.add(_bg("paper"))
        self.add(head("FROM CLOSED TO EMPIRE", 52).to_corner(UL, buff=0.5))
        line = Line(LEFT * 6.3 + DOWN * 0.4, RIGHT * 6.3 + DOWN * 0.4, color=INK, stroke_width=4)
        self.add(line)
        stops = [(1853, "Black ships", "Perry arrives"), (1858, "Unequal treaties", "ports opened"), (1868, "Meiji Restoration", "the emperor restored"),
                 (1889, "Constitution", "a parliament"), (1905, "War with Russia", "Japan wins")]
        x0, x1 = -5.6, 5.6
        for k, (year, title, sub) in enumerate(stops):
            x = x0 + (x1 - x0) * (year - 1853) / (1905 - 1853)
            p = np.array([x, -0.4, 0])
            key = year == 1868
            self.add(Dot(p, radius=0.13 if key else 0.09, color=RED if key else INK))
            self.add(Text(str(year), font=HEAD, font_size=34 if key else 28, color=RED if key else INK).next_to(p, DOWN, buff=0.22))
            card = tag(title, 24 if key else 21, fill=YELLOW if key else CARD, sub=sub)
            up = k % 2 == 0
            card.next_to(p, UP if up else DOWN, buff=1.0 if up else 1.05)
            if not up:
                card.shift(DOWN * 0.35)
            if key:
                card.scale(1.12)
            self.add(Line(p, card.get_bottom() if up else card.get_top(), color=MUTED, stroke_width=2), card)
        self.add(source("Each stop is a turn in the same story."))


class FrameFlow(Scene):
    def construct(self):
        self.add(_bg("navy", base=(30, 44, 58), dark=True))
        self.add(Text("WHAT CROSSED THE SEA", font=HEAD, weight=BOLD, font_size=54, color=CARD).to_corner(UL, buff=0.55))
        nodes = {"CHINA": LEFT * 4.8 + DOWN * 1.2, "JAPAN": UP * 0.3, "THE WEST": RIGHT * 4.8 + DOWN * 1.2}
        made = {}
        for name, at in nodes.items():
            disc = Circle(radius=1.0, fill_color=RED if name == "JAPAN" else "#E9E1CF", fill_opacity=1, stroke_color=CARD, stroke_width=4).move_to(at)
            label = Text(name, font=HEAD, weight=BOLD, font_size=30, color=CARD if name == "JAPAN" else INK).move_to(disc)
            made[name] = VGroup(disc, label)

        def flow(a, b, text, color, lane=0.0, bend=-0.35):
            """An arrow from rim to rim, set `lane` to the side of the line between the two (so a flow and its return
            run side by side), its label beside its middle, outside."""
            pa, pb = made[a][0].get_center(), made[b][0].get_center()
            u = (pb - pa) / np.linalg.norm(pb - pa)
            n = np.array([-u[1], u[0], 0])
            start = pa + u * 1.1 + n * lane
            end = pb - u * 1.1 + n * lane
            arr = CurvedArrow(start, end, angle=bend, color=color, stroke_width=6, tip_length=0.28)
            mid = arr.point_from_proportion(0.5)
            out = n if bend < 0 else -n
            lab = Text(text, font=SANS, weight=BOLD, font_size=26, color=color)
            lab.move_to(mid + out * (0.3 + lab.height / 2 + abs(out[0]) * lab.width / 2))
            self.add(arr, lab)

        flow("CHINA", "JAPAN", "writing, silk, tea", YELLOW)
        flow("THE WEST", "JAPAN", "steam, rifles, rails", "#9AD1CC", lane=0.28)
        flow("JAPAN", "THE WEST", "silk, porcelain", "#F4A79D", lane=0.28)
        for m in made.values():
            self.add(m)
        self.add(Text("Japan took from both, and remade what it took.", font=SERIF, slant=ITALIC, font_size=30, color="#CFC6B4").to_edge(DOWN, buff=0.5))


FRAMES = ["FrameMap", "FrameCollage", "FrameData", "FrameDocument", "FrameTimeline", "FrameFlow"]


def main() -> int:
    TEX.mkdir(exist_ok=True)
    out = HERE / ".style_render"
    shots = []
    for name in FRAMES:
        subprocess.run([sys.executable, "-m", "manim", "render", "-s", "--format", "png", "-r", "1280,720", "--disable_caching",
                        "--media_dir", str(out), "-v", "WARNING", __file__, name], check=True)
        shots.append(next(out.rglob(f"{name}*.png")))
    tile_w, tile_h, gap = 960, 540, 12
    sheet = Image.new("RGB", (2 * tile_w + 3 * gap, 3 * tile_h + 4 * gap), (18, 18, 18))
    for k, shot in enumerate(shots):
        im = Image.open(shot).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS)
        sheet.paste(im, (gap + (k % 2) * (tile_w + gap), gap + (k // 2) * (tile_h + gap)))
    sheet.save(HERE / "style-vox.jpg", quality=88)
    print(HERE / "style-vox.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
