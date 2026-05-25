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
import logging
import queue
import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from src.integrations.elevenlabs.client import ElevenLabsClient
from src.utils.tts_queue_db import (
    dequeue_pending,
    get_connection,
    get_job,
    increment_retry,
    mark_done,
    mark_failed,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "output" / "tts"


class TtsQueueWorker:
    """Bounded thread-pool worker that drains the ``tts_queue`` table."""

    def __init__(
        self,
        *,
        workers: int = 2,
        poll_interval: float = 5.0,
        max_retries: int = 3,
        output_dir: Path | str | None = None,
    ) -> None:
        self._workers = workers
        self._poll_interval = poll_interval
        self._max_retries = max_retries
        self._output_dir = Path(output_dir) if output_dir is not None else _DEFAULT_OUTPUT_DIR
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
                    jobs = dequeue_pending(conn, limit=self._workers)
                finally:
                    conn.close()

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
        logger.info("Processing TTS job %s (voice=%s)", job_id, job["voice_id"])

        try:
            client = ElevenLabsClient()
            audio_bytes: bytes = client.text_to_speech(
                text=job["text"],
                voice_id=job["voice_id"],
                model_id=job["model_id"],
                output_format=job["output_format"],
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._handle_rate_limit(job, exc)
                return
            logger.error("HTTP error for job %s: %s", job_id, exc)
            conn = get_connection()
            try:
                mark_failed(conn, job_id, str(exc))
            finally:
                conn.close()
            return
        except Exception as exc:
            logger.error("Unexpected error for job %s: %s", job_id, exc)
            conn = get_connection()
            try:
                mark_failed(conn, job_id, str(exc))
            finally:
                conn.close()
            return

        # Compute checksum, write atomically
        sha256 = hashlib.sha256(audio_bytes).hexdigest()
        output_path = self._output_dir / f"{job_id}.mp3"
        tmp_path = output_path.with_suffix(".tmp")
        tmp_path.write_bytes(audio_bytes)
        tmp_path.rename(output_path)

        conn = get_connection()
        try:
            mark_done(conn, job_id, str(output_path), sha256)
        finally:
            conn.close()

        logger.info("Job %s → DONE (%s, %d bytes)", job_id, output_path.name, len(audio_bytes))

    def _handle_rate_limit(self, job: dict[str, Any], exc: httpx.HTTPStatusError) -> None:
        """Back off and requeue a rate-limited job."""
        job_id: int = job["id"]
        retry_after_header = exc.response.headers.get("Retry-After")

        conn = get_connection()
        try:
            new_count = increment_retry(conn, job_id)
        finally:
            conn.close()

        if retry_after_header is not None:
            try:
                delay = float(retry_after_header)
            except ValueError:
                delay = 2 ** new_count * 30 + random.uniform(-10, 10)
        else:
            delay = 2 ** new_count * 30 + random.uniform(-10, 10)

        delay = max(0.0, delay)
        logger.warning(
            "Job %s rate-limited (retry %d); sleeping %.1fs before requeueing.",
            job_id,
            new_count,
            delay,
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
