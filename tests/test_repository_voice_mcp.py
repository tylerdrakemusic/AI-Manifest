from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from unittest.mock import patch

from src.services.governed_repository_voice import RepositoryVoiceSubmissionResult
from src.services.tts_queue_worker import TtsQueueWorker
from src.utils import tts_queue_db
from src.utils.tts_queue_db import get_job, init_tts_queue


def test_repository_voice_submission_is_exposed_as_a_governed_mcp_capability() -> None:
    from src.integrations.elevenlabs import mcp_server

    expected = RepositoryVoiceSubmissionResult(
        decision_id="decision-604",
        job_id=17,
        accepted=True,
    )
    with patch.object(
        mcp_server.governed_repository_voice,
        "submit_repository_voice",
        return_value=expected,
    ) as submit:
        result = mcp_server.submit_repository_voice(
            "decision-604",
            "Approval is required.",
            voice_id="voice-1",
        )

    submit.assert_called_once_with(
        "decision-604",
        "Approval is required.",
        voice_id="voice-1",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        priority=5,
        max_retries=3,
    )
    assert result == {
        "decision_id": "decision-604",
        "job_id": 17,
        "accepted": True,
        "deduplicated": False,
        "error": None,
    }


def test_repository_voice_status_reports_governed_queue_boundary() -> None:
    from src.integrations.elevenlabs import mcp_server

    status = mcp_server.repository_voice_status()

    assert status["capability"] == "repository_voice"
    assert status["status"] == "healthy"
    assert status["transport"] == "durable_tts_queue"
    assert status["provider_access"] == "worker_only"
    assert status["credentials_exposed"] is False


def test_repository_voice_status_is_actionable_when_service_is_unavailable() -> None:
    from src.integrations.elevenlabs import mcp_server

    with patch.object(
        mcp_server.governed_repository_voice,
        "enqueue_with_status",
        None,
    ):
        status = mcp_server.repository_voice_status()

    assert status["status"] == "unavailable"
    assert status["reason"] == "queue unavailable"
    assert "ELEVENLABS_API_KEY" not in str(status)


def test_registered_mcp_capability_delivers_one_authorized_decision_end_to_end(
    tmp_path: Path,
    caplog,
) -> None:
    """Exercise MCP enqueue, durable deduplication, fake provider, and playback."""
    from src.integrations.elevenlabs import mcp_server

    db_path = tmp_path / "manifest_todos.db"
    output_dir = tmp_path / "tts"
    original_db_path = tts_queue_db.DB_PATH
    tts_queue_db.DB_PATH = db_path
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            init_tts_queue(conn)

        status = mcp_server.repository_voice_status()
        first = mcp_server.submit_repository_voice(
            "decision-e2e-606",
            "Approve the controlled repository change.",
            voice_id="fake-voice",
        )
        duplicate = mcp_server.submit_repository_voice(
            "decision-e2e-606",
            "Approve the controlled repository change.",
            voice_id="fake-voice",
        )

        provider_calls: list[dict[str, object]] = []
        played: list[Path] = []

        def fake_provider(**kwargs: object) -> bytes:
            provider_calls.append(kwargs)
            return b"controlled-fake-mp3"

        def fake_playback(path: Path) -> None:
            played.append(path)

        with caplog.at_level(logging.INFO):
            worker = TtsQueueWorker(
                workers=1,
                output_dir=output_dir,
                provider=fake_provider,
                playback=fake_playback,
            )
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                job = get_job(conn, first["job_id"])
            assert job is not None
            worker._process_job(job)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            persisted = get_job(conn, first["job_id"])
            count = conn.execute("SELECT COUNT(*) FROM tts_queue").fetchone()[0]

        assert status["status"] == "healthy"
        assert first["accepted"] is True
        assert duplicate["accepted"] is True
        assert duplicate["deduplicated"] is True
        assert count == 1
        assert persisted is not None
        assert persisted["decision_id"] == "decision-e2e-606"
        assert persisted["status"] == "DONE"
        assert persisted["publication_state"] == "VERIFIED"
        assert Path(persisted["output_path"]).read_bytes() == b"controlled-fake-mp3"
        assert provider_calls == [
            {
                "text": "Approve the controlled repository change.",
                "voice_id": "fake-voice",
                "model_id": "eleven_multilingual_v2",
                "output_format": "mp3_44100_128",
            }
        ]
        assert played == [output_dir / f"{first['job_id']}.mp3"]
        lifecycle = "\n".join(record.getMessage() for record in caplog.records)
        assert "ELEVENLABS_API_KEY" not in lifecycle
        assert "controlled-private-workflow-result" not in lifecycle
        assert json.dumps(first, sort_keys=True)
    finally:
        tts_queue_db.DB_PATH = original_db_path