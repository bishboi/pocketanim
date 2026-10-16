/**
 * The map of a figure triaged Map: one model that reads images is shown the book's figure and writes it as a short
 * map script for the lecture engine (harness_v2/engine, a copy of v1's), in the same call: the region it is on and a
 * few beats, each adding what the figure shows (rivers, places, areas, routes, empires...) with a short line said as
 * it appears. The engine draws it on real map data, looking every place up by name. The ops and their rules are v1's
 * (harness/app/lib/lecture.ts "Map operations"), without pictures on markers (there is no illustration model here).
 */

import { part, type Part } from "./parts";

const ROLE = "You rebuild ONE map from a textbook (attached) as a short animated map for a video lecture, drawn by the lecture's map " +
  "engine on real map data: the same region, the same places, rivers, areas, routes and labels as the book's map, built up a few at a time.";

const SHAPE = [
  "Answer with write_map: {region, title, beats}.",
  'region: {"country": "India"} | {"state": "Rajasthan", "country": "India"} | {"area": "World" | a continent ("Asia",',
  '  "Europe", "Africa") | a world region ("South Asia", "Middle East", "Western Europe", "Southern Africa", "Indian',
  '  subcontinent")}: the land the book\'s map shows (an area\'s "state" op fills a country).',
  "title: the map's title, a few words.",
  "beats: 2 to 6 steps, in the order a teacher builds the map: each {say, do}: say is one short line (6-15 words) said",
  "  as it appears, shown as the caption; do is 1 to 4 map operations. Everything on the book's map is drawn by the last beat.",
].join("\n");

const OPS = [
  "Map operations (colour = palette name SAND RIVER GOLD ROSE TEAL GREEN VIOLET MUTED CREAM HI, or #RRGGBB):",
  '  {"op":"marker","place":"Jaipur" | "lonlat":[lon,lat],"label"?,"color"?,"side"?:"left|right|up|down"}',
  "     A marker is for a POINT: a town, a city, a battlefield, a temple, a port. Labels never cover one another.",
  '  {"op":"river","name":"Ganges","color"?}   a Natural Earth river by its English name',
  '  {"op":"state","name":"Normandy","label"?,"color"?,"opacity"?}   SHADE AN AREA, its name written on it: a state',
  "     or province, a country (\"England\", \"Spain\"), a region or a continent. A country or a region is the land",
  "     it covers, never a dot: a marker naming one big enough to see is shaded instead. Use a different colour",
  "     for each area that is compared (England and France at war: two colours).",
  '  {"op":"arrow","points":["Delhi","Agra",...],"color"?,"label"?}  a curved arrow: winds, migrations, routes;',
  "     label: what moves (\"spices\", \"the Aryans\", \"SW monsoon\"): it rides the arrow as it is drawn",
  '  {"op":"empire","name":"Mughal Empire","year":1600,"label"?,"color"?}  a state as it stood in that year, filled',
  "     with its border (historical maps, 2000 BC to 2010): kingdoms and empires, never today's borders for the past.",
  "     Use the state's usual English name (Maurya Empire, Delhi Sultanate, Ottoman Empire, Maratha Confederacy).",
  '  {"op":"relief","names"?:["Himalayas","Western Ghats"],"label"?:false}  the mountains and plateaus in view,',
  "     shaded with hill marks and named; names: only these. When the land's shape is the point.",
  '  {"op":"path","points":["Haridwar","Prayagraj"],"color"?}  a hand-drawn line: a ridge, a canal',
  "     points are place names (looked up) or [lon, lat] for a spot with no name (the open sea, a desert).",
  '  {"op":"journey","stops":["Ahmedabad","Surat",[72.8,20.89]],"labels"?:["Sabarmati","Surat","Dandi"],"color"?}',
  "     a journey drawn as it happens: a traveller moves stop to stop, the route behind it, each stop named as it is",
  "     reached. A stop the map may not know (a village) goes as [lon, lat] with its name in labels.",
  '  {"op":"graticule","lat":23.44 | "lon":82.5,"label"?,"color"?}   a line of latitude or longitude (the Tropic of Cancer)',
  '  {"op":"dim","opacity"?}                fade filled areas down before highlighting one',
].join("\n");

const RULES = [
  "ALWAYS NAME PLACES; never guess coordinates: the engine looks names up in real gazetteers (towns, historic sites such",
  "as Lothal, Plassey, Dandi), and a guessed [lon, lat] is usually tens of kilometres off. A place is its name in English",
  "(\"Prayagraj\", not \"प्रयागराज\"). A site the gazetteer does not know goes by the modern town it is in. Give lonlat",
  "only for a spot with no name (a point at sea).",
  "Rebuild the book's map, not more: its own places, rivers, areas and routes, labelled as it labels them.",
].join("\n");

export const MAP_TOOL = {
  type: "function" as const,
  function: {
    name: "write_map",
    description: "Save the map: its region, title and beats of map operations.",
    parameters: {
      type: "object",
      properties: {
        region: { type: "object", description: 'The land the map shows: {"country"}, {"state", "country"} or {"area"}.' },
        title: { type: "string" },
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              say: { type: "string", description: "One short line said as this step appears (the caption)." },
              do: { type: "array", items: { type: "object" }, description: "1 to 4 map operations." },
            },
            required: ["say", "do"],
          },
        },
      },
      required: ["region", "title", "beats"],
    },
  },
};

export function mapPrompt(x: { documentId: string; blockId: string; page: number; caption?: string; context?: string; how?: string;
  retry?: { script: string; errors: string[] } }): { system: Part[]; user: Part[] } {
  return {
    system: [
      part("role", "Role", "rules", ROLE),
      part("shape", "The map script's shape", "rules", SHAPE),
      part("ops", "Map operations (v1's)", "rules", OPS),
      part("rules", "Places and fidelity", "rules", RULES),
    ],
    user: [
      part("figure", "The figure", "book", `Figure ${x.blockId} (page ${x.page + 1}): ${x.caption || "(no caption)"}`),
      ...(x.context?.trim() ? [part("context", "The book around it", "book", `The book around it:\n${x.context.trim().slice(0, 1200)}`)] : []),
      ...(x.how?.trim() ? [part("how", "Note on this figure (triage)", "items", `Note on this figure: ${x.how.trim().slice(0, 300)}`)] : []),
      part("image", "The book's map (picture)", "book", `The book's map, to rebuild: [attached: /api/documents/${x.documentId}/figure/${encodeURIComponent(x.blockId)}]`),
      ...(x.retry ? [part("retry", "Your last map, and what the engine refused", "retry", ["YOUR LAST MAP was refused by the map engine:",
        x.retry.script.slice(0, 3000), "", "What was wrong:", ...x.retry.errors.map((e) => `- ${e}`), "", "Fix exactly that and keep everything else."])] : []),
      part("ask", "Request", "ask", "Write the map (write_map)."),
    ],
  };
}

/** The offline stand-in's map: the northern plain's rivers and two cities. */
export function standInMap(caption: string) {
  return {
    region: { country: "India" }, title: (caption || "The map").slice(0, 60),
    beats: [
      { say: "The Ganga flows across the northern plain.", do: [{ op: "river", name: "Ganges" }] },
      { say: "The Yamuna joins it at Prayagraj.", do: [{ op: "river", name: "Yamuna" }, { op: "marker", place: "Prayagraj", label: "Prayagraj" }] },
      { say: "Delhi stands on the Yamuna.", do: [{ op: "marker", place: "Delhi", label: "Delhi" }] },
    ],
  };
}
