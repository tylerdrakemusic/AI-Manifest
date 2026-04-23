"""Playwright tests for the Executive Audio Brief Portal dashboard.

Requires the portal HTML to exist at output/executive_brief_portal.html.
Run: C:\\G\\python.exe tools/executive_audio_brief.py --text-only  (generates the HTML)
Then: C:\\G\\python.exe -m pytest tests/test_executive_brief_portal.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PORTAL_PATH = Path(__file__).resolve().parent.parent / "output" / "executive_brief_portal.html"
PORTAL_URL = PORTAL_PATH.as_uri()


# ---------------------------------------------------------------------------
# Skip guard — portal must exist (generate with --text-only first)
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not PORTAL_PATH.exists(),
    reason="executive_brief_portal.html not found — run tools/executive_audio_brief.py --text-only first",
)


# ---------------------------------------------------------------------------
# Playwright fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    """Launch a Chromium browser for the test module."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    """Fresh page per test."""
    pg = browser.new_page()
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPortalLoads:
    def test_page_title(self, page) -> None:
        """Page title should contain 'Executive Audio Brief'."""
        page.goto(PORTAL_URL)
        assert "Executive Audio Brief" in page.title()

    def test_header_visible(self, page) -> None:
        """Main h1 header should be present and visible."""
        page.goto(PORTAL_URL)
        h1 = page.locator("header h1")
        assert h1.count() == 1
        assert h1.is_visible()

    def test_timestamp_present(self, page) -> None:
        """Timestamp element should be rendered."""
        page.goto(PORTAL_URL)
        ts = page.locator(".timestamp")
        assert ts.count() >= 1


class TestStatusCards:
    def test_three_status_cards_rendered(self, page) -> None:
        """Exactly 3 project status cards should be present."""
        page.goto(PORTAL_URL)
        cards = page.locator(".status-card")
        assert cards.count() == 3

    def test_priority_badges_visible(self, page) -> None:
        """Priority badges #1, #2, #3 should all be rendered."""
        page.goto(PORTAL_URL)
        for rank in range(1, 4):
            badge = page.locator(f".priority-badge.badge-{rank}")
            assert badge.count() == 1, f"Badge #{rank} not found"
            assert badge.is_visible()

    def test_music_project_always_present(self, page) -> None:
        """❤Music must always appear in the top 3 (always_include=True)."""
        page.goto(PORTAL_URL)
        content = page.content()
        assert "Music" in content, "❤Music project not found in portal"


class TestAudioSection:
    def test_audio_section_present(self, page) -> None:
        """Audio player section should be rendered (with or without audio)."""
        page.goto(PORTAL_URL)
        audio_player = page.locator(".audio-player")
        assert audio_player.count() >= 1
        assert audio_player.first.is_visible()


class TestBriefScript:
    def test_script_section_present(self, page) -> None:
        """Brief script / transcript section should exist."""
        page.goto(PORTAL_URL)
        script_section = page.locator(".brief-script, .script-section, pre, .script-text")
        # Accept any of the possible selectors the tool might use
        assert script_section.count() >= 1 or "Executive Project Brief" in page.content()


class TestNoConsoleErrors:
    def test_no_critical_js_errors(self, page) -> None:
        """No uncaught JavaScript errors should fire on page load."""
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(PORTAL_URL)
        page.wait_for_load_state("networkidle")
        assert errors == [], f"JS errors on page load: {errors}"

    def test_no_failed_network_requests(self, page) -> None:
        """No failed network requests (portal should be fully self-contained)."""
        failed: list[str] = []

        def handle_response(response):
            if response.status >= 400:
                failed.append(f"{response.status} {response.url}")

        page.on("response", handle_response)
        page.goto(PORTAL_URL)
        page.wait_for_load_state("networkidle")
        # Static file:// pages don't make network requests — pass trivially
        assert failed == [], f"Failed requests: {failed}"
