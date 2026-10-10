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


def test_a_section_that_skips_part_of_its_book_is_refused_and_mended(lib):
    section = {"n": 2, "parts": [], "minutes": 1, "words": 85, "source": BOOK, "book": True}
    body = (f"const s = {json.dumps(section)};"
            f"const good = {json.dumps(GOOD)};"
            "const skipped = good.replace(/A quick side note.*?Back to our question\\. /, '')"
            "  .replace('Now that we know inertia, we can understand momentum: mass times velocity.', 'That is all.');"
            "console.log(JSON.stringify({good: t.sectionProblem(good, s, 'english'),"
            "  bad: t.sectionProblem(skipped, s, 'english'),"
            "  hindi: t.sectionProblem(skipped, s, 'hindi')}));")
    got = _node(lib, body)
    assert got["good"] is None, got["good"]
    assert "leaves out parts of its source" in got["bad"] and "Momentum" in got["bad"] and "friction" in got["bad"]
    # An English book taught in Hindi cannot be matched word for word: left to the prompt, not refused.
    assert got["hindi"] is None or "leaves out" not in got["hindi"]
    assert _node(lib, f"console.log(JSON.stringify(t.repairable({json.dumps(got['bad'])})))") is True


def test_the_prompt_has_three_aims_and_no_rules_of_teaching(lib):
    """Only three things are asked: the quality of the learning (how to teach is the writer's), videos of 25-30
    minutes, and everything in the source covered."""
    section = {"n": 1, "parts": [], "minutes": 1, "words": 60, "source": BOOK, "book": True}
    got = _node(lib, f"""const s = {json.dumps(section)};
      console.log(JSON.stringify({{prompt: t.transcriptPrompt({{sections: [s], minutes: 5, language: 'english',
        languageRules: '', hasReference: false, content: ''}}), request: t.sectionRequest(s, 1, [])}}))""")
    prompt, request = got["prompt"], got["request"]
    assert "THE QUALITY OF THE LEARNING" in prompt and "How to teach is yours to decide" in prompt
    assert "VIDEOS OF 25-30 MINUTES" in prompt and "COVER EVERYTHING IN THE SOURCE" in prompt
    for rule in ("TELL IT AS ONE STORY", "SAY EACH THING ONCE", "everyday example", "बच्चों", "Short sentences",
                 "at least", "words in", "EXAMPLE of the voice"):
        assert rule not in prompt, rule
    assert "about" not in request.split("\n")[0] or "words" not in request          # no word target per section
    assert "WHAT THIS PART COVERS" in request and "Newton's First Law of Motion" in request
    assert "ASIDES IN THIS PART" in request and "Do you know?" in request


def test_length_style_and_repetition_are_the_writers(lib):
    """A section is never sent back for its length, for saying something twice, for its questions or examples:
    only for leaving part of its source out."""
    section = {"n": 3, "parts": [], "minutes": 1, "words": 1200, "source": "plain notes"}
    once = "A force is a push or a pull on a body."
    again = once + " Remember, a force is a push or a pull on a body. " * 3
    got = _node(lib, f"""const s = {json.dumps(section)};
      console.log(JSON.stringify({{ short: t.sectionProblem({json.dumps(once)}, s, 'english'),
        again: t.sectionProblem({json.dumps(again)}, s, 'english'),
        long: t.sectionProblem({json.dumps(once * 400)}, {{ ...s, words: 50 }}, 'english') }}))""")
    assert got == {"short": None, "again": None, "long": None}, got
