"""
Strategy B (MinerU variant) -- Layout-Aware via OpenDataLab MinerU.

Heavyweight (GPU-oriented, downloads ~1-2 GB of models) but world-class on
scientific papers, multi-column research, and especially mathematical formulas
(UniMERNet -> LaTeX). The selector chooses this for math/scientific documents.

We invoke MinerU through its CLI (the most stable cross-version interface) and
read back the Markdown it writes. MinerU is imported/located lazily so the rest
of the pipeline works even when MinerU is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from src.config import EXTRACTION_MAX_PAGES
from src.extraction.base import BaseExtractionEngine


# MinerU pins old pdfminer-six / pypdfium2 that conflict with pdfplumber+docling,
# so it CANNOT live in the project venv. It is installed in isolation (e.g.
# `uv tool install "mineru[core]"`) and invoked through its CLI. We therefore
# detect MinerU by locating its executable, not by importing it.
def _find_mineru_executable() -> str | None:
    """Return the MinerU CLI path if installed (PATH or common tool dirs)."""
    found = shutil.which("mineru")
    if found:
        return found
    candidates = [
        Path(sys.executable).parent / "mineru.exe",
        Path(sys.executable).parent / "mineru",
        Path.home() / ".local" / "bin" / "mineru.exe",
        Path.home() / ".local" / "bin" / "mineru",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


class MinerULayoutEngine(BaseExtractionEngine):
    """Layout + formula extraction using the MinerU toolchain."""

    name = "layout_mineru"

    def __init__(self, max_pages: int | None = EXTRACTION_MAX_PAGES):
        self.max_pages = max_pages

    @staticmethod
    def is_available() -> bool:
        """True if the MinerU CLI can be located in this environment."""
        return _find_mineru_executable() is not None

    @staticmethod
    def _executable() -> str:
        exe = _find_mineru_executable()
        return exe if exe else "mineru"  # last resort: rely on PATH

    def extract(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No PDF found at '{path}'.")
        if not self.is_available():
            raise RuntimeError(
                "MinerU is not installed. Install it (GPU recommended) or let the "
                "selector fall back to Docling."
            )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            cmd = [
                self._executable(),
                "-p", str(path),
                "-o", str(out_dir),
                "-m", "auto",
            ]
            if self.max_pages is not None:
                # MinerU page range is 0-indexed and inclusive.
                cmd += ["-s", "0", "-e", str(self.max_pages - 1)]

            subprocess.run(cmd, check=True, capture_output=True, text=True)

            markdown_files = sorted(out_dir.rglob("*.md"))
            if not markdown_files:
                raise RuntimeError("MinerU produced no Markdown output.")
            # The main document markdown is typically the largest file.
            best = max(markdown_files, key=lambda p: p.stat().st_size)
            return best.read_text(encoding="utf-8")
