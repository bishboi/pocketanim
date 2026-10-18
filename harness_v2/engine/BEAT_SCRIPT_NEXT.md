# A proposal: the next beat script

A proposal, not built. The current beat script ([BEAT_SCRIPT.md](BEAT_SCRIPT.md)) works and stays: the idea is a
cleaner format that a **translator** turns into today's beat script, so the compiler and engine need no change to
start, and the Lab tab can play both side by side.

## What is hard about today's format

1. **Sync is guessed, not written.** A beat says its words (`say`) and its operations (`do`), but not *which word*
   each animation lands on. That is guessed after the voice is made: a timing model's call per chapter
   (align_cues), plus name matching for labels and diagram nodes. The writer of the script already knows the word
   ("…stored in the **granary**"), but it has nowhere to write it.
2. **Highlighting is implicit.** A picture's part, a diagram's node and a place on the map are pointed at when the
   line happens to say their name. If the words differ ("the store" vs a label "granary"), nothing is pointed at,
   and there is no way to point at something on purpose.
3. **References differ by kind.** `{"op":"focus","diagram":"chain","node":"granary"}`, a picture's labels by their
   words, map places by name, a working by `id`. There is no single way to name "that thing on screen".
4. **Arrays where objects are meant.** `events: [["1526","Panipat"]]`, `edges: [["a","b","grain","bold"]]`,
   `spans: [[from,to,label]]`. These are short, but a model often mis-orders them and the errors are vague.
5. **Layout is all heuristics.** Where things go (left half, top band, full screen) is decided by the engine from
   what is on stage. It works mostly, but there is no way to ask for "timeline on top, working below".
6. **Exits are implicit.** A picture stays until another replaces it. There is no `hide`, and no way to keep two
   things on screen on purpose.
7. **No schema.** The model is given prose rules, and the compiler mends what it gets. A JSON Schema would let the
   writing model use strict structured output, and let the editor show errors at their place.

## The proposal

Two ideas carry most of the gain: **things have ids**, and **words carry cues**.

```json
{
  "version": 3,
  "look": {"style": "chalkboard", "art": "auto"},
  "chapter": {
    "title": "Where the surplus went",
    "beats": [
      {
        "say": "Farmers grew more grain than they needed, and stored it in the [granary].",
        "show": [
          {"id": "chain", "diagram": {"kind": "flow", "title": "Where the surplus went",
            "nodes": [{"id": "fields", "label": "Fields"},
                      {"id": "granary", "label": "Granary", "kind": "place"},
                      {"id": "crafts", "label": "Craftsmen", "hidden": true}],
            "edges": [{"from": "fields", "to": "granary", "label": "grain"},
                      {"from": "granary", "to": "crafts", "label": "food", "style": "bold"}]}}
        ],
        "cues": {"granary": {"point": "chain.granary"}}
      },
      {
        "say": "The stored food fed [craftsmen], who no longer had to farm.",
        "cues": {"craftsmen": {"reveal": "chain.crafts"}}
      },
      {
        "say": "Look closer at the [granary].",
        "cues": {"granary": {"zoom": "chain.granary", "scale": 2}}
      }
    ]
  }
}
```

What changes:

| Today | Proposed | Why |
|---|---|---|
| `do: [ops]` mixing what appears and what happens to it | `show` (what comes on screen, each with an `id`) and `cues` (what happens on a word) | What is on screen and when it moves are two questions; separating them makes both easier to write and to check |
| Sync guessed after the voice | `[word]` marked in `say`, its action in `cues` | Deterministic: the word's time from the aligner *is* the start. No timing call, no cost, no wrong guesses. The timing model stays as a fallback for unmarked actions |
| `focus` / `reveal` / `zoom` per kind, label pointing by name | One target form: `"chain.granary"`, `"loco.boiler"`, `"map.Varanasi"`, `"w.2"` (a working's 2nd line) | One way to name anything on screen. **Highlighting a picture's label becomes explicit**: `{"point": "loco.boiler"}` |
| Tuples (`["1526","Panipat"]`) | Objects (`{"date": "1526", "label": "Panipat"}`), tuples still read | Fewer mis-ordered fields, clearer errors |
| Placement guessed | Optional `"place": "full" \| "left" \| "right" \| "top" \| "bottom"` on a shown thing | Ask for a layout when it matters; the engine still decides when it is left out |
| Stays until replaced | `"hide": "chain"` as a cue, `"keep": true` on a shown thing | Exits on purpose |
| Prose rules only | A JSON Schema generated from the compiler's own tables | Strict structured output for the writing model, errors at their path in the editor and the Lab |

The cue actions: `point` (shade round it and dim the rest), `reveal`, `zoom` (and `zoom: null` to back out),
`hide`, `pulse` (a short flash with no dimming), `move` (a picture's motion), `write` (a working's next line). They
are the same set the engine has today; only how they are named and timed changes.

## How to get there

1. **Translator** (`compile_next.py`, about 300 lines): version-3 script → today's beat script. `show` items become
   today's ops, cues become today's `focus` / `reveal` / `zoom`, and the `[word]` marks become per-op `at` words that
   the voice step times exactly (they replace the timing call for those ops). Tuples and objects both read.
2. **Exact cues in the voice step:** when an op has its word, its start is that word's time from the aligner; the
   timing call is made only for ops without one.
3. **Explicit `point`** in the engine for picture labels and map places: today's implicit name-pointing is kept as the
   fallback.
4. **Schema** from the compiler's tables; used by the scene writer's tool and by the Lab's editor.
5. **The scene writer** writes version 3 once the Lab shows it plays better on the same chapters.

The Lab tab is where this gets judged: the same chapter in both formats, played side by side with the voice.
