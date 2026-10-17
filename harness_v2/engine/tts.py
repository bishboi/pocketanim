"""Which voice narrates: Gemini 3.8 Flash-Lite TTS (gemini_tts.py), Google Chirp 3 HD (chirp.py) or ElevenLabs
(eleven_tts.py) when asked for.

PANIM_TTS=chirp keeps the older Chirp 3 HD voice, PANIM_TTS=eleven speaks with ElevenLabs (and times each word, so
the animations can be timed to the words); otherwise the voice is Gemini's. The modules have the same
shape: configured(), voice_for(style), speak(text, voice, speed) -> WAV bytes, NAME, REVISION.
"""

from __future__ import annotations

import chirp
import eleven_tts
import espeak_tts
import gemini_tts

chirp.NAME = "Google Chirp 3 HD"
ENGINES = {"gemini": gemini_tts, "chirp": chirp, "eleven": eleven_tts, "espeak": espeak_tts}   # espeak: v2's offline voice


def engine_name() -> str:
    chosen = (chirp._env("PANIM_TTS") or "").strip().lower()
    return chosen if chosen in ("chirp", "eleven", "espeak") else "gemini"


def engine(name: str | None = None):
    """The voice module: by name (a cached line's mode, "gemini:Charon"), else the configured one."""
    return ENGINES.get(name or engine_name(), gemini_tts)


def setup_hint() -> str:
    if engine_name() == "espeak":
        return "Narration is spoken offline by espeak-ng (PANIM_TTS=espeak), and it is not installed: apt install espeak-ng."
    if engine_name() == "eleven":
        return ("Narration is spoken by ElevenLabs (PANIM_TTS=eleven), and no ElevenLabs API key is set: put "
                "ELEVENLABS_API_KEY=<key> in harness/app/.env.local and restart the app.")
    if engine_name() == "chirp":
        return ("Narration is spoken by Google Chirp 3 HD (PANIM_TTS=chirp), and no Google credentials are set: "
                "sign in with `gcloud auth application-default login`, or set GOOGLE_APPLICATION_CREDENTIALS or "
                "GOOGLE_TTS_API_KEY (harness/SETUP.md).")
    return ("Narration is spoken by Gemini 3.8 Flash-Lite TTS, and no Gemini API key is set: put GEMINI_API_KEY=<key "
            "from aistudio.google.com/apikey> in harness/app/.env.local and restart the app (harness/SETUP.md).")
