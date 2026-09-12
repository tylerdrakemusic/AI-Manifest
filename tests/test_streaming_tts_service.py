from __future__ import annotations

import threading
import time
import logging
import sys
import types
from unittest.mock import Mock

import pytest

from src.services.streaming_tts import StreamingTtsService, _AudioSink


def test_start_rejects_empty_and_overlong_text() -> None:
    service = StreamingTtsService(client_factory=Mock())

    with pytest.raises(ValueError, match="empty"):
        service.start("", "voice")

    with pytest.raises(ValueError, match="5000"):
        service.start("x" * 5001, "voice")


def test_only_one_streaming_session_can_be_active() -> None:
    client = Mock()
    service = StreamingTtsService(client_factory=lambda: client)
    client.text_to_speech_stream.return_value = iter(())

    first = service.start("hello", "voice")

    with pytest.raises(RuntimeError, match="active"):
        service.start("again", "voice")

    service.cancel(first["session_id"])


def test_completed_session_reports_pcm_telemetry_and_retains_snapshot() -> None:
    client = Mock()
    client.text_to_speech_stream.return_value = iter([b"\x00\x01", b"\x02\x03"])
    sink = Mock()
    service = StreamingTtsService(
        client_factory=lambda: client,
        audio_factory=lambda: sink,
    )

    started = service.start("hello", "voice", model_id="model")
    deadline = time.monotonic() + 2
    snapshot = service.status(started["session_id"])
    while snapshot["state"] == "starting" or snapshot["state"] == "running":
        assert time.monotonic() < deadline
        snapshot = service.status(started["session_id"])

    assert snapshot["state"] == "completed"
    assert snapshot["characters"] == 5
    assert snapshot["chunks"] == 2
    assert snapshot["bytes"] == 4
    assert snapshot["first_byte_latency_ms"] is not None
    assert snapshot["first_audible_latency_ms"] is not None
    assert snapshot["target_met"] is True
    client.text_to_speech_stream.assert_called_once_with(
        "hello", "voice", model_id="model", output_format="pcm_22050"
    )
    assert sink.write.call_count == 2
    sink.stop.assert_called_once()
    sink.close.assert_called_once()


def test_audio_sink_uses_mono_int16_pcm_at_22050_hz(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = Mock()
    sounddevice = types.SimpleNamespace(RawOutputStream=Mock(return_value=stream))
    monkeypatch.setitem(sys.modules, "sounddevice", sounddevice)

    _AudioSink()

    sounddevice.RawOutputStream.assert_called_once_with(
        samplerate=22050,
        channels=1,
        dtype="int16",
        blocksize=0,
    )


def test_cancel_closes_provider_aborts_audio_and_flushes_pending_pcm() -> None:
    client = Mock()
    provider_closed = threading.Event()

    def provider() -> object:
        try:
            while True:
                yield b"\x00\x00"
        finally:
            provider_closed.set()

    client.text_to_speech_stream.return_value = provider()
    sink = Mock()
    service = StreamingTtsService(client_factory=lambda: client, audio_factory=lambda: sink)

    started = service.start("hello", "voice")
    service.cancel(started["session_id"])
    deadline = time.monotonic() + 2
    snapshot = service.status(started["session_id"])
    while snapshot["state"] in {"starting", "running"}:
        assert time.monotonic() < deadline
        snapshot = service.status(started["session_id"])

    assert snapshot["state"] == "cancelled"
    assert provider_closed.is_set()
    sink.abort.assert_called()
    sink.close.assert_called_once()


def test_deadline_terminates_session_and_logs_secret_free_terminal_telemetry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    client = Mock()

    def provider() -> object:
        now[0] = 3.0
        yield b"\x00\x00"

    client.text_to_speech_stream.return_value = provider()
    sink = Mock()
    service = StreamingTtsService(
        client_factory=lambda: client,
        audio_factory=lambda: sink,
        clock=clock,
        deadline_seconds=2.0,
    )

    with caplog.at_level(logging.INFO):
        started = service.start("private text", "private voice", "private model")
        deadline = time.monotonic() + 2
        snapshot = service.status(started["session_id"])
        while snapshot["state"] in {"starting", "running"}:
            assert time.monotonic() < deadline
            snapshot = service.status(started["session_id"])

    assert snapshot["state"] == "cancelled"
    assert snapshot["reason"] == "deadline"
    assert snapshot["total_elapsed_ms"] == 3000.0
    terminal_log = "\n".join(record.getMessage() for record in caplog.records)
    assert "private text" not in terminal_log
    assert "private voice" not in terminal_log
    assert "private model" not in terminal_log
    assert '"target_met"' in terminal_log


def test_terminal_snapshot_expires_after_ten_minutes() -> None:
    now = [0.0]
    client = Mock()
    client.text_to_speech_stream.return_value = iter(())
    service = StreamingTtsService(
        client_factory=lambda: client,
        audio_factory=Mock,
        clock=lambda: now[0],
    )

    started = service.start("hello", "voice")
    deadline = time.monotonic() + 2
    snapshot = service.status(started["session_id"])
    while snapshot["state"] in {"starting", "running"}:
        assert time.monotonic() < deadline
        snapshot = service.status(started["session_id"])

    now[0] = 601.0
    with pytest.raises(KeyError):
        service.status(started["session_id"])