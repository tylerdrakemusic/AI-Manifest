"""Root conftest for 👁AI-Manifest worktree.

Ensures the project root is at the HEAD of sys.path so that
`src.*` imports resolve to this project's src/, not f:\\⊕Workspace\\src.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
# Insert at index 0 so this project's src wins over any workspace src
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
else:
    # Promote to front if already present but not first
    sys.path.remove(str(_PROJECT_ROOT))
    sys.path.insert(0, str(_PROJECT_ROOT))
