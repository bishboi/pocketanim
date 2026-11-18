"""The languages a video can be made in: English, Hinglish, and the Indian languages Gemini TTS
(gemini-3.8-flash-lite-tts) speaks. For each: its name, the script it is written in, how the voice should sound, and
the fonts its letters are set in on the screen (setup.sh fetches them; look.for_script picks one by the letters).

    code: (name, name in its own script, script, how it is written)

Everything else reads this table: the script writer (prompts.SCRIPT_LANG), the storyboard and score calls
(prompts.LANG), the voice (tts_gemini.STYLES, voice.py's word timing), the UI's language lists (runs.LANGUAGES).
"""

from __future__ import annotations

import re

# script -> (headline face, body face, the letters' Unicode range)
SCRIPTS = {
    "Latin": (None, None, r"[A-Za-z]"),
    "Devanagari": ("Teko", "Hind", "ऀ-ॿ꣠-ꣿ"),
    "Bengali": ("Noto Sans Bengali", "Noto Sans Bengali", "ঀ-৿"),
    "Gurmukhi": ("Noto Sans Gurmukhi", "Noto Sans Gurmukhi", "਀-੿"),
    "Gujarati": ("Noto Sans Gujarati", "Noto Sans Gujarati", "઀-૿"),
    "Odia": ("Noto Sans Oriya", "Noto Sans Oriya", "଀-୿"),
    "Tamil": ("Noto Sans Tamil", "Noto Sans Tamil", "஀-௿"),
    "Telugu": ("Noto Sans Telugu", "Noto Sans Telugu", "ఀ-౿"),
    "Kannada": ("Noto Sans Kannada", "Noto Sans Kannada", "ಀ-೿"),
    "Malayalam": ("Noto Sans Malayalam", "Noto Sans Malayalam", "ഀ-ൿ"),
    "Meetei Mayek": ("Noto Sans Meetei Mayek", "Noto Sans Meetei Mayek", "ꯀ-꯿ꫠ-꫿"),
    "Ol Chiki": ("Noto Sans Ol Chiki", "Noto Sans Ol Chiki", "᱐-᱿"),
    "Perso-Arabic": ("Noto Naskh Arabic", "Noto Naskh Arabic", "؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿"),
}

LANGS = {
    "en": ("English", "English", "Latin", "plain, clear English"),
    "hinglish": ("Hinglish", "Hinglish", "Latin", "everyday Hindi in Roman letters with English words mixed in"),
    "hi": ("Hindi", "हिन्दी", "Devanagari", "standard spoken Hindi (हिन्दी) in Devanagari"),
    "bn": ("Bengali (Bangla)", "বাংলা", "Bengali", "standard spoken Bengali (বাংলা) in the Bengali script"),
    "gu": ("Gujarati", "ગુજરાતી", "Gujarati", "spoken Gujarati (ગુજરાતી) in the Gujarati script"),
    "mr": ("Marathi", "मराठी", "Devanagari", "standard spoken Marathi (मराठी) in Devanagari"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi", "spoken Punjabi (ਪੰਜਾਬੀ) in the Gurmukhi script"),
    "ta": ("Tamil", "தமிழ்", "Tamil", "clear spoken Tamil (தமிழ்) in the Tamil script, not overly literary"),
    "te": ("Telugu", "తెలుగు", "Telugu", "spoken Telugu (తెలుగు) in the Telugu script"),
    "kn": ("Kannada", "ಕನ್ನಡ", "Kannada", "spoken Kannada (ಕನ್ನಡ) in the Kannada script"),
    "ml": ("Malayalam", "മലയാളം", "Malayalam", "spoken Malayalam (മലയാളം) in the Malayalam script"),
    "or": ("Odia", "ଓଡ଼ିଆ", "Odia", "spoken Odia (ଓଡ଼ିଆ) in the Odia script"),
    "as": ("Assamese", "অসমীয়া", "Bengali", "spoken Assamese (অসমীয়া) in the Assamese (Bengali-Assamese) script, "
           "with Assamese letters such as ৰ and ৱ"),
    "bho": ("Bhojpuri", "भोजपुरी", "Devanagari", "everyday Bhojpuri (भोजपुरी) in Devanagari, as it is spoken, not Hindi"),
    "awa": ("Awadhi", "अवधी", "Devanagari", "everyday Awadhi (अवधी) in Devanagari, as it is spoken, not Hindi"),
    "hne": ("Chhattisgarhi", "छत्तीसगढ़ी", "Devanagari", "everyday Chhattisgarhi (छत्तीसगढ़ी) in Devanagari, as it is spoken, "
            "not Hindi"),
    "mai": ("Maithili", "मैथिली", "Devanagari", "Maithili (मैथिली) in Devanagari, as it is spoken, not Hindi"),
    "mag": ("Magahi", "मगही", "Devanagari", "everyday Magahi (मगही) in Devanagari, as it is spoken, not Hindi"),
    "ne": ("Nepali", "नेपाली", "Devanagari", "standard Nepali (नेपाली) in Devanagari"),
    "ks": ("Kashmiri", "کٲشُر", "Perso-Arabic", "Kashmiri (کٲشُر) in its Perso-Arabic script, right to left"),
    "mni": ("Manipuri (Meitei)", "ꯃꯩꯇꯩꯂꯣꯟ", "Meetei Mayek", "Manipuri (Meiteilon, ꯃꯩꯇꯩꯂꯣꯟ) in the Meetei Mayek script"),
    "sat": ("Santali", "ᱥᱟᱱᱛᱟᱲᱤ", "Ol Chiki", "Santali (ᱥᱟᱱᱛᱟᱲᱤ) in the Ol Chiki script"),
    "lus": ("Mizo", "Mizo ṭawng", "Latin", "Mizo (Mizo ṭawng) in its Roman alphabet, with ṭ"),
}

# For the UI: "Tamil · தமிழ்"
NAMES = {k: (v[0] if v[1] in (v[0], "English", "Hinglish") or k == "en" else f"{v[0]} · {v[1]}") for k, v in LANGS.items()}
INDIAN = [k for k in LANGS if k not in ("en", "hinglish")]


def name(code: str) -> str:
    return LANGS.get(code or "en", LANGS["en"])[0]


def script_of(code: str) -> str:
    return LANGS.get(code or "en", LANGS["en"])[2]


def native(code: str) -> bool:
    """Written in its own script (not English, not Hinglish)."""
    return (code or "en") not in ("en", "hinglish")


def face(words: str, font: str, headline: bool = True) -> str:
    """The face words are set in: the one with their letters (the kit's faces have Latin only)."""
    s = str(words)
    for script, (head, body, rng) in SCRIPTS.items():
        if script != "Latin" and re.search(f"[{rng}]", s):
            return (head if headline else body) or font
    return font


def tts_style(code: str) -> str:
    n, _, _, how = LANGS.get(code or "en", LANGS["en"])
    return (f"a warm, clear documentary narrator speaking natural {n}, unhurried, every word pronounced as a native "
            f"{n} speaker says it ({how}); names and English terms said naturally")


def script_rules(code: str) -> str:
    """How the script writer writes in this language."""
    if not native(code):
        return ""
    n, own, script, how = LANGS[code]
    return f"""
WRITE IN {n.upper()} ({own}): {how}. Write as a good teacher speaks it to students today, warm and simple, the way a
popular explainer in {n} talks: short spoken sentences, common everyday words over rare literary ones, an English
term kept (in the {script} script, as people say it) where that is what people use. Numbers as digits. Names of
people and places as they are said in {n}. Every spoken line is in {n}, in the {script} script, never in Roman letters.
TITLES (the video's, the chapters') are in {n} too: they are written on the screen."""


def score_rules(code: str) -> str:
    """How the storyboard and score calls treat a narration in this language."""
    if not native(code):
        return ""
    n, own, script, _ = LANGS[code]
    return f"""
THE NARRATION IS IN {n.upper()} ({own}, {script} script). Words WRITTEN ON THE SCREEN (tags, labels, cards, titles,
notes, bubbles, callouts, stamps, chart labels) are in {n}, in the {script} script, short (1-3 words); a `phrase`
shows the narration's own words. Keep numbers as digits. The plans, the names of things (ent names), and the words a
picture is made from (pic, photo, backdrop, img) are in English. Map place names stay as the map draws them."""
