"""Install LaTeX for typeset equations (MathTex, Tex, axis numbers): TinyTeX, with what Manim needs.

    .venv/bin/python harness/scripts/fetch_latex.py            # install when missing, then check
    .venv/bin/python harness/scripts/fetch_latex.py --check    # only report what is there

Without LaTeX a lecture still renders, with its maths drawn as plain Unicode text (nolatex.py). With it,
equations are typeset properly, and formulas with Hindi in them (\\text{फिसलन होगी}) are typeset by XeLaTeX.

What it does:
- when `latex`, `xelatex` and `dvisvgm` are already installed (MacTeX, TeX Live, an earlier TinyTeX), it only
  adds the few packages Manim uses, if `tlmgr` can;
- otherwise it installs TinyTeX (a small TeX Live, about 250 MB, yihui.org/tinytex) with its own installer,
  into ~/Library/TinyTeX (macOS) or ~/.TinyTeX (Linux). No administrator rights are needed;
- then typesets one test formula, and one with Hindi, the way the lectures do.

The harness finds TinyTeX, MacTeX and TeX Live by itself even when they are not on PATH (nolatex.TEX_HOMES).
On Windows, use WSL.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LECTURE = SCRIPTS.parent / "lecture"
sys.path.insert(0, str(LECTURE))

import nolatex  # noqa: E402

INSTALLERS = ("https://yihui.org/tinytex/install-bin-unix.sh",
              "https://raw.githubusercontent.com/rstudio/tinytex/main/tools/install-bin-unix.sh")
# What Manim's templates load (standalone, preview, babel, amsmath, amssymb) and XeLaTeX with fontspec for
# non-Latin text, plus dvisvgm, which turns the output into the SVG Manim draws.
CTAN = "https://mirror.ctan.org/systems/texlive/tlnet"
PACKAGES = ("standalone", "preview", "babel-english", "amsmath", "amsfonts", "dvisvgm", "xetex", "fontspec",
            "tools", "l3packages", "xcolor")


def _tinytex_home() -> Path:
    return Path.home() / ("Library/TinyTeX" if sys.platform == "darwin" else ".TinyTeX")


def install_tinytex() -> bool:
    """Run TinyTeX's own installer. Never over an existing TinyTeX (the installer deletes the folder first)."""
    if _tinytex_home().exists():
        print(f"TinyTeX is already in {_tinytex_home()}; not reinstalling it.")
        return True
    if not shutil.which("perl"):
        print("TinyTeX's installer needs perl. Install it (it ships with macOS; `sudo apt install perl`).")
        return False
    script = None
    for url in INSTALLERS:
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                script = response.read()
            break
        except Exception as error:  # noqa: BLE001 -- try the mirror
            print(f"could not download {url}: {error}")
    if script is None:
        return False
    with tempfile.NamedTemporaryFile("wb", suffix=".sh", delete=False) as handle:
        handle.write(script)
        path = handle.name
    print("Installing TinyTeX (a few minutes, about 250 MB)...", flush=True)
    try:
        return subprocess.run(["sh", path]).returncode == 0
    finally:
        os.unlink(path)


def tlmgr() -> str | None:
    nolatex.add_tex_to_path()
    return shutil.which("tlmgr")


def missing_packages() -> list[str]:
    """Packages from PACKAGES whose files kpsewhich cannot find."""
    nolatex.add_tex_to_path()
    if not shutil.which("kpsewhich"):
        return list(PACKAGES)
    probes = {"standalone": "standalone.cls", "preview": "preview.sty", "babel-english": "english.ldf",
              "amsmath": "amsmath.sty", "amsfonts": "amssymb.sty", "fontspec": "fontspec.sty", "xcolor": "xcolor.sty",
              "tools": "calc.sty", "l3packages": "xparse.sty"}
    out = []
    for package, probe in probes.items():
        found = subprocess.run(["kpsewhich", probe], capture_output=True, text=True).stdout.strip()
        if not found:
            out.append(package)
    if not shutil.which("dvisvgm"):
        out.append("dvisvgm")
    if not shutil.which("xelatex"):
        out.append("xetex")
    return out


def add_packages(names: list[str]) -> bool:
    manager = tlmgr()
    if not names:
        return True
    if manager is None:
        print("Missing LaTeX packages: " + ", ".join(names) + ". Install them with your TeX distribution "
              "(TeX Live: `sudo apt install texlive-latex-extra texlive-xetex dvisvgm`).")
        return False
    print("Adding LaTeX packages: " + ", ".join(names), flush=True)
    if subprocess.run([manager, "install", *names]).returncode == 0:
        return True
    # "tlmgr itself needs to be updated" is the usual refusal on a TinyTeX a few weeks old.
    print("Updating tlmgr and trying again...", flush=True)
    subprocess.run([manager, "update", "--self"])
    if subprocess.run([manager, "install", *names]).returncode == 0:
        return True
    # TinyTeX's own package mirror can be unreachable: CTAN's mirror network has the same packages.
    print("Trying CTAN's mirror...", flush=True)
    return subprocess.run([manager, "--repository", CTAN, "install", *names]).returncode == 0


def check() -> dict:
    """What is installed, and whether a formula (and one with Hindi) typesets."""
    report = {"latex": shutil.which("latex") if nolatex.latex_available() else None,
              "xelatex": shutil.which("xelatex") if nolatex.xelatex_available() else None,
              "dvisvgm": shutil.which("dvisvgm"), "hindi_font": nolatex.script_font()}
    if report["latex"]:
        report["maths"] = _typesets(r"v^2 = u^2 + 2as,\quad \frac{mv^2}{R}\le\mu_s mg")
    if report["xelatex"] and report["hindi_font"]:
        report["hindi"] = _typesets(r"25 > 2.94 \Rightarrow \text{फिसलन होगी}")
    return report


def _typesets(tex: str) -> bool:
    from manim import tempconfig

    with tempfile.TemporaryDirectory() as folder, tempconfig({"media_dir": folder, "verbosity": "ERROR"}):
        nolatex.install()
        try:
            # A drawing made by the text fallback is named nolatex_*: LaTeX did not typeset it.
            path = nolatex.typeset(tex, "align*")
            return not Path(path).name.startswith("nolatex_")
        except Exception as error:  # noqa: BLE001
            print(f"typesetting failed: {error}")
            return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only report what is installed")
    args = ap.parse_args()
    if not args.check:
        if not nolatex.latex_available():
            if not install_tinytex():
                print("TinyTeX did not install. Or install LaTeX yourself: macOS `brew install --cask "
                      "mactex-no-gui`, Ubuntu `sudo apt install texlive texlive-latex-extra texlive-xetex dvisvgm`.")
                return 1
        add_packages(missing_packages())
    report = check()
    for key, value in report.items():
        print(f"  {key:10} {value if value else 'MISSING'}")
    if not report.get("dvisvgm") and report.get("latex"):
        print("dvisvgm is missing: LaTeX is there, but Manim needs dvisvgm to turn its output into drawings. "
              f"Try `{tlmgr() or 'tlmgr'} install dvisvgm`" + (", or `brew install dvisvgm`" if sys.platform == "darwin"
                                                                 else ", or `sudo apt install dvisvgm`") + ".")
    ready = bool(report.get("latex") and report.get("maths"))
    print("LaTeX is ready." if ready else "LaTeX is not ready: equations are drawn as plain text.")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
