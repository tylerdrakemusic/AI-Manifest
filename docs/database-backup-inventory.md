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