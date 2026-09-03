# 🔧 Hermes Agent Restore Guide

## Prerequisites

- A fresh Hermes Agent installation (or existing one)
- Git installed
- Python 3.8+
- Access to this repository

## Quick Restore (Full)

```bash
# 1. Clone the backup repo
git clone https://github.com/hossein76e1/HERMES-AGENT.git /tmp/hermes-backup-repo
cd /tmp/hermes-backup-repo

# 2. Find the latest backup
LATEST=$(readlink -f backups/latest || ls -td backups/*/ | head -1)
echo "Restoring from: $LATEST"

# 3. Stop Hermes if running
hermes gateway stop 2>/dev/null || true

# 4. Restore configuration files
cp "$LATEST/config/config.yaml" ~/.hermes/config.yaml
cp "$LATEST/config/SOUL.md" ~/.hermes/SOUL.md
cp "$LATEST/config/.env" ~/.hermes/.env
cp "$LATEST/config/auth.json" ~/.hermes/auth.json
cp "$LATEST/config/channel_directory.json" ~/.hermes/channel_directory.json

# 5. Restore memories
cp -a "$LATEST/memories/memories/"* ~/.hermes/memories/ 2>/dev/null || true

# 6. Restore sessions
cp -a "$LATEST/sessions/sessions/"* ~/.hermes/sessions/ 2>/dev/null || true

# 7. Restore cron jobs
cp "$LATEST/cron/executions.db" ~/.hermes/cron/executions.db 2>/dev/null || true

# 8. Restore skills
cp -a "$LATEST/skills/skills/"* ~/.hermes/skills/ 2>/dev/null || true

# 9. Restore databases
cp "$LATEST/databases/state.db" ~/.hermes/state.db
cp "$LATEST/databases/kanban.db" ~/.hermes/kanban.db

# 10. Restore platform configs
cp -a "$LATEST/platforms/platforms/"* ~/.hermes/platforms/ 2>/dev/null || true

# 11. Restore state
cp -a "$LATEST/state/state/"* ~/.hermes/state/ 2>/dev/null || true

# 12. Restore runtime
cp -a "$LATEST/runtime/runtime/"* ~/.hermes/runtime/ 2>/dev/null || true

# 13. Restart Hermes
hermes gateway start
```

## Selective Restore

To restore only specific components:

```bash
# Only restore memories
cp -a "$LATEST/memories/memories/"* ~/.hermes/memories/

# Only restore config
cp "$LATEST/config/config.yaml" ~/.hermes/config.yaml
cp "$LATEST/config/SOUL.md" ~/.hermes/SOUL.md

# Only restore skills
cp -a "$LATEST/skills/skills/"* ~/.hermes/skills/

# Only restore databases
cp "$LATEST/databases/state.db" ~/.hermes/state.db
cp "$LATEST/databases/kanban.db" ~/.hermes/kanban.db
```

## Verify Backup Integrity

```bash
# Check manifest
cat "$LATEST/manifest.json" | python3 -m json.tool

# List all backed up files
ls -laR "$LATEST/"
```

## Backup Manifest Structure

The `manifest.json` in each backup contains:

```json
{
  "backup_timestamp": "2026/09/03 10:58:00",
  "backup_id": "2026-09-03_10-58-00",
  "total_files": 50,
  "total_size": "4.5M",
  "categories": {
    "core_config": ["config.yaml", "SOUL.md", ...],
    "memory": ["memories/"],
    "sessions": ["sessions/"],
    ...
  },
  "files": [
    {
      "description": "config.yaml",
      "source": "/data/.hermes/config.yaml",
      "backup_path": "2026-09-03_10-58-00/config/config.yaml",
      "size_bytes": 221
    }
  ]
}
```

## Important Notes

- **API Keys**: The `.env` file contains API keys. Keep this repo PRIVATE.
- **SQLite Files**: `state.db` and `kanban.db` are copied while Hermes is running — this is safe for small databases.
- **Sessions**: Session files may be in active use; restore after stopping Hermes.
- **Skills**: Custom skills in `~/.hermes/skills/` are fully backed up.
- **Cache Files**: Model caches can be regenerated but are included for faster startup.
