"""The transcript tells the lesson as one story and covers its source whole (app/lib/transcript.ts, coverage.ts):
the prompt asks for the why, what, how and so-what of each idea with bridges between them, and for the book's
asides said plainly as asides; each section is told its part's thread and asides, and a section that leaves out a
heading, an aside or more than one key term is refused and mended by adding what it left out."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

BOOK = """# 4.1 Force and Motion

A **force** is a push or a pull. Forces change the **velocity** of a body.

## 4.2 Newton's First Law of Motion

A body stays at rest or keeps moving unless a force acts on it. This is **inertia**.

### Do you know?

Galileo rolled balls down slopes to discover **friction**.

## 4.3 Momentum

The **momentum** of a body is its mass times its velocity.
"""

GOOD = ("Why does a bus jerk you forward when it brakes? Let us find out. A force is a push or a pull, for example a kick, and forces "
        "change the velocity of a body. But this raises a question: what happens when no force acts? That is Newton's "
        "first law of motion: a body keeps doing what it was doing. We call this inertia. A quick side note, not part "
        "of our main story: Galileo rolled balls down slopes and found friction slowing them. Back to our question. "
        "Now that we know inertia, we can understand momentum: mass times velocity.")


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    out = tmp_path_factory.mktemp("lib")
    built = subprocess.run([str(tsc), "lib/transcript.ts", "lib/coverage.ts", "--outDir", str(out), "--module",
                            "commonjs", "--target", "es2022", "--skipLibCheck", "--esModuleInterop"],
                           cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    return out


def _node(lib: Path, body: str):
    script = (f"const t = require({json.dumps(str(lib / 'transcript.js'))});"
              f"const c = require({json.dumps(str(lib / 'coverage.js'))});" + body)
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60,
                          env={"PATH": os.environ["PATH"]})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_thread_and_the_asides_are_found(lib):
    got = _node(lib, f"console.log(JSON.stringify({{ideas: c.ideasOf({json.dumps(BOOK)}), asides: c.asidesOf({json.dumps(BOOK)})}}))")
    thread = [i["text"] for i in got["ideas"] if i["kind"] != "aside"]
    assert "Force and Motion" in thread and "Newton's First Law of Motion" in thread and "Momentum" in thread
    assert {"force", "velocity", "inertia"} <= set(thread)            # "momentum" is the heading "Momentum" already
    assert [a["title"] for a in got["asides"]] == ["Do you know?"]
    assert "Galileo" in got["asides"][0]["text"]
    assert {"kind": "aside", "text": "friction"} in got["ideas"]


def test_the_prompt_has_four_aims_and_tells_it_as_a_story(lib):
    """Four things are asked: the quality of the learning (how to teach is the writer's), told as a story, videos
    of 25-30 minutes, and everything in the source covered."""
    section = {"n": 1, "parts": [], "minutes": 1, "words": 60, "source": BOOK, "book": True}
    got = _node(lib, f"""const s = {json.dumps(section)};
      console.log(JSON.stringify({{prompt: t.transcriptPrompt({{sections: [s], minutes: 5, language: 'english',
        languageRules: '', hasReference: false, content: ''}}), request: t.sectionRequest(s, 1, [])}}))""")
    prompt, request = got["prompt"], got["request"]
    assert "THE QUALITY OF THE LEARNING" in prompt and "are yours to decide" in prompt
    assert "VIDEOS OF 25-30 MINUTES" in prompt and "COVER EVERYTHING IN THE SOURCE" in prompt
    # Told as a story, with the facts exact and the figures used in the story, not read out.
    assert "TOLD AS A STORY" in prompt and "HOW TO TELL IT AS A STORY" in prompt
    assert "never changes the facts" in prompt and "Never read out every label" in prompt
    for rule in ("SAY EACH THING ONCE", "everyday example", "Short sentences",
                 "at least", "words in", "EXAMPLE of the voice"):
        assert rule not in prompt, rule
    assert "about" not in request.split("\n")[0] or "words" not in request          # no word target per section
    assert "WHAT THIS PART COVERS" in request and "Newton's First Law of Motion" in request
    assert "ASIDES IN THIS PART" in request and "Do you know?" in request


@pytest.mark.parametrize("language", ["hinglish", "hindi", "english", "auto"])
def test_the_teacher_talks_to_the_class_as_friends(lib, language):
    """The class is addressed as friends ("दोस्तों", "समझे दोस्तों?"), never as children, with check-ins after an
    idea; in Devanagari for Hindi and Hinglish, so the voice reads it as Hindi."""
    got = _node(lib, f"""console.log(JSON.stringify(t.transcriptPrompt({{sections: [], minutes: 5,
        language: '{language}', languageRules: '', hasReference: false, content: ''}})))""")
    voice = got.split("THE VOICE", 1)[1].split("HOW THE TRANSCRIPT IS USED", 1)[0]
    if language != "english":
        assert "समझे दोस्तों?" in voice and "never \"बच्चों\"" in voice
    if language in ("english", "auto"):
        assert "got it, friends?" in voice


def test_only_an_empty_section_is_sent_back(lib):
    """A section is never sent back for its length, for saying something twice, for what it covers: what it
    teaches is the writer's, told in the prompt. Only an empty reply is refused."""
    section = {"n": 3, "parts": [], "minutes": 1, "words": 1200, "source": "plain notes"}
    once = "A force is a push or a pull on a body."
    again = once + " Remember, a force is a push or a pull on a body. " * 3
    got = _node(lib, f"""const s = {json.dumps(section)};
      console.log(JSON.stringify({{ short: t.sectionProblem({json.dumps(once)}, s),
        again: t.sectionProblem({json.dumps(again)}, s),
        long: t.sectionProblem({json.dumps(once * 400)}, {{ ...s, words: 50 }}),
        book: t.sectionProblem('Nothing of the book.', {{ ...s, book: true, source: {json.dumps(BOOK)} }}),
        empty: t.sectionProblem('  ', s) }}))""")
    assert {k: v for k, v in got.items() if k != "empty"} == {"short": None, "again": None, "long": None, "book": None}, got
    assert "came back empty" in got["empty"]


def test_a_section_is_told_what_the_ones_before_it_taught(lib):
    """The transcript writer notes what each section taught (write_section "taught"); a later section is given those
    notes, to point back instead of explaining again or reusing an example."""
    prior = [{"n": 1, "title": "Force", "text": "...", "taught": ["defined force", "example: pushing a door"]},
             {"n": 2, "title": "Inertia", "text": "...", "taught": ["defined inertia", "asked: why does a ball stop?"]}]
    section = {"n": 3, "parts": [], "minutes": 1, "words": 60, "source": BOOK, "book": True}
    got = _node(lib, f"""console.log(JSON.stringify({{request: t.sectionRequest({json.dumps(section)}, 5,
        {json.dumps(prior)}), tool: t.SECTION_TOOL, first: t.sectionRequest({json.dumps(section)}, 5, [])}}))""")
    request = got["request"]
    assert "ALREADY TAUGHT" in request
    assert 'Section 1 "Force": defined force; example: pushing a door' in request
    assert 'Section 2 "Inertia": defined inertia; asked: why does a ball stop?' in request
    assert "ALREADY TAUGHT" not in got["first"]
    assert "taught" in got["tool"]["function"]["parameters"]["required"]


def test_taught_notes_are_short_and_distinct(lib):
    notes = ["- defined force", "defined force", "example: " + "x" * 300, "", "asked: why?"]
    got = _node(lib, f"""const k = require({json.dumps(str(lib / 'continuity.js'))});
        console.log(JSON.stringify(k.taughtNotes({json.dumps(notes)})))""")
    assert got[0] == "defined force" and len(got) == 3 and len(got[1]) <= 90


def test_a_video_section_is_told_what_the_others_put_on_screen(lib):
    """Each section's video writer sees what the other sections' chapters showed (figures, pictures, diagrams,
    timelines, maps), so the same picture is not drawn again in every section."""
    def script(*ops):
        return {"chapters": [{"title": "A", "beats": [{"lines": [1], "do": list(ops)}]}]}
    done = [[1, script({"op": "figure", "id": "fig4", "caption": "A manorial estate", "show": ["church", "fields"]},
                       {"op": "picture", "generate": "a medieval knight on horseback", "labels": ["lance"]})],
            [2, script({"op": "diagram", "id": "orders", "kind": "hub", "nodes": [{"id": "k", "label": "King"},
                                                                                  {"id": "n", "label": "Nobles"}]},
                       {"op": "timeline", "events": [["800", "Charlemagne crowned"], ["1066", "Norman Conquest"]]},
                       {"op": "panel", "title": "words only"})],
            [3, script({"op": "picture", "generate": "a monk copying a book"})]]
    got = _node(lib, f"""const k = require({json.dumps(str(lib / 'continuity.js'))});
        const done = new Map({json.dumps(done)});
        console.log(JSON.stringify({{forTwo: k.shownSoFar(done, 2), none: k.shownSoFar(new Map(), 1)}}))""")
    text = "\n".join(got["forTwo"])
    assert "ALREADY ON SCREEN" in text and "Do not draw these again" in text
    assert "the book's figure fig4 (\"A manorial estate\"), parts church, fields" in text
    assert 'a picture made of "a medieval knight on horseback" (labelled lance)' in text
    assert 'Section 3: a picture made of "a monk copying a book"' in text
    assert 'the very same "generate" words' in text
    assert "Section 2" not in text and "words only" not in text          # its own section, and words, are left out
    assert got["none"] == []


def test_a_preview_is_the_opening_few_minutes(lib):
    """Preview first: the opening sections only, cut at a paragraph to about three minutes of teaching, without
    the book's exercise questions, renumbered from 1."""
    para = "Feudal society had three orders. " * 40
    sections = [{"n": 1, "parts": [], "minutes": 8, "words": 1600, "source": "\n\n".join([para] * 8), "book": True,
                 "questions": [{"text": "Q?"}]},
                {"n": 2, "parts": [], "minutes": 6, "words": 1200, "source": para, "book": True},
                {"n": 3, "parts": [], "minutes": 2, "words": 300, "source": "Questions.", "questionsOnly": True}]
    got = _node(lib, f"""console.log(JSON.stringify(t.previewSections({json.dumps(sections)})))""")
    assert len(got) == 1 and got[0]["n"] == 1 and got[0]["questions"] == []
    assert got[0]["minutes"] == 3 and len(got[0]["source"]) < len(sections[0]["source"]) * 0.5
    short = [{**sections[1], "n": 1, "minutes": 1.5}, {**sections[1], "n": 2, "minutes": 1.2},
             {**sections[1], "n": 3, "minutes": 2}]
    got = _node(lib, f"""console.log(JSON.stringify(t.previewSections({json.dumps(short)})))""")
    assert [s["n"] for s in got] == [1, 2] and sum(s["minutes"] for s in got) <= 3.01
