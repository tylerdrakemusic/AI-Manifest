"""Unit tests for executive_audio_brief.py (non-Playwright).

BFX-20260530-remove-live-dash-chrome
"""
from __future__ import annotations

from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
_PORTAL_OUTPUT = Path(__file__).resolve().parent.parent / "output" / "executive_brief_portal.html"


def test_executive_audio_brief_source_has_no_static_banner() -> None:
    """BFX-20260530-remove-live-dash-chrome: source template must not contain static-banner."""
    src = (_TOOLS / "executive_audio_brief.py").read_text(encoding="utf-8")
    assert "static-banner" not in src, "executive_audio_brief.py still defines static-banner CSS/element"
    assert "Static snapshot" not in src, "executive_audio_brief.py still contains 'Static snapshot' text"


def test_executive_brief_portal_output_has_no_static_banner() -> None:
    """BFX-20260530-remove-live-dash-chrome: generated output HTML must not contain the toast."""
    if not _PORTAL_OUTPUT.exists():
        import pytest
        pytest.skip(f"Portal not generated — run executive_audio_brief.py first: {_PORTAL_OUTPUT}")
    html = _PORTAL_OUTPUT.read_text(encoding="utf-8")
    assert "static-banner" not in html, "executive_brief_portal.html still contains static-banner"
    assert "Static snapshot" not in html, "executive_brief_portal.html still contains 'Static snapshot' text"
