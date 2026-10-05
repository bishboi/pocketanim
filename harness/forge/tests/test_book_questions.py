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


def test_many_questions_are_split_into_sections_a_model_can_write(tmp_path):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    built = subprocess.run([str(tsc), "lib/transcript.ts", "lib/questions.ts", "--outDir", str(tmp_path), "--module",
                            "commonjs", "--target", "es2022", "--skipLibCheck", "--esModuleInterop"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    script = f"""
const t = require({json.dumps(str(tmp_path / 'transcript.js'))});
let md = '# Motion\\n\\n' + 'Motion is change of place. '.repeat(200) + '\\n\\n## Exercises\\n\\n';
for (let i = 1; i <= 20; i++) md += i + '. Which unit is number ' + i + ' here?\\n(a) metre\\n(b) second\\n(c) newton\\n(d) watt\\n\\n';
const s = t.bookSections(md, 10);
const last = s[s.length - 1];
const said = last.questions.map((x) => 'बच्चों, ' + x.text + ' Option A, metre, यह length है। Option B, second, यह time है। ' +
  'Option C, newton, यही सही है? Option D, watt, power है।').join(' ') + ' ' + 'और ध्यान से समझो। '.repeat(400);
console.log(JSON.stringify({{
  sections: s.map((x) => [x.words, (x.questions || []).length, !!x.questionsOnly]),
  problem: t.sectionProblem(said, last, 'hinglish'),
}}));
"""
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert sum(n for _, n, _ in out["sections"]) == 20
    assert all(words <= 1600 for words, n, _ in out["sections"] if n)     # no section of 5,000 words of questions
    assert sum(only for *_, only in out["sections"]) >= 2
    # Read out as the book prints them, in English, with no example of its own: still a good section.
    assert out["problem"] is None


def test_a_long_lecture_without_a_topic_plan_is_cut_between_chapters_into_parts(tmp_path):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    built = subprocess.run([str(tsc), "lib/parts.ts", "--outDir", str(tmp_path), "--module", "commonjs", "--target",
                            "es2022", "--skipLibCheck", "--esModuleInterop"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    script = (f"const {{ splitLecture }} = require({json.dumps(str(tmp_path / 'parts.js'))});"
              "const ch = (n, w) => ({ title: 'C' + n, narration: 'x', beats: [{ say: Array(w).fill('w').join(' ') }] });"
              "const s = { title: 'Forces', intro: 'hi', recap: [['a', 'b']], credits: 'c',"
              " chapters: [ch(1, 500), ch(2, 700), ch(3, 600), ch(4, 800), ch(5, 400), ch(6, 900)] };"
              "console.log(JSON.stringify([50, 90, 130].map((m) => splitLecture(s, m, 60).map((p) => ({"
              " title: p.title, chapters: p.script.chapters.map((c) => c.title), minutes: p.minutes,"
              " intro: 'intro' in p.script, recap: 'recap' in p.script, credits: p.script.credits })))));")
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    whole, two, three = json.loads(done.stdout)
    assert whole == []                                             # under the limit: one video
    assert [p["chapters"] for p in two] == [["C1", "C2", "C3"], ["C4", "C5", "C6"]]
    assert all(p["minutes"] <= 60 for p in two) and len(three) == 3
    assert [p["title"] for p in two] == ["Forces · Part 1 of 2", "Forces · Part 2 of 2"]
    assert [(p["intro"], p["recap"], p["credits"]) for p in two] == [(True, False, "c"), (False, True, "c")]


def test_chapter_numbered_exercises_and_a_hindi_explanation_of_english_questions():
    out = _run("import { bookQuestions, unexplainedQuestions } from './lib/questions.ts';"
               "const md = '## Exercises\\n\\n4.1 Give the magnitude and direction of the net force acting on a drop of rain.\\n\\n"
               "4.2 A pebble of mass 0.05 kg is thrown vertically upwards. Give the net force on it at 2.5 s.\\n\\n"
               "4.23 Explain why\\n(a) a horse cannot pull a cart and run in empty space,\\n"
               "(b) passengers are thrown forward from their seats when a speeding bus stops suddenly,\\n';"
               "const qs = bookQuestions(md);"
               "const hindi = 'अब प्रश्न 4.1 देखो, बूंद पर नेट बल शून्य है। कंकड़ का द्रव्यमान 0.05 किलोग्राम, समय 2.5 सेकंड।';"
               "console.log(JSON.stringify({ qs: qs.map((q) => [q.number, q.choices.length, q.text.slice(0, 12)]),"
               " left: unexplainedQuestions(hindi, qs).map((x) => x.id) }));")
    assert out["qs"] == [["4.1", 0, "Give the mag"], ["4.2", 0, "A pebble of "], ["4.23", 0, "Explain why "]]
    # 4.1 by its number, 4.2 by its numbers (0.05 kg, 2.5 s); 4.23, its parts, never: still to explain.
    assert out["left"] == ["q3"]
