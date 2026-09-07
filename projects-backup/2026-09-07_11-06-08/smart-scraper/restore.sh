#!/usr/bin/env bash
# =============================================================================
# Hermes Agent Restore Script
# Restores Hermes from a backup on a fresh VPS
# =============================================================================
set -euo pipefail

BACKUP_REPO="/data/hermes-backup-repo"
HERMES_HOME="${HOME}/.hermes"

echo "🔧 Hermes Agent Restore Script"
echo "================================"

# 1. Check if backup repo exists
if [ ! -d "${BACKUP_REPO}" ]; then
    echo "📦 Cloning backup repository..."
    cd /data
    git clone "https://github.com/hossein76e1/HERMES-AGENT.git" hermes-backup-repo
fi

cd "${BACKUP_REPO}"

# 2. Find latest backup
LATEST=$(readlink -f backups/latest 2>/dev/null || ls -td backups/*/ 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    echo "❌ No backup found!"
    exit 1
fi

echo "📂 Restoring from: $(basename $LATEST)"

# 3. Stop Hermes if running
echo "⏸️  Stopping Hermes..."
hermes gateway stop 2>/dev/null || true

# 4. Create hermes home
mkdir -p "${HERMES_HOME}"

# 5. Restore configuration
echo "⚙️  Restoring configuration..."
cp "${LATEST}/config/config.yaml" "${HERMES_HOME}/config.yaml" 2>/dev/null || true
cp "${LATEST}/config/SOUL.md" "${HERMES_HOME}/SOUL.md" 2>/dev/null || true
cp "${LATEST}/config/.env" "${HERMES_HOME}/.env" 2>/dev/null || true
cp "${LATEST}/config/auth.json" "${HERMES_HOME}/auth.json" 2>/dev/null || true
cp "${LATEST}/config/channel_directory.json" "${HERMES_HOME}/channel_directory.json" 2>/dev/null || true
cp "${LATEST}/config/gateway_state.json" "${HERMES_HOME}/gateway_state.json" 2>/dev/null || true

# 6. Restore memories
echo "🧠 Restoring memories..."
mkdir -p "${HERMES_HOME}/memories"
cp -a "${LATEST}/memories/memories/"* "${HERMES_HOME}/memories/" 2>/dev/null || true

# 7. Restore sessions
echo "💬 Restoring sessions..."
mkdir -p "${HERMES_HOME}/sessions"
cp -a "${LATEST}/sessions/sessions/"* "${HERMES_HOME}/sessions/" 2>/dev/null || true

# 8. Restore cron jobs
echo "⏰ Restoring cron jobs..."
mkdir -p "${HERMES_HOME}/cron"
cp "${LATEST}/cron/executions.db" "${HERMES_HOME}/cron/executions.db" 2>/dev/null || true

# 9. Restore skills
echo "🛠️  Restoring skills..."
mkdir -p "${HERMES_HOME}/skills"
cp -a "${LATEST}/skills/skills/"* "${HERMES_HOME}/skills/" 2>/dev/null || true

# 10. Restore databases
echo "🗄️  Restoring databases..."
cp "${LATEST}/databases/state.db" "${HERMES_HOME}/state.db" 2>/dev/null || true
cp "${LATEST}/databases/kanban.db" "${HERMES_HOME}/kanban.db" 2>/dev/null || true

# 11. Restore platform configs
echo "📱 Restoring platform configs..."
mkdir -p "${HERMES_HOME}/platforms"
cp -a "${LATEST}/platforms/platforms/"* "${HERMES_HOME}/platforms/" 2>/dev/null || true

# 12. Restore state
echo "🔄 Restoring state..."
mkdir -p "${HERMES_HOME}/state"
cp -a "${LATEST}/state/state/"* "${HERMES_HOME}/state/" 2>/dev/null || true

# 13. Restore runtime
mkdir -p "${HERMES_HOME}/runtime"
cp -a "${LATEST}/runtime/runtime/"* "${HERMES_HOME}/runtime/" 2>/dev/null || true

# 14. Restore other files
cp "${LATEST}/other/.initialized" "${HERMES_HOME}/.initialized" 2>/dev/null || true
cp "${LATEST}/other/install_id" "${HERMES_HOME}/install_id" 2>/dev/null || true
cp "${LATEST}/cache_files/.skills_prompt_snapshot.json" "${HERMES_HOME}/.skills_prompt_snapshot.json" 2>/dev/null || true
cp "${LATEST}/cache_files/provider_models_cache.json" "${HERMES_HOME}/provider_models_cache.json" 2>/dev/null || true

# 15. Re-clone backup repo for future backups
if [ ! -d "${BACKUP_REPO}/.git" ]; then
    echo "📦 Re-initializing backup repo..."
    cd /data
    rm -rf "${BACKUP_REPO}"
    git clone "https://github.com/hossein76e1/HERMES-AGENT.git" hermes-backup-repo
fi

# 16. Setup cron job for backups
echo "⏰ Setting up backup cron..."
mkdir -p "${HERMES_HOME}/scripts"
if [ -f "${BACKUP_REPO}/backups/latest/scripts/backup.sh" ]; then
    cp "${BACKUP_REPO}/backups/latest/scripts/backup.sh" "${HERMES_HOME}/scripts/backup.sh"
fi

echo ""
echo "✅ Restore complete!"
echo "================================"
echo "Next steps:"
echo "1. Install Hermes: pip install hermes-agent"
echo "2. Start Hermes: hermes gateway start"
echo "3. Verify: hermes gateway status"
