"""Run Stage 3 from the repository root: python run_sentinel.py."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agripulse.sentinel import main

if __name__ == "__main__":
    raise SystemExit(main())
