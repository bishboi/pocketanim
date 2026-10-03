/**
 * How a problem in mathematics, physics or chemistry is solved in a lecture: from the very basics, every step
 * said and shown, for a student meeting the idea for the first time. Used by the transcript (lib/transcript.ts),
 * which says every word, and by the video's beat script (lib/lecture.ts), which shows each step as it is said;
 * the compiler refuses a problem with too few steps of working (compile_lecture._problem_depth).
 */

/** The fewest lines of working a problem's solution shows (the compiler's MIN_WORK_LINES). */
export const MIN_WORK_LINES = 6;

export const SOLVING_STEPS = [
  "SOLVE EVERY PROBLEM FROM THE VERY BASICS, as if the student has never solved one like it. No step is",
  "obvious; nothing is skipped; never \"simplifying, we get\" or \"clearly\". In this order:",
  "  1. READ the question slowly, twice. Then go through it phrase by phrase and say what each phrase means in",
  "     the subject: \"smooth surface\" means no friction, \"starts from rest\" means u = 0, \"uniform\" means it",
  "     does not change, \"STP\" means 273 K and 1 atm, \"real roots\" means the discriminant is not negative.",
  "  2. PICTURE it: draw the situation (the figure, the forces one by one, the axes, the triangle, the",
  "     molecule), saying what each part is and why it is there.",
  "  3. GIVEN and ASKED: write each given quantity with its symbol and unit; convert every unit to SI one at a",
  "     time and say how (\"1 km = 1000 m, so 2 km = 2000 m\"); say what is asked and its unit.",
  "  4. THE IDEA: which concept or law solves it and WHY it applies here. Say the law in plain words first,",
  "     then write its formula, then say what every symbol in it means. Recall where it comes from if it is",
  "     short (\"F = m a because...\").",
  "  5. THE PLAN, before any calculation: \"first we find ..., then with it ..., and that gives ...\".",
  "  6. WORK, one small step per line, and say why each step is allowed: one operation at a time (\"divide",
  "     both sides by 2\", \"take the square root of both sides\", \"cross-multiply\"); put each number in by",
  "     itself, with its unit; do the arithmetic out loud and in pieces (\"5 into 9.8: 5 nines are 45, 5",
  "     point-eights are 4, so 49\"); keep the signs and say what each sign means (left, down, loss of energy).",
  "  7. CHECK: the unit of the answer; whether its size makes sense; put it back in, or check it another way.",
  "  8. ANSWER, said twice and boxed, in a full sentence with its unit. Then the common mistakes on this kind",
  "     of problem and why they are wrong, and the method in three short steps to remember.",
];
