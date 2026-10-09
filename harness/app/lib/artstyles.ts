/**
 * Art styles: how a lecture's pictures are drawn (harness/lecture/artstyle.py), chosen beside the template.
 * The template is the whole film's frame (background, fonts, panel, captions); the art style is the hand that
 * draws the sims, diagrams, charts, SVG drawings and maps on it. "auto" draws with the template's own.
 */

export type ArtStyle = {
  id: string;
  name: string;
  summary: string;
};

export const ART_STYLES: ArtStyle[] = [
  { id: "auto", name: "Template's own", summary: "The art the template draws with." },
  { id: "clean", name: "Clean", summary: "Flat colours and crisp lines." },
  { id: "detailed", name: "Detailed", summary: "Shaded shapes with highlights and rims; a relief map." },
  { id: "blueprint", name: "Blueprint", summary: "Fine technical line drawings, faint fills, construction marks." },
  { id: "chalk", name: "Chalk", summary: "Soft pastel chalk lines with a hand-drawn wobble and dust." },
  { id: "sketch", name: "Sketch", summary: "Pencil outlines with cross-hatched shading." },
  { id: "neon", name: "Neon", summary: "Glowing lines of light over dark, translucent shapes." },
  { id: "watercolour", name: "Watercolour", summary: "Layered translucent washes and thin ink lines." },
];

/** The art each template draws with when the art style is left to it (artstyle.TEMPLATE_ART). */
export const TEMPLATE_ART: Record<string, string> = {
  atlas: "detailed", vox: "clean", cardboard: "watercolour", whiteboard: "sketch", blueprint: "blueprint",
  chalkboard: "chalk", parchment: "sketch", lab: "detailed", cosmos: "neon",
};

/** A known art style id, or "auto". */
export function artStyle(value: unknown): string {
  const id = typeof value === "string" ? value.trim().toLowerCase().replace("watercolor", "watercolour") : "";
  return ART_STYLES.some((a) => a.id === id) ? id : "auto";
}

/** What "auto" means for a template's style ("auto" itself when the style is picked from the subject later). */
export function artFor(art: string, templateStyle?: string): string {
  if (art !== "auto") return art;
  return (templateStyle && TEMPLATE_ART[templateStyle]) || "auto";
}

/** A miniature of each art style for the picker: a circle and a bar drawn that way, in a 64×36 viewBox. */
export function artPreview(id: string, ink: string, accent: string): string {
  const shapes: Record<string, string> = {
    clean: `<circle cx="20" cy="18" r="10" fill="${accent}"/><rect x="38" y="10" width="14" height="18" fill="${ink}" opacity=".8"/>`,
    detailed:
      `<circle cx="20" cy="18" r="10" fill="${accent}" stroke="#000" stroke-opacity=".45" stroke-width="1.2"/>` +
      `<circle cx="22" cy="20" r="8" fill="#000" opacity=".18"/><circle cx="16.5" cy="14.5" r="4" fill="#fff" opacity=".45"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="${ink}" opacity=".8" stroke="#000" stroke-opacity=".45"/>` +
      `<rect x="40" y="11" width="3" height="16" fill="#fff" opacity=".35"/>`,
    blueprint:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".12" stroke="${accent}" stroke-width="1"/>` +
      `<path d="M8 18H32M20 6V30" stroke="${ink}" stroke-width=".5" opacity=".6"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="1"/>`,
    chalk:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".5" stroke="${accent}" stroke-width="1.6"/>` +
      `<path d="M13 23L25 11M16 26L28 14M11 19L21 9" stroke="#fff" stroke-width=".7" opacity=".35"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="${ink}" fill-opacity=".45" stroke="${ink}" stroke-width="1.5"/>`,
    sketch:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".3" stroke="${ink}" stroke-width="1.2"/>` +
      `<path d="M12 22L24 10M14 26L28 12M18 27L29 16" stroke="${ink}" stroke-width=".6" opacity=".6"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="1.2"/>` +
      `<path d="M38 18L46 10M38 26L52 12M44 28L52 20" stroke="${ink}" stroke-width=".6" opacity=".6"/>`,
    neon:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".2" stroke="${accent}" stroke-width="5" stroke-opacity=".18"/>` +
      `<circle cx="20" cy="18" r="10" fill="none" stroke="${accent}" stroke-width="1.6"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="5" stroke-opacity=".18"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="1.4"/>`,
    watercolour:
      `<circle cx="20" cy="18" r="10" fill="${accent}" opacity=".45"/><circle cx="21" cy="17" r="11" fill="${accent}" opacity=".18"/>` +
      `<circle cx="19" cy="19" r="9" fill="${accent}" opacity=".18"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="${ink}" opacity=".45"/><rect x="37" y="11" width="15" height="18" fill="${ink}" opacity=".15"/>`,
  };
  return shapes[id] ?? shapes.clean;
}
