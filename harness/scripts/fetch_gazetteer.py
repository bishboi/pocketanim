"""Download the GeoNames gazetteer the lecture engine looks places up in.

Natural Earth, which draws the maps, lists about 7,300 towns for the whole
world. GeoNames' cities1000 lists every town of 1,000 people or more (about
150,000), with their other names: renamed cities (Prayagraj), old names
(Cawnpore) and names in other scripts. About 10 MB to download, once.

    .venv/bin/python harness/scripts/fetch_gazetteer.py [--set cities500|cities1000|cities5000|cities15000]

Data: GeoNames (geonames.org), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "lecture" / "data" / "geonames"
URL = "https://download.geonames.org/export/dump/{name}.zip"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", default="cities1000", choices=["cities500", "cities1000", "cities5000", "cities15000"])
    args = ap.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    out = TARGET / "cities.txt"
    url = URL.format(name=args.set)
    print(f"Downloading {url} ...", flush=True)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "pocketanim-lecture/0.4"})
        with urllib.request.urlopen(request, timeout=300) as response:
            data = response.read()
    except Exception as error:  # noqa: BLE001
        print(f"Could not download the gazetteer: {error}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".txt"))
        out.write_bytes(archive.read(member))
    rows = sum(1 for _ in out.open(encoding="utf-8"))
    (TARGET / "SOURCE").write_text(f"{url}\nGeoNames (geonames.org), CC BY 4.0\n")
    print(f"Wrote {out} ({rows:,} places)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
