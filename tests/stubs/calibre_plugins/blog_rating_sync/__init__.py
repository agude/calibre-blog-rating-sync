"""Maps the Calibre plugin package name onto the repository's plugin/ directory."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[4] / "plugin")]
