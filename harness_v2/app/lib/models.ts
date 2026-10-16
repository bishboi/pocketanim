/**
 * Every model v2 uses, by its role, and where each comes from: the environment (harness_v2/app/.env.local, or v1's
 * harness/app/.env.local for what that one does not set: next.config.ts), else a default. The first variable set
 * wins: v2's own name, then v1's name for the same job, so a v1 .env.local works as it is.
 *
 * The page starts from these and can change a run's own; nothing has to be typed.
 */

export type ModelRole = "planner" | "writer" | "figure" | "triage" | "triageChat" | "image" | "svg" | "manim" | "map" | "script" | "scenes";

export type RoleInfo = {
  role: ModelRole;
  label: string;
  /** What it does, and in which step. */
  what: string;
  /** text: writes text or code; vision: reads images, writes text; image: makes images; decision: answers typed
   * questions with probabilities (OpenRouter's Decisions API), no text. */
  kind: "text" | "vision" | "image" | "decision";
  /** The variables read, in order. */
  env: string[];
  fallback: string;
  /** Built in v2 yet, or set for a step to come. */
  used: boolean;
};

export const ROLES: RoleInfo[] = [
  { role: "planner", label: "Planner", kind: "text", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Divides the book into lectures and maps their goals (transcript, step 3).",
    env: ["V2_PLANNER_MODEL", "OPENROUTER_MODEL"] },
  { role: "writer", label: "Writer", kind: "text", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Writes each lecture's transcript and its patches (transcript, step 4).",
    env: ["V2_WRITER_MODEL", "OPENROUTER_TRANSCRIPT_MODEL", "OPENROUTER_MODEL"] },
  { role: "figure", label: "Figures", kind: "vision", used: true, fallback: "google/gemini-2.5-flash",
    what: "Describes each figure from its picture (transcript, step 2).",
    env: ["V2_FIGURE_MODEL", "OPENROUTER_FIGURE_MODEL", "OPENROUTER_SVG_MODEL"] },
  { role: "triage", label: "Triage", kind: "decision", used: true, fallback: "typesafe/jev-1.14",
    what: "Decides how each figure is shown in the video: a choice among the ways offered, with probabilities (figure triage).",
    env: ["V2_TRIAGE_MODEL"] },
  { role: "triageChat", label: "Triage (chat)", kind: "vision", used: true, fallback: "google/gemini-2.5-flash",
    what: "The figure triage asked of a chat model instead, with its instruction and reason: for unsure figures, or a whole run.",
    env: ["V2_TRIAGE_CHAT_MODEL", "V2_FIGURE_MODEL", "OPENROUTER_FIGURE_MODEL"] },
  { role: "image", label: "Image (redraw)", kind: "image", used: true, fallback: "google/gemini-2.5-flash-image",
    what: "Makes images: redraws the figures triaged Exact or Styled (generation).",
    env: ["V2_IMAGE_MODEL", "PANIM_DIAGRAM_MODEL", "PANIM_IMAGE_MODEL"] },
  { role: "svg", label: "SVG", kind: "vision", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Draws the figures triaged SVG: reads the figure and writes its SVG, in one call (generation).",
    env: ["V2_SVG_MODEL", "OPENROUTER_MODEL"] },
  { role: "manim", label: "Manim", kind: "vision", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Draws the figures triaged Manim: reads the figure and writes its Manim code, in one call; rendered here (generation).",
    env: ["V2_MANIM_MODEL", "PANIM_MANIM_MODEL", "OPENROUTER_MODEL"] },
  { role: "script", label: "Script", kind: "text", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Cuts each lecture's transcript into chapters and beats, every sentence in one beat, and places its figures (script).",
    env: ["V2_SCRIPT_MODEL", "OPENROUTER_MODEL"] },
  { role: "scenes", label: "Scenes", kind: "text", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Writes each beat's visuals as the lecture engine's operations (maps, diagrams, pictures, timelines, Manim...), mends what the engine refuses (scenes).",
    env: ["V2_SCENES_MODEL", "OPENROUTER_MODEL"] },
  { role: "map", label: "Map", kind: "vision", used: true, fallback: "anthropic/claude-sonnet-4.5",
    what: "Draws the figures triaged Map: reads the book's map and writes its map script, in one call; v2's engine renders it (generation).",
    env: ["V2_MAP_MODEL", "PANIM_MAP_MODEL", "PANIM_MANIM_MODEL", "OPENROUTER_MODEL"] },
];

export type ResolvedModel = RoleInfo & { model: string; source: string };

/** Each role's model now, and the variable it came from ("default" when none is set). */
export function resolveModels(): Record<ModelRole, ResolvedModel> {
  const out = {} as Record<ModelRole, ResolvedModel>;
  for (const r of ROLES) {
    const name = r.env.find((k) => process.env[k]?.trim());
    out[r.role] = { ...r, model: name ? process.env[name]!.trim() : r.fallback, source: name ?? "default" };
  }
  return out;
}

export function modelFor(role: ModelRole): string {
  return resolveModels()[role].model;
}
