"""Manim's LaTeX mobjects without LaTeX: MathTex, Tex, axis numbers, brace labels, DecimalNumber.

Manim typesets all of these by running the `latex` program (then dvisvgm), and without a LaTeX installation
a scene dies with `FileNotFoundError: [Errno 2] No such file or directory: 'latex'`. When LaTeX is not
installed, install() swaps the one function they all go through (`tex_to_svg_file`) for one that writes the
same kind of SVG from Pango text: the TeX turned into readable Unicode maths (E = mc², H₂O, (a)/(b), √x),
drawn in a serif font at the size LaTeX would have used. The groups MathTex looks for (one per part, so
`MathTex("a", "=", "b")[2]` and `set_color_by_tex` still work) are written as LaTeX would write them.

It looks plainer than LaTeX, but the scene renders. Install LaTeX for real typesetting (see harness/SETUP.md);
then install() does nothing.

    import nolatex
    nolatex.install()      # before building any MathTex; pocket_lecture and the harness's runners do this
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

_MARK = re.compile(r"\\special\{dvisvgm:raw <g id='([^']+)'>\}|\\special\{dvisvgm:raw </g>\}")
FONT = "Serif"
# SVG units per unit of Pango text drawn at font size 48: sized so the text lands at the height LaTeX's
# glyphs have at the same font_size (SingleStringMathTex scales the SVG by font_size / 960).
UNITS = 20.0
_installed = False


def latex_available() -> bool:
    """The LaTeX program Manim's default template compiles with is installed."""
    try:
        from manim import config

        compiler = config["tex_template"].tex_compiler
    except Exception:  # noqa: BLE001 -- no manim config yet: the default compiler
        compiler = "latex"
    return shutil.which(compiler) is not None


def install(font: str | None = None) -> bool:
    """Use the Pango fallback for every TeX mobject when LaTeX is not installed. True when it is in use."""
    global _installed, FONT
    if font:
        FONT = font
    if _installed:
        return True
    if latex_available():
        return False
    import manim.mobject.text.tex_mobject as tex_mobject

    tex_mobject.tex_to_svg_file = tex_to_svg_file
    _installed = True
    return True


def _tree(expression: str) -> list:
    """The expression as nested parts: text, and (group id, [parts]) where MathTex marked a part."""
    root: list = []
    stack = [root]
    at = 0
    for m in _MARK.finditer(expression):
        if m.start() > at:
            stack[-1].append(expression[at:m.start()])
        if m.group(1):
            group: list = []
            stack[-1].append((m.group(1), group))
            stack.append(group)
        elif len(stack) > 1:
            stack.pop()
        at = m.end()
    if at < len(expression):
        stack[-1].append(expression[at:])
    return root


def _plain(tex: str) -> str:
    """TeX as readable Unicode maths, with the layout commands a formula's look depends on dropped."""
    from pocket_lecture import unicode_math

    text = re.sub(r"\\(?:text|mathrm|mathbf|mathit|textbf|textit|operatorname|mbox)\{([^{}]*)\}", r"\1", tex)
    text = re.sub(r"\\(?:left|right|displaystyle|limits|,|;|!|quad|qquad)(?![a-zA-Z])", " ", text)
    text = text.replace("&", "").replace("\\\\", " ").replace("~", " ")
    return unicode_math(text)


def _leaves(parts: list, out: list) -> None:
    for part in parts:
        if isinstance(part, str):
            out.append(part)
        else:
            _leaves(part[1], out)


def _path(glyph) -> str:
    """A glyph's outline as SVG path data (y down)."""
    d = []
    for sub in glyph.get_subpaths():
        if len(sub) < 4:
            continue
        d.append(f"M{sub[0][0] * UNITS:.3f} {-sub[0][1] * UNITS:.3f}")
        for i in range(0, len(sub) - 3, 4):
            h0, h1, a1 = sub[i + 1], sub[i + 2], sub[i + 3]
            d.append(f"C{h0[0] * UNITS:.3f} {-h0[1] * UNITS:.3f} {h1[0] * UNITS:.3f} {-h1[1] * UNITS:.3f} "
                     f"{a1[0] * UNITS:.3f} {-a1[1] * UNITS:.3f}")
        d.append("Z")
    return " ".join(d)


def tex_to_svg_file(expression: str, environment: str | None = None, tex_template=None) -> Path:
    """What Manim's tex_to_svg_file returns, an SVG of the expression, drawn from Pango text instead."""
    from manim import Text, config

    folder = Path(config.get_dir("tex_dir"))
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{FONT}|{UNITS}|{environment}|{expression}".encode()).hexdigest()[:16]
    target = folder / f"nolatex_{key}.svg"
    if target.exists():
        return target

    tree = _tree(expression)
    leaves: list[str] = []
    _leaves(tree, leaves)
    plain = [_plain(leaf) for leaf in leaves]
    whole = "".join(plain)
    glyphs = list(Text(whole, font=FONT, font_size=48, disable_ligatures=True).submobjects) if whole.strip() else []
    # Which glyphs are whose: each leaf's own glyph count, in order. When shaping makes the counts disagree
    # (a script that joins letters), everything goes to the first part rather than being split wrongly.
    counts = [len(Text(p, font=FONT, font_size=48, disable_ligatures=True).submobjects) if p.strip() else 0
              for p in plain]
    if sum(counts) != len(glyphs):
        counts = [len(glyphs)] + [0] * (len(counts) - 1)
    shares = iter(counts)
    taken = [0]

    def write(parts: list) -> str:
        out = []
        for part in parts:
            if isinstance(part, str):
                n = next(shares, 0)
                mine = glyphs[taken[0]:taken[0] + n]
                taken[0] += n
                out += [f'<path d="{_path(g)}"/>' for g in mine]
            else:
                out.append(f"<g id='{part[0]}'>{write(part[1])}</g>")
        return "".join(out)

    body = write(tree)
    target.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1">{body}</svg>', encoding="utf-8")
    return target
