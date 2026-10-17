"""Pictures for lectures: made by an image model as cutouts (genimage.py), never searched for on the web.

`fetch` is the one way a script's photo, illustration, detailed diagram, gallery item, picture beside a label or
picture of a thing (a diagram's node, a map's icon) gets its file: the words it gives (a subject, a query, a
description) are what the image model is asked to make. Every other picture a lecture shows is built in Manim;
nothing is drawn as an SVG.

PANIM_IMAGES=0 turns pictures off (a lecture then shows Manim and the document's figures only).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("PANIM_IMAGE_CACHE") or (HERE / ".cache" / "images"))

# Map pictures ("Map of the Mughal Empire", a locator map of a state) are never shown: a lecture's maps are drawn
# from Natural Earth through Cartopy, on the map (mapguard).
LOCATOR = re.compile(r"\b(?:locator|location map|orthographic projection|disputed|hatched|relief map|topographic)\b",
                     re.I)
# "Rajasthan in India.svg": a locator map's name (a photo, "Taj Mahal in Agra.jpg", is not one).
LOCATOR_SVG = re.compile(r"^(?:File:)?[A-Z][\w ]+ in [A-Z][\w ]+(?: \(.*\))?\.svg$")


def enabled() -> bool:
    """Whether pictures can be had: they are made by the image model (genimage.py), never searched for."""
    import genimage

    return genimage.enabled()


def is_map_row(row: dict | None) -> bool:
    """Whether a picture is a map (by what it is called)."""
    import mapguard

    if not row:
        return False
    text = " ".join(str(row.get(k) or "") for k in ("title", "description"))
    text = re.sub(r"^File:|\.(?:svg|png|jpe?g|gif|tiff?|webp)$", "", text.replace("_", " "), flags=re.I)
    title = re.sub(r"^File:|\.(?:svg|png|jpe?g|gif|tiff?|webp)$", "", str(row.get("title") or "").replace("_", " "),
                   flags=re.I)
    return (mapguard.is_map(text) or bool(LOCATOR.search(title))
            or bool(LOCATOR_SVG.match(str(row.get("title") or "").replace("_", " "))))


def fetch(image: str | None = None, query: str | None = None, subject: str | None = None,
          illustration: str | None = None, avoid: set | None = None, genre: str | None = None,
          style: str | None = None, realistic: bool = False, parts=None, context: str | None = None,
          scene: bool = False, match: bool = True, kind: str | None = None, aspect: str | None = None,
          look: str | None = None) -> dict | None:
    """The picture a script asks for, made by the image model as a cutout (genimage.py). What it shows is the
    subject, the illustration's words, the query, or an old script's Commons title's words. Returns its row with
    `file` set, or None when it cannot be made (no key, refused, a map). `avoid` and `genre` are an old caller's:
    a picture made for given words is the same picture each time. `parts`: what it will label, shown clearly.
    `context`: what the picture is for (the lesson, the chapter, the lines said over it), told to the model.
    `kind` "diagram": made by the diagram model (a detailed, exact picture), as a picture with labels is.
    `aspect` ("16:9", "4:3", "1:1"): the shape it is made in; `look` "child": drawn as a child draws (a small
    picture the board draws on)."""
    import genimage

    title = re.sub(r"\.(jpe?g|png|svg|webp|gif|tiff?)$", "", re.sub(r"^File:", "", str(image or ""), flags=re.I), flags=re.I)
    what = subject or illustration or query or title.replace("_", " ")
    row = genimage.generate(str(what or ""), style=style or os.environ.get("LECTURE_STYLE"), realistic=realistic,
                            parts=parts, context=context, scene=scene, match=match, kind=kind, aspect=aspect,
                            look=look)
    if row and is_map_row(row):
        genimage._failed(str(what or ""), "left out: what it shows reads as a map (mapguard), and maps are drawn "
                                          "only on the map")
        return None
    return row


def credit(rows) -> str:
    """The credits line for the pictures a lecture showed: which image model made them."""
    models = sorted({str(r.get("model") or r.get("artist") or "") for r in rows if r} - {""})
    return f"Pictures made with {', '.join(models)}" if models else ""
