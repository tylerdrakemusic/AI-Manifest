"""Governed MCP operations for manifest todos."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

from mcp.server.fastmcp import FastMCP

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils import todos_db

_ALLOWED_OPERATIONS = frozenset({
    "todo.list_open", "todo.link_fr", "todo.link_prerequisite",
    "todo.required", "todo.required_by", "todo.readiness",
    "todo.related", "todo.fr_links", "todo.decompose",
    "todo.create", "todo.read", "todo.draft_scope",
    "todo.set_decision_metadata", "todo.get_decision_metadata",
    "todo.get_decision_assessments", "todo.priority_guidance",
    "todo.set_priority", "todo.update", "todo.graph", "todo.create_children_batch",
})
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
        "todo.link_prerequisite": {"todo_id", "prerequisite_id", "allowed_terminal_states", "confirmed"},
        "todo.required": {"todo_id"},
        "todo.required_by": {"todo_id"},
        "todo.readiness": {"todo_id"},
        "todo.related": {"todo_id"},
        "todo.fr_links": {"todo_id"},
        "todo.decompose": {"parent_id", "children", "confirmed"},
        "todo.create": {
            "project", "text", "priority", "source", "autonomy_level",
            "rationale", "implementation_hints", "context_snapshot",
            "estimated_effort", "dependencies", "parent_id", "confirmed",
        },
        "todo.read": {"todo_id"},
        "todo.draft_scope": {"todo_id", "scope"},
        "todo.set_decision_metadata": {"todo_id", "metadata", "assessed_by", "confirmed"},
        "todo.get_decision_metadata": {"todo_id"},
        "todo.get_decision_assessments": {"todo_id"},
        "todo.priority_guidance": {"todo_id"},
        "todo.set_priority": {"todo_id", "priority", "confirmed", "expected_version"},
        "todo.update": {
            "todo_id", "expected_version", "authenticated", "text", "priority",
            "autonomy_level", "rationale", "implementation_hints", "context_snapshot",
            "estimated_effort", "dependencies", "perfected_at",
        },
        "todo.graph": {"todo_id"},
        "todo.create_children_batch": {"parent_id", "children", "confirmed", "idempotency_key"},
    }[operation]
    if set(payload) - allowed_fields:
        raise ValueError("unexpected arguments for todo operation")
    if operation == "todo.list_open":
        return todos_db.get_open_todos(payload.get("project"))
    if operation == "todo.create":
        if "priority" in payload and payload.get("confirmed") is not True:
            raise PermissionError("confirmation is required before assigning a priority")
        values = {key: payload[key] for key in allowed_fields if key in payload}
        values.pop("confirmed", None)
        return todos_db.add_todo(**values)
    if operation == "todo.read":
        return todos_db.get_todo_response(payload["todo_id"])
    if operation == "todo.draft_scope":
        if todos_db.get_todo_by_id(payload["todo_id"]) is None:
            raise ValueError("todo not found")
        return {"todo_id": payload["todo_id"], "scope": payload["scope"], "draft": True}
    if operation == "todo.set_decision_metadata":
        if payload.get("confirmed") is not True:
            raise PermissionError("confirmation is required before writing decision metadata")
        todos_db.set_decision_metadata(
            payload["todo_id"], payload["metadata"], assessed_by=payload["assessed_by"]
        )
        return True
    if operation == "todo.get_decision_metadata":
        return todos_db.get_decision_metadata(payload["todo_id"])
    if operation == "todo.get_decision_assessments":
        return todos_db.get_decision_assessments(payload["todo_id"])
    if operation == "todo.priority_guidance":
        return todos_db.get_priority_guidance(payload["todo_id"])
    if operation == "todo.set_priority":
        if payload.get("confirmed") is not True:
            raise PermissionError("confirmation is required before changing priority")
        result = todos_db.update_priority(
            payload["todo_id"], payload["priority"], payload.get("expected_version")
        )
        if payload.get("expected_version") is not None:
            return todos_db.get_todo_response(payload["todo_id"])
        return result
    if operation == "todo.update":
        if payload.get("authenticated") is not True:
            raise PermissionError("authentication is required before updating a todo")
        if not isinstance(payload.get("expected_version"), str):
            raise ValueError("expected_version is required")
        if "priority" in payload:
            raise ValueError(
                "priority is a protected field for todo.update; use todo.set_priority"
            )
        fields = {key: value for key, value in payload.items() if key not in {
            "todo_id", "expected_version", "authenticated"
        }}
        todos_db.update_todo(payload["todo_id"], payload["expected_version"], fields)
        return todos_db.get_todo_response(payload["todo_id"])
    if operation == "todo.graph":
        return todos_db.get_todo_graph(payload["todo_id"])
    if operation == "todo.create_children_batch":
        return todos_db.create_children_batch(
            payload["parent_id"], payload["children"],
            confirmed=payload.get("confirmed") is True,
            idempotency_key=payload["idempotency_key"],
        )
    if operation == "todo.link_fr":
        return link_todo_to_fr(payload["todo_id"], payload["fr_id"], payload.get("confirmed", False))
    if operation == "todo.link_prerequisite":
        if payload.get("confirmed") is not True:
            raise PermissionError("confirmation is required before linking a prerequisite")
        return todos_db.link_prerequisite(
            payload["todo_id"], payload["prerequisite_id"], payload.get("allowed_terminal_states")
        )
    if operation == "todo.required":
        return todos_db.get_required_todos(payload["todo_id"])
    if operation == "todo.required_by":
        return todos_db.get_required_by_todos(payload["todo_id"])
    if operation == "todo.readiness":
        return todos_db.get_readiness(payload["todo_id"])
    if operation == "todo.related":
        return todos_db.get_related_todos(payload["todo_id"])
    if operation == "todo.fr_links":
        return todos_db.get_todo_fr_links(payload["todo_id"])
    if payload.get("confirmed") is not True:
        raise PermissionError("confirmation is required before decomposing a todo")
    return todos_db.decompose_todo(
        payload["parent_id"], payload["children"], allow_priority_override=True
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


@mcp.tool()
def link_confirmed_prerequisite(
    todo_id: int,
    prerequisite_id: int,
    allowed_terminal_states: list[str] | None = None,
    confirmed: bool = False,
) -> bool:
    """Add a prerequisite edge after explicit confirmation."""
    return invoke_todo_operation("todo.link_prerequisite", {
        "todo_id": todo_id,
        "prerequisite_id": prerequisite_id,
        "allowed_terminal_states": allowed_terminal_states,
        "confirmed": confirmed,
    })


@mcp.tool()
def todo_readiness(todo_id: int) -> dict[str, Any]:
    """Explain whether a manifest todo is ready for completion."""
    return invoke_todo_operation("todo.readiness", {"todo_id": todo_id})


@mcp.tool()
def create_todo(
    project: str,
    text: str,
    priority: int | None = None,
    source: str = "TYLER",
    autonomy_level: str = "supervised",
    confirmed: bool = False,
    rationale: str | None = None,
    implementation_hints: str | None = None,
    context_snapshot: str | None = None,
    estimated_effort: str | None = None,
    dependencies: str | None = None,
    parent_id: int | None = None,
) -> int:
    """Create a manifest todo, requiring confirmation for explicit priority."""
    if confirmed is not False and confirmed is not True:
        raise PermissionError("confirmation is required and must be literal True or False")
    payload: dict[str, Any] = {
        "project": project,
        "text": text,
        "source": source,
        "autonomy_level": autonomy_level,
        "confirmed": confirmed,
    }
    if parent_id is not None:
        payload["parent_id"] = parent_id
    if priority is not None:
        payload["priority"] = priority
    for key, value in {
        "rationale": rationale,
        "implementation_hints": implementation_hints,
        "context_snapshot": context_snapshot,
        "estimated_effort": estimated_effort,
        "dependencies": dependencies,
    }.items():
        if value is not None:
            payload[key] = value
    return invoke_todo_operation("todo.create", payload)


@mcp.tool()
def read_todo(todo_id: int) -> dict[str, Any]:
    """Read one manifest todo by id."""
    return invoke_todo_operation("todo.read", {"todo_id": todo_id})


@mcp.tool()
def draft_todo_scope(todo_id: int, scope: str) -> dict[str, Any]:
    """Return a non-persisting scope draft for a manifest todo."""
    return invoke_todo_operation("todo.draft_scope", {"todo_id": todo_id, "scope": scope})


@mcp.tool()
def set_todo_decision_metadata(
    todo_id: int,
    metadata: dict[str, Any],
    assessed_by: str,
    confirmed: bool = False,
) -> bool:
    """Persist canonical decision metadata after explicit confirmation."""
    return invoke_todo_operation("todo.set_decision_metadata", {
        "todo_id": todo_id,
        "metadata": metadata,
        "assessed_by": assessed_by,
        "confirmed": confirmed,
    })


@mcp.tool()
def get_todo_decision_metadata(todo_id: int) -> dict[str, Any] | None:
    """Read current canonical decision metadata for a manifest todo."""
    return invoke_todo_operation("todo.get_decision_metadata", {"todo_id": todo_id})


@mcp.tool()
def get_todo_decision_assessments(todo_id: int) -> list[dict[str, Any]]:
    """Read append-only decision assessments for a manifest todo."""
    return invoke_todo_operation("todo.get_decision_assessments", {"todo_id": todo_id})


@mcp.tool()
def todo_priority_guidance(todo_id: int) -> dict[str, Any]:
    """Return advisory priority guidance without mutating a todo."""
    return invoke_todo_operation("todo.priority_guidance", {"todo_id": todo_id})


@mcp.tool()
def set_todo_priority(
    todo_id: int,
    priority: int,
    confirmed: bool = False,
    expected_version: str | None = None,
) -> bool | dict[str, Any]:
    """Change a todo priority after explicit confirmation."""
    return invoke_todo_operation("todo.set_priority", {
        "todo_id": todo_id,
        "priority": priority,
        "confirmed": confirmed,
        **({"expected_version": expected_version} if expected_version is not None else {}),
    })


@mcp.tool(name="todo.update")
def update_todo(
    todo_id: int,
    expected_version: str,
    authenticated: bool,
    text: str | None = None,
    autonomy_level: str | None = None,
    rationale: str | None = None,
    implementation_hints: str | None = None,
    context_snapshot: str | None = None,
    estimated_effort: str | None = None,
    dependencies: str | None = None,
    perfected_at: str | None = None,
) -> dict[str, Any]:
    """Update mutable todo fields through the authenticated public contract."""
    payload: dict[str, Any] = {
        "todo_id": todo_id,
        "expected_version": expected_version,
        "authenticated": authenticated,
    }
    for key, value in {
        "text": text,
        "autonomy_level": autonomy_level,
        "rationale": rationale,
        "implementation_hints": implementation_hints,
        "context_snapshot": context_snapshot,
        "estimated_effort": estimated_effort,
        "dependencies": dependencies,
        "perfected_at": perfected_at,
    }.items():
        if value is not None:
            payload[key] = value
    return invoke_todo_operation("todo.update", payload)


@mcp.tool(name="todo.graph")
def todo_graph(todo_id: int) -> dict[str, Any]:
    """Read a complete todo graph snapshot through the public contract."""
    return invoke_todo_operation("todo.graph", {"todo_id": todo_id})


@mcp.tool(name="todo.create_children_batch")
def create_children_batch(
    parent_id: int,
    children: list[dict[str, Any]],
    confirmed: bool,
    idempotency_key: str,
) -> list[int]:
    """Create a governed atomic child batch through the public contract."""
    return invoke_todo_operation("todo.create_children_batch", {
        "parent_id": parent_id,
        "children": children,
        "confirmed": confirmed,
        "idempotency_key": idempotency_key,
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")