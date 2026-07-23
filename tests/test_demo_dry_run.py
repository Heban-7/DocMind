"""Smoke test wrapping the offline Phase 4 demo dry-run."""

from __future__ import annotations

from pathlib import Path

from run_demo_dry_run import run_offline_demo


def test_offline_demo_dry_run(tmp_path: Path):
    result = run_offline_demo(work_dir=tmp_path / "demo")
    assert result["ok"] is True
    assert result["answer_citations"] >= 1
    assert result["verified_status"] == "verified"
    assert result["unverifiable_status"] == "unverifiable"
