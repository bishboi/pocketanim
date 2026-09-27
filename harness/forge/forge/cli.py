"""forge: the command line. Every command is also an HTTP route in the harness app.

    forge new <id> --template T --style S [--brief TEXT | --brief-file F] [--source F ...] [--region R]
    forge make <id> [--until outline|script|preview] [--quality l|m|h] [--accept]
    forge status <id>            state, history, open questions, what waits on a person
    forge review <id>            the outline, or the preview's contact sheet, to review
    forge revise <id> "c6.b07: say: a better line"      (or "c6: note", "outline: note")
    forge restyle <id> <style>
    forge learn-style <example.mp4|png> --name N
    forge learn-template <outline.md> --name N
    forge list | registry | tools
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from forge import machine, registry, tools
from forge.job import Job, list_jobs, slug


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_new(args) -> int:
    brief = args.brief or ""
    if args.brief_file:
        brief = Path(args.brief_file).read_text(encoding="utf-8")
    sources = [str(Path(s).resolve()) if not s.startswith("http") else s for s in args.source or []]
    job_id = slug(args.id)
    auto = args.template == "auto" or args.style == "auto"
    problems = []
    if not auto:
        # "auto" is decided from the sources at the resolve state, where compatibility is checked.
        template = registry.load_template(args.template)
        style = registry.resolve_style(args.style, args.template)
        problems = registry.check_compat(template, style, args.lang)
    if problems:
        nearest = registry.nearest_compatible(template, args.style, args.lang)  # noqa: F821 -- set when not auto
        print("incompatible: " + "; ".join(problems) + (f" (try --style {nearest})" if nearest else ""),
              file=sys.stderr)
        return 2
    overrides = json.loads(args.overrides) if args.overrides else {}
    job = Job.create(job_id, template=args.template, style=args.style, content=brief, sources=sources,
                     title=args.title or "", lang=args.lang, region=args.region, target_minutes=args.minutes,
                     review={"outline": args.review_outline, "preview": args.review_preview}, overrides=overrides)
    job.update_spec(quality=args.quality, phone=not args.no_phone, subtitle=args.subtitle)
    _print({"id": job.id, "dir": str(job.dir), "state": job.state["state"]})
    return 0


def cmd_make(args) -> int:
    tools.register_engine_tools()
    job = Job(args.id)
    result = machine.run(job, until=args.until, quality=args.quality, accept=args.accept)
    report = result.pop("report", None)
    if report:
        result["video"] = report["delivered"]["video"]
        result["output"] = report["output"]
    _print(result)
    return 1 if result.get("error") else 0


def cmd_status(args) -> int:
    job = Job(args.id)
    state = job.state
    _print({"id": job.id, "spec": job.spec, "state": state["state"], "history": state["history"][-12:],
            "open_questions": state.get("open_questions"), "human_review": state.get("human_review"),
            "waived": len(state.get("waived", [])), "errors": [e["error"] for e in state.get("errors", [])][-3:],
            "tokens": state.get("tokens"), "cost_usd": state.get("cost_usd"), "timings": state.get("timings"),
            "out": sorted(p.name for p in job.path("out").glob("*")) if job.path("out").exists() else []})
    return 0


def cmd_review(args) -> int:
    job = Job(args.id)
    outline = job.read("outline.json") or {}
    out = {"state": job.state["state"],
           "outline": [{"id": c["id"], "title": c["title"], "slot": c["slot"], "seconds": c["target_seconds"],
                        "passages": c["passages"]} for c in outline.get("chapters", [])],
           "open_questions": job.state.get("open_questions")}
    for name in ("qa/preview_sheet.png", "out/contact_sheet.png", "qa/gates.json", "qa/report.json"):
        if job.path(name).exists():
            out[name] = str(job.path(name))
    if args.chapter:
        out["script"] = job.script(args.chapter)
    _print(out)
    return 0


def cmd_revise(args) -> int:
    job = Job(args.id)
    for note in args.notes:
        _print(machine.revise(job, note))
    return 0


def cmd_restyle(args) -> int:
    _print(machine.restyle(Job(args.id), args.style))
    return 0


def cmd_learn_style(args) -> int:
    from forge.engine import learn

    result = learn.learn_style(args.example, slug(args.name).replace("-", "_"), args.label)
    result.pop("palette", None)
    registry.build_registry()
    _print(result)
    return 0


def cmd_learn_template(args) -> int:
    from forge.engine import learn

    result = learn.learn_template(args.example, slug(args.name).replace("-", "_"), args.label)
    registry.build_registry()
    _print(result)
    return 0


def cmd_list(args) -> int:
    _print(list_jobs())
    return 0


def cmd_registry(args) -> int:
    _print(registry.build_registry())
    return 0


def cmd_tools(args) -> int:
    tools.register_engine_tools()
    _print([{"name": t.name, "read_only": t.read_only, "doc": t.doc} for t in tools.TOOLS.values()])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="forge", description="Lecture Forge: content + template + style -> video.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create a job")
    p.add_argument("id")
    p.add_argument("--template", default="auto", help="a template id, or auto: chosen from the content's subject")
    p.add_argument("--style", default="auto", help="a style pack id, or auto: the subject's style")
    p.add_argument("--title")
    p.add_argument("--subtitle")
    p.add_argument("--brief")
    p.add_argument("--brief-file")
    p.add_argument("--source", action="append", help="a file or URL; repeat for more")
    p.add_argument("--region", help="a region pack id or a place name")
    p.add_argument("--minutes", type=float, help="target length")
    p.add_argument("--lang", default="en-GB")
    p.add_argument("--quality", default="m", choices=list("lmhk"))
    p.add_argument("--review-outline", action="store_true")
    p.add_argument("--review-preview", action="store_true")
    p.add_argument("--no-phone", action="store_true", help="skip the .panim export for the phone")
    p.add_argument("--overrides", help='JSON: {"voice": {...}, "music": {...}, "motion": {...}}')
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("make", help="run a job from where it stands")
    p.add_argument("id")
    p.add_argument("--until", choices=sorted(machine.UNTIL))
    p.add_argument("--quality", choices=list("lmhk"))
    p.add_argument("--accept", action="store_true", help="waive gate findings the repair budget left")
    p.set_defaults(fn=cmd_make)

    for name, fn, helptext in (("status", cmd_status, "where a job stands"), ("review", cmd_review, "what to review")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("id")
        if name == "review":
            p.add_argument("--chapter")
        p.set_defaults(fn=fn)

    p = sub.add_parser("revise", help='apply "c6.b07: note", "c6: note" or "outline: note"')
    p.add_argument("id")
    p.add_argument("notes", nargs="+")
    p.set_defaults(fn=cmd_revise)

    p = sub.add_parser("restyle", help="same words, another style")
    p.add_argument("id")
    p.add_argument("style")
    p.set_defaults(fn=cmd_restyle)

    for name, fn in (("learn-style", cmd_learn_style), ("learn-template", cmd_learn_template)):
        p = sub.add_parser(name, help="draft a library entry from an example")
        p.add_argument("example")
        p.add_argument("--name", required=True)
        p.add_argument("--label")
        p.set_defaults(fn=fn)

    for name, fn in (("list", cmd_list), ("registry", cmd_registry), ("tools", cmd_tools)):
        sub.add_parser(name).set_defaults(fn=fn)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (KeyError, ValueError, FileNotFoundError) as error:
        print(f"forge: {error}", file=sys.stderr)
        return 2
