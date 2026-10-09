"""An AI-drawn SVG as the board shows it, for the web page to display: its colour names (INK, ROSE, BOARD...) in the
lecture style's colours and near-black lines in the ink (pocket_lecture.board_svg's painting, without the layout).

    .venv/bin/python harness/scripts/board_svg.py <style> <file.svg>

Prints the painted SVG, with the board's colour as its background.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lecture"))


def main() -> int:
    style, file = sys.argv[1], sys.argv[2]
    import animsvg
    import icons
    import pocket_lecture as pl

    pl.use_style(style)
    palette = {**pl.TH["pal"], "INK": pl.P.CREAM, "MUTED": pl.P.MUTED, "BOARD": pl.P.BG}
    raw = pl._ink_svg(icons.flatten_gradients(Path(file).read_text(encoding="utf-8")), pl.P.CREAM)
    text = animsvg.paint(raw, palette)
    # The board behind it, so light ink on a dark board reads on any page.
    text = re.sub(r"(<svg\b[^>]*>)", rf'\1<rect x="-10000" y="-10000" width="20000" height="20000" fill="{pl.P.BG}"/>',
                  text, count=1)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
