/**
 * Maps come from one place: the lecture's map, Natural Earth's geometry projected through Cartopy
 * (harness/lecture/mapguard.py, which the compiler enforces). This is its test of a picture's description, so a
 * map asked of the SVG drawer is turned away before a model is paid to guess at the shape of the world.
 * Keep it in step with mapguard.is_map.
 */

const NOT_GEO = "concept|mind|heat|flow|tree|bubble|story|site|bit|key|genetic|gene|linkage|star|sky|memory|empathy|" +
  "process|value[- ]stream|feature|thinking|circle|spider|texture|normal|colou?r|tone|body|karnaugh|k|" +
  "self[- ]organi[sz]ing|logistic|contour|topic|journey|customer|argument|word|idea|cognitive|" +
  "pixel|frame|look[- ]?up|hash|tile|bump|shadow|uv|depth|environment|cube|chord|fate|cell";
const NOT_GEO_MAP = new RegExp(`\\b(?:${NOT_GEO})[\\s-]*maps?\\b`, "gi");
const MAP = /\bmaps?\b(?!\s+(?:onto|to|into|out|each|every|a\b|an\b|one|the (?:input|domain|values?|points?)|\w+\s+(?:on)?to\b))/i;
const GEO = /\b(?:atlas|cartograph\w*|coastlines?|continents|world map|political (?:divisions|boundaries)|trade routes?|sea routes?|caravan routes?|migration routes?|(?:the )?silk road)/i;
const DIVISIONS = /\b(?:[Ss]tates|[Pp]rovinces|[Dd]istricts|[Cc]ountries|[Kk]ingdoms|[Cc]olonies) (?:of|in) (?:the )?[A-Z]\w+/;
const SHAPE = /\b(?:outlines?|shape|borders?|boundar(?:y|ies)|frontiers?|territor(?:y|ies)|extent|coast|spread|expansion|conquests?|voyages?|routes?|journey|march|campaigns?|migrations?)\s+(?:of|between|from|across|through|over|along|around|to|into)\s+(?:the\s+)?(?:(?!an?\b)[a-z]+\s+)?(?!(?:Earth|Sun|Moon|Milky|Solar|Universe|Atom|Cell)\b)[A-Z][a-z]/;
const ROUTE = /\bfrom\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+to\s+[A-Z][a-z]+/;
const ROUTE_WORDS = /\b(?:route|journey|voyage|march|travel(?:led|ed)?|sail(?:ed|ing)?|migrat\w*|path|road)\b/i;

/** Whether a description of a picture asks for a geographic map. */
export function isMap(text: string | undefined | null): boolean {
  const stripped = String(text ?? "").replace(NOT_GEO_MAP, " ");
  if (!stripped.trim()) return false;
  if ([MAP, GEO, DIVISIONS, SHAPE].some((pattern) => pattern.test(stripped))) return true;
  return ROUTE.test(stripped) && ROUTE_WORDS.test(stripped);
}

export const MAP_ADVICE = "a map is never drawn as a picture, an SVG or a block of Manim: maps come only from the " +
  "lecture's map (Natural Earth through Cartopy, accurate to the coastline). Give the script a region and use the " +
  "map operations (marker, state, river, arrow, path, journey, graticule) for it";
