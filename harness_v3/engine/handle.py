"""People using things: the verbs that put a person's hands (and feet, and seat) on a prop.

    pickup P X                  walks to it, bends, lifts it into the hands (then carried: it goes where they go)
    put P X on Y | at X,Y       sets what it holds down on a table, a shelf, the ground (`drop P X`: lets it fall)
    wear P X                    a crown, a helmet, a hat put on the head (it stays there)
    holdup P X                  raised high in both hands (a trophy, a medal, a sign, a baby lion)
    read P X | write P [X]      a book held open before the eyes; a hand writing (a quill in it, at a desk)
    eat P X | drink P X         bites (the food gets smaller, then gone); a cup tipped to the lips
    phone P X | type P X        the phone at the ear, talking; both hands tapping at a laptop or typewriter
    hammer P X | sweep P X      striking an anvil (sparks); a broom swept side to side
    count P X | vote P X        tapping coins one by one; a slip dropped into a ballot box
    ring P X | stir P X         a bell swung; a pot stirred (steam rising)
    open P X | shut P X         walks to a chest, box, letter or gate and opens it with a hand
    enter P X | exit P X        walks in at a building's door and is gone; comes out of it
    climb P X                   up a ladder, hand over hand
    sit P on X | sleep P on X   on a chair, stool, bench, throne or charpai; lying on a bed or charpai (`stand P`)
    kick P X [to X,Y]           a ball kicked away, bouncing
    use P X                     whichever of these the thing is for (eat bread, drink tea, read a book...)
    ride P V | drive V to X,Y   a person on a bicycle, rickshaw, cart, tractor or boat (in a car, bus, train or plane:
                                gone inside); the vehicle driven, its wheels turning, its riders carried along

Things alive on their own (no verb): flames flicker, flags wave, a windmill turns, smoke and steam drift.
"""

from __future__ import annotations

import math

import numpy as np
from manim import DOWN, RIGHT, UP, Line, VGroup, rate_functions

import look
import people as P

USE_VERBS = ("pickup", "put", "drop", "wear", "holdup", "read", "write", "eat", "drink", "phone", "type", "hammer",
             "sweep", "count", "vote", "ring", "stir", "enter", "exit", "climb", "sleep", "use", "drive")
RUN = {"pickup": 1.4, "put": 1.4, "drop": 0.7, "wear": 1.2, "holdup": 1.2, "read": 2.4, "write": 2.4, "eat": 2.6,
       "drink": 2.0, "phone": 2.6, "type": 2.4, "hammer": 2.4, "sweep": 2.4, "count": 2.4, "vote": 1.8, "ring": 1.8,
       "stir": 2.4, "enter": 1.6, "exit": 1.4, "climb": 2.2, "sleep": 1.6, "use": 2.0, "drive": 2.6}

FOOD = ("bread", "apple", "mango", "banana", "coconut", "fish", "bowl", "thali", "basket")
CUPS = ("teacup", "kulhad", "goblet", "jar", "bucket", "milkcan")
READ = ("book", "books", "openbook", "ledger", "newspaper", "scroll", "document", "charter", "letter", "oldmap",
        "notebook", "clipboard", "folder", "receipt")
SEATS = {"chair": 0.24, "stool": 0.2, "bench": 0.22, "throne": 0.3, "charpai": 0.23, "bed": 0.28, "sofa": 0.26}
BEDS = {"bed": 0.3, "charpai": 0.23}
BUILDINGS = ("house", "hut", "tent", "castle", "palace", "temple", "mosque", "church", "school", "hospital", "bank",
             "shop", "tower", "gate", "skyscraper", "factory", "lighthouse", "parliament", "court", "prison", "barn",
             "warehouse", "igloo", "pagoda", "door")
WEARS = ("crown", "helmet", "gradcap")
RAISE = ("trophy", "medal", "gem", "coin", "goldbars", "seal", "lightbulb", "key", "sword", "flagindia")
USES = {**{n: "eat" for n in FOOD}, **{n: "drink" for n in CUPS}, **{n: "read" for n in READ},
        **{n: "sit" for n in SEATS}, **{n: "enter" for n in BUILDINGS}, **{n: "wear" for n in WEARS},
        **{n: "holdup" for n in RAISE},
        "phone": "phone", "oldphone": "phone", "laptop": "type", "computer": "type", "typewriter": "type",
        "anvil": "hammer", "broom": "sweep", "coins": "count", "cash": "count", "moneybag": "count", "abacus": "count",
        "ballotbox": "vote", "bell": "ring", "pot": "stir", "ladder": "climb", "ball": "kick", "quill": "write",
        "pencil": "write", "inkwell": "write", "desk": "write", "chest": "open", "box": "open", "safe": "count",
        "bicycle": "ride", "rickshaw": "ride", "cart": "ride", "tractor": "ride", "boat": "ride", "car": "ride",
        "bus": "ride", "truck": "ride", "train": "ride", "plane": "ride", "carriage": "ride", "autorickshaw": "ride",
        "ship": "ride", "microphone": "talk", "megaphone": "phone", "plough": "push", "wheel": "push",
        "telescope": "read", "map": "read", "lantern": "holdup", "torch": "holdup", "goblet": "drink",
        "motorcycle": "ride", "scooter": "ride", "canoe": "ride", "sailboat": "ride", "hotairballoon": "ride",
        "wheelchair": "ride", "jeep": "ride", "ambulance": "ride", "firetruck": "ride", "policecar": "ride",
        "helicopter": "ride", "submarine": "ride", "jet": "ride", "tram": "ride", "bulldozer": "ride",
        "hammer": "hammer", "shovel": "sweep", "hoe": "sweep", "pitchfork": "sweep", "wheelbarrow": "push",
        "cake": "eat", "pizza": "eat", "samosa": "eat", "laddoo": "eat", "roti": "eat", "icecream": "eat",
        "teapot": "holdup", "passport": "read", "ticket": "read", "calendar": "read",
        "cheque": "read", "idcard": "holdup", "tablet": "type", "evm": "vote", "gavel": "hammer",
        "scepter": "holdup", "orb": "holdup", "spectacles": "holdup", "necklace": "holdup",
        "dumbbell": "holdup", "racket": "holdup", "hockeystick": "holdup"}
# Where a rider sits on a vehicle (its own frame), and those that swallow their riders (seen through no window)
VEHICLE_SEATS = {"bicycle": (-0.06, 0.24), "rickshaw": (0.2, 0.3), "cart": (-0.05, 0.3), "tractor": (-0.15, 0.3),
                 "boat": (0.05, 0.12), "motorcycle": (-0.2, 0.41), "scooter": (-0.26, 0.41), "canoe": (0.0, 0.04),
                 "sailboat": (-0.12, 0.05), "hotairballoon": (0.0, 0.08), "wheelchair": (0.03, 0.22), "jeep": (-0.15, 0.22)}
INSIDE = ("car", "bus", "truck", "train", "plane", "carriage", "autorickshaw", "ship", "ambulance", "firetruck",
          "policecar", "helicopter", "submarine", "jet", "tram", "bulldozer")


def verb_for(prop_name: str) -> str:
    return USES.get(prop_name, "pickup")


SWAP = {"fa1": "ba1", "fa2": "ba2", "ba1": "fa1", "ba2": "fa2"}
HOLDS = ("pickup", "wear", "holdup", "read", "phone", "eat", "drink", "sweep")


class UseActs:
    """The scene's verbs for a person using a thing (render.ScoreScene mixes this in)."""

    # -- which hand -------------------------------------------------------------------------------------------------
    def _holder_of(self, pm, xm):
        """The hand that holds this thing now (None: not held)."""
        return next((r[1] for r in self.follows if r[0] is xm and r[1] in (pm.hand, getattr(pm, "hand_b", None))), None)

    def _grip(self, pm, xm=None):
        """The hand a thing goes into: the one already holding it; else the right, unless the right is busy (a
        sword, a staff, a thing already in it), then the left (a shield there is put away while it holds)."""
        if xm is not None:
            h = self._holder_of(pm, xm)
            if h is not None:
                return h
        back = getattr(pm, "hand_b", None)
        if back is None or back is pm.hand:
            return pm.hand
        front_busy = getattr(pm, "tool", None) is not None or any(r[1] is pm.hand for r in self.follows)
        back_busy = any(r[1] is back for r in self.follows)
        return back if front_busy and not back_busy else pm.hand

    def _use_hand(self, pm, hand):
        """From now on the arm moves as that hand's; the left hand's shield is stowed while it holds something."""
        left = hand is getattr(pm, "hand_b", None) and hand is not pm.hand
        pm._left = left
        off = getattr(pm, "offhand_m", None)
        if off is not None and left and not getattr(pm, "_stowed", None):
            pm._stowed = [(x, x.get_fill_opacity(), x.get_stroke_opacity()) for x in off.family_members_with_points()]
            for x, _, _ in pm._stowed:
                x.set_fill(opacity=0, family=False)
                x.set_stroke(opacity=0, family=False)

    def _free_hand(self, pm, hand):
        """A hand let go: the left's shield back in it, the arms the right's again."""
        if hand is getattr(pm, "hand_b", None) and hand is not pm.hand:
            pm._left = False
            for x, fo, so in getattr(pm, "_stowed", None) or []:
                x.set_fill(opacity=fo, family=False)
                x.set_stroke(opacity=so, family=False)
            pm._stowed = None

    # -- small helpers ----------------------------------------------------------------------------------------------
    @staticmethod
    def _sh(pm):
        return pm.w((0.0, pm.D["HIP"] + pm.D["TORSO"]))

    def _aim(self, pm, pt):
        """The arm angle from the shoulder toward a point (from down, toward the face)."""
        d = pt - self._sh(pm)
        return math.atan2(pm.facing() * d[0], -d[1])

    @staticmethod
    def _blend(pm, p0, target: dict, k: float):
        if getattr(pm, "_left", False):         # holding with the other hand: its arm does what the right would;
            # the right arm, busy with its own (a sword), stays as it is
            target = {SWAP.get(key, key): v for key, v in target.items() if key not in ("ba1", "ba2")}
        p = dict(pm.pose)
        for key, v in target.items():
            p[key] = p0.get(key, v) + (v - p0.get(key, v)) * k
        pm.set_pose(p)

    def _let_go(self, xm):
        self.follows[:] = [r for r in self.follows if r[0] is not xm]

    def _keep(self, xm, anchor):
        self._let_go(xm)
        self.follows.append([xm, anchor, anchor.get_center().copy(), None])

    def _up(self, xn, xm):
        if id(self.E[xn]) not in self.up:
            self._show(xn, xm)
            self._alpha(xm).set(1.0)

    def _approach(self, pm, xm, st, a, walk, gap=0.35):
        """Walks up beside the thing over the first `walk` of the action (not at all if it is near), facing it."""
        if "f0" not in st:
            st["f0"] = pm.feet().copy()
            c = xm.get_center()
            side = 1.0 if c[0] >= st["f0"][0] else -1.0
            reach = xm.width / 2 + gap * pm.unit() + getattr(pm, "body_w", 0.2) * pm.unit() * 0.5
            goal = np.array([c[0] - side * reach, st["f0"][1], 0.0])
            st["f1"] = st["f0"] if abs(c[0] - st["f0"][0]) <= reach * 1.1 else goal
            st["side"] = side
            st["face0"] = pm.pose["face"]
        turn = min(1.0, a / max(0.12, walk * 0.3)) if walk > 0 else min(1.0, a / 0.12)
        if pm.pose["face"] != st["side"]:       # turned toward it over a moment, not flipped
            p = dict(pm.pose)
            p["face"] = st["face0"] + (st["side"] - st["face0"]) * rate_functions.ease_in_out_sine(turn)
            pm.set_pose(p)
        k = rate_functions.ease_in_out_sine(min(1.0, a / walk)) if walk > 0 else 1.0
        pm.shift(st["f0"] + (st["f1"] - st["f0"]) * k - pm.feet())
        gone = float(np.linalg.norm(pm.feet() - st["f0"]))
        if 0 < a < walk and np.linalg.norm(st["f1"] - st["f0"]) > 0.05:
            wp = P.walk_pose(gone / max(getattr(pm, "stride", 0.3) * pm.unit(), 1e-3) * math.pi / 2)
            p = dict(pm.pose)
            for key in ("fl1", "fl2", "bl1", "bl2", "bob"):
                p[key] = wp[key]
            pm.set_pose(p)
        elif not st.get("stood") and a >= walk:
            st["stood"] = True
            p = dict(pm.pose)
            for key in ("fl1", "fl2", "bl1", "bl2", "bob"):
                p[key] = pm.rest[key]
            pm.set_pose(p)
        return max(0.0, min(1.0, (a - walk) / max(1e-6, 1 - walk)))

    def _in_front(self, xm, pm):
        """What is held is drawn over its holder."""
        z = max((x.z_index for x in pm.get_family()), default=0)
        if max((x.z_index for x in xm.get_family()), default=0) <= z:
            xm.set_z_index(z + 1)

    @staticmethod
    def _arc(p0, p1, k, height):
        """A point on a lifted path from p0 to p1 (things are carried, not slid)."""
        e = rate_functions.ease_in_out_sine(k)
        return p0 + (p1 - p0) * e + UP * height * math.sin(math.pi * k)

    def _sparks(self, at, size):
        """A burst of little strokes at a point (a strike), gone in a moment."""
        g = VGroup(*(Line(at + size * 0.3 * np.array([math.cos(t), math.sin(t), 0]),
                          at + size * np.array([math.cos(t), math.sin(t), 0]),
                          stroke_color="#F2A93B", stroke_width=look.STROKE * 0.6)
                     for t in np.linspace(0.3, math.pi - 0.3, 5)))
        g.set_z_index(900)
        return g

    # -- the verbs --------------------------------------------------------------------------------------------------
    def _use(self, act, t0, t1) -> None:
        from render import Call
        import props
        v = act.verb
        (pn, pm), = self._targets(act.target)[:1]
        if v == "drive":
            return self._drive(pn, pm, act, t0, t1)
        if not isinstance(pm, P.Person):
            raise ValueError(f"{v} is a person's (`ent NAME person`): {pn} is a {self._kind(pn)}")
        names = [x for x in act.args if x in self.E]
        on = act.args[act.args.index("on") + 1] if "on" in act.args and act.args.index("on") + 1 < len(act.args) else None
        item = next((x for x in names if x != on), None)
        xn, xm = (item, self.E[item]) if item else (None, None)
        kind = xm.name if isinstance(xm, props.Prop) else ""
        if v == "use":
            if xm is None:
                raise ValueError("use needs the thing: `use P X`")
            v = verb_for(kind)
            if v == "sit" or v == "sleep":
                on, xn, xm = xn, None, None
            if v in ("ride", "talk", "kick", "open", "push"):
                from score import Act
                sub = Act(act.t0, act.t1, v, act.target, [item], act.line, act.text) if v != "talk" else \
                    Act(act.t0, act.t1, "talk", act.target, [], act.line, act.text)
                return self._do(sub)
        if v in ("sit", "sleep"):
            return self._sit_on(pn, pm, v, self.E[on] if on else xm, t0, t1)
        need = v not in ("write", "exit", "enter", "climb") or xm is not None
        if xm is None and need and v not in ("drop",):
            raise ValueError(f"{v} needs a thing: `{v} P X`")
        dur = max(t1 - t0, 0.3)
        st = {}
        f = lambda: pm.facing()  # noqa: E731
        hp = lambda: st.get("grip", pm.hand)  # noqa: E731  (the hand at work: the right, or the left if it is busy)
        u = pm.unit
        arms = ("fa1", "fa2", "ba1", "ba2")

        def start():
            st["p0"] = dict(pm.pose)
            if xm is not None and v in HOLDS:
                st["grip"] = self._grip(pm, xm)
                self._use_hand(pm, st["grip"])
            if xm is not None and v not in ("enter", "exit", "climb", "type", "hammer", "count", "vote", "ring",
                                             "stir", "write", "put", "drop"):
                self._up(xn, xm)
                if v in ("read", "phone", "eat", "drink", "wear", "holdup", "sweep", "pickup"):
                    self._in_front(xm, pm)
            if xm is not None:
                st["x0"] = xm.get_center().copy()

        def to_hand(k, lift=0.4):
            """The thing from where it was into the hand, then kept there."""
            goal = hp().get_center() + UP * xm.height * lift
            self._in_front(xm, pm)
            if k < 1:
                xm.move_to(self._arc(st["x0"], goal, k, 0.12 * u()))
            else:
                xm.move_to(goal)
            pop = 1 + 0.12 * math.sin(math.pi * min(1.0, k * 1.2))     # a little pop as it is grabbed
            xm.scale(pop / st.get("pop", 1.0))
            st["pop"] = pop

        step = stop = None
        if v == "pickup":
            def step(a):
                k = self._approach(pm, xm, st, a, 0.4)
                bend = math.sin(math.pi * min(1.0, k / 0.75))
                down = {"lean": 0.3, "fa1": 0.35, "fa2": 0.3, "ba1": 0.25, "ba2": 0.2, "brow": 0.3}
                up_ = P.carry_pose()
                if k < 0.5:
                    self._blend(pm, st["p0"], down, bend)
                else:
                    tgt = {**{key: up_[key] for key in arms}, "lean": 0.0}
                    self._blend(pm, {**pm.pose, **{key: pm.pose[key] for key in tgt}}, tgt, (k - 0.5) / 0.5)
                if k > 0.35:
                    if "x0" not in st or st.get("grab") is None:
                        st["grab"] = True
                        st["x0"] = xm.get_center().copy()
                    to_hand(min(1.0, (k - 0.35) / 0.3))

            def stop():
                if st.get("pop", 1.0) != 1.0:
                    xm.scale(1.0 / st["pop"])
                pm.carrying = True
                self._keep(xm, hp())
        elif v in ("put", "drop"):
            dest_ent = self.E.get(on) if on else None

            def start():                        # (what it holds: the thing named, else what is in its hands)
                st["p0"] = dict(pm.pose)
                held = xm
                if held is None:
                    held = next((r[0] for r in self.follows if r[1] in (pm.hand, getattr(pm, "hand_b", None))), None)
                if held is not None:
                    st["grip"] = self._holder_of(pm, held) or pm.hand
                    self._use_hand(pm, st["grip"])
                if held is None:
                    raise ValueError(f"{v}: {pn} holds nothing")
                st["held"] = held
                self._let_go(held)
                st["x0"] = held.get_center().copy()

            def step(a):
                held = st["held"]
                if v == "drop":
                    if "y1" not in st:
                        st["y1"] = pm.feet()[1] + held.height / 2
                        st["x1"] = pm.feet()[0] + f() * 0.3 * u()
                    k = rate_functions.ease_in_quad(min(1.0, a / 0.7))
                    bounce = 0.15 * u() * abs(math.sin(math.pi * (a - 0.7) / 0.3)) * (1 - a) if a > 0.7 else 0.0
                    held.move_to([st["x0"][0] + (st["x1"] - st["x0"][0]) * k,
                                  st["x0"][1] + (st["y1"] - st["x0"][1]) * k + bounce, 0])
                    self._blend(pm, st["p0"], {key: pm.rest[key] for key in arms}, min(1.0, a * 3))
                    return
                if "goal" not in st:
                    if dest_ent is not None:
                        st["goal"] = np.array([dest_ent.get_center()[0], dest_ent.get_top()[1] + held.height / 2, 0])
                    elif "at" in act.args:
                        g = self._locate(act.args[act.args.index("at") + 1], self.SCORE.ents[pn].shot)
                        st["goal"] = np.array([g[0], g[1] + held.height / 2, 0])
                    else:
                        st["goal"] = np.array([pm.feet()[0] + f() * 0.45 * u(), pm.feet()[1] + held.height / 2, 0])
                k = self._approach(pm, dest_ent if dest_ent is not None else held, st, a, 0.4 if dest_ent is not None else 0.0)
                if k <= 0:                      # carried along as it walks
                    held.move_to(hp().get_center() + UP * held.height * 0.4)
                    st["x0"] = held.get_center().copy()
                    return
                reach = math.sin(math.pi * k)
                ang = self._aim(pm, st["goal"])
                base = st["p0"] if k < 0.5 else {**st["p0"], **{key: pm.rest[key] for key in arms}, "lean": 0.0}
                self._blend(pm, base, {"fa1": ang, "fa2": ang, "ba1": ang * 0.9, "ba2": ang, "lean": 0.15}, reach)
                kk = min(1.0, k / 0.55)
                held.move_to(self._arc(st["x0"], st["goal"], kk, 0.1 * u()))
                if kk >= 1.0:                   # set down: a small squash and settle
                    t = min(1.0, (k - 0.55) / 0.3)
                    sq = 1 - 0.12 * math.sin(math.pi * t) * (1 - t)
                    bot = held.get_bottom()
                    held.stretch(sq / st.get("sq", 1.0), 1, about_point=bot)
                    st["sq"] = sq

            def stop():
                if st.get("sq", 1.0) != 1.0:
                    st["held"].stretch(1.0 / st["sq"], 1, about_point=st["held"].get_bottom())
                self._free_hand(pm, hp())
                pm.carrying = any(r[1] in (pm.hand, getattr(pm, "hand_b", None)) for r in self.follows)
        elif v == "wear":
            def step(a):
                top = pm.head.get_top() + UP * xm.height * 0.28
                if a < 0.45:
                    k = rate_functions.ease_in_out_sine(a / 0.45)
                    goal = hp().get_center() + UP * xm.height * 0.5
                    xm.move_to(st["x0"] + (goal - st["x0"]) * k)
                    self._blend(pm, st["p0"], {"fa1": 1.2, "fa2": 1.8}, k)
                else:
                    k = rate_functions.ease_in_out_sine((a - 0.45) / 0.55)
                    if "x1" not in st:
                        st["x1"] = xm.get_center().copy()
                    xm.move_to(st["x1"] + (top - st["x1"]) * k)
                    up_ = math.sin(math.pi * k)
                    self._blend(pm, st["p0"], {"fa1": 2.6 * up_ + 0.14 * (1 - up_), "fa2": 3.0 * up_ + 0.22 * (1 - up_),
                                               "smile": 0.9}, 1.0)

            def stop():
                self._keep(xm, pm.head)
                self._free_hand(pm, hp())
        elif v == "holdup":
            def step(a):
                k = rate_functions.ease_out_back(min(1.0, a / 0.6)) if a < 0.6 else 1.0
                self._blend(pm, st["p0"], {"fa1": 2.75, "fa2": 2.95, "ba1": 2.6, "ba2": 2.9, "smile": 1.0, "joy": 0.8,
                                           "bob": 0.02 * abs(math.sin(a * dur * 6))}, min(1.0, k))
                goal = hp().get_center() + UP * xm.height * 0.5
                xm.move_to(st["x0"] + (goal - st["x0"]) * min(1.0, a / 0.5))

            def stop():
                self._keep(xm, hp())
        elif v in ("read", "phone", "eat", "drink"):
            def step(a):
                tt = a * dur
                k = min(1.0, a / 0.25)
                k = k * k * (3 - 2 * k)
                out = max(0.0, min(1.0, (a - 0.8) / 0.2))       # the last of it: arms down, face back to itself
                out = out * out * (3 - 2 * out)
                held = hp().get_center() + UP * xm.height * 0.4
                if v == "read":                 # held before the eyes, the eyes running along its lines
                    tgt = {"fa1": 1.25, "fa2": 2.3, "ba1": 1.15, "ba2": 2.2, "nod": 0.12, "gaze": -0.5,
                           "side": 0.8 * math.sin(tt * 3.2), "smile": 0.2}
                    goal = hp().get_center() + UP * xm.height * 0.45
                elif v == "phone":              # at the ear, talking
                    tgt = {"fa1": 0.55, "fa2": 2.75, "mouth": 0.5 + 0.5 * math.sin(tt * 11) * math.sin(tt * 3.7),
                           "side": 0.4}
                    goal = pm.head.get_center() + RIGHT * f() * pm.head.width * 0.45
                elif v == "eat":                # bite after bite, the food smaller each time
                    bite = max(0.0, math.sin(tt * 3.6)) * (1 - out)
                    tgt = {"fa1": 0.7 + 0.9 * bite, "fa2": 1.5 + 1.3 * bite, "mouth": 0.6 * bite, "joy": 0.5}
                    R = pm.head.width / 2
                    mouth = pm.head.get_center() + RIGHT * f() * R * 0.7 + DOWN * R * 0.35
                    hand = hp().get_center() + UP * xm.height * 0.3
                    goal = hand + (mouth - hand) * 0.75 * bite
                    n = int(tt * 3.6 / (2 * math.pi) + 0.25)
                    if n > st.get("bites", 0) and a < 0.85:
                        st["bites"] = n
                        xm.scale(0.78)
                    if a > 0.85:
                        self._alpha(xm).set(max(0.0, (1 - a) / 0.15))
                else:                           # drink: tipped up to the lips and held there
                    lift = math.sin(math.pi * min(1.0, a / 0.95)) if a < 0.95 else 0.0
                    tgt = {"fa1": 0.8 + 1.0 * lift, "fa2": 1.6 + 1.2 * lift, "nod": -0.18 * lift, "lids": 0.6 * lift}
                    R = pm.head.width / 2
                    lips = pm.head.get_center() + RIGHT * f() * R * 0.75 + DOWN * R * 0.35
                    hand = hp().get_center() + UP * xm.height * 0.3
                    goal = hand + (lips - hand) * 0.8 * lift
                    tilt = -f() * 0.9 * lift
                    xm.rotate(tilt - st.get("tilt", 0.0))
                    st["tilt"] = tilt
                after = {key: (P.carry_pose()[key] if key in arms and v != "eat" else pm.rest[key]) for key in tgt}
                tgt = {key: val + (after[key] - val) * out for key, val in tgt.items()}
                self._blend(pm, st["p0"], tgt, k)
                goal = goal + (held - goal) * out
                xm.move_to(st["x0"] + (goal - st["x0"]) * min(1.0, a / 0.2))

            def stop():
                if v == "eat":
                    self._let_go(xm)
                    self._free_hand(pm, hp())
                else:
                    pm.carrying = True
                    self._keep(xm, hp())
        elif v == "sweep":                      # the broom in both hands, swept to and fro along the ground
            def step(a):
                tt = a * dur
                k = min(1.0, a / 0.2, (1 - a) / 0.1)
                sw = math.sin(tt * 5.0)
                self._blend(pm, st["p0"], {"fa1": 0.55 + 0.3 * sw, "fa2": 0.7 + 0.3 * sw, "ba1": 0.75 + 0.3 * sw,
                                           "ba2": 0.95 + 0.3 * sw, "lean": 0.1, "gaze": -0.5, "smile": 0.4}, k)
                ang = -pm.facing() * (0.45 + 0.2 * sw) * k
                xm.rotate(ang - st.get("ang", 0.0))
                st["ang"] = ang
                o, ex, ey = xm._frame() if hasattr(xm, "_frame") else (xm.get_center(), RIGHT, UP)
                grip = o + 0.7 * ey
                xm.shift(hp().get_center() - grip)

            def stop():
                self._keep(xm, hp())
        elif v in ("type", "hammer", "count", "vote", "ring", "stir", "write"):
            def step(a):
                tt = a * dur
                if xm is not None:
                    k = self._approach(pm, xm, st, a, 0.3, gap=0.15)
                else:
                    k = 1.0
                if k <= 0:
                    return
                e = min(1.0, k / 0.2, (1 - k) / 0.25)
                e = e * e * (3 - 2 * e)
                tgt = xm.get_top() if xm is not None else pm.w((0.45, 0.5))
                base = self._aim(pm, tgt)
                if v == "type":
                    j = 0.08 * math.sin(tt * 30) * math.sin(tt * 7)
                    pose = {"fa1": base - 0.2, "fa2": base + 0.25 + j, "ba1": base - 0.25, "ba2": base + 0.2 - j,
                            "gaze": -0.6, "nod": 0.1}
                elif v == "hammer":             # up and down; a burst at each blow
                    ph = (tt * 2.2) % 1.0
                    swing = 2.9 * (1 - ph / 0.6) + base * (ph / 0.6) if ph < 0.6 else base + (2.9 - base) * (ph - 0.6) / 0.4
                    pose = {"fa1": swing, "fa2": swing + 0.2, "frown": 0.4, "nod": 0.08}
                    blow = int(tt * 2.2 + 0.4)
                    if blow > st.get("blows", 0) and k > 0.05:
                        st["blows"] = blow
                        sp = self._sparks(tgt, xm.width * 0.5)
                        self.add(sp)
                        st.setdefault("sp", []).append((sp, tt))
                        xm.shift(DOWN * 0.02)
                        st["jolt"] = 0.02
                    elif st.get("jolt"):
                        xm.shift(UP * st["jolt"])
                        st["jolt"] = 0.0
                    for sp, at in list(st.get("sp", [])):
                        if tt - at > 0.25:
                            self.remove(sp)
                            st["sp"].remove((sp, at))
                elif v == "count":
                    tap = abs(math.sin(tt * 5))
                    pose = {"fa1": base, "fa2": base + 0.35 * tap, "gaze": -0.5, "smile": 0.7, "lids": 0.3}

                elif v == "vote":               # a slip from the hand into the slot
                    if "slip" not in st:
                        import props
                        slip = props.rect(-0.04, 0.0, 0.04, 0.1, "#F7F5F0", 1.2)
                        slip.scale(u()).set_z_index(max(x.z_index for x in xm.get_family()) + 1)
                        st["slip"] = slip
                        self.add(slip)
                    slip = st["slip"]
                    lift = min(1.0, k / 0.5)
                    pose = {"fa1": base + 0.5 * lift, "fa2": base + 0.6 * lift, "smile": 0.6}
                    if k < 0.55:
                        slip.move_to(hp().get_center() + UP * slip.height * 0.4)
                    else:
                        kk = min(1.0, (k - 0.55) / 0.35)
                        slip.move_to(xm.get_top() + UP * slip.height * (0.5 - 0.9 * kk))
                        st["al"] = st.get("al") or __import__("render").Alpha(slip)
                        st["al"].set(1 - kk)
                elif v == "ring":
                    sw = 0.35 * math.sin(tt * 9) * e
                    xm.rotate(sw - st.get("sw", 0.0), about_point=xm.get_top())
                    st["sw"] = sw
                    pose = {"fa1": 2.4 + sw, "fa2": 2.6 + sw, "mouth": 0.4, "smile": 0.6}
                elif v == "stir":               # round and round, steam rising
                    pose = {"fa1": base + 0.15 * math.cos(tt * 6), "fa2": base + 0.4 + 0.2 * math.sin(tt * 6),
                            "gaze": -0.5, "smile": 0.5}
                    if int(tt * 2) > st.get("puffs", -1):
                        st["puffs"] = int(tt * 2)
                        import props
                        puff = props.circ(0, 0, 0.05, "#FFFFFF", 0).set_fill(opacity=0.6).scale(u())
                        puff.move_to(xm.get_top())
                        self.add(puff)
                        st.setdefault("steam", []).append((puff, tt))
                    for puff, at in list(st.get("steam", [])):
                        age = tt - at
                        puff.move_to(xm.get_top() + UP * age * 0.5 * u() + RIGHT * 0.05 * u() * math.sin(age * 5))
                        puff.set_fill(opacity=max(0.0, 0.6 - age * 0.6))
                        if age > 1.0:
                            self.remove(puff)
                            st["steam"].remove((puff, at))
                else:                           # write: a small hand going back and forth
                    pose = {"fa1": base - 0.1, "fa2": base + 0.3 + 0.12 * math.sin(tt * 14), "gaze": -0.6, "nod": 0.1,
                            "frown": 0.2}
                if v in ("type", "count", "write", "stir", "hammer", "vote"):     # bent to reach what is low
                    low = (self._sh(pm)[1] - tgt[1]) / max(u(), 1e-3)
                    pose["lean"] = max(0.0, min(0.45, (low - 0.05) * 0.9))
                self._blend(pm, st["p0"], pose, e)

            def stop():
                for key in ("sp", "steam"):
                    for mob, _ in st.get(key, []):
                        self.remove(mob)
                if "slip" in st:
                    self.remove(st["slip"])
                if st.get("sw"):
                    xm.rotate(-st["sw"], about_point=xm.get_top())
        elif v in ("enter", "exit"):
            al = self._alpha(pm)

            def step(a):
                if v == "enter":                # to the door, then smaller and gone
                    if "f0" not in st:
                        st["f0"] = pm.feet().copy()
                        door = np.array([xm.get_center()[0], st["f0"][1], 0.0])
                        st["f1"] = door
                        pm.pose["face"] = 1.0 if door[0] >= st["f0"][0] else -1.0
                        st["s"] = 1.0
                    k = min(1.0, a / 0.7)
                    pos = st["f0"] + (st["f1"] - st["f0"]) * rate_functions.ease_in_out_sine(k)
                    pm.shift(pos - pm.feet())
                    wp = P.walk_pose(np.linalg.norm(pos - st["f0"]) / max(0.3 * u(), 1e-3) * math.pi / 2)
                    p = dict(pm.pose)
                    p.update({key: wp[key] for key in ("fl1", "fl2", "bl1", "bl2", "bob")})
                    pm.set_pose(p)
                    if a > 0.6:
                        al.set(max(0.0, 1 - (a - 0.6) / 0.4))
                else:                           # out of the door, toward the viewer's side
                    if "f0" not in st:
                        st["f0"] = np.array([xm.get_center()[0], pm.feet()[1], 0.0])
                        side = pm.facing()
                        st["f1"] = (self._dest(pn, pm, act) if "to" in act.args else
                                    st["f0"] + RIGHT * side * (xm.width / 2 + 0.6 * u()))
                        pm.pose["face"] = 1.0 if st["f1"][0] >= st["f0"][0] else -1.0
                        self._show(pn, pm)
                    al.set(min(1.0, a / 0.3))
                    pos = st["f0"] + (st["f1"] - st["f0"]) * rate_functions.ease_in_out_sine(a)
                    pm.shift(pos - pm.feet())
                    wp = P.walk_pose(np.linalg.norm(pos - st["f0"]) / max(0.3 * u(), 1e-3) * math.pi / 2)
                    p = dict(pm.pose)
                    p.update({key: (wp[key] if a < 0.95 else pm.rest[key]) for key in ("fl1", "fl2", "bl1", "bl2", "bob")})
                    pm.set_pose(p)
        elif v == "climb":
            def step(a):
                if "f0" not in st:              # the ladder's rungs over the climber
                    xm.set_z_index(max(x.z_index for x in pm.get_family()) + 1)
                    st["f0"] = pm.feet().copy()
                    st["foot"] = np.array([xm.get_center()[0] - pm.facing() * 0.05 * u(), xm.get_bottom()[1], 0.0])
                    st["top"] = np.array([xm.get_center()[0] - pm.facing() * 0.05 * u(),
                                          xm.get_bottom()[1] + xm.height * 0.42, 0.0])
                if a < 0.3:
                    k = rate_functions.ease_in_out_sine(a / 0.3)
                    pm.shift(st["f0"] + (st["foot"] - st["f0"]) * k - pm.feet())
                    return
                k = (a - 0.3) / 0.7
                pm.shift(st["foot"] + (st["top"] - st["foot"]) * rate_functions.ease_in_out_sine(k) - pm.feet())
                hand = math.sin(k * 14)
                self._blend(pm, st["p0"], {"fa1": 2.5 + 0.3 * hand, "fa2": 2.7 + 0.3 * hand, "ba1": 2.5 - 0.3 * hand,
                                           "ba2": 2.7 - 0.3 * hand, "fl1": 0.4 * hand, "bl1": -0.4 * hand, "gaze": 0.7}, 1.0)
        elif v == "kick":
            pass
        if step is None:
            raise ValueError(f"no way to {v} {xn}")
        # what is not yet in its hands is fetched first: walked to, bent for, picked up (then the action itself)
        if v in ("read", "phone", "eat", "drink", "wear", "holdup", "sweep") and xm is not None:
            F = 0.4
            act_step, act_start = step, start

            def start():                        # (in hand already, as it starts: no fetching)
                st["fetch"] = self._holder_of(pm, xm) is None
                act_start()

            def step(a):
                if not st["fetch"]:
                    return act_step(a)
                if a < F:
                    k = self._approach(pm, xm, st, a / F, 0.5)
                    if k <= 0:
                        return
                    bend = math.sin(math.pi * k)
                    self._blend(pm, st["p0"], {"lean": 0.3, "fa1": 0.35, "fa2": 0.3, "ba1": 0.25, "ba2": 0.2}, bend)
                    if k > 0.35:
                        if "g0" not in st:
                            st["g0"] = xm.get_center().copy()
                        kk = rate_functions.ease_in_out_sine(min(1.0, (k - 0.35) / 0.4))
                        goal = hp().get_center() + UP * xm.height * 0.4
                        self._in_front(xm, pm)
                        xm.move_to(self._arc(st["g0"], goal, kk, 0.12 * u()))
                    return
                if not st.get("fetched"):
                    st["fetched"] = True
                    p = dict(pm.pose)
                    p["lean"] = 0.0
                    pm.set_pose(p)
                    st["p0"] = dict(pm.pose)
                    st["x0"] = xm.get_center().copy()
                act_step((a - F) / (1 - F))
        self.tweens.append(Call(t0, t1, start, step, stop or (lambda: None), rate_functions.linear))

    def _do(self, act):
        """Plays another action now (`use` turned into the verb it means): it is this action, not one queued after."""
        self._no_queue = True
        try:
            self._schedule(act)
        finally:
            self._no_queue = False

    def _open_by(self, pn, pm, xn, xm, verb, t0, t1) -> None:
        """`open P X`: walks to it, a hand to its lid, and it opens (or shuts)."""
        from render import Call
        import props
        if not isinstance(xm, props.Prop) or xm.lid is None:
            raise ValueError(f"{verb}: {xn} has nothing to open (a chest, box, letter or gate does)")
        st = {}

        def start():
            st["p0"] = dict(pm.pose)
            st["k0"] = xm.open_k

        def step(a):
            k = self._approach(pm, xm, st, a, 0.4, gap=0.1)
            if k <= 0:
                return
            reach = math.sin(math.pi * min(1.0, k))
            ang = self._aim(pm, xm.get_top())
            self._blend(pm, st["p0"], {"fa1": ang, "fa2": ang + 0.2, "lean": 0.12, "brow": 0.6,
                                       "mouth": 0.4 if verb == "open" else 0.0}, reach)
            goal = 1.0 if verb == "open" else 0.0
            kk = rate_functions.ease_out_cubic(min(1.0, k / 0.7))
            xm.set_open(st["k0"] + (goal - st["k0"]) * kk)
        self.tweens.append(Call(t0, t1, start, step, lambda: None, rate_functions.linear))

    # -- sitting and lying on things -----------------------------------------------------------------------------
    def _sit_on(self, pn, pm, v, xm, t0, t1) -> None:
        from render import Call
        import props
        import zoo
        if xm is None:
            raise ValueError(f"{v} P on X: X a chair, stool, bench, throne, bed or charpai")
        name = xm.name if isinstance(xm, props.Prop) else ""
        st = {}

        def seat_pt():
            o, xr, yr = (d.get_center() for d in xm._ref) if isinstance(xm, props.Prop) else (None,) * 3
            if o is None:
                return np.array([xm.get_center()[0], xm.get_top()[1], 0.0])
            ey = (yr - o) / 0.1
            h = (BEDS if v == "sleep" else SEATS).get(name, 0.25)
            return np.array([xm.get_center()[0], (o + h * ey)[1], 0.0])

        def start():
            st["p0"] = dict(pm.pose)
            st["f0"] = pm.feet().copy()
            side = 1.0 if xm.get_center()[0] >= st["f0"][0] else -1.0
            st["f1"] = np.array([xm.get_center()[0] - side * (xm.width / 2 + 0.15 * pm.unit()), st["f0"][1], 0.0])
            if abs(xm.get_center()[0] - st["f0"][0]) < xm.width / 2 + 0.2 * pm.unit():
                st["f1"] = st["f0"].copy()
            st["side"], st["face0"] = side, pm.pose["face"]
            # sat on: facing the way the chair does (its back behind); lain on: the head toward where it came from
            st["sitface"] = xm.facing() if (v == "sit" and isinstance(xm, props.Prop) and name in ("chair",)) else side
            z = max((x.z_index for x in xm.get_family()), default=0)
            pm.set_z_index(max(z + 1, max(x.z_index for x in pm.get_family())))
            st["H"] = pm.height

        def turn_to(face, k):
            p = dict(pm.pose)
            p["face"] = st["fa"] + (face - st["fa"]) * rate_functions.ease_in_out_sine(min(1.0, k))
            pm.set_pose(p)

        def step(a):
            if a < 0.45:                        # to it, turning toward it as it goes
                k = rate_functions.ease_in_out_sine(a / 0.45)
                pos = st["f0"] + (st["f1"] - st["f0"]) * k
                pm.shift(pos - pm.feet())
                p = dict(pm.pose)
                p["face"] = st["face0"] + (st["side"] - st["face0"]) * min(1.0, a / 0.12)
                if np.linalg.norm(st["f1"] - st["f0"]) > 0.05:
                    wp = P.walk_pose(np.linalg.norm(pos - st["f0"]) / max(0.3 * pm.unit(), 1e-3) * math.pi / 2)
                    p.update({key: wp[key] * (1 - k ** 8) + pm.rest[key] * k ** 8 for key in ("fl1", "fl2", "bl1", "bl2", "bob")})
                pm.set_pose(p)
                st["s0"] = zoo.rider_seat(pm).copy()
                st["fa"] = pm.pose["face"]
                return
            k = (a - 0.45) / 0.55
            u = pm.unit()
            seat = seat_pt()
            if v == "sit":                      # a little hop up and back into the seat, sinking into it
                turn_to(st["sitface"], k / 0.4)
                kk = min(1.0, k / 0.7)
                tgt = pm.sit_target()
                self._blend(pm, st["p0"], {**{key: tgt[key] for key in ("fa1", "fa2", "ba1", "ba2", "fl1", "fl2",
                                                                       "bl1", "bl2", "drop")},
                                           "lean": -0.06 * math.sin(math.pi * kk), "smile": 0.5}, rate_functions.ease_in_out_sine(kk))
                goal = seat + DOWN * 0.04 * u
                settle = 0.03 * u * math.sin(math.pi * min(1.0, max(0.0, (k - 0.7) / 0.3)))   # a bounce on landing
                pm.shift(self._arc(st["s0"], goal, kk, 0.18 * u) + DOWN * settle - zoo.rider_seat(pm))
                return
            # lying down: first sat on its edge, then lain back along it, eyes closing
            L = st["H"]
            f = st["side"]
            bx = max(xm.get_left()[0] + L * 0.05, min(xm.get_right()[0] - L * 0.05, xm.get_center()[0] + f * L * 0.45))
            pivot = np.array([bx, seat[1], 0.0])
            if k < 0.4:
                kk = k / 0.4
                turn_to(f, kk / 0.5)
                tgt = pm.sit_target()
                self._blend(pm, st["p0"], {key: tgt[key] for key in ("fa1", "fa2", "ba1", "ba2", "fl1", "fl2", "bl1",
                                                                      "bl2", "drop")}, rate_functions.ease_in_out_sine(kk))
                pm.shift(self._arc(st["s0"], pivot, kk, 0.18 * u) - zoo.rider_seat(pm))
                st["s1"] = zoo.rider_seat(pm).copy()
                return
            kk = rate_functions.ease_in_out_sine((k - 0.4) / 0.6)
            self._blend(pm, st["p0"], {"lids": 1.0, "smile": 0.3, "fa1": 0.35, "fa2": 0.6, "ba1": 0.3, "ba2": 0.5,
                                       "fl1": 0.0, "fl2": 0.0, "bl1": 0.0, "bl2": 0.0, "drop": 0.0}, kk)
            ang = f * (math.pi / 2) * kk          # lain back: the head away from where it sat facing
            pm.rotate(ang - getattr(pm, "fallen", 0.0), about_point=zoo.rider_seat(pm))
            pm.fallen = ang
            lift = getattr(pm, "body_w", 0.2) * u * 0.5 * kk
            pm.shift(pivot + UP * lift - zoo.rider_seat(pm))
            pm.abed = (pivot.copy(), getattr(pm, "body_w", 0.2) * u * 0.5, st["f1"].copy())   # for `stand`
        self.tweens.append(Call(t0, t1, start, step, lambda: None, rate_functions.linear))

    # -- a ball kicked -------------------------------------------------------------------------------------------
    def _kick_ball(self, pn, pm, xn, xm, act, t0, t1) -> None:
        from render import Call
        st = {}
        dur = max(t1 - t0, 0.4)

        def start():
            st["p0"] = dict(pm.pose)
            self._up(xn, xm)

        def step(a):
            k = self._approach(pm, xm, st, a, 0.35, gap=0.05)
            if k <= 0:
                return
            sw = math.sin(math.pi * min(1.0, k / 0.4))
            # a run-up lean back, then a lunge into it with a little hop (a peg figure has no leg to swing)
            self._blend(pm, st["p0"], {"fl1": -0.3 + 1.7 * sw, "fl2": -0.2 + 1.4 * sw,
                                       "lean": -0.25 * sw if k < 0.2 else 0.2 * sw, "bob": 0.05 * sw,
                                       "fa1": -0.6 * sw, "ba1": 0.9 * sw, "mouth": 0.4 * sw, "brow": 0.5 * sw}, 1.0)
            if k > 0.25:
                if "b0" not in st:
                    st["b0"] = xm.get_center().copy()
                    st["b1"] = (self._dest(pn, xm, act) if "to" in act.args else
                                st["b0"] + RIGHT * pm.facing() * 4.0 + UP * 0.0)
                kk = (k - 0.25) / 0.75
                x = st["b0"] + (st["b1"] - st["b0"]) * kk
                hop = abs(math.sin(math.pi * kk * 2.0)) * (1.6 if kk < 0.5 else 0.6) * (1 - 0.5 * kk)
                xm.move_to(x + UP * hop)
                xm.rotate(-pm.facing() * 0.4)
        self.tweens.append(Call(t0, t1, start, step, lambda: None, rate_functions.linear))
        _ = dur

    # -- vehicles ----------------------------------------------------------------------------------------------
    def _drive(self, vn, vm, act, t0, t1) -> None:
        """`drive V to X,Y`: the vehicle goes there, its wheels turning, rocking a little; who rides it comes too."""
        from render import Call
        import props
        if not isinstance(vm, props.Prop):
            raise ValueError(f"drive: {vn} is not a vehicle (a car, cart, bicycle, train, boat...)")
        st = {}

        def start():
            st["c0"] = vm.get_center().copy()
            st["c1"] = self._dest(vn, vm, act)
            go = 1.0 if st["c1"][0] >= st["c0"][0] else -1.0
            if go != vm.facing():
                vm.turn()
            st["last"] = st["c0"].copy()
            st["c1"] = st["c1"] + UP * vm.height / 2        # (its place is where its wheels stand)

        def step(a):
            e = rate_functions.ease_in_out_sine(a)
            pos = st["c0"] + (st["c1"] - st["c0"]) * e
            rock = 0.012 * vm.height * math.sin(a * 40)
            vm.move_to(pos + UP * rock)
            vm.roll(float(np.linalg.norm(pos - st["last"])))
            st["last"] = pos
        self.tweens.append(Call(t0, t1, start, step, lambda: None, rate_functions.linear))

    def _ride_vehicle(self, pn, pm, vn, vm, t0, t1) -> None:
        """`ride P V` on a thing: in the seat of a bicycle, rickshaw, cart, tractor or boat; into a car, bus, train,
        plane, carriage or ship (gone inside, and out again at `dismount`)."""
        from render import Call
        import zoo
        st = {}
        inside = vm.name in INSIDE

        def start():
            st["p0"] = dict(pm.pose)
            st["at"] = zoo.rider_seat(pm).copy()
            self.mounts = [mt for mt in self.mounts if mt[0] is not pm]
            z = max((x.z_index for x in vm.get_family()), default=0)
            if not inside:
                pm.set_z_index(z + 1)

        def step(a):
            goal = vm.saddle()
            pose = zoo.rider_pose(pm)
            pose["face"] = vm.facing()
            k = min(1.0, a * 1.5)
            q = dict(pm.pose)
            for key in ("fa1", "fa2", "ba1", "ba2", "fl1", "fl2", "bl1", "bl2", "drop", "lean", "face"):
                q[key] = st["p0"][key] + (pose[key] - st["p0"][key]) * k
            pm.set_pose(q)
            hop = UP * 0.25 * pm.unit() * math.sin(math.pi * a)
            pm.shift(st["at"] + (goal - st["at"]) * rate_functions.ease_in_out_sine(a) + hop - zoo.rider_seat(pm))
            if inside:
                self._alpha(pm).set(max(0.0, 1 - max(0.0, a - 0.5) / 0.5))

        def stop():
            self.mounts.append([pm, vm])
            pm.inside = inside
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.linear))
