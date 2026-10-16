"""Manim's LaTeX mobjects, typeset by LaTeX when it is installed, and never a crash when it is not.

MathTex, Tex, axis numbers, brace labels and DecimalNumber all go through one function, Manim's
`tex_to_svg_file`. install() puts this module's `typeset` in its place, which:

- finds LaTeX where the installers put it (TinyTeX from `fetch_latex.py`, MacTeX, TeX Live), even when the
  app was started without it on PATH;
- turns the Unicode a model writes in maths (μ, θ, ², ×, →) into TeX, which pdfLaTeX cannot read;
- typesets maths holding Hindi or other non-Latin text (\\text{फिसलन होगी}) with XeLaTeX and a font that has
  the script, since pdfLaTeX cannot typeset it at all;
- and when LaTeX is missing, or a formula will not compile, draws the same maths from Pango text as
  readable Unicode (E = mc², H₂O, (a)/(b), √x) at the size LaTeX would have used, rather than stopping the
  lecture. The groups MathTex looks for (one per part, so `MathTex("a", "=", "b")[2]` and
  `set_color_by_tex` still work) are written as LaTeX would write them.

Install LaTeX for real typesetting: `.venv/bin/python harness/scripts/fetch_latex.py` (see harness/SETUP.md).

    import nolatex
    nolatex.install()      # before building any MathTex; pocket_lecture and the harness's runners do this
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
import re
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

_MARK = re.compile(r"\\special\{dvisvgm:raw <g id='([^']+)'>\}|\\special\{dvisvgm:raw </g>\}")
FONT = "Serif"
# SVG units per unit of Pango text drawn at font size 48: sized so the text lands at the height LaTeX's
# glyphs have at the same font_size (SingleStringMathTex scales the SVG by font_size / 960).
UNITS = 20.0
_installed = False


# Where LaTeX installers put their programs. The app may run without them on PATH (a macOS app started from the
# Dock, a server started before the install), so these are added to it.
TEX_HOMES = ("~/Library/TinyTeX/bin/*", "~/.TinyTeX/bin/*", "/Library/TeX/texbin", "/usr/local/texlive/*/bin/*",
             "/opt/homebrew/bin", "/usr/local/bin", "/usr/texbin")


def add_tex_to_path() -> list[str]:
    """Put installed LaTeX on PATH; the folders added."""
    added = []
    path = os.environ.get("PATH", "").split(os.pathsep)
    for pattern in TEX_HOMES:
        for folder in sorted(glob.glob(os.path.expanduser(pattern)), reverse=True):
            if folder not in path and os.path.isfile(os.path.join(folder, "latex")):
                path.append(folder)
                added.append(folder)
    if added:
        os.environ["PATH"] = os.pathsep.join(path)
    return added


def latex_available() -> bool:
    """The programs Manim's default template needs (latex, then dvisvgm) are installed."""
    add_tex_to_path()
    return shutil.which("latex") is not None and shutil.which("dvisvgm") is not None


def xelatex_available() -> bool:
    add_tex_to_path()
    return shutil.which("xelatex") is not None and shutil.which("dvisvgm") is not None


# Fonts with Devanagari (and Latin), best first: Google's Noto and Hind, then what macOS and Windows ship.
SCRIPT_FONTS = ("Noto Sans Devanagari", "Noto Serif Devanagari", "Hind", "Mukta", "Poppins", "Tiro Devanagari Hindi",
                "Kohinoor Devanagari", "Devanagari Sangam MN", "Devanagari MT", "Lohit Devanagari", "Mangal",
                "Nirmala UI")


def script_font() -> str | None:
    """An installed font XeLaTeX can typeset Hindi in, or None."""
    global _SCRIPT_FONT
    if _SCRIPT_FONT is not False:
        return _SCRIPT_FONT
    _SCRIPT_FONT = None
    families: set[str] = set()
    if shutil.which("fc-list"):
        try:
            out = subprocess.run(["fc-list", ":lang=hi", "family"], capture_output=True, text=True, timeout=20).stdout
            for line in out.splitlines():
                families.update(part.strip() for part in line.split(","))
        except Exception:  # noqa: BLE001
            pass
    for name in SCRIPT_FONTS:
        if name in families:
            _SCRIPT_FONT = name
            break
    return _SCRIPT_FONT


_SCRIPT_FONT: str | None | bool = False
_log = logging.getLogger("nolatex")

# Unicode a model writes in maths, as TeX (pdfLaTeX stops on any of these).
UNICODE_TEX = {
    "μ": r"\mu ", "θ": r"\theta ", "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ", "δ": r"\delta ",
    "Δ": r"\Delta ", "λ": r"\lambda ", "π": r"\pi ", "ρ": r"\rho ", "σ": r"\sigma ", "Σ": r"\Sigma ",
    "ω": r"\omega ", "Ω": r"\Omega ", "φ": r"\phi ", "Φ": r"\Phi ", "τ": r"\tau ", "ε": r"\varepsilon ",
    "η": r"\eta ", "ν": r"\nu ", "κ": r"\kappa ", "ψ": r"\psi ", "χ": r"\chi ", "ξ": r"\xi ", "ζ": r"\zeta ",
    "×": r"\times ", "·": r"\cdot ", "÷": r"\div ", "±": r"\pm ", "−": "-", "–": "-", "—": "-",
    "→": r"\rightarrow ", "←": r"\leftarrow ", "⇒": r"\Rightarrow ", "⇔": r"\Leftrightarrow ",
    "↔": r"\leftrightarrow ", "⇌": r"\rightleftharpoons ", "≤": r"\le ", "≥": r"\ge ", "≠": r"\ne ",
    "≈": r"\approx ", "∝": r"\propto ", "∞": r"\infty ", "√": r"\sqrt ", "∫": r"\int ", "∂": r"\partial ",
    "∇": r"\nabla ", "°": r"^{\circ}", "⊥": r"\perp ", "∥": r"\parallel ", "∠": r"\angle ", "∴": r"\therefore ",
    "…": r"\ldots ", "ħ": r"\hbar ", "ℓ": r"\ell ", "′": "'",
    "⁰": "^{0}", "¹": "^{1}", "²": "^{2}", "³": "^{3}", "⁴": "^{4}", "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}",
    "⁸": "^{8}", "⁹": "^{9}", "⁻": "^{-}", "⁺": "^{+}", "ⁿ": "^{n}",
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}", "₄": "_{4}", "₅": "_{5}", "₆": "_{6}", "₇": "_{7}",
    "₈": "_{8}", "₉": "_{9}", "ₛ": "_{s}", "ₖ": "_{k}",
}
_TEXT_BLOCK = re.compile(r"(\\(?:text|textrm|textbf|textit|mbox)\s*\{[^{}]*\})")
_NON_ASCII = re.compile(r"[^\x00-\x7f]")


def to_tex(expression: str) -> str:
    """The expression with Unicode maths symbols written as TeX, outside \\text{} (whose words stay as they are)."""
    parts = _TEXT_BLOCK.split(expression)
    for i in range(0, len(parts), 2):
        parts[i] = "".join(UNICODE_TEX.get(ch, ch) for ch in parts[i])
    return "".join(parts)


def _script_template(font: str):
    from manim import TexTemplate

    template = TexTemplate(tex_compiler="xelatex", output_format=".xdv")
    template.add_to_preamble(r"\usepackage[no-math]{fontspec}" "\n"
                             rf"\setmainfont{{{font}}}[Script=Devanagari]")
    return template


_original = None
_installed = False


def install(font: str | None = None) -> bool:
    """Route every TeX mobject through `typeset`. True when LaTeX is missing (text is drawn instead)."""
    global _installed, FONT, _original
    if font:
        FONT = font
    missing = not latex_available()
    if _installed:
        return missing
    import manim.mobject.text.tex_mobject as tex_mobject

    _original = tex_mobject.tex_to_svg_file
    tex_mobject.tex_to_svg_file = typeset
    _atomic_text()
    _installed = True
    return missing


# Builds share Manim's TeX and text caches (export_scene.manim_cache) and run several at once. Two writing the same
# file at the same moment broke the text one ("error while writing to output stream" from manimpango.text2svg) and
# could leave a half-written formula SVG for a third to read. Text files are now written under a name of their own
# and moved into place in one step; formulas are typeset under one lock per cache, across processes.

def _atomic(write, at: int):
    """`write` (a manimpango text2svg) writing to a private file, then renamed over the target: a reader sees no
    file or a whole one, and two writers no longer write into one. Tried twice before the error is let through."""

    def wrapped(*args, **kwargs):
        args = list(args)
        target = str(kwargs["file_name"] if "file_name" in kwargs else args[at])
        if os.path.exists(target):
            return target
        for attempt in (1, 2):
            temp = f"{target}.{os.getpid()}.{uuid.uuid4().hex[:8]}.svg"
            if "file_name" in kwargs:
                kwargs["file_name"] = temp
            else:
                args[at] = temp
            try:
                write(*args, **kwargs)
                os.replace(temp, target)
                return target
            except Exception:
                try:
                    os.remove(temp)
                except OSError:
                    pass
                if os.path.exists(target):
                    return target       # another build wrote it meanwhile
                if attempt == 2:
                    raise
        return target

    wrapped.__wrapped__ = write
    return wrapped


def _private_svg_scratch() -> None:
    """SVGMobject parses a cached SVG through a scratch copy beside it, "<name>_.svg", and deletes it: in a cache
    shared by builds running at once, one build deleted another's copy (FileNotFoundError). Each process now uses
    a scratch name of its own."""
    import xml.etree.ElementTree as ET

    import svgelements as se
    from manim import RIGHT
    from manim.mobject.svg.svg_mobject import SVGMobject

    if getattr(SVGMobject.generate_mobject, "_panim", False):
        return

    def generate_mobject(self):
        file_path = self.get_file_path()
        new_tree = self.modify_xml_tree(ET.parse(file_path))
        scratch = file_path.with_name(f"{file_path.stem}_{os.getpid()}_{uuid.uuid4().hex[:8]}{file_path.suffix}")
        new_tree.write(scratch)
        try:
            svg = se.SVG.parse(scratch)
        finally:
            scratch.unlink(missing_ok=True)
        mobjects, mobject_dict = self.get_mobjects_from(svg)
        self.add(*mobjects)
        self.id_to_vgroup_dict = mobject_dict
        self.flip(RIGHT)
        return self

    generate_mobject._panim = True
    SVGMobject.generate_mobject = generate_mobject


def _remove_last_m(file_name: str) -> None:
    """manimpango's PangoUtils.remove_last_M, which Text runs on its SVG every time, cached or not: it rewrote the
    file in place, so a build reading it at that moment read an empty file ("no element found"). Now the file is
    rewritten only when there is something to remove, and then by a rename."""
    with open(file_name, "r") as handle:
        content = handle.read()
    cleaned = re.sub(r'Z M [^A-Za-z]*? "\/>', 'Z "/>', content)
    if cleaned == content:
        return
    temp = f"{file_name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    with open(temp, "w") as handle:
        handle.write(cleaned)
    os.replace(temp, file_name)


def _atomic_text() -> None:
    import manimpango

    _private_svg_scratch()
    manimpango.PangoUtils.remove_last_M = staticmethod(_remove_last_m)

    if not hasattr(manimpango.text2svg, "__wrapped__"):
        manimpango.text2svg = _atomic(manimpango.text2svg, 4)
    markup = manimpango.MarkupUtils
    if not hasattr(markup.text2svg, "__wrapped__"):
        markup.text2svg = staticmethod(_atomic(markup.text2svg, 7))


@contextmanager
def _cache_lock():
    """One formula typeset at a time across the builds sharing this cache (a no-op where flock does not exist)."""
    try:
        import fcntl
        from manim import config

        folder = Path(config.get_dir("tex_dir"))
        folder.mkdir(parents=True, exist_ok=True)
        handle = open(folder / ".panim.lock", "a")
    except Exception:  # noqa: BLE001 -- no lock is the old behaviour, not a failure
        yield
        return
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        handle.close()


def typeset(expression: str, environment: str | None = None, tex_template=None) -> Path:
    """Manim's tex_to_svg_file, by LaTeX when it can, by XeLaTeX for non-Latin text, by Pango otherwise; one at a
    time across the builds sharing the cache."""
    with _cache_lock():
        return _typeset(expression, environment, tex_template)


def _typeset(expression: str, environment: str | None = None, tex_template=None) -> Path:
    if not latex_available():
        return tex_to_svg_file(expression, environment, tex_template)
    source = to_tex(expression)
    try:
        if _NON_ASCII.search(source):
            font = script_font() if xelatex_available() else None
            if font is None:
                return tex_to_svg_file(expression, environment, tex_template)
            return _original(source, environment, _script_template(font))
        return _original(source, environment, tex_template)
    except Exception as error:  # noqa: BLE001 -- a formula that will not compile is drawn as text
        _log.warning("LaTeX could not typeset %r (%s); drawing it as text", expression[:80], error)
        return tex_to_svg_file(expression, environment, tex_template)


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
    temp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temp.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1">{body}</svg>', encoding="utf-8")
    os.replace(temp, target)
    return target
