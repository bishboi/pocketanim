"""The registry: every style pack, template and region pack, versioned and resolved.

Libraries are folders. The registry scans them, resolves a style's `extends:`
chain, applies the precedence rules, and answers the one question Resolve asks
before any model is called: can this style draw everything this template needs?
"""

from __future__ import annotations

import json
from pathlib import Path

from forge import ENGINE_VERSION
from forge.util import (OPS_FILE, REGIONS, REGISTRY_FILE, STYLES, TEMPLATES, deep_merge, read_json,
                        read_yaml, write_json)

# Harness defaults: the bottom of the precedence stack.
DEFAULT_STYLE = {
    "engine_theme": "atlas",
    "motion": {"entrance": "fade"},
    "ops": ["*"],
    "scripts": ["Latn"],
    "voice": {"engine": "auto", "name": "af_sarah", "speed": 1.0},
    "music": {"preset": "drone", "volume": 0.07, "duck_db": 15},
    "tokens": {},
    "theme": {},
    "roles": {},
    "fonts": {},
}

LANG_SCRIPT = {"en": "Latn", "fr": "Latn", "de": "Latn", "es": "Latn", "it": "Latn", "pt": "Latn",
               "hi": "Deva", "mr": "Deva", "ne": "Deva", "bn": "Beng", "ta": "Taml", "ar": "Arab", "ru": "Cyrl"}


def ops() -> dict:
    return json.loads(OPS_FILE.read_text())


def _versions(folder: Path, name: str) -> dict:
    out = {}
    if not folder.is_dir():
        return out
    for child in sorted(folder.iterdir()):
        spec = read_yaml(child / name)
        if spec:
            out[child.name] = spec
    return out


def styles() -> dict:
    return _versions(STYLES, "style.yaml")


def templates() -> dict:
    return _versions(TEMPLATES, "template.yaml")


def regions() -> dict:
    return _versions(REGIONS, "region.yaml")


def resolve_style(style_id: str, template_id: str | None = None, overrides: dict | None = None) -> dict:
    """A style with everything it inherits, in precedence order.

    Lowest to highest: harness defaults, the parent chain (`extends:`), the
    style itself, its `per_template` block for this template, the job's own
    overrides. The more specific setting always wins.
    """
    known = styles()
    if style_id not in known:
        raise KeyError(f"no style pack {style_id!r}; have {', '.join(known)}")
    chain = []
    seen = set()
    current = style_id
    while current:
        if current in seen:
            raise ValueError(f"style {style_id!r} extends itself through {current!r}")
        seen.add(current)
        spec = dict(known[current])
        spec["tokens"] = deep_merge(read_yaml(STYLES / current / "tokens.yaml"), spec.get("tokens") or {})
        chain.append((current, spec))
        current = spec.get("extends")
    resolved = dict(DEFAULT_STYLE)
    for name, spec in reversed(chain):
        resolved = deep_merge(resolved, {k: v for k, v in spec.items() if k != "per_template"})
        writing = STYLES / name / "writing.md"
        if writing.exists():
            resolved["writing"] = writing.read_text(encoding="utf-8")
    per = (known[style_id].get("per_template") or {}).get(template_id or "", {})
    resolved = deep_merge(resolved, per)
    resolved = deep_merge(resolved, overrides or {})
    resolved["id"] = style_id
    resolved["chain"] = [name for name, _ in chain]
    return resolved


def engine_theme(style: dict) -> dict:
    """The pocket_lecture THEMES entry a resolved style becomes."""
    theme = dict(style.get("theme") or {})
    theme["base"] = style.get("engine_theme") or "atlas"
    theme["roles"] = dict(style.get("roles") or {})
    theme["anim"] = (style.get("motion") or {}).get("entrance", "fade")
    theme["tokens"] = dict(style.get("tokens") or {})
    fonts = (style.get("fonts") or {}).get("Latn") or {}
    if fonts.get("title"):
        theme["serif"] = fonts["title"]
    if fonts.get("body"):
        theme["sans"] = fonts["body"]
    if theme.get("label") is None:
        theme["label"] = style.get("label", style["id"])
    return theme


def load_template(template_id: str) -> dict:
    known = templates()
    if template_id not in known:
        raise KeyError(f"no template {template_id!r}; have {', '.join(known)}")
    spec = dict(known[template_id])
    folder = TEMPLATES / template_id
    spec["arc"] = read_yaml(folder / "arc.yaml").get("slots", [])
    spec["patterns"] = {p.stem: read_yaml(p) for p in sorted((folder / "patterns").glob("*.yaml"))}
    spec["prompts"] = {p.stem: p.read_text(encoding="utf-8") for p in sorted((folder / "prompts").glob("*.md"))}
    return spec


def load_region(region_id: str) -> dict:
    known = regions()
    if region_id not in known:
        raise KeyError(f"no region pack {region_id!r}")
    return known[region_id]


def check_compat(template: dict, style: dict, lang: str = "en") -> list[str]:
    """What stops this style drawing this template. Empty means compatible."""
    problems = []
    all_ops = set(ops())
    can_draw = set(all_ops) if "*" in style.get("ops", []) else set(style.get("ops", []))
    for op in template.get("requires_ops", []):
        if op not in all_ops:
            problems.append(f"template needs operation {op!r}, which no engine version here defines")
        elif op not in can_draw:
            problems.append(f"style {style['id']} cannot draw {op!r}")
    roles = style.get("roles") or {}
    for name in template.get("requires_roles", []):
        if name not in roles:
            problems.append(f"style {style['id']} does not define the role {name!r}")
    script = LANG_SCRIPT.get(lang.split("-")[0].lower(), "Latn")
    if script not in style.get("scripts", ["Latn"]):
        problems.append(f"style {style['id']} has no fonts for the {script} script ({lang})")
    allowed = template.get("compatible_styles", ["*"])
    if "*" not in allowed and style["id"] not in allowed:
        problems.append(f"template {template['id']} does not list {style['id']} as compatible")
    return problems


def nearest_compatible(template: dict, style_id: str, lang: str = "en") -> str | None:
    """The compatible style closest to the one asked for: its parent first."""
    wanted = resolve_style(style_id, template["id"])
    candidates = []
    for other in styles():
        if other == style_id:
            continue
        resolved = resolve_style(other, template["id"])
        if check_compat(template, resolved, lang):
            continue
        shared = len(set(resolved["chain"]) & set(wanted["chain"]))
        candidates.append((-shared, other))
    return min(candidates)[1] if candidates else None


def build_registry() -> dict:
    """registry.json: the index of every library folder, with its contract."""
    all_ops = sorted(ops())
    out = {"engine": ENGINE_VERSION, "ops": all_ops, "styles": {}, "templates": {}, "regions": {}}
    for sid, spec in styles().items():
        resolved = resolve_style(sid)
        out["styles"][sid] = {
            "version": spec.get("version", "0.1.0"), "extends": spec.get("extends"), "label": spec.get("label"),
            "engine": f">={ENGINE_VERSION.rsplit('.', 1)[0]}", "roles": sorted(resolved.get("roles") or {}),
            "ops": resolved.get("ops", ["*"]), "scripts": resolved.get("scripts", ["Latn"]),
            "status": spec.get("status", "released"),
        }
    for tid, spec in templates().items():
        out["templates"][tid] = {
            "version": spec.get("version", "0.1.0"), "label": spec.get("label"),
            "requires_ops": spec.get("requires_ops", []), "requires_roles": spec.get("requires_roles", []),
            "engine": f">={ENGINE_VERSION.rsplit('.', 1)[0]}",
        }
    for rid, spec in regions().items():
        out["regions"][rid] = {"version": spec.get("version", "0.1.0"), "name": spec.get("name"),
                               "focus": spec.get("focus"), "aliases": spec.get("aliases", []),
                               "battlefield": bool(spec.get("battlefield"))}
    write_json(REGISTRY_FILE, out)
    return out


def registry() -> dict:
    return read_json(REGISTRY_FILE) or build_registry()
