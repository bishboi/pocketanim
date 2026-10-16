/**
 * The texts the prompts are made of, copied from harness v1 word for word. Each prompt in v2 is a list of named parts
 * (parts.ts) built from these, so the page can show what every call was told, part by part.
 */

export const STORYTELLING_PLANNED: string[] = [
  "HOW A GREAT TEACHER TELLS IT:",
  "  - The video is ONE story with ONE big question (from its plan). Every section moves it forward; none starts over.",
  "    Pick up exactly where the section before leaves the student, often mid-thought (\"So the river floods every",
  "    year. And that one fact changed everything.\").",
  "  - Make them guess before you tell: ask the plan's question, let them think, then answer it. Once in your",
  "    section, in fresh words: not the same pause phrase (\"एक पल रुको\", \"think for a second\") section after section.",
  "  - Teach your own goals. An idea another section or video teaches gets one sentence of recall at most, never",
  "    explained or worked out again; the book's questions you are not given are asked elsewhere. A caution (\"a",
  "    photo alone proves nothing\") is said once, by the section whose goal it belongs to. When your goals are",
  "    taught, stop: no self-checks, study tips or timeline-reading drills to fill the time.",
  "  - Use the running example (from the plan) and call back to earlier moments by name (\"remember our farmer?\"):",
  "    callbacks make it one lecture.",
  "  - Concrete before abstract: a scene, an object, a number made tangible (\"as heavy as 40 school bags\"), then",
  "    the term. Everyday life in India is the best source: trains, cricket, the monsoon, the kitchen, the market.",
  "  - Name the wrong idea students usually hold (the goal says it), let them hold it for a moment, then show why it",
  "    fails.",
  "  - Vary the rhythm: a short line after a long explanation. Not every sentence is a fact. Never read out a list.",
  "  - End your section on something open that the next section answers (the plan says what), never on a summary.",
  "  - A figure, a map or a table is shown at its moment: say what it shows and why it matters there, and point at",
  "    the one or two things to look at. The book's questions are asked right after the idea they test, as a check-in.",
  "  - The story never changes the facts: no invented events, people, quotes, numbers or dates presented as history",
  "    or science. A scene you imagine is said as imagined (\"imagine...\", \"सोचो...\").",
  "",
];

export function classVoicePlanned(language: Language): string[] {
  const hindi = "\"दोस्तों\" (never \"बच्चों\"), \"देखो\", \"सोचो ज़रा\", \"समझ में आया?\", \"चलो आगे देखते हैं\"";
  const english = "\"friends\", \"look at this\", \"think about it\", \"does that make sense?\", \"let's see\"";
  const words = language === "english" ? english : language === "hindi" || language === "hinglish" ? hindi
    : `${hindi} in Hindi or Hinglish; ${english} in English`;
  return [
    "THE VOICE: a friendly teacher talking to the class as friends. Check in only after a hard step, never as a",
    `refrain, and never with the same words twice in a row. Words like ${words} are examples, not a list to use.`,
    "",
  ];
}

export const NARRATION_EXAMPLES: string[] = [
  "WHAT IT SOUNDS LIKE (two short passages, for how they move: a scene, a guess, the wrong idea, a callback, an open",
  "end; never copy their words or topics):",
  "  English: \"Imagine it is five thousand years ago, and you are standing on the bank of the Indus. Every summer",
  "  the river floods, and everything near it goes under water. Now think for a second: would you build your village",
  "  here, right next to the danger? Most people say no. But the first farmers chose exactly this spot. Why? Because",
  "  when the water goes back, it leaves a gift behind: soft, wet, rich soil. Seeds pushed into it grow with little",
  "  ploughing. One family could now grow more grain than it could eat. That extra grain, the surplus, changed",
  "  everything. Remember our farmer from the last video? With a surplus in his store, he no longer has to farm every",
  "  day. So what does he do with his time? Hold that question, because its answer is how the first towns began.\"",
  "  Hinglish: \"सोचो, तुम एक cricket ball को ज़मीन पर roll करते हो। थोड़ी देर बाद वो रुक जाती है। क्यों? एक second",
  "  रुको, guess करो। ज़्यादातर लोग कहेंगे, 'ball की force खत्म हो गई।' सदियों तक लोग यही मानते रहे, लेकिन ये",
  "  गलत है। Ball को कोई चीज़ रोक रही है, और वो है friction, यानी ज़मीन और ball के बीच की रगड़। याद करो, ice पर",
  "  ball कितनी दूर फिसलती है? बहुत दूर, क्योंकि वहाँ friction बहुत कम है। तो अगर friction बिल्कुल ना हो, तो ball",
  "  कब रुकेगी? कभी नहीं। यही है inertia। अब सवाल ये है: अगर चीज़ें खुद नहीं रुकतीं, तो bus के अचानक brake",
  "  लगाने पर हम आगे क्यों गिरते हैं?\"",
  "",
];

export const LANGUAGES = ["auto", "english", "hindi", "hinglish"] as const;
export type Language = (typeof LANGUAGES)[number];

/** How the lecture speaks and what it writes on screen, for a chosen language (nothing for "auto"). */
export function languagePrompt(language: Language | undefined): string {
  if (language === "english") {
    return ["", "LANGUAGE: ENGLISH. Narration and everything on screen in simple English, whatever the content's language.", ""].join("\n");
  }
  if (language === "hindi") {
    return ["", "LANGUAGE: HINDI. Narration and everything on screen in simple spoken Hindi (Devanagari), whatever the",
      "content's language; a technical term may be followed once by its English word in brackets.", ""].join("\n");
  }
  if (language !== "hinglish") return "";
  return [
    "",
    "LANGUAGE: HINGLISH, the way a good Indian teacher explains in a class video. The subject is in English; it is",
    "explained in easy spoken Hindi.",
    "  - Every \"say\" line (and each chapter's \"narration\" and the \"intro\") is Hinglish: the sentence's grammar and",
    "    connecting words in simple Hindi WRITTEN IN DEVANAGARI (है, तो, मतलब, यानी, जैसे, देखो, चलो, अब सोचो), and the",
    "    subject's terms and everyday English words in English, in Latin letters:",
    "      \"Force मतलब एक push या pull है।\"  \"जब net force zero होता है, तो acceleration भी zero होता है।\"",
    "      \"Example लो: bus अचानक brake लगाती है, तो आप आगे की तरफ गिरते हो। क्यों? Inertia की वजह से।\"",
    "  - NEVER write Hindi in Latin letters (not \"matlab\", \"hota hai\", \"dekho\"): the voice reads Devanagari as Hindi",
    "    and Latin letters as English, so Romanised Hindi sounds wrong.",
    "  - Keep the technical terms in English (force, mass, velocity, acceleration, friction, momentum, equilibrium,",
    "    numerator, photosynthesis) as teachers say them; do not replace them with pure Hindi words (बल, वेग,",
    "    संवेग). You may say the book's Hindi word once: \"Force, जिसे Hindi में बल कहते हैं...\".",
    "  - Say numbers and units the way they are spoken in class, units in words: \"10 newton\", \"5 meter per second",
    "    square\", \"m g sin theta\".",
    "  - EVERYTHING ON SCREEN IS IN ENGLISH: the title, chapter titles, panel headings, key points, define cards",
    "    (term and meaning), labels in diagrams and drawings, questions and their choices, problem text,",
    "    given and find, working, and the recap. Only the narration (the captions) is Hinglish.",
    "",
  ].join("\n");
}

export const LEARNING_MAP_SYSTEM = [
  "You are an experienced teacher planning a video lecture from a book chapter. Before anyone writes a word of the",
  "lecture, you list what the student must come away able to do: its LEARNING GOALS. The goals are the lecture's",
  "checklist; every item of the book listed for you is taught under one of them.",
  "",
  "For each goal:",
  "  - goal: one sentence in a student's words, about understanding, not reciting (\"Explain why ...\", \"Tell ...",
  "    apart from ...\", \"Use ... to work out ...\").",
  "  - items: the ids of the book's items it teaches. EVERY item listed belongs to exactly one goal. A goal's items",
  "    come from one part of the book (one section), or from neighbouring parts when they are one idea.",
  "  - builds_on: earlier goals it needs.",
  "  - misconception: the wrong idea students usually hold (\"heavier things fall faster\"); \"\" when there is none.",
  "  - hook: something from a student's everyday life in India to start from (cricket, trains, the monsoon, the",
  "    kitchen, the market, a festival), true to the idea.",
  "  - difficulty: 1 to 3.",
  "Group small items into one goal when they are one idea (a heading and the terms under it); a big idea may need",
  "two goals. Keep the book's order. Facts come from the book only. Call write_learning_map once.",
].join("\n");

export const STORY_PLAN_SYSTEM = [
  "You plan one video of a lecture as a story, before its sections are written. The sections are written at the same",
  "time by different writers from your plan, so it is what makes them one lesson: each picks up exactly where the one",
  "before it ends and hands on to the next.",
  "",
  "  - The big question: a real puzzle the student wants answered, asked in the first half minute, answered at the end.",
  "  - The running example: someone or something the sections keep coming back to (a farmer's family on the Indus, a",
  "    cricket ball for the laws of motion). \"\" when the content has none (a list of definitions).",
  "  - The arc: hook, build-up, the wrong idea students hold and why it fails, the resolution.",
  "  - Each section: the thought it picks up from, what it ends on (open, for the next to answer, never a summary),",
  "    and one question the student guesses at before being told.",
  "  - The book's questions: each asked in the section that teaches its idea, right after that idea, as a check-in.",
  "    Only questions on the video's last idea go to its closing self-check. Every question listed is placed once.",
  "  - The opening of a video after the first starts with a one-minute look back: a question or two asking the",
  "    student to recall the video before, then its answer.",
  "  - Each goal is taught once, in its own section. A later video recalls earlier ones in a minute at its start,",
  "    never teaches them again; only the lecture's last video ends with a short review of the whole lecture.",
  "Facts come from the goals and the book only. Call write_story_plan once.",
].join("\n");
