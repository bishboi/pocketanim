"""A YouTube video as a lecture's reference (harness/lecture/youtube_source.py), and Hinglish narration checks
(compile_lecture._language_mix)."""

from __future__ import annotations

import json
import sys
import types

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture  # noqa: E402
import youtube_source as yt  # noqa: E402

PASTED = "\n".join(f"{m}:{s:02d}\n{text}" for (m, s), text in zip(
    [(i * 20 // 60, i * 20 % 60) for i in range(30)],
    ["आज हम Newton के laws पढ़ेंगे।", "Force मतलब push या pull।", "First law को law of inertia कहते हैं।"] * 10))


def test_links_of_every_shape_give_the_video_id():
    for url in ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "https://youtu.be/dQw4w9WgXcQ",
                "https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://m.youtube.com/live/dQw4w9WgXcQ?x=1"]:
        assert yt.video_id(url) == "dQw4w9WgXcQ"


def test_a_pasted_transcript_keeps_its_timestamps_and_splits_into_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, "CACHE", tmp_path / "cache")
    manifest = yt.convert("", tmp_path / "out", pasted=PASTED, title="Laws of Motion")
    assert manifest["source"] == "youtube" and manifest["figures"] == []
    parts = manifest["parts"]
    assert len(parts) >= 3 and parts[0]["start"] == 0.0
    assert all(a["end"] <= b["start"] + 0.01 for a, b in zip(parts, parts[1:]))
    assert "## Part 1 (0:00" in open(manifest["markdown"], encoding="utf-8").read()


def test_youtube_captions_are_read_hand_made_first(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(yt, "_metadata", lambda vid: {"title": "Laws of Motion", "channel": "Physics Wallah"})

    class Snip:
        def __init__(self, text, start):
            self.text, self.start, self.duration = text, start, 4.0

    class Transcript:
        language_code, is_generated = "hi", False

        def fetch(self):
            return [Snip(f"line {i} about force।", i * 4.0) for i in range(120)]

    class Listing:
        def find_manually_created_transcript(self, languages):
            assert languages[0] == "hi"
            return Transcript()

    class Api:
        def list(self, vid):
            return Listing()

    monkeypatch.setitem(sys.modules, "youtube_transcript_api", types.SimpleNamespace(YouTubeTranscriptApi=Api))
    manifest = yt.convert("https://youtu.be/dQw4w9WgXcQ", tmp_path / "out")
    assert manifest["video"]["title"] == "Laws of Motion" and manifest["video"]["language"] == "hi"
    assert manifest["video"]["duration"] >= 470 and len(manifest["parts"]) >= 3


def test_a_blocked_network_says_to_paste_the_transcript():
    blocked = type("IpBlocked", (Exception,), {})("blocked")
    assert "Paste the transcript" in yt._why(blocked)


def _script(say, **op):
    beats = [{"say": say, "do": [op] if op else []} for _ in range(3)]
    return {"language": "hinglish", "title": "Laws of Motion", "chapters": [{"title": "Force", "narration": "x",
                                                                             "beats": beats}]}


def test_hinglish_narration_passes():
    errors, _ = compile_lecture._language_mix(_script("जब net force zero होता है, तो acceleration भी zero होता है।",
                                                      op="define", term="Inertia", meaning="Resistance to change"))
    assert errors == []


def test_romanised_hindi_is_refused():
    errors, _ = compile_lecture._language_mix(_script("Force matlab ek push hota hai, yaani dhakka।"))
    assert any("Latin letters" in e for e in errors)


def test_english_only_narration_is_refused():
    errors, _ = compile_lecture._language_mix(_script("Force is a push or a pull."))
    assert any("English only" in e for e in errors)


def test_hindi_on_screen_is_refused():
    errors, _ = compile_lecture._language_mix(_script("Force मतलब एक push है।", op="define", term="बल",
                                                      meaning="धक्का"))
    assert any("Hindi on the screen" in e for e in errors)


def test_other_languages_are_not_checked():
    script = _script("Force is a push.")
    script["language"] = "english"
    assert compile_lecture._language_mix(script) == ([], [])
    json.dumps(script)


def test_forge_reads_a_youtube_link_as_a_source(tmp_path, monkeypatch):
    from forge.engine import ingest
    from forge.job import Job

    def fake(url, out):
        md = tmp_path / "document.md"
        md.write_text("# Laws of Motion\n\n## Part 1 (0:00–2:30)\n\nForce मतलब push या pull है, और यह motion बदलता है।\n",
                      encoding="utf-8")
        return {"markdown": str(md), "video": {"title": "Laws of Motion"}, "note": None}

    monkeypatch.setattr(yt, "convert", fake)
    job = Job.create("yt", template="science_explainer", style="blueprint", sources=["https://youtu.be/dQw4w9WgXcQ"],
                     root=tmp_path)
    bundle = ingest.intake(job)
    assert bundle["problems"] == []
    assert bundle["sources"][0]["title"] == "Laws of Motion" and bundle["passages"]
