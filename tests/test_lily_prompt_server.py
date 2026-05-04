"""Tests for the Flask HTTP endpoints in tools/lily/lily_prompt_server.py.

Endpoints tested:
    GET  /lily/prompt          → 200 JSON {"positive_prompt": "..."}
    POST /lily/prompt          → 200 JSON {"ok": true}  |  400 on empty body
    GET  /lily/portrait/regen  → 200 JSON {"status": "ok", "path": "..."}

All external I/O (DB, portrait generation) is mocked — no live HF / DALL-E calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Bootstrap project root
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import the Flask app from the server module
_SERVER_MODULE = str(_REPO_ROOT / "tools" / "lily" / "lily_prompt_server.py")
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("lily_prompt_server", _SERVER_MODULE)
_server_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_server_mod)  # type: ignore[union-attr]

app = _server_mod.app
app.config["TESTING"] = True


# ---------------------------------------------------------------------------
# Fixture: Flask test client
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /lily/prompt
# ---------------------------------------------------------------------------

class TestGetPrompt:
    def test_returns_active_positive_prompt(self, client) -> None:
        with patch.object(_server_mod, "get_active_prompt", return_value=("hello portrait", "no negative")):
            resp = client.get("/lily/prompt")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["positive_prompt"] == "hello portrait"

    def test_returns_500_when_db_raises(self, client) -> None:
        with patch.object(_server_mod, "get_active_prompt", side_effect=RuntimeError("DB missing")):
            resp = client.get("/lily/prompt")
        assert resp.status_code == 500
        assert "DB missing" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# POST /lily/prompt
# ---------------------------------------------------------------------------

class TestPostPrompt:
    def test_updates_prompt_and_returns_ok(self, client) -> None:
        with patch.object(_server_mod, "update_active_prompt") as mock_update:
            resp = client.post(
                "/lily/prompt",
                json={"positive_prompt": "brand new prompt"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        mock_update.assert_called_once_with("brand new prompt")

    def test_returns_400_when_positive_prompt_missing(self, client) -> None:
        resp = client.post("/lily/prompt", json={}, content_type="application/json")
        assert resp.status_code == 400
        assert "positive_prompt" in resp.get_json()["error"]

    def test_returns_400_when_body_empty_string(self, client) -> None:
        resp = client.post(
            "/lily/prompt",
            json={"positive_prompt": "   "},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_returns_500_when_db_raises(self, client) -> None:
        with patch.object(_server_mod, "update_active_prompt", side_effect=RuntimeError("DB gone")):
            resp = client.post(
                "/lily/prompt",
                json={"positive_prompt": "something"},
                content_type="application/json",
            )
        assert resp.status_code == 500
        assert "DB gone" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# GET /lily/portrait/regen
# ---------------------------------------------------------------------------

class TestRegenPortrait:
    def test_regen_returns_ok_with_path(self, client, tmp_path: Path) -> None:
        new_portrait = tmp_path / "lily_portrait_2026-05-03.png"
        new_portrait.write_bytes(b"fake png")

        with (
            patch.object(_server_mod, "_today_cache_path", return_value=tmp_path / "nonexistent.png"),
            patch.object(_server_mod, "_IMAGE_CACHE_DIR", tmp_path),
            patch.object(_server_mod, "get_daily_portrait", return_value=new_portrait),
        ):
            resp = client.get("/lily/portrait/regen")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert str(new_portrait) in data["path"]

    def test_regen_deletes_existing_cache_before_regen(self, client, tmp_path: Path) -> None:
        today_png = tmp_path / "lily_portrait_today.png"
        today_png.write_bytes(b"old portrait data")
        new_portrait = tmp_path / "lily_portrait_new.png"
        new_portrait.write_bytes(b"new portrait data")

        deleted: list[Path] = []

        def _fake_cache_path():
            return today_png

        original_unlink = Path.unlink

        def _tracking_unlink(self, missing_ok=False):  # type: ignore[override]
            deleted.append(self)
            original_unlink(self, missing_ok=missing_ok)

        with (
            patch.object(_server_mod, "_today_cache_path", side_effect=_fake_cache_path),
            patch.object(_server_mod, "_IMAGE_CACHE_DIR", tmp_path),
            patch.object(_server_mod, "get_daily_portrait", return_value=new_portrait),
            patch.object(Path, "unlink", _tracking_unlink),
        ):
            resp = client.get("/lily/portrait/regen")

        assert resp.status_code == 200
        assert today_png in deleted

    def test_regen_returns_500_when_portrait_generation_fails(self, client, tmp_path: Path) -> None:
        with (
            patch.object(_server_mod, "_today_cache_path", return_value=tmp_path / "no.png"),
            patch.object(_server_mod, "_IMAGE_CACHE_DIR", tmp_path),
            patch.object(_server_mod, "get_daily_portrait", side_effect=Exception("API failure")),
        ):
            resp = client.get("/lily/portrait/regen")

        assert resp.status_code == 500
        assert "API failure" in resp.get_json()["error"]
