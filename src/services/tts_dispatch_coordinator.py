"""Shared quota admission and local playback coordination for TTS paths."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class QuotaSnapshot:
    """Provider quota state observed at a monotonic timestamp."""

    used_characters: int
    character_limit: int
    observed_at: float


class _Lease:
    def __init__(self, release: Callable[[], None]) -> None:
        self._release = release
        self._lock = threading.Lock()
        self._released = False

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._release()


class TtsDispatchCoordinator:
    """Coordinate provider quota reservations and local playback leases."""

    def __init__(
        self,
        *,
        quota_reader: Callable[[], QuotaSnapshot | None],
        max_quota_age_seconds: float = 60.0,
    ) -> None:
        self._quota_reader = quota_reader
        self._max_quota_age_seconds = max_quota_age_seconds
        self._quota_lock = threading.Lock()
        self._reserved_characters = 0
        self._playback_lock = threading.Lock()

    def reserve_quota(self, characters: int) -> _Lease:
        """Reserve character capacity, rejecting unknown or stale quota state."""
        if characters < 0:
            raise ValueError("characters cannot be negative")
        try:
            snapshot = self._quota_reader()
        except Exception as exc:
            raise RuntimeError("quota unavailable") from exc
        if not self._valid_snapshot(snapshot):
            raise RuntimeError("quota unavailable or stale")
        assert snapshot is not None
        with self._quota_lock:
            available = snapshot.character_limit - snapshot.used_characters - self._reserved_characters
            if characters > available:
                raise RuntimeError("quota exhausted")
            self._reserved_characters += characters
        return _Lease(lambda: self._release_quota(characters))

    def acquire_playback(self) -> _Lease:
        """Wait until this dispatch owns the process-wide playback lease."""
        self._playback_lock.acquire()
        return _Lease(self._playback_lock.release)

    def _release_quota(self, characters: int) -> None:
        with self._quota_lock:
            self._reserved_characters -= characters

    def _valid_snapshot(self, snapshot: QuotaSnapshot | None) -> bool:
        if snapshot is None:
            return False
        if not isinstance(snapshot.used_characters, int) or not isinstance(snapshot.character_limit, int):
            return False
        if snapshot.used_characters < 0 or snapshot.character_limit < 0:
            return False
        if not isinstance(snapshot.observed_at, (int, float)):
            return False
        age = time.monotonic() - snapshot.observed_at
        return 0 <= age <= self._max_quota_age_seconds and snapshot.used_characters <= snapshot.character_limit


_shared_coordinator: TtsDispatchCoordinator | None = None
_shared_coordinator_lock = threading.Lock()


def get_shared_tts_dispatch_coordinator() -> TtsDispatchCoordinator:
    """Return the process-wide coordinator shared by all TTS dispatch paths."""
    global _shared_coordinator
    coordinator = _shared_coordinator
    if coordinator is not None:
        return coordinator

    from src.integrations.elevenlabs.mcp_server import _read_quota

    with _shared_coordinator_lock:
        if _shared_coordinator is None:
            _shared_coordinator = TtsDispatchCoordinator(quota_reader=_read_quota)
        return _shared_coordinator


__all__ = [
    "QuotaSnapshot",
    "TtsDispatchCoordinator",
    "get_shared_tts_dispatch_coordinator",
]