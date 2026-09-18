"""Provider-neutral readiness result contract."""

from __future__ import annotations

from typing import TypedDict


class Quota(TypedDict):
    """Normalized provider quota values."""

    used: int
    limit: int


class ReadinessResult(TypedDict):
    """Normalized, non-persistent provider readiness result."""

    provider: str
    state: str
    latency_ms: float | None
    quota: Quota | None
    capabilities: list[str]
    freshness: str
    diagnostic_code: str | None


READINESS_STATES = frozenset({"ready", "degraded", "unavailable", "unknown"})
ELEVENLABS_CAPABILITIES = ["voice_synthesis", "voice_listing", "streaming"]


def readiness_result(
    *,
    state: str,
    latency_ms: float | None,
    quota: Quota | None,
    diagnostic_code: str | None,
) -> ReadinessResult:
    """Build the stable provider-neutral result shape for a live check."""
    if state not in READINESS_STATES:
        state = "unknown"
    return {
        "provider": "elevenlabs",
        "state": state,
        "latency_ms": latency_ms,
        "quota": quota,
        "capabilities": list(ELEVENLABS_CAPABILITIES),
        "freshness": "live",
        "diagnostic_code": diagnostic_code,
    }