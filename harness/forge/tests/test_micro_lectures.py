"""A long lecture as a series of micro-lectures of 20-30 minutes, one per topic (app/lib/topics.ts, parts.ts)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    out = tmp_path_factory.mktemp("lib")
    built = subprocess.run([str(tsc), "lib/topics.ts", "lib/parts.ts", "lib/transcript.ts", "--outDir", str(out),
                            "--module", "commonjs", "--target", "es2022", "--skipLibCheck", "--esModuleInterop"],
                           cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    return out


def _node(lib: Path, body: str):
    script = (f"const topics = require({json.dumps(str(lib / 'topics.js'))});"
              f"const parts = require({json.dumps(str(lib / 'parts.js'))});"
              f"const transcript = require({json.dumps(str(lib / 'transcript.js'))});" + body)
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60,
                          env={"PATH": __import__("os").environ["PATH"]})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


SECTIONS = """
const sec = (n, minutes, source = 'text', extra = {}) => ({ n, parts: [], minutes, words: minutes * 100, source, book: true, ...extra });
"""


def test_a_long_lecture_is_planned_as_topics_of_twenty_to_thirty_minutes(lib):
    out = _node(lib, SECTIONS + """
const twelve = Array.from({ length: 12 }, (_, i) => sec(i + 1, 6, i % 4 === 0 ? '## Topic ' + (i / 4 + 1) + '\\nMore' : 'text'));
const short = [sec(1, 6), sec(2, 6), sec(3, 6)];
const withQuestions = [sec(1, 6, '# Motion'), sec(2, 6), sec(3, 6), sec(4, 6, 'q', { questionsOnly: true }),
  sec(5, 6, '# Force'), sec(6, 6), sec(7, 6), sec(8, 6)];
const tooLongForTwo = Array.from({ length: 8 }, (_, i) => sec(i + 1, 7));
console.log(JSON.stringify({
  twelve: topics.planTopics(twelve).map((t) => [t.sections, t.minutes, t.title]),
  short: topics.planTopics(short).length,
  questions: topics.planTopics(withQuestions).map((t) => t.sections),
  tooLongForTwo: topics.planTopics(tooLongForTwo).length,
}));
""")
    # 72 min: three lectures of 24 min, cut where the book's topics start.
    assert out["twelve"] == [[[1, 2, 3, 4], 24, "Topic 1"], [[5, 6, 7, 8], 24, "Topic 2"], [[9, 10, 11, 12], 24, "Topic 3"]]
    assert out["short"] == 1                                    # 18 min: one lecture, as before
    # A section of only the book's questions stays with the teaching before it; the cut goes to the next heading.
    assert out["questions"] == [[1, 2, 3, 4], [5, 6, 7, 8]]
    # 56 min as two would be 31 min each with their openings and closes: three, all inside 20-30.
    assert out["tooLongForTwo"] == 3


def test_each_section_is_asked_to_open_or_close_its_lecture(lib):
    out = _node(lib, SECTIONS + """
const s = Array.from({ length: 8 }, (_, i) => sec(i + 1, 6, i % 4 === 0 ? '## Part ' + (i / 4 + 1) : 'x'));
const plan = topics.planTopics(s);
const ask = (n) => transcript.sectionRequest(s[n - 1], 8, [], undefined, topics.topicOf(plan, n));
console.log(JSON.stringify({ plan: plan.map((t) => t.sections), first: ask(5), middle: ask(6), last: ask(4), end: ask(8),
  prompt: transcript.transcriptPrompt({ sections: s, minutes: 56, language: 'auto', languageRules: '', hasReference: false,
    content: '', topics: plan }) }));
""")
    assert out["plan"] == [[1, 2, 3, 4], [5, 6, 7, 8]]
    assert "OPENS micro-lecture 2 of 2" in out["first"] and "lecture before taught" in out["first"]
    assert "OPENS" not in out["middle"] and "CLOSES" not in out["middle"]
    assert "CLOSES micro-lecture 1 of 2" in out["last"] and "next lecture covers" in out["last"]
    assert "last lecture of the series" in out["end"]
    assert "A SERIES OF 2 MICRO-LECTURES" in out["prompt"] and "Lecture 2: sections 5-8" in out["prompt"]


def test_the_finished_lecture_is_cut_where_its_topics_meet(lib):
    out = _node(lib, """
const ch = (title, section) => ({ title, section, narration: 'x', beats: [{ say: Array(300).fill('w').join(' ') }] });
const script = { title: 'Forces', intro: 'Welcome.', recap: [['last', 'one']], credits: 'c',
  chapters: [ch('A', 1), ch('B', 2), ch('C', 2), ch('D', 3), ch('E', 4), ch('F', 4)],
  topics: [{ index: 1, title: 'Newton', sections: [1, 2], recap: [['n', 'newton']] },
           { index: 2, title: 'Friction', sections: [3, 4], recap: [['f', 'friction']] }] };
const cut = parts.splitByTopics(script, 50);
console.log(JSON.stringify({ cut: cut.map((p) => ({ title: p.title, chapters: p.script.chapters.map((c) => c.title),
  card: [p.script.title, p.script.sub], intro: p.script.intro, recap: p.script.recap, topics: 'topics' in p.script,
  minutes: p.minutes })), none: parts.splitByTopics({ ...script, topics: [script.topics[0]] }, 50).length }));
""")
    one, two = out["cut"]
    assert [one["chapters"], two["chapters"]] == [["A", "B", "C"], ["D", "E", "F"]]
    assert one["title"] == "Lecture 1: Newton" and two["card"] == ["Friction", "Forces · Lecture 2 of 2"]
    assert one["intro"] == "Welcome." and two["intro"] == "Friction."
    assert one["recap"] == [["n", "newton"]] and two["recap"] == [["f", "friction"]]
    assert not one["topics"] and one["minutes"] == 25
    assert out["none"] == 0                                     # no plan of two: not cut by topic


def test_a_whole_book_is_ten_to_fifteen_micro_lectures(lib):
    """A book read without paragraph breaks (pypdf) came as one block, one section and one video of hours: it is cut
    into small sections, planned as micro-lectures of 20-30 min, never more than 15."""
    out = _node(lib, """
const sentence = 'The force on a body changes its motion, and this is what Newton saw. ';
const book = '# Laws of motion\\n' + Array.from({ length: 2400 }, () => sentence).join('');   // 31,000 words, no blank line
const sections = transcript.bookSections(book, 375);
const plan = topics.planTopics(sections);
console.log(JSON.stringify({ sections: sections.length, longest: Math.max(...sections.map((s) => s.minutes)),
  plan: plan.map((t) => t.minutes), most: topics.maxVideos(), cap: topics.maxSeriesMinutes() }));
""")
    assert out["most"] == 15 and out["cap"] == 375
    assert out["sections"] >= 40 and out["longest"] <= 12
    assert 12 <= len(out["plan"]) <= 15 and max(out["plan"]) <= 30


def _chapter(k, beats, diagram=False):
    return {"title": f"C{k}", "section": k, "beats": [
        {"say": " ".join(["word"] * 300), "do": ([{"op": "diagram", "id": f"d{k}", "kind": "flow", "nodes": []}]
                                                if diagram and b == 0 else
                                                [{"op": "reveal", "diagram": f"d{k}", "nodes": []}] if diagram and b == 1 else [])}
        for b in range(beats)]}


def test_a_long_video_is_cut_again_and_never_more_than_fifteen(lib):
    script = {"title": "Book", "chapters": [_chapter(1, 40, diagram=True), _chapter(2, 40)]}   # two chapters of ~120 min
    out = _node(lib, f"""
const script = {json.dumps(script)};
const one = {{ index: 1, of: 1, script, minutes: 240, title: 'Lecture 1: Book' }};
const bounded = parts.boundParts([one]);
const many = Array.from({{ length: 20 }}, (_, k) => ({{ index: k + 1, of: 20, script: {{ title: 'x', chapters: [] }},
  minutes: 12, title: 'L' + k }}));
const pieces = parts.expandChapters(script.chapters, 3000);
console.log(JSON.stringify({{
  bounded: bounded.map((p) => [p.minutes, p.index, p.of]),
  joined: parts.boundParts(many).length,
  // the reveal of d1 stays in the piece that draws d1
  firstPiece: pieces[0].beats.slice(0, 2).map((b) => b.do.map((o) => o.op)),
  continued: pieces.filter((c) => /continued/.test(c.title)).length,
}}));
""")
    assert len(out["bounded"]) >= 8 and max(m for m, _, _ in out["bounded"]) <= 33
    assert [i for _, i, _ in out["bounded"]] == list(range(1, len(out["bounded"]) + 1))
    assert out["joined"] == 15
    assert out["firstPiece"] == [["diagram"], ["reveal"]]
    assert out["continued"] >= 4
