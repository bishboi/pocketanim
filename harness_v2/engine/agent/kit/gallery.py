"""The kit's gallery: every kind of piece previewed in each look, put side by side (vox left, blueprint right).

    .venv/bin/python harness_v2/engine/agent/kit/gallery.py <out_dir> [name ...]

Each snippet runs through tools/kit_preview.py (the agent's kit_preview tool) in both looks; <out_dir>/<name>.jpg is
the pair of last frames. A test that every piece builds and draws, and a look at how it draws.
"""

import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "kit_preview.py"

SNIPPETS = {
 "text-and-marks": "h = headline(\"A long tradition of history\")\nh.to_edge(UP, buff=0.8)\nk = kicker(\"China · Japan\").next_to(h, UP, buff=0.3)\nc = card(4, 2.4, title=\"Official histories\", body=\"Written by court departments\", kick=\"SOURCE 1\").shift(LEFT * 3.5 + DOWN * 0.8)\nt = text(\"दोनों देशों में इतिहास लिखने की लंबी परंपरा थी।\", size=32, width=5).shift(RIGHT * 3 + DOWN * 0.3)\nm = circle(t)\ns = stamp(\"OFFICIAL\").shift(RIGHT * 3 + DOWN * 2.4)\nself.play(h.appear(), FadeIn(k))\nself.play(c.appear(), t.appear())\nself.play(m.appear(), s.appear())\n",
 "map": "m = Map(\"east asia\", names=True)\nself.play(m.appear())\nself.play(m.shade(\"Japan\"), m.shade(\"China\", color=L().palette[1]))\nk = m.pin(\"Kyoto\")\nb = m.pin(\"Beijing\", side=LEFT)\nself.play(k.appear(), b.appear())\nr = m.route([\"Beijing\", \"Nanjing\", \"Hangzhou\", \"Nagasaki\", \"Kyoto\"])\nself.play(r.appear(run=2))\n",
 "timeline": "tl = Timeline(1200, 1950, width=12).shift(UP * 1.6)\nself.play(tl.appear())\ne1 = tl.event(1869, \"Meiji history bureau\")\ne2 = tl.event(1907, \"Kyoto Oriental Studies\")\ne3 = tl.event(1914, \"Shinaron\")\nself.play(e1.appear(), e2.appear(), e3.appear())\np1 = tl.lifespan(\"Marco Polo\", 1254, 1324, stay=(1274, 1290, \"in China\"))\np2 = tl.lifespan(\"Matteo Ricci\", 1552, 1610)\np3 = tl.lifespan(\"Luis Frois\", 1532, 1597)\np4 = tl.lifespan(\"Naito Konan\", 1866, 1934)\nself.play(stagger([p1, p2, p3, p4], lag=0.3))\n",
 "people": "a = person(hat=\"official\", beard=\"long\", clothes=\"robe\")\nb = person(hat=\"scholar\", beard=\"long\", clothes=\"robe\", skin=\"light\")\nc = person(hair=\"short\", beard=\"mustache\", glasses=True, clothes=\"suit\")\nd = person(hair=\"tonsure\", clothes=\"cassock\", skin=\"light\")\ne = person(hat=\"cap\", beard=\"full\", clothes=\"robe\", skin=\"light\", clothes_color=\"#3D6FA3\")\nf = person(silhouette=True)\nfit_to(row([a, b, c, d, e, f], gap=0.5), 13.4).to_edge(UP, buff=0.4)\np1 = portrait(\"Sima Qian\", \"145–86 BCE\", picture=person(hat=\"official\", beard=\"long\", clothes=\"robe\"), role=\"Grand Historian\")\np2 = portrait(\"Luis Frois\", \"1532–1597\", role=\"Jesuit in Japan\")\nrow([p1, p2], gap=1).scale(0.75).to_edge(DOWN, buff=0.3)\nself.play(stagger([a, b, c, d, e, f]), p1.appear(), p2.appear())\n",
 "diagrams": "f = Flow([\"Rulers\", \"History office\", {\"name\": \"Official history\", \"key\": True}, \"Later rulers\"],\n         [(\"Rulers\", \"History office\", \"set up\"), (\"History office\", \"Official history\", \"writes\"), (\"Official history\", \"Later rulers\", \"judges\")])\nf.scale(0.8).to_edge(UP, buff=0.6)\nself.play(f.appear())\nself.play(f.pulse(\"Rulers\", \"History office\"))\nt = Tree({\"Sources\": {\"Insiders\": {\"Official\": {}, \"Scholarly\": {}, \"Popular\": {}}, \"Outsiders\": {\"Travellers\": {}, \"Missionaries\": {}}}})\nt.scale(0.7).to_edge(DOWN, buff=0.3)\nself.play(t.appear())\nself.play(t.focus(\"Outsiders\", \"Travellers\", \"Missionaries\"))\n",
 "charts": "b = bars({\"Official\": 40, \"Scholarly\": 25, \"Popular\": 20, \"Religious\": 15}, width=6, height=3, unit=\"%\").shift(LEFT * 3.3 + UP * 1.6)\nd = donut({\"China\": 60, \"Japan\": 30, \"Europe\": 10}, radius=1.4, thickness=0.45, centre=\"Sources\").shift(RIGHT * 3.8 + UP * 1.6)\nu = units(50, 12, label=\"12 of 50\", shape=\"dot\").scale(0.8).shift(LEFT * 3.5 + DOWN * 2.2)\nn = Network({\"N\": \"Naito Konan\", \"C\": \"Chinese tradition\", \"J\": \"Journalism\", \"W\": \"Western method\", \"K\": \"Kyoto Univ.\"},\n            [(\"C\", \"N\"), (\"J\", \"N\"), (\"W\", \"N\"), (\"N\", \"K\")]).scale(0.55).shift(RIGHT * 3.3 + DOWN * 2.0)\nself.play(b.appear(), d.appear(), u.appear(), n.appear())\nself.play(b.highlight(\"Scholarly\"), u.fill(), d.pop(\"Japan\"))\n",
 "documents": "d = document(\"史記\", seal=\"史\").shift(LEFT * 5)\nc = clipping(\"Meiji government sets up history bureau\", masthead=\"TOKYO TIMES\", date=\"1869\").scale(0.8).shift(LEFT * 0.8 + UP * 1.5)\ns = scroll(\"The Records of the Grand Historian\", width=6, height=2).scale(0.8).shift(RIGHT * 2 + DOWN * 2.2)\nbk = book(\"Science and Civilisation in China\", author=\"Joseph Needham\").scale(0.8).shift(RIGHT * 4.8 + UP * 1.6)\nsh = shelf([\"Vol 1\", \"Vol 2\", \"Vol 3\", \"Vol 4\", \"Vol 5\", \"Vol 6\", \"Vol 7\"], height=2).shift(LEFT * 1 + DOWN * 2.3)\nst = sticky(\"कौन लिख रहा है?\").scale(0.7).shift(RIGHT * 2.2 + UP * 1.6)\nself.play(stagger([d, c, bk, sh, st]), s.appear())\nself.play(self.cam_to(c, run=1))\nself.play(underline(c.part(\"headline\")).appear())\n",
 "icons-photos-quotes": "from pathlib import Path\npic = Path(__import__(\"kit\").__file__).resolve().parents[1] / \"style-vox.jpg\"\nph = photo(pic, height=3.0, caption=\"an archival picture\").shift(LEFT * 4.3 + UP * 1.2)\nics = row([icon(n, size=0.9) for n in (\"ship\", \"scroll\", \"book\", \"temple\", \"compass\")], gap=0.35).shift(RIGHT * 2.5 + UP * 2.6)\nq = quote(\"History is written by the victors.\", who=\"a saying\", width=6, size=28).shift(RIGHT * 2.4 + UP * 0.6)\ncr = crowd(14, rows=2, height=0.55).shift(LEFT * 4.2 + DOWN * 2.4)\nc = caption(\"एक ही समाज, दो नज़रिये\")\nself.play(ph.appear(), stagger(list(ics)), q.appear(), cr.appear(), c.appear())\nself.play(spotlight(q).appear())\n",
 "more-diagrams": "cy = Cycle([\"Rulers\", \"Records\", \"History\", \"Judgement\"], radius=1.4, size=18, width=1.7).scale(0.8).shift(LEFT * 4.6 + UP * 1.6)\nhb = Hub(\"Naito\", [\"Chinese study\", \"Journalism\", \"Western method\"], radius=1.3, size=18, width=1.8).scale(0.75).shift(RIGHT * 0.2 + UP * 1.7)\npy = Pyramid([\"Emperor\", \"Aristocrats\", \"Officials\", \"Local society\"], width=4.2, height=2.6, size=20).shift(RIGHT * 4.6 + UP * 1.6)\nch = Chain([\"Winners\", \"write history\", \"their point of view\", \"read it critically\"], size=18, width=2.0).shift(DOWN * 1.0)\nlc = line_chart([(1600, 10), (1700, 25), (1800, 60), (1900, 140)], width=4.5, height=1.6, x_label=\"year\").shift(LEFT * 3.6 + DOWN * 2.9)\nvs = versus(\"Inside\", [\"court histories\", \"scholars\"], \"Outside\", [\"travellers\", \"missionaries\"], width=6.4, size=18).shift(RIGHT * 3.6 + DOWN * 2.9)\nself.play(cy.appear(), hb.appear(), py.appear(), ch.appear(), lc.appear(), vs.appear())\n",
 "historical-map": "m = Map(\"china\", year=1100)\nself.play(m.appear())\ns = m.empire(\"Song\", 1100)\nself.play(s.appear())\nlab = label(f\"{s.state_name}, {s.year}\", size=26).move_to(m.place_point(\"Kaifeng\") + DOWN * 1.2)\nself.play(m.pin(\"Kaifeng\").appear(), lab.appear())\nself.wipe(then=headline(\"960 – 1279\"))\n"
}


def preview(code: str, look: str, work: Path) -> dict:
    f = work / f"{abs(hash((code, look)))}.py"
    f.write_text(code, encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOL), str(work), str(f), str(work / "out"), look], capture_output=True, text=True)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "error": (r.stderr or r.stdout)[-1500:]}


def main(out: Path, names: list[str]) -> int:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="kit_gallery_"))
    jobs = [(n, lk) for n in (names or SNIPPETS) for lk in ("vox", "blueprint")]
    with ThreadPoolExecutor(4) as pool:
        results = dict(zip(jobs, pool.map(lambda j: preview(SNIPPETS[j[0]], j[1], work), jobs)))
    failed = 0
    for n in names or SNIPPETS:
        a, b = results[(n, "vox")], results[(n, "blueprint")]
        if not (a.get("ok") and b.get("ok")):
            failed += 1
            print(f"{n}: FAILED\n{a.get('error') or b.get('error')}")
            continue
        ia, ib = Image.open(a["still"]).convert("RGB"), Image.open(b["still"]).convert("RGB")
        pair = Image.new("RGB", (ia.width + ib.width + 12, ia.height), "#000")
        pair.paste(ia, (0, 0))
        pair.paste(ib, (ia.width + 12, 0))
        pair.save(out / f"{n}.jpg", quality=86)
        print(f"{n}: ok")
    return failed


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2:]))
