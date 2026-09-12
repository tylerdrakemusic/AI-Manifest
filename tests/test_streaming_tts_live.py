from __future__ import annotations

import os
import time

import pytest

from src.services.streaming_tts import PCM_OUTPUT_FORMAT, StreamingTtsService


@pytest.mark.live
@pytest.mark.skipif(
    os.name != "nt" or os.getenv("ELEVENLABS_LIVE_SMOKE") != "1",
    reason="set ELEVENLABS_LIVE_SMOKE=1 on Windows to run the live smoke test",
)
def test_windows_live_streaming_tts_smoke() -> None:
    assert PCM_OUTPUT_FORMAT == "pcm_22050"
    service = StreamingTtsService()
    started = service.start("Live streaming smoke test.", "21m00Tcm4TlvDq8ikWAM")
    deadline = time.monotonic() + 125
    snapshot = service.status(started["session_id"])
    while snapshot["state"] in {"starting", "running"}:
        if time.monotonic() >= deadline:
            service.cancel(started["session_id"])
            pytest.fail("live streaming smoke test exceeded local wait budget")
        snapshot = service.status(started["session_id"])
    assert snapshot["state"] == "completed", snapshot