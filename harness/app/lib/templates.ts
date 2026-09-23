/**
 * A template is a *kind of video*, not a layout: it fixes the visual language
 * a scene is generated in -- palette, pacing, how a beat is introduced -- and
 * names the Manim the model is expected to reach for.
 *
 * Deliberately data, not prompt prose. The same fields feed the prompt and the
 * UI, so what the user picked and what the model was told cannot drift apart.
 */

export type Template = {
  id: string;
  name: string;
  summary: string;
  /** Hex colours the scene should stay within. */
  palette: string[];
  /** Background, as Manim's config.background_color. */
  background: string;
  /** Appended to the system prompt: the visual contract for this kind. */
  direction: string;
  /** Extra Manim the model may use. Kept explicit so maps and molecules are
   *  opt-in per template rather than always-on noise in the prompt. */
  extraImports?: string[];
};

export const TEMPLATES: Template[] = [
  {
    id: "explainer",
    name: "Explainer",
    summary: "Title, then one idea at a time. Calm pacing, lots of space.",
    palette: ["#58C4DD", "#F7D96F", "#83C167", "#FFFFFF"],
    background: "#000000",
    direction: [
      "One idea on screen at a time. Introduce with Write or Create, then hold.",
      "Prefer a title that shrinks to the top edge, then body beats below it.",
      "Use Text for prose and MathTex only for real mathematics.",
    ].join(" "),
  },
  {
    id: "derivation",
    name: "Derivation",
    summary: "Equations that transform into each other, step by step.",
    palette: ["#FFFFFF", "#58C4DD", "#F7D96F"],
    background: "#000000",
    direction: [
      "Each step is a MathTex that becomes the next via TransformMatchingTex.",
      "Keep one equation centred; do not stack every step on screen.",
    ].join(" "),
  },
  {
    id: "map",
    name: "Map",
    summary: "Geography with cartopy coastlines, annotated.",
    palette: ["#83C167", "#58C4DD", "#FFFFFF"],
    background: "#000000",
    direction: [
      "Draw the coastline first, then annotate places with Dot and Text.",
      "Keep the projection fixed; move attention with Create and FadeIn.",
    ].join(" "),
    extraImports: ["import cartopy.feature as cfeature", "import cartopy.crs as ccrs"],
  },
  {
    id: "molecule",
    name: "Molecule",
    summary: "3D structures: spheres and bonds, with a slow camera orbit.",
    palette: ["#BBBBBB", "#58C4DD", "#FC6255", "#FFFFFF"],
    background: "#000000",
    direction: [
      "Use ThreeDScene. Build atoms as Sphere and bonds as Line3D.",
      "Grow the structure in, then orbit with begin_ambient_camera_rotation.",
    ].join(" "),
  },
];

export function templateById(id: string): Template {
  const found = TEMPLATES.find((t) => t.id === id);
  if (!found) throw new Error(`unknown template: ${id}`);
  return found;
}
