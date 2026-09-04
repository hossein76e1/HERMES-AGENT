#!/usr/bin/env bash
# =============================================================================
# Hermes Agent Automated Backup Script
# Backs up critical Hermes data and pushes to GitHub repository
# Customize: GITHUB_REPO, GITHUB_TOKEN, GIT_USER, GIT_EMAIL
# =============================================================================
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKUP_REPO="/data/hermes-backup-repo"
BACKUP_BASE="${BACKUP_REPO}/backups"
LOG_DIR="${BACKUP_REPO}/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
BACKUP_LOG="${LOG_DIR}/backup_${TIMESTAMP}.log"
LATEST_SYMLINK="${BACKUP_BASE}/latest"

# GitHub settings — UPDATE THESE
GITHUB_REPO="https://github.com/OWNER/REPO.git"
GITHUB_TOKEN="YOUR_TOKEN_HERE"
GIT_USER="your-username"
GIT_EMAIL="your-email@users.noreply.github.com"

# ── Logging ───────────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "${BACKUP_LOG}"
}

log "═══════════════════════════════════════════════════════════════"
log "  Hermes Agent Backup — ${TIMESTAMP}"
log "═══════════════════════════════════════════════════════════════"
mkdir -p "${BACKUP_DIR}"

# ── Configure Git ────────────────────────────────────────────────────────
git config --global user.name "${GIT_USER}" 2>/dev/null || true
git config --global user.email "${GIT_EMAIL}" 2>/dev/null || true

# ── Clone backup repo if needed ──────────────────────────────────────────
if [ ! -d "${BACKUP_REPO}/.git" ]; then
    log "Cloning backup repository..."
    cd /data
    rm -rf "${BACKUP_REPO}"
    git clone "https://${GITHUB_TOKEN}@${GITHUB_REPO#https://}" "${BACKUP_REPO}"
fi
cd "${BACKUP_REPO}"
git remote set-url origin "https://${GITHUB_TOKEN}@${GITHUB_REPO#https://}" 2>/dev/null || true

# ── Backup Function ──────────────────────────────────────────────────────
backup_item() {
    local src="$1" dest="$2" desc="$3"
    if [ -e "${src}" ]; then
        mkdir -p "$(dirname "${dest}")"
        cp -a "${src}" "${dest}" 2>/dev/null || cp -rL "${src}" "${dest}" 2>/dev/null || true
        if [ -e "${dest}" ]; then
            local size=$(du -sb "${dest}" 2>/dev/null | cut -f1)
            log "  ✓ ${desc} (${size} bytes)"
            echo "${desc}|||${src}|||${dest}|||${size}" >> "${BACKUP_DIR}/.file_list.tmp"
            return 0
        fi
    fi
    log "  ✗ ${desc} — skipped"
    return 1
}

# ── Backup ───────────────────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"/{config,memories,sessions,cron,skills,platforms,databases,state,runtime,hooks,logs,cache_files,other,scripts}
> "${BACKUP_DIR}/.file_list.tmp"

log "── Core Config ──"
backup_item "${HERMES_HOME}/config.yaml" "${BACKUP_DIR}/config/config.yaml" "config.yaml"
backup_item "${HERMES_HOME}/SOUL.md" "${BACKUP_DIR}/config/SOUL.md" "SOUL.md"
backup_item "${HERMES_HOME}/.env" "${BACKUP_DIR}/config/.env" ".env"
backup_item "${HERMES_HOME}/auth.json" "${BACKUP_DIR}/config/auth.json" "auth.json"
backup_item "${HERMES_HOME}/channel_directory.json" "${BACKUP_DIR}/config/channel_directory.json" "channel_directory.json"
backup_item "${HERMES_HOME}/gateway_state.json" "${BACKUP_DIR}/config/gateway_state.json" "gateway_state.json"

log "── Memory & Sessions ──"
backup_item "${HERMES_HOME}/memories" "${BACKUP_DIR}/memories/memories" "memories/"
backup_item "${HERMES_HOME}/sessions" "${BACKUP_DIR}/sessions/sessions" "sessions/"

log "── Cron ──"
backup_item "${HERMES_HOME}/cron/executions.db" "${BACKUP_DIR}/cron/executions.db" "cron/executions.db"
backup_item "${HERMES_HOME}/cron/jobs.json" "${BACKUP_DIR}/cron/jobs.json" "cron/jobs.json"

log "── Skills ──"
backup_item "${HERMES_HOME}/skills" "${BACKUP_DIR}/skills/skills" "skills/"
backup_item "${HERMES_HOME}/skills/.usage.json" "${BACKUP_DIR}/skills/skills/.usage.json" ".usage.json"
backup_item "${HERMES_HOME}/skills/.bundled_manifest" "${BACKUP_DIR}/skills/skills/.bundled_manifest" ".bundled_manifest"

log "── Backup Script (self) ──"
backup_item "${HERMES_HOME}/scripts/backup.sh" "${BACKUP_DIR}/scripts/backup.sh" "scripts/backup.sh"

log "── Platforms ──"
backup_item "${HERMES_HOME}/platforms" "${BACKUP_DIR}/platforms/platforms" "platforms/"

log "── Databases ──"
backup_item "${HERMES_HOME}/state.db" "${BACKUP_DIR}/databases/state.db" "state.db"
backup_item "${HERMES_HOME}/kanban.db" "${BACKUP_DIR}/databases/kanban.db" "kanban.db"

log "── State & Runtime ──"
backup_item "${HERMES_HOME}/state" "${BACKUP_DIR}/state/state" "state/"
backup_item "${HERMES_HOME}/runtime" "${BACKUP_DIR}/runtime/runtime" "runtime/"
backup_item "${HERMES_HOME}/hooks" "${BACKUP_DIR}/hooks/hooks" "hooks/"

log "── Logs ──"
backup_item "${HERMES_HOME}/logs" "${BACKUP_DIR}/logs/hermes_logs" "logs/"

log "── Caches ──"
backup_item "${HERMES_HOME}/.skills_prompt_snapshot.json" "${BACKUP_DIR}/cache_files/skills_prompt_snapshot.json" "skills_prompt_snapshot.json"
backup_item "${HERMES_HOME}/provider_models_cache.json" "${BACKUP_DIR}/cache_files/provider_models_cache.json" "provider_models_cache.json"
backup_item "${HERMES_HOME}/models_dev_cache.json" "${BACKUP_DIR}/other/models_dev_cache.json" "models_dev_cache.json"

# ── Manifest ─────────────────────────────────────────────────────────────
FILE_COUNT=$(wc -l < "${BACKUP_DIR}/.file_list.tmp" 2>/dev/null || echo "0")
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
python3 -c "
import json, os
backup_dir = '${BACKUP_DIR}'
timestamp = '${TIMESTAMP}'
files = []
if os.path.exists('${BACKUP_DIR}/.file_list.tmp'):
    with open('${BACKUP_DIR}/.file_list.tmp') as f:
        for line in f:
            parts = line.strip().split('|||')
            if len(parts) >= 3:
                files.append({'description': parts[0], 'source': parts[1],
                    'backup_path': os.path.relpath(parts[2], backup_dir),
                    'size_bytes': int(parts[3]) if len(parts) > 3 else 0})
manifest = {'backup_id': timestamp, 'total_files': len(files),
    'total_size': '${TOTAL_SIZE}', 'files': files}
with open(os.path.join(backup_dir, 'manifest.json'), 'w') as f:
    json.dump(manifest, f, indent=2)
print(f'Manifest: {len(files)} items')
" 2>&1 | tee -a "${BACKUP_LOG}"
rm -f "${BACKUP_DIR}/.file_list.tmp"

# ── Archive ──────────────────────────────────────────────────────────────
cd "${BACKUP_BASE}"
tar -czf "${TIMESTAMP}.tar.gz" "${TIMESTAMP}/" 2>/dev/null || true
ARCHIVE_SIZE=$(du -sh "${TIMESTAMP}.tar.gz" 2>/dev/null | cut -f1)
rm -f "${LATEST_SYMLINK}" && ln -s "${TIMESTAMP}" "${LATEST_SYMLINK}"

# ── Git Push ─────────────────────────────────────────────────────────────
cd "${BACKUP_REPO}"
git config user.name "${GIT_USER}" 2>/dev/null || true
git config user.email "${GIT_EMAIL}" 2>/dev/null || true
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
git checkout "${DEFAULT_BRANCH}" 2>/dev/null || git checkout -b "${DEFAULT_BRANCH}" 2>/dev/null || true
git add -A
if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "🔄 Auto-backup: ${TIMESTAMP}" 2>&1 | tee -a "${BACKUP_LOG}"
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null)
    if git push origin "${DEFAULT_BRANCH}" 2>&1 | tee -a "${BACKUP_LOG}"; then
        PUSH_STATUS="success"
    else
        PUSH_STATUS="failed"
    fi
else
    PUSH_STATUS="no_changes"
fi

log "Backup ${TIMESTAMP}: ${FILE_COUNT} files, ${TOTAL_SIZE}, push=${PUSH_STATUS}"
ls -t "${LOG_DIR}"/backup_*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true
echo "BACKUP_RESULT: ${TIMESTAMP}|${FILE_COUNT}|${TOTAL_SIZE}|${PUSH_STATUS}|${COMMIT_HASH:-N/A}"
