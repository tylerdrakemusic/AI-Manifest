"""Deterministic priority scorer for todo items.

Rule-based heuristic only (no LLM dependency — Ollama/OpenAI paths were
removed as part of FR-20260807-tech-debt-scanner's workspace-wide Ollama
dependency removal). Returns an int 1-10; never raises.

The scorer accepts the existing open todos for the same project for API
compatibility with callers, but the current heuristic does not yet use them
for calibration (reserved for future use).
"""

from __future__ import annotations

import re
from typing import Any


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
    """Score a todo item's priority 1-10 using the deterministic heuristic.

    Args:
        text: The new todo text to score.
        project: Project key (e.g. 'music', 'life', 'workspace').
        existing_todos: Open todos for this project (from get_open_todos).
                        Accepted for API compatibility; not yet used by the
                        heuristic (reserved for future calibration).

    Returns int 1-10. Never raises.
    """
    todos = existing_todos or []
    return _heuristic_priority(text, project, todos)
