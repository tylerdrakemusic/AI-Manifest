"""LLM-based priority scorer for todo items.

Tries Ollama (local) first, falls back to OpenAI GPT-4.1-mini.
Returns an int 1–10. Never raises — returns 5 (neutral) on total failure.

The scorer receives the existing open todos for the same project (with their
current priorities) so the LLM can score relatively — calibrated against the
existing scale rather than scoring in a vacuum.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are prioritizing work items for the {project} project on a scale of 1–10 \
(10 = most urgent/impactful, 1 = lowest priority).

Here are the existing open todos for this project and their current priorities, \
so you can score relative to them:
{existing_context}

New todo to score: "{text}"

Respond with only a single integer 1–10. No explanation."""

_NO_EXISTING_TEMPLATE = """\
On a scale of 1–10 (10 = most urgent/impactful), rate the priority of this \
todo item for the {project} project.

Todo: "{text}"

Respond with only a single integer 1–10. No explanation."""


def _format_existing_context(existing_todos: list[dict[str, Any]]) -> str:
    """Format existing todos into a readable context block for the prompt."""
    if not existing_todos:
        return "(none yet)"
    lines = []
    for t in existing_todos[:20]:  # cap at 20 to stay within token limits
        pri = t.get("priority", "?")
        text = t.get("text", "")[:120]
        lines.append(f"  [P{pri}] {text}")
    return "\n".join(lines)


def _extract_int(text: str) -> int | None:
    """Extract the first integer 1-10 from a string."""
    match = re.search(r"\b([1-9]|10)\b", text.strip())
    if match:
        return int(match.group(1))
    return None


def _build_prompt(text: str, project: str, existing_todos: list[dict[str, Any]]) -> str:
    if existing_todos:
        return _PROMPT_TEMPLATE.format(
            project=project,
            existing_context=_format_existing_context(existing_todos),
            text=text,
        )
    return _NO_EXISTING_TEMPLATE.format(project=project, text=text)


def _score_via_ollama(text: str, project: str, existing_todos: list[dict[str, Any]]) -> int:
    """Try Ollama local LLM. Raises on failure."""
    import urllib.request
    import json as _json

    prompt = _build_prompt(text, project, existing_todos)
    payload = _json.dumps(
        {"model": "llama3", "prompt": prompt, "stream": False}
    ).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = _json.loads(resp.read().decode("utf-8"))

    raw = body.get("response", "")
    value = _extract_int(raw)
    if value is None:
        raise ValueError(f"Ollama returned unparseable response: {raw!r}")
    return value


def _score_via_openai(text: str, project: str, existing_todos: list[dict[str, Any]]) -> int:
    """Try OpenAI GPT-4.1-mini. Raises on failure."""
    import openai  # type: ignore[import]

    api_key = os.environ.get("OPENAPI_TOKEN")
    if not api_key:
        raise RuntimeError("OPENAPI_TOKEN env var not set")

    client = openai.OpenAI(api_key=api_key, timeout=10)
    prompt = _build_prompt(text, project, existing_todos)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    value = _extract_int(raw)
    if value is None:
        raise ValueError(f"OpenAI returned unparseable response: {raw!r}")
    return value


def score_priority(
    text: str,
    project: str,
    existing_todos: list[dict[str, Any]] | None = None,
) -> int:
    """Score a todo item's priority 1–10 relative to existing open todos.

    Args:
        text: The new todo text to score.
        project: Project key (e.g. 'music', 'life', 'workspace').
        existing_todos: Open todos for this project (from get_open_todos).
                        Passed to the LLM as calibration context. If None
                        or empty, the LLM scores without context.

    Returns int 1–10. Never raises — returns 5 on total failure.
    """
    todos = existing_todos or []
    try:
        value = _score_via_ollama(text, project, todos)
        logger.debug("Ollama scored '%s' → %d", text[:40], value)
        return value
    except Exception as e:
        logger.debug("Ollama failed (%s), trying OpenAI", e)

    try:
        value = _score_via_openai(text, project, todos)
        logger.debug("OpenAI scored '%s' → %d", text[:40], value)
        return value
    except Exception as e:
        logger.warning(
            "Both LLM scorers failed for '%s': %s — defaulting to 5", text[:40], e
        )
        return 5
