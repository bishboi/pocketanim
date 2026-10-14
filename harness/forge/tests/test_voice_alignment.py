"""The voice made first, the animations timed to it after: ElevenLabs' word times (eleven_tts), the voice
director's marking of each line (voice_director), the timing slots a model fills in (align_cues), and the engine
playing a beat's animations at their cues (Lecture.beat / free with cues)."""

from __future__ import annotations

import ast
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import align_cues  # noqa: E402
import compile_lecture as cl  # noqa: E402
import eleven_tts  # noqa: E402
import pocket_lecture as pl  # noqa: E402
import voice_director  # noqa: E402


def _serve(reply):
    """A local server answering every POST with reply(path, body) as JSON; the requests it got."""
    got = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
            data = json.dumps(reply(self.path, body)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", got, server


def _alignment(text: str, per_char: float = 0.05) -> dict:
    chars = list(text)
    return {"characters": chars, "character_start_times_seconds": [i * per_char for i in range(len(chars))],
            "character_end_times_seconds": [(i + 1) * per_char for i in range(len(chars))]}


def test_word_times_come_from_the_character_alignment_without_the_tags():
    text = "[thoughtful] The lord gave a FIEF... to the knight."
    said = eleven_tts.words(**{k: v for k, v in zip(("characters", "starts", "ends"),
                                                    _alignment(text).values())})
    assert [w["w"] for w in said] == ["The", "lord", "gave", "a", "FIEF", "to", "the", "knight"]
    assert said[0]["start"] == round(text.index("The") * 0.05, 3)
    assert all(a["end"] <= b["start"] for a, b in zip(said, said[1:]))


def test_elevenlabs_speaks_a_line_with_its_word_times(monkeypatch):
    pcm = b"\x00\x01" * 2400

    def reply(path, body):
        return {"audio_base64": base64.b64encode(pcm).decode(), "alignment": _alignment(body["text"])}

    url, got, server = _serve(reply)
    try:
        monkeypatch.setenv("ELEVENLABS_URL", url)
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
        monkeypatch.delenv("PANIM_ELEVEN_MODEL", raising=False)
        wav = eleven_tts.speak("[curious] What holds a kingdom together?", "voice123", 1.0)
    finally:
        server.shutdown()
    path, headers, body = got[0]
    assert path.startswith("/v1/text-to-speech/voice123/with-timestamps") and "pcm_24000" in path
    assert headers.get("xi-api-key") == "test" and body["model_id"] == "eleven_v4_turbo"
    assert wav[:4] == b"RIFF"
    assert [w["w"] for w in eleven_tts.last_words()] == ["What", "holds", "a", "kingdom", "together"]


def test_the_director_may_not_change_a_word():
    line = "The king owned all the land, and granted it to his nobles."
    assert voice_director.acceptable(line, "[thoughtful] The king owned ALL the land... and granted it to his nobles.")
    assert not voice_director.acceptable(line, "[thoughtful] The king owned the land, and granted it to his nobles.")
    assert not voice_director.acceptable(line, "[laughs] The king owned all the land, and granted it to his nobles.")
    assert not voice_director.acceptable(line, "[warm] [curious] [slowly] The king owned all the land, and granted "
                                               "it to his nobles.")


def test_the_director_marks_lines_and_drops_a_line_it_reworded(monkeypatch):
    lines = ["William won at Hastings in 1066.", "Then he needed to hold the land."]

    def reply(path, body):
        return {"choices": [{"message": {"content": json.dumps({"lines": [
            {"n": 1, "say": "[serious] William won at HASTINGS in 1066."},
            {"n": 2, "say": "[curious] Then he had to hold the land."}]})}}], "usage": {"cost": 0.001}}

    url, got, server = _serve(reply)
    try:
        monkeypatch.setenv("OPENROUTER_URL", url)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test")
        marked, usd = voice_director.mark(lines)
    finally:
        server.shutdown()
    assert marked == {lines[0]: "[serious] William won at HASTINGS in 1066."} and usd == 0.001


def _script():
    nodes = [{"id": "w", "label": "William I"}, {"id": "n", "label": "Norman nobles"}, {"id": "k", "label": "Knights"}]
    return {"title": "T", "style": "parchment", "teaching_rules": False, "auto_visuals": False, "place_figures": False,
            "chapters": [{"title": "Royal power", "map": False, "beats": [
                {"say": "William granted land to his nobles, and the nobles owed knights.",
                 "do": [{"op": "diagram", "id": "d", "kind": "hierarchy", "nodes": nodes,
                         "edges": [["w", "n"], ["n", "k"]]}, {"op": "focus", "diagram": "d", "node": "k"}]},
                {"say": "A square, then a circle beside it.", "do": [{"op": "manim", "id": "f", "code":
                    "s = Square()\nself.play(Create(s), run_time=0.3)\nc = Circle().next_to(s)\n"
                    "self.play(Create(c), run_time=0.3)"}]}]}]}


def test_the_model_fills_the_timing_slots_of_a_compiled_lecture(monkeypatch):
    monkeypatch.setenv("PANIM_MANIM_CHECK", "off")
    source = cl.compile_script(_script())
    found = align_cues.beats(source)
    kinds = {b["kind"]: b for b in found}
    assert len(kinds["beat"]["parts"]) == 2 and "focus" in kinds["beat"]["parts"][1]
    assert len(kinds["free"]["parts"]) == 2

    def words(text):
        return [{"w": w, "start": round(i * 0.4, 2), "end": round(i * 0.4 + 0.35, 2)}
                for i, w in enumerate(text.rstrip(".").replace(",", "").split())]

    asked = []

    def reply(path, body):
        user = body["messages"][1]["content"]
        asked.append(user)
        beats = []
        for block in user.split("\n\n"):
            k = int(block.split("\n")[0].split()[1])
            if "FREE" in block:
                beats.append({"id": k, "starts": [0, 1.6]})
            else:
                # Out of order on purpose: the focus before the diagram is pushed after it.
                beats.append({"id": k, "cues": [[0.2, 1.5], [0.0, 0.7]]})
        return {"choices": [{"message": {"content": json.dumps({"beats": beats})}}], "usage": {"cost": 0.002}}

    url, got, server = _serve(reply)
    try:
        monkeypatch.setenv("OPENROUTER_URL", url)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test")
        aligned, report = align_cues.align(source, words, lambda text: 5.0)
    finally:
        server.shutdown()
    assert "4.00:knights" in asked[0]                        # the words go with their times
    assert report["aligned"] == 2 and report["usd"] == 0.002
    ast.parse(aligned)
    assert "cues=[[0.2, 1.5], [0.2, 0.7]]" in aligned       # kept in the order given
    assert "cues=[0.0, 1.6]" in aligned
    # Aligned again: the slots are replaced, not added to.
    assert align_cues.write_cues(aligned, [(b, [[0, 1], [1, 1]]) for b in align_cues.beats(aligned)
                                           if b["kind"] == "beat"]).count("cues=") == 2


def _probe():
    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    log, clock = [], [0.0]
    real_play = scene.play

    def play(*anims, run_time=1.0, **kw):
        log.append((round(clock[0], 2), round(run_time, 2)))
        clock[0] += run_time
        real_play(*anims, run_time=0.05, **kw)

    def wait(t=1.0, **kw):
        clock[0] += t

    scene.play, scene.wait = play, wait
    return scene, log, clock


def test_a_beat_plays_each_animation_at_its_cue(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 6.0))
    scene, log, clock = _probe()
    nodes = [{"id": k, "label": k} for k in ("lord", "knight", "fief")]
    scene.beat("Here is how it worked, and here is the fief.",
               scene.diagram("d", "flow", nodes, [["lord", "knight"], ["knight", "fief"]]),
               scene.spotlight("d", "fief"), cues=[[0.0, 1.5], [3.4, 0.7]])
    assert log == [(0.0, 1.5), (3.4, 0.7)]                   # the diagram as the line begins, the focus on "fief"
    assert clock[0] >= 6.0                                   # the line is never cut short


def test_a_cue_too_late_or_too_long_is_kept_inside_the_line(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 3.0))
    scene, log, clock = _probe()
    nodes = [{"id": k, "label": k} for k in ("a", "b")]
    scene.beat("One and two.", scene.diagram("d", "flow", nodes, [["a", "b"]]), scene.spotlight("d", "b"),
               cues=[[0.0, 9.0], [7.0, 0.5]])
    assert log[0] == (0.0, 2.7) and log[1][0] == 2.7         # cut to fit before the next, which starts in the line


def test_without_cues_a_beat_plays_as_before(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 4.0))
    scene, log, clock = _probe()
    nodes = [{"id": k, "label": k} for k in ("a", "b")]
    scene.beat("One and two.", scene.diagram("d", "flow", nodes, [["a", "b"]]), scene.spotlight("d", "b"))
    assert log == [(0.0, 2.2)]                               # 55% of the line, together


def test_a_free_blocks_plays_start_at_their_cues(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 4.0))

    class Probe(pl.MapLecture):
        def construct(self):
            pass

        def play(self, *anims, **kw):
            names = [type(getattr(a, "mobject", None)).__name__ for a in anims]
            starts.append((self.renderer.time, names))
            return super().play(*anims, **kw)

    starts: list[float] = []
    scene = Probe()
    scene.setup()
    scene.board()
    code = "s = Square()\nself.play(Create(s), run_time=0.2)\nc = Circle()\nself.play(Create(c), run_time=0.2)"
    scene.free("f", "A square, then a circle.", code, cues=[0.0, 2.0])
    square = next(t for t, names in starts if "Square" in names)
    circle = next(t for t, names in starts if "Circle" in names)
    assert circle - square >= 1.95                           # the circle on its words, not straight after


def test_a_lecture_is_spoken_then_timed_then_built(tmp_path, monkeypatch):
    # The whole way, as the export route runs it: the voice director marks the lines, ElevenLabs speaks them
    # with their word times, the timing slots are filled from those, and the lecture builds for the video and
    # the phone with the animations at their cues.
    import os
    import subprocess
    import sys

    from forge.util import REPO

    monkeypatch.setenv("PANIM_MANIM_CHECK", "off")
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(_script()))
    spoken = []

    def reply(path, body):
        if path.startswith("/v1/text-to-speech/"):
            spoken.append(body["text"])
            n = int(len(body["text"]) * 0.06 * 24000)
            return {"audio_base64": base64.b64encode(b"\x00\x00" * n).decode(),
                    "alignment": _alignment(body["text"], 0.06)}
        user = body["messages"][1]["content"]
        if "lecture's lines" in body["messages"][0]["content"]:
            first = user.split("\n")[0].split(". ", 1)[1]
            return {"choices": [{"message": {"content": json.dumps({"lines": [{"n": 1, "say": "[warm] " + first}]})}}]}
        beats = []
        for block in user.split("\n\n"):
            k = int(block.split("\n")[0].split()[1])
            beats.append({"id": k, "starts": [0, 1.0]} if "FREE" in block else {"id": k, "cues": [[0, 1.2], [2.6, 0.6]]})
        return {"choices": [{"message": {"content": json.dumps({"beats": beats})}}], "usage": {"cost": 0.0}}

    url, got, server = _serve(reply)
    env = {**os.environ, "PANIM_TTS": "eleven", "ELEVENLABS_API_KEY": "t", "ELEVENLABS_URL": url,
           "OPENROUTER_API_KEY": "t", "OPENROUTER_URL": url, "PANIM_AUDIO_DIR": str(tmp_path / "audio"),
           "PANIM_ENV_FILE": "", "PANIM_BUILD_WORKERS": "2"}
    env.pop("PANIM_VOICE", None)

    def run(*args):
        return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=env, timeout=900,
                              cwd=REPO)

    try:
        said = run(REPO / "harness/scripts/prespeak.py", scene)
        assert json.loads(said.stdout.strip().splitlines()[-1])["ok"], said.stderr[-800:]
        out = tmp_path / "aligned.py"
        aligned = run(REPO / "harness/scripts/align_beats.py", scene, out)
        report = json.loads(aligned.stdout.strip().splitlines()[-1])
        assert report["aligned"] == 2, (report, aligned.stderr[-800:], scene.read_text()[-1500:])
        built = run(REPO / "harness/scripts/export_scene.py", out, "GeneratedScene", tmp_path / "build")
        result = json.loads(built.stdout.strip().splitlines()[-1])
    finally:
        server.shutdown()
    assert any(t.startswith("[warm] ") for t in spoken)          # the director's marking is what was said
    assert "cues=[[0.0, 1.2], [2.6, 0.6]]" in out.read_text()
    assert result["tier"] == 1 and not result.get("skipped"), built.stderr[-1500:]
