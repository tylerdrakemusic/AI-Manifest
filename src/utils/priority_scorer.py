"""LLM-based priority scorer for todo items.

Tries Ollama (local) first, falls back to OpenAI GPT-4.1-mini, then uses a
deterministic heuristic scorer when both LLM paths fail.

Returns an int 1–10. Never raises — returns 5 (neutral) only as a last resort.

The scorer receives the existing open todos for the same project (with their
current priorities) so the LLM can score relatively — calibrated against the
existing scale rather than scoring in a vacuum.

Ollama configuration
--------------------
OLLAMA_BASE_URL : base URL of the Ollama server (default: http://localhost:11434)
OLLAMA_MODEL    : model tag to use (default: llama3.1:8b)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.integrations.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)

_PREFERRED_OLLAMA_MODELS = (
    "llama3.2:1b",
    "llama3.2",
    "llama3.1:8b",
    "llama3.1",
    "mistral:7b",
    "qwen2:0.5b",
)

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


def _preferred_ollama_models(client: OllamaClient) -> list[str]:
    """Return Ollama models to try, ordered from most to least preferred."""
    preferred: list[str] = []
    env_model = os.environ.get("OLLAMA_MODEL")
    if client.model:
        preferred.append(client.model)
    if env_model:
        preferred.append(env_model)
    preferred.extend(_PREFERRED_OLLAMA_MODELS)

    ordered: list[str] = []
    seen: set[str] = set()
    for model in preferred:
        if model and model not in seen:
            seen.add(model)
            ordered.append(model)
    return ordered


def _model_name_candidates(models: list[dict[str, Any]]) -> list[str]:
    """Extract model names from Ollama /api/tags responses."""
    names: list[str] = []
    for row in models:
        if not isinstance(row, dict):
            continue
        for key in ("name", "model"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
                break
    return names


def _model_base_name(model: str) -> str:
    return model.split(":", 1)[0].strip().lower()


def _select_local_model(client: OllamaClient) -> str | None:
    """Pick the best locally installed Ollama model, if any are available."""
    try:
        available = _model_name_candidates(client.list_models())
    except Exception as exc:
        logger.debug("Unable to inspect local Ollama models: %s", exc)
        return None

    if not available:
        return None

    available_set = set(available)
    preferred = _preferred_ollama_models(client)

    for target in preferred:
        if target in available_set:
            return target

    for target in preferred:
        target_base = _model_base_name(target)
        for candidate in available:
            if _model_base_name(candidate) == target_base:
                return candidate

    return available[0]


def _score_via_ollama(text: str, project: str, existing_todos: list[dict[str, Any]]) -> int:
    """Try Ollama local LLM via the mirrored OllamaClient. Raises on failure."""
    prompt = _build_prompt(text, project, existing_todos)
    client = OllamaClient()  # reads OLLAMA_BASE_URL / OLLAMA_MODEL from env
    model = _select_local_model(client) or client.model
    raw = client.generate(prompt, model=model)
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


def _heuristic_priority(
    text: str,
    project: str,
    existing_todos: list[dict[str, Any]] | None = None,
) -> int:
    """Score a todo with a deterministic rule-based fallback.

    The heuristic is intentionally simple: start from neutral priority 5, then
    add or subtract points for urgency, system-level scope, and maintenance-
    only wording. This keeps discovery output spread out when LLM scoring is
    unavailable.
    """
    _ = existing_todos  # Reserved for future calibration against current backlog.

    normalized = text.strip().lower()
    score = 5

    positive_rules: tuple[tuple[str, int], ...] = (
        (r"\blaunch(?:ed|ing)?\b|\bship(?:ped|ping)?\b|\bproduction\b|\breliab", 2),
        (r"\bsecurity\b|\bcompliance\b|\bunblock\b|\bincident\b|\bhotfix\b", 2),
        (r"\bintegration\b|\bpipeline\b|\bdashboard\b|\btelemetry\b|\bobservab", 1),
        (r"\bworkflow\b|\broadmap\b|\bautomation\b|\brollout\b|\bdelivery\b", 1),
        (r"\bcross-project\b|\bworkspace-wide\b|\bend-to-end\b|\ball projects\b|\bpublic-repo\b", 1),
    )
    negative_rules: tuple[tuple[str, int], ...] = (
        (r"\bdocs?\b|\bcleanup\b|\btypo\b|\brename\b|\brefactor\b", -2),
        (r"\blint\b|\bformat\b|\bcomment\b|\bspelling\b|\bminor\b", -1),
    )
    project_rules: dict[str, tuple[tuple[str, int], ...]] = {
        "music": (
            (r"\bradio\b|\baudience\b|\bstream\b|\blaunch\b", 2),
        ),
        "life": (
            (r"\bbiomarker\b|\bintervention\b|\bingest\b|\bhealth\b|\bclinical\b", 2),
        ),
        "quantum": (
            (r"\bbenchmark\b|\bexecution-policy\b|\bvariance\b|\bpolicy\b|\bqpu\b", 2),
        ),
        "ai_manifest": (
            (r"\bbrief\b|\bmcp\b|\bportal\b|\bvoice\b|\bexecutive\b", 2),
        ),
        "workspace": (
            (r"\bdiscovery\b|\btriage\b|\bscan\b|\bregistry\b|\broadmap\b", 2),
        ),
    }

    for pattern, delta in positive_rules:
        if re.search(pattern, normalized):
            score += delta
    for pattern, delta in negative_rules:
        if re.search(pattern, normalized):
            score += delta
    for pattern, delta in project_rules.get(project, ()):
        if re.search(pattern, normalized):
            score += delta

    words = normalized.split()
    if len(words) >= 10 or len(normalized) >= 95:
        score += 1
    if len(words) <= 3 or len(normalized) <= 24:
        score -= 1

    return max(1, min(10, score))


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

    Returns int 1–10. Never raises — uses a heuristic fallback before
    returning 5 on total failure.
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
        heuristic = _heuristic_priority(text, project, todos)
        logger.warning(
            "Both LLM scorers failed for '%s': %s — using heuristic score %d",
            text[:40],
            e,
            heuristic,
        )
        return heuristic
