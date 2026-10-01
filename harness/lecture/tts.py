"""Which voice narrates: Gemini 3.8 Flash-Lite TTS (gemini_tts.py), or Google Chirp 3 HD (chirp.py) when asked for.

PANIM_TTS=chirp keeps the older Chirp 3 HD voice; otherwise the voice is Gemini's. Both modules have the same
shape: configured(), voice_for(style), speak(text, voice, speed) -> WAV bytes, NAME, REVISION.
"""

from __future__ import annotations

import chirp
import gemini_tts

chirp.NAME = "Google Chirp 3 HD"
ENGINES = {"gemini": gemini_tts, "chirp": chirp}


def engine_name() -> str:
    return "chirp" if (chirp._env("PANIM_TTS") or "").strip().lower() == "chirp" else "gemini"


def engine(name: str | None = None):
    """The voice module: by name (a cached line's mode, "gemini:Charon"), else the configured one."""
    return ENGINES.get(name or engine_name(), gemini_tts)


def setup_hint() -> str:
    if engine_name() == "chirp":
        return ("Narration is spoken by Google Chirp 3 HD (PANIM_TTS=chirp), and no Google credentials are set: "
                "sign in with `gcloud auth application-default login`, or set GOOGLE_APPLICATION_CREDENTIALS or "
                "GOOGLE_TTS_API_KEY (harness/SETUP.md).")
    return ("Narration is spoken by Gemini 3.8 Flash-Lite TTS, and no Gemini API key is set: put GEMINI_API_KEY=<key "
            "from aistudio.google.com/apikey> in harness/app/.env.local and restart the app (harness/SETUP.md).")
