"""Run Stage 4.5 offline from the repository root: python run_spectral.py."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agripulse.spectral import main

if __name__ == "__main__":
    raise SystemExit(main())
