# Durable TTS Queue Operations

The SQLite-backed queue is stored in `manifest_todos.db` and is safe to use
with a process restart. `TtsQueueWorker` requeues `IN_PROGRESS` jobs whose
`started_at` is older than `lease_timeout_seconds` (five minutes by default).
Recovery preserves `retry_count` and records an entry in
`tts_queue_recoveries`.

## Retry policy

HTTP 408, 429, and 5xx responses, plus `httpx.RequestError`, are transient.
They are retried with bounded exponential backoff. A numeric `Retry-After`
header takes precedence, subject to the configured maximum delay. Other 4xx
responses are permanent and end in `FAILED`. The job's `max_retries` value
controls terminal failure.

## Publication and billing

Audio is written to a temporary file and atomically published as
`output/tts/<job-id>.mp3`. The deterministic path makes recovery at-least-once:
if a process exits after publication but before the database update, a retry
may call ElevenLabs again and replace the same path. This can result in
duplicate provider billing, so callers should use the queue's retry history
when reconciling usage.

## Governed repository voice

Use `src.services.governed_repository_voice.submit_repository_voice()` for
repository voice. It is the first authorized consumer for blocking decisions:
it validates the decision ID and text, inserts a `PENDING` queue job, and
returns a `RepositoryVoiceSubmissionResult`. Ordinary status narration is out
of scope. The boundary does not call ElevenLabs or mutate the caller's
decision state. A non-empty `decision_id` is protected by a SQLite unique
index, so concurrent submissions converge on one job and report
`deduplicated=True` for ignored duplicates. The legacy
`src.services.governed_voice_alerts.submit_alert()` import remains an alias for
existing consumers.

Provider synthesis remains asynchronous through `TtsQueueWorker`. The
`playback` callback is the injected local-capability boundary, so tests and
deployments can provide their own playback implementation without changing
queue or repository-voice authorization. When no callback is injected on
Windows, `windows_playback` uses the native `winmm` multimedia API through
MCI: it opens the published MP3 as `mpegvideo` and issues a background `play`
command. It does not call `os.startfile`, open the Windows-associated player,
or launch a visible application.

MCI playback is asynchronous. `windows_playback` schedules a daemon cleanup
timer to close the native MCI alias after 120 seconds, which keeps the
operation bounded without stopping audio immediately. The cleanup is best
effort; a playback diagnostic must not hold the queue worker open indefinitely.

Playback is decision-scoped: the worker invokes the injected capability only
when the queue job contains a stable, non-empty persisted `decision_id`.
Ordinary queue jobs without that identifier are never played. The decision ID
is not regenerated or inferred from playback state, so retries and concurrent
submissions use the same authorization boundary described above.

Synthesis and atomic publication determine the queue result. Playback runs
after the job is marked `DONE`; playback exceptions are logged as
`PLAYBACK_FAILED` diagnostics and do not change a successfully synthesized
job back to `FAILED` or trigger another ElevenLabs attempt. This is
intentional fail-open playback behavior: inspect lifecycle logs for local
playback failures while treating the persisted audio and queue job as
complete.

## Operations CLI

The CLI emits JSON and never prints credentials:

```powershell
C:\G\python.exe tools\tts_queue.py --db path\to\manifest_todos.db status
C:\G\python.exe tools\tts_queue.py --db path\to\manifest_todos.db job 42
C:\G\python.exe tools\tts_queue.py --db path\to\manifest_todos.db recover-stale --lease-timeout 300
```

Worker lifecycle records are structured JSON log messages. They include job
ID, lifecycle event, character count, retry count, latency, output size,
backoff, and provider error fields when applicable. Quota data is only logged
when an existing caller already has it; the queue does not persist credentials
or fetch quota solely for logging.