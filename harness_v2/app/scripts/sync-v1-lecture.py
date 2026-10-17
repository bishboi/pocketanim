"""Copy v1's instructions for the beat script into v2, word for word: harness/app/lib/lecture.ts (lecturePrompt,
FREE_DRAWINGS_HEAD, MANIM_RULES, MANIM_PLAN) -> lib/prompts/v1-lecture.ts, cut into v1's own sections.

    python3 scripts/sync-v1-lecture.py           write it again from v1
    python3 scripts/sync-v1-lecture.py --check   exit 1 when v2's copy is not v1's text (npm run check runs this)
"""

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
V1 = APP.parents[1] / "harness" / "app" / "lib" / "lecture.ts"
OUT = APP / "lib" / "prompts" / "v1-lecture.ts"
SECTIONS = [("matters", '"WHAT MATTERS'), ("question", '"A QUESTION FOR THE CLASS, when'), ("pauses", '"PAUSES.'),
            ("pictures", '"EVERY PICTURE IS MADE'), ("beat", '"A beat is one narration line'), ("shape", '"Script shape:"'),
            ("ops", '"Operations (colour'), ("stage", '"THE STAGE (the board'), ("free", "...FREE_DRAWINGS_HEAD"),
            ("concept", '"CONCEPT MAPS AND CHAINS'), ("camera", '"CAMERA:'), ("manim", "...(manimModel()"),
            ("detailed", '"DETAILED DIAGRAMS, for'), ("map", '"Map operations (only with a region)')]
# The script shape, the drawings head and the Manim rules are placed by v2 itself (prompts/scenes.ts).
KEPT = ["matters", "question", "pauses", "pictures", "beat", "ops", "stage", "concept", "camera", "detailed", "map"]


def build() -> str:
    src = V1.read_text(encoding="utf-8").split("\n")

    def find(prefix: str, start: int = 0) -> int:
        return next(i for i in range(start, len(src)) if src[i].startswith(prefix))

    def array_body(name: str) -> list[str]:
        i = find(name)
        j = next(k for k in range(i, len(src)) if src[k].strip() == "];")
        return src[i + 1:j]

    k = find("export function lecturePrompt(")
    start = next(i for i in range(k, len(src)) if src[i].strip() == "return [") + 1
    end = next(i for i in range(start, len(src)) if src[i].strip() == '].join("\\n");')
    body = src[start:end]
    marks = sorted(((name, next(i for i, line in enumerate(body) if text in line)) for name, text in SECTIONS),
                   key=lambda x: x[1])
    sections = {name: body[i:(marks[n + 1][1] if n + 1 < len(marks) else len(body))] for n, (name, i) in enumerate(marks)}

    def arr(lines: list[str]) -> str:
        out = list(lines)
        while out and out[-1].strip() in ('"",', ""):
            out.pop()
        return "[\n" + "\n".join(out) + "\n]"

    parts = "\n".join(f"  {name}: {arr(sections[name])}," for name in KEPT)
    return ("/**\n * v1's instructions for the beat script, word for word (harness/app/lib/lecture.ts: lecturePrompt, "
            "FREE_DRAWINGS_HEAD,\n * MANIM_RULES, MANIM_PLAN), generated from v1's source by scripts/sync-v1-lecture.py and cut into "
            "its own sections\n * so the page can show them as parts. v2's scene writer is told these, exactly; only what v1 says "
            "about writing the\n * narration and calling its tool is v2's own (prompts/scenes.ts), since v2's narration is the "
            "script's, fixed.\n *\n * Regenerate it from v1 (python3 scripts/sync-v1-lecture.py) rather than editing it here.\n */\n\n"
            "/* eslint-disable */\n"
            f"export const V1_FREE_DRAWINGS_HEAD: string[] = {arr(array_body('const FREE_DRAWINGS_HEAD'))};\n\n"
            f"export const V1_MANIM_RULES: string[] = {arr(array_body('export const MANIM_RULES'))};\n\n"
            f"export const V1_MANIM_PLAN: string[] = {arr(array_body('export const MANIM_PLAN'))};\n\n"
            "/** lecturePrompt's sections, in v1's order (its script shape, subject and tool lines are v2's own). */\n"
            f"export const V1_LECTURE: Record<string, string[]> = {{\n{parts}\n}};\n")


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        if OUT.read_text(encoding="utf-8") != text:
            print("lib/prompts/v1-lecture.ts is not v1's text: run python3 scripts/sync-v1-lecture.py", file=sys.stderr)
            sys.exit(1)
        print("v1-lecture.ts is v1's text")
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(APP)}")
