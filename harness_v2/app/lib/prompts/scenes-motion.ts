/**
 * The motion engine's looks (beta: engine/MOTION_ENGINE.md), as the Scenes tab offers them. What its scene writer is
 * told is in prompts/scenes-beta.ts.
 */

export const MOTION_LOOKS = ["paper", "newsroom", "chalk", "data", "studio", "sketch", "archive", "neon", "brush", "collage",
  "textbook", "chalkcolour", "isometric", "drafting"] as const;
/** How one picture gives way to the next (engine/motion_looks.py TRANSITIONS). */
export const MOTION_TRANSITIONS = ["slide", "push", "wipe", "dissolve", "zoom", "page", "cut", "whip", "stack", "flash", "turn",
  "match"] as const;
/** How what is up keeps moving while the voice goes on (engine/motion_looks.py IDLES). */
export const MOTION_IDLES = ["float", "drift", "boil", "breathe", "sway", "parallax", "flicker", "none"] as const;
