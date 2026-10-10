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
    assert "leaves out parts of its book text" in got["bad"] and "Momentum" in got["bad"] and "friction" in got["bad"]
    # An English book taught in Hindi cannot be matched word for word: left to the prompt, not refused.
    assert got["hindi"] is None or "leaves out" not in got["hindi"]
    assert _node(lib, f"console.log(JSON.stringify(t.repairable({json.dumps(got['bad'])})))") is True


def test_the_prompt_asks_for_one_story_and_each_section_lists_its_thread(lib):
    section = {"n": 1, "parts": [], "minutes": 1, "words": 60, "source": BOOK, "book": True}
    got = _node(lib, f"""const s = {json.dumps(section)};
      console.log(JSON.stringify({{prompt: t.transcriptPrompt({{sections: [s], minutes: 5, language: 'english',
        languageRules: '', hasReference: false, content: ''}}), request: t.sectionRequest(s, 1, [])}}))""")
    prompt, request = got["prompt"], got["request"]
    assert "TELL IT AS ONE STORY" in prompt and "WHY we need it" in prompt and "ASIDES" in prompt
    assert "COVER EVERYTHING" in prompt
    assert "THE THREAD OF THIS PART" in request and "Newton's First Law of Motion" in request
    assert "ASIDES IN THIS PART" in request and "Do you know?" in request


def test_a_section_that_repeats_itself_or_an_earlier_one_is_refused(lib):
    section = {"n": 3, "parts": [], "minutes": 1, "words": 120, "source": "plain notes"}
    once = ("A force is a push or a pull on a body. For example, you push a door to open it. Why does a ball "
            "stop rolling on grass? The grass rubs against the ball and slows it down. That rubbing is friction, "
            "and it always acts against the motion. Can you think of a place with very little friction? On ice a "
            "puck slides a long way because almost nothing rubs it. A heavier body needs a bigger force to start "
            "moving, which we call inertia. So the same kick moves a football far and a stone hardly at all.")
    again = once + (" Remember, a force is a push or a pull on a body. The grass rubs against the ball and slows it "
                    "down. That rubbing is friction, and it always acts against the motion. On ice a puck slides a long "
                    "way because almost nothing rubs it.")
    got = _node(lib, f"""const s = {json.dumps(section)};
      console.log(JSON.stringify({{ once: t.sectionProblem({json.dumps(once)}, s, 'english'),
        again: t.sectionProblem({json.dumps(again)}, s, 'english'),
        earlier: t.sectionProblem({json.dumps(once)}, s, 'english', [{json.dumps(once)}]),
        short: t.sectionProblem({json.dumps(once)}, {{ ...s, words: 110 }}, 'english') }}))""")
    assert got["once"] is None and got["short"] is None, got        # said once, and 75% of the target is enough
    assert "repeats itself" in got["again"]
    assert "repeats itself" in got["earlier"]                      # teaching again what an earlier section taught


def test_the_prompts_ask_for_each_thing_once(lib):
    section = {"n": 1, "parts": [], "minutes": 1, "words": 60, "source": BOOK, "book": True}
    prompt = _node(lib, f"""console.log(JSON.stringify(t.transcriptPrompt({{sections: [{json.dumps(section)}],
      minutes: 5, language: 'english', languageRules: '', hasReference: false, content: ''}})))""")
    assert "SAY EACH THING ONCE" in prompt and "ONE everyday example" in prompt
    assert "REPEAT." not in prompt and "again in other words" not in prompt and "two or three everyday" not in prompt
