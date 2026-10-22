# The kit

Building blocks for explainer videos in Manim, drawn in a **look** (`vox`: paper, collage, marker; `blueprint`:
drafting grid, outlines, mono type). Optional: use any of it, none of it, or take pieces apart and restyle them.
Every piece is an ordinary Manim mobject (a `VGroup`, or a `Group` when it holds a picture) and every helper returns an
ordinary Manim animation, so plain Manim works beside it everywhere.

```python
from kit import *                       # the kit and all of manim

class Chapter(KitScene):                # NarratedScene + MovingCameraScene + the look's stage
    look = "vox"                        # or "blueprint", or look("vox", accent="#2A9D8F")
    def construct(self):
        self.until(self.at(0, "Japan"), lead=0.2)   # hold until 0.2 s before "Japan" in line 0
        m = Map("east asia"); self.play(m.appear())
        self.play(m.shade("Japan"))
        self.play(self.cam_to(m.view("Japan")))     # the camera frames Japan
        self.clear_stage()
        self.wait_until_end()
```

**See before you use**: the `kit_preview` tool renders any snippet (the body of `construct`, `self` is the scene) in a
look and shows you the frame and a sheet of frames. Read a piece's source with
`python -c "import inspect, kit.maps as m; print(inspect.getsource(m.Map))"`.

Every piece has `.appear(how=None, run=None)`, `.disappear(how=None)`, `.emphasize(how=None)` (its own entrance, exit
and emphasis in the look) and named parts: `piece.part("title")`, `piece.parts`.

## KitScene
| | |
|---|---|
| `look = "vox"` | the class's look (set before construct) |
| `self.at(n, word, occurrence=0)` | when `word` is said in line n (seconds) |
| `self.until(t, lead=0)` | hold until `lead` s before t |
| `self.word / phrase / line / wait_until / wait_until_end / now` | NarratedScene's own |
| `self.cam_to(target, width=None, zoom=None, run=1.5)` | camera to a point or mobject (framing it); returns an animation |
| `self.cam_reset(run)` · `self.cam_push(k=1.12, run=4)` · `self.cam_pan(vector)` | back home · slow push in · pan |
| `self.camera_drift(speed=0.02, zoom=0.004)` | the camera creeps on its own from now on (0 stops); `drift = 0.02` on the class starts it |
| `self.clear_stage(how="fade", keep=())` | everything off but the stage |
| `self.wipe(color=None, direction=RIGHT, then=None)` | a panel sweeps across, the stage is cleared (and `then` put on) behind it |
| `self.frame` · `self.backdrop` | the camera frame · the look's stage (kept on the camera) |

## Looks
`use("blueprint")`, `look("vox", accent=..., mark=..., palette=(...))`, `with looking("blueprint"): ...`, `L()` the
current look (`L().accent`, `L().mark`, `L().ink`, `L().muted`, `L().bg`, `L().color(i)` the i-th series colour,
`L().head` / `body` / `hand` / `serif` / `mono` fonts). A look sets colours, fonts (Latin, Devanagari, CJK), cards,
shadows, tilt, map colours, photo treatment and motion (its default entrances, easing, overshoot, stagger).

## Text
| | |
|---|---|
| `text(s, size=30, role="body", color=None, weight=None, width=None, italic=False, align="left")` | words in the look's font for their script (Hindi in Hind, Chinese/Japanese in WenQuanYi); `width` wraps; role: body, head, serif, hand, mono |
| `headline(s, size=56, mark=True)` | the look's headline (vox: condensed capitals, a highlighter swept behind; blueprint: mono, a ruled line); appears by sweeping |
| `kicker(s)` | the small spaced line above a headline |
| `label(s, size=22, backing=True)` | a small label on a backing (readable over maps and lines) |
| `quote(s, who=None, width=9)` | a quotation with a big quote mark |
| `caption(s)` | a lower-third band |
| `title_card(title, kick=None, sub=None)` | a chapter opening |
| `n = number("1,869"); self.play(count(n))` | a figure counting up to itself (prefixes and suffixes kept: "₹2.4", "60%") |
| `fit(mob, width, height)` | shrink to fit |

## Marks (point at something; they stay)
`highlight(m)` · `circle(m)` · `underline(m)` · `strike(m)` · `box(m)` · `arrow(a, b, curve=0.35, label_text=None)`
(a, b: mobjects or points) · `callout(target, "words", side=None)` (a note with a leader line) ·
`bracket(group, "words", side=RIGHT)` · `stamp("OFFICIAL", angle=-12)` · `tick()` · `cross()` ·
`dimension(a, b, "1,200 km")` (a drafting measure) · `spotlight(m, dim=0.6)` (everything else veiled).
Vox draws them by hand (wobbly marker lines); blueprint as drafting marks. `self.play(mark.appear())` draws one on.

## Motion
| | |
|---|---|
| `enter(m, how, side=None, run=None)` | fade, rise, drop, slide, pop, grow, grow_left, grow_up, draw, write, type, unfold, unfold_down, zoom, spin, stamp, spring, instant |
| `leave(m, how)` | fade, sink, lift, slide, shrink, zoom, unwrite, uncreate, instant |
| `emph(m, how, color=None)` | pulse, wiggle, shake, flash, bounce, tint (lasting marks: use Marks) |
| `stagger(items, how=None, lag=0.12)` | one after another, overlapping (items: mobjects or animations) |
| `chain(anims)` · `together(anims)` · `later(anim, delay)` | in sequence · at once · starting late |
| `drift(m, speed=0.04, zoom=0.006)` · `bob(m)` · `stop_drift(m)` | idle motion while on screen (keep it for short holds: idle motion costs phone bytes) |

## Cards and things on the page
| | |
|---|---|
| `card(w, h, title=None, body=None, kick=None, content=None, tilt=0)` | a card (vox: paper with a shadow; blueprint: an outlined panel with corner ticks) |
| `chip(s, color)` · `tag(s)` · `sticky(s)` | a pill · a luggage tag / spec label · a sticky note |
| `document(title, lines=9, seal="史", vertical=None)` | a page of text with an optional red seal; Chinese/Japanese titles in vertical columns |
| `clipping(headline, masthead=None, date=None)` | a torn newspaper clipping |
| `book(title, color, author=None)` · `shelf(["Vol 1", ...])` | a book cover · spines on a shelf |
| `scroll(title, width=6.5)` | a handscroll that unrolls |
| `portrait(name, years, picture=None, role=None)` | a portrait card: picture a file (treated in the look), a mobject such as `person(...)`, or None (a silhouette) |
| `stat("60%", "of sources are official")` | a big figure with its meaning; `count(card.part("number"))` |
| `l = checklist(items, marker="dot"/"number"/"tick")` | a list; `l.reveal(i)` brings on one row |
| `panel(w, h)` · `shadow_of(shape)` | a bare card surface · a soft shadow |

## People and icons
`person(hair="short", hat=None, beard=None, glasses=False, clothes="suit", skin="medium", silhouette=False)`:
hair short/bald/long/topknot/tonsure/side/bun · hat official (Chinese official's winged cap)/scholar/cap/top/bowler/
turban · beard mustache/goatee/long/full · clothes suit/robe/kimono/cassock/shirt/uniform · skin light/medium/tan/
brown/dark or a colour. Parts: head, hair, hat, beard, glasses, body, face.
`figure(color)` a small standing figure · `crowd(n, rows=1)`.
`icon("ship", size=1, style=None)`: about 30,000 icons by name (vox: colour drawings; blueprint: silhouettes);
`icon_names("printing")` lists what there is.

## Pictures
`photo(path, height=3.5, how=None, frame=None, tilt=None, tape=None, caption=None)`: a picture treated in the look:
`how` cutout (black and white on paper) / bw / color / duotone (blueprint) / halftone / sepia; `frame` torn / sticker /
polaroid / border / none; a soft shadow drawn in.
`commons("Matteo Ricci portrait")` or `commons("File:Ricciportrait.jpg")`: a freely licensed picture from Wikimedia
Commons into `assets/` (its licence and source beside it as JSON); `commons_search(q)` lists candidates.
Pictures you make with make_image are in `assets/` too.

## Maps
```python
m = Map("east asia", names=False, year=None)  # REGIONS: world, east asia, china, japan, korea, india, south asia,
                                              # southeast asia, middle east, europe, mediterranean, africa, eurasia,
                                              # silk road, europe to china, central asia, russia, americas, ...
m = Map(bounds=(lon0, lat0, lon1, lat1))      # any box; year=1600 draws the states of then (historical borders)
```
`m.shade(name, color)` · `m.dim(keep=[...])` · `m.outline(name)` (traced) · `m.country(name)` (its shapes) ·
`m.country_label(name)` · `m.pin(place, label_text=None, side=RIGHT)` (place: a name such as "Edo", "Kaifeng",
"Constantinople", or (lon, lat)) · `m.route([stops], curve=0.12)` (`.appear(run=4)` draws it; `.travel(run, marker=)`
sends a marker along) · `m.empire("Song", 1100)` (a state's extent then) · `m.area([(lon, lat), ...])` ·
`m.point(lon, lat)` / `m.place_point(name)` (where it is now, after any move or scale) · `m.view(*names)` (a box to
give `cam_to`). Move or scale the map first; what you make from it afterwards is placed where it then stands.

## Timelines
```python
tl = Timeline(1200, 1950, width=12).shift(UP)   # negative years are BCE; place it first
tl.event(1869, "Meiji history bureau")          # a card on a stem, kept clear of the others (above, else below)
tl.span(960, 1279, "Song dynasty")              # a band along the axis
tl.lifespan("Marco Polo", 1254, 1324, stay=(1274, 1290, "in China"))   # a bar in rows under the axis
mk = tl.marker(1500, "here"); self.play(mk.move(1800))
tl.x(1600)                                      # where a year is
```

## Charts
`bars({name: value}, unit="", vertical=False)` (`.highlight(name)`) · `donut({name: value}, centre=None)`
(`.pop(name)`) · `units(100, 23, label=..., shape="square"/"dot"/"person")` (`.fill()`) ·
`line_chart([(x, y), ...] or [[...], [...]], names=[...])` · `versus("Insiders", [...], "Outsiders", [...])`.
Each builds itself with `.appear()` (bars grow, values count up, lines draw).

## Diagrams
Node specs: `"Name"` or `{"name": ..., "label": ..., "shape": box|pill|circle|diamond, "key": True, "icon": "scroll"}`.
| | |
|---|---|
| `Flow(nodes, edges, direction="right")` | layered left to right (or down); edges `(a, b)` or `(a, b, "label")` |
| `Tree({"root": {"child": {...}}})` | top down, elbow connectors |
| `Cycle(items)` · `Hub(centre, items)` · `Chain(items)` | round a circle · spokes · cause and effect |
| `Network(nodes, edges, layout="spring")` | who influenced whom |
| `Pyramid(levels, inverted=False)` | levels top down |
Verbs: `.appear()` (in order, edges once both ends are on) · `.reveal(*names)` (only these, as the voice names them) ·
`.focus(*names)` / `.unfocus()` · `.pulse(a, b)` (a dot along an edge) · `.node(name)` · `.edge(a, b)`.

## Layout
`place(m, "left")` (zones: full, center, left, right, top, bottom, left_third, middle_third, right_third,
left_two_thirds, right_two_thirds, upper_left, upper_right, lower_left, lower_right, title, body) · `row(items, gap)` ·
`column(items, gap)` · `grid(items, cols)` · `fit_to(m, w, h)` · `keep_in_frame(m, frame=self.frame)` ·
`separate(labels)` (pushes overlapping ones apart) · `overlaps(mobs)` · `spread(mobs, start, end)` ·
`edge_point(m, direction)`.

## On the phone
All of it plays on the phone as Manim draws it (the faithful export records every frame of motion). Stills cost
nothing; motion costs bytes, so idle drift through long holds and huge point counts make the program big. The look's
stage is one picture, sent once.
