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
    # 56 min as two would be 31 min each with their openings and closes: three.
    assert out["tooLongForTwo"] == 3


def test_sections_are_written_as_one_lecture_and_videos_are_decided_after(lib):
    """The writer is not told where videos start and end before writing: they are decided from what it writes."""
    out = _node(lib, SECTIONS + """
const s = Array.from({ length: 8 }, (_, i) => sec(i + 1, 6, i % 4 === 0 ? '## Part ' + (i / 4 + 1) : 'x'));
const ask = (n) => transcript.sectionRequest(s[n - 1], 8, []);
console.log(JSON.stringify({ middle: ask(5), end: ask(8),
  prompt: transcript.transcriptPrompt({ sections: s, minutes: 56, language: 'auto', languageRules: '', hasReference: false,
    content: '' }) }));
""")
    assert "OPENS" not in out["middle"] and "CLOSES" not in out["middle"] and "video" not in out["middle"]
    assert "the lecture ends with it" in out["end"]
    assert "decided from your" in out["prompt"] and "written transcript, always between sections" in out["prompt"]
    assert "one continuous lecture" in out["prompt"]


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
    assert one["title"] == "Lecture 1: Newton" and two["card"] == ["Friction", "Forces · Lecture 2"]
    assert one["intro"] == "Welcome." and two["intro"] == "Friction."
    assert one["recap"] == [["n", "newton"]] and two["recap"] == [["f", "friction"]]
    assert not one["topics"] and one["minutes"] == 25
    assert out["none"] == 0                                     # no plan of two: not cut by topic


@pytest.mark.parametrize("minutes", [150, 375, 900])
def test_a_whole_book_is_as_many_micro_lectures_as_it_needs(lib, minutes):
    """A book read without paragraph breaks (pypdf) came as one block, one section and one video of hours: it is cut
    into small sections, planned as micro-lectures of 20-30 min, as many as its length makes (no set number)."""
    out = _node(lib, """
const sentence = 'The force on a body changes its motion, and this is what Newton saw. ';
const book = '# Laws of motion\\n' + Array.from({ length: 2400 }, () => sentence).join('');   // 31,000 words, no blank line
const sections = transcript.bookSections(book, MINUTES);
const plan = topics.planTopics(sections);
console.log(JSON.stringify({ sections: sections.length, longest: Math.max(...sections.map((s) => s.minutes)),
  plan: plan.map((t) => t.minutes) }));
""".replace("MINUTES", str(minutes)))
    assert out["longest"] <= 12
    assert max(out["plan"]) + 3 <= 30                     # with its opening and close, never past 30 min
    assert minutes / 30 <= len(out["plan"]) <= minutes / 20 + 1


def _chapter(k, beats, diagram=False):
    return {"title": f"C{k}", "section": k, "beats": [
        {"say": " ".join(["word"] * 300), "do": ([{"op": "diagram", "id": f"d{k}", "kind": "flow", "nodes": []}]
                                                if diagram and b == 0 else
                                                [{"op": "reveal", "diagram": f"d{k}", "nodes": []}] if diagram and b == 1 else [])}
        for b in range(beats)]}


def test_a_long_chapter_is_cut_only_where_nothing_points_back(lib):
    """(For a lecture edited by hand, without a transcript.) A chapter is cut only at a beat where nothing after the
    cut points back at a picture drawn before it."""
    script = {"title": "Book", "chapters": [_chapter(1, 40, diagram=True), _chapter(2, 40)]}
    out = _node(lib, f"""
const script = {json.dumps(script)};
const pieces = parts.expandChapters(script.chapters, 3000);
console.log(JSON.stringify({{
  firstPiece: pieces[0].beats.slice(0, 2).map((b) => b.do.map((o) => o.op)),
  continued: pieces.filter((c) => /continued/.test(c.title)).length,
}}));
""")
    assert out["firstPiece"] == [["diagram"], ["reveal"]]
    assert out["continued"] >= 4
    assert "boundParts" not in (APP / "lib" / "parts.ts").read_text()      # a made video is never cut again


def test_videos_end_where_the_written_transcript_reaches_25_to_30_minutes(lib):
    """The videos are decided from the transcript as it is written: each ends between sections, where the next
    would take it past 30 minutes or, once it has 25, where the book starts a new heading; the rest, once all is
    written, as evenly as it goes."""
    out = _node(lib, SECTIONS + """
const s = (mins, heads = []) => mins.map((m, i) => sec(i + 1, m, heads.includes(i + 1) ? '## Part ' + (i + 1) : 'x'));
console.log(JSON.stringify({
  waiting: topics.nextVideos(s([6, 6]), true),                        // 15 min: cannot tell yet
  full: topics.nextVideos(s([8, 8, 8, 8]), true),                     // the 4th would pass 30
  heading: topics.nextVideos(s([7, 8, 8, 4, 4], [5]), true),          // 26 + a heading: a natural break
  big: topics.nextVideos(s([40, 5]), true),                           // one long section is a video of its own
  rest: topics.nextVideos(s([9, 9, 9, 9, 9, 9]), false),              // all written: even
  short: topics.nextVideos(s([5, 5]), false),
}));
""")
    assert out["waiting"] == []
    assert out["full"] == [3]
    assert out["heading"] == [4]
    assert out["big"] == [1]
    assert out["rest"] == [3, 3]
    assert out["short"] == [2]


def test_the_words_between_two_videos_are_the_writers(lib):
    out = _node(lib, """
console.log(JSON.stringify(transcript.transitionRequest(
  { index: 2, minutes: 27.4, titles: ['Inertia', 'Momentum'], tail: 'and that is why the ball keeps rolling.' },
  { title: 'Friction', head: 'Now think of a ball rolling on grass.' })));
""")
    assert "CLOSE video 2" in out and "OPEN video 3" in out and "keeps rolling" in out and "rolling on grass" in out
    assert "as you judge best for the learning" in out and "write_transition" in out


@pytest.mark.parametrize("mcqs", [0, 100, 200])
def test_a_book_full_of_exercises_still_makes_videos_of_20_to_30_minutes(lib, mcqs):
    """A book with 100 multiple-choice questions came out as fifteen videos of an hour: its questions take their
    time as more videos, never as longer ones."""
    got = _node(lib, f"""
const para = () => Array.from({{length: 120}}, (_, i) => 'idea' + (i % 50)).join(' ') + '.';
let md = '';
for (let c = 1; c <= 10; c++) {{
  md += `# Chapter ${{c}}\\n\\n` + Array.from({{length: 33}}, para).join('\\n\\n') + '\\n\\n## Exercises\\n\\n';
  for (let q = 1; q <= {mcqs} / 10; q++)
    md += `${{q}}. In chapter ${{c}}, which statement ${{q}} is true?\\n(a) one (b) two (c) three (d) four\\n\\n`;
}}
const words = md.split(/\s+/).filter(Boolean).length;
const sections = transcript.bookSections(md, Math.round(words / 100));
const plan = topics.planTopics(sections);
console.log(JSON.stringify({{total: sections.reduce((n, s) => n + s.minutes, 0), count: plan.length,
  longest: Math.max(...plan.map((t) => t.minutes)) + topics.OPEN_CLOSE_MINUTES}}));
""")
    assert got["longest"] <= 30, got
    assert got["count"] >= got["total"] / 30, got
