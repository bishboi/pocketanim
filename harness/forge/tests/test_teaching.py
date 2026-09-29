"""Teaching pace: questions for the class, time to think, pauses, and lectures that teach rather than recite."""

from __future__ import annotations

import json

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402


def _beat(say: str, *ops, **extra) -> dict:
    return {"say": say, "do": list(ops), **extra}


def _lecture(beats: list) -> dict:
    return {"title": "Forces", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
            "chapters": [{"title": "Force", "narration": "Chapter one.", "beats": beats}]}


QUESTION = {"op": "question", "text": "Which of these is a force?", "choices": ["Kicking a ball", "Sleeping"],
            "answer": "A", "think": 4}


def test_answer_index_takes_a_letter_a_number_or_the_text():
    op = {"choices": ["Push", "Pull", "Sleep"]}
    assert cl._answer_index({**op, "answer": "B"}) == 1
    assert cl._answer_index({**op, "answer": "(c)"}) == 2
    assert cl._answer_index({**op, "answer": 1}) == 0
    assert cl._answer_index({**op, "answer": "pull"}) == 1
    assert cl._answer_index({**op, "answer": "D"}) is None
    assert cl._answer_index({**op, "answer": "Jump"}) is None


def test_question_problems():
    assert cl._build_problem({"op": "question", "text": ""}, {}, {})
    assert cl._build_problem({"op": "question", "text": "Why?", "choices": ["only one"]}, {}, {})
    assert "not one of its choices" in cl._build_problem({**QUESTION, "answer": "Z"}, {}, {})
    assert cl._build_problem({"op": "answer"}, {}, {})           # no question asked before it
    asked: dict = {}
    assert cl._build_problem(QUESTION, asked, {}) is None
    assert cl._build_problem({"op": "answer"}, asked, {}) is None
    assert cl._build_problem({"op": "question", "text": "Why does a ball stop?", "answer": "Friction"}, {}, {}) is None


def test_compile_asks_waits_answers_and_pauses():
    script = _lecture([
        _beat("A force is a push or a pull.", paragraph=True),
        _beat("For example, you push a door open.", pause=2),
        _beat("Let us check.", QUESTION),
        _beat("It is A: kicking is a push.", {"op": "answer"}),
    ])
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert "self.question(\"Which of these is a force?\", ['Kicking a ball', 'Sleeping'], answer=0)" in source
    lines = source.splitlines()
    asked = next(i for i, line in enumerate(lines) if "self.question(" in line)
    assert lines[asked + 1].strip() == "self.think(4)"
    assert "self.answer()" in source
    assert 'pad=PARAGRAPH_PAD + 2' in source            # a paragraph's end, and the beat's own pause
    assert source.count("pad=PARAGRAPH_PAD") >= 2       # paragraph ends: before the question, at the chapter's end


def test_questions_and_pauses_add_to_the_running_time():
    plain = _lecture([_beat("A force is a push or a pull.") for _ in range(4)])
    slower = _lecture([_beat("A force is a push or a pull.", pause=3)] + [_beat("A force is a push or a pull.")] * 2
                      + [_beat("Let us check.", QUESTION)])
    assert cl.estimate_minutes(slower) > cl.estimate_minutes(plain)


def test_a_written_lecture_must_ask_questions_and_give_examples():
    beats = [_beat(f"Force is a push or a pull, fact number {n}.") for n in range(14)]
    errors, warnings = cl.lint(_lecture(beats), min_minutes=0.5)
    assert any("asks the class no questions" in e for e in errors)
    assert any("give an example" in e for e in errors)
    # Without a length to reach (an offline or hand-made script) the same checks are only advice.
    errors, warnings = cl.lint(_lecture(beats))
    assert not any("questions" in e or "example" in e for e in errors)
    assert any("asks the class no questions" in w for w in warnings)

    taught = [_beat("For example, you push a door.") if n % 4 == 0 else _beat(f"Force fact number {n}.")
              for n in range(12)]
    taught[6] = _beat("Let us check.", QUESTION)
    taught[7] = _beat("It is A.", {"op": "answer"})
    errors, _ = cl.lint(_lecture(taught), min_minutes=0.5)
    assert not any("questions" in e or "example" in e for e in errors), errors
