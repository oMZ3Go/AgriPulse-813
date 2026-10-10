"""Run Stage 4.6 offline from the repository root: python run_ml.py."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agripulse.ml import main

if __name__ == "__main__":
    raise SystemExit(main())
