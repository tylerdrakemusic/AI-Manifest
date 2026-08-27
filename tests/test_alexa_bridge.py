"""Tests for the Alexa bridge — unit-level, no real Alexa requests."""
import sqlite3
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from integrations.alexa.alexa_bridge import (
        _resolve_project,
        _insert_todo,
        _query_todos,
        VALID_PROJECTS,
    )
except Exception as e:  # oscrypto/certvalidator may fail on some CI runners
    pytest.skip(f"alexa SDK not importable: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    db = str(tmp_path / "todos.db")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE todos (
            id INTEGER PRIMARY KEY,
            project TEXT NOT NULL,
            source TEXT NOT NULL,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 5,
            autonomy_level TEXT NOT NULL DEFAULT 'supervised',
            context_snapshot TEXT,
            fr_id TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# _resolve_project
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spoken,expected", [
    ("workspace", "workspace"),
    ("music", "music"),
    ("sigma capital", "sigmacapital"),
    ("capital", "sigmacapital"),
    ("quantum", "quantum"),
    ("ai manifest", "aimanifest"),
    ("life", "life"),
    ("infinite life", "life"),
    ("workspace", "workspace"),
])
def test_resolve_project_known(spoken, expected):
    assert _resolve_project(spoken) == expected


def test_resolve_project_unknown_returns_none():
    assert _resolve_project("nonsense project xyz") is None


def test_resolve_project_case_insensitive():
    assert _resolve_project("WORKSPACE") == "workspace"
    assert _resolve_project("Music") == "music"


# ---------------------------------------------------------------------------
# _insert_todo / _query_todos
# ---------------------------------------------------------------------------

def test_insert_and_query_todo(tmp_db):
    with patch("integrations.alexa.alexa_bridge.DB_PATH", tmp_db):
        _insert_todo("fix the auth bug", "workspace", 8)
        rows = _query_todos("workspace")

    assert len(rows) == 1
    assert rows[0][0] == "fix the auth bug"
    assert rows[0][1] == 8


def test_query_todos_empty(tmp_db):
    with patch("integrations.alexa.alexa_bridge.DB_PATH", tmp_db):
        rows = _query_todos("quantum")
    assert rows == []


def test_query_todos_ordered_by_priority(tmp_db):
    with patch("integrations.alexa.alexa_bridge.DB_PATH", tmp_db):
        _insert_todo("low prio task", "workspace", 2)
        _insert_todo("high prio task", "workspace", 9)
        _insert_todo("mid prio task", "workspace", 5)
        rows = _query_todos("workspace")

    assert rows[0][0] == "high prio task"
    assert rows[1][0] == "mid prio task"
    assert rows[2][0] == "low prio task"


def test_query_todos_respects_done_flag(tmp_db):
    conn = sqlite3.connect(tmp_db)
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO todos (project, source, text, done, created_at, priority, autonomy_level) VALUES (?,?,?,?,?,?,?)",
        ("workspace", "alexa", "already done", 1, datetime.now(timezone.utc).isoformat(), 10, "supervised"),
    )
    conn.commit()
    conn.close()

    with patch("integrations.alexa.alexa_bridge.DB_PATH", tmp_db):
        rows = _query_todos("workspace")

    assert rows == []


def test_query_todos_limit(tmp_db):
    with patch("integrations.alexa.alexa_bridge.DB_PATH", tmp_db):
        for i in range(10):
            _insert_todo(f"task {i}", "workspace", i)
        rows = _query_todos("workspace", limit=5)

    assert len(rows) == 5
