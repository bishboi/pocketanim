/**
 * The script: a lecture's transcript cut into chapters and beats. A chapter is a topic (a few minutes), with a title
 * card and one stage (a map, or a board); a beat is one or two of the transcript's numbered sentences and what is on
 * screen while they are said. Every sentence is in exactly one beat, in order, so the narration is the transcript
 * word for word. The beats name their sentences by number, never copy them (v1's "lines", lib/lines.ts).
 *
 * This first cut builds the structure and places the lecture's figures (those triaged and generated); what each beat
 * shows besides a figure is said in a short note, built into operations by a step to come.
 */

import { part, type Part } from "./parts";

const ROLE = "You cut ONE lecture's transcript into the script of its video: chapters, and beats inside them. You do not " +
  "change or add a word of the transcript: you group its numbered sentences and say what is on screen while each group is said.";

const UNITS = [
  "A CHAPTER is a topic of the lecture, a few minutes long. It begins with a title card: its title (a few words) and",
  '  one short line said on the card ("Chapter two. The first cities."). It has one stage: "map": true when the chapter',
  "  is taught on a map (a Map figure is in it, or the places are the point), else a board for pictures and diagrams.",
  "  Start a new chapter where the topic changes (the lecture's goals are a good guide); 3 to 8 chapters a lecture.",
  "A BEAT is the smallest unit of the video: \"lines\", the numbers of 1 or 2 consecutive sentences said together (3",
  "  at most, for a short run that is one thought), and what is on screen while they are said: \"show\", one short",
  "  note (a few words: \"the Indus valley on the map\", \"key term: surplus\", \"the figure, the granary labelled\"), and",
  '  "figure" when a figure of the lecture is shown on this beat (its id, from the list). A new beat wherever what is',
  "  on screen should change.",
].join("\n");

const RULES = [
  "RULES (code checks them, and mends what it can):",
  "- Every sentence, 1 to the last, is in exactly ONE beat, in order: none left out, none twice, none out of order.",
  "- Beats inside a chapter follow each other; chapters follow each other: the sentence numbers only go up.",
  "- Each figure of the lecture is shown ONCE, on the beat whose sentences talk about it (the sentences given beside",
  "  it are a guide). A figure not listed is never named.",
  '- A Map figure goes in a chapter with "map": true.',
].join("\n");

export const SCRIPT_TOOL = {
  type: "function" as const,
  function: {
    name: "write_script",
    description: "Save the lecture's script: its chapters, each with its beats and their sentence numbers.",
    parameters: {
      type: "object",
      properties: {
        chapters: {
          type: "array",
          items: {
            type: "object",
            properties: {
              title: { type: "string" },
              narration: { type: "string", description: "The one line said on the chapter's title card." },
              map: { type: "boolean", description: "Taught on a map." },
              beats: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    lines: { type: "array", items: { type: "integer" }, description: "The numbers of the sentences said on this beat." },
                    show: { type: "string", description: "What is on screen, in a few words." },
                    figure: { type: "string", description: "The id of the figure shown on this beat, if any." },
                  },
                  required: ["lines", "show"],
                  additionalProperties: false,
                },
              },
            },
            required: ["title", "narration", "map", "beats"],
            additionalProperties: false,
          },
        },
      },
      required: ["chapters"],
      additionalProperties: false,
    },
  },
};

export type FigureForScript = { id: string; way: string; caption: string; ready: boolean; lines: number[] };

export function scriptPrompt(x: { lecture: { n: number; title: string; why: string }; lines: string[]; goals: { id: string; goal: string; lines: number[] }[];
  figures: FigureForScript[]; retry?: string[] }): { system: Part[]; user: Part[] } {
  return {
    system: [
      part("role", "Role", "rules", ROLE),
      part("units", "Chapters and beats", "rules", UNITS),
      part("rules", "Rules", "rules", RULES),
    ],
    user: [
      part("lecture", "The lecture", "context", `Lecture ${x.lecture.n}: ${x.lecture.title}${x.lecture.why ? `\n${x.lecture.why}` : ""}`),
      part("goals", "Its goals (and the sentences that teach each)", "goals", x.goals.map((g) => `${g.id}: ${g.goal}${g.lines.length ? ` [sentences ${g.lines.join(", ")}]` : ""}`)),
      part("figures", `Its figures (${x.figures.length})`, "items", x.figures.length ? x.figures.map((f) =>
        `${f.id}: ${f.way}${f.ready ? "" : " (not made yet)"} — ${f.caption || "(no caption)"}${f.lines.length ? ` [taught in sentences ${f.lines.join(", ")}]` : ""}`)
        : "This lecture has no figures: every beat's show is what the board or map shows."),
      part("transcript", `The transcript, numbered (${x.lines.length} sentences)`, "book", x.lines.map((l, i) => `${i + 1}| ${l}`)),
      ...(x.retry?.length ? [part("retry", "What your last script broke", "retry", ["Your last script broke these rules; write it again with them kept:",
        ...x.retry.map((r) => `- ${r}`)])] : []),
      part("ask", "Request", "ask", `Write the script of lecture ${x.lecture.n} (write_script): every sentence 1 to ${x.lines.length} in one beat, in order.`),
    ],
  };
}
