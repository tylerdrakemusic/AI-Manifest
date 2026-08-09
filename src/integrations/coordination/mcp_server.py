"""Governed MCP operations for manifest todos."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

from mcp.server import FastMCP

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils import todos_db

_ALLOWED_OPERATIONS = frozenset({"todo.list_open", "todo.link_fr"})
_FORBIDDEN_ARGUMENTS = frozenset({"db", "sql"})


def link_todo_to_fr(todo_id: int, fr_id: str, confirmed: bool = False) -> bool:
    """Link a todo to an FR only after explicit caller confirmation."""
    if confirmed is not True:
        raise PermissionError("confirmation is required before linking a todo to an FR")
    return todos_db.link_todo_to_fr(todo_id, fr_id)


def invoke_todo_operation(operation: str, payload: Mapping[str, Any]) -> Any:
    """Invoke one allowlisted manifest-todo operation."""
    if operation not in _ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported todo operation: {operation}")
    if _FORBIDDEN_ARGUMENTS.intersection(payload):
        raise ValueError("database and SQL arguments are not supported")
    todos_db.use_worktree_aware_db_path(_REPO_ROOT)
    todos_db.init_db()
    allowed_fields = {
        "todo.list_open": {"project"},
        "todo.link_fr": {"todo_id", "fr_id", "confirmed"},
    }[operation]
    if set(payload) - allowed_fields:
        raise ValueError("unexpected arguments for todo operation")
    if operation == "todo.list_open":
        return todos_db.get_open_todos(payload.get("project"))
    return link_todo_to_fr(
        payload["todo_id"], payload["fr_id"], payload.get("confirmed", False)
    )


mcp = FastMCP(
    "manifest-coordination",
    instructions=(
        "Governed manifest-todo operations only. Todo-to-FR linkage requires "
        "explicit confirmation; arbitrary database names and SQL are unsupported."
    ),
)


@mcp.tool()
def list_open_todos(project: str | None = None) -> list[dict[str, Any]]:
    """List open manifest todos, optionally filtered by project."""
    return invoke_todo_operation("todo.list_open", {"project": project})


@mcp.tool()
def link_confirmed_todo_to_fr(todo_id: int, fr_id: str, confirmed: bool = False) -> bool:
    """Link a manifest todo to an FR after explicit confirmation."""
    return invoke_todo_operation(
        "todo.link_fr",
        {"todo_id": todo_id, "fr_id": fr_id, "confirmed": confirmed},
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")