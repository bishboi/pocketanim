"""LaTeX-heavy derivation.

Stresses: per-glyph addressability. TransformMatchingTex morphs one equation
into the next by matching sub-expressions, which is the case that decides
whether text can ship as shaped glyph runs or must ship as outlines.
"""

from manim import *


class LatexDerivation(Scene):
    def construct(self):
        title = Tex(r"Gaussian integral").to_edge(UP)
        self.play(Write(title))

        step1 = MathTex(r"I", r"=", r"\int_{-\infty}^{\infty}", r"e^{-x^2}", r"dx")
        step2 = MathTex(r"I^2", r"=", r"\int_{-\infty}^{\infty}", r"e^{-x^2}", r"dx",
                        r"\int_{-\infty}^{\infty}", r"e^{-y^2}", r"dy")
        step3 = MathTex(r"I^2", r"=", r"\int_0^{2\pi}\!\!\int_0^{\infty}",
                        r"e^{-r^2}", r"r\,dr\,d\theta")
        step4 = MathTex(r"I", r"=", r"\sqrt{\pi}")

        self.play(Write(step1))
        self.wait(0.5)
        self.play(TransformMatchingTex(step1, step2))
        self.wait(0.5)
        self.play(TransformMatchingTex(step2, step3))
        self.wait(0.5)
        self.play(TransformMatchingTex(step3, step4))
        self.wait(1)
