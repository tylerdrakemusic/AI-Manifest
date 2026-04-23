"""👁AI-Manifest test configuration.

Puts ⊕Workspace first on sys.path so that shared integrations
(e.g. src.integrations.elevenlabs) resolve to the canonical workspace
client, not the backwards-compatibility shim in this project.
"""

import sys
from pathlib import Path

_WORKSPACE = Path(r"f:\⊕Workspace")
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

# Evict any cached shim modules so the next import picks up the workspace client.
for _key in list(sys.modules.keys()):
    if _key.startswith("src.integrations.elevenlabs") or _key.startswith("src.config.elevenlabs"):
        del sys.modules[_key]
