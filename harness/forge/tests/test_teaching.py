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


def test_the_length_decides_examples_and_questions_not_the_topics():
    short, long = cl.teaching_plan(10, 2500), cl.teaching_plan(30, 2500)
    assert short["topics"] == long["topics"]            # the same content, the same topics
    assert long["examples"] > short["examples"]
    assert long["min_questions"] > short["min_questions"]
    assert long["min_examples"] > short["min_examples"]
    # A short video of a long chapter is not asked for more than it has room for.
    tight = cl.teaching_plan(5, 5000)
    assert tight["min_questions"] <= 2 and tight["min_examples"] <= 6


def test_the_plan_s_counts_are_checked_for_a_written_lecture():
    beats = [_beat("For example, you push a door.") if n % 3 == 0 else _beat(f"Force fact number {n}.")
             for n in range(14)]
    beats[7] = _beat("Let us check.", QUESTION)
    beats[8] = _beat("It is A.", {"op": "answer"})
    errors, _ = cl.lint(_lecture(beats), min_minutes=0.5, min_questions=3, min_examples=8)
    assert any("should ask at least 3" in e for e in errors)
    assert any("at least 8" in e for e in errors)
    errors, _ = cl.lint(_lecture(beats), min_minutes=0.5, min_questions=1, min_examples=4)
    assert not any("question" in e or "example" in e for e in errors), errors


MCQ = {"op": "question", "from_book": "q1", "text": "The SI unit of force is", "choices": ["joule", "newton", "watt", "pascal"],
       "answer": "B"}


def test_option_names_a_choice_of_the_question_up():
    asked: dict = {}
    assert "needs a question with choices" in cl._build_problem({"op": "option", "choice": "A"}, asked, {})
    assert cl._build_problem(MCQ, asked, {}) is None
    assert cl._build_problem({"op": "option", "choice": "(d)"}, asked, {}) is None
    assert cl._build_problem({"op": "option", "choice": "newton"}, asked, {}) is None
    assert "not one of the question's choices" in cl._build_problem({"op": "option", "choice": "E"}, asked, {})
    assert cl._build_problem({**MCQ, "choices": ["a", "b", "c", "d", "e"], "answer": "E"}, {}, {}) is None  # five


def test_every_book_question_is_asked_and_every_option_explained():
    book = [{"n": "q1", "text": "The SI unit of force is", "choices": ["joule", "newton", "watt", "pascal"]},
            {"n": "q2", "text": "Define momentum.", "choices": []}]
    beats = [_beat("Question one.", MCQ)] + [_beat(f"Option {x}.", {"op": "option", "choice": x}) for x in "ABC"] + \
        [_beat("So it is B.", {"op": "answer"})]
    errors, _ = cl._book_questions({**_lecture(beats), "book_questions": book})
    assert any("explains option(s) D nowhere" in e for e in errors)
    assert any("question q2" in e and "never asked" in e for e in errors)
    errors, _ = cl._book_questions({**_lecture(beats), "book_questions": book}, whole=False)
    assert not any("never asked" in e for e in errors)          # a part of a long lecture: the rest may come later
    beats.insert(4, _beat("Option D.", {"op": "option", "choice": "D"}))
    beats.append(_beat("Define momentum.", {"op": "question", "from_book": "q2", "text": "Define momentum.",
                                             "answer": "Mass times velocity."}))
    assert cl._book_questions({**_lecture(beats), "book_questions": book}) == ([], [])
    short = [_beat("Q.", {**MCQ, "choices": ["joule", "newton"]})]
    errors, _ = cl._book_questions({**_lecture(short), "book_questions": book[:1]})
    assert any("show all of them" in e for e in errors)


def test_options_compile_to_marks_on_the_card():
    script = _lecture([_beat("Question one.", MCQ)] + [_beat(f"Option {x}.", {"op": "option", "choice": x}) for x in "ABCD"]
                      + [_beat("So it is B.", {"op": "answer"})])
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert "answer=1" in source and all(f"self.option({i})" in source for i in range(4))


def test_reading_the_books_question_out_is_not_copying():
    words = "which of the following statements about the inertia of a body at rest is correct here"
    script = {**_lecture([_beat(words.capitalize() + "?") for _ in range(6)]), "source_text": f"Exercises. 1. {words}?"}
    errors, warnings = cl._plain_language(script)
    assert warnings or errors                                   # read out, and not a book question: flagged
    script["book_questions"] = [{"n": "q1", "text": words, "choices": []}]
    assert cl._plain_language(script) == ([], [])


def test_a_problem_is_solved_from_the_basics_in_many_small_steps():
    problem = {"op": "problem", "id": "p1", "title": "Problem 1", "text": "A 5 kg block is pulled with 20 N. Find a.",
               "given": ["m = 5 kg", "F = 20 N"], "find": "a"}
    quick = [_beat("Problem one.", problem), _beat("So a is four.", {"op": "work", "id": "p1", "lines": ["a = F/m = 4"]})]
    errors, _ = cl._problem_depth(_lecture(quick))
    assert len(errors) == 1 and "solved in 1 line(s)" in errors[0] and "very basics" in errors[0]
    steps = ["m = 5\\ \\text{kg}", "F = 20\\ \\text{N}", "F = m a", "a = \\frac{F}{m}", "a = \\frac{20}{5}",
             "a = 4\\ \\text{m/s}^2"]
    slow = [_beat("Problem one.", problem)] + [
        _beat(f"Step {i}.", {"op": "work", "id": "p1", "lines": [line]}) for i, line in enumerate(steps)]
    assert cl._problem_depth(_lecture(slow)) == ([], [])
    # Only a written lecture of a science is held to it (the lint runs it with min_problems).
    errors, _ = cl.lint(_lecture(quick), min_minutes=0.1, min_problems=1)
    assert any("very basics" in e for e in errors)
    errors, _ = cl.lint(_lecture(quick))
    assert not any("very basics" in e for e in errors)


def test_a_problems_diagram_is_walked_through_while_it_is_solved():
    figure = {"op": "incline", "angle": 30, "show": ["ground", "wedge", "theta", "block"]}
    problem = {"op": "problem", "id": "p1", "title": "Problem 1", "text": "A block slides down a smooth 30° incline. Find a.",
               "given": ["\\theta = 30°"], "find": "a", "figure": figure}
    work = [_beat(f"Step {i}.", {"op": "work", "id": "p1", "lines": [f"x_{i} = {i}"]}) for i in range(6)]
    errors, _ = cl._problem_depth(_lecture([_beat("Problem one.", problem)] + work))
    assert any("pointed at 0 time(s)" in e and '"diagram":"p1_figure"' in e for e in errors)
    assert any("never moves" in e for e in errors)                  # and a block on a wedge is shown sliding
    pointing = [_beat("This angle is theta.", {"op": "focus", "diagram": "p1_figure", "node": "theta"}),
                _beat("This is the block.", {"op": "focus", "diagram": "p1_figure", "node": "block"}),
                _beat("Its weight acts down.", {"op": "focus", "diagram": "p1_figure", "node": "wedge"}),
                _beat("Watch it slide down.", {"op": "motion", "diagram": "p1_figure"})]
    assert cl._problem_depth(_lecture([_beat("Problem one.", problem)] + pointing + work)) == ([], [])
    named = {**problem, "figure": {**figure, "id": "slope"}}           # a figure with its own id is pointed at by it
    pointing = [_beat(b["say"], {**b["do"][0], "diagram": "slope"}) for b in pointing]
    assert cl._problem_depth(_lecture([_beat("Problem one.", named)] + pointing + work)) == ([], [])


def test_a_diagram_that_can_move_is_set_moving_and_its_moving_parts_drawn_apart():
    incline = {"op": "incline", "id": "ramp", "angle": 30, "forces": ["mg", "N"]}
    beats = [_beat("A block on a wedge.", incline), _beat("It slides down.", {"op": "motion", "diagram": "ramp"})]
    assert not any("never moves" in e for e in cl._problem_depth(_lecture(beats))[0])
    assert any("never moves" in e for e in cl._problem_depth(_lecture(beats[:1]))[0])
    asked: dict = {}
    assert cl._build_problem(incline, asked, {}) is None
    assert cl._build_problem({"op": "motion", "diagram": "ramp"}, asked, {}) is None
    assert "for a pendulum" in cl._build_problem({"op": "motion", "diagram": "ramp", "kind": "swing"}, asked, {})
    assert "needs by" in cl._build_problem({"op": "motion", "diagram": "ramp", "kind": "move", "parts": ["block"]},
                                           asked, {})
    assert "no part" in cl._build_problem({"op": "motion", "diagram": "ramp", "kind": "pulse", "parts": ["moon"]},
                                          asked, {})
    source = cl.compile_script(json.loads(json.dumps(_lecture(beats))))
    # The block and the forces on it are drawn as parts of their own, so they move without leaving a copy.
    assert "movable=['N', 'block', 'mg']" in source and 'self.motion("ramp", {})' in source
