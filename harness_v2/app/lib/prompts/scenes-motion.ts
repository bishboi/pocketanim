/**
 * The engine's looks, transitions and idle motions (engine/MOTION_ENGINE.md §6), as the Scenes tab offers them. What
 * the scene writer is told of the templates is in prompts/scenes-templates.ts.
 */

export const MOTION_LOOKS = ["paper", "newsroom", "chalk", "data", "studio", "sketch", "archive", "neon", "brush", "collage",
  "textbook", "chalkcolour", "isometric", "drafting"] as const;
/** How one picture gives way to the next (engine/motion_looks.py TRANSITIONS). */
export const MOTION_TRANSITIONS = ["slide", "push", "wipe", "dissolve", "zoom", "page", "cut", "whip", "stack", "flash", "turn",
  "match"] as const;
/** How what is up keeps moving while the voice goes on (engine/motion_looks.py IDLES). */
export const MOTION_IDLES = ["float", "drift", "boil", "breathe", "sway", "parallax", "flicker", "none"] as const;
