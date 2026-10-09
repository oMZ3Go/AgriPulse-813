"""Run Phase 2 from the repository root: python run_stress.py."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agripulse.stress import main

if __name__ == "__main__":
    raise SystemExit(main())
