/**
 * How a problem in mathematics, physics or chemistry is solved in a lecture: from the very basics, every step
 * said and shown, for a student meeting the idea for the first time. Used by the transcript (lib/transcript.ts),
 * which says every word, and by the video's beat script (lib/lecture.ts), which shows each step as it is said;
 * the compiler refuses a problem with too few steps of working (compile_lecture._problem_depth).
 */

/** The fewest lines of working a problem's solution shows (the compiler's MIN_WORK_LINES). */
export const MIN_WORK_LINES = 6;
/** The fewest times a problem's figure is pointed at while it is solved (the compiler's MIN_FIGURE_STEPS). */
export const MIN_FIGURE_STEPS = 3;

export const SOLVING_STEPS = [
  "SOLVE EVERY PROBLEM FROM THE VERY BASICS, as if the student has never solved one like it. No step is",
  "obvious; nothing is skipped; never \"simplifying, we get\" or \"clearly\". In this order:",
  "  1. READ the question slowly, twice. Then go through it phrase by phrase and say what each phrase means in",
  "     the subject: \"smooth surface\" means no friction, \"starts from rest\" means u = 0, \"uniform\" means it",
  "     does not change, \"STP\" means 273 K and 1 atm, \"real roots\" means the discriminant is not negative.",
  "  2. WHAT IT ASKS, in your own simple words: what we must find, what that quantity means, its unit, and",
  "     what a sensible answer would roughly look like. Name the kind of question it is (\"यह Newton's second",
  "     law का question है\") and the chapter idea it tests.",
  "  3. THE DIAGRAM, when the question has one (or draw one when it does not): go through it part by part",
  "     before solving. What it shows (a block on an incline, a circuit, a triangle, a graph); what every",
  "     label, letter, arrow, angle, length and mark on it stands for, physically (\"यह arrow F है, block पर",
  "     दाईं ओर लगाया गया force\"); which given values sit only in the diagram, not the text; what it shows",
  "     without saying (a right angle, a smooth surface, a common side, a string that stays taut); and what",
  "     we must add to it (the forces, the axes, a construction line). Point at each part on the board as",
  "     you name it.",
  "  4. GIVEN: write each given quantity, from the text and from the diagram, with its symbol and unit;",
  "     convert every unit to SI one at a time and say how (\"1 km = 1000 m, so 2 km = 2000 m\").",
  "  5. THE APPROACH, and WHY this way: which concept or law solves it and why it fits THIS situation (what",
  "     in the question or the diagram tells us so); if there is another way, say it and why this one is",
  "     simpler. Say the law in plain words first, then its formula, then every symbol in it. Recall where it",
  "     comes from if it is short (\"F = m a because...\").",
  "  6. THE PLAN, before any calculation: \"first we find ..., then with it ..., and that gives ...\".",
  "  7. WORK, one small step per line, and say why each step is allowed: one operation at a time (\"divide",
  "     both sides by 2\", \"take the square root of both sides\", \"cross-multiply\"); put each number in by",
  "     itself, with its unit; do the arithmetic out loud and in pieces (\"5 into 9.8: 5 nines are 45, 5",
  "     point-eights are 4, so 49\"); keep the signs and say what each sign means (left, down, loss of energy).",
  "     Whenever a step uses the diagram, go back to it and point (\"figure में देखो, यह angle theta है, इसलिए",
  "     component m g sin theta होगा\"): which part, and why it gives this step.",
  "  8. CHECK: the unit of the answer; whether its size makes sense; put it back in, or check it another way.",
  "  9. ANSWER, said twice and boxed, in a full sentence with its unit. Then the common mistakes on this kind",
  "     of problem and why they are wrong, and the method in three short steps to remember.",
];
