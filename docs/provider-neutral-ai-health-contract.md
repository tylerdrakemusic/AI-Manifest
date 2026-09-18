# Provider-Neutral AI Health Contract

## Ownership

`src/integrations/provider_health.py` defines AI-Manifest's local normalized
readiness result shape. `ElevenLabsClient.check_readiness()` is the provider
adapter: it performs one authenticated, non-generative `/v1/user` check with a
bounded timeout and one retry for transient failures.

The result is intentionally compatible by shape with the Workspace AI Health
consumer. This is a cross-repository contract description, not a shared Python
module. AI-Manifest has no runtime import from Workspace for readiness.

## ReadinessResult

The in-memory result contains `provider`, `state`, `latency_ms`, optional
`quota`, `capabilities`, `freshness`, and `diagnostic_code`.

The normalized states are:

- `ready`: the provider response and quota values are valid.
- `degraded`: the provider is responding with a provider/transient error or
  quota data cannot be trusted.
- `unavailable`: credentials are missing or authentication failed.
- `unknown`: transport, parsing, or unexpected failures prevent a conclusion.

The ElevenLabs capability list is `voice_synthesis`, `voice_listing`, and
`streaming`. Quota is normalized to integer `used` and `limit` values when
valid; otherwise it is `null`.

## Diagnostics And Freshness

Diagnostics are stable reason codes, not raw provider messages. The adapter
uses codes including `missing_credentials`, `authentication_failed`,
`provider_unavailable`, `provider_error`, `quota_malformed`,
`transport_error`, and `unexpected_error`. Callers must not expose API keys,
authorization headers, response bodies, or exception text in the widget.

`freshness: live` identifies a result from the current bounded check. The
result is an in-memory readiness projection. It is not a persistence contract,
database schema, polling loop, queue record, playback request, or voice
delivery authorization.

## Boundary And Exclusions

The readiness adapter is adjacent to the existing ElevenLabs client but is
separate from TTS generation, TTS queue persistence, streaming playback,
Executive Audio Brief generation, and repository voice delivery. The existing
provider-bound voice paths remain unchanged. The Workspace widget consumes the
normalized shape without importing this repository at runtime.