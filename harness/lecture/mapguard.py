"""Maps come from one place: the lecture's map (MapLecture), whose every outline, river and coastline is Natural
Earth's geometry projected through Cartopy. A map drawn any other way -- an SVG the model draws, a block of free
Manim, an AI picture, a picture search's map file -- is a guess at the shape of the world, and it is wrong.

is_map(text) says whether a description asks for a geographic map ("a map of the Mughal Empire", "the trade
routes from Venice to China", "the outline of India"), and not a concept map, a function that maps x to y, or the
border of a cell. code_draws_map(code) says the same of a block of Manim. The compiler refuses such ops with
MAP_ADVICE, so the writer moves the picture onto the map.
"""

from __future__ import annotations

import re

# "map" in names that are not geography.
_NOT_GEO = (r"concept|mind|heat|flow|tree|bubble|story|site|bit|key|genetic|gene|linkage|star|sky|memory|empathy|"
            r"process|value[- ]stream|feature|thinking|circle|spider|texture|normal|colou?r|tone|body|karnaugh|k|"
            r"self[- ]organi[sz]ing|logistic|tone|contour|topic|journey|customer|argument|word|idea|cognitive|"
            r"pixel|frame|look[- ]?up|hash|tile|bump|shadow|uv|depth|environment|cube|chord|fate|cell")
# The verb ("f maps x to y", "map out the steps") is not a map.
_MAP = re.compile(r"\bmaps?\b(?!\s+(?:onto|to|into|out|each|every|a\b|an\b|one|the (?:input|domain|values?|points?)|"
                  r"\w+\s+(?:on)?to\b))", re.I)
_NOT_GEO_MAP = re.compile(rf"\b(?:{_NOT_GEO})[\s-]*maps?\b", re.I)
_GEO = re.compile(
    r"\b(?:atlas|cartograph\w*|coastlines?|continents|world map|political (?:divisions|boundaries)|"
    r"trade routes?|sea routes?|caravan routes?|migration routes?|(?:the )?silk road)", re.I)
_DIVISIONS = re.compile(r"\b(?:[Ss]tates|[Pp]rovinces|[Dd]istricts|[Cc]ountries|[Kk]ingdoms|[Cc]olonies) (?:of|in) "
                        r"(?:the )?[A-Z]\w+")
# Shapes and extents of named places: "the outline of India", "the borders between France and Spain", "the
# extent of the Roman Empire", "a route from Delhi to Agra". The capital letter is what makes it a place (the
# border of the cell is not).
_SHAPE = re.compile(r"\b(?:outlines?|shape|borders?|boundar(?:y|ies)|frontiers?|territor(?:y|ies)|extent|coast|spread|"
                    r"expansion|conquests?|voyages?|routes?|journey|march|campaigns?|migrations?)\s+"
                    r"(?:of|between|from|across|through|over|along|around|to|into)\s+(?:the\s+)?(?:(?!an?\b)[a-z]+\s+)?"
                    r"(?!(?:Earth|Sun|Moon|Milky|Solar|Universe|Atom|Cell)\b)[A-Z][a-z]")
_ROUTE = re.compile(r"\bfrom\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+to\s+[A-Z][a-z]+")
_ROUTE_WORDS = re.compile(r"\b(?:route|journey|voyage|march|travel(?:led|ed)?|sail(?:ed|ing)?|migrat\w*|path|road)\b",
                          re.I)


def is_map(text: str | None) -> bool:
    """Whether a description of a picture asks for a geographic map."""
    text = str(text or "")
    if not text.strip():
        return False
    stripped = _NOT_GEO_MAP.sub(" ", text)
    if any(p.search(stripped) for p in (_MAP, _GEO, _DIVISIONS, _SHAPE)):
        return True
    return bool(_ROUTE.search(stripped) and _ROUTE_WORDS.search(stripped))


# In code: names that only a map has (india_outline, coast, lon, lat, longitude, borders_of), and map words in its
# strings and comments. Python's map() is not one.
_CODE_NAMES = re.compile(r"(?i)\b(?:[a-z0-9]+_)*(?:map|maps|coast|coastline|coastlines|lon|lat|lons|lats|longitude|"
                         r"latitude|lonlat|latlon|continent|continents|country|countries|cartopy|geopandas|shapely)"
                         r"(?:_[a-z0-9]+)*\b(?!\s*\()")
_STRINGS = re.compile(r"(\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"[^\"\n]*\"|'[^'\n]*'|#[^\n]*)")


def code_draws_map(code: str | None) -> bool:
    """Whether a block of Manim draws a map of its own."""
    code = str(code or "")
    if any(is_map(s.strip("\"'# ")) for s in _STRINGS.findall(code)):
        return True
    return bool(_CODE_NAMES.search(_STRINGS.sub(" ", code)))


MAP_ADVICE = ("a map is never drawn as a picture, an SVG or a block of Manim: maps come only from the lecture's map "
              "(Natural Earth through Cartopy, accurate to the coastline). Give the script a region and use the map "
              "operations (marker, state, river, arrow, path, journey, graticule) for it")
