from __future__ import annotations

import time

import pytest

from src.services.tts_dispatch_coordinator import (
    QuotaSnapshot,
    TtsDispatchCoordinator,
)


def test_quota_admission_reserves_known_capacity_and_fails_closed() -> None:
    coordinator = TtsDispatchCoordinator(
        quota_reader=lambda: QuotaSnapshot(
            used_characters=8,
            character_limit=10,
            observed_at=time.monotonic(),
        )
    )

    lease = coordinator.reserve_quota(2)

    assert lease is not None
    lease.release()

    with pytest.raises(RuntimeError, match="quota"):
        TtsDispatchCoordinator(
            quota_reader=lambda: None,
        ).reserve_quota(1)


def test_quota_admission_accounts_for_outstanding_reservations() -> None:
    coordinator = TtsDispatchCoordinator(
        quota_reader=lambda: QuotaSnapshot(
            used_characters=0,
            character_limit=5,
            observed_at=time.monotonic(),
        )
    )

    first = coordinator.reserve_quota(4)

    with pytest.raises(RuntimeError, match="quota"):
        coordinator.reserve_quota(2)

    first.release()


def test_playback_lease_serializes_complete_playback_lifetime() -> None:
    coordinator = TtsDispatchCoordinator(
        quota_reader=lambda: QuotaSnapshot(0, 100, time.monotonic())
    )
    first_started = False
    second_started = False
    first = coordinator.acquire_playback()

    def try_second_playback() -> None:
        nonlocal second_started
        lease = coordinator.acquire_playback()
        second_started = True
        lease.release()

    import threading

    thread = threading.Thread(target=try_second_playback)
    thread.start()
    thread.join(timeout=0.05)
    assert second_started is False

    first_started = True
    first.release()
    thread.join(timeout=1)

    assert first_started is True
    assert second_started is True