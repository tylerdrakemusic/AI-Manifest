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
