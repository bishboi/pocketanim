/**
 * Tools the scene agent may call.
 *
 * find_map resolves a place to its own Natural Earth outline. The agent is
 * never given a rendered frame, so it cannot revise from the picture.
 */

import { spawn } from "node:child_process";
import path from "node:path";
import { REPO, python } from "./pocketanim";

export type AgentEvent = {
  type: "message" | "input" | "delta" | "tool_call" | "tool_result" | "usage" | "done" | "error";
  role?: string;
  name?: string;
  text?: string;
  args?: string;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  source?: string;
  model?: string;
};

export const TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "find_map",
      description:
        "Look up a country, state, or province and return a Manim scene of that place only. Call it for any map. If the result is not an exact match, call it again with the exact name from the match list. A map of Rajasthan must be Rajasthan, not the world.",
      parameters: {
        type: "object",
        properties: {
          place: { type: "string", description: "The place to draw, such as Rajasthan or Japan." },
        },
        required: ["place"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "locate_on_map",
      description:
        "Return the real longitude and latitude of one feature inside a region from Natural Earth. Call it for every city, river, desert, or range you mark. Plot only the coordinates it returns, through the scene's project(). If it does not find the feature, leave it off the map. Never invent a coordinate.",
      parameters: {
        type: "object",
        properties: {
          region: { type: "string", description: "The region already drawn, such as Rajasthan." },
          feature: { type: "string", description: "The thing to mark, such as Jaipur or the Thar Desert." },
        },
        required: ["region", "feature"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "write_scene",
      description:
        "Write the opening of the Manim file only: title, first picture, and one or two voice lines. source must be valid Python starting with `from manim import *`. Do not put the whole lecture here. Add later stretches with edit_scene, about two minutes of speech per call.",
      parameters: {
        type: "object",
        properties: {
          source: { type: "string", description: "The complete Python file." },
        },
        required: ["source"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "edit_scene",
      description:
        "Replace one exact span of the current Manim file, the way a code editor applies a search-and-replace. old_string must appear exactly once, including indentation and blank lines. new_string is what replaces it. For a lecture, new_string should add several beats, about two minutes of speech, not a single line. Each new beat FadeOuts the previous beat first, so titles and sentences never share the frame. If the result says the span was missing or matched more than once, copy a longer or shorter span from the file and call again. Do not reprint the file in your reply.",
      parameters: {
        type: "object",
        properties: {
          old_string: { type: "string", description: "The exact text to replace. Copy it from the current file." },
          new_string: { type: "string", description: "The text to put in its place. May be empty to delete the span." },
        },
        required: ["old_string", "new_string"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "molecule_guide",
      description:
        "Return Sphere and Line3D coordinates for a molecule. Call when the scene is a chemical structure. Call again if you need a different molecule.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Molecule name or formula." },
        },
        required: ["subject"],
        additionalProperties: false,
      },
    },
  },
];

const MOLECULES: Record<string, { atoms: string; bonds: string; label: string }> = {
  water: {
    atoms: "[(0.0, 0.0, 0.0, 'O'), (-0.76, 0.59, 0.0, 'H'), (0.76, 0.59, 0.0, 'H')]",
    bonds: "[(0, 1), (0, 2)]",
    label: "Water",
  },
  methane: {
    atoms:
      "[(0.0, 0.0, 0.0, 'C'), (0.63, 0.63, 0.63, 'H'), (-0.63, -0.63, 0.63, 'H'), (-0.63, 0.63, -0.63, 'H'), (0.63, -0.63, -0.63, 'H')]",
    bonds: "[(0, 1), (0, 2), (0, 3), (0, 4)]",
    label: "Methane",
  },
  co2: {
    atoms: "[(-1.16, 0.0, 0.0, 'O'), (0.0, 0.0, 0.0, 'C'), (1.16, 0.0, 0.0, 'O')]",
    bonds: "[(0, 1), (1, 2)]",
    label: "Carbon dioxide",
  },
};

export function moleculeGuide(subject: string): string {
  const key = subject.toLowerCase();
  const data = /water|h2o|h₂o/.test(key)
    ? MOLECULES.water
    : /methane|ch4|ch₄/.test(key)
      ? MOLECULES.methane
      : /carbon dioxide|co2|co₂/.test(key)
        ? MOLECULES.co2
        : { ...MOLECULES.water, label: subject.slice(0, 40) || "Molecule" };
  return `Use these coordinates for ${data.label} on a ThreeDScene. Sphere resolution=(8, 8).

ATOMS = ${data.atoms}
BONDS = ${data.bonds}
COLORS = {"C": "#BBBBBB", "N": "#58C4DD", "O": "#FC6255", "H": "#FFFFFF"}
RADII = {"C": 0.32, "N": 0.30, "O": 0.30, "H": 0.18}

class GeneratedScene(ThreeDScene):
    def construct(self):
        self.set_camera_orientation(phi=70 * DEGREES, theta=-50 * DEGREES, zoom=0.9)
        atoms = VGroup()
        for x, y, z, el in ATOMS:
            atoms.add(Sphere(radius=RADII[el], resolution=(8, 8)).set_color(COLORS[el]).move_to([x, y, z]))
        bonds = VGroup()
        for i, j in BONDS:
            a = np.array(ATOMS[i][:3], dtype=float)
            b = np.array(ATOMS[j][:3], dtype=float)
            bonds.add(Line3D(start=a, end=b, thickness=0.04, color="#888888"))
        title = Text(${JSON.stringify(data.label)}, font_size=28, color="#F4F1EA")
        title.to_edge(UP, buff=0.45)
        self.add_fixed_in_frame_mobjects(title)
        self.play(FadeIn(title), run_time=0.4)
        self.play(FadeIn(bonds), run_time=0.8)
        self.play(*[GrowFromCenter(atom) for atom in atoms], run_time=1.2)
        self.begin_ambient_camera_rotation(rate=0.15)
        self.wait(2)
        self.stop_ambient_camera_rotation()
`;
}

function runPython(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), args, { cwd: REPO });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk.toString()));
    child.stderr.on("data", (chunk) => (stderr += chunk.toString()));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr }));
  });
}

export async function findMap(place: string): Promise<string> {
  const script = path.join(REPO, "harness", "scripts", "map_region.py");
  const { stdout, stderr, code } = await runPython([script, place]);
  const line = stdout.trim().split("\n").pop() || "";
  let data: {
    found?: boolean;
    name?: string;
    parent?: string;
    dataset?: string;
    matches?: { name: string; parent: string; dataset: string }[];
    scene?: string;
    error?: string;
  } = {};
  try {
    data = JSON.parse(line);
  } catch {
    return stderr.trim().slice(-500) || `map lookup failed (exit ${code})`;
  }
  if (data.scene) {
    const where = data.parent ? `${data.name}, ${data.parent}` : data.name;
    return `Exact match: ${where} (${data.dataset}). Draw this place, not the world. Keep the geometry filter. build_region() returns (group, project). Unpack both: region, project = build_region(). Every mark must call that project(lon, lat). Do not invent coordinates. For every mark, call locate_on_map and plot only the lon/lat it returns.\n\n${data.scene}`;
  }
  const matches = (data.matches ?? [])
    .map((hit) => `${hit.name}${hit.parent ? ` (${hit.parent})` : ""}`)
    .join(", ");
  if (matches) {
    return `No exact match for "${place}". Closest: ${matches}. Call find_map again with the exact name.`;
  }
  return data.error || `No Natural Earth region named "${place}". Try the country or the state name.`;
}

export async function locateOnMap(region: string, feature: string): Promise<string> {
  const script = path.join(REPO, "harness", "scripts", "locate_feature.py");
  const { stdout, stderr, code } = await runPython([script, region, feature]);
  const line = stdout.trim().split("\n").pop() || "";
  let data: { found?: boolean; name?: string; lon?: number; lat?: number; path?: number[][]; kind?: string; error?: string } = {};
  try {
    data = JSON.parse(line);
  } catch {
    return stderr.trim().slice(-500) || `locate failed (exit ${code})`;
  }
  if (!data.found) return data.error || `No mapped feature named "${feature}" inside ${region}. Do not mark it.`;
  const pathText = (data.path ?? []).map(([lon, lat]) => `(${lon}, ${lat})`).join(", ");
  return [
    `Exact feature: ${data.name} (${data.kind}) inside ${region}.`,
    `Point: project(${data.lon}, ${data.lat}).`,
    data.path && data.path.length > 1 ? `Shape, in order, each pair passed through project(lon, lat): ${pathText}.` : "",
    "Use these numbers only. Do not replace them.",
  ].filter(Boolean).join("\n");
}

function preview(text: string): string {
  const lines = text.split("\n");
  if (lines.length <= 14) return text;
  return `${lines.slice(0, 14).join("\n")}\n… (${lines.length} lines)`;
}

/** Apply write_scene or edit_scene. Other tool names return null. */
export function applySceneTool(
  source: string,
  name: string,
  args: { source?: string; old_string?: string; new_string?: string },
): { source: string; message: string } | null {
  if (name === "write_scene") {
    const next = String(args.source ?? "");
    if (!/^from manim import\b/m.test(next)) {
      return { source, message: "Rejected. source must be Python that contains `from manim import *`." };
    }
    const file = next.endsWith("\n") ? next : `${next}\n`;
    return { source: file, message: `Wrote the scene (${file.split("\n").length} lines). Use edit_scene for any further change.` };
  }
  if (name !== "edit_scene") return null;
  const oldString = String(args.old_string ?? "");
  const newString = String(args.new_string ?? "");
  if (!source.trim()) return { source, message: "No scene yet. Call write_scene with the full file first." };
  if (!oldString) return { source, message: "old_string is empty. Pass the exact lines to replace." };
  if (oldString === newString) return { source, message: "old_string and new_string are the same. Nothing changed." };
  const count = source.split(oldString).length - 1;
  if (count === 0) {
    return { source, message: "old_string was not found. Copy it exactly from the current scene, including indentation." };
  }
  if (count > 1) {
    return { source, message: `old_string matched ${count} times. Include more surrounding lines so it matches once.` };
  }
  const replaced = source.replace(oldString, newString);
  const file = replaced.endsWith("\n") ? replaced : `${replaced}\n`;
  return {
    source: file,
    message: `Edited the scene.\n\nold:\n${preview(oldString)}\n\nnew:\n${preview(newString)}`,
  };
}

export async function runTool(name: string, args: { place?: string; subject?: string; region?: string; feature?: string }): Promise<string> {
  if (name === "find_map") return findMap(String(args.place ?? args.subject ?? "").slice(0, 80));
  if (name === "locate_on_map") return locateOnMap(String(args.region ?? args.place ?? "").slice(0, 80), String(args.feature ?? args.subject ?? "").slice(0, 80));
  if (name === "molecule_guide") return moleculeGuide(String(args.subject ?? ""));
  return `Unknown tool ${name}.`;
}
