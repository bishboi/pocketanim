"""The voice director: how each line of a lecture is said, marked up for an expressive voice (ElevenLabs v4, or
Gemini TTS).

Before the lines are spoken (scripts/prespeak.py), a chat model reads them in order, a chapter's worth at a time,
and marks each for delivery. For ElevenLabs as its own "Enhance" does: audio tags in brackets ("[curious]",
"[thoughtful]", "[short pause]"), a capitalised key word, an ellipsis before a reveal. For Gemini, its vocal
events in angle brackets ("<chuckle>", "<sigh>", "<breath>"), a teacher's few (GEMINI_TAGS). It may not change a word:
a marked line whose words differ from the line's is thrown away and the line is said as written. The marked
line is kept beside the line's audio (pocket_lecture.delivery_file) and is what the voice is given; the caption
and every cache key stay the plain line.

PANIM_VOICE_DIRECTOR=off turns it off; PANIM_VOICE_DIRECTOR_MODEL picks the model (else OPENROUTER_MODEL).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import llm
from chirp import _env

CHUNK = 40              # lines a request
PARALLEL = 4
MAX_TAGS = 2            # a line's tags at most
# Delivery a teacher would use. Anything that is a sound effect, a character voice or a song is not delivery.
BANNED = re.compile(r"gunshot|applause|clapping|explosion|fart|sing|accent|shout|scream|whisper|cry|crying|"
                    r"laugh|giggl|snort|wheez|swallow|gulp|music|woo|robotic|beep", re.I)

SYSTEM = """You direct the voice of a teacher narrating a video lecture, read by ElevenLabs Eleven v4, an \
expressive text-to-speech model that follows audio tags. You are given the lecture's lines in order. Mark each \
line so it is said the way a warm, clear, engaged teacher would say it to students meeting the idea for the \
first time.

You may ONLY:
- add an audio tag in square brackets before (or, rarely, after) a part of the line, describing the voice's \
delivery: [warm], [curious], [thoughtful], [gently], [reassuring], [encouraging], [intrigued], [serious], \
[amazed], [emphatic], [matter-of-fact], [short pause], [inhales], [exhales] and similar \
delivery directions. At most 2 tags in a line; many lines need none. Vary them over the lecture; never the same \
tag on every line.
- write ONE key word of a line in CAPITALS for emphasis, only where a new idea or the answer is named, and only \
in a few lines;
- add an ellipsis (...) where a teacher would pause before a reveal or an answer, or change a full stop to a \
question mark or exclamation mark where the sentence really is one.

You must NOT add, remove, reorder or change any word, number or letter of the line. No sound effects, no \
laughing, no whispering or shouting, no accents, no singing. Lines in Hindi or Hinglish keep their words; tags \
are written in English.

Reply with JSON only: {"lines": [{"n": <the line's number>, "say": "<the marked line>"}]}, one entry for every \
line you were given."""


# Gemini TTS's vocal events a teacher uses (a breath, a sigh of relief, a quiet laugh, a gasp at a surprise, a
# whispered aside); none that is a pause (the voice keeps its pace) or that no teacher would make in class.
GEMINI_TAGS = ("breath", "exhales", "sigh", "sighs", "chuckle", "chuckles", "laugh", "gasp", "phew", "tsk",
               "throat-clearing", "cheer", "whispers")

GEMINI_SYSTEM = """You direct the voice of a teacher narrating a video lecture, read by Gemini TTS, an \
expressive text-to-speech model that makes a vocal sound where it finds a tag in angle brackets. You are given the \
lecture's lines in order. Mark them so the lecture sounds like a warm, lively, engaged teacher talking to students, \
not a voice reading text.

You may ONLY:
- add one of these tags, in angle brackets, where that sound would come naturally from the teacher: \
""" + ", ".join(f"<{t}>" for t in GEMINI_TAGS) + """. For example a <breath> before starting a new idea, a \
<chuckle> at something funny or surprising, a <gasp> or "Wow" moment before an astonishing fact, a <sigh> at \
something sad, a <phew> after a hard part, <whispers> before a secret-like aside. At most 2 tags in a line; about \
one line in three has one; vary them over the lecture, never the same tag twice in a row.
- add an ellipsis (...) where a teacher would pause before a reveal, or change a full stop to a question mark or \
exclamation mark where the sentence really is one.

You must NOT add, remove, reorder or change any word, number or letter of the line, and no other tags (no pauses: \
the voice keeps its pace). Lines in Hindi or Hinglish keep their words; tags are written in English.

Reply with JSON only: {"lines": [{"n": <the line's number>, "say": "<the marked line>"}]}, one entry for every \
line you were given."""


def plain_words(text: str) -> list[str]:
    """A line's words for comparing: tags and IPA out, case, ellipses and punctuation ignored."""
    text = re.sub(r"\[[^\]]*\]|<[^>]*>", " ", text)
    return re.findall(r"\w+", text.replace("…", " ").lower())


def acceptable(line: str, marked: str, engine: str = "eleven") -> bool:
    """Whether a marked line says exactly the line's words, with a few delivery tags of a teacher's kind."""
    if not isinstance(marked, str) or not marked.strip() or plain_words(marked) != plain_words(line):
        return False
    if engine == "gemini":
        tags = re.findall(r"<([^>]*)>", marked)
        return "[" not in marked and len(tags) <= MAX_TAGS and all(t.strip().lower() in GEMINI_TAGS for t in tags)
    if "<" in marked:
        return False
    tags = re.findall(r"\[([^\]]*)\]", marked)
    if len(tags) > MAX_TAGS or any(len(t) > 40 or BANNED.search(t) for t in tags):
        return False
    return sum(1 for w in re.findall(r"\b[A-Z]{3,}\b", marked) if w not in re.findall(r"\b[A-Z]{3,}\b", line)) <= 1


def mark(lines: list[str], engine: str = "eleven") -> tuple[dict[str, str], float]:
    """{line: marked line} for the lines a model marked acceptably for this voice (`engine`), and what the requests
    cost."""
    system = GEMINI_SYSTEM if engine == "gemini" else SYSTEM
    if not lines or not llm.configured():
        return {}, 0.0
    model = llm.model("PANIM_VOICE_DIRECTOR_MODEL")
    chunks = [lines[i:i + CHUNK] for i in range(0, len(lines), CHUNK)]

    def ask(chunk: list[str]) -> tuple[dict[str, str], float]:
        user = "\n".join(f"{n}. {line}" for n, line in enumerate(chunk, 1))
        try:
            reply, usd = llm.chat_json(model, system, user)
        except RuntimeError:
            return {}, 0.0
        out: dict[str, str] = {}
        for item in reply.get("lines") or []:
            try:
                n = int(item.get("n"))
            except (TypeError, ValueError, AttributeError):
                continue
            if 1 <= n <= len(chunk):
                said = str(item.get("say") or "").strip()
                if said != chunk[n - 1] and acceptable(chunk[n - 1], said, engine):
                    out[chunk[n - 1]] = said
        return out, usd

    marked: dict[str, str] = {}
    spent = 0.0
    with ThreadPoolExecutor(max_workers=min(PARALLEL, len(chunks))) as pool:
        for found, usd in pool.map(ask, chunks):
            marked.update(found)
            spent += usd
    return marked, spent


def enabled(engine: str) -> bool:
    return engine in ("eleven", "gemini") and (_env("PANIM_VOICE_DIRECTOR") or "on").strip().lower() not in ("off", "0", "no")
