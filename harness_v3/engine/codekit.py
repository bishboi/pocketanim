"""Raw manim, written by the score's model where no prop or kit piece draws what it needs: a curve that morphs, a
mechanism, a geometric construction, a field of arrows, a wave.

    ent NAME manim [size S] [at X,Y]
    | def build(t):
    |     ...                      # manim code: returns one Mobject (a VGroup of parts), drawn about the origin
    |     return VGroup(...)

The code lines follow their `ent` line, each starting with `|`. `build(t)` is called with t = 0 when the thing is
made (its first look) and again on every frame of a `wA-wB play NAME` action, t going from 0 to 1 across those
words (`play NAME to 0.5` stops half way), so what it draws can grow, turn, morph or flow in step with the voice. Like
any other thing it comes `in`, goes `out`, moves, scales and is marked; `size S` makes its longest side S.

What the code may use: manim's shapes, groups, graphs and constants (Circle, Line, Arrow, VGroup, Axes,
ParametricFunction, Text, Polygon, UP, LEFT, PI...), `np` (its array maths only), `math`, and the look's colours (`C["ink"]`, `C["accent"]`,
`C["coral"]`..., or `col("teal")`). It may not import, open files, reach names that start with `_`, or loop with
`while`; a build that fails, runs too long (V3_CODE_STEPS lines) or returns no shape draws a plain placeholder box
instead (said in the score's notes), and the rest of the video plays. V3_MANIM_CODE=0 turns code off (placeholders).
"""

from __future__ import annotations

import ast
import math
import os
import sys

import numpy as np
import manim
from manim import Dot, Mobject, RoundedRectangle, Text, VGroup, VMobject

import look

STEPS = int(os.environ.get("V3_CODE_STEPS", "200000"))
# Built-ins a drawing needs; nothing that reaches files, modules, or the interpreter's own machinery.
BUILTINS = {n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n)
            for n in ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len",
                      "list", "map", "max", "min", "pow", "range", "reversed", "round", "set", "sorted", "str", "sum",
                      "tuple", "zip", "divmod", "print", "ValueError", "Exception")}
BANNED = {"open", "exec", "eval", "compile", "globals", "locals", "vars", "input", "breakpoint", "getattr", "setattr",
          "delattr", "help", "exit", "quit", "type", "object", "memoryview", "super", "classmethod", "staticmethod",
          "property", "config", "tempconfig", "logger", "console", "os", "sys", "subprocess", "importlib", "builtins"}
# manim's drawable things (no pictures from files, no LaTeX: it may not be installed), its constants and a few helpers
SKIP = {"ImageMobject", "SVGMobject", "Tex", "MathTex", "SingleStringMathTex", "Title", "BulletedList", "Code",
        "DecimalTable", "MathTable", "IntegerTable", "Table", "MobjectTable", "Variable", "BraceLabel", "BraceText"}


# numpy as a drawing needs it: arrays and their maths, nothing that reads or writes files
NP_NAMES = ("array", "asarray", "linspace", "arange", "zeros", "ones", "full", "eye", "pi", "e", "inf", "sin", "cos",
            "tan", "arcsin", "arccos", "arctan", "arctan2", "sinh", "cosh", "tanh", "sqrt", "exp", "log", "log10", "abs",
            "sign", "floor", "ceil", "round", "clip", "minimum", "maximum", "min", "max", "sum", "mean", "cumsum", "prod",
            "dot", "cross", "outer", "hypot", "deg2rad", "rad2deg", "radians", "degrees", "interp", "polyval", "stack",
            "vstack", "hstack", "concatenate", "where", "isclose", "allclose", "meshgrid", "float64", "int64")
SAFE_NP = type("np", (), {n: staticmethod(getattr(np, n)) if callable(getattr(np, n)) else getattr(np, n)
                          for n in NP_NAMES if hasattr(np, n)})
SAFE_NP.linalg = type("linalg", (), {"norm": staticmethod(np.linalg.norm)})
SAFE_NP.random = type("random", (), {"default_rng": staticmethod(lambda seed=0: np.random.default_rng(seed))})
# method names that reach files or the screen's own machinery, refused whatever they are called on
BANNED_ATTRS = {"save", "load", "tofile", "fromfile", "savetxt", "loadtxt", "save_image", "get_image", "save_state",
                "restore", "write", "read", "system", "popen", "remove", "unlink", "rmtree", "mkdir", "open", "path",
                "file", "files", "file_writer", "renderer", "camera", "config"}


def _names() -> dict:
    out = {}
    for n in dir(manim):
        if n.startswith("_") or n in SKIP or n in BANNED:
            continue
        v = getattr(manim, n)
        if isinstance(v, type) and issubclass(v, Mobject):
            out[n] = v
        elif n.isupper() and isinstance(v, (int, float, np.ndarray, str, manim.ManimColor)):
            out[n] = v
    for n in ("interpolate", "interpolate_color", "rotate_vector", "normalize", "ManimColor", "ValueTracker",
              "rate_functions", "smooth", "linear", "there_and_back"):
        if hasattr(manim, n):
            out[n] = getattr(manim, n)
    out.pop("ValueTracker", None)          # (a mobject, but nothing to draw: build(t) is the clock)
    return out


NAMES = _names()


def check(code: str) -> None:
    """Raise ValueError when the code does what a drawing must not (imports, files, private names, while loops)."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("no imports: manim, np and math are already there")
        if isinstance(node, (ast.While, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.Yield,
                             ast.YieldFrom, ast.ClassDef)):
            raise ValueError(f"no {type(node).__name__.lower()} in a drawing")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in BANNED):
            raise ValueError(f"the name {node.id!r} is not for drawings")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in BANNED_ATTRS):
            raise ValueError(f"the attribute {node.attr!r} is not for drawings")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "build" for n in tree.body):
        raise ValueError("the code defines no build(t)")


def compile_build(code: str):
    """The code's build(t), checked and run with only drawing names in reach."""
    if os.environ.get("V3_MANIM_CODE", "1").strip() == "0":
        raise ValueError("manim code is turned off (V3_MANIM_CODE=0)")
    check(code)
    env = {"__builtins__": BUILTINS, **NAMES, "np": SAFE_NP, "math": math, "C": dict(look.L), "col": look.col}
    exec(compile(code, "<score manim>", "exec"), env)      # noqa: S102 -- checked above; only drawing names in reach
    fn = env.get("build")
    if not callable(fn):
        raise ValueError("build is not a function")
    return fn


def call(fn, t: float):
    """build(t), stopped if it runs past STEPS lines; it must return a shape."""
    count = [0]

    def tracer(frame, event, arg):
        if frame.f_code.co_filename == "<score manim>":
            count[0] += 1
            if count[0] > STEPS:
                raise TimeoutError(f"the drawing ran past {STEPS} lines")
            return tracer
        return None
    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        m = fn(float(t))
    finally:
        sys.settrace(old)
    if isinstance(m, (list, tuple)):
        m = VGroup(*m)
    if not isinstance(m, Mobject) or not m.get_family() or not any(len(x.points) for x in m.get_family()):
        raise ValueError("build(t) returned no shape")
    return m


def placeholder(words: str = "drawing") -> VGroup:
    box = RoundedRectangle(width=3.0, height=2.0, corner_radius=0.15, stroke_color=look.col("soft"), stroke_width=3,
                           fill_color=look.col("card"), fill_opacity=0.6)
    t = Text(words[:24], font=look.L.get("mono") or "IBM Plex Mono", color=look.col("soft")).scale_to_fit_width(2.2)
    if t.height > 0.4:
        t.scale_to_fit_height(0.4)
    return VGroup(box, t.move_to(box))


class CodeThing(VGroup):
    """A thing drawn by the score's own manim code: its drawing, and two hidden dots that remember where the code's
    origin and unit went, so a new frame of it lands where the thing now is (moved, scaled, turned)."""

    def __init__(self, code: str, notes: list | None = None, name: str = ""):
        super().__init__()
        self.fn, self.t, self.error = None, 0.0, None
        try:
            self.fn = compile_build(code)
            drawing = call(self.fn, 0.0)
        except Exception as e:  # noqa: BLE001 -- the video plays on with a placeholder
            self.error = f"{type(e).__name__}: {e}"
            self.fn = None
            drawing = placeholder(name or "drawing")
            if notes is not None:
                notes.append(f"{name}: its manim code did not draw ({self.error[:200]}): a placeholder instead")
        self.drawing = drawing
        self.ref = VGroup(Dot([0, 0, 0], radius=0.001).set_opacity(0), Dot([1, 0, 0], radius=0.001).set_opacity(0))
        self.add(drawing, self.ref)

    def set_t(self, t: float) -> None:
        """The drawing at t (0..1), put where the thing is now; the same pieces reshaped when the code draws the same
        number of them (the player follows a piece as it changes), else new pieces."""
        if self.fn is None:
            return
        try:
            new = call(self.fn, t)
        except Exception as e:  # noqa: BLE001 -- the frame before stays
            self.error = f"{type(e).__name__}: {e}"
            return
        self.t = t
        o, u = self.ref[0].get_center(), self.ref[1].get_center()
        v = u - o
        k = float(np.hypot(v[0], v[1])) or 1.0
        new.scale(k, about_point=np.zeros(3)).rotate(math.atan2(v[1], v[0]), about_point=np.zeros(3)).shift(o)
        old = [x for x in self.drawing.get_family() if len(x.points)]
        fresh = [x for x in new.get_family() if len(x.points)]
        if len(old) == len(fresh):
            for a, b in zip(old, fresh):
                a.set_points(b.points)
                if isinstance(a, VMobject) and isinstance(b, VMobject):
                    a.set_fill(b.get_fill_color(), b.get_fill_opacity())
                    a.set_stroke(b.get_stroke_color(), b.get_stroke_width(), b.get_stroke_opacity())
            return
        self.remove(self.drawing)
        self.drawing = new
        self.submobjects.insert(0, new)
