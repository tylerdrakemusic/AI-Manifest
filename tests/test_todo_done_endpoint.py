"""HTTP integration tests for the /api/todo/done endpoint.

Spins up a real HTTPServer in a background thread and hits the endpoint with
urllib to confirm end-to-end behaviour without any browser / Playwright deps.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect todos_db.DB_PATH to a fresh temp file for each test."""
    db_file = tmp_path / "test_todos.db"
    import src.utils.todos_db as todos_db
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    todos_db.init_db()
    yield db_file


@pytest.fixture()
def todo_server(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Start a BriefRequestHandler server on a random free port.

    Yields the base URL string, e.g. 'http://127.0.0.1:54321'.
    Server is shut down after the test.
    """
    from tools.executive_audio_brief import BriefRequestHandler

    # Minimal portal state — _serve_portal won't be called by these tests
    BriefRequestHandler.portal_state = {
        "html": "<h1>test</h1>",
        "voices": [],
        "audio_path": None,
    }

    server = HTTPServer(("127.0.0.1", 0), BriefRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    """POST JSON and return (status_code, response_body_dict)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTodoDoneEndpoint:
    def test_returns_200_for_valid_open_todo(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/todo/done with a valid open todo ID returns HTTP 200 + ok:true."""
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        row_id = todos_db.insert_todo("music", "AI", "Register with ASCAP")

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": row_id})

        assert status == 200
        assert body.get("ok") is True
        assert body["affected_count"] == 1
        assert body["affected_ids"] == [row_id]

    def test_done_closes_open_parent_descendants(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        parent = todos_db.insert_todo("music", "AI", "Parent")
        child = todos_db.insert_todo("music", "AI", "Child", parent_id=parent)

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": parent})

        assert status == 200
        assert body["affected_ids"] == [parent, child]
        assert todos_db.get_todo_by_id(child)["done"] == 1

    def test_done_rejects_blocked_parent_without_force_escape(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        parent = todos_db.insert_todo("music", "AI", "Blocked parent")
        blocker = todos_db.insert_todo("music", "AI", "Blocking prerequisite")
        todos_db.link_prerequisite(parent, blocker)

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": parent, "force": True})

        assert status == 409
        assert body["ok"] is False
        assert todos_db.get_todo_by_id(parent)["done"] == 0

    def test_db_write_confirmed_after_200(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """After a successful mark-done HTTP call the todo is no longer in open list."""
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        row_id = todos_db.insert_todo("music", "AI", "DB write check")

        _post_json(f"{todo_server}/api/todo/done", {"id": row_id})

        open_todos = todos_db.get_open_todos()
        assert all(t["id"] != row_id for t in open_todos), "todo should be removed from open list"

    def test_returns_409_for_already_done_todo(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/todo/done for an already-done todo returns HTTP 409."""
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        row_id = todos_db.insert_todo("music", "AI", "Already done task")
        todos_db.mark_done(row_id)

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": row_id})

        assert status == 409
        assert body.get("ok") is False

    def test_returns_404_for_nonexistent_todo(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/todo/done for a non-existent ID returns HTTP 404."""
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": 99999})

        assert status == 404
        assert body.get("ok") is False

    def test_dashboard_completion_enforces_readiness_without_changing_prerequisite_edge(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A blocked dashboard completion is rejected without changing its prerequisite edge."""
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        prerequisite = todos_db.insert_todo("music", "AI", "Still pending")
        dependent = todos_db.insert_todo("music", "AI", "Complete from dashboard")
        todos_db.link_prerequisite(dependent, prerequisite)

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": dependent})

        assert status == 409
        assert body.get("ok") is False
        completed = todos_db.get_todo_by_id(dependent)
        assert completed is not None
        assert completed["done"] == 0
        assert completed["closed_at"] is None
        assert completed["closure_reason"] is None
        assert [row["id"] for row in todos_db.get_required_todos(dependent)] == [prerequisite]


class TestTodoCancelEndpoint:
    def test_cancel_closes_open_parent_descendants(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        parent = todos_db.insert_todo("music", "AI", "Parent")
        child = todos_db.insert_todo("music", "AI", "Child", parent_id=parent)

        status, body = _post_json(f"{todo_server}/api/todo/cancel", {"id": parent})

        assert status == 200
        assert body["affected_ids"] == [parent, child]
        assert todos_db.get_todo_by_id(child)["closure_reason"] == "cancelled"

    def test_cancel_persists_terminal_outcome(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/todo/cancel closes an open todo as cancelled."""
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        row_id = todos_db.insert_todo("music", "AI", "Cancel through API")

        status, body = _post_json(f"{todo_server}/api/todo/cancel", {"id": row_id})

        assert status == 200
        assert body.get("ok") is True
        row = todos_db.get_todo_by_id(row_id)
        assert row is not None
        assert row["done"] == 1
        assert row["closure_reason"] == "cancelled"
        assert row["closed_at"] is not None
