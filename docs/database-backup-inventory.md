# AI-Manifest Database Backup Inventory

The inventory at `src/config/database_backup_inventory.json` is the AI-Manifest
projection of the shared manifest-driven database backup contract.

It contains policy metadata only. It does not contain database contents, key
values, or backup artifacts. Key names identify system environment variables;
the corresponding values remain outside the repository.

`manifest_todos.db` is the canonical coordination store and is explicitly
approved for the shared backup flow. Legacy `todos.db` and generated
`lily_config.db` remain registered for auditability but are default-denied.

Future databases must be added as inventory entries with an explicit
`backup_allowed` decision. Backup selection reads the inventory generically, so
no per-database implementation branch is required.

## Operational Contract

This FR activates only the `manifest-todos` entry. The runner resolves
`src/data/manifest_todos.db` from the explicit AI-Manifest project root; it does
not scan the workspace, worktrees, output, temporary, log, or virtual-environment
directories. The legacy and generated stores remain default-denied.

The scheduled task passes only the project root and inventory path. The backup
volume path, trusted volume marker identity, manifest HMAC key, and SQLCipher
database key are read from environment variables. The PowerShell 5.1 launcher
hydrates User-scope values before invoking Python and validates the trusted
marker before any source read.

Each generation is published atomically with SHA-256 file identity metadata and
an HMAC-SHA256 authenticated manifest. Restore is a separate operator-approved
operation into an isolated directory; the restored SQLCipher file is reopened
with `MANIFEST_TODOS_DB_KEY` during validation. Audit records contain only
generation locators and redacted target identifiers.