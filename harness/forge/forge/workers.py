"""Model workers: planner, fact grounder, script writer, repairer.

Each has two implementations behind one function. With a model key, a
stateless LLM call with a cached prefix, read-only tools and a JSON schema.
Without one, a deterministic worker that reads the same inputs and writes the
same JSON -- so every stage after it runs, and is testable, with no network.
The offline workers never invent: every sentence they narrate is a sentence of
a source, every number on screen is one of those sentences' numbers.
"""

from __future__ import annotations

import json
import re

from forge import llm, patterns, region, registry, tools
from forge.util import NUMBER_RE, numbers_in, sentences, words

MONTHS = "January February March April May June July August September October November December".split()
STOP_NAMES = set(MONTHS) | {"The", "A", "An", "In", "On", "At", "By", "It", "He", "She", "They", "This", "That",
                             "These", "Those", "His", "Her", "Their", "Its", "But", "And", "Yet", "When", "After",
                             "Before", "During", "While", "Then", "There", "Here", "For", "With", "From", "As",
                             "Today", "Some", "Many", "Most", "One", "Two", "Three", "Chapter", "British", "French",
                             "English", "Indian", "Bengal", "Company", "East", "West", "North", "South"}
YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
TIME_RE = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.m\.|p\.m\.|am\b|pm\b|o'clock)|\b(noon|midday|midnight|dawn|dusk)\b",
                     re.I)
NAMED_TIMES = {"noon": (12, 0), "midday": (12, 0), "midnight": (0, 0), "dawn": (6, 0), "dusk": (18, 0)}


# ════════════════════════════════════════════════════════════════════════
#  Reading text
# ════════════════════════════════════════════════════════════════════════

def times_in(text: str) -> list[str]:
    """Clock times a sentence names, as HH:MM."""
    out = []
    for m in TIME_RE.finditer(text or ""):
        if m.group(4):
            h, mi = NAMED_TIMES[m.group(4).lower()]
        else:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            suffix = m.group(3).lower()
            if suffix.startswith("p") and h < 12:
                h += 12
            if suffix.startswith("a") and h == 12:
                h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            out.append(f"{h:02d}:{mi:02d}")
    return out


def names_in(text: str, corpus: str | None = None) -> list[str]:
    """Proper names: runs of capitalised words.

    A single word at a sentence start counts only when `corpus` (or the text)
    also has it capitalised mid-sentence -- "Clive now joined" is a name,
    "Around noon" is not. Possessives are dropped: Nawab's is Nawab.
    """
    corpus = corpus if corpus is not None else text
    out = []
    for m in re.finditer(r"\b([A-Z][a-z'’-]+(?:\s+(?:ud-|al-|de\s+|of\s+)?[A-Z][a-z'’-]+){0,2})", text or ""):
        name = re.sub(r"['’]s$", "", m.group(1).strip())
        first = name.split()[0]
        if first in STOP_NAMES and len(name.split()) == 1:
            continue
        starts = m.start() == 0 or re.search(r"[.!?:]\s*$", text[:m.start()])
        if starts and len(name.split()) == 1:
            if not re.search(r"[a-z,;]\s+" + re.escape(name) + r"\b", corpus or ""):
                continue
        name = re.sub(r"^(?:The|A|An)\s+", "", name)
        if name and name not in out:
            out.append(name)
    return out


def _quantities(sentence: str):
    """Numbers that are amounts: not years, not days of a month, not clock times."""
    for m in NUMBER_RE.finditer(sentence):
        after = sentence[m.end():m.end() + 12].strip().lower()
        before = sentence[:m.start()].rstrip().split(" ")[-1] if sentence[:m.start()].strip() else ""
        if YEAR_RE.fullmatch(m.group(1)) and not re.match(r"(men|guns|km|troops|soldiers|people)", after):
            continue
        if any(after.startswith(month.lower()) for month in MONTHS) or before in MONTHS:
            continue
        if re.match(r"(a\.m\.|p\.m\.|am\b|pm\b|o'clock|:\d)", after):
            continue
        yield m


class Context:
    """What a worker knows about the job's region, for the offline path."""

    def __init__(self, job, template: dict):
        self.job = job
        self.template = template
        spec = job.spec
        self.region_id = spec.get("region_id")
        self.pack = region.load(self.region_id) if self.region_id else None
        self.anchors = dict((self.pack or {}).get("anchors") or {})
        self.features = dict(((self.pack or {}).get("features") or {}).get("paths") or {})
        self.units = list(((self.pack or {}).get("battlefield") or {}).get("units") or [])
        self.places = [r["name"] for r in region.gazetteer(self.region_id)[:250]] if self.region_id else []
        self.rivers = region.rivers(self.region_id) if self.region_id else []

    def places_in(self, text: str) -> list[str]:
        found = []
        for name in list(self.anchors) + self.places:
            label = name.replace("_", " ")
            pattern = r"\b" + re.escape(label) + r"\b"
            m = re.search(pattern, text, re.I if "_" in name or name in self.anchors else 0)
            if m and name not in found:
                found.append((m.start(), name))
        return [n for _, n in sorted(found)]

    def rivers_in(self, text: str) -> list[str]:
        out = []
        aliases = {"Ganga": "Ganges"}
        for river in self.rivers:
            if re.search(r"\b" + re.escape(river) + r"\b", text):
                out.append(river)
        for alias, river in aliases.items():
            if re.search(r"\b" + alias + r"\b", text) and river in self.rivers and river not in out:
                out.append(river)
        return out

    def features_in(self, text: str) -> list[str]:
        return [f for f in self.features if re.search(r"\b" + re.escape(f.replace("_", " ")) + r"\b", text, re.I)]

    def unit_mentions(self, text: str) -> list[tuple[int, str]]:
        """(position, unit id) of each unit a sentence names: by id, label or alias."""
        hits = []
        for unit in self.units:
            found = []
            for key in [unit["id"].replace("_", " ")]:
                found += [m.start() for m in re.finditer(r"\b" + re.escape(key) + r"\b", text, re.I)]
            for key in [unit.get("label", "")] + list(unit.get("aliases") or []):
                if key:
                    found += [m.start() for m in re.finditer(r"\b" + re.escape(key) + r"\b", text)]
            hits += [(pos, unit["id"]) for pos in found]
        return sorted(hits)

    def units_in(self, text: str) -> list[str]:
        out = []
        for _, uid in self.unit_mentions(text):
            if uid not in out:
                out.append(uid)
        return out

    def side(self, uid: str) -> str:
        return next((u.get("side", "friendly") for u in self.units if u["id"] == uid), "friendly")


# ════════════════════════════════════════════════════════════════════════
#  Plan
# ════════════════════════════════════════════════════════════════════════

def _prefix(job, template: dict, style: dict, role: str) -> str:
    """The cached prefix: identical across calls for this template and style."""
    return "\n\n".join([
        f"You are the {role} of Lecture Forge. You write content into a template's structure. You never write "
        "styling or code. Reply with one JSON object and nothing else.",
        "TEMPLATE\n" + json.dumps(tools.call("template.describe", template=template["id"]), ensure_ascii=False),
        template["prompts"].get("planner" if role == "planner" else "writer", ""),
        "STYLE\n" + json.dumps(tools.call("style.vocabulary", style=style["id"], template=template["id"]),
                               ensure_ascii=False),
    ])


def plan(job, template: dict, style: dict, bundle: dict, notes: str = "") -> dict:
    spec = job.spec
    total_words = sum(words(p["text"]) for p in bundle["passages"])
    wpm = template.get("words_per_minute", 143)
    target = float(spec.get("target_minutes") or max(template["target_minutes"]["min"],
                                                     min(total_words / wpm * 1.25, template["target_minutes"]["max"])))
    if llm.available():
        system = _prefix(job, template, style, "planner")
        task = json.dumps({
            "brief": spec.get("brief", "")[:4000], "target_minutes": round(target, 1), "revision_notes": notes,
            "passages": [{"id": p["id"], "text": p["text"][:400]} for p in bundle["passages"]],
            "return": {"chapters": [{"slot": "arc slot id", "title": "2-4 words", "purpose": "...",
                                     "passages": ["p01"], "facts_needed": ["what numbers this chapter needs"]}],
                       "open_questions": ["..."], "lexicon": {"Name": "respelling"}},
        }, ensure_ascii=False)
        slots = {s["id"] for s in template["arc"]}
        known = {p["id"] for p in bundle["passages"]}

        def check(obj):
            problems = [f"unknown slot {c.get('slot')!r}" for c in obj.get("chapters", []) if c.get("slot") not in slots]
            problems += [f"unknown passage {p}" for c in obj.get("chapters", []) for p in c.get("passages", []) if p not in known]
            return problems or ([] if obj.get("chapters") else ["no chapters"])

        out = llm.ask(job, system, task, check=check)
        chapters = out["chapters"]
        open_questions = out.get("open_questions", [])
        if out.get("lexicon"):
            lex = job.lexicon
            lex.update(out["lexicon"])
            from forge.util import write_yaml
            write_yaml(job.path("lexicon.yaml"), lex)
    else:
        chapters, open_questions = _plan_offline(template, bundle)
    supported = total_words / wpm * 1.25
    if not spec.get("target_minutes") and supported < template["target_minutes"]["min"] * 0.9:
        open_questions = list(open_questions) + [
            f"The sources support about {supported:.1f} min of narration; the template's minimum is "
            f"{template['target_minutes']['min']} min. Add material, or expect a shorter video."]
    arc = {s["id"]: s for s in template["arc"]}
    share_sum = sum(arc[c["slot"]]["share"] for c in chapters) or 1
    outline = {"target_minutes": round(target, 2), "chapters": []}
    for index, chapter in enumerate(chapters, 1):
        slot = arc[chapter["slot"]]
        outline["chapters"].append({
            "id": f"c{index}", "slot": slot["id"], "title": chapter.get("title") or slot["title"],
            "purpose": chapter.get("purpose") or slot.get("purpose", ""),
            "passages": chapter.get("passages", []), "facts_needed": chapter.get("facts_needed", []),
            "share": round(slot["share"] / share_sum, 3),
            "target_seconds": round(target * 60 * slot["share"] / share_sum, 1),
            "required": slot.get("required", []), "min_phases": slot.get("min_phases", 0),
            "layout": slot.get("layout") or template.get("default_layout", "map_panel"),
        })
    outline["open_questions"] = open_questions
    return outline


def _plan_offline(template: dict, bundle: dict):
    """Route each passage to the arc slot its words point at, keeping order."""
    arc = template["arc"]
    scored = []
    for p in bundle["passages"]:
        text = p["text"].lower()
        scores = [sum(len(re.findall(r"\b" + re.escape(k.lower()) + (r"\w*" if len(k) > 3 else r"\b"), text))
                      for k in set(s.get("keywords", []))) for s in arc]
        scored.append((p, scores))
    assigned: dict[str, list[str]] = {s["id"]: [] for s in arc}
    last = 0
    for index, (p, scores) in enumerate(scored):
        if index == 0 and "title" in arc[0].get("required", []) and max(scores[1:] or [0]) < 2:
            best = 0
        elif max(scores) == 0:
            # No signal: stay in the current slot -- but the title slot holds
            # one passage, the hook, and the rest of the story moves on.
            best = last
            if "title" in arc[last].get("required", []) and assigned[arc[last]["id"]]:
                best = next((i for i in range(last + 1, len(arc)) if "recap" not in arc[i].get("required", [])), last)
        else:
            # The best slot not earlier than the story so far, unless a much
            # better one lies behind: arcs are read in order.
            # A story moves forward: a tie with the next slot goes to the next slot.
            best = max(range(len(arc)), key=lambda i: scores[i] - (0.5 if i < last else 0)
                       + (0.25 if i == last + 1 else 0) - 0.05 * abs(i - last))
        assigned[arc[best]["id"]].append(p["id"])
        last = max(last, best)
    chapters, questions = [], []
    body = sum(1 for slot in arc if assigned[slot["id"]] and "title" not in slot.get("required", []))
    for slot in arc:
        if "recap" in slot.get("required", []) and body < 2:
            continue      # nothing to sum up
        if assigned[slot["id"]] or {"recap", "title"} & set(slot.get("required", [])):
            chapters.append({"slot": slot["id"], "title": slot["title"], "passages": assigned[slot["id"]]})
        else:
            questions.append(f"The sources say nothing for the '{slot['title']}' part of the template; it is left out.")
    return chapters, questions


# ════════════════════════════════════════════════════════════════════════
#  Ground
# ════════════════════════════════════════════════════════════════════════

def ground(job, bundle: dict, outline: dict) -> dict:
    """facts.json: every claim with a number, date or time, and its passage."""
    facts = []
    for p in bundle["passages"]:
        for sentence in sentences(p["text"]):
            values = sorted(numbers_in(sentence))
            clock = times_in(sentence)
            if not values and not clock:
                continue
            facts.append({"id": f"f{len(facts) + 1:03d}", "claim": sentence, "values": values,
                          "dates": YEAR_RE.findall(sentence), "times": clock, "source": p["id"]})
    if llm.available():
        # The model adds the facts a chapter asked for that the plain scan
        # cannot see (a figure written out in words, a date implied by a
        # neighbour); each must quote its passage, and is checked against it.
        system = ("You extract facts from source passages for a narrated video. Reply with JSON only: "
                  '{"facts": [{"claim": "one sentence", "values": ["numbers as written"], "source": "p01"}]}. '
                  "A fact states only what its passage states.")
        wanted = [q for c in outline["chapters"] for q in c.get("facts_needed", [])]
        task = json.dumps({"needed": wanted, "passages": bundle["passages"]}, ensure_ascii=False)[:60000]
        by_id = {p["id"]: p["text"] for p in bundle["passages"]}

        def check(obj):
            problems = []
            for f in obj.get("facts", []):
                text = by_id.get(f.get("source"), "")
                missing = [v for v in numbers_in(" ".join(map(str, f.get("values", [])))) if v not in numbers_in(text)]
                if not text:
                    problems.append(f"fact cites unknown passage {f.get('source')!r}")
                elif missing:
                    problems.append(f"values {missing} are not in passage {f['source']}")
            return problems

        try:
            extra = llm.ask(job, system, task, check=check).get("facts", [])
        except Exception as error:  # noqa: BLE001 -- the scanned facts still stand
            job.log(f"fact extractor: {error}; keeping the scanned facts")
            extra = []
        seen = {f["claim"] for f in facts}
        for f in extra:
            if f["claim"] not in seen:
                facts.append({"id": f"f{len(facts) + 1:03d}", "claim": f["claim"],
                              "values": sorted(numbers_in(" ".join(map(str, f.get("values", []))))),
                              "dates": YEAR_RE.findall(f["claim"]), "times": times_in(f["claim"]),
                              "source": f["source"]})
    numbers = sorted({v for f in facts for v in f["values"]})
    return {"facts": facts, "numbers": numbers, "times": sorted({t for f in facts for t in f["times"]})}


# ════════════════════════════════════════════════════════════════════════
#  Script
# ════════════════════════════════════════════════════════════════════════

def write_chapter(job, template: dict, style: dict, chapter: dict, bundle: dict, facts: dict,
                  outline: dict, notes: str = "") -> dict:
    if llm.available():
        system = _prefix(job, template, style, "script writer") + "\n\nOPERATIONS\n" + json.dumps(registry.ops())
        facts_rows = tools.call("facts.query", job=job, chapter=chapter["id"])
        region_index = region.index(job.spec["region_id"]) if job.spec.get("region_id") else None
        task = json.dumps({
            "chapter": chapter, "facts": facts_rows[:80], "region": region_index, "revision_notes": notes,
            "passages": [p for p in bundle["passages"] if p["id"] in chapter["passages"]],
            "rules": ["Every number you narrate or show must be in facts.",
                      f"Each beat's say is {template['beat_words']['min']}-{template['beat_words']['max']} words.",
                      "Use tone roles, never colours. Use region anchors, places and unit ids by name.",
                      "Use a pattern beat when one fits: {pattern, slots, lines}."],
            "return": {"beats": [{"say": "...", "do": [{"op": "panel", "title": "..."}]}]},
        }, ensure_ascii=False)

        def check(obj):
            from forge import gates

            draft = patterns.expand_chapter({"beats": obj.get("beats", [])}, template["patterns"])
            return [e["message"] for e in gates.schema_errors(draft, chapter, job)]

        out = llm.ask(job, system, task, check=check)
        script = patterns.expand_chapter({"beats": out["beats"]}, template["patterns"])
    else:
        script = _write_offline(job, template, chapter, bundle, facts)
    script.update({"chapter": chapter["id"], "slot": chapter["slot"], "title": chapter["title"],
                   "layout": chapter["layout"]})
    if chapter["slot"] in ("recap",) or "recap" in chapter.get("required", []):
        script["recap"] = recap_points(job, outline)
    fill_required(job, template, chapter, script, bundle, facts)
    return script


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def _stat_of(sentence: str):
    m = next(_quantities(sentence), None)
    if not m:
        return None
    after = sentence[m.end():].split()
    unit = ""
    if after and re.fullmatch(r"(%|km²|km|mm|m|million|billion|lakh|crore|men|guns|troops|soldiers|years|°C|kg|per)",
                              after[0].strip(".,;")):
        unit = " " + after[0].strip(".,;")
    before = sentence[:m.start()].split()
    prefix = "about " if before and before[-1].lower() in ("about", "around", "nearly", "some", "roughly") else ""
    return {"value": (prefix + m.group(1) + unit).strip(), "label": _clip(sentence, 70)}


def _beats_from_sentences(texts: list[str], lo: int, hi: int) -> list[str]:
    """Narration lines within the template's word budget: merge short, split long."""
    out: list[str] = []
    for s in texts:
        if out and words(out[-1]) < lo:
            out[-1] = f"{out[-1]} {s}"
            continue
        if words(s) > hi:
            parts = re.split(r"(?<=[,;:])\s+", s)
            chunk = ""
            for part in parts:
                if chunk and words(chunk) + words(part) > hi:
                    out.append(chunk)
                    chunk = part
                else:
                    chunk = f"{chunk} {part}".strip()
            if chunk:
                out.append(chunk)
            continue
        out.append(s)
    if len(out) > 1 and words(out[-1]) < lo:
        last = out.pop()
        out[-1] = f"{out[-1]} {last}"
    return out


def _write_offline(job, template: dict, chapter: dict, bundle: dict, facts: dict) -> dict:
    ctx = Context(job, template)
    budget = template.get("beat_words", {"min": 8, "max": 40})
    texts = [s for p in bundle["passages"] if p["id"] in chapter["passages"] for s in sentences(p["text"])]
    lines = _beats_from_sentences(texts, budget["min"], budget["max"])
    is_map = registry.load_template(template["id"])["layouts"].get(chapter["layout"], {}).get("map", True) \
        and bool(job.spec.get("region_id"))
    battle = "unit" in chapter.get("required", [])
    fact_claims = {f["claim"] for f in facts["facts"]}
    beats, seen_places, seen_rivers = [], set(), set()
    deployed = False
    for index, line in enumerate(lines):
        ops: list[dict] = []
        if index == 0 and chapter["slot"] not in ("prologue", "intro"):
            ops.append({"op": "panel", "title": chapter["title"]})
        if battle and ctx.units and not deployed:
            ops += [{"op": "unit", "id": u["id"]} for u in ctx.units]
            deployed = True
        if is_map and not battle:
            for place in ctx.places_in(line):
                if place not in seen_places:
                    seen_places.add(place)
                    ops.append({"op": "marker", "place": place})
                    break
            for river in ctx.rivers_in(line):
                if river not in seen_rivers:
                    seen_rivers.add(river)
                    ops.append({"op": "river", "name": river})
                    break
            for feature in ctx.features_in(line):
                ops.append({"op": "path", "points": feature})
                break
        if battle and ctx.units:
            ops += _battle_ops(ctx, line)
        numeric = any(line.startswith(c[:40]) or c in line for c in fact_claims if NUMBER_RE.search(c))
        stat = _stat_of(line) if numeric else None
        if stat:
            ops.append({"op": "stat", **stat})
        elif len(ops) < 3:
            ops.append({"op": "fact", "text": _clip(line, 88)})
        placed = [o for o in ops if o["op"] == "unit"]
        rest = [o for o in ops if o["op"] != "unit"]
        beats.append({"id": f"b{index + 1:02d}", "say": line, "do": placed + rest[:5],
                      "sources": [p["id"] for p in bundle["passages"] if p["id"] in chapter["passages"]
                                  and line[:30] in p["text"]][:1]})
    return {"beats": beats}


def _battle_ops(ctx: Context, line: str) -> list[dict]:
    low = line.lower()
    named = ctx.units_in(line)
    ops = []
    clock = times_in(line)
    if clock:
        ops.append({"op": "clock", "time": clock[0]})
    first = named[0] if named else None
    enemy_of = lambda uid: next((u["id"] for u in ctx.units  # noqa: E731
                                 if ctx.side(u["id"]) not in (ctx.side(uid), "ally") and u["id"] != uid), None)
    held = re.search(r"\b(held back|stood aside|did not|refused|watched|waited)", low)
    if held and first:
        ops.append({"op": "highlight", "target": first})
    elif re.search(r"\b(fire|fired|firing|cannon|cannonade|guns opened|bombard|shot|volley)", low) and first:
        target = named[1] if len(named) > 1 and ctx.side(named[1]) != ctx.side(first) else enemy_of(first)
        ops.append({"op": "volley", "from": first, **({"to": target} if target else {})})
    elif re.search(r"\b(charge|charged|attack|attacked|advanced|stormed|rushed)", low) and first:
        target = enemy_of(first)
        if target:
            ops.append({"op": "charge", "unit": first, "to": target})
    verb = re.search(r"\b(killed|fled|flee|retreat|retreated|routed|broke|collapsed|scattered|withdrew)", low)
    if verb and named and not held:
        # The unit that breaks is the one named nearest before the verb.
        before = [uid for pos, uid in ctx.unit_mentions(line) if pos < verb.start()]
        loser = before[-1] if before else named[-1]
        ops.append({"op": "rout", "unit": loser})
    elif re.search(r"\b(rain|storm|monsoon|downpour)", low):
        target = next((u["id"] for u in ctx.units if u.get("kind") == "artillery"), ctx.units[0]["id"])
        ops.append({"op": "highlight", "target": target})
    return ops


def recap_points(job, outline: dict) -> list[list[str]]:
    """[chapter title, card text, spoken line] per chapter.

    The card takes a clipped phrase; the voice says the whole sentence, so it
    never stops mid-clause.
    """
    points = []
    for chapter in outline["chapters"]:
        if chapter["slot"] in ("recap", "prologue", "intro"):
            continue
        script = job.script(chapter["id"])
        say = next((b["say"] for b in script.get("beats", []) if b.get("say")), "") or chapter.get("purpose", "")
        say = (sentences(say) or [say])[0]
        card = say if len(say) <= 60 else re.split(r"(?<=,)\s|\s(?:and|but|while|which)\s", say)[0].rstrip(",")
        points.append([chapter["title"], _clip(card, 60), say])
    return points[:8]


# ════════════════════════════════════════════════════════════════════════
#  Required elements (the template-fit gate's deterministic fix)
# ════════════════════════════════════════════════════════════════════════

def fill_required(job, template: dict, chapter: dict, script: dict, bundle: dict, facts: dict) -> list[str]:
    """Add what a slot requires and the chapter lacks, from the chapter's own material.

    Returns what could not be supplied, which the template gate reports.
    """
    ctx = Context(job, template)
    beats = script.setdefault("beats", [])
    have = {op["op"] for b in beats for op in b.get("do", [])}
    text = " ".join(b["say"] for b in beats)
    claims = [f for f in facts["facts"] if f["source"] in chapter["passages"]]
    missing = []

    def place_op(op: dict, prefer: str | None = None):
        if not beats:
            return False
        target = next((b for b in beats if prefer and any(o["op"] == prefer for o in b["do"]) and len(b["do"]) < 5), None)
        target = target or min(beats, key=lambda b: len(b["do"]))
        target["do"].append(op)
        return True

    for element in chapter.get("required", []):
        if element in have or element in ("title", "map", "recap"):
            continue
        if element == "marker" and ctx.region_id:
            place = (ctx.places_in(text) or ctx.places[:1] or [None])[0]
            if place and place_op({"op": "marker", "place": place}):
                continue
        elif element == "route" and ctx.region_id:
            stops = ctx.places_in(text)
            stops = stops if len(stops) >= 2 else (list(ctx.anchors)[:3] or ctx.places[:3])
            if len(stops) >= 2 and place_op({"op": "route", "points": stops[:5]}):
                continue
        elif element == "network":
            corpus = " ".join(p["text"] for p in bundle["passages"])
            people = [n for n in names_in(text, corpus) if n not in ctx.places and n.lower().replace(" ", "_")
                      not in ctx.anchors and not YEAR_RE.search(n)][:6]
            if len(people) >= 2:
                tones = {}
                for name in people:
                    uid = next(iter(ctx.units_in(name)), None)
                    tones[name] = {"friendly": "friendly", "enemy": "enemy", "ally": "ally"}.get(
                        ctx.side(uid) if uid else "", "accent")
                edges = []
                for sentence in sentences(text):
                    here = [n for n in people if n in sentence]
                    edges += [[a, b] for i, a in enumerate(here) for b in here[i + 1:] if [a, b] not in edges]
                if not edges:
                    edges = [[people[i], people[i + 1]] for i in range(len(people) - 1)]
                if place_op({"op": "network", "nodes": [[n, tones[n]] for n in people], "edges": edges[:8]}):
                    continue
        elif element == "bars":
            corpus = " ".join(p["text"] for p in bundle["passages"])
            items = []
            for f in claims:
                m = next(_quantities(f["claim"]), None)
                if not m:
                    continue
                before = names_in(f["claim"][:m.start()], corpus)
                label = before[-1] if before else " ".join(f["claim"][m.end():].split()[:2]).strip(".,")
                items.append([_clip(label, 18), float(m.group(1).replace(",", ""))])
            if len(items) >= 2 and place_op({"op": "bars", "items": items[:6]}):
                continue
        elif element == "timeline":
            corpus = " ".join(p["text"] for p in bundle["passages"])
            events, seen = [], set()
            for f in facts["facts"]:
                for year in f["dates"]:
                    if year in seen:
                        continue
                    seen.add(year)
                    at = f["claim"].index(year)
                    tail = re.split(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", f["claim"][at + 4:])[0]
                    after = [n for n in names_in(tail, corpus) if n not in MONTHS]
                    before = [n for n in names_in(f["claim"][:at], corpus) if n not in MONTHS]
                    pick = (sorted(after, key=lambda n: -len(n.split()))[:1] or before[-1:]
                            or [" ".join(tail.split()[:3]).strip(",.;")])
                    events.append([year, _clip(pick[0], 18)])
            events.sort()
            if len(events) >= 2 and place_op({"op": "timeline", "events": events[:6]}):
                continue
        elif element in ("stat", "fact"):
            f = next((f for f in claims if f["values"]), None)
            if element == "stat" and f and _stat_of(f["claim"]):
                place_op({"op": "stat", **_stat_of(f["claim"])})
                continue
            if element == "fact" and beats:
                place_op({"op": "fact", "text": _clip(beats[0]["say"], 88)})
                continue
        elif element == "river" and ctx.rivers:
            river = (ctx.rivers_in(text) or ctx.rivers[:1])[0]
            if place_op({"op": "river", "name": river}):
                continue
        elif element in ("unit", "move", "volley", "clock") and ctx.units:
            if element == "unit":
                if beats:
                    beats[0]["do"] = [{"op": "unit", "id": u["id"]} for u in ctx.units] + beats[0]["do"]
                    continue
            elif element == "move" and "charge" in have:
                continue
            elif element == "move":
                mover = next((u["id"] for u in ctx.units if u.get("side") == "friendly"), ctx.units[0]["id"])
                goal = next((u.get("at") for u in ctx.units if u.get("side") == "enemy"), None)
                if goal and place_op({"op": "move", "unit": mover, "to": goal}, prefer="volley"):
                    continue
            elif element == "volley":
                shooter = next((u["id"] for u in ctx.units if u.get("kind") == "artillery"), ctx.units[0]["id"])
                if place_op({"op": "volley", "from": shooter}):
                    continue
            elif element == "clock":
                clock = facts.get("times") or []
                if clock and place_op({"op": "clock", "time": clock[0]}):
                    continue
        missing.append(element)
    return missing


# ════════════════════════════════════════════════════════════════════════
#  Repair
# ════════════════════════════════════════════════════════════════════════

def repair_beat(job, template: dict, chapter: dict, script: dict, index: int, errors: list[str]) -> dict | None:
    """Targeted model repair: only the failing beat, its errors and its neighbours.

    None when there is no model; the orchestrator then marks the beat for a
    person rather than spending anything further.
    """
    if not llm.available():
        return None
    beats = script["beats"]
    task = json.dumps({
        "beat": beats[index], "errors": errors,
        "before": beats[index - 1]["say"] if index > 0 else None,
        "after": beats[index + 1]["say"] if index + 1 < len(beats) else None,
        "facts": tools.call("facts.query", job=job, chapter=chapter["id"])[:60],
        "operations": registry.ops(),
        "return": {"say": "...", "do": [{"op": "..."}]},
    }, ensure_ascii=False)
    system = ("You repair one beat of a narrated video script so it passes the named checks. Change as little as "
              "you can. Reply with the beat as JSON only.")

    def check(obj):
        from forge import gates

        return [e["message"] for e in gates.schema_errors({"beats": [obj]}, chapter, job)]

    fixed = llm.ask(job, system, task, check=check)
    fixed["id"] = beats[index]["id"]
    return fixed
