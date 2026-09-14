from __future__ import annotations

import threading
import sys
import time
import types

import pytest

import src.services.tts_dispatch_coordinator as coordinator_module
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


def test_shared_coordinator_is_singleton_during_concurrent_first_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent first callers must all receive one process-wide coordinator."""
    first_constructor_started = threading.Event()
    release_first_constructor = threading.Event()
    real_coordinator = coordinator_module.TtsDispatchCoordinator

    def delayed_constructor(*, quota_reader):
        first_constructor_started.set()
        release_first_constructor.wait(timeout=1)
        return real_coordinator(quota_reader=quota_reader)

    monkeypatch.setattr(coordinator_module, "_shared_coordinator", None)
    monkeypatch.setattr(coordinator_module, "TtsDispatchCoordinator", delayed_constructor)
    monkeypatch.setitem(
        sys.modules,
        "src.integrations.elevenlabs.mcp_server",
        types.SimpleNamespace(_read_quota=lambda: None),
    )

    barrier = threading.Barrier(16)
    instances: list[object] = []

    def get_coordinator() -> None:
        barrier.wait()
        instances.append(coordinator_module.get_shared_tts_dispatch_coordinator())

    threads = [threading.Thread(target=get_coordinator) for _ in range(16)]
    for thread in threads:
        thread.start()

    assert first_constructor_started.wait(timeout=1)
    release_first_constructor.set()
    for thread in threads:
        thread.join(timeout=1)

    assert len(instances) == len(threads)
    assert len({id(instance) for instance in instances}) == 1