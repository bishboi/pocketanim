"""What kind of lecture a piece of content wants: its subject, and the kit that goes with it.

The subject decides the style, whether the map is a main character or a guest,
which pictures the stage should use (molecules for chemistry, equations and
graphs for physics, timelines and quotes for history...), and what the model
is told. Classification is a fast, deterministic vocabulary score with a few
structural signals (years, chemical formulas, equations, place names), so it
works offline and says why it chose.

    python harness/lecture/genre.py < content.txt        # prints {genre, style, scores, kit}
"""

from __future__ import annotations

import json
import re
import sys

VOCAB = {
    "geography": """river rivers mountain mountains plateau plain plains desert climate rainfall monsoon latitude
        longitude border borders state states region regions capital population district coast coastal delta
        forest forests soil soils crop crops agriculture irrigation relief terrain map continent ocean lake
        lakes valley himalaya ganga ganges yamuna mineral minerals km area landforms tributary basin wildlife
        conservation biodiversity resource resources sanctuary sanctuaries reserve reserves park parks""",
    "history": """empire emperor king kings queen dynasty war wars battle battles revolt revolution rebellion
        treaty kingdom sultan mughal british colonial independence century centuries ancient medieval reign
        ruled ruler rulers conquered invasion army armies freedom movement partition president parliament
        constitution civilisation civilization era period archaeology monument fort temple empire rajput
        maratha company viceroy nawab pharaoh roman greek historian""",
    "biology": """cell cells organism organisms tissue organ organs photosynthesis chlorophyll respiration dna rna
        gene genes genetic chromosome protein proteins enzyme enzymes bacteria virus species evolution
        ecosystem heart blood digestion nervous hormone plant plants animal animals leaf leaves root roots
        reproduction mitosis meiosis nucleus membrane immune""",
    "chemistry": """atom atoms molecule molecules compound compounds element elements reaction reactions acid
        acids base bases salt bond bonds ion ions electron electrons valency oxidation reduction catalyst
        solution solvent periodic metal metals carbon hydrogen oxygen nitrogen organic polymer ph mole
        equation formula combustion""",
    "physics": """force forces motion velocity speed acceleration mass energy momentum gravity gravitational
        newton wave waves light sound frequency wavelength electric electricity current voltage resistance
        magnetic field fields quantum relativity particle particles friction pressure heat temperature
        thermodynamics lens mirror refraction reflection orbit planet planets star stars galaxy universe""",
    "mathematics": """equation equations function functions graph graphs derivative integral calculus algebra
        geometry triangle circle angle angles theorem proof prime primes number numbers fraction fractions
        probability statistics matrix vector vectors polynomial quadratic linear exponential logarithm
        sequence series limit sum product ratio proportion""",
    "economics": """economy economic market markets price prices demand supply inflation gdp growth trade
        export exports import imports tax taxes bank banks money investment income employment unemployment
        industry industries budget fiscal monetary interest profit cost costs""",
}
# The same subjects in Hindi (NCERT's vocabulary), so a Hindi chapter is classified by its words, not only its dates.
VOCAB_HI = {
    "geography": """नदी नदियाँ नदियों पर्वत पहाड़ पठार मैदान मरुस्थल जलवायु वर्षा मानसून अक्षांश देशांतर सीमा राज्य राज्यों
        क्षेत्र क्षेत्रों प्रदेश राजधानी जनसंख्या जिला जिले जिलों तट तटीय डेल्टा वन वनों जंगल जंगलों मृदा मिट्टी फसल फसलें
        कृषि सिंचाई भूमि महाद्वीप महासागर झील घाटी हिमालय गंगा यमुना खनिज संसाधन संसाधनों वन्य संरक्षण अभयारण्य उद्यान
        आवास पर्यावरण भूगोल मानचित्र""",
    "history": """साम्राज्य सम्राट राजा राजाओं रानी वंश राजवंश युद्ध युद्धों लड़ाई विद्रोह क्रांति संधि सुल्तान मुगल ब्रिटिश
        अंग्रेज़ अंग्रेज औपनिवेशिक स्वतंत्रता आज़ादी शताब्दी सदी प्राचीन मध्यकालीन शासन शासक शासकों आक्रमण सेना विभाजन
        संविधान सभ्यता इतिहास इतिहासकार किला राष्ट्रवाद""",
    "biology": """कोशिका कोशिकाएँ ऊतक अंग संश्लेषण श्वसन आनुवंशिक गुणसूत्र प्रोटीन एंजाइम जीवाणु विषाणु विकास हृदय रक्त
        पाचन तंत्रिका हार्मोन पौधे पौधा जंतु पत्ती पत्तियाँ जड़ प्रजनन केंद्रक""",
    "chemistry": """परमाणु अणु यौगिक तत्व अभिक्रिया अभिक्रियाएँ अम्ल क्षार लवण आबंध आयन इलेक्ट्रॉन संयोजकता ऑक्सीकरण अपचयन
        उत्प्रेरक विलयन धातु धातुएँ कार्बन हाइड्रोजन ऑक्सीजन नाइट्रोजन रासायनिक दहन""",
    "physics": """बल गति वेग चाल त्वरण द्रव्यमान ऊर्जा संवेग गुरुत्वाकर्षण तरंग तरंगें ध्वनि आवृत्ति तरंगदैर्ध्य विद्युत
        धारा विभव प्रतिरोध चुंबकीय घर्षण दाब ऊष्मा ताप लेंस दर्पण अपवर्तन परावर्तन ग्रह तारा""",
    "mathematics": """समीकरण फलन ग्राफ अवकलज समाकलन बीजगणित ज्यामिति त्रिभुज वृत्त कोण प्रमेय उपपत्ति अभाज्य संख्या
        संख्याएँ भिन्न प्रायिकता सांख्यिकी आव्यूह सदिश बहुपद द्विघात रैखिक घातांक लघुगणक अनुक्रम श्रेणी गुणनफल अनुपात""",
    "economics": """अर्थव्यवस्था आर्थिक बाज़ार बाजार मूल्य कीमत माँग मांग आपूर्ति मुद्रास्फीति जीडीपी व्यापार निर्यात आयात
        बैंक मुद्रा निवेश आय रोज़गार रोजगार बेरोज़गारी उद्योग बजट ब्याज लाभ लागत""",
}
PROFILES = {
    "geography": {
        "label": "Geography", "style": "vox", "map": "often",
        "kit": ["marker", "river", "state", "journey", "diagram", "figure", "gallery", "compare", "bars", "sim"],
        "guidance": "Geography: the map carries the where (markers, rivers, states) and movement (a journey: the "
                    "monsoon winds, a trade route, a river's course); the stage carries how it works: diagrams built "
                    "from drawings (how rivers feed a delta, what a crop needs), the water cycle and the seasons as "
                    "sims (water_cycle, seasons), the Earth's or the soil's layers peeled (sim layers), real figures "
                    "as data stories (sim columns: rainfall by month; pyramid; trend), the document's figures, "
                    "comparisons and differences (sim differences). Photos only for people, communities and historic "
                    "places.",
    },
    "history": {
        "label": "History", "style": "parchment", "map": "sometimes",
        "kit": ["timeline", "gallery", "diagram", "figure", "marker", "journey", "arrow", "quote", "compare", "sim"],
        "guidance": "History: open each era with a timeline on the stage, and zoom from the century into the decade "
                    "the lecture is about (sim timeline_zoom); show the people, communities and places of a "
                    "paragraph together in a gallery (portraits, monuments, paintings); build causes and consequences "
                    "as a chain (diagram kind flow, edges saying why) revealed step by step; journeys on the map as "
                    "they happened (journey: the Dandi March, Vasco da Gama, the Silk Road); differences between two "
                    "systems or periods as flip cards (sim differences); quote primary sources; the map for where "
                    "events happened, routes and empires.",
    },
    "biology": {
        "label": "Biology", "style": "lab", "map": "rarely",
        "kit": ["figure", "illustration", "diagram", "sketch", "compare", "define", "manim", "graph", "equation", "sim",
                "draw"],
        "guidance": "Biology: pick the format from what the paragraph is. A STRUCTURE (a cell, a leaf, a flower, the "
                    "heart, a neuron, a nephron): the book's figure or a textbook illustration (find_illustration), "
                    "and when its parts are named one by one, a labelled sketch (or manim) built part by part with "
                    "each label revealed as it is said. A PROCESS (digestion, photosynthesis, blood flow, a reflex, "
                    "protein synthesis): a flow or steps diagram with a drawing in each node, a stage at a time; a "
                    "CYCLE (cell cycle, life cycles, the cardiac cycle, nitrogen cycle): diagram kind cycle. A "
                    "HIERARCHY or CLASSIFICATION (cell, tissue, organ, system; kingdoms, phyla): diagram kind tree or "
                    "steps. A detailed structure no sketch can show well (a nephron, a neuron, an eye, a flower in section): "
                    "draw it (draw). Two things side by side (mitosis and meiosis, plant and animal cells, arteries and "
                    "veins): compare. Something that MOVES (diffusion and osmosis, chromosomes separating, a heart "
                    "beating, a muscle contracting, an impulse along a neuron): manim, set moving as it is said. "
                    "Measurements (growth, enzyme activity against temperature, populations): graph. Hard terms: "
                    "define. Photos only of organisms, habitats and scientists the lecture names. A molecule's "
                    "structural formula only where the lecture explains its structure (DNA's base pairs, ATP's "
                    "phosphates), never for every substance named; a summary reaction with equation. No map unless "
                    "the topic is where life lives.",
    },
    "chemistry": {
        "label": "Chemistry", "style": "lab", "map": "never",
        "kit": ["molecule", "equation", "graph", "sketch", "piston", "problem", "work", "define", "compare", "sim",
                "counter", "draw"],
        "guidance": "Chemistry: show a molecule's structural formula (molecule: name, formula or SMILES) only "
                    "where its structure is what is being taught: its bonds, its shape, its functional groups, "
                    "isomers, how it reacts because of them; once, not again each time it is named, and never for a "
                    "substance only mentioned (water, air, salt in passing). Write "
                    "reactions with equation (reactants -> products, subscripts as H_2O), plot rates, concentrations "
                    "and energy profiles with graph, draw apparatus (a beaker, a gas syringe, a burette) with sketch and "
                    "gases with piston. Numerical problems (moles, concentration, gas laws, equilibrium) are solved "
                    "with problem and work. "
                    "THEORY, THEN PROBLEMS: for each concept, first the theory, built on the board a piece at a time; then 2-3 "
                    "long problems on it (problem op: the full question, its figure, given and find), each "
                    "solved in detail over many beats (work op: one step a beat, every step explained, the answer "
                    "boxed). Label everything. Build pictures in Manim (draw only what the Manim ops cannot show "
                    "well); no photos except of a scientist the lecture names.",
    },
    "physics": {
        "label": "Physics", "style": "blueprint", "map": "never",
        "kit": ["incline", "pulley", "piston", "spring", "pendulum", "projectile", "circuit", "lever", "lens",
                "sketch", "graph", "problem", "work", "equation", "define", "sim", "counter", "trace", "zoom", "draw"],
        "guidance": "Physics: draw every situation as a labelled diagram (the presets incline, pulley, piston, spring, "
                    "pendulum, projectile, circuit, lever, lens, or a sketch for anything else), then reveal its "
                    "forces, velocities and lengths one by one as the narration names them; graph how quantities "
                    "vary (v against t, and the area under it, x against t, P against V); state each law as an "
                    "equation; show a process happening with a sim (orbit, wave, collision, field, refraction) and a moving "
                    "graph with trace. "
                    "THEORY, THEN PROBLEMS: for each concept, first the theory, built on the board a piece at a time; then 2-3 "
                    "long problems on it (problem op: the full question, its figure, given and find), each "
                    "solved in detail over many beats (work op: one step a beat, every step explained, the answer "
                    "boxed). Label everything. Build pictures in Manim (draw only what the Manim ops cannot show "
                    "well); no photos except of a scientist the lecture names.",
    },
    "mathematics": {
        "label": "Mathematics", "style": "chalkboard", "map": "never",
        "kit": ["graph", "sketch", "work", "problem", "equation", "define", "trace", "sweep", "sim"],
        "guidance": "Mathematics: graph every function you discuss (curves, points, tangents, areas, roots marked); "
                    "draw geometry with sketch (triangles and circles with their angles and lengths labelled), and a "
                    "construction step by step with ruler and compass (sim construction); derive and solve with work, "
                    "one step per beat, each step said and justified; an equation solved on a balance (sim balance). "
                    "Young classes: numbers as hops on a number line, fraction bars, place-value blocks (sims "
                    "numberline, fractions, placevalue). Ideas that move: the unit circle and the sine wave "
                    "(unit_circle), area under a curve (area_fill), chance (probability), moving a graph "
                    "(transform_graph). "
                    "THEORY, THEN PROBLEMS: for each concept, first the theory, built on the board a piece at a time; then 2-3 "
                    "long problems on it (problem op: the full question, its figure, given and find), each "
                    "solved in detail over many beats (work op: one step a beat, every step explained, the answer "
                    "boxed). Label everything. Build pictures in Manim (draw only what the Manim ops cannot show "
                    "well); no photos except of a scientist the lecture names.",
    },
    "economics": {
        "label": "Economics", "style": "atlas", "map": "sometimes",
        "kit": ["diagram", "bars", "plot", "compare", "define", "stat", "marker", "sim"],
        "guidance": "Economics: show quantities as bars and trends as plot, or as a data story with real figures (sims "
                    "bar_race, trend, columns, pyramid), supply and demand moving (sim supply_demand), money growing "
                    "(sim compound_interest), mechanisms (how inflation spreads) as a chain of causes revealed step by "
                    "step, kinds side by side with compare or flip cards (sim differences), and places on the map only "
                    "when trade or regions are the point.",
    },
    "general": {
        "label": "General", "style": "vox", "map": "sometimes",
        "kit": ["diagram", "figure", "gallery", "define", "compare", "timeline", "bars"],
        "guidance": "Give each paragraph one visual that explains it: a diagram built from drawings, the "
                    "document's figures, a comparison, a timeline; pictures only of people and places; the map only "
                    "for where.",
    },
}

# The sims each science has for what moves or builds up (live.py, sims_more.py), added to its guidance.
_SIM_HINTS = {
    "physics": "Sims for what moves: pendulum_period, projectile_angle, circuit_brightness (series against parallel), "
               "magnetic_wire, lens_image (the object walks in, the image follows), sound (compressions), as well as "
               "orbit, wave, collision, field and refraction.",
    "chemistry": "Sims: balance_equation (atoms counted each side as it is balanced), ph_scale, electrolysis, states "
                 "(solid to liquid to gas as it is heated), rusting, titration, gas, decay.",
    "biology": "Sims: digestion (food down the gut), double_circulation, photosynthesis, punnett (Mendel's cross), "
               "food_web (take a species away), mitosis, heart; a structure peeled from the outside in (draw with a "
               "part per layer, or sim layers); differences as flip cards (sim differences).",
}
for _genre, _hint in _SIM_HINTS.items():
    PROFILES[_genre]["guidance"] += " " + _hint
# English terms as YouTube's Hindi captions spell them (फोर्स for force): a Hinglish lecture's captions have few
# NCERT Hindi words, and without these its only clue was a date or two (Newton, 1642-1727) and it read as history.
VOCAB_TRANSLIT = {
    "geography": "रिवर माउंटेन प्लेटो क्लाइमेट मानसून रेनफॉल लैटीट्यूड लॉन्गिट्यूड कॉन्टिनेंट ओशन डेल्टा मैप",
    "history": "किंग एम्पायर डायनेस्टी वॉर बैटल रिवॉल्यूशन रिवोल्ट ट्रीटी ब्रिटिश कॉलोनियल इंडिपेंडेंस हिस्ट्री",
    "biology": "सेल सेल्स टिशू ऑर्गन डीएनए आरएनए जीन प्रोटीन एंजाइम बैक्टीरिया वायरस प्लांट फोटोसिंथेसिस",
    "chemistry": "एटम एटम्स मॉलिक्यूल मॉलिक्यूल्स कंपाउंड एलिमेंट एसिड बॉन्ड आयन इलेक्ट्रॉन वैलेंसी ऑक्सीडेशन मोल",
    "physics": """फोर्स फोर्सेज टेंशन नार्मल नॉर्मल रिएक्शन मोशन न्यूटन न्यूटन्स एक्सेलरेशन एक्सीलरेशन वेलोसिटी
        स्पीड मास स्प्रिंग फ्रिक्शन फ्रिक्शनल ग्रेविटी ग्रेविटेशनल एनर्जी मोमेंटम इनर्शिया पुली फील्ड करंट वोल्टेज
        फ्री बॉडी डायग्राम इक्विलिब्रियम मैकेनिक्स काइनेमेटिक्स डायनेमिक्स एमजी""",
    "mathematics": "इक्वेशन फंक्शन ग्राफ एंगल ट्रायंगल सर्कल वेक्टर मैट्रिक्स डेरिवेटिव इंटीग्रेशन प्रोबेबिलिटी",
    "economics": "इकोनॉमी मार्केट डिमांड सप्लाई प्राइस इन्फ्लेशन जीडीपी बैंक इन्वेस्टमेंट",
}
WORDS = {genre: set(v.split()) | set(VOCAB_HI.get(genre, "").split()) | set(VOCAB_TRANSLIT.get(genre, "").split())
         for genre, v in VOCAB.items()}
FORMULA = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")
YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b|\b\d{1,2}(?:st|nd|rd|th) century\b", re.I)
MATHS = re.compile(r"[=^√∫∑π]|\b(sin|cos|tan|log|dx|dy)\b")


def classify(text: str) -> dict:
    """{genre, label, style, map, kit, guidance, scores, confidence, why}."""
    low = (text or "").lower()
    tokens = re.findall(r"[a-z]+|[\u0900-\u097F]+", low)
    total = max(len(tokens), 1)
    scores = {g: sum(1 for t in tokens if t in words) / total * 100 for g, words in WORDS.items()}
    why = []
    years = len(YEAR.findall(text or ""))
    if years:
        # Dates count by how thick they are in the text: a history chapter is full of them, while a science
        # lecture names a year or two (a scientist's lifetime) in thousands of words.
        density = years / max(total / 250, 1)
        scores["history"] += min(density, 12) * 0.8
        why.append(f"{years} dates")
    formulas = [f for f in FORMULA.findall(text or "") if re.search(r"\d", f) or f in ("NaCl", "HCl", "CO")]
    if formulas:
        scores["chemistry"] += min(len(formulas), 10) * 1.2
        why.append(f"formulas {formulas[:3]}")
    maths = len(MATHS.findall(text or ""))
    if maths:
        scores["mathematics"] += min(maths, 10) * 0.5
        scores["physics"] += min(maths, 10) * 0.3
        why.append(f"{maths} maths signs")
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    genre, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top < 1.0:
        genre = "general"
    confidence = round(min(1.0, (top - second) / (top or 1) + 0.3), 2) if genre != "general" else 0.0
    profile = PROFILES[genre]
    return {"genre": genre, **profile, "scores": {k: round(v, 2) for k, v in ranked}, "confidence": confidence,
            "why": why}


def profile(genre: str) -> dict:
    """The profile of a subject chosen by hand (the page's Subject menu), in classify()'s shape."""
    genre = genre if genre in PROFILES else "general"
    return {"genre": genre, **PROFILES[genre], "scores": {}, "confidence": 1.0, "why": ["chosen"]}


if __name__ == "__main__":
    # genre.py < text            the subject the text is about
    # genre.py --genre physics   a subject's profile
    if len(sys.argv) > 2 and sys.argv[1] == "--genre":
        print(json.dumps(profile(sys.argv[2]), indent=1))
    else:
        print(json.dumps(classify(sys.stdin.read()), indent=1))
