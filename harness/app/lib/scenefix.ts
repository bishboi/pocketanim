// Mechanical fixes to a scene the model wrote as a whole file (model.ts, api/export).

/** Drop the broken half of a line the model rewrote in place. */
export function sanitizeScene(source: string): string {
  // A compiled lecture is the compiler's, and parses as it comes: its Manim blocks are quoted strings on one line
  // each, and cutting a line at a block's "if False else" cut its opening quote off with it.
  if (/^from\s+pocket_lecture\s+import/m.test(source)) return source;
  return source
    .split("\n")
    .map((line) => {
      const dead = line.match(/^(\s*).*\bif False else\b\s+(.*)$/);
      // Manim has rotate_vector, not a free function named rotate. Method
      // calls such as square.rotate(PI/4) are left alone.
      const fixed = (dead ? `${dead[1]}${dead[2]}` : line)
        .replace(/(?<!\.)\brotate\(/g, "rotate_vector(")
        // `UP * (t / 50)[1]` indexes the number, not the vector.
        .replace(
          /(\b(?:UP|DOWN|LEFT|RIGHT|OUT|IN|ORIGIN)\s*\*\s*)\(([^()\n]+)\)(\[\d+\])/g,
          "($1($2))$3",
        );
      return fixed;
    })
    .join("\n");
}
