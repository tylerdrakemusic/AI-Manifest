"""Versioned, repository-local snapshot of the Workspace-owned TODO contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "todo_decision_metadata.v1.json"


def _load_contract() -> dict[str, Any]:
    with _CONTRACT_PATH.open(encoding="utf-8") as contract_file:
        return json.load(contract_file)


CONTRACT = _load_contract()
VERSION = CONTRACT["version"]
SCORE_FIELDS = tuple(CONTRACT["score_fields"])
REQUIRED_FIELDS = frozenset(CONTRACT["required_fields"])
OPTIONAL_FIELDS = frozenset(CONTRACT["optional_fields"])
SUPPORTED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS | {"scale"}
BENEFIT_CATEGORIES = tuple(CONTRACT["benefit_categories"])
SCALE_ANCHORS = {
    "min": CONTRACT["scale"]["min"],
    "max": CONTRACT["scale"]["max"],
    "anchors": {
        int(score): label for score, label in CONTRACT["scale"]["anchors"].items()
    },
}
EVIDENCE_POLICY = CONTRACT["evidence_policy"]