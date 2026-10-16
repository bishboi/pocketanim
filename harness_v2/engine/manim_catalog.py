"""Diagrams the free-form `manim` op builds that the fixed ops (diagram, sketch, the presets, graph, plot, timeline,
layers, differences...) do not: a catalogue, each with blocks that pass the sandbox and the phone's player
(free_check.py), so the script writer has a worked pattern for each kind and a lecture can show one as it is.

Each entry is one kind of diagram: its name, its subject, when a lesson wants it, and its beats -- (line said, Manim
code) -- built over the beats like a teacher builds it on a board: first the frame, then the parts, then what it
shows. The code is the body of construct(), with Manim's names, np, INK, MUTED_INK, PALETTE and the board's bounds
(x -6.9 to 6.9, y -3.05 to 2.85).

    python manim_catalog.py --script > examples/manim-diagrams.json    # every kind, as one lecture
    python manim_catalog.py --list                                      # the kinds, one a line
"""

from __future__ import annotations

import json
import sys

# (id, name, subject, when to use it, [(say, code), ...])
CATALOG: list[dict] = []


def kind(key: str, name: str, subject: str, use: str, *beats: tuple[str, str]) -> None:
    CATALOG.append({"id": key, "name": name, "subject": subject, "use": use, "beats": list(beats)})


# ---------------------------------------------------------------- mathematics

kind("venn", "Venn diagram", "mathematics",
     "sets and what they share: classifying, logic, probability of A and B",
     ("Some animals are mammals, and some can fly.", """
A = Circle(radius=1.9, color=PALETTE["RIVER"]).set_fill(PALETTE["RIVER"], 0.2).shift(LEFT * 1.2 + DOWN * 0.2)
B = Circle(radius=1.9, color=PALETTE["ROSE"]).set_fill(PALETTE["ROSE"], 0.2).shift(RIGHT * 1.2 + DOWN * 0.2)
la = Text("Mammals", font_size=30, color=PALETTE["RIVER"]).next_to(A, UP, buff=0.1).shift(LEFT * 0.9)
lb = Text("Can fly", font_size=30, color=PALETTE["ROSE"]).next_to(B, UP, buff=0.1).shift(RIGHT * 0.9)
dog = Text("dog", font_size=26, color=INK).move_to(A.get_center() + LEFT * 0.9)
eagle = Text("eagle", font_size=26, color=INK).move_to(B.get_center() + RIGHT * 0.9)
self.play(Create(A), Create(B), Write(la), Write(lb))
self.play(FadeIn(dog), FadeIn(eagle))
"""), ("A bat is both: it sits where the circles overlap.", """
both = Intersection(A, B, color=PALETTE["GOLD"], fill_color=PALETTE["GOLD"], fill_opacity=0.45, stroke_width=0)
bat = Text("bat", font_size=28, color=INK).move_to(both)
self.play(FadeIn(both), Write(bat))
"""))

kind("number_line", "Number line with an interval", "mathematics",
     "inequalities, intervals, integers, rounding, distance between numbers",
     ("Draw the numbers from minus five to five on a line.", """
line = NumberLine(x_range=[-5, 5, 1], length=11, include_numbers=True, font_size=30, color=INK).shift(DOWN * 0.3)
self.play(Create(line))
"""), ("x is more than minus two, and at most three.", """
a, b = line.n2p(-2), line.n2p(3)
open_end = Circle(radius=0.13, color=PALETTE["ROSE"], stroke_width=4).move_to(a)
closed_end = Dot(b, radius=0.13, color=PALETTE["ROSE"])
band = Line(a + RIGHT * 0.13, b, color=PALETTE["ROSE"], stroke_width=10)
rule = MathTex(r"-2 < x \\le 3", font_size=48, color=INK).next_to(line, UP, buff=0.9)
self.play(Create(open_end), FadeIn(closed_end), Create(band), Write(rule))
"""))

kind("unit_circle", "Unit circle", "mathematics",
     "sine and cosine as lengths, angles in radians, the signs in each quadrant",
     ("On a circle of radius one, mark an angle theta.", """
O = LEFT * 2.5 + DOWN * 0.1
R = 2.4
circle = Circle(radius=R, color=INK).move_to(O)
axes = VGroup(Line(O + LEFT * 2.8, O + RIGHT * 2.8, color=MUTED_INK), Line(O + DOWN * 2.8, O + UP * 2.8, color=MUTED_INK))
theta = ValueTracker(0.9)
def P():
    t = theta.get_value()
    return O + R * np.array([np.cos(t), np.sin(t), 0])
radius = always_redraw(lambda: Line(O, P(), color=INK, stroke_width=4))
cos_line = always_redraw(lambda: Line(O, [P()[0], O[1], 0], color=PALETTE["RIVER"], stroke_width=7))
sin_line = always_redraw(lambda: Line([P()[0], O[1], 0], P(), color=PALETTE["ROSE"], stroke_width=7))
dot = always_redraw(lambda: Dot(P(), color=PALETTE["GOLD"], radius=0.1))
self.play(Create(axes), Create(circle))
self.play(Create(radius), FadeIn(dot))
"""), ("The point is at cos theta across and sin theta up.", """
key = VGroup(MathTex(r"\\cos\\theta", font_size=46, color=PALETTE["RIVER"]),
             MathTex(r"\\sin\\theta", font_size=46, color=PALETTE["ROSE"]),
             MathTex(r"\\cos^2\\theta + \\sin^2\\theta = 1", font_size=40, color=INK)).arrange(DOWN, aligned_edge=LEFT, buff=0.45)
key.move_to(RIGHT * 3.6 + UP * 0.4)
self.play(Create(cos_line), Create(sin_line), Write(key[0]), Write(key[1]))
self.play(theta.animate.set_value(2.3), run_time=2)
self.play(Write(key[2]))
"""))

kind("pythagoras", "Squares on a right triangle", "mathematics",
     "Pythagoras' theorem shown, not just stated",
     ("A right triangle with sides three, four and five.", """
s = 0.5
A, B, C = np.array([-1.6, -0.7, 0]), np.array([-1.6 + 4 * s, -0.7, 0]), np.array([-1.6, -0.7 + 3 * s, 0])
tri = Polygon(A, B, C, color=INK, stroke_width=5)
corner = Square(0.25, color=INK, stroke_width=2).move_to(A + np.array([0.125, 0.125, 0]))
self.play(Create(tri), Create(corner))
"""), ("Build a square on each side: nine plus sixteen is twenty-five.", """
def square_on(p, q, colour, label):
    d = q - p
    n = np.array([d[1], -d[0], 0])
    sq = Polygon(p, q, q + n, p + n, color=colour, fill_color=colour, fill_opacity=0.3, stroke_width=3)
    return VGroup(sq, MathTex(label, font_size=40, color=INK).move_to(sq))
a2 = square_on(C, A, PALETTE["RIVER"], "9")
b2 = square_on(A, B, PALETTE["GREEN"], "16")
c2 = square_on(B, C, PALETTE["ROSE"], "25")
law = MathTex("a^2 + b^2 = c^2", font_size=52, color=PALETTE["GOLD"]).move_to(RIGHT * 4.6 + UP * 1.8)
self.play(FadeIn(a2), FadeIn(b2))
self.play(FadeIn(c2), Write(law))
"""))

kind("area_model", "Area model of a product", "mathematics",
     "multiplying multi-digit numbers or brackets: (20+3)(10+4) as four rectangles",
     ("Twenty-three times fourteen is a rectangle twenty-three by fourteen.", """
w1, w2, h1, h2 = 4.6, 0.9, 2.6, 1.1
x0, y0 = -4.2, 1.6
def cell(x, y, w, h, colour):
    return Rectangle(width=w, height=h, color=INK, fill_color=colour, fill_opacity=0.35).move_to([x + w / 2, y - h / 2, 0])
r = [cell(x0, y0, w1, h1, PALETTE["RIVER"]), cell(x0 + w1, y0, w2, h1, PALETTE["GREEN"]),
     cell(x0, y0 - h1, w1, h2, PALETTE["GOLD"]), cell(x0 + w1, y0 - h1, w2, h2, PALETTE["ROSE"])]
tops = VGroup(MathTex("20", color=INK).next_to(r[0], UP), MathTex("3", color=INK).next_to(r[1], UP))
sides = VGroup(MathTex("10", color=INK).next_to(r[0], LEFT), MathTex("4", color=INK).next_to(r[2], LEFT))
self.play(*[Create(c) for c in r], Write(tops), Write(sides))
"""), ("Each part is easy: two hundred, thirty, eighty and twelve make three hundred and twenty-two.", """
parts = [MathTex(t, font_size=40, color=INK).move_to(c) for t, c in zip(["200", "30", "80", "12"], r)]
total = MathTex("200 + 30 + 80 + 12", "= 322", font_size=44, color=PALETTE["GOLD"]).arrange(DOWN, aligned_edge=LEFT).move_to(RIGHT * 4.3 + UP * 0.2)
self.play(*[Write(p) for p in parts])
self.play(Write(total))
"""))

kind("fraction_bars", "Fraction bars", "mathematics",
     "equivalent fractions, comparing and adding fractions",
     ("One whole, cut into halves, thirds and sixths.", """
def bar(n, y, colour):
    w = 9.0 / n
    cells = VGroup(*[Rectangle(width=w, height=0.7, color=INK, stroke_width=3) for _ in range(n)]).arrange(RIGHT, buff=0)
    cells.move_to([0.6, y, 0])
    name = MathTex(r"\\tfrac{1}{%d}" % n if n > 1 else "1", font_size=40, color=colour).next_to(cells, LEFT, buff=0.3)
    return cells, name
rows = [bar(n, y, c) for n, y, c in [(1, 2.1, INK), (2, 1.0, PALETTE["RIVER"]), (3, -0.1, PALETTE["GREEN"]),
                                     (6, -1.2, PALETTE["ROSE"])]]
self.play(*[Create(c) for c, _ in rows], *[Write(n) for _, n in rows])
"""), ("One half covers just as much as three sixths.", """
half, sixths = rows[1][0], rows[3][0]
self.play(half[0].animate.set_fill(PALETTE["RIVER"], 0.6), *[s.animate.set_fill(PALETTE["ROSE"], 0.6) for s in sixths[:3]])
same = MathTex(r"\\tfrac{1}{2} = \\tfrac{3}{6}", font_size=50, color=PALETTE["GOLD"]).move_to([0.6, -2.4, 0])
self.play(Write(same))
"""))

kind("probability_tree", "Probability tree", "mathematics",
     "outcomes of repeated events, multiplying along branches",
     ("Toss a coin twice: each toss is heads or tails, half and half.", """
root = Dot([-5.6, 0, 0], color=INK)
first = {"H": np.array([-2.2, 1.5, 0]), "T": np.array([-2.2, -1.5, 0])}
lines, words = VGroup(), VGroup()
for k, p in first.items():
    lines.add(Line(root.get_center(), p + LEFT * 0.3, color=INK))
    words.add(Text(k, font_size=32, color=PALETTE["GOLD"]).move_to(p))
    words.add(MathTex(r"\\tfrac12", font_size=32, color=MUTED_INK).move_to((root.get_center() + p) / 2 + UP * 0.3))
self.play(FadeIn(root), Create(lines), Write(words))
"""), ("Then again from each: four outcomes, each one quarter.", """
second = VGroup()
outcomes = VGroup()
for k, p in first.items():
    for j, dy in (("H", 0.75), ("T", -0.75)):
        q = p + np.array([3.2, dy, 0])
        second.add(Line(p + RIGHT * 0.3, q + LEFT * 0.3, color=INK))
        second.add(Text(j, font_size=30, color=PALETTE["GOLD"]).move_to(q))
        outcomes.add(MathTex(k + j + r"\\;:\\;\\tfrac14", font_size=34, color=INK).move_to(q + RIGHT * 2.2))
self.play(Create(second))
self.play(Write(outcomes))
"""))

kind("function_map", "Mapping diagram", "mathematics",
     "functions and relations: each input to its output, one-to-one, many-to-one",
     ("A function sends each input to exactly one output.", """
left = Ellipse(width=2.4, height=4.6, color=PALETTE["RIVER"]).move_to([-3, -0.2, 0])
right = Ellipse(width=2.4, height=4.6, color=PALETTE["ROSE"]).move_to([3, -0.2, 0])
xs = [MathTex(str(v), color=INK).move_to(left.get_center() + UP * (1.4 - k * 0.95)) for k, v in enumerate([-2, -1, 1, 2])]
ys = [MathTex(str(v), color=INK).move_to(right.get_center() + UP * (0.8 - k * 1.6)) for k, v in enumerate([4, 1])]
names = VGroup(Text("x", font_size=30, color=PALETTE["RIVER"]).next_to(left, UP, buff=0.1),
               MathTex("x^2", color=PALETTE["ROSE"]).next_to(right, UP, buff=0.1))
self.play(Create(left), Create(right), *[Write(m) for m in xs + ys], Write(names))
"""), ("Squaring sends minus two and two to the same place: many to one.", """
pairs = [(0, 0), (1, 1), (2, 1), (3, 0)]
arrows = [Arrow(xs[a].get_right(), ys[b].get_left(), buff=0.15, color=PALETTE["GOLD"], stroke_width=4) for a, b in pairs]
self.play(*[GrowArrow(a) for a in arrows])
"""))

kind("vector_addition", "Vector addition", "mathematics",
     "adding vectors head to tail, resultants of forces or displacements",
     ("Walk three east, then two north.", """
o = np.array([-4, -2, 0])
a = Arrow(o, o + RIGHT * 4.5, buff=0, color=PALETTE["RIVER"], stroke_width=6)
b = Arrow(o + RIGHT * 4.5, o + RIGHT * 4.5 + UP * 3, buff=0, color=PALETTE["GREEN"], stroke_width=6)
la = MathTex(r"\\vec a", color=PALETTE["RIVER"], font_size=46).next_to(a, DOWN)
lb = MathTex(r"\\vec b", color=PALETTE["GREEN"], font_size=46).next_to(b, RIGHT)
self.play(GrowArrow(a), Write(la))
self.play(GrowArrow(b), Write(lb))
"""), ("The single step from start to end is their sum.", """
c = Arrow(o, o + RIGHT * 4.5 + UP * 3, buff=0, color=PALETTE["GOLD"], stroke_width=7)
lc = MathTex(r"\\vec a + \\vec b", color=PALETTE["GOLD"], font_size=46).next_to(c.get_center(), UL, buff=0.2)
self.play(GrowArrow(c), Write(lc))
"""))

kind("grid_transform", "Linear transformation of the plane", "mathematics",
     "what a matrix does: shear, rotation, stretch of the whole grid",
     ("Here is the plane with its grid.", """
plane = NumberPlane(x_range=[-4, 4, 1], y_range=[-3, 3, 1], x_length=7.5, y_length=5.6,
                    background_line_style={"stroke_color": PALETTE["RIVER"], "stroke_opacity": 0.5})
plane.move_to(DOWN * 0.1)
i_hat = Arrow(plane.c2p(0, 0), plane.c2p(1, 0), buff=0, color=PALETTE["GREEN"], stroke_width=6)
j_hat = Arrow(plane.c2p(0, 0), plane.c2p(0, 1), buff=0, color=PALETTE["ROSE"], stroke_width=6)
self.play(Create(plane), GrowArrow(i_hat), GrowArrow(j_hat))
"""), ("A shear slides each row across: the matrix one one, zero one.", """
m = MathTex(r"\\begin{bmatrix}1 & 1\\\\0 & 1\\end{bmatrix}", font_size=44, color=INK, fill_opacity=1).move_to([-5.6, 2.1, 0])
self.play(Write(m))
self.play(ApplyMatrix([[1, 1], [0, 1]], VGroup(plane, i_hat, j_hat), about_point=plane.c2p(0, 0)), run_time=2)
"""))

kind("riemann", "Area under a curve", "mathematics",
     "integration as adding thin rectangles, distance from a speed graph",
     ("Under the curve, stack thin rectangles.", """
ax = Axes(x_range=[0, 4, 1], y_range=[0, 5, 1], x_length=8, y_length=4.6, axis_config={"color": INK}).shift(DOWN * 0.1)
f = ax.plot(lambda x: 0.3 * x * x + 0.5, color=PALETTE["GOLD"])
rects = ax.get_riemann_rectangles(f, x_range=[0, 4], dx=0.5, color=[PALETTE["RIVER"], PALETTE["GREEN"]], fill_opacity=0.6)
self.play(Create(ax), Create(f))
self.play(Create(rects))
"""), ("Thinner rectangles fit the curve better: in the limit, the area.", """
finer = ax.get_riemann_rectangles(f, x_range=[0, 4], dx=0.1, color=[PALETTE["RIVER"], PALETTE["GREEN"]], fill_opacity=0.6)
label = MathTex(r"\\int_0^4 f(x)\\,dx", font_size=46, color=INK).move_to([-1.9, 1.9, 0])
self.play(Transform(rects, finer), Write(label))
"""))

kind("pie_chart", "Pie chart", "mathematics",
     "parts of a whole: shares, percentages, budgets, land use",
     ("India's land: how it is used, as slices of one whole.", """
shares = [("Farmland", 0.55, PALETTE["GREEN"]), ("Forest", 0.22, PALETTE["TEAL"]), ("Barren", 0.13, PALETTE["SAND"]),
          ("Other", 0.10, PALETTE["MUTED"] if "MUTED" in PALETTE else MUTED_INK)]
centre, start = LEFT * 2.6 + DOWN * 0.1, PI / 2
slices, labels = VGroup(), VGroup()
for name, part, colour in shares:
    angle = -part * TAU
    piece = AnnularSector(inner_radius=0, outer_radius=2.4, angle=angle, start_angle=start, color=colour,
                          fill_opacity=0.85, stroke_color=BACKGROUND, stroke_width=3).shift(centre)
    slices.add(piece)
    mid = start + angle / 2
    labels.add(Text(f"{name} {round(part * 100)}%", font_size=26, color=INK).move_to(
        [3.2, 1.6 - len(labels) * 0.9, 0]))
    start += angle
dots = VGroup(*[Square(0.3, color=s.get_color(), fill_opacity=1).next_to(l, LEFT, buff=0.2) for s, l in zip(slices, labels)])
self.play(*[Create(s) for s in slices])
self.play(FadeIn(dots), Write(labels))
"""))

kind("slope_triangle", "Slope of a line", "mathematics",
     "gradient as rise over run, the equation y = mx + c",
     ("The line y equals one half x plus one.", """
ax = Axes(x_range=[-1, 7, 1], y_range=[-1, 5, 1], x_length=7.5, y_length=5.2, axis_config={"color": INK},
          tips=False).shift(LEFT * 1.6 + DOWN * 0.1)
line = ax.plot(lambda x: 0.5 * x + 1, x_range=[-1, 7], color=PALETTE["GOLD"])
eq = MathTex("y = \\\\tfrac12 x + 1", font_size=44, color=PALETTE["GOLD"]).move_to([4.6, 2.0, 0])
self.play(Create(ax), Create(line), Write(eq))
"""), ("Go across four, and it rises two: the slope is two over four, one half.", """
p, q, r = ax.c2p(1, 1.5), ax.c2p(5, 1.5), ax.c2p(5, 3.5)
run = DashedLine(p, q, color=PALETTE["RIVER"], stroke_width=5)
rise = DashedLine(q, r, color=PALETTE["ROSE"], stroke_width=5)
lr = MathTex("4", color=PALETTE["RIVER"]).next_to(run, DOWN)
lu = MathTex("2", color=PALETTE["ROSE"]).next_to(rise, RIGHT)
m = MathTex(r"m = \\frac{\\text{rise}}{\\text{run}} = \\frac{2}{4}", font_size=42, color=INK).move_to([4.6, 0.6, 0])
self.play(Create(run), Write(lr))
self.play(Create(rise), Write(lu), Write(m))
"""))

kind("bar_model", "Bar model for a word problem", "mathematics",
     "ratio, part-whole and comparison word problems, drawn before solved",
     ("Asha has three times as many marbles as Ravi; together they have forty-eight.", """
u = 1.7
ravi = Rectangle(width=u, height=0.75, color=INK, fill_color=PALETTE["RIVER"], fill_opacity=0.5)
asha = VGroup(*[Rectangle(width=u, height=0.75, color=INK, fill_color=PALETTE["ROSE"], fill_opacity=0.5) for _ in range(3)]).arrange(RIGHT, buff=0)
ravi.move_to([-3.4 + u / 2, 0.6, 0])
asha.move_to([-3.4 + 1.5 * u, -0.6, 0])
names = VGroup(Text("Ravi", font_size=28, color=INK).next_to(ravi, LEFT), Text("Asha", font_size=28, color=INK).next_to(asha, LEFT))
total = BraceBetweenPoints(asha.get_corner(DR) + RIGHT * 0.1, ravi.get_corner(UR) + RIGHT * 0.1 + UP * 0.0, direction=RIGHT)
total_label = MathTex("48", color=PALETTE["GOLD"], font_size=48).next_to(total, RIGHT)
self.play(Create(ravi), Write(names[0]))
self.play(Create(asha), Write(names[1]), Create(total), Write(total_label))
"""), ("Four equal units make forty-eight, so one unit is twelve.", """
units = VGroup(*[MathTex("12", font_size=38, color=INK).move_to(b) for b in [ravi, *asha]])
sum_ = MathTex(r"4 \\text{ units} = 48 \\Rightarrow 1 \\text{ unit} = 12", font_size=40, color=PALETTE["GOLD"]).move_to([1.5, -2.3, 0])
self.play(Write(sum_))
self.play(*[Write(m) for m in units])
"""))

# ---------------------------------------------------------------- physics

kind("banked_road", "Free-body diagram in a real setting", "physics",
     "forces on a body where a preset has no picture: a car on a banked road, a person in a lift",
     ("A car takes a bend on a road banked at an angle.", """
theta = 20 * DEGREES
base = np.array([-5.5, -2.4, 0])
top = base + 8 * np.array([np.cos(theta), np.sin(theta), 0])
road = Polygon(base, top, [top[0], base[1], 0], color=INK, fill_color=PALETTE["DUNE"], fill_opacity=0.5)
car = RoundedRectangle(width=1.8, height=0.8, corner_radius=0.15, color=INK, fill_color=PALETTE["RIVER"], fill_opacity=0.8)
car.rotate(theta).move_to(base + 4 * np.array([np.cos(theta), np.sin(theta), 0]) + 0.45 * np.array([-np.sin(theta), np.cos(theta), 0]))
arc = Arc(radius=1.1, start_angle=0, angle=theta, arc_center=base, color=PALETTE["GOLD"])
lt = MathTex(r"\\theta", color=PALETTE["GOLD"]).move_to(base + 1.5 * np.array([np.cos(theta / 2), np.sin(theta / 2), 0]))
self.play(Create(road), FadeIn(car), Create(arc), Write(lt))
"""), ("Its weight pulls down; the road pushes back at right angles to itself.", """
c = car.get_center()
mg = Arrow(c, c + DOWN * 2.0, buff=0, color=PALETTE["ROSE"], stroke_width=6)
n_dir = np.array([-np.sin(theta), np.cos(theta), 0])
N = Arrow(c, c + 2.2 * n_dir, buff=0, color=PALETTE["GREEN"], stroke_width=6)
lm = MathTex("mg", color=PALETTE["ROSE"]).next_to(mg.get_end(), RIGHT)
ln = MathTex("N", color=PALETTE["GREEN"]).next_to(N.get_end(), UP)
note = MathTex(r"N\\sin\\theta = \\frac{mv^2}{r}", font_size=44, color=INK).move_to([3.8, 2.2, 0])
self.play(GrowArrow(mg), Write(lm), GrowArrow(N), Write(ln))
self.play(Write(note))
"""))

kind("lens_rays", "Ray diagram for a lens", "physics",
     "where a lens or mirror forms an image, real or virtual, bigger or smaller",
     ("A convex lens, its axis, and its focus on each side.", """
axis = Line(LEFT * 6.8, RIGHT * 6.8, color=MUTED_INK)
lens = Ellipse(width=0.45, height=4.6, color=PALETTE["RIVER"], fill_color=PALETTE["RIVER"], fill_opacity=0.2)
f = 1.8
foci = VGroup(*[Dot([s * f, 0, 0], color=INK) for s in (-1, 1)], *[MathTex("F", font_size=34, color=INK).move_to([s * f, -0.35, 0]) for s in (-1, 1)])
obj = Arrow([-4.2, 0, 0], [-4.2, 1.4, 0], buff=0, color=PALETTE["GOLD"], stroke_width=6)
self.play(Create(axis), FadeIn(lens), FadeIn(foci), GrowArrow(obj))
"""), ("A ray parallel to the axis bends through the focus; one through the centre goes straight.", """
top = np.array([-4.2, 1.4, 0])
u, v = 4.2, 1 / (1 / f - 1 / 4.2)
img_top = np.array([v, -1.4 * v / u, 0])
r1 = VGroup(Line(top, [0, 1.4, 0], color=PALETTE["ROSE"]), Line([0, 1.4, 0], img_top + (img_top - [0, 1.4, 0]) * 0.4, color=PALETTE["ROSE"]))
r2 = Line(top, img_top + (img_top - top) * 0.25, color=PALETTE["GREEN"])
image = Arrow([v, 0, 0], img_top, buff=0, color=PALETTE["GOLD"], stroke_width=6)
tag = Text("real, inverted", font_size=26, color=INK).move_to([4.8, -2.4, 0])
self.play(Create(r1), Create(r2))
self.play(GrowArrow(image), Write(tag))
"""))

kind("field_lines", "Electric field lines", "physics",
     "fields around charges or magnets: direction and strength from how close the lines are",
     ("A positive and a negative charge, side by side.", """
p, n = LEFT * 2.6 + DOWN * 0.1, RIGHT * 2.6 + DOWN * 0.1
plus = VGroup(Circle(radius=0.38, color=PALETTE["ROSE"], fill_opacity=0.9), MathTex("+", color=BACKGROUND, font_size=50)).move_to(p)
minus = VGroup(Circle(radius=0.38, color=PALETTE["RIVER"], fill_opacity=0.9), MathTex("-", color=BACKGROUND, font_size=50)).move_to(n)
self.play(FadeIn(plus), FadeIn(minus))
"""), ("Field lines leave the positive charge and end on the negative one.", """
lines = VGroup()
for angle in [-1.3, -0.85, -0.45, 0.0, 0.45, 0.85, 1.3]:
    arc = ArcBetweenPoints(p + RIGHT * 0.4, n + LEFT * 0.4, angle=-angle * 1.6, color=PALETTE["GOLD"], stroke_width=3)
    tip = arc.point_from_proportion(0.5)
    ahead = arc.point_from_proportion(0.52)
    lines.add(arc, Arrow(tip, ahead, buff=0, color=PALETTE["GOLD"], stroke_width=3, max_tip_length_to_length_ratio=8, tip_length=0.18))
self.play(Create(lines), run_time=2)
"""))

kind("wave", "Transverse wave", "physics",
     "wavelength, amplitude, crest and trough; sound, light, water waves",
     ("A wave on a string: crests and troughs.", """
ax_line = Line(LEFT * 6.3, RIGHT * 6.3, color=MUTED_INK).shift(DOWN * 0.2)
wave = FunctionGraph(lambda x: 1.3 * np.sin(2 * PI * x / 4), x_range=[-6.3, 6.3], color=PALETTE["RIVER"], stroke_width=5).shift(DOWN * 0.2)
self.play(Create(ax_line), Create(wave), run_time=2)
"""), ("Crest to crest is the wavelength; the height from the middle is the amplitude.", """
c1, c2 = np.array([-3, 1.1, 0]), np.array([1, 1.1, 0])
lam = DoubleArrow(c1 + UP * 0.35, c2 + UP * 0.35, buff=0, color=PALETTE["GOLD"], stroke_width=4)
ll = MathTex(r"\\lambda", color=PALETTE["GOLD"], font_size=46).next_to(lam, UP, buff=0.1)
amp = DoubleArrow([5, -0.2, 0], [5, 1.1, 0], buff=0, color=PALETTE["ROSE"], stroke_width=4)
la = Text("amplitude", font_size=26, color=PALETTE["ROSE"]).next_to(amp, UP, buff=0.35)
self.play(GrowArrow(lam), Write(ll))
self.play(GrowArrow(amp), Write(la))
"""))

kind("circuit", "Circuit diagram", "physics",
     "series and parallel circuits with their symbols, current and potential difference",
     ("A cell, a switch and two bulbs in series.", """
w, h = 9.0, 3.8
box = [np.array(p) for p in ([-w / 2, h / 2 - 0.1, 0], [w / 2, h / 2 - 0.1, 0], [w / 2, -h / 2 - 0.1, 0], [-w / 2, -h / 2 - 0.1, 0])]
def cell(at):
    return VGroup(Line(at + LEFT * 0.12 + UP * 0.5, at + LEFT * 0.12 + DOWN * 0.5, color=INK, stroke_width=5),
                  Line(at + RIGHT * 0.12 + UP * 0.25, at + RIGHT * 0.12 + DOWN * 0.25, color=INK, stroke_width=9))
def bulb(at):
    c = Circle(radius=0.35, color=INK, stroke_width=4).move_to(at)
    return VGroup(c, Line(at + UL * 0.25, at + DR * 0.25, color=INK), Line(at + UR * 0.25, at + DL * 0.25, color=INK))
top_mid = (box[0] + box[1]) / 2
parts = VGroup(cell(top_mid), bulb(np.array([w / 2, -0.1, 0])), bulb((box[2] + box[3]) / 2))
wires = VGroup(Line(box[0], top_mid + LEFT * 0.12, color=INK), Line(top_mid + RIGHT * 0.12, box[1], color=INK),
               Line(box[1], parts[1][0].get_top(), color=INK), Line(parts[1][0].get_bottom(), box[2], color=INK),
               Line(box[2], parts[2][0].get_right(), color=INK), Line(parts[2][0].get_left(), box[3], color=INK),
               Line(box[3], box[0], color=INK))
names = VGroup(Text("cell", font_size=24, color=INK).next_to(parts[0], UP), Text("bulb", font_size=24, color=INK).next_to(parts[1], RIGHT),
               Text("bulb", font_size=24, color=INK).next_to(parts[2], DOWN))
self.play(Create(wires), FadeIn(parts), Write(names))
"""), ("The same current flows all the way round, from positive to negative.", """
flow = VGroup(*[Arrow(a, b, buff=0, color=PALETTE["GOLD"], stroke_width=5) for a, b in [
    (np.array([-3.4, 1.8, 0]), np.array([-2.2, 1.8, 0])), (np.array([4.5, 1.2, 0]), np.array([4.5, 0.4, 0])),
    (np.array([1.8, -2.0, 0]), np.array([0.8, -2.0, 0])), (np.array([-4.5, -1.2, 0]), np.array([-4.5, -0.2, 0]))]])
lab = MathTex("I", color=PALETTE["GOLD"], font_size=48).move_to([-1.6, 1.25, 0])
self.play(*[GrowArrow(a) for a in flow], Write(lab))
"""))

kind("energy_levels", "Energy level diagram", "physics",
     "atomic spectra, electron transitions, emission and absorption of light",
     ("The energy levels of hydrogen, closer together as they rise.", """
energies = {1: -13.6, 2: -3.4, 3: -1.51, 4: -0.85}
# Not to scale: the upper levels crowd together, so each gets room for its words.
heights = {-13.6: -2.6, -3.4: 0.0, -1.51: 1.15, -0.85: 2.0, -2.4: 0.6}
def y(e):
    return heights[e]
levels = VGroup()
for n, e in energies.items():
    levels.add(Line([-4.5, y(e), 0], [1.5, y(e), 0], color=INK, stroke_width=4))
    levels.add(MathTex(f"n={n}", font_size=32, color=INK).move_to([-5.3, y(e), 0]))
    levels.add(MathTex(f"{e}\\\\,\\\\text{{eV}}", font_size=30, color=MUTED_INK).move_to([2.6, y(e), 0]))
self.play(Create(levels), run_time=2)
"""), ("An electron falling from level three to two gives out red light.", """
drop = Arrow([-1.5, y(-1.51), 0], [-1.5, y(-3.4), 0], buff=0, color=PALETTE["ROSE"], stroke_width=7)
photon = FunctionGraph(lambda x: 0.15 * np.sin(8 * x), x_range=[0, 2.4], color=PALETTE["ROSE"]).move_to([4.6, 0.6, 0])
lab = MathTex(r"\\Delta E = h f", font_size=42, color=PALETTE["ROSE"]).next_to(photon, UP)
self.play(GrowArrow(drop))
self.play(Create(photon), Write(lab))
"""))

kind("projectile_components", "Projectile with velocity components", "physics",
     "why the horizontal speed stays and the vertical one changes",
     ("A ball thrown at an angle follows a curve.", """
ax = Axes(x_range=[0, 10, 2], y_range=[0, 5, 1], x_length=11, y_length=4.8, axis_config={"color": INK}, tips=False).shift(DOWN * 0.15)
path = ax.plot(lambda x: 1.9 * x - 0.19 * x * x, x_range=[0, 10], color=PALETTE["GOLD"])
self.play(Create(ax), Create(path), run_time=2)
"""), ("At every point it moves across at the same speed; only its upward speed changes.", """
arrows = VGroup()
for x in (1, 5, 9):
    p = ax.c2p(x, 1.9 * x - 0.19 * x * x)
    vy = (1.9 - 0.38 * x) * 0.55
    arrows.add(Arrow(p, p + RIGHT * 1.0, buff=0, color=PALETTE["RIVER"], stroke_width=5),
               Arrow(p, p + UP * vy, buff=0, color=PALETTE["ROSE"], stroke_width=5) if abs(vy) > 0.05 else VGroup())
key = VGroup(MathTex("v_x", color=PALETTE["RIVER"]), MathTex("v_y", color=PALETTE["ROSE"])).arrange(RIGHT, buff=0.6).move_to([4.5, 2.4, 0])
self.play(*[GrowArrow(a) for a in arrows if isinstance(a, Arrow)], Write(key))
"""))

# ---------------------------------------------------------------- chemistry

kind("bohr_atom", "Shell (Bohr) model of an atom", "chemistry",
     "electron configuration, valence electrons, why atoms bond",
     ("Sodium: eleven protons in the nucleus.", """
centre = LEFT * 2 + DOWN * 0.1
nucleus = VGroup(Circle(radius=0.5, color=PALETTE["ROSE"], fill_opacity=0.8), Text("11+", font_size=26, color=BACKGROUND)).move_to(centre)
shells = VGroup(*[Circle(radius=r, color=MUTED_INK, stroke_width=2).move_to(centre) for r in (1.0, 1.75, 2.5)])
self.play(FadeIn(nucleus), Create(shells))
"""), ("Its electrons fill shells of two, eight and one.", """
electrons = VGroup()
for shell, count in zip(shells, (2, 8, 1)):
    for k in range(count):
        a = TAU * k / count + 0.3
        electrons.add(Dot(centre + shell.radius * np.array([np.cos(a), np.sin(a), 0]), color=PALETTE["RIVER"], radius=0.1))
filled = MathTex("2,\\\\,8,\\\\,1", font_size=54, color=INK).move_to([3.6, 1.2, 0])
valence = Text("one valence electron", font_size=28, color=PALETTE["GOLD"]).next_to(filled, DOWN, buff=0.4)
self.play(FadeIn(electrons, lag_ratio=0.1), Write(filled))
self.play(Indicate(electrons[-1], color=PALETTE["GOLD"]), Write(valence))
"""))

kind("reaction_profile", "Reaction energy profile", "chemistry",
     "activation energy, exothermic and endothermic reactions, catalysts",
     ("As a reaction goes on, energy rises over a hill and falls.", """
ax = Axes(x_range=[0, 10, 1], y_range=[0, 6, 1], x_length=9, y_length=4.8, axis_config={"color": INK}, tips=True).shift(LEFT * 1.0 + DOWN * 0.1)
labels = VGroup(Text("progress of reaction", font_size=24, color=INK).next_to(ax, DOWN, buff=0.1),
                Text("energy", font_size=24, color=INK).rotate(PI / 2).next_to(ax, LEFT, buff=0.1))
curve = ax.plot(lambda x: 3.6 + 1.6 * np.exp(-((x - 4.5) ** 2) / 1.6) - 2.0 / (1 + np.exp(-(x - 5.5))), x_range=[0.5, 9.5], color=PALETTE["GOLD"], stroke_width=5)
self.play(Create(ax), Write(labels), Create(curve), run_time=2)
"""), ("The hill is the activation energy; the drop is the energy given out.", """
ea = DoubleArrow(ax.c2p(1.2, 3.6), ax.c2p(1.2, 5.18), buff=0, color=PALETTE["ROSE"], stroke_width=4)
dh = DoubleArrow(ax.c2p(8.6, 3.6), ax.c2p(8.6, 1.62), buff=0, color=PALETTE["RIVER"], stroke_width=4)
guides = VGroup(DashedLine(ax.c2p(0.5, 3.6), ax.c2p(9, 3.6), color=MUTED_INK), DashedLine(ax.c2p(1.0, 5.18), ax.c2p(4.5, 5.18), color=MUTED_INK))
lea = MathTex("E_a", color=PALETTE["ROSE"]).next_to(ea, LEFT)
ldh = MathTex(r"\\Delta H < 0", color=PALETTE["RIVER"]).next_to(dh, RIGHT)
self.play(Create(guides), GrowArrow(ea), Write(lea))
self.play(GrowArrow(dh), Write(ldh))
"""))

kind("periodic_block", "Part of the periodic table", "chemistry",
     "groups and periods, metals and non-metals, trends across and down",
     ("The first twenty elements, by period and group.", """
rows = [["H", "", "", "", "", "", "", "He"], ["Li", "Be", "B", "C", "N", "O", "F", "Ne"],
        ["Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar"], ["K", "Ca", "", "", "", "", "", ""]]
metals = {"Li", "Be", "Na", "Mg", "Al", "K", "Ca"}
noble = {"He", "Ne", "Ar"}
cells = VGroup()
for r, row in enumerate(rows):
    for c, sym in enumerate(row):
        if not sym:
            continue
        colour = PALETTE["RIVER"] if sym in metals else PALETTE["VIOLET"] if sym in noble else PALETTE["GREEN"]
        box = Square(1.05, color=INK, stroke_width=2, fill_color=colour, fill_opacity=0.45).move_to([-4.2 + c * 1.15, 1.9 - r * 1.15, 0])
        cells.add(VGroup(box, Text(sym, font_size=30, color=INK).move_to(box)))
self.play(FadeIn(cells, lag_ratio=0.05), run_time=2)
"""), ("Metals on the left, non-metals on the right, the noble gases in the last column.", """
key = VGroup(*[VGroup(Square(0.3, fill_color=c, fill_opacity=0.6, color=INK, stroke_width=1), Text(t, font_size=24, color=INK)).arrange(RIGHT, buff=0.15)
               for c, t in ((PALETTE["RIVER"], "metals"), (PALETTE["GREEN"], "non-metals"), (PALETTE["VIOLET"], "noble gases"))]).arrange(RIGHT, buff=0.6).move_to([0.4, -2.5, 0])
self.play(FadeIn(key))
"""))

# ---------------------------------------------------------------- biology

kind("punnett", "Punnett square", "biology",
     "inheritance: the offspring of a cross and their ratios",
     ("Cross two tall plants that each carry a short gene: big T, small t.", """
size = 1.5
x0, y0 = -1.5, 1.2
grid = VGroup(*[Square(size, color=INK).move_to([x0 + c * size, y0 - r * size, 0]) for r in range(2) for c in range(2)])
top = VGroup(*[MathTex(g, font_size=48, color=PALETTE["RIVER"]).move_to([x0 + c * size, y0 + size * 0.85, 0]) for c, g in enumerate(["T", "t"])])
side = VGroup(*[MathTex(g, font_size=48, color=PALETTE["ROSE"]).move_to([x0 - size * 0.85, y0 - r * size, 0]) for r, g in enumerate(["T", "t"])])
self.play(Create(grid), Write(top), Write(side))
"""), ("Three of the four are tall: a ratio of three to one.", """
kids = ["TT", "Tt", "Tt", "tt"]
fills = [grid[k].animate.set_fill(PALETTE["GREEN"] if "T" in g else PALETTE["SAND"], 0.45) for k, g in enumerate(kids)]
words = VGroup(*[MathTex(g, font_size=46, color=INK).move_to(grid[k]) for k, g in enumerate(kids)])
ratio = MathTex(r"\\text{tall} : \\text{short} = 3 : 1", font_size=44, color=PALETTE["GOLD"]).move_to([4.2, 0.4, 0])
self.play(*fills, Write(words))
self.play(Write(ratio))
"""))

kind("pedigree", "Pedigree chart", "biology",
     "how a trait or a disorder passes down a family",
     ("A father and mother; neither shows the trait.", """
def male(at, shaded=False):
    return Square(0.7, color=INK, stroke_width=4, fill_color=PALETTE["ROSE"], fill_opacity=0.8 if shaded else 0).move_to(at)
def female(at, shaded=False):
    return Circle(radius=0.37, color=INK, stroke_width=4, fill_color=PALETTE["ROSE"], fill_opacity=0.8 if shaded else 0).move_to(at)
dad, mum = male([-1.5, 1.8, 0]), female([1.5, 1.8, 0])
couple = Line(dad.get_right(), mum.get_left(), color=INK)
self.play(Create(dad), Create(mum), Create(couple))
"""), ("Of their three children, one son shows it: both parents carried it.", """
drop = Line([0, 1.8, 0], [0, 0.6, 0], color=INK)
bar = Line([-3, 0.6, 0], [3, 0.6, 0], color=INK)
kids = [male([-3, -0.3, 0]), female([0, -0.3, 0]), male([3, -0.3, 0], shaded=True)]
legs = VGroup(*[Line([k.get_center()[0], 0.6, 0], k.get_top(), color=INK) for k in kids])
key = VGroup(Square(0.35, color=INK, fill_color=PALETTE["ROSE"], fill_opacity=0.8), Text("shows the trait", font_size=24, color=INK)).arrange(RIGHT).move_to([4.5, 2.2, 0])
self.play(Create(drop), Create(bar), Create(legs), *[Create(k) for k in kids])
self.play(FadeIn(key), Indicate(kids[2]))
"""))

kind("food_web", "Food web", "biology",
     "who eats whom when more than one chain crosses: a network, not a line or a cycle",
     ("Grass and seeds feed the rabbit, the mouse and the grasshopper.", """
# In feeding levels, plants at the bottom and the top predator above, so no arrow runs through a name.
pos = {"grass": [-3.6, -2.3], "seeds": [1.6, -2.3], "rabbit": [-5.4, -0.6], "grasshopper": [-1.8, -0.6], "mouse": [2.4, -0.6],
       "frog": [-1.0, 0.9], "snake": [2.4, 0.9], "hawk": [0.3, 2.3]}
nodes = {k: Text(k, font_size=28, color=INK).move_to([x, y, 0]) for k, (x, y) in pos.items()}
self.play(*[Write(v) for v in nodes.values()])
"""), ("Arrows show where the energy goes: from what is eaten to what eats it.", """
eats = [("grass", "rabbit"), ("grass", "grasshopper"), ("seeds", "mouse"), ("grasshopper", "frog"), ("frog", "snake"),
        ("mouse", "snake"), ("rabbit", "hawk"), ("snake", "hawk"), ("mouse", "hawk"), ("seeds", "grasshopper")]
arrows = [Arrow(nodes[a].get_center(), nodes[b].get_center(), buff=0.45, color=PALETTE["GREEN"], stroke_width=3, tip_length=0.18) for a, b in eats]
self.play(*[GrowArrow(a) for a in arrows], run_time=2)
"""))

# ---------------------------------------------------------------- economics, geography, history

kind("supply_demand", "Supply and demand", "economics",
     "market price, shortages and surpluses, what a shift in demand does",
     ("Demand falls as the price rises; supply rises with it.", """
ax = Axes(x_range=[0, 10, 1], y_range=[0, 10, 1], x_length=6.5, y_length=4.5, axis_config={"color": INK}, tips=True).shift(LEFT * 2.3)
labels = VGroup(Text("quantity", font_size=24, color=INK).next_to(ax, DOWN, buff=0.05), Text("price", font_size=24, color=INK).next_to(ax, UP, buff=0.05).align_to(ax, LEFT))
demand = ax.plot(lambda q: 9 - 0.8 * q, x_range=[0.5, 9.5], color=PALETTE["RIVER"], stroke_width=5)
supply = ax.plot(lambda q: 1 + 0.8 * q, x_range=[0.5, 9.5], color=PALETTE["ROSE"], stroke_width=5)
ld = Text("D", font_size=30, color=PALETTE["RIVER"]).next_to(demand.get_end(), RIGHT)
ls = Text("S", font_size=30, color=PALETTE["ROSE"]).next_to(supply.get_end(), RIGHT)
eq = Dot(ax.c2p(5, 5), color=PALETTE["GOLD"], radius=0.1)
guides = VGroup(DashedLine(ax.c2p(5, 0), ax.c2p(5, 5), color=MUTED_INK), DashedLine(ax.c2p(0, 5), ax.c2p(5, 5), color=MUTED_INK))
self.play(Create(ax), Write(labels), Create(demand), Create(supply), Write(ld), Write(ls))
self.play(FadeIn(eq), Create(guides))
"""), ("When more people want it, demand moves right: the price and the quantity both rise.", """
demand2 = ax.plot(lambda q: 11 - 0.8 * q, x_range=[2, 9.5], color=PALETTE["RIVER"], stroke_width=5, stroke_opacity=0.6)
eq2 = Dot(ax.c2p(6.25, 6), color=PALETTE["GOLD"], radius=0.1)
note = Text("demand rises:\\nprice and quantity up", font_size=28, color=INK).move_to([4.4, 1.0, 0])
self.play(Create(demand2), FadeIn(eq2), Write(note))
"""))

kind("climograph", "Climate graph", "geography",
     "a place's year of weather: rainfall as bars, temperature as a line",
     ("Mumbai's rainfall, month by month.", """
rain = [1, 1, 0, 1, 18, 485, 617, 340, 264, 64, 13, 3]
temp = [24, 25, 27, 29, 30, 29, 28, 27, 28, 29, 28, 26]
ax = Axes(x_range=[0, 12, 1], y_range=[0, 700, 100], x_length=10, y_length=4.6, axis_config={"color": INK}, tips=False).shift(DOWN * 0.3)
bars = VGroup(*[Rectangle(width=0.6, height=max(0.02, ax.c2p(0, r)[1] - ax.c2p(0, 0)[1]), color=PALETTE["RIVER"], fill_opacity=0.7, stroke_width=1)
                .move_to(ax.c2p(m + 0.5, 0), aligned_edge=DOWN) for m, r in enumerate(rain)])
months = VGroup(*[Text(c, font_size=22, color=INK).next_to(ax.c2p(m + 0.5, 0), DOWN, buff=0.1) for m, c in enumerate("JFMAMJJASOND")])
self.play(Create(ax), Write(months))
self.play(*[GrowFromEdge(b, DOWN) for b in bars], run_time=2)
"""), ("The temperature hardly changes: warm all year.", """
pts = [ax.c2p(m + 0.5, (t - 20) * 50) for m, t in enumerate(temp)]
line = VMobject(color=PALETTE["ROSE"], stroke_width=5).set_points_smoothly(pts)
key = VGroup(Text("rain (mm)", font_size=24, color=PALETTE["RIVER"]), Text("temperature", font_size=24, color=PALETTE["ROSE"])).arrange(DOWN, aligned_edge=LEFT).move_to([5.3, 2.3, 0])
self.play(Create(line), Write(key))
"""))

kind("quadrant", "Two-by-two matrix", "economics",
     "sorting things on two scales at once: urgent and important, cost and benefit, rich and poor",
     ("Sort tasks by how urgent and how important they are.", """
size = 2.3
cells = VGroup(*[Square(size, color=INK, fill_color=c, fill_opacity=0.25).move_to([(k % 2 - 0.5) * size, (0.5 - k // 2) * size - 0.2, 0])
                 for k, c in enumerate([PALETTE["ROSE"], PALETTE["GOLD"], PALETTE["RIVER"], PALETTE["MUTED"] if "MUTED" in PALETTE else MUTED_INK])])
words = ["Do now", "Plan it", "Hand over", "Drop it"]
names = VGroup(*[Text(w, font_size=30, color=INK).move_to(c) for w, c in zip(words, cells)])
axes = VGroup(Text("urgent", font_size=26, color=INK).next_to(cells, UP, buff=0.15).shift(LEFT * size / 2),
              Text("not urgent", font_size=26, color=INK).next_to(cells, UP, buff=0.15).shift(RIGHT * size / 2),
              Text("important", font_size=26, color=INK).rotate(PI / 2).next_to(cells, LEFT, buff=0.15).shift(UP * size / 2),
              Text("not important", font_size=26, color=INK).rotate(PI / 2).next_to(cells, LEFT, buff=0.15).shift(DOWN * size / 2))
self.play(Create(cells), Write(axes))
self.play(Write(names))
"""))

kind("fishbone", "Cause-and-effect (fishbone) diagram", "geography",
     "the many causes behind one effect, grouped: floods, a war, a famine, a disease",
     ("Why do floods happen? The effect goes at the head.", """
spine = Arrow([-6.2, -0.2, 0], [3.6, -0.2, 0], buff=0, color=INK, stroke_width=5)
head = VGroup(RoundedRectangle(width=2.6, height=1.0, corner_radius=0.15, color=PALETTE["ROSE"], fill_opacity=0.3),
              Text("Floods", font_size=32, color=INK)).move_to([5.1, -0.2, 0])
self.play(GrowArrow(spine), FadeIn(head))
"""), ("Causes branch in from nature and from people.", """
groups = [("Heavy rain", [-4.2, 1]), ("Deforestation", [-1.0, 1]), ("Silted rivers", [-4.2, -1]), ("Building on floodplains", [-1.0, -1])]
ribs = VGroup()
for name, (x, side) in groups:
    end = np.array([x + 1.4, -0.2, 0])
    start = np.array([x, -0.2 + side * 2.0, 0])
    ribs.add(Line(start, end, color=PALETTE["GOLD"], stroke_width=4))
    ribs.add(Text(name, font_size=24, color=INK).next_to(start, UP if side > 0 else DOWN, buff=0.1))
self.play(Create(ribs), run_time=2)
"""))

kind("energy_flow", "Flow (Sankey) diagram", "geography",
     "where energy, water or money goes, each band as wide as its share",
     ("A bulb takes in one hundred joules of electrical energy.", """
inp = Rectangle(width=3.0, height=3.0, color=PALETTE["GOLD"], fill_opacity=0.6, stroke_width=0).move_to([-4.6, 0.3, 0])
lab = Text("100 J electrical", font_size=26, color=INK).next_to(inp, DOWN)
self.play(FadeIn(inp), Write(lab))
"""), ("Only ten joules come out as light; ninety are lost as heat.", """
x0 = inp.get_right()[0]
useful = Polygon([x0, 1.8, 0], [x0 + 3, 1.8, 0], [x0 + 4, 2.3, 0], [x0 + 7.4, 2.3, 0], [x0 + 7.4, 2.0, 0], [x0 + 4, 2.0, 0], [x0 + 3, 1.5, 0], [x0, 1.5, 0],
                 color=PALETTE["RIVER"], fill_opacity=0.7, stroke_width=0)
waste = Polygon([x0, 1.5, 0], [x0 + 2.4, 1.5, 0], [x0 + 3.6, -1.0, 0], [x0 + 3.6, -2.6, 0], [x0 + 0.9, -2.6, 0], [x0 + 0.9, -1.2, 0], [x0, -1.2, 0],
                color=PALETTE["ROSE"], fill_opacity=0.6, stroke_width=0)
labels = VGroup(Text("10 J light", font_size=26, color=PALETTE["RIVER"]).next_to(useful, DOWN, buff=0.1).align_to(useful, RIGHT),
                Text("90 J heat", font_size=26, color=PALETTE["ROSE"]).next_to(waste, RIGHT))
self.play(FadeIn(useful), FadeIn(waste), Write(labels))
"""))

kind("swimlanes", "Parallel timelines (swimlanes)", "history",
     "what happened at the same time in different places or to different people",
     ("Two empires, side by side through the same centuries.", """
years = [1500, 1600, 1700, 1800]
def x(year):
    return -4.3 + (year - 1500) / 300 * 10
axis = VGroup(Line([x(1500), -2.6, 0], [x(1800), -2.6, 0], color=INK),
              *[Text(str(y), font_size=24, color=INK).move_to([x(y), -2.9, 0]) for y in years])
lanes = VGroup(Text("Mughals", font_size=28, color=PALETTE["GOLD"]).move_to([-5.7, 1.2, 0]),
               Text("Ottomans", font_size=28, color=PALETTE["RIVER"]).move_to([-5.7, -0.8, 0]))
self.play(Create(axis), Write(lanes))
"""), ("Each bar is a reign; you can read who ruled at the same time.", """
reigns = [("Akbar", 1556, 1605, 1.2, PALETTE["GOLD"]), ("Aurangzeb", 1658, 1707, 1.2, PALETTE["GOLD"]),
          ("Suleiman", 1520, 1566, -0.8, PALETTE["RIVER"]), ("Mehmed IV", 1648, 1687, -0.8, PALETTE["RIVER"])]
bars = VGroup()
for name, a, b, y, c in reigns:
    bar = Rectangle(width=x(b) - x(a), height=0.55, color=c, fill_opacity=0.6, stroke_width=0).move_to([(x(a) + x(b)) / 2, y, 0])
    bars.add(bar, Text(name, font_size=22, color=INK).next_to(bar, UP, buff=0.08))
self.play(*[FadeIn(m) for m in bars])
"""))

# ---------------------------------------------------------------- computing

kind("binary_tree", "Binary search tree", "computing",
     "trees, searching by halves, recursion",
     ("A binary search tree: smaller to the left, larger to the right.", """
pos = {50: [0, 2.2], 30: [-3, 0.8], 70: [3, 0.8], 20: [-4.5, -0.6], 40: [-1.5, -0.6], 60: [1.5, -0.6], 80: [4.5, -0.6]}
nodes = {v: VGroup(Circle(radius=0.42, color=INK, fill_color=BACKGROUND, fill_opacity=1), MathTex(str(v), font_size=36, color=INK)).move_to([x, y, 0])
         for v, (x, y) in pos.items()}
edges = VGroup(*[Line(nodes[a].get_center(), nodes[b].get_center(), color=MUTED_INK, buff=0.42)
                 for a, b in [(50, 30), (50, 70), (30, 20), (30, 40), (70, 60), (70, 80)]])
self.play(Create(edges), *[FadeIn(n) for n in nodes.values()])
"""), ("To find sixty: more than fifty, go right; less than seventy, go left.", """
for v in (50, 70, 60):
    self.play(nodes[v][0].animate.set_fill(PALETTE["GOLD"], 0.6), run_time=0.6)
found = Text("found in 3 steps", font_size=28, color=PALETTE["GOLD"]).move_to([0, -2.3, 0])
self.play(Write(found))
"""))

kind("array_pointers", "Array and linked list", "computing",
     "how data sits in memory: indexes, pointers, inserting in the middle",
     ("An array keeps its items side by side, numbered from zero.", """
vals = [7, 3, 9, 4, 1]
cells = VGroup(*[VGroup(Square(1.0, color=INK), MathTex(str(v), font_size=40, color=INK)) for v in vals]).arrange(RIGHT, buff=0).move_to([0, 1.5, 0])
idx = VGroup(*[MathTex(str(k), font_size=28, color=MUTED_INK).next_to(c, UP, buff=0.1) for k, c in enumerate(cells)])
self.play(Create(cells), Write(idx))
"""), ("A linked list keeps each item with an arrow to the next.", """
nodes = VGroup(*[VGroup(Rectangle(width=1.0, height=0.8, color=INK), Rectangle(width=0.5, height=0.8, color=INK, fill_color=PALETTE["RIVER"], fill_opacity=0.3)).arrange(RIGHT, buff=0)
                 for _ in range(4)]).arrange(RIGHT, buff=0.9).move_to([0, -1.4, 0])
texts = VGroup(*[MathTex(str(v), font_size=36, color=INK).move_to(n[0]) for v, n in zip([7, 3, 9, 4], nodes)])
links = VGroup(*[Arrow(nodes[k][1].get_center(), nodes[k + 1][0].get_left(), buff=0.05, color=PALETTE["GOLD"], stroke_width=4) for k in range(3)])
null = Text("null", font_size=24, color=MUTED_INK).next_to(nodes[-1], RIGHT, buff=0.3)
self.play(Create(nodes), Write(texts))
self.play(*[GrowArrow(a) for a in links], Write(null))
"""))

kind("stack_queue", "Stack", "computing",
     "last in, first out: undo, function calls, brackets",
     ("A stack: each new plate goes on top.", """
base = Line([-1.4, -2.5, 0], [1.4, -2.5, 0], color=INK, stroke_width=5)
walls = VGroup(Line([-1.4, -2.5, 0], [-1.4, 2.0, 0], color=MUTED_INK), Line([1.4, -2.5, 0], [1.4, 2.0, 0], color=MUTED_INK))
self.play(Create(base), Create(walls))
items = VGroup()
for k, (t, c) in enumerate([("A", PALETTE["RIVER"]), ("B", PALETTE["GREEN"]), ("C", PALETTE["ROSE"])]):
    box = VGroup(Rectangle(width=2.4, height=0.8, color=INK, fill_color=c, fill_opacity=0.5), Text(t, font_size=32, color=INK))
    box.move_to([0, 2.5, 0])
    self.play(FadeIn(box), run_time=0.3)
    self.play(box.animate.move_to([0, -2.05 + k * 0.85, 0]), run_time=0.5)
    items.add(box)
"""), ("Pop takes from the top: the last one in is the first one out.", """
self.play(items[-1].animate.shift(RIGHT * 4), run_time=0.8)
tag = Text("pop() -> C", font_size=30, color=PALETTE["GOLD"]).move_to([4.2, 0.4, 0])
self.play(Write(tag))
"""))

kind("logic_gates", "Logic gate with its truth table", "computing",
     "AND, OR, NOT: how a circuit decides, and its table of every input",
     ("An AND gate: two inputs, one output.", """
body = VGroup(Line([-2.6, 1.0, 0], [-1.6, 1.0, 0], color=INK, stroke_width=5), Line([-2.6, -1.0, 0], [-1.6, -1.0, 0], color=INK, stroke_width=5),
              Line([-2.6, 1.0, 0], [-2.6, -1.0, 0], color=INK, stroke_width=5), Arc(radius=1.0, start_angle=-PI / 2, angle=PI, arc_center=[-1.6, 0, 0], color=INK, stroke_width=5))
wires = VGroup(Line([-4.2, 0.5, 0], [-2.6, 0.5, 0], color=INK), Line([-4.2, -0.5, 0], [-2.6, -0.5, 0], color=INK), Line([-0.6, 0, 0], [0.6, 0, 0], color=INK))
names = VGroup(MathTex("A", color=INK).next_to([-4.2, 0.5, 0], LEFT), MathTex("B", color=INK).next_to([-4.2, -0.5, 0], LEFT),
               MathTex("Q", color=INK).next_to([0.6, 0, 0], RIGHT))
self.play(Create(body), Create(wires), Write(names))
"""), ("The output is one only when both inputs are one.", """
rows = [("A", "B", "Q"), ("0", "0", "0"), ("0", "1", "0"), ("1", "0", "0"), ("1", "1", "1")]
table = VGroup(*[VGroup(*[MathTex(v, font_size=36, color=PALETTE["GOLD"] if r == 4 else INK) for v in row]).arrange(RIGHT, buff=0.7) for r, row in enumerate(rows)]).arrange(DOWN, buff=0.3)
table.move_to([4.4, 0, 0])
rule = Line(table[0].get_corner(DL) + DOWN * 0.12, table[0].get_corner(DR) + DOWN * 0.12, color=MUTED_INK)
self.play(Write(table), Create(rule))
"""))

kind("weighted_graph", "Weighted graph and shortest path", "computing",
     "routes and networks: shortest path, cheapest connection",
     ("Five towns and the roads between them, with distances.", """
pos = {"A": [-5, 0], "B": [-2, 1.9], "C": [-2, -1.9], "D": [1.5, 0.6], "E": [4.8, -0.4]}
roads = [("A", "B", 4), ("A", "C", 2), ("B", "D", 5), ("C", "D", 8), ("C", "B", 1), ("D", "E", 3), ("C", "E", 10)]
towns = {k: VGroup(Circle(radius=0.38, color=INK, fill_color=BACKGROUND, fill_opacity=1), Text(k, font_size=30, color=INK)).move_to([x, y, 0]) for k, (x, y) in pos.items()}
lines = {}
weights = VGroup()
for a, b, w in roads:
    lines[(a, b)] = Line(towns[a].get_center(), towns[b].get_center(), color=MUTED_INK, stroke_width=4, buff=0.38)
    weights.add(MathTex(str(w), font_size=32, color=INK).move_to(lines[(a, b)].get_center() + UP * 0.25))
self.play(*[Create(l) for l in lines.values()], *[FadeIn(t) for t in towns.values()], Write(weights))
"""), ("The shortest way from A to E: A, C, B, D, E, eleven in all.", """
path = [("A", "C"), ("C", "B"), ("B", "D"), ("D", "E")]
for edge in path:
    self.play(lines[edge].animate.set_color(PALETTE["GOLD"]).set_stroke(width=8), run_time=0.5)
total = MathTex("2 + 1 + 5 + 3 = 11", font_size=40, color=PALETTE["GOLD"]).move_to([1.5, -2.4, 0])
self.play(Write(total))
"""))


def script(style: str = "chalkboard") -> dict:
    """Every kind as one lecture: a chapter a kind, its beats as written."""
    chapters = []
    for entry in CATALOG:
        beats = [{"say": say, "do": [{"op": "manim", "id": entry["id"], "code": code.strip()}]}
                 for say, code in entry["beats"]]
        chapters.append({"title": entry["name"], "map": False, "beats": beats})
    return {"title": "Diagrams in free Manim", "style": style, "auto_visuals": False, "place_figures": False,
            "teaching_rules": False, "chapters": chapters}


def listing() -> str:
    """The kinds, one a line, for the script writer's prompt."""
    return "\n".join(f"{e['name']} ({e['subject']}): {e['use']}" for e in CATALOG)


if __name__ == "__main__":
    if "--script" in sys.argv:
        print(json.dumps(script(), indent=1, ensure_ascii=False))
    else:
        print(listing())
