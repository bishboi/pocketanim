"""The questions of an uploaded book, found by app/lib/questions.ts (run with Node's TypeScript support)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

BOOK = """
# Force and Laws of Motion

A force is a push or a pull.

## Intext Questions

1. Which of the following has more inertia: a rubber ball or a stone of the same size?
2. In a game of football, why does the ball stop
rolling after some time?

## Exercises

**Multiple Choice Questions**

1. Which of these is a force?
(a) Kicking a ball
(b) Sleeping
(c) Thinking
(d) Reading
Ans. (a)

2. The SI unit of force is (a) joule (b) newton (c) watt (d) pascal

3. Define momentum.

प्रश्न 4. बल का SI मात्रक क्या है?
(क) जूल
(ख) न्यूटन
(ग) वाट
(घ) पास्कल

# Summary

1. Inertia is the tendency to stay at rest.
"""


def _run(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node")
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    if int(version.split(".")[0]) < 22:
        pytest.skip("Node 22+ runs TypeScript directly")
    done = subprocess.run([node, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
                          capture_output=True, text=True, cwd=APP, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_books_questions_are_found_with_their_choices():
    found = _run(f"import {{ bookQuestions }} from './lib/questions.ts';"
                 f"console.log(JSON.stringify(bookQuestions({json.dumps(BOOK)})));")
    assert [q["id"] for q in found] == ["q1", "q2", "q3", "q4", "q5", "q6"]       # the summary's list is not a question
    assert found[1]["text"].endswith("rolling after some time?")                  # run on to the next line
    assert found[2]["choices"] == ["Kicking a ball", "Sleeping", "Thinking", "Reading"] and found[2]["answer"] == "(a)"
    assert found[3]["text"] == "The SI unit of force is" and found[3]["choices"][1] == "newton"   # choices on one line
    assert found[4]["choices"] == [] and found[4]["number"] == "3"
    assert found[5]["choices"] == ["जूल", "न्यूटन", "वाट", "पास्कल"]


def test_a_section_that_skips_an_option_is_refused():
    out = _run("import { unexplainedQuestions } from './lib/questions.ts';"
               "const q = { id: 'q4', number: '2', text: 'The SI unit of force is', choices: ['joule', 'newton', 'watt', 'pascal'] };"
               "const told = 'The SI unit of force is asked here. Option A, joule, is energy. Option B, newton, is right. ';"
               "console.log(JSON.stringify([unexplainedQuestions(told, [q]),"
               " unexplainedQuestions(told + 'Watt is power, and pascal is pressure.', [q]),"
               " unexplainedQuestions('Nothing about it.', [q])]));")
    assert out[0] == [{"id": "q4", "what": "question 2: options C, D"}]
    assert out[1] == []
    assert out[2][0]["what"].startswith("question 2 (")
