"""👁AI-Manifest test configuration.

Adds the repo root to ``sys.path`` so tests can ``import src.*`` directly,
and evicts any previously-cached ``src.integrations.elevenlabs`` modules so
imports always resolve to this repo's local copy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Evict any previously-cached shim modules so imports pick up the local client.
for _key in list(sys.modules.keys()):
    if _key.startswith("src.integrations.elevenlabs") or _key.startswith(
        "src.config.elevenlabs"
    ):
        del sys.modules[_key]


def pytest_collection_modifyitems(config, items):
    """Skip playwright-marked tests unless PLAYWRIGHT_ENABLED=1 is set."""
    if os.getenv("PLAYWRIGHT_ENABLED") != "1":
        skip = pytest.mark.skip(reason="Set PLAYWRIGHT_ENABLED=1 to run Playwright tests")
        for item in items:
            if item.get_closest_marker("playwright"):
                item.add_marker(skip)
