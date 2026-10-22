from __future__ import annotations

import re
from pathlib import Path


_FRONTMATTER_KEY = re.compile(
    r"^(?:([A-Za-z_][A-Za-z0-9_-]*)|\"([^\"]+)\"|'([^']+)'):[ \t]*(?:.*)$"
)


def _is_disallowed_pin_field(field_name: str) -> bool:
    normalized = field_name.lower().replace("-", "_")
    parts = set(normalized.split("_"))
    if normalized in {"model", "provider"}:
        return True
    if "pin" in parts and parts.intersection({"model", "provider", "cost", "multiplier"}):
        return True
    return "multiplier" in parts and parts.intersection({"model", "provider", "cost"})


def _frontmatter_pin_fields(frontmatter: str) -> list[str]:
    lines = frontmatter.splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        len(lines),
    )
    fields: list[str] = []
    for line in lines[1:closing_index]:
        match = _FRONTMATTER_KEY.match(line)
        if match:
            field_name = next(value for value in match.groups() if value is not None)
            if _is_disallowed_pin_field(field_name):
                fields.append(field_name)
    return fields


def _agent_file_pin_fields(agent_path: Path) -> list[str]:
    return _frontmatter_pin_fields(agent_path.read_text(encoding="utf-8"))


def test_frontmatter_pin_detection_ignores_role_tiers_and_nested_keys() -> None:
    frontmatter = """---
description: agent metadata
role_tier: coordinator
model_tier: reasoning
tiers:
  model: inherited from role tier
  cost_multiplier: inherited from role tier
---
"""

    assert _frontmatter_pin_fields(frontmatter) == []


def test_frontmatter_pin_detection_finds_explicit_top_level_pins() -> None:
    frontmatter = """---
model: provider-model-name
provider: vendor-name
model_cost_multiplier: 1.5
cost_multiplier_pin: 1.2
---
"""

    assert _frontmatter_pin_fields(frontmatter) == [
        "model",
        "provider",
        "model_cost_multiplier",
        "cost_multiplier_pin",
    ]


def test_agent_definitions_do_not_pin_models_providers_or_cost_multipliers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agents_dir = repo_root / ".github" / "agents"
    offenders = [
        f"{agent_path.relative_to(agents_dir)}: {field_name}"
        for agent_path in sorted(agents_dir.rglob("*.agent.md"))
        for field_name in _agent_file_pin_fields(agent_path)
    ]

    assert not offenders, (
        "Agent frontmatter must not pin models, providers, or model/cost multipliers: "
        + "; ".join(offenders)
    )