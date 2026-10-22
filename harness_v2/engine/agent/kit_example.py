"""A chapter's first 70 seconds built with the kit: an example of motion, not a template.

The narration is a Hindi chapter about Japan (its lines 0-13 are in the comments, with their times); read this to see
how a Vox-like chapter moves, then build yours in your own way for your own narration. It is not meant to run against
another chapter's timing.

What it shows: one thing at a time, each landing on the word that names it; the camera pushing in and panning on a
map instead of cutting; a wipe between scenes; numbers that count; marks drawn on (highlight, circle, strike, stamp);
diagrams built as the voice names their parts; a slow drift through holds so nothing freezes; and very few plain fades.
"""

from kit import *


class Chapter(KitScene):
    look = "vox"

    def construct(self):
        # [0] 0.0-3.8  Chapter four। अब समुद्र पार Japan की तरफ चलते हैं।
        k = kicker("Chapter four")
        h = headline("समुद्र पार: Japan", size=72)
        VGroup(k, h).arrange(DOWN, buff=0.35)
        self.camera_drift(0.015, 0.003)                      # a slow creep through the title's hold
        self.play(k.appear(), h.appear())
        self.until(self.at(0, "Japan"), lead=0.2)
        self.play(emph(h.part("words"), "pulse"))

        # [1] 4.1-8.1  China के विशाल mainland के सामने Japan एक string of islands है।
        m = Map("east asia")
        self.wipe(then=m)                                     # a scene change: a panel sweeps, the map is under it
        self.camera_drift(0)
        self.until(self.at(1, "mainland"), lead=0.25)
        self.play(m.shade("China", color=L().palette[1]), run_time=0.8)
        china = m.country_label("China", size=34, color=L().ink)
        self.play(china.appear("rise"))
        self.until(self.at(1, "string"), lead=0.2)
        self.play(m.shade("Japan"))
        self.play(self.cam_to(m.view("Japan", pad=0.8), run=1.6))   # the camera goes to the subject

        # [2] 8.4-14.9  Map पर north में Hokkaido, बीच में Honshu, और south की तरफ Shikoku तथा Kyushu पहचानिए।
        pins = {}
        for word, side in (("Hokkaido", RIGHT), ("Honshu", RIGHT), ("Shikoku", DOWN), ("Kyushu", LEFT)):
            self.until(self.at(2, word), lead=0.15)
            pins[word] = m.pin(word, size=20, side=side)
            self.play(pins[word].appear(run=0.4))

        # [3] 15.2-17.9  ये Japan की चार सबसे बड़ी islands हैं।
        self.until(self.at(3, "चार"), lead=0.2)
        four = number("4", size=110, color=L().accent).move_to(self.frame.get_center() + RIGHT * 2.2 + UP * 0.6)
        ring = circle(four, pad=0.3)
        self.play(enter(four, "stamp"))
        self.play(ring.appear())

        # [4] 18.1-24.3  सबसे south की तरफ Okinawan island chain है, लगभग उसी latitude पर जिस पर Bahamas हैं।
        self.until(self.at(4, "Okinawan"), lead=0.3)
        self.play(FadeOut(four), FadeOut(ring), *(FadeOut(p) for p in pins.values()),
                  self.cam_to(m.place_point("Okinawa"), width=8.5, run=1.4))   # pan south rather than cut
        oki = callout(m.place_point("Okinawa"), "Okinawan chain", side=LEFT + UP)
        self.play(oki.appear())
        self.until(self.at(4, "latitude"), lead=0.2)
        lat = DashedLine(m.point(118, 26.3), m.point(147, 26.3), color=L().accent, dash_length=0.12)
        tag_ = label("≈ 26° N · Bahamas भी", size=22, color=L().accent).next_to(lat, UP, buff=0.12).align_to(lat, RIGHT)
        self.play(Create(lat, run_time=1.0), tag_.appear())

        # [5] 24.6-29.0  Latitude से यहाँ north-south position compare कर रहे हैं, दूरी नहीं।
        self.until(self.at(5, "north"), lead=0.2)
        x = lat.get_left()[0] + 1.2
        updown = DoubleArrow([x, lat.get_y() + 1.6, 0], [x, lat.get_y() - 0.6, 0], color=L().ink, buff=0)
        self.play(GrowFromCenter(updown))
        self.until(self.at(5, "दूरी"), lead=0.15)
        dist = text("दूरी", size=30, weight=True).next_to(updown, RIGHT, buff=0.3)
        self.play(dist.appear("rise"))
        self.play(strike(dist).appear())

        # [6] 29.3-34.1  Okinawa को देखकर पूरे Japan का climate एक जैसा मान लेना गलत होगा।
        self.until(self.at(6, "Okinawa"), lead=0.3)
        self.clear_stage("lift", run=0.5)                    # the stage empty, the view is home again
        q = headline("पूरा Japan, एक जैसा climate?", size=54)
        self.play(q.appear())
        self.until(self.at(6, "गलत"), lead=0.15)
        self.play(stamp("गलत", angle=-10, size=48).move_to(q.get_corner(DR) + DOWN * 0.7).appear())

        # [7] 34.4-39.2  Main islands के land area का 50 per cent से भी ज़्यादा हिस्सा mountainous है।
        self.until(self.at(7, "Main"), lead=0.3)
        self.wipe(direction=LEFT)
        grid = units(100, 50, cols=10, shape="square", size=0.32).shift(LEFT * 3)
        self.play(grid.appear(run=1.0))
        self.until(self.at(7, "50"), lead=0.2)
        big = number("50%+", size=110, color=L().accent).shift(RIGHT * 3 + UP * 0.6)
        self.play(grid.fill(run=1.2), count(big, run=1.2))
        sub = text("पहाड़ी ज़मीन", size=36, weight=True).next_to(big, DOWN, buff=0.2)
        self.play(sub.appear("rise"), highlight(sub).appear())

        # [8] 39.5-44.9  यानी map पर जितनी ज़मीन दिखाई देती है, उसका आधे से ज़्यादा हिस्सा पहाड़ी है।
        self.until(self.at(8, "आधे"), lead=0.2)
        self.play(emph(grid, "pulse", k=1.05), self.cam_push(1.08, run=4.5))   # a slow push through the hold

        # [9] 45.2-48.3  Japan एक बहुत active earthquake zone में भी है।
        self.until(self.at(9, "earthquake"), lead=0.3)
        self.clear_stage("sink", run=0.4)
        jm = Map("japan")
        self.play(jm.appear(run=1.0))
        warn = stamp("EARTHQUAKE ZONE", size=40).shift(RIGHT * 3.6 + DOWN * 2.2)
        self.play(warn.appear(), emph(jm, "shake"))

        # [10] 48.6-52.9  अब बताइए, घर बनाने वाला इन conditions को ignore कर सकता है?
        # [11] 53.2-56.5  नहीं, geography architecture को भी shape करती है।
        self.until(self.at(10, "घर"), lead=0.3)
        self.wipe()
        f = Flow([{"name": "geo", "label": "Geography", "icon": "mountain"},
                  {"name": "cond", "label": "Conditions", "icon": "earthquake"},
                  {"name": "arch", "label": "Architecture", "icon": "house", "key": True}],
                 [("geo", "cond"), ("cond", "arch", "shapes")])
        self.play(f.reveal("geo"))
        self.until(self.at(10, "conditions"), lead=0.2)
        self.play(f.reveal("cond"))
        self.until(self.at(11, "architecture"), lead=0.2)
        self.play(f.reveal("arch"))
        self.play(f.pulse("geo", "cond"), run_time=0.6)
        self.play(f.pulse("cond", "arch"), run_time=0.6)

        # [12] 56.8-64.2  Building सिर्फ देखने में अच्छी हो, इतना काफी नहीं; उसे अपनी जगह की conditions के हिसाब से ...
        self.until(self.at(12, "Building"), lead=0.3)
        self.play(f.animate.scale(0.7).to_edge(UP, buff=0.5))
        good = checklist(["देखने में अच्छी", "अपनी जगह की conditions के हिसाब से"], marker="square", size=32, width=9).shift(DOWN * 1.2)
        self.play(good.reveal(0))
        self.until(self.at(12, "काफी"), lead=0.2)
        self.play(cross(0.4).next_to(good.rows[0], RIGHT, buff=0.3).appear())
        self.until(self.at(12, "हिसाब"), lead=0.3)
        self.play(good.reveal(1))
        self.play(tick(0.45).next_to(good.rows[1], RIGHT, buff=0.3).appear())

        # [13] 64.5-69.1  Population largely Japanese है, लेकिन Ainu की छोटी minority भी है।
        self.until(self.at(13, "Population"), lead=0.3)
        self.clear_stage("fade", run=0.4)
        a = portrait("Japanese", None, picture=person(hair="short", clothes="kimono"), role="बहुसंख्यक")
        b = portrait("Ainu", None, picture=person(hair="long", beard="full", clothes="robe", skin="tan"), role="छोटी minority")
        row([a, b], gap=1.2).move_to(DOWN * 0.2)
        self.play(a.appear())
        self.until(self.at(13, "Ainu"), lead=0.2)
        self.play(b.appear())
        self.play(circle(b, pad=0.15).appear())

        self.wait_until_end()
