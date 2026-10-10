"""The faster lecture: beats name the transcript's numbered lines instead of copying them (app/lib/lines.ts), a
refused transcript section is mended rather than rewritten (transcript.ts), and a micro-lecture written early is
cut the same way the final cut does (parts.ts topicPart)."""

from __future__ import annotations

import json
import os
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
    built = subprocess.run([str(tsc), "lib/lines.ts", "lib/parts.ts", "lib/transcript.ts", "--outDir", str(out),
                            "--module", "commonjs", "--target", "es2022", "--skipLibCheck", "--esModuleInterop"],
                           cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    return out


def _node(lib: Path, body: str):
    script = (f"const lines = require({json.dumps(str(lib / 'lines.js'))});"
              f"const parts = require({json.dumps(str(lib / 'parts.js'))});"
              f"const transcript = require({json.dumps(str(lib / 'transcript.js'))});" + body)
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60,
                          env={"PATH": os.environ["PATH"]})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


SECTION = """
const ws = { n: 3, title: 'Forces', text: 'A force is a push. A force is a pull.\\nFriction slows things! Why does it? ' +
  'Because surfaces rub. Ice has little friction. Rubber has a lot. That is all.' };
"""


def test_beats_name_lines_and_the_words_are_filled_in(lib):
    out = _node(lib, SECTION + """
const script = { chapters: [
  { title: 'A', section: 3, beats: [{ lines: [1, 2], do: [{ op: 'fact', text: 'push or pull' }] }, { lines: '3-4', do: [] }] },
  { title: 'B', section: 3, beats: [{ lines: [5], do: [] }, { lines: [8, 99], do: [] }] },
] };
const report = lines.fillLines(script, [ws], { complete: [3] });
console.log(JSON.stringify({ numbered: lines.numberedSection(ws).split('\\n'), report,
  says: script.chapters.flatMap((c) => c.beats.map((b) => b.say)), left: script.chapters.flatMap((c) => c.beats.map((b) => 'lines' in b)) }));
""")
    assert out["numbered"][:3] == ["1| A force is a push.", "2| A force is a pull.", "3| Friction slows things!"]
    assert out["says"][0] == "A force is a push. A force is a pull."
    assert out["says"][1] == "Friction slows things! Why does it?"
    # Lines 6 and 7, named by no beat, are said on a beat of their own after line 5, in order.
    assert out["says"][2:] == ["Because surfaces rub.", "Ice has little friction. Rubber has a lot.", "That is all."]
    assert out["report"]["added"] == 2 and not any(out["left"])
    assert out["report"]["problems"] == ["chapter 2 beat 2: line 99 not in section 3, which has lines 1-8"]


def test_a_thin_chapter_is_merged_and_a_copied_beat_still_counts(lib):
    out = _node(lib, SECTION + """
const script = { chapters: [
  { title: 'A', section: 3, beats: [1, 2, 3, 4].map((k) => ({ lines: [k], do: [] })) },
  { title: 'B', section: 3, beats: [{ say: 'Because surfaces rub.', do: [] }] },
  { title: 'C', section: 3, beats: [6, 7, 8].map((k) => ({ lines: [k], do: [] })) },
] };
const report = lines.fillLines(script, [ws], { complete: [3], minBeats: 3 });
console.log(JSON.stringify({ report, titles: script.chapters.map((c) => c.title), counts: script.chapters.map((c) => c.beats.length),
  unsaid: transcript.transcriptProblem(script, [ws], [3]) }));
""")
    assert out["report"]["added"] == 0                 # the beat that wrote line 5 out says it
    assert out["titles"] == ["A", "C"] and out["counts"] == [5, 3]
    assert out["unsaid"] is None


def test_a_refused_section_is_mended_not_rewritten(lib):
    out = _node(lib, """
const sec = { n: 2, parts: [], minutes: 5, words: 500, source: '## Motion\\nSpeed is distance over time.', book: true };
const text = 'Speed tells how fast. '.repeat(40);
console.log(JSON.stringify({
  missing: transcript.repairable('Section 2 leaves out parts of its source: "speed".'),
  empty: transcript.repairable('Section 2 came back empty.'),
  ask: transcript.repairRequest(sec, 6, text, 'Section 2 leaves out parts of its source: "speed".'),
  rewrote: transcript.rewroteWhole(text + ' More.', text),
  added: transcript.rewroteWhole('And here is a new example about a car.', text),
  clean: transcript.cleanSection('## Heading\\n- Speed is fast. [pause]\\n\\n\\n\\n2. Then slow.'),
}));
""")
    assert out["missing"] and not out["empty"]
    assert "Do NOT write the section again" in out["ask"] and "teach what is missing" in out["ask"]
    assert "Speed is distance over time." in out["ask"]       # the section's own source comes with it
    assert out["rewrote"] and not out["added"]
    assert out["clean"] == "Speed is fast.\n\nThen slow."


def test_an_early_part_is_cut_as_the_final_cut_does(lib):
    out = _node(lib, """
const ch = (n, k) => ({ title: 'c' + n + k, section: n, beats: [{ say: 'Words of ' + n + '.', do: [] }] });
const head = { title: 'Forces', intro: 'Forces today.', chapters: [] };
const script = { ...head, chapters: [ch(1, 1), ch(2, 1), ch(3, 1), ch(4, 1)], recap: [['last', 'x']],
  topics: [{ index: 1, title: 'Push', sections: [1, 2], recap: [['push', 'y']] },
           { index: 2, title: 'Pull', sections: [3, 4], recap: null }] };
const final = parts.splitByTopics(script, 50);
const early = [0, 1].map((k) => parts.topicPart({ ...head, chapters: script.chapters.filter((c) => script.topics[k].sections.includes(c.section)) },
  script.topics[k], k, 2, 'Forces', k === 1 ? script.recap : null));
const sorted = (o) => Array.isArray(o) ? o.map(sorted) : o && typeof o === 'object'
  ? Object.fromEntries(Object.keys(o).sort().map((k) => [k, sorted(o[k])])) : o;
const canon = (o) => JSON.stringify(sorted(o));
console.log(JSON.stringify({ same: final.map((p, k) => canon(p.script) === canon(early[k].script)),
  titles: final.map((p) => p.title), sub: final[1].script.sub }));
""")
    assert out["same"] == [True, True]
    assert out["titles"] == ["Lecture 1: Push", "Lecture 2: Pull"] and out["sub"] == "Forces · Lecture 2 of 2"


def test_a_section_request_carries_its_own_source_and_the_prompt_only_an_outline(lib):
    out = _node(lib, """
const secs = [1, 2].map((n) => ({ n, parts: [], minutes: 5, words: 500, source: '## Heading ' + n + '\\nBODY-' + n, book: true }));
const prompt = transcript.transcriptPrompt({ sections: secs, minutes: 10, language: 'en', languageRules: '', content: 'Forces', topics: [] });
const ask = transcript.sectionRequest(secs[1], 2, [], undefined, undefined);
const video = transcript.sectionForVideo({ n: 2, title: 'Two', text: 'One line. Two lines.' });
console.log(JSON.stringify({ prompt, ask, video }));
""")
    assert "BODY-1" not in out["prompt"] and "BODY-2" not in out["prompt"]
    assert "Heading 1" in out["prompt"] and "Heading 2" in out["prompt"]
    assert "BODY-2" in out["ask"] and "BODY-1" not in out["ask"]
    assert "1| One line.\n2| Two lines." in out["video"] and '"lines"' in out["video"]
