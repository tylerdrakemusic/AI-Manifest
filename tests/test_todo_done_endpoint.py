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
from urllib.parse import urlsplit

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


def _post_json(
    url: str,
    payload: dict,
    *,
    origin: str | None = None,
    include_origin: bool = True,
) -> tuple[int, dict]:
    """POST JSON and return (status_code, response_body_dict)."""
    data = json.dumps(payload).encode("utf-8")
    parsed_url = urlsplit(url)
    headers = {"Content-Type": "application/json"}
    if include_origin:
        headers["Origin"] = origin or f"{parsed_url.scheme}://{parsed_url.netloc}"
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
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

    def test_done_closes_readiness_blocked_parent_and_descendants(self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        parent = todos_db.insert_todo("music", "AI", "Blocked parent")
        child = todos_db.insert_todo("music", "AI", "Blocked child", parent_id=parent)
        grandchild = todos_db.insert_todo("music", "AI", "Blocked grandchild", parent_id=child)
        prerequisite = todos_db.insert_todo("music", "AI", "Blocking prerequisite")
        todos_db.link_prerequisite(parent, prerequisite)

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": parent})

        assert status == 200
        assert body["ok"] is True
        assert body["affected_ids"] == [parent, child, grandchild]
        assert body["affected_count"] == 3
        assert all(todos_db.get_todo_by_id(todo_id)["done"] == 1 for todo_id in (parent, child, grandchild))
        assert todos_db.get_todo_by_id(prerequisite)["done"] == 0

    def test_cross_origin_force_request_is_rejected_without_mutation(
        self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        parent = todos_db.insert_todo("music", "AI", "Blocked parent")
        prerequisite = todos_db.insert_todo("music", "AI", "Blocking prerequisite")
        todos_db.link_prerequisite(parent, prerequisite)

        status, body = _post_json(
            f"{todo_server}/api/todo/done",
            {"id": parent, "force": True},
            origin="https://attacker.example",
        )

        assert status == 403
        assert body["ok"] is False
        assert todos_db.get_todo_by_id(parent)["done"] == 0
        assert todos_db.get_todo_by_id(prerequisite)["done"] == 0

    def test_done_rejects_client_force_field_as_invalid_shape(
        self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        row_id = todos_db.insert_todo("music", "AI", "Client force field")

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": row_id, "force": True})

        assert status == 400
        assert body["ok"] is False
        assert todos_db.get_todo_by_id(row_id)["done"] == 0

    def test_done_rolls_back_tree_when_descendant_update_fails(
        self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        parent = todos_db.insert_todo("music", "AI", "Parent")
        child = todos_db.insert_todo("music", "AI", "Failing child", parent_id=parent)
        prerequisite = todos_db.insert_todo("music", "AI", "Blocking prerequisite")
        todos_db.link_prerequisite(parent, prerequisite)
        with todos_db.get_connection() as conn:
            conn.execute(
                f"""CREATE TRIGGER fail_dashboard_close
                    BEFORE UPDATE OF done ON todos WHEN OLD.id = {child}
                    BEGIN SELECT RAISE(ABORT, 'injected close failure'); END"""
            )

        status, body = _post_json(f"{todo_server}/api/todo/done", {"id": parent})

        assert status == 500
        assert body["error"] == "todo could not be closed"
        assert todos_db.get_todo_by_id(parent)["done"] == 0
        assert todos_db.get_todo_by_id(child)["done"] == 0
        assert todos_db.get_todo_by_id(prerequisite)["done"] == 0

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

    def test_done_rejects_missing_origin_without_mutation(
        self, todo_server: str, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.utils.todos_db as todos_db
        monkeypatch.setattr(todos_db, "DB_PATH", tmp_db)
        row_id = todos_db.insert_todo("music", "AI", "Missing origin")

        status, body = _post_json(
            f"{todo_server}/api/todo/done", {"id": row_id}, include_origin=False
        )

        assert status == 403
        assert body["ok"] is False
        assert todos_db.get_todo_by_id(row_id)["done"] == 0


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
