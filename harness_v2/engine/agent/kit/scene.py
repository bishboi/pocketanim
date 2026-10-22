"""KitScene: the chapter's scene with the kit set up. The look's stage behind everything (paper or a drafting
grid), the narration's clock (NarratedScene), and scene-wide moves: camera moves (made by moving the stage, as the
phone has no 2D camera), clearing the stage, wipes and zooms between scenes.

    from kit import *

    class Chapter(KitScene):
        look = "vox"                                  # or "blueprint", or look("vox", accent="#2A9D8F")
        def construct(self):
            self.until(self.at(0, "Japan"))           # hold until "Japan" in line 0
            m = Map("east asia"); self.play(m.appear())
            self.play(self.cam_to(m.place_point("Kyoto"), width=6))   # the camera moves in
            self.clear_stage()                        # everything off, the stage stays
            ...
            self.wait_until_end()
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, Animation, AnimationGroup, FadeIn, FadeOut, Group, Mobject,
                   MovingCameraScene, Rectangle, VMobject, config, linear, smooth)

from .images import surface
from .look import L, Look, use
from .motion import leave

try:
    from narrated import FROM, TO, NarratedScene
except ImportError:                          # outside the agent's workspace: a scene with no narration
    from manim import Scene as NarratedScene
    FROM = TO = 0.0


class KitScene(NarratedScene, MovingCameraScene):
    look: str | Look = "vox"
    #: units a second the camera creeps on its own (0: still); camera_drift() changes it during the scene
    drift: float = 0.0

    def setup(self):
        super().setup()
        use(self.look)
        look = L()
        self.camera.background_color = look.bg
        self.frame = self.camera.frame
        self.home_width = self.frame.width
        self.backdrop = surface(look)
        self.backdrop.set_z_index(-1000)
        self.add(self.backdrop)
        self._scale, self._offset = 1.0, np.zeros(3)   # the view: screen = scale * home + offset
        self._drift = None
        if self.drift:
            self.camera_drift(self.drift)

    # ---- the narration's clock, shorter names
    def at(self, n: int, word: str, occurrence: int = 0, edge: str = "start") -> float:
        """When `word` is said in line n (see NarratedScene.word)."""
        return self.word(n, word, occurrence, edge)

    def until(self, t: float, lead: float = 0.0) -> None:
        """Hold until `lead` seconds before time t."""
        self.wait_until(t, lead)

    # ---- the stage
    def stage_items(self, keep=()) -> list:
        """Everything on stage but the backdrop (and `keep`)."""
        keep = set(id(k) for k in keep)
        return [m for m in self.mobjects if m is not self.backdrop and m is not self.frame and id(m) not in keep]

    def clear_stage(self, how: str = "fade", run: float = 0.6, keep=(), lag: float = 0.0) -> None:
        """Everything off the stage (but `keep`), each with the exit `how` (motion.EXITS). With nothing left, the
        view is home again (camera moves start from the whole frame)."""
        items = self.stage_items(keep)
        if items:
            if lag:
                from manim import LaggedStart
                self.play(LaggedStart(*(leave(m, how, run=run) for m in items), lag_ratio=lag))
            else:
                self.play(*(leave(m, how, run=run) for m in items))
        if not keep:
            self.view_home()

    def wipe(self, color: str | None = None, direction=RIGHT, run: float = 0.9, keep=(), then=None) -> None:
        """A panel sweeps across the frame, the stage is cleared behind it, and it sweeps off: a scene change.
        `then`: mobjects put on the stage while it is covered (they are revealed as it leaves)."""
        look = L()
        f = self.frame
        d = np.array(direction, dtype=float)
        panel = Rectangle(width=f.width * 1.05, height=f.height * 1.05, stroke_width=0,
                          fill_color=color or look.accent, fill_opacity=1)
        panel.set_z_index(900)
        panel.move_to(f.get_center() - d * f.width * 1.05)
        self.add(panel)
        self.play(panel.animate(rate_func=look.ease_out).move_to(f.get_center()), run_time=run / 2)
        for m in self.stage_items(list(keep) + [panel]):
            self.remove(m)
        if not keep:
            self.view_home()
        if then is not None:
            self.add(*(then if isinstance(then, (list, tuple)) else [then]))
        self.play(panel.animate(rate_func=look.ease).move_to(f.get_center() + d * f.width * 1.05), run_time=run / 2)
        self.remove(panel)

    # ---- the camera (each returns an animation to play, except camera_drift)
    # The phone has no 2D camera, so the camera never moves: these move the stage (everything on it but the backdrop)
    # the way a camera move would look. The view is tracked as screen = scale * home + offset, so cam_to's `width` and
    # `zoom` and cam_reset mean the same as they would for a camera. Points are where things are now on screen.
    # A move takes what is on stage when it is made: what appears in the same play does not move with it.
    def _move(self, point, k: float, run: float, rate_func=None):
        point = np.array(point, dtype=float)
        self._scale, self._offset = self._scale * k, k * (self._offset - point)
        items = self.stage_items()
        if not items:
            from manim import Wait
            return Wait(run)
        return _StageMove(Group(*items), point, k, run_time=run, rate_func=rate_func or smooth)

    def view_home(self) -> None:
        """Count the view as home now, moving nothing (clear_stage and wipe do this when the stage is empty)."""
        self._scale, self._offset = 1.0, np.zeros(3)

    def cam_to(self, target, width: float | None = None, zoom: float | None = None, run: float = 1.5,
               rate_func=None):
        """The view moves to `target` (a point or mobject, where it is now) and centres it; `width`: how many units
        of the scene (as first laid out) the view spans, or `zoom` (2 = twice as close as at the start). With a
        mobject and neither, it frames the mobject with a margin."""
        point = target.get_center() if hasattr(target, "get_center") else np.array(target, dtype=float)
        if width is None and zoom is None and hasattr(target, "width"):
            span = max(target.width * 1.25, target.height * 1.25 * config.frame_width / config.frame_height)
            k = self.home_width / span if span > 1e-6 else 1.0
        else:
            goal = zoom if zoom is not None else (self.home_width / width if width else self._scale)
            k = goal / self._scale
        return self._move(point, k, run, rate_func)

    def cam_reset(self, run: float = 1.2):
        """The view back to the start (everything on stage moves back with it)."""
        return self._move(self._offset, 1 / self._scale, run)

    def cam_push(self, k: float = 1.12, run: float = 4.0):
        """A slow push in (k times closer) on the centre of the view: a documentary's creep."""
        return self._move(ORIGIN, k, run, linear)

    def cam_pan(self, by, run: float = 1.5):
        """The view moves by a vector (the stage moves the other way)."""
        return self._move(by, 1.0, run)

    def camera_drift(self, speed: float = 0.02, zoom: float | None = None, direction=(1, 0.35, 0)) -> None:
        """The view creeps on its own through every hold from now on: `speed` units a second along `direction`,
        closing in by `zoom` a second (default speed / 5). camera_drift(0) stops it. Each hold is played as a slow
        move of the stage (so it is recorded for the phone like any other play)."""
        if not speed and not zoom:
            self._drift = None
            return
        d = np.array(direction, dtype=float)
        self._drift = (speed, speed / 5 if zoom is None else zoom, d / (np.linalg.norm(d) or 1))

    def wait(self, duration=1.0, *args, **kwargs):
        if not self._drift or duration < 1 / 15 or not self.stage_items():
            return super().wait(duration, *args, **kwargs)
        speed, zoom, d = self._drift
        start, end = self.now, self.now + float(duration)
        # Split where a section render begins or ends, so a section starts and stops where it was asked to.
        cuts = sorted({start, end, *(t for t in (FROM, TO) if t and start < t < end)})
        for a, b in zip(cuts, cuts[1:]):
            if TO and a >= TO - 1e-6:
                return super().wait(b - a)          # past the section's end: NarratedScene stops the render
            span = b - a
            self.play(self._move(d * speed * span, 1 / max(0.05, 1 - zoom * span), span, linear))


class _StageMove(Animation):
    """Moves a group as a camera move would show it: the view's centre goes to `point` and it closes in k times,
    the view's width changing evenly (as a camera's frame would). Applied as a step each frame, so other animations
    on the same things (a fade, a shift) still play."""

    def __init__(self, group, point, k, **kwargs):
        self.point, self.k = point, k
        self._sigma, self._r = 1.0, 0.0
        super().__init__(group, suspend_mobject_updating=False, **kwargs)

    def create_starting_mobject(self):
        return Mobject()                             # nothing to copy: each frame is a step from the last

    def interpolate_mobject(self, alpha: float) -> None:
        r = self.rate_func(alpha)
        sigma = 1 / (1 + (1 / self.k - 1) * r)
        f = sigma / self._sigma
        self.mobject.scale(f, about_point=ORIGIN)
        self.mobject.shift(sigma * (self._r - r) * self.point)
        if abs(f - 1) > 1e-9:
            for m in self.mobject.get_family():
                if isinstance(m, VMobject):
                    m.stroke_width *= f
                    m.background_stroke_width *= f
        self._sigma, self._r = sigma, r
