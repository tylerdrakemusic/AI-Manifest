# Scheduled Tasks — 👁AI-Manifest

Automated background tasks registered in Windows Task Scheduler for this project.

---

## AI_Manifest_Priority_Rescore

| Field | Value |
|-------|-------|
| **Task name** | `AI_Manifest_Priority_Rescore` |
| **Schedule** | Weekly, every Sunday at 02:00 |
| **Command** | `C:\G\python.exe f:\👁AI-Manifest\tools\weekly_priority_rescore.py` |
| **Purpose** | Re-scores all open todos in `manifest_todos.db`, detects stale high-priority items (priority ≥ 7, no `priority_history` entry in the past 30 days), auto-downgrades them, and appends a JSONL diff entry to `logs/priority_rescore.jsonl`. |
| **Dry-run flag** | Append `--dry-run` to preview changes without writing to the DB or JSONL log. |
| **Log** | `f:\👁AI-Manifest\logs\priority_rescore.jsonl` |
| **Registered** | 2026-05-24 |

### Registration command

```powershell
schtasks /Create /TN "AI_Manifest_Priority_Rescore" `
  /TR "C:\G\python.exe f:\???AI-Manifest\tools\weekly_priority_rescore.py" `
  /SC WEEKLY /D SUN /ST 02:00 `
  /RU "$env:USERDOMAIN\$env:USERNAME" /F
```

### Manual trigger

```powershell
schtasks /Run /TN "AI_Manifest_Priority_Rescore"
```

### Remove task

```powershell
schtasks /Delete /TN "AI_Manifest_Priority_Rescore" /F
```

---

## Notes

- All tasks run under the current Windows user account.
- Python executable: `C:\G\python.exe`
- Ensure `PYTHONUTF8=1` is set in the system environment for correct Unicode handling.

## AI-Manifest Database Backup

| Field | Value |
|-------|-------|
| **Task name** | `AI-Manifest-DatabaseBackup` |
| **Schedule** | Daily at 02:00 |
| **Registration** | `tools/register_database_backup_task.ps1` |
| **Launcher** | `tools/run_database_backup.ps1` |
| **Scope** | `src/data/manifest_todos.db` only |
| **Restore** | `tools/restore_database_backup.py --manifest <path> --restore-root <isolated-path> --operator-approved` |

The scheduled action contains no database key, manifest key, volume identity,
or other secret. The launcher reads those values from the current user's
environment and refuses to run when the trusted volume marker is missing or
does not match.
