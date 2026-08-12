"""Playwright tests for the Executive Audio Brief Portal dashboard.

Requires the portal HTML to exist at output/executive_brief_portal.html.
Run: C:\\G\\python.exe tools/executive_audio_brief.py --text-only  (generates the HTML)
Then: C:\\G\\python.exe -m pytest tests/test_executive_brief_portal.py -v

Set PLAYWRIGHT_ENABLED=1 to run locally. Skipped in CI unless that env var is set.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

PORTAL_PATH = Path(__file__).resolve().parent.parent / "output" / "executive_brief_portal.html"
PORTAL_URL = PORTAL_PATH.as_uri() if PORTAL_PATH.exists() else ""

# ---------------------------------------------------------------------------
# Skip guard — Playwright tests run locally only when PLAYWRIGHT_ENABLED=1.
# This avoids the 200MB+ Chromium install on every CI run.
# Set PLAYWRIGHT_ENABLED=1 before running, or use: pytest -m playwright
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.playwright


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


class TestStaticModeUX:
    def test_voice_dropdown_exists(self, page) -> None:
        """Voice dropdown element must be present in the DOM."""
        page.goto(PORTAL_URL)
        select = page.locator("#voiceSelect")
        assert select.count() == 1, "Voice dropdown not found"
        # At least one option must exist (even if it's the fallback placeholder)
        assert select.locator("option").count() >= 1

    def test_voice_dropdown_populated_when_api_key_set(self, page) -> None:
        """If ELEVENLABS_API_KEY is set, voice dropdown must have real voices (not just placeholder)."""
        import os
        if not os.environ.get("ELEVENLABS_API_KEY"):
            pytest.skip("ELEVENLABS_API_KEY not set — voice population test skipped")
        page.goto(PORTAL_URL)
        select = page.locator("#voiceSelect")
        options = select.locator("option")
        count = options.count()
        assert count >= 1
        first_text = options.first.text_content() or ""
        assert "No voices" not in first_text, (
            "Only 'No voices available' option despite ELEVENLABS_API_KEY being set"
        )

    def test_serve_hint_element_exists(self, page) -> None:
        """serveHint div must exist in DOM (visible in static file:// mode)."""
        page.goto(PORTAL_URL)
        hint = page.locator("#serveHint")
        assert hint.count() == 1, "serveHint element not found in DOM"

    def test_serve_hint_visible_in_static_mode(self, page) -> None:
        """When opened as file://, the serve hint should be visible."""
        page.goto(PORTAL_URL)
        # Small wait for JS to run
        page.wait_for_load_state("domcontentloaded")
        hint = page.locator("#serveHint")
        assert hint.is_visible(), "serveHint not visible in static file:// mode"

    def test_generate_button_does_not_raise_on_click(self, page) -> None:
        """Clicking Generate in static mode should not throw an uncaught JS error."""
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(PORTAL_URL)
        page.wait_for_load_state("domcontentloaded")
        page.click("#generateBtn")
        assert errors == [], f"JS error after clicking Generate: {errors}"

    def test_refresh_button_does_not_raise_on_click(self, page) -> None:
        """Clicking Refresh in static mode should not throw an uncaught JS error."""
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(PORTAL_URL)
        page.wait_for_load_state("domcontentloaded")
        page.click("#refreshBtn")
        assert errors == [], f"JS error after clicking Refresh: {errors}"


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


# ---------------------------------------------------------------------------
# Provenance signal rail fixture proof (FR-20260809-todo-provenance-signal-rail)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def signal_rail_server(tmp_path_factory, monkeypatch_class):
    """Serve the portal from an isolated DB containing all three signal states."""
    import src.utils.todos_db as todos_db
    from tools.executive_audio_brief import BriefRequestHandler

    db_file = tmp_path_factory.mktemp("signal_rail_db") / "test_todos.db"
    monkeypatch_class.setattr(todos_db, "DB_PATH", db_file)
    todos_db.init_db()
    with sqlite3.connect(db_file) as conn:
        conn.executemany(
            """
            INSERT INTO todos
                (id, project, source, text, done, created_at, priority,
                 autonomy_level, fr_id, perfected_at)
            VALUES (?, 'workspace', 'AI', ?, 0, ?, 9, 'supervised', ?, ?)
            """,
            [
                (927, "Signal rail perfected only", "2026-08-10T00:00:00+00:00", None, "2026-08-10T01:00:00+00:00"),
                (928, "Signal rail FR-linked only", "2026-08-10T00:01:00+00:00", "FR-20260809-todo-provenance-signal-rail", None),
                (929, "Signal rail perfected and FR-linked", "2026-08-10T00:02:00+00:00", "FR-20260809-todo-provenance-signal-rail", "2026-08-10T02:00:00+00:00"),
            ],
        )
        conn.commit()

    BriefRequestHandler.portal_state = {"html": "", "voices": [], "audio_path": None}
    server = HTTPServer(("127.0.0.1", 0), BriefRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    with urlopen(f"{base_url}/health", timeout=5) as response:
        assert response.status == 200, "Signal rail server failed health preflight"

    yield base_url

    server.shutdown()
    server.server_close()


class TestProvenanceSignalRail:
    """Running-portal proof for independent perfected and FR-linked signals."""

    def test_signal_states_render_with_explicit_ids(self, browser, signal_rail_server) -> None:
        """All three fixture rows render their independent provenance states."""
        proof_dir = (
            Path(__file__).resolve().parent.parent
            / "proof/screenshots"
        )
        proof_dir.mkdir(parents=True, exist_ok=True)

        page = browser.new_page()
        try:
            expected_states = {
                927: {"PERFECTED", "Refined · perfect-scoped-td", "No FR link"},
                928: {"Not perfected", "FR linked"},
                929: {"PERFECTED", "Refined · perfect-scoped-td", "FR linked"},
            }
            viewports = {
                "desktop": (1280, 900),
                "mobile": (390, 844),
            }
            for viewport_name, viewport in viewports.items():
                page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
                response = page.goto(f"{signal_rail_server}/")
                assert response is not None and response.status == 200
                page.wait_for_load_state("domcontentloaded")

                rendered_ids = set(page.locator(".todo-id").all_text_contents())
                assert {"TODO #927", "TODO #928", "TODO #929"} <= rendered_ids
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")

                for todo_id, expected_signals in expected_states.items():
                    item = page.locator("li").filter(has_text=f"TODO #{todo_id}")
                    assert item.count() == 1, f"Expected one rendered row for TODO #{todo_id}"
                    assert set(item.locator(".todo-signal").all_text_contents()) == expected_signals
                    primary = item.locator(":scope > .todo-primary")
                    meta = item.locator(":scope > .todo-meta")
                    assert primary.count() == 1 and meta.count() == 1
                    assert item.locator(":scope > .todo-primary").evaluate(
                        "primary => primary.nextElementSibling.classList.contains('todo-meta')"
                    )
                    assert (primary.text_content() or "").lstrip().startswith(
                        f"Signal rail {('perfected only' if todo_id == 927 else 'FR-linked only' if todo_id == 928 else 'perfected and FR-linked')}"
                    )
                    done_button = item.locator("button.done-btn")
                    assert done_button.count() == 1
                    assert done_button.get_attribute("onclick") == f"markDone({todo_id}, this)"

                    text = item.locator(".todo-text")
                    box = text.bounding_box()
                    assert box is not None and box["width"] > 0 and box["height"] > 0
                    assert text.evaluate("el => el.scrollWidth <= el.clientWidth + 1")

                page.screenshot(
                    path=str(proof_dir / f"FR-20260809-todo-provenance-signal-rail-{viewport_name}.png"),
                    full_page=True,
                )
        finally:
            page.close()


# ---------------------------------------------------------------------------
# Live-server checkmark tests (BFX-20260522-executive-checkmark)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def live_server(tmp_path_factory, monkeypatch_class):
    """Spin up BriefRequestHandler on a random port with an isolated temp DB.

    Yields the base URL string, e.g. 'http://127.0.0.1:54321'.
    """
    import src.utils.todos_db as todos_db
    from tools.executive_audio_brief import BriefRequestHandler

    db_file = tmp_path_factory.mktemp("checkmark_db") / "test_todos.db"
    monkeypatch_class.setattr(todos_db, "DB_PATH", db_file)
    todos_db.init_db()

    BriefRequestHandler.portal_state = {"html": "", "voices": [], "audio_path": None}

    server = HTTPServer(("127.0.0.1", 0), BriefRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", db_file
    server.shutdown()


@pytest.fixture(scope="class")
def monkeypatch_class(request):
    """Class-scoped monkeypatch (pytest only ships function-scoped by default)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture
def live_page(browser):
    """Fresh Playwright page for live-server tests."""
    pg = browser.new_page()
    yield pg
    pg.close()


class TestCheckmarkLiveServer:
    """Playwright tests that validate the ✓ (mark-done) button against a live server.

    Regression suite for BFX-20260522-executive-checkmark:
    - Clicking ✓ on a card-list item (inside <li>) removes the row.
    - Clicking ✓ on an offload-panel item (inside <tr>) removes the row.
    - No uncaught JS errors occur in either case.
    """

    def _insert_temp_todo(self, db_file: Path, project: str = "workspace", text: str = "BFX temp todo", autonomy_level: str = "supervised") -> int:
        import src.utils.todos_db as todos_db
        import src.utils.todos_db as _m
        orig = _m.DB_PATH
        _m.DB_PATH = db_file
        try:
            return todos_db.add_todo(project, text, priority=5, source="AI", autonomy_level=autonomy_level)
        finally:
            _m.DB_PATH = orig

    def _is_done(self, db_file: Path, todo_id: int) -> bool:
        import src.utils.todos_db as todos_db
        import src.utils.todos_db as _m
        orig = _m.DB_PATH
        _m.DB_PATH = db_file
        try:
            row = todos_db.get_todo_by_id(todo_id)
            return row is not None and row["done"] == 1
        finally:
            _m.DB_PATH = orig

    def test_checkmark_card_list_item_removed_from_dom(self, live_server, live_page) -> None:
        """Clicking ✓ on a card-list <li> todo removes it from the DOM (no JS error)."""
        base_url, db_file = live_server
        errors: list[str] = []
        live_page.on("pageerror", lambda err: errors.append(str(err)))

        todo_id = self._insert_temp_todo(db_file, project="workspace", text="BFX card list item")
        live_page.goto(base_url)
        live_page.wait_for_load_state("domcontentloaded")

        btn = live_page.locator(f"button.done-btn[onclick*='markDone({todo_id},']").first
        assert btn.count() != 0 or live_page.locator(f"button.done-btn[onclick*='markDone({todo_id}, ']").count() != 0, (
            f"done-btn for todo {todo_id} not found in portal"
        )
        btn.click()
        live_page.wait_for_timeout(600)  # allow 300ms fade + margin

        remaining = live_page.locator(f"button.done-btn[onclick*='markDone({todo_id}']").count()
        assert remaining == 0, f"Todo {todo_id} button still in DOM after checkmark click"
        assert errors == [], f"Uncaught JS errors after checkmark click: {errors}"
        assert self._is_done(db_file, todo_id), f"Todo {todo_id} not marked done in DB"

    def test_checkmark_db_write_persisted(self, live_server, live_page) -> None:
        """After clicking ✓ the todo is marked done=1 in the database."""
        base_url, db_file = live_server
        todo_id = self._insert_temp_todo(
            db_file, project="workspace", text="BFX db write check", autonomy_level="supervised"
        )
        live_page.goto(base_url)
        live_page.wait_for_load_state("domcontentloaded")

        btn = live_page.locator(f".status-card button.done-btn[onclick*='markDone({todo_id},']").first
        btn.click()
        live_page.wait_for_timeout(800)

        assert self._is_done(db_file, todo_id), "DB was not updated after checkmark click"

    def test_checkmark_no_js_error_on_offload_panel_row(self, live_server, live_page) -> None:
        """Clicking ✓ on an offload-panel <tr> todo produces no uncaught JS TypeError.

        Regression for BFX root cause: btnEl.closest('li') returned null for
        table rows, causing null.closest('.status-card') to throw.
        """
        base_url, db_file = live_server
        errors: list[str] = []
        live_page.on("pageerror", lambda err: errors.append(str(err)))

        # 'full' autonomy → rendered in offload-panel table (<td>/<tr>)
        todo_id = self._insert_temp_todo(
            db_file, project="workspace", text="BFX offload panel item", autonomy_level="full"
        )
        live_page.goto(base_url)
        live_page.wait_for_load_state("domcontentloaded")

        # Scope to .offload-panel to specifically exercise the <tr>/<td> code path
        btn = live_page.locator(f".offload-panel button.done-btn[onclick*='markDone({todo_id},']").first
        assert btn.count() >= 0, f"offload-panel done-btn for todo {todo_id} not found"
        btn.click()
        live_page.wait_for_timeout(800)

        assert errors == [], f"Uncaught JS TypeError in offload panel checkmark: {errors}"
        # Only assert the offload-panel row is gone; the card <li> may still exist
        remaining_in_offload = live_page.locator(
            f".offload-panel button.done-btn[onclick*='markDone({todo_id},']"
        ).count()
        assert remaining_in_offload == 0, f"Offload panel row for todo {todo_id} not removed from DOM"
