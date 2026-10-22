"""How well a compiled scene's animations land on their words: the scene run (no frames drawn), and for every word a
line says that something on the screen shows (a label, a node, an event, a term), when that thing came on against
when the word was said.

    .venv/bin/python harness_v2/engine/tools/sync_probe.py scene.py [--fake-voice] [--json]

The voice is the one the scene is spoken in (PANIM_TTS, PANIM_VOICE, PANIM_AUDIO_DIR, as for prespeak.py), with
its word times (pocket_lecture.line_words). --fake-voice speaks every line first in a stand-in voice whose words'
times are known exactly (each word a tone, a short gap between words, a longer one at a comma), into a folder of
its own: the check and a developer can then measure the engine's timing alone, without a voice or an aligner.

For each line: its words with their times, each play with its start (seconds into the line) and the words it put
on the screen, and each word matched to the first play that showed it: "lag" is how long after the word the play
began (negative: before it). A thing should begin a little before its word (SYNC_LEAD) and never long after it.
Each animation timed to words (the scene writer's "on" anchor, a part's name, a card's own words) is measured too:
when it began against when its words were said ("anchors").

The last line of stdout is a JSON summary: {"lines", "matched", "on_time", "early", "late", "mean_abs_lag",
"worst": [...], "anchors": {"count", "on_time", "early", "late", "worst"}, "readable": {"count", "on_time", "late",
"unreachable", "worst"}} (on time: from 0.6 s before the word to 0.35 s after it). "readable" measures each anchored
animation by when its key words can be read (MotionLecture._readable_share: what brings them on 60% of the way
through), not when it began: no later than 0.35 s after the word; "unreachable" when the word is said sooner into
its line than the picture takes to read.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import wave
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

EARLY, LATE = -0.6, 0.35       # on time: the play begins this long before its word, at most, to this long after it
READ_LATE = 0.35                # read on time: its key words readable no later than this after their word
RATE = 16000


def _norm(word: str) -> str:
    import unicodedata

    word = unicodedata.normalize("NFC", str(word)).lower().replace("\u0964", "").replace("\u0965", "")
    return re.sub(r"[^\w\u0900-\u0DFF]+", "", word)          # the danda (।, ॥) is a full stop, not a letter


# ---------------- a stand-in voice whose words' times are known ----------------

def fake_voice(source: str) -> str:
    """Every line of the scene spoken in the stand-in voice ("eleven:probe", into a folder of its own): a tone a
    word, about 2.6 words a second, a longer gap at a comma or a stop; each line's words' times written beside it
    as a voice that times its words does. Returns the folder."""
    import numpy as np

    from prespeak import beat_lines

    folder = Path(tempfile.mkdtemp(prefix="sync-probe-voice-"))
    os.environ.update({"PANIM_TTS": "eleven", "PANIM_VOICE": "eleven:probe", "ELEVENLABS_API_KEY": "probe",
                       "PANIM_AUDIO_DIR": str(folder), "PANIM_VOICE_DIRECTOR": "off"})
    import pocket_lecture as pl

    mode = pl.voice_mode()
    for line in dict.fromkeys(beat_lines(source)):
        spoken = pl.speechify(line)
        words, pcm, at = [], [], 0.0
        for raw in spoken.split():
            word = raw.strip("\"'“”‘’.,;:!?…—–-()[]")
            length = 0.12 + 0.055 * len(word or raw)
            n = int(length * RATE)
            pcm.append((np.sin(np.arange(n) * 0.09) * 9000).astype(np.int16))
            if word:
                words.append({"w": word, "start": round(at, 3), "end": round(at + length, 3)})
            at += length
            gap = 0.32 if re.search(r"[,;:.!?।]$", raw) else 0.07
            pcm.append(np.zeros(int(gap * RATE), np.int16))
            at += gap
        audio = np.concatenate(pcm[:-1]) if len(pcm) > 1 else pcm[0]
        out = pl.audio_file(mode, spoken)
        with wave.open(str(out), "w") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes(audio.tobytes())
        pl.words_file(out).write_text(json.dumps(words))
    return str(folder)


# ---------------- the scene, run and watched ----------------

def _words_of(x) -> str | None:
    return next((x.__dict__.get(k) for k in ("text", "original_text", "tex_string")
                 if isinstance(x.__dict__.get(k), str) and x.__dict__.get(k).strip()), None)


def _text_pieces(mobs) -> list:
    """The pieces of text among these mobjects and inside them."""
    out, seen = [], set()
    for top in mobs:
        for x in top.get_family():
            if id(x) not in seen and _words_of(x) is not None:
                seen.add(id(x))
                out.append(x)
    return out


def _anim_mobjects(anims) -> list:
    out, todo = [], list(anims)
    while todo:
        a = todo.pop()
        todo.extend(getattr(a, "animations", None) or [])
        for key in ("mobject", "target_mobject"):
            m = getattr(a, key, None)
            if m is not None:
                out.append(m)
    return out


MADE: list = []           # every piece of text made while the scene runs (_register)


def _register() -> None:
    """Every Text, MarkupText and Tex made from now on kept in MADE: a piece typed in a letter at a time has only its
    letters on the screen, and nothing on the screen leads back to the piece and its words."""
    import weakref

    from manim import MarkupText, SingleStringMathTex, Text

    for cls in (Text, MarkupText, SingleStringMathTex):
        if getattr(cls, "_probe_registered", False):
            continue
        real = cls.__init__

        def init(self, *a, _real=real, **k):
            _real(self, *a, **k)
            MADE.append(weakref.ref(self))

        cls.__init__ = init
        cls._probe_registered = True


def _visible_texts(scene, extra=()) -> dict:
    """{id: words} of every piece of text on the screen now and not see-through (the caption left out). A piece is
    on the screen when any of its letters is: text typed in a letter at a time is put on the screen letter by
    letter, without the piece that holds its words."""
    cap = getattr(scene, "cap", None)
    skip = {id(x) for x in cap.get_family()} if cap is not None else set()
    on = {id(x) for top in scene.mobjects for x in top.get_family()}
    out = {}
    pieces = {id(x): x for x in _text_pieces([*scene.mobjects, *extra])}
    for ref in MADE:
        x = ref()
        if x is not None and _words_of(x) is not None:
            pieces.setdefault(id(x), x)
    for x in pieces.values():
        if id(x) in skip:
            continue
        for g in x.family_members_with_points() or [x]:
            if id(g) not in on:
                continue
            try:
                seen = max(float(g.get_fill_opacity()), float(g.get_stroke_opacity()))
            except Exception:  # noqa: BLE001 -- not a vector shape: counted as seen
                seen = 1.0
            if seen > 0.05:
                out[id(x)] = _words_of(x)
                break
    return out


CARDS = ("chapter", "title_slide", "recap", "outro_fade")


def run(scene_file: Path) -> list[dict]:
    """The scene run without drawing: [{"text", "voice" (its start, on the render's clock), "seconds", "words",
    "plays": [{"at", "run", "kinds", "texts"}]}] a line, in order. A play's "texts" are the words that came on the
    screen with it (put up by it, or put up as it began: a picture added outright), never those already up."""
    import importlib.util

    from manim import Scene, tempconfig

    import pocket_lecture as pl

    lines: list[dict] = []
    state = {"line": None, "shown": {}}
    real_play, real_beat, real_sound = Scene.play, pl.MapLecture.beat, Scene.add_sound
    real_on_words = pl.MapLecture._on_words
    pending: dict = {}                    # id(animation) -> its anchor: the words it lands on and when they are said

    def on_words(self, given, words, seconds, text):
        out = real_on_words(self, given, words, seconds, text)
        line = state["line"]
        for anim, _ in out:
            said = getattr(anim, "panim_said", None)
            at = self._said(words, said) if (said and words) else None
            if line is not None and at is not None and id(anim) not in pending:
                pending[id(anim)] = {"line": line, "word": str(said), "said": round(float(at), 3), "anim": anim}
        return out

    def beat(self, text, *anims, **kw):
        import inspect

        # A chapter's card or the title slide speaks through beat too: its card is up as it begins, by design.
        card = any(f.function in CARDS for f in inspect.stack()[1:4])
        state["line"] = {"text": text, "voice": None, "seconds": None, "words": None, "plays": [], "card": card}
        lines.append(state["line"])
        return real_beat(self, text, *anims, **kw)

    def add_sound(self, path, *a, **kw):
        line = state["line"]
        if line is not None and line["voice"] is None:
            line["voice"] = float(self.renderer.time)
        return real_sound(self, path, *a, **kw)

    def play(self, *anims, **kw):
        line = state["line"]
        at = float(self.renderer.time)
        mobs = _anim_mobjects(anims)
        before = _visible_texts(self, mobs)
        added = [w for k, w in before.items() if k not in state["shown"]]
        todo = list(anims)
        while todo:
            a = todo.pop()
            todo.extend(getattr(a, "animations", None) or [])
            hit = pending.pop(id(a), None)
            # A new picture set late in its line comes on as the line begins (MotionLecture._on_words): not an anchor.
            if hit is not None and hit["line"]["voice"] is not None and not getattr(a, "panim_line_start", False):
                begun = round(at - hit["line"]["voice"], 3)
                row = {"word": hit["word"], "said": hit["said"], "play": begun}
                # When it can be read (its key words in: MotionLecture._readable_share), not only when it began.
                share = self._readable_share(a) if hasattr(self, "_readable_share") else None
                if share is not None:
                    top = any(a is x for x in anims)
                    run = float((kw.get("run_time") if top else None) or getattr(a, "run_time", 0.0) or 0.0)
                    row["reads"] = round(begun + share * run, 3)
                    row["need"] = round(share * run, 3)
                hit["line"].setdefault("anchors", []).append(row)
        result = real_play(self, *anims, **kw)
        after = _visible_texts(self, mobs)
        came = added + [w for k, w in after.items() if k not in before]
        state["shown"] = after
        if line is not None:
            line["plays"].append({"at": at, "run": float(self.renderer.time) - at,
                                  "kinds": [type(a).__name__ for a in anims][:6], "texts": came})
        return result

    Scene.play, Scene.add_sound = play, add_sound
    pl.MapLecture.beat, pl.MapLecture._on_words = beat, on_words
    _register()
    try:
        spec = importlib.util.spec_from_file_location("probed_scene", scene_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = next(v for k, v in vars(module).items() if isinstance(v, type) and issubclass(v, Scene)
                   and v.__module__ == "probed_scene" and "construct" in vars(v))
        with tempconfig({"dry_run": True, "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none"}):
            cls().render()
    finally:
        Scene.play, Scene.add_sound, pl.MapLecture.beat = real_play, real_sound, real_beat
        pl.MapLecture._on_words = real_on_words
    for line in lines:
        line["words"] = pl.line_words(line["text"]) or []
        wav = pl.audio_file(pl.voice_mode(), pl.speechify(line["text"]))
        line["seconds"] = pl._tight(wav)[2] if pl._cached_seconds(wav) else None
    return lines


# ---------------- how well they land ----------------

def measure(lines: list[dict]) -> dict:
    rows, lags = [], []
    for k, line in enumerate(lines):
        if line["voice"] is None or line.get("card"):
            continue
        end = next((x["voice"] for x in lines[k + 1:] if x["voice"] is not None), float("inf"))
        plays = [p for p in line["plays"] if p["at"] < end - 1e-6]
        # A play just before the voice begins (a template's entrance, a transition) belongs to this line too.
        before = []
        if k and lines[k - 1]["voice"] is not None:
            said_until = lines[k - 1]["voice"] + float(lines[k - 1]["seconds"] or 0)
            before = [p for p in lines[k - 1]["plays"] if p["at"] >= max(said_until, line["voice"] - 1.5)]
        shown = []
        for p in before + plays:
            # Manim's text keeps no spaces: a word is found inside the words shown, not among them.
            shown.append((p["at"] - line["voice"], "|" + "|".join(_norm(t) for t in p["texts"]) + "|", p))
        matched = []
        for w in line["words"]:
            word = _norm(w["w"])
            if len(word) < 3 or word in STOP:
                continue
            first = next(((at, p) for at, joined, p in shown if word in joined), None)
            if first is None:
                continue
            lag = round(first[0] - float(w["start"]), 3)
            matched.append({"word": w["w"], "said": w["start"], "play": round(first[0], 3), "lag": lag,
                            "what": " / ".join(first[1]["texts"])[:80]})
        # A thing shown once and named again later is matched on its first naming only.
        seen, kept = set(), []
        for m in matched:
            key = (m["play"], m["what"])
            if key in seen:
                continue
            seen.add(key)
            kept.append(m)
        lags += [m["lag"] for m in kept]
        rows.append({"line": line["text"], "seconds": line["seconds"], "voice": round(line["voice"], 3),
                     "words": [f"{float(w['start']):.2f}:{w['w']}" for w in line["words"]],
                     "plays": [f"{p['at'] - line['voice']:+.2f}s ({p['run']:.2f}s) {'+'.join(p['kinds'][:2])} "
                               f"{' / '.join(p['texts'])[:70]}" for p in plays],
                     "matched": kept})
    # The anchors: each animation timed to words (the writer's "on", a part's name, a picture's own words), when it
    # began against when its words were said.
    # Began on time: as long before its word as it takes to read (`need`, so its words read on the word), or as the
    # line began when that is sooner than the line's start; without a measure of that, against the word itself.
    anchored = [{**a, "lag": round(a["play"] - (max(0.0, a["said"] - a["need"]) if "need" in a else a["said"]), 3),
                 "line": line["text"][:60]}
                for line in lines if not line.get("card") for a in line.get("anchors") or []]
    for row in rows:
        row["anchors"] = next((x.get("anchors") or [] for x in lines if x["text"] == row["line"]), [])
    # Read: when each anchored picture's words can be read against its word. One that cannot be read in time even
    # begun as its line begins (its words said sooner than it takes to read) is counted apart ("unreachable").
    readable = [{**a, "read_lag": round(a["reads"] - a["said"], 3)} for a in anchored if "reads" in a]
    r_late = [a for a in readable if a["read_lag"] > READ_LATE and a["said"] >= a["need"]]
    r_cannot = [a for a in readable if a["read_lag"] > READ_LATE and a["said"] < a["need"]]
    a_late = [a for a in anchored if a["lag"] > LATE]
    a_early = [a for a in anchored if a["lag"] < EARLY]
    early = [m for r in rows for m in r["matched"] if m["lag"] < EARLY]
    late = [m for r in rows for m in r["matched"] if m["lag"] > LATE]
    worst = sorted((m for r in rows for m in r["matched"]), key=lambda m: -abs(m["lag"]))[:8]
    return {"rows": rows, "summary": {"lines": len(rows), "matched": len(lags),
                                      "on_time": len(lags) - len(early) - len(late), "early": len(early),
                                      "late": len(late),
                                      "mean_abs_lag": round(sum(abs(x) for x in lags) / len(lags), 3) if lags else None,
                                      "worst": worst,
                                      "anchors": {"count": len(anchored),
                                                  "on_time": len(anchored) - len(a_late) - len(a_early),
                                                  "early": len(a_early), "late": len(a_late),
                                                  "worst": sorted(anchored, key=lambda a: -abs(a["lag"]))[:6]},
                                      "readable": {"count": len(readable), "late": len(r_late),
                                                   "unreachable": len(r_cannot),
                                                   "on_time": len(readable) - len(r_late) - len(r_cannot),
                                                   "worst": sorted(readable, key=lambda a: -a["read_lag"])[:6]}}}


STOP = {"the", "and", "for", "with", "that", "this", "are", "was", "from", "its", "his", "her", "their", "into",
        "one", "two", "has", "have", "had", "but", "not", "you", "our", "all", "more", "than", "what", "who"}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    scene = Path(args[0])
    source = scene.read_text(encoding="utf-8")
    style = re.search(r"""os\.environ\.setdefault\(\s*["']LECTURE_STYLE["']\s*,\s*["'](\w+)["']""", source)
    if style:
        os.environ.setdefault("LECTURE_STYLE", style.group(1))
    if "--fake-voice" in sys.argv:
        fake_voice(source)
    result = measure(run(scene))
    if "--json" not in sys.argv:
        for row in result["rows"]:
            print(f"\n[{row['voice']:.2f}s] {row['line']}  ({row['seconds'] or 0:.2f} s)")
            print("   words:", " ".join(row["words"]))
            for p in row["plays"]:
                print("   play ", p)
            for a in row.get("anchors") or []:
                lag = a["play"] - a["said"]
                flag = "ok " if EARLY <= lag <= LATE else "LATE" if lag > LATE else "EARLY"
                print(f"   anchor {flag} {a['word']!r} said {a['said']:.2f}, began {a['play']:+.2f} (lag {lag:+.2f})")
            for m in row["matched"]:
                flag = "ok " if EARLY <= m["lag"] <= LATE else "LATE" if m["lag"] > LATE else "EARLY"
                print(f"   {flag} {m['word']!r} said {m['said']:.2f}, shown {m['play']:+.2f} (lag {m['lag']:+.2f}): {m['what']}")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
