"""Compile: validated chapter scripts -> one Manim scene file per chapter.

The output is ordinary pocket_lecture code: the style pack registered as an
engine theme, the region pack's focus and anchors as class attributes, and
one `self.beat(...)` per beat with an engine call per operation. Operations
name places, anchors and units; this stage turns every name into lon/lat
once, so a scene never looks anything up at render time.

`chapter_lines` is the single list of what each scene says, in order. The
narrate stage speaks exactly these lines, so every beat finds its audio in
the cache when the scene renders.
"""

from __future__ import annotations

import math

from forge import ENGINE_VERSION, region, registry
from forge.util import LECTURE, digest, write_json

MAP_OPS = {name for name, spec in registry.ops().items() if spec.get("map")}


def _title(name: str) -> str:
    return str(name).replace("_", " ").title() if "_" in str(name) or str(name).islower() else str(name)


def is_prologue(chapter: dict) -> bool:
    return chapter["slot"] in ("prologue", "intro") or "title" in chapter.get("required", [])


def is_recap(chapter: dict, script: dict) -> bool:
    return chapter["slot"] == "recap" or "recap" in chapter.get("required", []) or bool(script.get("recap"))


def numbering(outline: dict) -> dict:
    """Chapter id -> the number on its card. The prologue has a title slide, not a number."""
    out, n = {}, 0
    for chapter in outline["chapters"]:
        if is_prologue(chapter):
            out[chapter["id"]] = 0
        else:
            n += 1
            out[chapter["id"]] = n
    return out


def card_line(num: int, title: str) -> str:
    return f"Chapter {num}. {title}."


def recap_cards(points) -> list[tuple[str, str]]:
    return [(p[0], p[1]) for p in points]


def recap_lines(points) -> list[str]:
    """The spoken line per recap card: the whole sentence when the point carries one."""
    return [f"{p[0]}. {(p[2] if len(p) > 2 else p[1]).rstrip('.…')}." for p in points]


def caption(beat: dict) -> str:
    return beat.get("say_caption") or beat["say"]


def title_line(job) -> str:
    spec = job.spec
    return f"{spec['title']}. {spec['subtitle']}." if spec.get("subtitle") else f"{spec['title']}."


def chapter_lines(job, chapter: dict, script: dict, outline: dict) -> list[str]:
    """Every line the chapter's scene will speak, in order."""
    lines = []
    beats = list(script.get("beats", []))
    if is_prologue(chapter):
        if beats:
            lines.append(caption(beats.pop(0)))
        else:
            lines.append(title_line(job))
    else:
        lines.append(card_line(numbering(outline)[chapter["id"]], chapter["title"]))
    lines += [caption(b) for b in beats]
    if script.get("recap"):
        lines += recap_lines(script["recap"])
    return lines


def line_ids(chapter: dict, script: dict) -> list[str]:
    """The id of each line chapter_lines returns: beat ids, 'card', and r1.. for recap cards."""
    ids = [] if is_prologue(chapter) else ["card"]
    ids += [b.get("id", f"b{i + 1:02d}") for i, b in enumerate(script.get("beats", []))]
    if is_prologue(chapter) and not script.get("beats"):
        ids.append("title")
    ids += [f"r{i + 1}" for i in range(len(script.get("recap") or []))]
    return ids


# ════════════════════════════════════════════════════════════════════════
#  Places
# ════════════════════════════════════════════════════════════════════════

class Places:
    """Names to lon/lat for one job's region, and where each unit stands."""

    def __init__(self, region_id: str | None):
        self.region_id = region_id
        self.pack = region.load(region_id) if region_id else {}
        self.anchors = {k: tuple(v) for k, v in (self.pack.get("anchors") or {}).items()}
        self.features = dict(((self.pack.get("features") or {}).get("paths") or {}))
        self.units = {u["id"]: dict(u) for u in ((self.pack.get("battlefield") or {}).get("units") or [])}
        self.pos: dict[str, tuple] = {}
        self.figures: dict[str, dict] = {}
        self.photos: dict[str, dict] = {}      # Commons rows used, for the credits
        self.icons: set[str] = set()

    def lonlat(self, where):
        if isinstance(where, (list, tuple)) and len(where) == 2:
            return (float(where[0]), float(where[1]))
        if where in self.pos:
            return self.pos[where]
        if where in self.anchors:
            return self.anchors[where]
        found = region.lookup(str(where), self.region_id)
        if not found:
            raise KeyError(f"no place {where!r}")
        return tuple(found["lonlat"])

    def toward(self, uid: str, where, share: float = 0.7):
        """A point `share` of the way from a unit to a place or another unit."""
        start = self.pos.get(uid) or self.lonlat(self.units.get(uid, {}).get("at", where))
        end = self.lonlat(where)
        return (round(start[0] + (end[0] - start[0]) * share, 5), round(start[1] + (end[1] - start[1]) * share, 5))

    def away(self, uid: str):
        """The direction a unit breaks: away from the units of the other side."""
        side = self.units.get(uid, {}).get("side", "enemy")
        me = self.pos.get(uid)
        others = [p for u, p in self.pos.items() if u != uid and self.units.get(u, {}).get("side") not in (side, "ally")]
        if not me or not others:
            return (0.0, -1.0)
        cx = sum(p[0] for p in others) / len(others)
        cy = sum(p[1] for p in others) / len(others)
        dx, dy = me[0] - cx, me[1] - cy
        norm = math.hypot(dx, dy) or 1.0
        return (round(dx / norm, 3), round(dy / norm, 3))


def _ll(p) -> str:
    return f"({p[0]:.5f}, {p[1]:.5f})"


def _tone(op: dict, default: str | None = None, key: str = "tone") -> str | None:
    tone = op.get(key) or default
    return f"role({tone!r})" if tone else None


def op_call(op: dict, places: Places, has_map: bool) -> str | None:
    """The engine call for one operation, or None when it has no place here."""
    kind = op["op"]
    if kind in MAP_OPS and not has_map:
        return None
    if kind == "panel":
        sub = f", {op['sub']!r}" if op.get("sub") else ""
        return f"self.panel_title({op['title']!r}{sub})"
    if kind == "fact":
        tone = _tone(op)
        return f"self.fact({op['text']!r}" + (f", {tone}, {tone}" if tone else "") + ")"
    if kind == "stat":
        tone = _tone(op)
        return f"self.big_stat({str(op['value'])!r}, {op['label']!r}" + (f", {tone}" if tone else "") + ")"
    if kind == "bars":
        items = [(str(label), float(value)) for label, value in op["items"]][:6]
        return f"self.bar_chart({items!r}, {_tone(op) or 'None'}, {op.get('unit', '')!r})"
    if kind == "compare":
        return (f"self.compare({tuple(op['left'])!r}, {tuple(op['right'])!r}, "
                f"{op.get('left_tone', 'friendly')!r}, {op.get('right_tone', 'enemy')!r})")
    if kind == "timeline" and op.get("where") == "stage":
        events = [(str(d), str(label)) for d, label in op["events"]][:7]
        title = f", {op['title']!r}" if op.get("title") else ""
        return f"self.big_timeline({events!r}{title})"
    if kind == "molecule":
        return f"self.molecule({op['name']!r}" + (f", {op['label']!r}" if op.get("label") else "") + ")"
    if kind == "equation":
        return f"self.equation({op['tex']!r}" + (f", {op['label']!r}" if op.get("label") else "") + ")"
    if kind == "plot":
        exprs = op.get("exprs") or [op["expr"]]
        x = op.get("x") or [-5, 5]
        return (f"self.plot({[str(e) for e in exprs]!r}, ({float(x[0])}, {float(x[1])}), {op.get('label')!r}, "
                f"{op.get('x_label', 'x')!r}, {op.get('y_label', 'y')!r}, {list(op.get('names') or [])!r})")
    if kind == "process":
        return (f"self.process({[str(x) for x in op['steps']][:8]!r}, {op.get('title')!r}, "
                f"cycle={bool(op.get('cycle'))})")
    if kind == "quote":
        return f"self.quote({op['text']!r}, {op.get('who', '')!r})"
    if kind == "timeline":
        events = [(str(d), str(label)) for d, label in op["events"]][:6]
        return f"self.timeline({events!r}, {op.get('tone', 'accent')!r})"
    if kind == "network":
        nodes = [n if isinstance(n, str) else list(n) for n in op["nodes"]]
        edges = [list(e) for e in op.get("edges") or []]
        return f"self.network({nodes!r}, {edges!r}, {op.get('tone', 'accent')!r})"
    if kind == "clear":
        return "self.clear_panel()"
    if kind == "marker":
        where = places.lonlat(op["place"])
        label = op.get("label") or (_title(op["place"]) if isinstance(op["place"], str) else "")
        d = {"left": "LEFT", "right": "RIGHT", "up": "UP", "down": "DOWN"}.get(op.get("side"), "RIGHT")
        return f"self.mark({_ll(where)}, {label!r}, {_tone(op) or 'None'}, {d})"
    if kind == "river":
        return f"self.river({op['name']!r}, {_tone(op, 'water')})"
    if kind == "path":
        points = op["points"]
        if isinstance(points, str):
            points = places.features[points]
        pts = [places.lonlat(p) for p in points]
        return f"self.path([{', '.join(_ll(p) for p in pts)}], {_tone(op, 'highlight')})"
    if kind == "route":
        pts = [places.lonlat(p) for p in op["points"]]
        labels = op.get("labels")
        return f"self.route([{', '.join(_ll(p) for p in pts)}], {op.get('tone', 'accent')!r}, {labels!r})"
    if kind == "state":
        return f"self.fill_state({op['name']!r}, {_tone(op, 'accent')}, {float(op.get('opacity', 0.6)):g})"
    if kind == "dim":
        return f"*self.dim(opacity={float(op.get('opacity', 0.15)):g})"
    if kind == "graticule":
        axis = f"lat={float(op['lat']):g}" if op.get("lat") is not None else f"lon={float(op['lon']):g}"
        label = f", label={op['label']!r}" if op.get("label") else ""
        return f"self.graticule({axis}, color={_tone(op, 'muted')}{label})"
    if kind == "unit":
        uid = op["id"]
        known = places.units.get(uid, {})
        spec = {**known, **{k: v for k, v in op.items() if k != "op"}}
        at = places.lonlat(spec.get("at") or uid)
        places.pos[uid] = at
        places.units.setdefault(uid, spec)
        strength = f", strength={spec['strength']!r}" if spec.get("strength") else ""
        return (f"self.unit({uid!r}, {_ll(at)}, {spec.get('label') or _title(uid)!r}, "
                f"{spec.get('side', 'friendly')!r}, {spec.get('kind', 'infantry')!r}{strength})")
    if kind in ("move", "charge"):
        uid = op["unit"]
        share = 0.7 if op["to"] in places.units else 1.0
        target = places.toward(uid, op["to"], share)
        places.pos[uid] = target
        method = "move_unit" if kind == "move" else "charge"
        return f"self.{method}({uid!r}, {_ll(target)})"
    if kind == "rout":
        return f"self.rout({op['unit']!r}, {places.away(op['unit'])!r})"
    if kind == "volley":
        to = op.get("to")
        target = "None" if to is None else (repr(to) if to in places.pos else _ll(places.lonlat(to)))
        return f"self.volley({op['from']!r}, {target}, {op.get('tone', 'highlight')!r})"
    if kind == "icon":
        import icons

        found = icons.resolve(str(op.get("name", "")))
        if found:
            places.icons.add(found)
        tone = _tone(op)
        extra = (f", {tone}" if tone else ", None")
        if op.get("places") and has_map:
            spots = ", ".join(_ll(places.lonlat(p)) for p in op["places"])
            size = f", size={float(op['size']):g}" if op.get("size") else ""
            label = f", label={op['label']!r}" if op.get("label") else ""
            return f"self.icon({op['name']!r}, [{spots}]{extra}{size}{label})"
        return f"self.panel_icon({op['name']!r}, {op.get('label', '')!r}{extra})"
    if kind == "photo":
        import images

        row = images.fetch(op.get("image"), op.get("query"), op.get("subject"))
        if not row:
            raise KeyError(f"no reusable photo for {op.get('image') or op.get('subject') or op.get('query')!r}")
        places.photos[row["id"]] = row
        where = op.get("where", "stage")
        if where == "stage":
            return f"self.stage_image({row['file']!r}, {op.get('caption', '')!r}, credit={row['credit']!r})"
        return f"self.figure({row['file']!r}, {op.get('caption', '')!r}, where={where!r})"
    if kind == "illustration":
        import icons

        items = [(i, "") if isinstance(i, str) else (i[0], i[1] if len(i) > 1 else "") for i in op.get("items") or []]
        for name in [op["icon"]] + [i[0] for i in items]:
            found = icons.resolve(name)
            if found is None:
                raise KeyError(f"no icon for {name!r}")
            places.icons.add(found)
        title = f", title={op['title']!r}" if op.get("title") else ""
        color = f", color={_tone(op)}" if _tone(op) else ""
        return f"self.illustration({op['icon']!r}, {items!r}{title}{color})"
    if kind == "figure":
        figure = places.figures.get(op["id"])
        if not figure:
            raise KeyError(f"no figure {op['id']!r}")
        caption = op.get("caption") or figure.get("caption", "")
        return f"self.figure({figure['file']!r}, {caption!r}, where={op.get('where', 'stage')!r})"
    if kind == "clock":
        return f"self.clock({op['time']!r})"
    if kind == "highlight":
        target = op["target"]
        return f"self.highlight({target!r})" if target in places.pos else f"self.highlight({_ll(places.lonlat(target))})"
    raise ValueError(f"no engine call for operation {kind!r}")


# ════════════════════════════════════════════════════════════════════════
#  Scenes
# ════════════════════════════════════════════════════════════════════════

def class_name(chapter_id: str) -> str:
    return chapter_id.upper()


def points_at_map(op: dict) -> bool:
    return op.get("op") in MAP_OPS or (op.get("op") == "icon" and bool(op.get("places")))


STAGE_OPS = {"photo", "illustration", "molecule", "equation", "plot", "process", "quote"}


def chapter_source(job, template: dict, style: dict, outline: dict, chapter: dict, script: dict,
                   places: "Places | None" = None) -> str:
    spec = job.spec
    region_id = spec.get("region_id")
    places = places or Places(region_id)
    places.figures = {f["id"]: f for f in (job.read("bundle.json") or {}).get("figures", [])}
    layout = (template.get("layouts") or {}).get(chapter.get("layout") or "", {}) or {}
    # The map is drawn only when a beat points at it; every other chapter is
    # carried by the stage: photos, figures, illustrations.
    has_map = bool(region_id) and layout.get("map", True) and any(
        points_at_map(op) for b in script.get("beats", []) for op in b.get("do", []))
    battlefield = has_map and layout.get("zoom") == "battlefield" and (places.pack.get("battlefield") or {}).get("bbox")
    numbers = numbering(outline)
    sections = ["Introduction"] + [c["title"] for c in outline["chapters"] if not is_prologue(c)]
    theme = registry.engine_theme(style)
    style_key = f"forge_{style['id']}"
    lexicon = job.lexicon
    focus = dict(places.pack.get("focus") or {}) if region_id else {}
    base = "MapLecture"             # its layout: map or stage on the left, the panel on the right
    cls = class_name(chapter["id"])

    out = [
        f'"""{spec["title"]} -- {chapter["id"]}: {chapter["title"]}.',
        "",
        f"Compiled by Lecture Forge {ENGINE_VERSION} from script/{chapter['id']}.json",
        f"(template {template['id']} {template.get('version', '')}, style {style['id']} {style.get('version', '')}).",
        'Edit the script and re-run `forge make`, not this file."""',
        "import sys",
        "",
        f"sys.path.insert(0, {str(LECTURE)!r})",
        "",
        "from manim import *  # noqa: E402,F403",
        "from pocket_lecture import *  # noqa: E402,F403",
        "import pocket_lecture as pl  # noqa: E402",
        "",
        f"pl.register_style({style_key!r}, {theme!r})",
        f"pl.use_style({style_key!r})",
        f"pl.SAY.update({lexicon!r})",
        "",
        "",
        f"class {cls}({base}):",
    ]
    if has_map:
        out.append(f"    REGION = {focus!r}")
        out.append(f"    ANCHORS = {({k: list(v) for k, v in places.anchors.items()})!r}")
    out.append(f"    SECTIONS = {sections!r}")
    out += ["", "    def construct(self):"]
    body = []
    beats = list(script.get("beats", []))

    def stage():
        if battlefield:
            body.append(f"self.use_frame({tuple(battlefield)!r})")
        body.append("self.show_map()" if has_map else "self.add_panel()")

    if is_prologue(chapter):
        first = beats.pop(0) if beats else {"say": title_line(job)}
        # The slot's purpose is a note to the planner ("Hook the viewer"), not a subtitle.
        slot_note = next((a.get("purpose") for a in template.get("arc", []) if a["id"] == chapter["slot"]), None)
        planned = chapter.get("purpose") if chapter.get("purpose") != slot_note else None
        sub = spec.get("subtitle") or planned or ""
        tag = (template.get("label") or "An illustrated lecture").upper()
        body.append(f"self.title_slide({spec['title']!r}, {sub!r}, tag={tag!r}, narration={caption(first)!r})")
        if beats:
            stage()
    else:
        num = numbers[chapter["id"]]
        slot_note = next((a.get("purpose") for a in template.get("arc", []) if a["id"] == chapter["slot"]), None)
        sub = chapter.get("purpose") if chapter.get("purpose") != slot_note else ""
        body.append(f"self.chapter({num}, {chapter['title']!r}, {sub or ''!r}, "
                    f"{card_line(num, chapter['title'])!r})")
        if beats:
            stage()
    # Photos are fetched now (cached); one that cannot be found is dropped here,
    # so the automatic illustrations below fill its beat instead.
    import images

    for beat in beats:
        kept = []
        for op in beat.get("do", []):
            if op.get("op") == "photo" and not images.fetch(op.get("image"), op.get("query"), op.get("subject")):
                job.log(f"compile {chapter['id']}.{beat.get('id')}: no photo for {op.get('image') or op.get('query')!r}")
                continue
            kept.append(op)
        beat["do"] = kept
    from compile_lecture import auto_visuals   # harness/lecture: the editor's rule for bare beats

    fills = auto_visuals({"beats": beats, "title": chapter.get("title", "")}, points_at_map, spec.get("genre"))
    staged = False
    for index, beat in enumerate(beats):
        calls = []
        # Panel heads first: the engine clears the old panel when the head is built.
        ordered = sorted(beat.get("do", []), key=lambda o: o.get("op") not in ("panel", "clear"))
        if index < len(fills) and fills[index]:
            ordered.append(fills[index])
        if staged and has_map and any(points_at_map(op) for op in ordered):
            calls.append("self.clear_stage()")
            staged = False
        if any(op.get("op") in STAGE_OPS or (op.get("op") == "figure" and op.get("where", "stage") == "stage")
               or (op.get("op") == "timeline" and op.get("where") == "stage") for op in ordered):
            staged = True
        for op in ordered:
            try:
                call = op_call(op, places, has_map)
            except (KeyError, ValueError) as error:
                job.log(f"compile {chapter['id']}.{beat.get('id')}: skipped {op.get('op')}: {error}")
                continue
            if call:
                calls.append(call)
        args = "".join(f",\n                  {c}" for c in calls)
        body.append(f"# {beat.get('id', '')}")
        body.append(f"self.beat({caption(beat)!r}{args})")
    if beats:
        body.append("self.outro_fade()")
    if script.get("recap"):
        points = script["recap"]
        body.append(f"self.recap({recap_cards(points)!r}, narration={recap_lines(points)!r})")
    out += ["        " + line for line in body]
    return "\n".join(out) + "\n"


def compile_job(job, template: dict, style: dict) -> dict:
    """Write build/<chapter>.py for every chapter; return {chapter: {file, class, digest}}.

    Photos and icons are credited at the end of the last chapter and in
    build/credits.json, which the deliver stage turns into out/credits.txt.
    """
    import icons
    import images

    outline = job.read("outline.json")
    build = job.path("build")
    build.mkdir(exist_ok=True)
    manifest = {}
    places = Places(job.spec.get("region_id"))
    scripts = {c["id"]: job.script(c["id"]) for c in outline["chapters"]}
    # Every figure of the sources is shown somewhere: the ones no beat asked
    # for go where the narration talks about them (harness/lecture's rule).
    figures = {f["id"]: f for f in (job.read("bundle.json") or {}).get("figures", [])}
    if figures:
        from compile_lecture import place_figures

        placed = place_figures({"figures": figures, "chapters": [scripts[c["id"]] for c in outline["chapters"]]})
        if placed:
            job.log(f"compile: placed {placed} source figure(s) no beat showed")
    sources = {}
    for chapter in outline["chapters"]:
        sources[chapter["id"]] = chapter_source(job, template, style, outline, chapter, scripts[chapter["id"]], places)
    credits = {"photos": images.credit(places.photos.values()), "icons": icons.credit(places.icons)}
    write_json(build / "credits.json", {**credits, "rows": list(places.photos.values())})
    if credits["photos"] and outline["chapters"]:
        last = outline["chapters"][-1]["id"]
        line = "Map data: Natural Earth · Animation: Manim" if job.spec.get("region_id") else "Animation: Manim"
        sources[last] += f"        self.credits({line!r}, extra={credits['photos']!r})\n"
    for chapter in outline["chapters"]:
        source = sources[chapter["id"]]
        path = build / f"{chapter['id']}.py"
        if not path.exists() or path.read_text(encoding="utf-8") != source:
            path.write_text(source, encoding="utf-8")
        manifest[chapter["id"]] = {"file": str(path), "class": class_name(chapter["id"]),
                                   "digest": digest(source)}
    write_json(build / "manifest.json", manifest)
    return manifest
