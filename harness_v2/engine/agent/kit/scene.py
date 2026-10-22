"""KitScene: the chapter's scene with the kit set up. The look's stage behind everything (paper or a drafting
grid, kept on the camera), a moving camera, the narration's clock (NarratedScene), and scene-wide moves:
camera moves, clearing the stage, wipes and zooms between scenes.

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
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, AnimationGroup, FadeIn, FadeOut, MovingCameraScene, Rectangle,
                   config)

from .images import surface
from .look import L, Look, use
from .motion import leave

try:
    from narrated import NarratedScene
except ImportError:                          # outside the agent's workspace: a scene with no narration
    from manim import Scene as NarratedScene


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
        frame = self.frame

        def follow(m):
            k = frame.width / m.width
            if abs(k - 1) > 1e-6:
                m.scale(k)
            m.move_to(frame.get_center())

        self.backdrop.add_updater(follow)
        self.add(self.backdrop)
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
        """Everything off the stage (but `keep`), each with the exit `how` (motion.EXITS)."""
        items = self.stage_items(keep)
        if not items:
            return
        if lag:
            from manim import LaggedStart
            self.play(LaggedStart(*(leave(m, how, run=run) for m in items), lag_ratio=lag))
        else:
            self.play(*(leave(m, how, run=run) for m in items))

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
        if then is not None:
            self.add(*(then if isinstance(then, (list, tuple)) else [then]))
        self.play(panel.animate(rate_func=look.ease).move_to(f.get_center() + d * f.width * 1.05), run_time=run / 2)
        self.remove(panel)

    # ---- the camera (each returns an animation to play, except camera_drift)
    def cam_to(self, target, width: float | None = None, zoom: float | None = None, run: float = 1.5,
               rate_func=None):
        """The camera moves to `target` (a point or mobject); `width`: the frame's new width in units, or `zoom`
        (2 = twice as close). With a mobject and neither, it frames the mobject with a margin."""
        from manim import smooth
        f = self.frame
        point = target.get_center() if hasattr(target, "get_center") else np.array(target, dtype=float)
        if width is None and zoom is not None:
            width = self.home_width / zoom
        if width is None and hasattr(target, "width"):
            width = max(target.width * 1.25, target.height * 1.25 * config.frame_width / config.frame_height)
        anim = f.animate(run_time=run, rate_func=rate_func or smooth).move_to(point)
        if width:
            anim = anim.set(width=width)
        return anim

    def cam_reset(self, run: float = 1.2):
        """The camera back to the whole frame."""
        return self.cam_to(ORIGIN, width=self.home_width, run=run)

    def cam_push(self, k: float = 1.12, run: float = 4.0):
        """A slow push in (k times closer) on where the camera is: a documentary's creep."""
        from manim import linear
        return self.frame.animate(run_time=run, rate_func=linear).set(width=self.frame.width / k)

    def cam_pan(self, by, run: float = 1.5):
        """The camera moves by a vector."""
        return self.frame.animate(run_time=run).shift(np.array(by, dtype=float))

    def camera_drift(self, speed: float = 0.02, zoom: float = 0.004, direction=(1, 0.35, 0)) -> None:
        """The camera creeps on its own from now on (paused while the camera is animated); speed 0 stops it."""
        if self._drift is not None:
            self.frame.remove_updater(self._drift)
            self._drift = None
        if not speed and not zoom:
            return
        d = np.array(direction, dtype=float)
        d = d / (np.linalg.norm(d) or 1)

        def creep(m, dt):
            m.shift(d * speed * dt)
            m.set(width=m.width * (1 - zoom * dt))

        self._drift = creep
        self.frame.add_updater(creep)
