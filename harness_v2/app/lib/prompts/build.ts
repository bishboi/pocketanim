/**
 * The prompt of the transcription, as named parts (parts.ts): one call per lecture, in order, that writes the lecture
 * as its script: the lecture (its title), its CHAPTERS (a title card, a stage, the book's blocks each teaches from) and
 * its BEATS (the sentences said, what is on screen, the book's figures shown). The transcript is the beats' words.
 *
 * There is no planner: each call is given the whole book (each block marked taught or not yet), every lecture
 * before it whole, and how long a lecture is meant to be, and writes the NEXT lecture: where it ends is its own
 * choice, by what is learned. Chapters may teach from the same blocks; a figure may be on several beats. There is no
 * length ceiling: everything given is taught.
 */

import { blocksJson, bookWords, kindOf, type Block } from "../source/blocks";
import { classVoicePlanned, languagePrompt, type Language } from "./texts";
import { part, type Part, type Prompt } from "./parts";

/** How a great teacher tells it: v1's rules. */
const TELLING = [
  "HOW A GREAT TEACHER TELLS IT:",
  "  - The lecture is ONE story with ONE question the student wants answered, asked near the start and answered by",
  "    the end. Every part moves it forward.",
  "  - Make them guess before you tell: ask, let them think, then answer. In fresh words each time, never a stock",
  "    pause phrase.",
  "  - Concrete before abstract: a scene, an object, a number made tangible (\"as heavy as 40 school bags\"), then the",
  "    term. Everyday life in India is the best source: trains, cricket, the monsoon, the kitchen, the market.",
  "  - Name the wrong idea students usually hold, let them hold it for a moment, then show why it fails.",
  "  - Vary the rhythm: a short line after a long explanation. Not every sentence is a fact. Never read out a list.",
  "  - A figure, a map or a table is shown at its moment: say what it shows and why it matters there, and point at the",
  "    one or two things to look at. The book's questions are asked right after the idea they test, as a check-in,",
  "    then answered in full, every choice of a multiple-choice question explained.",
  "  - The story never changes the facts: no invented events, people, quotes, numbers or dates presented as history or",
  "    science. A scene you imagine is said as imagined (\"imagine...\", \"सोचो...\").",
  "  - When everything is taught, stop: no padding, no extra self-checks or study tips, no summary of what was just said",
  "    except the short close of the lecture.",
];

/** v2's own: how a good teacher in India actually talks in class, so the script sounds spoken, not written. */
function speechPrompt(language: Language): string[] {
  const hinglish = language === "hinglish" || language === "auto";
  const english = language === "english" || language === "auto";
  return [
    "SOUND LIKE A REAL TEACHER IN AN INDIAN CLASSROOM, talking, not reading. Write the words exactly as such a teacher",
    "would say them out loud to the class in front of them:",
    "  - SPOKEN SENTENCES: short, simple, the way people talk. Start a line with \"So\", \"Now\", \"See\", \"Okay\",",
    "    \"अच्छा\", \"तो\", \"अब\" when a teacher would. A fragment is fine (\"Simple.\", \"बस इतना ही।\", \"Why? Because...\").",
    "    One idea a sentence; a long explanation broken into small steps said one after another.",
    "  - TALK TO THEM: \"you\" (in Hindi, one of आप or तुम for the whole lecture, never mixed). Ask, and answer:",
    "    \"Now tell me, what will happen?\", \"क्या लगता है आपको?\". A question tag where it is natural (\"isn't it?\",",
    "    \"right?\", \"है ना?\", \"ठीक है?\"), not on every line.",
    "  - HOW TEACHERS STRESS A POINT: say the key line, then say it again more simply (\"Force is a push or a pull.",
    "    Just that, a push or a pull.\"); flag it (\"Now listen carefully.\", \"ये point ध्यान से सुनना।\", \"Very",
    "    important, remember this one.\"); warn where students slip (\"Many students make a mistake here.\", \"यहाँ",
    "    पे ज़्यादातर बच्चे गड़बड़ करते हैं।\"). Each of these a few times a lecture at most, at the points that deserve it.",
    "  - EXAMPLES FROM THEIR OWN LIFE in India, the first thing a teacher reaches for: the local train and the auto,",
    "    cricket, chai and the pressure cooker, the monsoon and the ceiling fan, Diwali, the kirana shop, the school",
    "    bus, mobile recharge, the village well and the city flyover. Money in rupees; big numbers in lakh and crore",
    "    when a teacher would say them so.",
    "  - WARMTH AND A LITTLE HUMOUR: a light joke, a smile in the voice (\"Don't worry, it sounds scary, it isn't.\",",
    "    \"घबराओ मत, ये बहुत simple है।\"), praise for a good guess (\"Correct! Well done.\").",
    "  - NEVER TEXTBOOK OR ESSAY LANGUAGE: not \"In this chapter we will learn\", \"Let us now discuss\", \"It is to be",
    "    noted that\", \"Furthermore\", \"Thus we can conclude\", \"Hence\" at a sentence's start; not presenter clichés",
    "    (\"Let's dive in\", \"fascinating journey\", \"delve\", \"unlock the secrets\"). And not the book's sentences",
    "    read out: say the same thing the way you would explain it to a student sitting in front of you.",
    ...(hinglish ? [
      "  - HINGLISH AS IT IS SPOKEN: real classroom mixing, Hindi carrying the sentence and the everyday English words",
      "    Indians say anyway in English (simple, basically, actually, important, point, example, doubt, chapter, topic,",
      "    tension, problem). Natural connectors: मतलब, यानी, देखो, समझो, एक काम करते हैं, अब यहाँ twist है, अब",
      "    बताओ, समझ आया? Easy everyday Hindi, never bookish Hindi (not \"अतः\", \"तत्पश्चात\", \"उपरोक्त\").",
    ] : []),
    ...(language === "hindi" ? [
      "  - HINDI AS IT IS SPOKEN in class: easy everyday Hindi, never bookish (not \"अतः\", \"तत्पश्चात\", \"उपरोक्त\").",
      "    Natural connectors: मतलब, यानी, देखो, समझो, अब बताओ, समझ आया?",
    ] : []),
    ...(english ? [
      "  - INDIAN ENGLISH AS A GOOD TEACHER SPEAKS IT: correct and simple, with its natural turns (\"See, ...\",",
      "    \"Now one small thing.\", \"Okay, now tell me.\", \"isn't it?\", \"na?\" at most rarely), never American or",
      "    British presenter talk.",
    ] : []),
    "  The facts stay the book's: the warmth is in how it is said, never in invented facts.",
  ];
}

/** v2's own examples: how such a teacher sounds (for how it moves and sounds, never to copy). */
function speechExamples(language: Language): string[] {
  const out = ["WHAT IT SOUNDS LIKE (for how a teacher talks and moves through an idea; never copy the words or topics):"];
  if (language !== "hindi" && language !== "hinglish") {
    out.push(
      "  English: \"Okay, a small question first. You are standing in a crowded local train, holding nothing. The train",
      "  suddenly starts. What happens to you? You fall backwards, isn't it? Now why? The train moved. Your feet moved",
      "  with it. But the rest of your body? It wanted to stay right where it was. That's it. That is inertia. Your",
      "  body likes to keep doing whatever it was already doing. Standing still? It wants to stay still. Moving? It",
      "  wants to keep moving. Now listen carefully, because many students get this wrong in the exam. Inertia is not",
      "  a force. Nobody is pushing you back. You are simply being left behind.\"",
    );
  }
  if (language === "hindi") {
    out.push(
      "  Hindi: \"अच्छा, एक छोटा सा सवाल। घर में प्रेशर कुकर तो देखा ही है ना? सीटी बजती है, भाप बाहर आती है। अब बताओ,",
      "  कुकर में खाना जल्दी क्यों पकता है? सोचो ज़रा। ज़्यादातर लोग कहेंगे, 'आग तेज़ है इसलिए।' नहीं! आग तो वही है।",
      "  असली बात है दबाव। दबाव बढ़ता है, तो पानी सौ डिग्री पे नहीं, उससे ज़्यादा पे उबलता है। और ज़्यादा गरम पानी,",
      "  मतलब खाना जल्दी तैयार। बस, इतनी सी बात है।\"",
    );
  } else if (language !== "english") {
    out.push(
      "  Hinglish: \"अच्छा, एक काम करते हैं। घर में pressure cooker तो देखा ही है ना? सीटी बजती है, steam बाहर आती है।",
      "  अब बताओ, cooker में खाना जल्दी क्यों पकता है? सोचो ज़रा। ज़्यादातर लोग कहेंगे, 'आग तेज़ है इसलिए।' नहीं! आग",
      "  तो वही है। असली बात है pressure। Pressure बढ़ता है, तो पानी का boiling point भी ऊपर चला जाता है। मतलब पानी",
      "  सौ degree पे नहीं, उससे ज़्यादा पे उबलता है। और ज़्यादा गरम पानी, मतलब खाना जल्दी तैयार। Simple! ये point",
      "  ध्यान से याद रखना: pressure बढ़ा, तो boiling point बढ़ा।\"",
    );
  }
  out.push("");
  return out;
}

/** How the lecture is built: lecture, chapters, beats, each a unit of the video. */
const STRUCTURE = [
  "HOW THE LECTURE IS BUILT (it is the script of the video: a later step draws each beat):",
  "  - THE LECTURE: one video a student sits down to learn: one topic and everything it needs, with a beginning, a",
  "    middle and an end. Start where the book is not taught yet (the blocks marked NOT TAUGHT, in the book's order),",
  "    and end where a topic is complete and the next begins: never cut an idea, an explanation, a worked example or a",
  "    figure away from the text that explains it. Its length is the topics', about the length given below.",
  "  - CHAPTERS: the lecture's topics in order, a few minutes each (usually 3 to 8 a lecture). Each has a title (a",
  "    few words), the one short line said on its title card (\"Chapter two. The first cities.\"), whether some of",
  "    its beats point at places on a map (\"map\": true; every chapter is on the board, the map coming in only for",
  "    those beats), and its CONTENT: the ids of the",
  "    book's blocks it teaches from. Content is not shared out: two chapters (of this lecture or another) may teach",
  "    from the same block, when both need it; and every block this lecture teaches is in some chapter's content.",
  "  - BEATS: a chapter is its beats in order, each the smallest unit of the video: \"say\", 1 or 2 sentences said",
  "    together (3 at most, for one short thought), and \"show\", a short note of what is on screen while they are",
  "    said (\"the Indus valley on the map\", \"key term: surplus\", \"the granary figure, its walls labelled\"). A new",
  "    beat wherever what is on screen should change. \"figures\": the ids of the book's figures shown on the beat, when",
  "    one is: a figure may be shown on several beats (built up, pointed at again, compared), and a beat may show two.",
  "  - THE TRANSCRIPT IS THE BEATS' WORDS, in order: everything the student hears is in a beat's say, nothing else.",
].join("\n");

export function lectureSystem(language: Language, subject?: string): Part[] {
  return [
    part("role", "Role", "rules", [
      "You write a video lecture series from a book, one lecture at a time. Each lecture you write is its complete",
      "spoken transcript, every word the teacher says, already built as the video's script: chapters and beats.",
    ]),
    part("matters", "What matters", "rules", [
      "WHAT MATTERS above all:",
      "  1. LEAVE NOTHING OUT. Everything in the book's blocks this lecture takes on is taught: every heading's idea, every",
      "     definition and bold term, every fact, number and example, every box, every figure, every book question. Take",
      "     the time each needs; nothing about the length is counted.",
      "  2. THE QUALITY OF THE LEARNING: the student truly understands and remembers.",
      "  3. TOLD AS A STORY, never a list of facts read out.",
      "  4. ONE SERIES. The lectures before this one are given to you whole: the student has watched them. Never teach",
      "     again what they taught; recall it in a sentence when this lecture needs it, and build on it. Open by",
      "     picking up from where the last lecture ended (a short look back), and end with a short close of this",
      "     lecture and what comes next.",
    ]),
    part("structure", "Lecture, chapters, beats", "rules", STRUCTURE),
    part("telling", "How to tell it", "rules", TELLING),
    part("voice", "Voice", "rules", classVoicePlanned(language)),
    part("speech", "How a teacher in India talks", "rules", speechPrompt(language)),
    part("examples", "Narration examples", "rules", speechExamples(language)),
    part("use", "How the transcript is used", "rules", [
      "HOW THE TRANSCRIPT IS USED (facts, not rules of style):",
      "  - A voice speaks each beat's say, so write only the words said: no headings, bullet lists, [brackets] or stage",
      "    directions in it, and say formulas and symbols the way they are spoken.",
      "  - Teach the subject only. The book's furniture is not content: never mention its QR codes, logos, page",
      "    numbers, page layout, reprint or copyright notes; list such blocks in skipped.",
      "  - Answer with Datalab's block ids (\"/page/3/Text/7\") for content and figures, never the book's text.",
      ...(subject ? [`  - The subject is ${subject}.`] : []),
    ]),
    part("language", "Language", "language", languagePrompt(language)),
  ].filter((p) => p.text);
}

export function writePrompt(o: {
  n: number; blocks: Block[]; taught: Map<string, number[]>; skipped: Set<string>; lectureMinutes: number; system: Part[];
  previous: { n: number; title: string; chapters: { title: string; says: string[] }[] }[]; note?: string;
}): Prompt {
  const left = o.blocks.filter((b) => !o.taught.has(b.id) && !o.skipped.has(b.id) && kindOf(b.type) !== "furniture");
  const words = bookWords(o.blocks);
  const leftWords = bookWords(left);
  const mark = (b: Block) => {
    const json = JSON.parse(blocksJson([b])) as Record<string, unknown>;
    const at = o.taught.get(b.id);
    return JSON.stringify({ ...json, taught: at ? `in lecture${at.length > 1 ? "s" : ""} ${at.join(", ")}` : o.skipped.has(b.id) ? "skipped" : "NOT TAUGHT" });
  };
  const user: Part[] = [
    part("length", "How long a lecture is", "context", [
      `HOW LONG A LECTURE IS: each lecture is one video of about ${o.lectureMinutes} minutes, watched on its own. A book is`,
      `taught at roughly its own length, about 100 words of the book a minute, so a lecture usually takes on about`,
      `${o.lectureMinutes * 100} words of the book; let the topics decide, not the count. The book has ${words} words; ${leftWords} of them`,
      `(${left.length} blocks) are not taught yet.`,
    ]),
    part("previous", "Lectures already given", "context", o.previous.length
      ? ["THE LECTURES ALREADY GIVEN, whole (the student has watched them: never teach their content again; recall it in",
        "a sentence where this lecture needs it):",
        ...o.previous.map((p) => `\n=== LECTURE ${p.n}: ${p.title} ===\n${p.chapters.map((c) => `-- ${c.title} --\n${c.says.join(" ")}`).join("\n")}`)]
      : "This is the first lecture of the series: nothing has been taught yet."),
    part("book", "The book as JSON", "book", [
      "THE BOOK as Datalab read it: every block in page order, one JSON object a line (Datalab's id, block_type and",
      "html; a figure has figure_shows, what it shows; taught: in which lecture it was taught, or NOT TAUGHT):",
      o.blocks.map(mark).join("\n"),
    ]),
    part("ask", "Request", "ask", `Write lecture ${o.n} now (write_lecture): the next lecture of the series, from where the book is not ` +
      "taught yet, as its chapters and beats, leaving nothing in what it takes on out. done: true when, after it, nothing of the " +
      "book is left to teach."),
  ];
  if (o.note) user.push(part("retry", "Why the last try was sent back", "retry", `Your last try was sent back: ${o.note}`));
  return { system: o.system, user };
}

export const WRITE_TOOL = {
  type: "function" as const,
  function: {
    name: "write_lecture",
    description: "Save one lecture as its script: its chapters, each with its content (the book's block ids) and its beats " +
      "(what is said, what is on screen, the figures shown). The beats' words are the whole transcript.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "The lecture's title." },
        about: { type: "string", description: "What it teaches, in one line." },
        chapters: {
          type: "array",
          items: {
            type: "object",
            properties: {
              title: { type: "string" },
              narration: { type: "string", description: "The one line said on the chapter's title card." },
              map: { type: "boolean", description: "Some of its beats point at places on the map (the chapter itself is on the board)." },
              content: { type: "array", items: { type: "string" }, description: "The ids of the book's blocks it teaches from (others may share them)." },
              beats: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    say: { type: "string", description: "1-2 sentences said on this beat (3 at most): only the words spoken." },
                    show: { type: "string", description: "What is on screen, in a few words." },
                    figures: { type: "array", items: { type: "string" }, description: "The ids of the book's figures shown on this beat, if any." },
                  },
                  required: ["say", "show"],
                  additionalProperties: false,
                },
              },
            },
            required: ["title", "narration", "map", "content", "beats"],
            additionalProperties: false,
          },
        },
        skipped: {
          type: "array",
          items: { type: "object", properties: { block: { type: "string" }, reason: { type: "string" } }, required: ["block", "reason"], additionalProperties: false },
          description: "Blocks of the book that are furniture, never taught (a QR code, a page header).",
        },
        done: { type: "boolean", description: "True when, after this lecture, nothing of the book is left to teach." },
      },
      required: ["title", "chapters", "done"],
      additionalProperties: false,
    },
  },
};
