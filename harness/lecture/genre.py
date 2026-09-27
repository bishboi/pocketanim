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
        "kit": ["marker", "river", "state", "icon", "photo", "illustration", "figure", "bars"],
        "guidance": "Geography: the map carries the where (markers, rivers, states, icons at towns); the stage carries "
                    "what it looks like (photos of landscapes and crops, illustrations). Alternate them.",
    },
    "history": {
        "label": "History", "style": "parchment", "map": "sometimes",
        "kit": ["timeline", "quote", "photo", "figure", "process", "marker", "arrow", "illustration"],
        "guidance": "History: open each era with a timeline on the stage; show people and places as photos (portraits, "
                    "monuments, paintings from Commons); quote primary sources with quote; show causes and "
                    "consequences as a process; use the map only for where events happened, routes and empires.",
    },
    "biology": {
        "label": "Biology", "style": "lab", "map": "rarely",
        "kit": ["figure", "photo", "process", "illustration", "molecule", "equation", "bars"],
        "guidance": "Biology: show structures (document figures, photos of organisms and microscope images), processes "
                    "and cycles as process (cycle=true for cycles), key molecules (glucose, ATP parts, DNA bases) with "
                    "molecule, and summary reactions with equation. No map unless the topic is where life lives.",
    },
    "chemistry": {
        "label": "Chemistry", "style": "lab", "map": "never",
        "kit": ["molecule", "equation", "process", "figure", "photo", "illustration", "bars"],
        "guidance": "Chemistry: draw every substance you discuss with molecule (name, formula or SMILES), write "
                    "reactions with equation (reactants -> products, subscripts as H_2O), show procedures as process, "
                    "and use photos of real reactions and apparatus. No map.",
    },
    "physics": {
        "label": "Physics", "style": "cosmos", "map": "never",
        "kit": ["equation", "plot", "process", "figure", "photo", "illustration"],
        "guidance": "Physics: state each law as an equation, show how quantities vary with plot (a function of x, with "
                    "axis labels), show chains of cause and effect as process, and use photos of the phenomenon. No map.",
    },
    "mathematics": {
        "label": "Mathematics", "style": "chalkboard", "map": "never",
        "kit": ["equation", "plot", "process", "figure", "illustration"],
        "guidance": "Mathematics: one equation per beat on the stage, built up step by step (each step its own beat), "
                    "graphs with plot, methods as process (the steps of a proof or an algorithm). No map, few photos.",
    },
    "economics": {
        "label": "Economics", "style": "atlas", "map": "sometimes",
        "kit": ["bars", "plot", "process", "photo", "illustration", "stat", "marker"],
        "guidance": "Economics: show quantities as bars and trends as plot, mechanisms (supply and demand, how inflation "
                    "spreads) as process, and places on the map only when trade or regions are the point.",
    },
    "general": {
        "label": "General", "style": "vox", "map": "sometimes",
        "kit": ["photo", "illustration", "process", "figure", "timeline", "quote", "equation", "bars"],
        "guidance": "Choose the picture that explains each beat: photos, illustrations, processes, timelines; the map "
                    "only for where.",
    },
}
WORDS = {genre: set(v.split()) | set(VOCAB_HI.get(genre, "").split()) for genre, v in VOCAB.items()}
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
        scores["history"] += min(years, 12) * 0.8
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


if __name__ == "__main__":
    print(json.dumps(classify(sys.stdin.read()), indent=1))
