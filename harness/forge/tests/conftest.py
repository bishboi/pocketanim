import sys
from pathlib import Path

# `forge` is a package in harness/forge; make it importable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
