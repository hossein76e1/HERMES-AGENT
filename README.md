# 🔄 Hermes Agent Backup Repository

This repository contains automated backups of the Hermes Agent configuration, memory, skills, sessions, and all critical data.

## Structure

```
backups/
├── latest -> 2026-09-03_10-58-00/    (symlink to latest backup)
├── 2026-09-03_10-58-00/
│   ├── manifest.json          # Backup metadata
│   ├── config/                # Configuration files
│   ├── memories/              # User memories & preferences
│   ├── sessions/              # Conversation sessions
│   ├── cron/                  # Scheduled jobs
│   ├── skills/                # All skills
│   ├── platforms/             # Platform configs
│   ├── databases/             # state.db, kanban.db
│   ├── state/                 # Runtime state
│   ├── hooks/                 # Custom hooks
│   ├── logs/                  # Hermes logs
│   └── cache_files/           # Model caches
└── 2026-09-03_10-58-00.tar.gz # Compressed archive
```

## What's Backed Up

| Category | Description |
|----------|-------------|
| config.yaml | Main Hermes configuration |
| SOUL.md | Agent personality/instructions |
| .env | Environment variables & API keys |
| memories/ | User memories & persistent data |
| sessions/ | Conversation session data |
| cron/ | Scheduled jobs & execution history |
| skills/ | All installed skills & templates |
| platforms/ | Telegram & other platform configs |
| state.db | Primary state database |
| kanban.db | Kanban/task database |
| auth.json | Authentication tokens |
| gateway_state.json | Gateway runtime state |

## Backup Schedule

Every 12 hours via cron job, managed by Hermes Agent.

## Restore Instructions

See `RESTORE.md` in the repository root for complete restore procedures.

## Automation

- **Script**: `/data/.hermes/scripts/backup.sh`
- **Cron**: Every 12 hours (managed via Hermes cron system)
- **Push**: Auto-commits and pushes to this repository via HTTPS
