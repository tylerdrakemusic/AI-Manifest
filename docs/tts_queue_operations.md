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