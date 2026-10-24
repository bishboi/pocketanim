/**
 * The current engine's word timing (voice first): a call of its own, after the scene writer, that puts every picture
 * and every part of one on the word of its line it comes on with. It is shown each beat's line as the voice says it
 * (its words by number with the second each is said) and the things the beat's operations put on the screen, and
 * answers each thing's word number; the app writes it as the thing's "on" ("w7": compile_lecture.anchors makes it
 * the line's own words from that word).
 */

import { part, type Prompt } from "./parts";

export type TimingSlot = { id: number; what: string; parent?: number; writer?: string };
export type TimingBeat = { beat: number; seconds: number; pause: number; words: { w: string; t: number }[]; slots: TimingSlot[] };

const RULES = `You time a lecture video's pictures to its narration. The narration is already spoken: for each beat you are
given its line as the voice says it, every word numbered (w0 is the first) with the second it is said from the line's
start, and the things the beat puts on the screen (slots: a picture, a card, a diagram, and the parts inside one: a
node, a label, a step, an event, a point). Give every slot the number of the word it comes on with.

HOW TO CHOOSE THE WORD
- A thing comes on as the voice NAMES it: the first word of the words that name it (the noun, the name, the number,
  the date), never a small word before it ("the", "a", "of", "and", "is", "है", "का", "की", "के", "में", "ने", "तो").
  "...and the GRANARY fed the city": a node "Granary" is the word "granary", not "the".
- A name may be said in another spelling or script, or a part may be said in other words (a node "Craftsmen" said as
  "कारीगर", a label "Third law" said as "reaction"): the word where the line says that.
- A thing the line does not name: the word where the idea it shows begins to be said. A title, a heading, a frame or
  a background picture that the rest is drawn on: with its first part, or word 0 when it should be up as the line
  begins.
- A part never comes before the picture it is in: its word is the same as its picture's or later. A picture's parts
  come in the order the line says them.
- Each moment should be seen: parts said in one breath may share a word; otherwise keep them at least about 0.6 s
  apart (the times tell you). Do not put everything on word 0, and do not leave a thing for the line's last word
  unless that is where it is said.
- The scene writer may have named words for a slot ("writer: ..."): a hint; choose the exact word yourself.

Answer with time_words: every slot by its id, each with one word number of its own beat's line.`;

export const WORD_TIMING_TOOL = {
  type: "function" as const,
  function: {
    name: "time_words",
    description: "Every slot's word: the number of the word of its beat's line it comes on with.",
    parameters: {
      type: "object",
      properties: {
        anchors: {
          type: "array",
          items: {
            type: "object",
            properties: {
              slot: { type: "integer", description: "The slot's id, as given." },
              word: { type: "integer", description: "The word's number in its beat's line (w0 = 0)." },
            },
            required: ["slot", "word"],
            additionalProperties: false,
          },
        },
      },
      required: ["anchors"],
      additionalProperties: false,
    },
  },
};

/** One beat as the call reads it: its line's words with their times, then its slots. */
function beatText(b: TimingBeat): string {
  const words = b.words.map((w, i) => `w${i} ${w.w} ${w.t.toFixed(1)}`).join(" | ");
  const depth = (s: TimingSlot): number => (s.parent === undefined ? 0 : 1 + depth(b.slots.find((x) => x.id === s.parent) ?? { id: -1, what: "" }));
  const slots = b.slots.map((s) => `  s${s.id} ${"  ".repeat(depth(s))}${s.parent !== undefined ? `(in s${s.parent}) ` : ""}${s.what}` +
    (s.writer ? ` [writer: ${JSON.stringify(s.writer)}]` : "")).join("\n");
  return `BEAT ${b.beat} (${b.seconds} s, then ${b.pause} s quiet)\nWords: ${words}\nSlots:\n${slots}`;
}

export function wordTimingPrompt(o: { lecture: number; chapter: number; title?: string; beats: TimingBeat[] }): Prompt {
  return {
    system: [part("word-timing", "How to time the pictures to the words", "rules", RULES)],
    user: [
      part("beats", `Lecture ${o.lecture}, chapter ${o.chapter}${o.title ? ` (${o.title})` : ""}: each beat's words and slots`, "items",
        o.beats.map(beatText).join("\n\n")),
      part("ask", "Request", "ask", "Give every slot above its word (time_words)."),
    ],
  };
}
