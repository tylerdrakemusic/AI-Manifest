"""Bounded local PCM streaming sessions for ElevenLabs TTS."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from queue import Empty, Full, Queue
import threading
import time
from typing import Callable, Iterator
from uuid import uuid4

from src.integrations.elevenlabs.client import ElevenLabsClient

MAX_TEXT_CHARS = 5000
PCM_SAMPLE_RATE = 22050
PCM_OUTPUT_FORMAT = "pcm_22050"
SESSION_DEADLINE_SECONDS = 120.0
SESSION_RETENTION_SECONDS = 600.0
TARGET_FIRST_AUDIBLE_SECONDS = 2.0
PCM_QUEUE_SIZE = 8
logger = logging.getLogger(__name__)


class _AudioSink:
    def __init__(self) -> None:
        import sounddevice

        self._stream = sounddevice.RawOutputStream(
            samplerate=PCM_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=0,
        )

    def start(self) -> None:
        self._stream.start()

    def write(self, chunk: bytes) -> None:
        self._stream.write(chunk)

    def stop(self) -> None:
        self._stream.stop()

    def abort(self) -> None:
        self._stream.abort()

    def close(self) -> None:
        self._stream.close()


@dataclass
class _Session:
    session_id: str
    text: str
    voice_id: str
    model_id: str
    created_at: float
    cancel_event: threading.Event = field(default_factory=threading.Event)
    provider_iterator: Iterator[bytes] | None = None
    audio_sink: object | None = None
    thread: threading.Thread | None = None
    snapshot: dict[str, object] = field(default_factory=dict)


class StreamingTtsService:
    """Manage one bounded, cancellable PCM TTS session at a time."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], ElevenLabsClient] = ElevenLabsClient,
        audio_factory: Callable[[], object] = _AudioSink,
        clock: Callable[[], float] = time.monotonic,
        deadline_seconds: float = SESSION_DEADLINE_SECONDS,
        retention_seconds: float = SESSION_RETENTION_SECONDS,
    ) -> None:
        self._client_factory = client_factory
        self._audio_factory = audio_factory
        self._clock = clock
        self._deadline_seconds = deadline_seconds
        self._retention_seconds = retention_seconds
        self._lock = threading.RLock()
        self._active: _Session | None = None
        self._snapshots: dict[str, tuple[float, dict[str, object]]] = {}

    def start(self, text: str, voice_id: str, model_id: str = "eleven_multilingual_v2") -> dict[str, object]:
        """Start a streaming session and return its opaque status immediately."""
        if not text or not text.strip():
            raise ValueError("text cannot be empty")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"text cannot exceed {MAX_TEXT_CHARS} characters")

        with self._lock:
            self._purge_expired()
            if self._active is not None:
                raise RuntimeError("a streaming TTS session is already active")
            session = _Session(
                session_id=uuid4().hex,
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                created_at=self._clock(),
            )
            session.snapshot = self._new_snapshot(session)
            self._active = session
            session.thread = threading.Thread(
                target=self._run,
                args=(session,),
                name=f"streaming-tts-{session.session_id[:8]}",
                daemon=True,
            )
            session.thread.start()
            return dict(session.snapshot)

    def status(self, session_id: str) -> dict[str, object]:
        """Return the active or retained terminal snapshot for a session."""
        with self._lock:
            self._purge_expired()
            if self._active is not None and self._active.session_id == session_id:
                return dict(self._active.snapshot)
            retained = self._snapshots.get(session_id)
            if retained is None:
                raise KeyError(session_id)
            return dict(retained[1])

    def cancel(self, session_id: str, reason: str = "cancelled") -> dict[str, object]:
        """Request cancellation and return the latest session snapshot."""
        with self._lock:
            self._purge_expired()
            session = self._active
            if session is None or session.session_id != session_id:
                retained = self._snapshots.get(session_id)
                if retained is None:
                    raise KeyError(session_id)
                return dict(retained[1])
            self._request_cancel(session, reason)
            return dict(session.snapshot)

    def shutdown(self) -> None:
        """Cancel active work during server shutdown without waiting on I/O."""
        with self._lock:
            active = self._active
        if active is not None:
            self.cancel(active.session_id, reason="shutdown")

    def _run(self, session: _Session) -> None:
        started = session.created_at
        chunks = 0
        byte_count = 0
        first_byte_at: list[float | None] = [None]
        first_audible: float | None = None
        audio_sink: object | None = None
        pcm_queue: Queue[bytes | None] = Queue(maxsize=PCM_QUEUE_SIZE)
        producer_error: list[BaseException] = []
        producer_done = threading.Event()

        def produce() -> None:
            try:
                client = self._client_factory()
                iterator = client.text_to_speech_stream(
                    session.text,
                    session.voice_id,
                    model_id=session.model_id,
                    output_format=PCM_OUTPUT_FORMAT,
                )
                with self._lock:
                    session.provider_iterator = iterator
                for chunk in iterator:
                    if session.cancel_event.is_set():
                        break
                    if first_byte_at[0] is None:
                        first_byte_at[0] = self._clock()
                    while not session.cancel_event.is_set():
                        try:
                            pcm_queue.put(chunk, timeout=0.05)
                            break
                        except Full:
                            continue
            except BaseException as exc:
                producer_error.append(exc)
            finally:
                try:
                    if session.provider_iterator is not None and hasattr(session.provider_iterator, "close"):
                        session.provider_iterator.close()
                except (RuntimeError, ValueError):
                    pass
                producer_done.set()

        try:
            audio_sink = self._audio_factory()
            with self._lock:
                session.audio_sink = audio_sink
                session.snapshot["state"] = "running"
            audio_sink.start()  # type: ignore[attr-defined]
            producer = threading.Thread(target=produce, name=f"tts-provider-{session.session_id[:8]}", daemon=True)
            producer.start()
            while not producer_done.is_set() or not pcm_queue.empty():
                if self._clock() - started >= self._deadline_seconds:
                    self._request_cancel(session, "deadline")
                    break
                if session.cancel_event.is_set():
                    break
                try:
                    chunk = pcm_queue.get(timeout=0.05)
                except Empty:
                    continue
                if chunk is None:
                    continue
                if self._clock() - started >= self._deadline_seconds:
                    self._request_cancel(session, "deadline")
                    break
                now = self._clock()
                chunks += 1
                byte_count += len(chunk)
                audio_sink.write(chunk)  # type: ignore[attr-defined]
                if first_audible is None:
                    first_audible = self._clock()
            producer.join(timeout=0.2)
            if producer_error and not session.cancel_event.is_set():
                raise producer_error[0]
            terminal_state = "cancelled" if session.cancel_event.is_set() else "completed"
        except BaseException:
            terminal_state = "failed"
            if not session.snapshot.get("reason"):
                session.snapshot["reason"] = "provider_error"
        finally:
            while True:
                try:
                    pcm_queue.get_nowait()
                except Empty:
                    break
            if audio_sink is not None:
                try:
                    if terminal_state == "cancelled":
                        audio_sink.abort()  # type: ignore[attr-defined]
                    else:
                        audio_sink.stop()  # type: ignore[attr-defined]
                except (OSError, RuntimeError):
                    pass
                try:
                    audio_sink.close()  # type: ignore[attr-defined]
                except (OSError, RuntimeError):
                    pass
            total_elapsed = self._clock() - started
            snapshot = {
                "session_id": session.session_id,
                "state": terminal_state,
                "reason": _safe_reason(str(session.snapshot.get("reason", ""))) if terminal_state != "completed" else None,
                "characters": len(session.text),
                "chunks": chunks,
                "bytes": byte_count,
                "first_byte_latency_ms": _elapsed_ms(first_byte_at[0], started),
                "first_audible_latency_ms": _elapsed_ms(first_audible, started),
                "total_elapsed_ms": round(total_elapsed * 1000, 3),
                "target_met": first_audible is not None and first_audible - started < TARGET_FIRST_AUDIBLE_SECONDS,
            }
            with self._lock:
                session.snapshot = snapshot
                self._snapshots[session.session_id] = (self._clock(), dict(snapshot))
                if self._active is session:
                    self._active = None
            logger.info("streaming_tts_terminal %s", json.dumps(snapshot, sort_keys=True))

    def _new_snapshot(self, session: _Session) -> dict[str, object]:
        return {
            "session_id": session.session_id,
            "state": "starting",
            "reason": None,
            "characters": len(session.text),
            "chunks": 0,
            "bytes": 0,
            "first_byte_latency_ms": None,
            "first_audible_latency_ms": None,
            "total_elapsed_ms": None,
            "target_met": False,
        }

    def _request_cancel(self, session: _Session, reason: str) -> None:
        session.snapshot["reason"] = _safe_reason(reason)
        session.cancel_event.set()
        iterator = session.provider_iterator
        if iterator is not None and hasattr(iterator, "close"):
            try:
                iterator.close()
            except (RuntimeError, ValueError):
                pass
        sink = session.audio_sink
        if sink is not None and hasattr(sink, "abort"):
            sink.abort()

    def _purge_expired(self) -> None:
        now = self._clock()
        for session_id, (retained_at, _) in list(self._snapshots.items()):
            if now - retained_at >= self._retention_seconds:
                del self._snapshots[session_id]


def _elapsed_ms(moment: float | None, started: float) -> float | None:
    return None if moment is None else round((moment - started) * 1000, 3)


def _safe_reason(reason: str) -> str:
    return reason if reason in {"cancelled", "shutdown", "deadline", "provider_error", "audio_error"} else "cancelled"


__all__ = ["StreamingTtsService"]