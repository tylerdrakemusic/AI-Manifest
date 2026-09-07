"""TTS queue worker — threading daemon with bounded worker pool.

Polls ``tts_queue`` at a configurable interval, dispatches jobs to a pool of
worker threads, and writes MP3 files to ``output/tts/``.

Usage (module-level convenience)::

    from src.services.tts_queue_worker import start_default_worker, stop_default_worker

    start_default_worker()   # spawns threads in the background
    ...
    stop_default_worker()    # graceful shutdown
"""

from __future__ import annotations

import hashlib
import ctypes
import json
import logging
import os
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from src.integrations.elevenlabs.client import ElevenLabsClient
from src.utils.tts_queue_db import (
    dequeue_pending,
    get_connection,
    get_job,
    increment_retry,
    mark_done,
    mark_failed,
    recover_stale_jobs,
)
from src.utils.audio_output_policy import atomic_write_bytes

logger = logging.getLogger(__name__)
IS_WINDOWS_PLATFORM = os.name == "nt"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "output" / "tts"
_TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def _default_provider(**kwargs: object) -> bytes:
    """Adapt the existing ElevenLabs client to the internal provider API."""
    client = ElevenLabsClient()
    return client.text_to_speech(**kwargs)  # type: ignore[arg-type]


def windows_playback(path: Path) -> None:
    """Play an MP3 through Windows multimedia APIs without launching an app."""
    if not IS_WINDOWS_PLATFORM:
        raise OSError("Windows playback is only available on Windows")
    if not path.is_file():
        raise FileNotFoundError(path)

    alias = f"repository_voice_{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:12]}"
    winmm = ctypes.windll.winmm
    command_buffer = ctypes.create_unicode_buffer(256)
    open_command = f'open "{path}" type mpegvideo alias {alias}'
    error = winmm.mciSendStringW(open_command, command_buffer, len(command_buffer), 0)
    if error:
        raise OSError(f"Windows multimedia open failed: {error}")

    error = winmm.mciSendStringW(f"play {alias}", command_buffer, len(command_buffer), 0)
    if error:
        winmm.mciSendStringW(f"close {alias}", command_buffer, len(command_buffer), 0)
        raise OSError(f"Windows multimedia play failed: {error}")

    # MCI playback is asynchronous. Close the native handle later so this call
    # remains bounded without stopping the audio immediately.
    cleanup = threading.Timer(
        120.0,
        winmm.mciSendStringW,
        args=(f"close {alias}", command_buffer, len(command_buffer), 0),
    )
    cleanup.daemon = True
    cleanup.start()


def classify_http_error(error: httpx.HTTPStatusError) -> str:
    """Classify an HTTP provider failure as transient or permanent."""
    status = error.response.status_code
    return "transient" if status in _TRANSIENT_HTTP_STATUS_CODES or status >= 500 else "permanent"


def compute_backoff_delay(
    retry_count: int,
    *,
    retry_after: float | None,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
) -> float:
    """Return a bounded exponential delay, preferring provider Retry-After."""
    delay = retry_after if retry_after is not None else base_delay * (2 ** retry_count)
    return min(max(0.0, delay), max_delay)


class TtsQueueWorker:
    """Bounded thread-pool worker that drains the ``tts_queue`` table."""

    def __init__(
        self,
        *,
        workers: int = 2,
        poll_interval: float = 5.0,
        max_retries: int = 3,
        lease_timeout_seconds: float = 300.0,
        backoff_base_seconds: float = 2.0,
        backoff_max_seconds: float = 60.0,
        output_dir: Path | str | None = None,
        playback: Callable[[Path], None] | None = None,
        provider: Callable[..., bytes] | None = None,
        failure_injector: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._workers = workers
        self._poll_interval = poll_interval
        self._max_retries = max_retries
        self._lease_timeout_seconds = lease_timeout_seconds
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        self._output_dir = Path(output_dir) if output_dir is not None else _DEFAULT_OUTPUT_DIR
        self._playback = playback if playback is not None else windows_playback
        self._provider = provider or _default_provider
        self._failure_injector = failure_injector
        self._job_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=workers * 4)
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn worker threads and the poll scheduler thread."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()

        poll_thread = threading.Thread(
            target=self._poll_loop,
            name="tts-poll",
            daemon=True,
        )
        poll_thread.start()
        self._threads.append(poll_thread)

        for i in range(self._workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"tts-worker-{i}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

        logger.info(
            "TtsQueueWorker started: %d worker(s), poll_interval=%.1fs, output_dir=%s",
            self._workers,
            self._poll_interval,
            self._output_dir,
        )

    def stop(self) -> None:
        """Signal all threads to stop and wait for them to finish."""
        self._stop_event.set()
        # Unblock worker threads waiting on the queue
        for _ in range(self._workers):
            try:
                self._job_queue.put_nowait(None)  # type: ignore[arg-type]
            except queue.Full:
                pass
        for t in self._threads:
            t.join(timeout=10)
        self._threads.clear()
        logger.info("TtsQueueWorker stopped.")

    # ------------------------------------------------------------------
    # Internal thread targets
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Scheduler thread: dequeue PENDING jobs and push onto internal queue."""
        while not self._stop_event.is_set():
            try:
                conn = get_connection()
                try:
                    recovered = recover_stale_jobs(
                        conn, lease_timeout_seconds=self._lease_timeout_seconds
                    )
                    jobs = dequeue_pending(conn, limit=self._workers)
                finally:
                    conn.close()

                for job_id in recovered:
                    self._log_lifecycle("RECOVERED", job_id=job_id, retry_count=None)

                for job in jobs:
                    try:
                        self._job_queue.put(job, timeout=self._poll_interval)
                    except queue.Full:
                        logger.warning("Job queue full; job %s will be retried next poll.", job["id"])
                        # Reset back to PENDING so it is picked up next poll
                        conn2 = get_connection()
                        try:
                            conn2.execute(
                                "UPDATE tts_queue SET status='PENDING', started_at=NULL WHERE id=?",
                                (job["id"],),
                            )
                            conn2.commit()
                        finally:
                            conn2.close()
            except Exception:
                logger.exception("Error in poll loop")

            self._stop_event.wait(self._poll_interval)

    def _worker_loop(self) -> None:
        """Worker thread: process jobs from the internal queue."""
        while not self._stop_event.is_set():
            try:
                job = self._job_queue.get(timeout=self._poll_interval)
            except queue.Empty:
                continue

            if job is None:
                # Sentinel value — stop requested
                break

            try:
                self._process_job(job)
            except Exception:
                logger.exception("Unhandled error processing job %s", job.get("id"))
            finally:
                self._job_queue.task_done()

    def _process_job(self, job: dict[str, Any]) -> None:
        """Synthesize audio for *job* and persist the result."""
        job_id: int = job["id"]
        started = time.perf_counter()
        self._log_lifecycle(
            "STARTED", job_id=job_id, retry_count=job["retry_count"], characters=len(job["text"])
        )

        try:
            audio_bytes: bytes = self._provider(
                text=job["text"],
                voice_id=job["voice_id"],
                model_id=job["model_id"],
                output_format=job["output_format"],
            )
        except httpx.HTTPStatusError as exc:
            if classify_http_error(exc) == "transient":
                if exc.response.status_code >= 500:
                    self._handle_ambiguous_error(job, exc)
                    return
                self._handle_transient_error(job, exc)
                return
            self._log_lifecycle(
                "FAILED", job_id=job_id, retry_count=job["retry_count"],
                characters=len(job["text"]), provider_error=str(exc),
            )
            conn = get_connection()
            try:
                mark_failed(conn, job_id, str(exc))
            finally:
                conn.close()
            return
        except httpx.RequestError as exc:
            self._handle_ambiguous_error(job, exc)
            return
        except Exception as exc:
            self._log_lifecycle(
                "FAILED", job_id=job_id, retry_count=job["retry_count"],
                characters=len(job["text"]), provider_error=str(exc),
            )
            if self._failure_injector is not None:
                raise
            conn = get_connection()
            try:
                mark_failed(conn, job_id, str(exc))
            finally:
                conn.close()
            return

        # Compute checksum, write atomically
        sha256 = hashlib.sha256(audio_bytes).hexdigest()
        output_path = self._output_dir / f"{job_id}.mp3"
        if self._failure_injector is not None:
            self._failure_injector("before_publish", job)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE tts_queue SET publication_state='WRITING' WHERE id=?",
                (job_id,),
            )
            conn.commit()
        finally:
            conn.close()
        atomic_write_bytes(output_path, audio_bytes)
        if self._failure_injector is not None:
            self._failure_injector("after_publish", job)

        conn = get_connection()
        try:
            mark_done(conn, job_id, str(output_path), sha256)
        finally:
            conn.close()

        if job.get("decision_id") and self._playback is not None:
            try:
                self._playback(output_path)
            except Exception as exc:
                logger.exception("Playback failed for queue job %s", job_id)
                self._log_lifecycle(
                    "PLAYBACK_FAILED", job_id=job_id, retry_count=job["retry_count"],
                    characters=len(job["text"]), provider_error=f"playback failed: {exc}",
                )

        self._log_lifecycle(
            "DONE", job_id=job_id, retry_count=job["retry_count"],
            characters=len(job["text"]), latency_ms=round((time.perf_counter() - started) * 1000, 2),
            output_size=len(audio_bytes), output_path=str(output_path),
        )

    def _handle_transient_error(self, job: dict[str, Any], exc: Exception) -> None:
        """Retry a transient provider failure with bounded backoff."""
        job_id: int = job["id"]
        retry_after: float | None = None
        if isinstance(exc, httpx.HTTPStatusError):
            retry_after_header = exc.response.headers.get("Retry-After")
            if retry_after_header is not None:
                try:
                    retry_after = float(retry_after_header)
                except ValueError:
                    retry_after = None

        conn = get_connection()
        try:
            new_count = increment_retry(conn, job_id)
        finally:
            conn.close()

        delay = compute_backoff_delay(
            new_count,
            retry_after=retry_after,
            base_delay=self._backoff_base_seconds,
            max_delay=self._backoff_max_seconds,
        )
        self._log_lifecycle(
            "RETRYING", job_id=job_id, retry_count=new_count,
            provider_error=str(exc), backoff_seconds=delay,
        )
        time.sleep(delay)

        # Put back on the queue if still PENDING (increment_retry may have set FAILED)
        conn2 = get_connection()
        try:
            refreshed = get_job(conn2, job_id)
        finally:
            conn2.close()

        if refreshed and refreshed["status"] == "PENDING":
            try:
                self._job_queue.put(refreshed, timeout=5)
            except queue.Full:
                pass  # Will be picked up by the next poll cycle

    def _handle_ambiguous_error(self, job: dict[str, Any], exc: Exception) -> None:
        """Stop replay when the provider outcome cannot be established."""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE tts_queue SET status='AMBIGUOUS', error_message=?, completed_at=? WHERE id=?",
                (str(exc), datetime.now(timezone.utc).isoformat(), job["id"]),
            )
            conn.execute(
                "UPDATE tts_queue_attempts SET status='AMBIGUOUS', usage_state='AMBIGUOUS', "
                "error_message=?, completed_at=? "
                "WHERE job_id=? AND status='STARTED'",
                (str(exc), datetime.now(timezone.utc).isoformat(), job["id"]),
            )
            conn.commit()
        finally:
            conn.close()
        self._log_lifecycle("AMBIGUOUS", job_id=job["id"], provider_error=str(exc))

    @staticmethod
    def _log_lifecycle(event: str, **fields: Any) -> None:
        """Emit a credential-free JSON lifecycle record."""
        payload = {"event": event, **fields}
        logger.info("tts_queue %s", json.dumps(payload, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Module-level default worker (convenience API)
# ---------------------------------------------------------------------------

_default_worker: TtsQueueWorker | None = None
_default_lock = threading.Lock()


def start_default_worker(**kwargs: Any) -> None:
    """Start the module-level default TtsQueueWorker (idempotent)."""
    global _default_worker
    with _default_lock:
        if _default_worker is None:
            _default_worker = TtsQueueWorker(**kwargs)
            _default_worker.start()


def stop_default_worker() -> None:
    """Stop and destroy the module-level default TtsQueueWorker."""
    global _default_worker
    with _default_lock:
        if _default_worker is not None:
            _default_worker.stop()
            _default_worker = None
