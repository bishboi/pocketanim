# A reference chapter for the video agent: built in free Manim, Vox-like (review/agent-trial/japan_ch4.py). Read it for
# the craft (drawn maps and zooms, staggered reveals, cut-paper labels, highlighter headlines); it is not a template.
"""Chapter 4 of "Paths to Modernisation" ("Japan: Islands and Everyday Life"), built by hand in raw Manim, the way a
free agent would: no lecture engine, no primitives -- only Manim, Natural Earth for the maps, and a Vox-style look
(paper grain, condensed headlines, yellow highlighter, cut-paper labels, a bold small palette).

    manim -qm japan_ch4.py JapanChapter4            # preview video
    python harness_v2/engine/tools/export_scene.py japan_ch4.py JapanChapter4 out/   # the phone's program (tier 1)

The narration is the chapter's 22 lines. With no voice here, each line lasts as long as it would be said (about
0.42 s a word); `at(word)` waits until a word of the current line would be said, so each thing lands on its words.
"""

import math
from pathlib import Path

import numpy as np
from manim import *  # noqa: F403

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

# ---------------------------------------------------------------- the look -------------------------------------------
PAPER = "#F1E9DA"
INK = "#1B1B1B"
LAND = "#E2D6BF"
LAND_EDGE = "#B9A98C"
MUTED = "#8A7E6B"
RED = "#E5383B"
YELLOW = "#FFD23F"
TEAL = "#2A9D8F"
BLUE = "#3D6FA3"
ORANGE = "#F08A3C"
CARD = "#FFFDF7"

HEAD = "Oswald"
SERIF = "Playfair Display"
SANS = "Source Sans 3"
DEVA = "Noto Sans Devanagari"

LINES = [
    "China के विशाल mainland के सामने Japan एक string of islands है।",
    "Map पर north में Hokkaido, बीच में Honshu, और south की तरफ Shikoku तथा Kyushu पहचानिए।",
    "ये Japan की चार सबसे बड़ी islands हैं।",
    "सबसे south की तरफ Okinawan island chain है, लगभग उसी latitude पर जिस पर Bahamas हैं।",
    "Latitude से यहाँ north-south position compare कर रहे हैं, दूरी नहीं।",
    "Okinawa को देखकर पूरे Japan का climate एक जैसा मान लेना गलत होगा।",
    "Main islands के land area का 50 per cent से भी ज़्यादा हिस्सा mountainous है।",
    "यानी map पर जितनी ज़मीन दिखाई देती है, उसका आधे से ज़्यादा हिस्सा पहाड़ी है।",
    "Japan एक बहुत active earthquake zone में भी है।",
    "अब बताइए, घर बनाने वाला इन conditions को ignore कर सकता है?",
    "नहीं, geography architecture को भी shape करती है।",
    "Building सिर्फ देखने में अच्छी हो, इतना काफी नहीं; उसे अपनी जगह की conditions के हिसाब से बनाना पड़ता है।",
    "Population largely Japanese है, लेकिन Ainu की छोटी minority भी है।",
    "साथ में Koreans भी हैं, जिनमें वे लोग शामिल हैं जिन्हें Korea के Japanese colony होने के दौरान ज़बरदस्ती labour के लिए लाया गया था।",
    "यहाँ एक important फर्क याद रखिए: कुछ लोगों का बसना अपनी पसंद से नहीं, colonial force से हुआ था।",
    "Population की कहानी में power का सवाल भी छिपा होता है।",
    "Japan में animal rearing की कोई मजबूत tradition नहीं थी।",
    "Rice staple crop था, और protein का major source fish था।",
    "Raw fish से जुड़े dishes, जैसे sashimi और sushi, आज दुनिया भर में popular हैं और healthy माने जाते हैं।",
    "यानी geography की बात आखिर kitchen तक आ गई।",
    "अब इस island society की politics देखते हैं।",
    "बाहर से emperor दिखाई देता है, लेकिन क्या असली power भी हमेशा उसी के पास थी?",
]
WORD = 0.42          # seconds a word, as the lecture engine estimates a line it cannot hear


def paper_texture() -> Path:
    """A paper grain, made once: warm off-white, fibres and a soft vignette (Vox's paper)."""
    out = ASSETS / "paper.png"
    if out.exists():
        return out
    from PIL import Image, ImageFilter

    ASSETS.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    w, h = 1280, 720
    base = np.array([241, 233, 218], dtype=np.float32)
    noise = rng.normal(0, 7, (h, w, 1)).astype(np.float32)
    fibres = np.array(Image.fromarray((rng.random((h // 4, w // 4)) * 255).astype(np.uint8))
                      .resize((w, h)).filter(ImageFilter.GaussianBlur(2)), dtype=np.float32)[..., None]
    yy, xx = np.mgrid[0:h, 0:w]
    vignette = 1 - 0.18 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    img = (base + noise + (fibres - 128) * 0.06) * vignette[..., None]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)
    return out


# ---------------------------------------------------------------- geography ------------------------------------------
def countries(names=None, min_area=0.0, tolerance=0.05):
    """{name: [shapely polygons]} from Natural Earth's countries, simplified."""
    import cartopy.io.shapereader as shp
    from shapely.geometry import MultiPolygon

    path = shp.natural_earth(resolution="10m", category="cultural", name="admin_0_countries")
    out = {}
    for rec in shp.Reader(path).records():
        name = rec.attributes["NAME"]
        if names is not None and name not in names:
            continue
        geom = rec.geometry
        polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        polys = [p.simplify(tolerance, preserve_topology=True) for p in polys if p.area >= min_area]
        if polys:
            out[name] = polys
    return out


class Projection:
    """Equirectangular, squeezed by the cosine of a middle latitude, centred and scaled onto the frame."""

    def __init__(self, lon0, lat0, scale, shift=ORIGIN, wrap=None):
        self.lon0, self.lat0, self.scale, self.shift = lon0, lat0, scale, np.array(shift, dtype=float)
        self.k = math.cos(math.radians(lat0))
        self.wrap = wrap

    def __call__(self, lon, lat):
        if self.wrap is not None and lon < self.wrap:
            lon += 360
        return np.array([(lon - self.lon0) * self.k * self.scale, (lat - self.lat0) * self.scale, 0]) + self.shift


def shape(poly, proj, fill, edge=LAND_EDGE, width=1.2, opacity=1.0):
    pts = [proj(x, y) for x, y in list(poly.exterior.coords)]
    m = Polygon(*pts, stroke_color=edge, stroke_width=width, fill_color=fill, fill_opacity=opacity)
    return m


# ---------------------------------------------------------------- pieces ---------------------------------------------
def headline(text, size=60, color=INK, mark=YELLOW):
    """A condensed headline with the yellow highlighter swept behind it."""
    words = Text(text.upper(), font=HEAD, weight=BOLD, font_size=size, color=color)
    bar = Rectangle(width=words.width + 0.35, height=words.height * 0.55, stroke_width=0,
                    fill_color=mark, fill_opacity=1).move_to(words.get_bottom() + UP * words.height * 0.3)
    bar.set_z_index(1)
    words.set_z_index(2)
    return VGroup(bar, words)


def sweep_in(head, run=0.6):
    bar, words = head
    return Succession(GrowFromEdge(bar, LEFT, run_time=run * 0.5, rate_func=rush_from),
                      FadeIn(words, shift=UP * 0.15, run_time=run * 0.5))


def kicker(text, color=RED):
    return Text(text, font=SERIF, slant=ITALIC, font_size=26, color=color)


def tag(text, color=INK, fill=CARD, size=26):
    """A cut-paper label: card, hard shadow, words."""
    words = Text(text, font=SANS, weight=SEMIBOLD, font_size=size, color=color)
    card = RoundedRectangle(corner_radius=0.06, width=words.width + 0.4, height=words.height + 0.28,
                            stroke_color=INK, stroke_width=1.6, fill_color=fill, fill_opacity=1)
    shadow = card.copy().set_fill(INK, 1).set_stroke(width=0).shift(RIGHT * 0.06 + DOWN * 0.06)
    words.move_to(card)
    return VGroup(shadow, card, words)


def inside(m, margin=0.35, bottom=1.25):
    """Moved fully onto the frame (and above the caption band)."""
    w, h = config.frame_width / 2 - margin, config.frame_height / 2 - margin
    dx = min(0, w - m.get_right()[0]) + max(0, -w - m.get_left()[0])
    dy = min(0, h - m.get_top()[1]) + max(0, -h + bottom - m.get_bottom()[1])
    return m.shift(RIGHT * dx + UP * dy)


def leader(label, point, side=RIGHT, gap=0.15):
    """A label placed beside a point (kept on the frame), with a line and a dot to it."""
    label.next_to(point, side, buff=1.0)
    inside(label)
    end = label.get_edge_center(-side) + (-side) * gap
    line = Line(point, end, stroke_color=INK, stroke_width=2)
    dot = Dot(point, radius=0.06, color=INK)
    return VGroup(line, dot, label)


def caption(text):
    words = Text(text, font=DEVA, font_size=24, color=CARD, line_spacing=0.8)
    if words.width > 12.2:
        cut = len(text) // 2
        cut = text.rfind(" ", 0, cut + 10) if text.rfind(" ", 0, cut + 10) > 0 else cut
        words = Text(text[:cut] + "\n" + text[cut + 1:], font=DEVA, font_size=24, color=CARD, line_spacing=0.8)
    box = RoundedRectangle(corner_radius=0.08, width=min(13.4, words.width + 0.6), height=words.height + 0.35,
                           stroke_width=0, fill_color=INK, fill_opacity=0.92)
    group = VGroup(box, words.move_to(box)).to_edge(DOWN, buff=0.25)
    group.set_z_index(50)
    return group


def rice_bowl():
    bowl = ArcBetweenPoints(LEFT * 0.9, RIGHT * 0.9, angle=PI, stroke_width=0, fill_color=RED, fill_opacity=1)
    bowl = VGroup(Polygon(LEFT * 0.9, RIGHT * 0.9, RIGHT * 0.55 + DOWN * 0.6, LEFT * 0.55 + DOWN * 0.6,
                          stroke_width=0, fill_color=RED, fill_opacity=1))
    rice = Ellipse(width=1.8, height=0.55, stroke_width=0, fill_color=CARD, fill_opacity=1).shift(UP * 0.02)
    grains = VGroup(*[Ellipse(width=0.12, height=0.06, stroke_width=0, fill_color="#E9E2D0", fill_opacity=1)
                      .move_to([x, y, 0]).rotate(a) for x, y, a in
                      [(-0.5, 0.08, 0.3), (-0.2, 0.15, -0.4), (0.15, 0.05, 0.2), (0.45, 0.12, -0.2), (0.0, -0.05, 0.6)]])
    rim = Line(LEFT * 0.92, RIGHT * 0.92, stroke_color=INK, stroke_width=3)
    return VGroup(rice, grains, bowl, rim)


def fish(color=BLUE):
    body = Ellipse(width=1.7, height=0.7, stroke_color=INK, stroke_width=2.5, fill_color=color, fill_opacity=1)
    tail = Polygon(RIGHT * 0.8, RIGHT * 1.3 + UP * 0.35, RIGHT * 1.3 + DOWN * 0.35, stroke_color=INK,
                   stroke_width=2.5, fill_color=color, fill_opacity=1)
    eye = Dot(LEFT * 0.5 + UP * 0.08, radius=0.06, color=INK)
    gill = Arc(radius=0.25, start_angle=-PI / 3, angle=2 * PI / 3, stroke_color=INK, stroke_width=2).shift(LEFT * 0.35)
    return VGroup(tail, body, eye, gill)


def sushi():
    rice = RoundedRectangle(corner_radius=0.18, width=1.5, height=0.5, stroke_color=INK, stroke_width=2.5,
                            fill_color=CARD, fill_opacity=1)
    top = RoundedRectangle(corner_radius=0.18, width=1.7, height=0.4, stroke_color=INK, stroke_width=2.5,
                           fill_color=ORANGE, fill_opacity=1).next_to(rice, UP, buff=-0.12)
    stripes = VGroup(*[Line(top.get_left() + RIGHT * (0.35 + 0.35 * i) + DOWN * 0.15,
                            top.get_left() + RIGHT * (0.5 + 0.35 * i) + UP * 0.15, stroke_color=CARD, stroke_width=3)
                       for i in range(4)])
    return VGroup(rice, top, stripes)


def house():
    walls = Rectangle(width=2.0, height=1.3, stroke_color=INK, stroke_width=3, fill_color=CARD, fill_opacity=1)
    roof = Polygon(walls.get_corner(UL) + LEFT * 0.35, walls.get_corner(UR) + RIGHT * 0.35,
                   walls.get_top() + UP * 1.0, stroke_color=INK, stroke_width=3, fill_color=RED, fill_opacity=1)
    door = Rectangle(width=0.45, height=0.75, stroke_color=INK, stroke_width=2.5, fill_color=TEAL,
                     fill_opacity=1).align_to(walls, DOWN)
    window = Square(0.38, stroke_color=INK, stroke_width=2.5, fill_color=YELLOW, fill_opacity=1).move_to(
        walls.get_center() + RIGHT * 0.55 + UP * 0.15)
    ground = Line(LEFT * 2.2, RIGHT * 2.2, stroke_color=INK, stroke_width=3).next_to(walls, DOWN, buff=0)
    return VGroup(ground, walls, door, window, roof)


def person(color=INK, s=0.32):
    head = Circle(radius=s * 0.32, stroke_width=0, fill_color=color, fill_opacity=1)
    body = RoundedRectangle(corner_radius=s * 0.25, width=s * 0.9, height=s * 0.9, stroke_width=0,
                            fill_color=color, fill_opacity=1).next_to(head, DOWN, buff=s * 0.06)
    return VGroup(head, body)


# ---------------------------------------------------------------- the scene ------------------------------------------
class JapanChapter4(Scene):
    def setup(self):
        self.camera.background_color = PAPER
        bg = ImageMobject(str(paper_texture())).set(height=config.frame_height + 0.02)
        bg.set_z_index(-100)
        self.add(bg)
        self.cap = None
        self.k = -1

    # -- the line clock: each line its estimated length; `at` waits until one of its words would be said
    def say(self, k):
        self.k = k
        self.t0 = self.renderer.time
        self.words = LINES[k].split()
        self.length = len(self.words) * WORD + 0.6
        new = caption(LINES[k])
        if self.cap is None:
            self.add(new)
        else:
            self.remove(self.cap)
            self.add(new)
        self.cap = new

    def at(self, word):
        """Hold until `word` (the first word of the current line starting with it) would be said, 0.2 s before it."""
        idx = next((i for i, w in enumerate(self.words) if w.strip("।,?;:").lower().startswith(word.lower())), 0)
        due = self.t0 + max(0.0, idx * WORD - 0.2)
        if due > self.renderer.time + 0.03:
            self.wait(due - self.renderer.time)

    def end(self):
        rest = self.t0 + self.length - self.renderer.time
        if rest > 0.03:
            self.wait(rest)

    def construct(self):
        # ---------- title card
        title = headline("Japan", 120)
        sub = Text("ISLANDS AND EVERYDAY LIFE", font=HEAD, font_size=40, color=INK)
        num = kicker("Chapter 4 · Paths to Modernisation")
        card = VGroup(num, title, sub).arrange(DOWN, buff=0.3)
        self.play(FadeIn(num, shift=DOWN * 0.2), run_time=0.5)
        self.play(sweep_in(title, 0.8))
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=0.5)
        self.wait(1.2)
        self.play(FadeOut(card, shift=UP * 0.4), run_time=0.5)

        # ---------- the map of East Asia
        names = ["China", "Japan", "South Korea", "North Korea", "Mongolia", "Russia", "Taiwan", "Vietnam", "Laos",
                 "Myanmar", "Philippines", "India", "Kazakhstan", "Thailand", "Bhutan", "Nepal", "Bangladesh"]
        geo = countries(names, min_area=0.02, tolerance=0.04)
        proj = Projection(124, 36, 0.155, shift=DOWN * 0.15)
        others = VGroup(*[shape(p, proj, LAND) for n, ps in geo.items() if n not in ("China", "Japan") for p in ps
                          if 85 < p.centroid.x < 160 and 5 < p.centroid.y < 62])
        china = VGroup(*[shape(p, proj, "#D9C9A8") for p in geo["China"]])
        japan_polys = geo["Japan"]
        japan = VGroup(*[shape(p, proj, RED, edge=INK, width=1.5) for p in japan_polys])
        world = VGroup(others, china, japan)

        def island(lon, lat):
            return min(range(len(japan_polys)),
                       key=lambda i: (japan_polys[i].centroid.x - lon) ** 2 + (japan_polys[i].centroid.y - lat) ** 2)

        # 117: China's mainland, Japan a string of islands
        self.say(0)
        self.play(FadeIn(others, run_time=0.8), FadeIn(china, run_time=0.8))
        self.at("mainland")
        big = Text("CHINA", font=HEAD, weight=BOLD, font_size=64, color=MUTED).move_to(proj(103, 35))
        self.play(FadeIn(big, scale=1.15), run_time=0.5)
        self.at("Japan")
        self.play(LaggedStart(*[DrawBorderThenFill(m) for m in japan], lag_ratio=0.03), run_time=1.2)
        self.at("string")
        string = headline("A string of islands", 40).next_to(proj(146, 30), DOWN, buff=0.1).shift(LEFT * 0.4)
        self.play(sweep_in(string, 0.6))
        self.end()

        # 118: zoom in, the four islands in turn
        self.say(1)
        self.play(FadeOut(string), FadeOut(big), run_time=0.3)
        self.play(world.animate.scale(2.6, about_point=proj(137, 37)).shift(proj(124, 36) - proj(137, 37)
                                                                            + LEFT * 1.8 + UP * 0.2),
                  run_time=1.4, rate_func=smooth)
        self.play(japan.animate.set_fill(LAND), run_time=0.3)
        named = []
        for word, lon, lat, side in (("Hokkaido", 142.6, 43.4, RIGHT), ("Honshu", 138.0, 36.7, RIGHT),
                                     ("Shikoku", 133.5, 33.7, DOWN), ("Kyushu", 130.9, 32.6, LEFT)):
            self.at(word)
            piece = japan[island(lon, lat)]
            lab = leader(tag(word), piece.get_center(), side=side)
            self.play(piece.animate.set_fill(RED), FadeIn(lab, shift=-side * 0.2), run_time=0.5)
            named.append(lab)
        self.end()

        # 119: four biggest
        self.say(2)
        self.at("चार")
        four = VGroup(Text("4", font=HEAD, weight=BOLD, font_size=150, color=RED),
                      Text("MAIN\nISLANDS", font=HEAD, font_size=44, color=INK, line_spacing=0.8)).arrange(RIGHT, buff=0.3)
        four.to_corner(UL, buff=0.7)
        self.play(FadeIn(four[0], scale=1.6, rate_func=rush_from), FadeIn(four[1], shift=RIGHT * 0.2), run_time=0.6)
        self.end()

        # 120: out to the world: Okinawa and the Bahamas on one latitude
        self.say(3)
        self.at("Okinawan")
        self.play(FadeOut(VGroup(*named)), FadeOut(four), run_time=0.3)
        oki = [i for i, p in enumerate(japan_polys) if p.centroid.y < 29.5 and p.centroid.x < 131.5]
        ring = Circle(radius=0.55, stroke_color=INK, stroke_width=3).move_to(VGroup(*[japan[i] for i in oki]).get_center())
        self.play(*[japan[i].animate.set_fill(YELLOW) for i in oki], Create(ring), run_time=0.6)
        self.at("latitude")
        self.play(FadeOut(world), FadeOut(ring), run_time=0.5)
        wgeo = countries(None, min_area=1.5, tolerance=0.4)
        wproj = Projection(195, 28, 0.058, shift=UP * 0.35, wrap=-30)
        strip = VGroup(*[shape(p, wproj, LAND, width=0.6) for ps in wgeo.values() for p in ps
                         if -12 < p.centroid.y < 66 and 95 < (p.centroid.x % 360) < 300])
        jp_small = VGroup(*[shape(p, wproj, RED, edge=INK, width=0.8) for p in geo["Japan"]])
        bah = VGroup(*[shape(p, wproj, RED, edge=INK, width=0.8) for p in countries(["Bahamas"], 0.0, 0.02)["Bahamas"]])
        self.play(FadeIn(strip), FadeIn(jp_small), run_time=0.8)
        line = DashedLine(wproj(126, 26.3), wproj(-76, 26.3), dash_length=0.12, stroke_color=INK, stroke_width=3)
        lat_tag = tag("≈ 26° N", fill=YELLOW, size=22).next_to(line, UP, buff=0.12)
        self.play(Create(line), FadeIn(lat_tag), run_time=1.0)
        self.at("Bahamas")
        b_lab = leader(tag("Bahamas", fill=YELLOW), wproj(-77.5, 24.5), side=DOWN, gap=0.1)
        o_lab = leader(tag("Okinawa", fill=YELLOW), wproj(127.8, 26.4), side=DOWN, gap=0.1)
        self.play(FadeIn(bah, scale=3), FadeIn(b_lab), FadeIn(o_lab), run_time=0.6)
        self.end()

        # 121: latitude compares north-south, not distance
        self.say(4)
        self.at("north-south")
        up_arrow = Arrow(wproj(-90, 0), wproj(-90, 26.3), buff=0, stroke_color=TEAL, stroke_width=6,
                         max_tip_length_to_length_ratio=0.12)
        ns = tag("north–south position", fill=CARD, size=22).next_to(up_arrow, LEFT, buff=0.15)
        self.play(GrowArrow(up_arrow), FadeIn(ns), run_time=0.6)
        self.at("दूरी")
        dist = Line(o_lab.get_top() + UP * 0.3, b_lab.get_top() + UP * 0.3, stroke_color=MUTED, stroke_width=4)
        cross = VGroup(Line(UL * 0.25, DR * 0.25), Line(UR * 0.25, DL * 0.25)).set_stroke(RED, 7).move_to(dist)
        not_d = tag("not distance", color=RED, size=22).next_to(cross, DOWN, buff=0.15)
        self.play(Create(dist), run_time=0.4)
        self.play(Create(cross), FadeIn(not_d), run_time=0.4)
        self.end()

        # 122: Japan is not one climate
        self.say(5)
        self.play(FadeOut(VGroup(strip, jp_small, bah, line, lat_tag, b_lab, o_lab, up_arrow, ns, dist, cross, not_d)),
                  run_time=0.4)
        jproj = Projection(137, 35, 0.40, shift=RIGHT * 0.6 + UP * 0.1)
        jp = VGroup(*[shape(p, jproj, LAND, edge=INK, width=1.4) for p in japan_polys])
        self.play(FadeIn(jp), run_time=0.5)
        self.at("climate")
        lats = [p.centroid.y for p in japan_polys]
        lo, hi = min(lats), max(lats)
        def climate(lat):
            return BLUE if lat > 40.5 else ("#E9D58A" if lat > 31.5 else ORANGE)
        self.play(*[m.animate.set_fill(climate(p.centroid.y)) for m, p in zip(jp, japan_polys)], run_time=0.9)
        legend = VGroup(tag("cold north", color=CARD, fill=BLUE, size=22), tag("mild middle", fill="#E9D58A", size=22),
                        tag("warm south", color=INK, fill=ORANGE, size=22))
        legend.arrange(DOWN, buff=0.25, aligned_edge=LEFT).to_corner(UL, buff=0.8)
        self.play(FadeIn(legend, shift=RIGHT * 0.2), run_time=0.4)
        self.at("गलत")
        no_one = headline("Not one climate", 44, mark=YELLOW).next_to(legend, DOWN, buff=0.6, aligned_edge=LEFT)
        self.play(sweep_in(no_one, 0.6))
        self.end()

        # 123: more than half mountainous
        self.say(6)
        self.play(FadeOut(legend), FadeOut(no_one), *[m.animate.set_fill(LAND) for m in jp], run_time=0.4)
        self.at("50")
        mains = [i for i, p in enumerate(japan_polys) if p.area > 1.0]
        peaks = VGroup()
        for i in mains:
            p = japan_polys[i]
            x0, y0, x1, y1 = p.bounds
            step = 0.55
            for gx in np.arange(x0 + step / 2, x1, step):
                for gy in np.arange(y0 + step / 2, y1, step):
                    from shapely.geometry import Point
                    if p.buffer(-0.2).contains(Point(gx, gy)) and (int(gx / step) + int(gy / step)) % 2 == 0:
                        peaks.add(Triangle(stroke_color=INK, stroke_width=1.5, fill_color="#7A8B5C",
                                           fill_opacity=1).scale(0.09).move_to(jproj(gx, gy)))
        self.play(LaggedStart(*[GrowFromPoint(t, t.get_bottom()) for t in peaks], lag_ratio=0.01), run_time=1.2)
        bar_bg = Rectangle(width=4.0, height=0.5, stroke_color=INK, stroke_width=2.5, fill_color=CARD, fill_opacity=1)
        bar_fill = Rectangle(width=4.0 * 0.6, height=0.5, stroke_width=0, fill_color="#7A8B5C",
                             fill_opacity=1).align_to(bar_bg, LEFT)
        half = DashedLine(bar_bg.get_top() + UP * 0.15, bar_bg.get_bottom() + DOWN * 0.15, dash_length=0.08,
                          stroke_color=INK, stroke_width=2.5)
        stat = VGroup(Text("50%+", font=HEAD, weight=BOLD, font_size=80, color=INK),
                      Text("of the main islands' land is mountainous", font=SANS, font_size=24, color=INK))
        stat.arrange(DOWN, buff=0.1, aligned_edge=LEFT)
        meter = VGroup(bar_bg, bar_fill, half)
        block = VGroup(stat, meter).arrange(DOWN, buff=0.35, aligned_edge=LEFT).to_corner(UL, buff=0.7)
        self.play(FadeIn(stat[0], scale=1.3), FadeIn(stat[1]), FadeIn(bar_bg), run_time=0.5)
        self.play(GrowFromEdge(bar_fill, LEFT), Create(half), run_time=0.7)
        self.end()

        # 124: half of the land you see is hills
        self.say(7)
        self.at("आधे")
        self.play(Indicate(peaks, color=RED, scale_factor=1.15), run_time=0.9)
        self.play(Circumscribe(meter, color=RED, buff=0.12), run_time=0.8)
        self.end()

        # 125: an active earthquake zone
        self.say(8)
        self.play(FadeOut(block), run_time=0.3)
        self.at("earthquake")
        centre = jproj(143.5, 38.0)
        rings = VGroup(*[Circle(radius=0.2, stroke_color=RED, stroke_width=5).move_to(centre) for _ in range(3)])
        quake = headline("Earthquake zone", 46, color=CARD, mark=RED).to_corner(UL, buff=0.7)
        self.play(sweep_in(quake, 0.5))
        for r in rings:
            self.play(r.animate.scale(9).set_stroke(opacity=0), Wiggle(VGroup(jp, peaks), scale_value=1.0,
                                                                      rotation_angle=0.015 * TAU), run_time=0.6)
        self.end()

        # 126: can a builder ignore this?
        self.say(9)
        self.play(FadeOut(VGroup(jp, peaks, rings, quake)), run_time=0.4)
        h = house().scale(1.2).shift(DOWN * 0.3)
        self.play(FadeIn(h[0]), DrawBorderThenFill(h[1:]), run_time=0.8)
        self.at("conditions")
        t1 = tag("Mountains", fill="#C8D3A8").next_to(h, LEFT, buff=0.8).shift(UP * 0.6)
        t2 = tag("Earthquakes", fill="#F2B8B5").next_to(h, RIGHT, buff=0.8).shift(UP * 0.6)
        q = Text("?", font=HEAD, weight=BOLD, font_size=120, color=RED).next_to(h, UP, buff=0.3)
        self.play(FadeIn(t1, shift=RIGHT * 0.3), FadeIn(t2, shift=LEFT * 0.3), run_time=0.5)
        self.play(FadeIn(q, scale=1.5), run_time=0.4)
        self.end()

        # 127: geography shapes architecture
        self.say(10)
        self.at("geography")
        arrow = headline("Geography  →  Architecture", 52).to_edge(UP, buff=0.6)
        self.play(FadeOut(q), sweep_in(arrow, 0.7))
        self.play(Wiggle(h, scale_value=1.02, rotation_angle=0.02 * TAU), run_time=0.8)
        self.end()

        # 128: built for its place, not only for looks
        self.say(11)
        self.at("conditions")
        fit_tag = tag("built for its place", fill=YELLOW, size=30).next_to(h, DOWN, buff=0.35)
        self.play(FadeIn(fit_tag, shift=UP * 0.2), Indicate(VGroup(t1, t2), color=RED), run_time=0.7)
        self.end()

        # 129: largely Japanese, a small Ainu minority
        self.say(12)
        self.play(FadeOut(VGroup(h, t1, t2, arrow, fit_tag)), run_time=0.4)
        pproj = Projection(135, 37.5, 0.30, shift=RIGHT * 1.6 + DOWN * 0.15)
        jp2 = VGroup(*[shape(p, pproj, LAND, edge=INK, width=1.4) for p in japan_polys])
        self.play(FadeIn(jp2), run_time=0.5)
        self.at("Japanese")
        crowd = VGroup(*[person(INK) for _ in range(12)]).arrange_in_grid(rows=3, buff=0.18).to_corner(UL, buff=0.8)
        crowd_tag = tag("largely Japanese", size=24).next_to(crowd, DOWN, buff=0.25)
        self.play(LaggedStart(*[FadeIn(p, shift=UP * 0.1) for p in crowd], lag_ratio=0.05), FadeIn(crowd_tag),
                  run_time=0.8)
        self.at("Ainu")
        hok = jp2[island(142.6, 43.4)]
        ainu = leader(tag("Ainu · small minority", fill=YELLOW, size=24), hok.get_center(), side=RIGHT)
        self.play(hok.animate.set_fill(YELLOW), FadeIn(ainu), run_time=0.6)
        self.end()

        # 130: Koreans, some brought for forced labour under colonial rule
        self.say(13)
        self.at("Koreans")
        korea = VGroup(*[shape(p, pproj, LAND, edge=INK, width=1.4) for n in ("South Korea", "North Korea")
                         for p in geo[n]])
        self.play(FadeIn(korea), run_time=0.4)
        self.at("ज़बरदस्ती")
        flow = CurvedArrow(pproj(127.5, 37.5), pproj(134.5, 35.0), angle=-TAU / 6, stroke_color=RED, stroke_width=6)
        f_tag = inside(tag("forced labour · colonial era", color=CARD, fill=RED, size=22)
                       .next_to(pproj(126.5, 34.0), DOWN + LEFT, buff=0.2))
        self.play(Create(flow), FadeIn(f_tag), run_time=0.8)
        self.end()

        # 131: not by choice -- by colonial force
        self.say(14)
        self.at("पसंद")
        choice = tag("by choice", size=30).move_to(RIGHT * 5.0 + DOWN * 0.6)
        force = tag("by colonial force", color=CARD, fill=RED, size=30).next_to(choice, DOWN, buff=0.3, aligned_edge=LEFT)
        inside(VGroup(choice, force))
        self.play(FadeIn(choice), run_time=0.3)
        strike = Line(choice.get_left(), choice.get_right(), stroke_color=RED, stroke_width=6)
        self.at("colonial")
        self.play(Create(strike), FadeIn(force, shift=UP * 0.2), run_time=0.6)
        self.end()

        # 132: population and power
        self.say(15)
        self.at("power")
        pp = headline("Population  ↔  Power", 56).move_to(UP * 0.3)
        self.play(FadeOut(VGroup(jp2, korea, flow, f_tag, choice, force, strike, crowd, crowd_tag, ainu)), run_time=0.4)
        self.play(sweep_in(pp, 0.7))
        self.end()

        # 133: no strong tradition of animal rearing
        self.say(16)
        self.play(FadeOut(pp), run_time=0.3)
        self.at("animal")
        herd = VGroup(*[RoundedRectangle(corner_radius=0.2, width=1.1, height=0.6, stroke_color=INK, stroke_width=2.5,
                                         fill_color=CARD, fill_opacity=1) for _ in range(3)]).arrange(RIGHT, buff=0.35)
        for b in herd:
            b.add(*[Line(b.get_bottom() + RIGHT * dx, b.get_bottom() + RIGHT * dx + DOWN * 0.35, stroke_color=INK,
                         stroke_width=3) for dx in (-0.35, 0.35)])
            b.add(Circle(radius=0.2, stroke_color=INK, stroke_width=2.5, fill_color=CARD, fill_opacity=1)
                  .next_to(b, LEFT, buff=-0.05).shift(UP * 0.2))
        herd.move_to(UP * 0.4)
        h_tag = tag("animal rearing", size=28).next_to(herd, DOWN, buff=0.5)
        self.play(LaggedStart(*[FadeIn(b, shift=LEFT * 0.3) for b in herd], lag_ratio=0.2), FadeIn(h_tag), run_time=0.7)
        self.at("नहीं")
        no = VGroup(Line(UL, DR), Line(UR, DL)).set_stroke(RED, 10).stretch_to_fit_width(herd.width * 0.8) \
            .stretch_to_fit_height(herd.height * 1.1).move_to(herd)
        self.play(Create(no), herd.animate.set_opacity(0.35), run_time=0.5)
        self.end()

        # 134: rice the staple, fish the protein
        self.say(17)
        self.play(FadeOut(VGroup(herd, no, h_tag)), run_time=0.3)
        self.at("Rice")
        bowl = rice_bowl().scale(1.2).move_to(LEFT * 3 + UP * 0.4)
        b_tag = tag("rice · the staple", size=26).next_to(bowl, DOWN, buff=0.45)
        self.play(FadeIn(bowl, shift=UP * 0.3), FadeIn(b_tag), run_time=0.5)
        self.at("fish")
        f = fish().scale(1.1).move_to(RIGHT * 3 + UP * 0.4)
        f_lab = tag("fish · the protein", size=26).next_to(f, DOWN, buff=0.45)
        self.play(FadeIn(f, shift=LEFT * 0.4), FadeIn(f_lab), run_time=0.5)
        self.end()

        # 135: sashimi and sushi, now loved worldwide
        self.say(18)
        self.at("sushi")
        s = sushi().scale(1.3).move_to(UP * 0.5)
        s_tag = headline("Sushi · worldwide", 44).to_edge(UP, buff=0.8)
        self.play(VGroup(bowl, b_tag).animate.shift(LEFT * 1.2).set_opacity(0.5),
                  VGroup(f, f_lab).animate.shift(RIGHT * 1.2).set_opacity(0.5), FadeIn(s, scale=0.6), run_time=0.6)
        self.play(sweep_in(s_tag, 0.6))
        self.end()

        # 136: geography all the way to the kitchen
        self.say(19)
        self.at("kitchen")
        end_line = headline("From the map to the kitchen", 52).to_edge(UP, buff=0.7)
        self.play(sweep_in(end_line, 0.7))
        self.end()

        # 137: now, the politics of this island society
        self.say(20)
        self.play(FadeOut(VGroup(bowl, b_tag, f, f_lab, s, s_tag, end_line)), run_time=0.4)
        self.at("politics")
        nxt = VGroup(kicker("Next"), headline("Politics", 90)).arrange(DOWN, buff=0.3)
        self.play(FadeIn(nxt[0]), sweep_in(nxt[1], 0.7))
        self.end()

        # 138: who really held the power?
        self.say(21)
        self.play(FadeOut(nxt), run_time=0.3)
        self.at("emperor")
        crown = VGroup(Polygon(LEFT * 0.8, LEFT * 0.8 + UP * 0.7, LEFT * 0.4 + UP * 0.3, UP * 0.85, RIGHT * 0.4 + UP * 0.3,
                               RIGHT * 0.8 + UP * 0.7, RIGHT * 0.8, stroke_color=INK, stroke_width=3, fill_color=YELLOW,
                               fill_opacity=1)).scale(1.2).move_to(LEFT * 2.5 + UP * 0.4)
        emp = tag("the emperor", size=28).next_to(crown, DOWN, buff=0.4)
        self.play(DrawBorderThenFill(crown), FadeIn(emp), run_time=0.7)
        self.at("असली")
        shadow = person(INK, 1.6).move_to(RIGHT * 2.5 + UP * 0.3).set_opacity(0.85)
        qm = Text("?", font=HEAD, weight=BOLD, font_size=110, color=RED).move_to(shadow[0])
        real = tag("real power?", color=CARD, fill=RED, size=28).next_to(shadow, DOWN, buff=0.4)
        self.play(FadeIn(shadow, shift=LEFT * 0.4), FadeIn(qm, scale=1.4), FadeIn(real), run_time=0.7)
        self.end()
        self.play(FadeOut(VGroup(crown, emp, shadow, qm, real)), FadeOut(self.cap), run_time=0.6)
