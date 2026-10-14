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
        "kit": ["marker", "river", "state", "journey", "relief", "diagram", "figure", "picture", "compare", "bars",
                "manim"],
    },
    "history": {
        "label": "History", "style": "parchment", "map": "sometimes",
        "kit": ["timeline", "picture", "diagram", "figure", "marker", "journey", "arrow", "empire", "quote", "compare",
                "manim"],
    },
    "biology": {
        "label": "Biology", "style": "lab", "map": "rarely",
        "kit": ["figure", "picture", "diagram", "compare", "define", "manim", "equation", "draw"],
    },
    "chemistry": {
        "label": "Chemistry", "style": "lab", "map": "never",
        "kit": ["diagram", "molecule", "equation", "problem", "work", "define", "compare", "draw", "manim"],
    },
    "physics": {
        "label": "Physics", "style": "blueprint", "map": "never",
        "kit": ["diagram", "problem", "work", "equation", "define", "zoom", "draw", "manim"],
    },
    "mathematics": {
        "label": "Mathematics", "style": "chalkboard", "map": "never",
        "kit": ["diagram", "work", "problem", "equation", "define", "manim"],
    },
    "economics": {
        "label": "Economics", "style": "atlas", "map": "sometimes",
        "kit": ["diagram", "bars", "compare", "define", "stat", "marker", "manim"],
    },
    "general": {
        "label": "General", "style": "vox", "map": "sometimes",
        "kit": ["diagram", "figure", "picture", "define", "compare", "timeline", "bars"],
        "guidance": "Give each paragraph one visual that explains it: a diagram built from drawings, the "
                    "document's figures, a comparison, a timeline; pictures only of people and places; the map only "
                    "for where.",
    },
}

# Where each subject's ideas become diagrams of boxes and arrows (diagram ops: flow, cycle, hub, pyramid), whichever
# way the drawings are made: a process, a sequence, causes and effects, kinds of something are diagrams, not cards.
_DIAGRAM_HINTS = {
    "physics": "Diagrams too: a procedure or a method of solving (drawing a free-body diagram, applying a law) as a "
               "numbered flow (\"steps\": true); kinds of something (forces, energy, motion, waves) as a hierarchy; "
               "energy changing form, or a chain of cause and effect (heating -> expansion -> pressure), as a flow; "
               "a big idea and what it connects to as a hub.",
    "chemistry": "Diagrams too: a lab procedure or an industrial process (the steps of a titration, the Haber "
                 "process, extracting a metal) as a numbered flow; classifications (matter, reactions, elements, "
                 "compounds) as a hierarchy; a cycle (the carbon or nitrogen cycle) as a cycle; what decides a "
                 "property or a rate as a hub.",
    "mathematics": "Diagrams too: a method in steps (completing the square, a proof's chain of reasons, an "
                   "algorithm) as a numbered flow; kinds of numbers, shapes or functions as a hierarchy; a decision "
                   "(which method to use) as a flowchart.",
    "economics": "Diagrams: how one change leads to the next (a rise in demand, prices, wages) as a flow whose "
                 "arrows say why; who pays whom (households, firms, the government, banks) as a cycle or flowchart "
                 "with lanes; kinds (of markets, taxes, sectors) as a hierarchy.",
    "geography": "Diagrams: a process (how a delta forms, how the monsoon arrives) as a numbered flow with a drawing "
                 "in each node; kinds (of soil, rock, forest, climate) as a hierarchy; what a crop or a region "
                 "depends on as a hub; causes and effects (deforestation -> erosion -> floods) as a chain.",
    "history": "Diagrams: causes and consequences as a chain whose arrows say why; who held power over whom as a "
               "pyramid or a hierarchy; how a system worked (land given for service, taxes paid upward) as a flow "
               "with arrows saying what passes; a movement and the groups in it as a hub.",
    "general": "A process, a sequence, causes and effects, parts of a whole or kinds of something is a diagram "
               "(flow, cycle, hub, hierarchy or pyramid), built across the paragraph.",
}
PROFILES["general"]["guidance"] += " " + _DIAGRAM_HINTS["general"]

# Free-form Manim draws every maths, science and moving drawing: the presets, sketches, graphs and sims there once
# were are gone (app/lib/lecture.ts FREE_DRAWN_OPS), so a subject's kit never offers them.
FREE_DRAWN = {"incline", "pulley", "piston", "spring", "pendulum", "projectile", "circuit", "lever", "lens",
              "sketch", "graph", "plot", "motion", "trace", "sweep", "sim", "counter"}
_THEORY = ("THEORY, THEN PROBLEMS: for each concept, first the theory, built on the board a piece at a time; then 2-3 "
           "long problems on it (problem op: the full question, given and find, its figure a manim drawing on the "
           "beats before it), each solved in detail over many beats (work op: one step a beat, every step "
           "explained, the answer boxed). Label everything. Build pictures in Manim (draw only what Manim cannot "
           "show well); no generated pictures except of a scientist the lecture names.")
FREE_GUIDANCE = {
    "physics": "Physics: draw every situation as a labelled free-form manim drawing (a block on a slope, pulleys, "
               "a circuit, a ray diagram, anything else), built over the beats that explain it, its forces, "
               "velocities and lengths revealed one by one as the narration names them; graphs of how quantities "
               "vary (v against t and the area under it, x against t, P against V) drawn in manim too, and set "
               "moving where the narration describes motion (an orbit, a wave, a collision, a point riding a "
               "graph). State each law as an equation. " + _THEORY,
    "chemistry": "Chemistry: show a molecule's structural formula (molecule: name, formula or SMILES) only where its "
                 "structure is what is being taught: its bonds, its shape, its functional groups, isomers, how it "
                 "reacts because of them; once, not again each time it is named, and never for a substance only "
                 "mentioned. Write reactions with equation (reactants -> products, subscripts as H_2O). Apparatus "
                 "(a beaker, a burette, a gas syringe), graphs of rates, concentrations and energy, and processes "
                 "that happen (a titration's colour change, particles of a gas, an equation being balanced) are "
                 "free-form manim drawings, built and set moving as they are said. " + _THEORY,
    "mathematics": "Mathematics: every function discussed is graphed, every figure of geometry drawn (triangles and "
                   "circles with their angles and lengths labelled), a construction done step by step with ruler and "
                   "compass, all as free-form manim drawings, and set moving where the idea moves (the unit circle "
                   "tracing a sine wave, rectangles closing in on an area, a graph shifted and stretched); derive "
                   "and solve with work, one step per beat, each step said and justified. Young classes: hops on a "
                   "number line, fraction bars, place-value blocks, drawn in manim. " + _THEORY,
    "biology": "Biology: pick the format from what the paragraph is. A STRUCTURE (a cell, a leaf, a flower, the "
               "heart, a neuron, a nephron): the book's figure or a detailed drawing (draw) with its parts labelled; "
               "when its parts are named one by one, a free-form manim drawing built part by part. A PROCESS "
               "(digestion, photosynthesis, blood flow, a reflex, protein synthesis): a flow diagram (\"steps\": "
               "true to number it) with a drawing in each node, a stage at a time; a CYCLE (cell cycle, life cycles, "
               "the cardiac cycle, the nitrogen cycle): diagram kind cycle. A HIERARCHY or CLASSIFICATION (cell, "
               "tissue, organ, system; kingdoms, phyla): a flow diagram whose edges go from each whole to its kinds. "
               "Two things side by side (mitosis and meiosis, plant and animal cells): compare. Something that MOVES "
               "(diffusion and osmosis, chromosomes separating, a heart beating, an impulse along a neuron) or a "
               "measurement graphed (growth, enzyme activity against temperature): free-form manim, set moving as "
               "it is said. Hard terms: define. Pictures only of organisms, habitats and scientists the lecture "
               "names. A molecule's structural formula only where the lecture explains its structure; a summary "
               "reaction with equation. No map unless the topic is where life lives.",
    "geography": "Geography: the map carries the where (markers, rivers, states shaded) and movement (a journey: the "
                 "monsoon winds, a trade route, a river's course); the stage carries how it works, as diagrams built "
                 "from drawings. The water cycle, the seasons and the Earth's or the soil's layers are free-form "
                 "manim drawings, set moving as they are said; real figures (rainfall by month, a population "
                 "pyramid) are drawn in manim from the content's numbers only. The document's figures, and compare "
                 "for differences. Pictures only of people, communities and places. " + _DIAGRAM_HINTS["geography"],
    "history": "History: open each era with a timeline on the stage (its dates, events and pictures of the people "
               "and places); a paragraph about several people or places is one scene picture with each labelled; "
               "journeys on the map as they happened (journey: the Dandi March, Vasco da Gama, the Silk Road); "
               "empires and kingdoms shaded on the map; differences between two systems or periods with compare; "
               "quote primary sources. " + _DIAGRAM_HINTS["history"],
    "economics": "Economics: quantities as bars, and trends, supply and demand moving, money growing and data stories "
                 "as free-form manim drawings, from real figures only; kinds side by side with compare; places on the "
                 "map only when trade or regions are the point. " + _DIAGRAM_HINTS["economics"],
}

for _genre in ("physics", "chemistry", "mathematics"):
    FREE_GUIDANCE[_genre] += " " + _DIAGRAM_HINTS[_genre]
for _genre, _text in FREE_GUIDANCE.items():
    PROFILES[_genre]["guidance"] = _text


def _as_told(genre: str) -> dict:
    """A subject's profile as the writer is told it."""
    return dict(PROFILES[genre])


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
    profile = _as_told(genre)
    return {"genre": genre, **profile, "scores": {k: round(v, 2) for k, v in ranked}, "confidence": confidence,
            "why": why}


def profile(genre: str) -> dict:
    """The profile of a subject chosen by hand (the page's Subject menu), in classify()'s shape."""
    genre = genre if genre in PROFILES else "general"
    return {"genre": genre, **_as_told(genre), "scores": {}, "confidence": 1.0, "why": ["chosen"]}


if __name__ == "__main__":
    # genre.py < text            the subject the text is about
    # genre.py --genre physics   a subject's profile
    if len(sys.argv) > 2 and sys.argv[1] == "--genre":
        print(json.dumps(profile(sys.argv[2]), indent=1))
    else:
        print(json.dumps(classify(sys.stdin.read()), indent=1))
