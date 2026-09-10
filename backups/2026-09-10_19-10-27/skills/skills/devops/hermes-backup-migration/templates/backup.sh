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

# ── Lock file to prevent concurrent backups ────────────────────────────────
LOCK_FILE="${BACKUP_REPO}/.backup.lock"
LOCK_FD=200

# ── Retention: keep last N backups ─────────────────────────────────────────
MAX_BACKUPS=10

# ── Logging ───────────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "${BACKUP_LOG}"
}

# ── Acquire lock ───────────────────────────────────────────────────────────
acquire_lock() {
    eval "exec ${LOCK_FD}>${LOCK_FILE}"
    if ! flock -n ${LOCK_FD}; then
        log "⏳ Another backup is running, exiting"
        exit 0
    fi
    echo $$ >&${LOCK_FD}
}

# ── Cleanup old backups ────────────────────────────────────────────────────
cleanup_old_backups() {
    log "Cleaning up old backups (keeping last ${MAX_BACKUPS})..."
    cd "${BACKUP_BASE}"
    ls -1dt */ 2>/dev/null | grep -v '^latest$' | tail -n +$((MAX_BACKUPS + 1)) | while read dir; do
        log "  Removing old backup: ${dir%/}"
        rm -rf "${dir%/}"
        rm -f "${BACKUP_BASE}/${dir%/}.tar.gz"
    done
    ls -t "${LOG_DIR}"/backup_*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true
    ls -t "${LOG_DIR}"/watch_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true
}

log "════════════════════════════════════════════════════════════════"
log "  Hermes Agent Backup — ${TIMESTAMP}"
log "════════════════════════════════════════════════════════════════"
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

# Acquire lock and cleanup old backups
acquire_lock
cleanup_old_backups

# ── Backup Function ──────────────────────────────────────────────────────
backup_item() {
    local src="$1" dest="$2" desc="$3" sanitize="${4:-false}"
    if [ -e "${src}" ]; then
        mkdir -p "$(dirname "${dest}")"
        if [ "${sanitize}" = "true" ] && [[ "${src}" == *".env" ]]; then
            sed 's/^\([^=]*\)=.*/\1=***REDACTED***/' "${src}" > "${dest}" 2>/dev/null || cp -a "${src}" "${dest}"
        elif [ "${sanitize}" = "true" ] && [[ "${src}" == *"state.db" || "${src}" == *"auth.json" || "${src}" == *"gateway_state.json" ]]; then
            log "  ⊘ ${desc} — skipped for GitHub (contains secrets)"
            return 0
        else
            cp -a "${src}" "${dest}" 2>/dev/null || cp -rL "${src}" "${dest}" 2>/dev/null || true
        fi
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

# ── Sanitize for GitHub push ─────────────────────────────────────────────
sanitize_for_github() {
    local src_dir="$1" dest_dir="$2"
    log "Creating sanitized copy for GitHub..."
    cp -a "${src_dir}" "${dest_dir}"
    rm -f "${dest_dir}/databases/state.db"
    rm -f "${dest_dir}/databases/kanban.db"
    rm -f "${dest_dir}/config/.env"
    rm -f "${dest_dir}/config/auth.json"
    rm -f "${dest_dir}/config/gateway_state.json"
    if [ -f "${src_dir}/config/.env" ]; then
        sed 's/^\([^=]*\)=.*/\1=***REDACTED***/' "${src_dir}/config/.env" > "${dest_dir}/config/.env.example" 2>/dev/null || true
    fi
    log "Sanitized copy ready at ${dest_dir}"
}

# ── Create backup structure ──────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"/{config,memories,sessions,cron,skills,platforms,state,runtime,hooks,logs,databases,cache_files,other}
> "${BACKUP_DIR}/.file_list.tmp"

log "── Core Configuration ──"
backup_item "${HERMES_HOME}/config.yaml" "${BACKUP_DIR}/config/config.yaml" "config.yaml" "true"
backup_item "${HERMES_HOME}/SOUL.md" "${BACKUP_DIR}/config/SOUL.md" "SOUL.md" "true"
backup_item "${HERMES_HOME}/.env" "${BACKUP_DIR}/config/.env" ".env (environment variables)" "true"
backup_item "${HERMES_HOME}/auth.json" "${BACKUP_DIR}/config/auth.json" "auth.json" "true"
backup_item "${HERMES_HOME}/channel_directory.json" "${BACKUP_DIR}/config/channel_directory.json" "channel_directory.json" "true"
backup_item "${HERMES_HOME}/gateway_state.json" "${BACKUP_DIR}/config/gateway_state.json" "gateway_state.json" "true"

log "── Memory & User Data ──"
backup_item "${HERMES_HOME}/memories" "${BACKUP_DIR}/memories/memories" "memories/" "true"

log "── Sessions ──"
backup_item "${HERMES_HOME}/sessions" "${BACKUP_DIR}/sessions/sessions" "sessions/" "true"

log "── Cron & Scheduled Jobs ──"
backup_item "${HERMES_HOME}/cron/executions.db" "${BACKUP_DIR}/cron/executions.db" "cron/executions.db" "true"
find "${HERMES_HOME}/cron" -maxdepth 1 -name "*.json" -o -name "*.yaml" -o -name "*.yml" 2>/dev/null | while read f; do
    backup_item "$f" "${BACKUP_DIR}/cron/$(basename "$f")" "cron/$(basename "$f")" "true"
done

log "── Skills ──"
backup_item "${HERMES_HOME}/skills" "${BACKUP_DIR}/skills/skills" "skills/" "true"

log "── Platform Configurations ──"
backup_item "${HERMES_HOME}/platforms" "${BACKUP_DIR}/platforms/platforms" "platforms/" "true"

log "── State Data ──"
backup_item "${HERMES_HOME}/state.db" "${BACKUP_DIR}/databases/state.db" "state.db" "true"
backup_item "${HERMES_HOME}/kanban.db" "${BACKUP_DIR}/databases/kanban.db" "kanban.db" "true"
backup_item "${HERMES_HOME}/state" "${BACKUP_DIR}/state/state" "state/" "true"

log "── Runtime State ──"
backup_item "${HERMES_HOME}/runtime" "${BACKUP_DIR}/runtime/runtime" "runtime/" "true"

log "── Hooks ──"
backup_item "${HERMES_HOME}/hooks" "${BACKUP_DIR}/hooks/hooks" "hooks/" "true"

log "── Logs ──"
backup_item "${HERMES_HOME}/logs" "${BACKUP_DIR}/logs/hermes_logs" "hermes logs" "true"

log "── Cache/Config Files ──"
backup_item "${HERMES_HOME}/.skills_prompt_snapshot.json" "${BACKUP_DIR}/cache_files/skills_prompt_snapshot.json" ".skills_prompt_snapshot.json" "true"
backup_item "${HERMES_HOME}/provider_models_cache.json" "${BACKUP_DIR}/cache_files/provider_models_cache.json" "provider_models_cache.json" "true"
backup_item "${HERMES_HOME}/ollama_cloud_models_cache.json" "${BACKUP_DIR}/cache_files/ollama_cloud_models_cache.json" "ollama_cloud_models_cache.json" "true"

log "── Other Metadata ──"
backup_item "${HERMES_HOME}/.initialized" "${BACKUP_DIR}/other/.initialized" ".initialized" "true"
backup_item "${HERMES_HOME}/.update_check" "${BACKUP_DIR}/other/.update_check" ".update_check" "true"
backup_item "${HERMES_HOME}/install_id" "${BACKUP_DIR}/other/install_id" "install_id" "true"
backup_item "${HERMES_HOME}/models_dev_cache.json" "${BACKUP_DIR}/other/models_dev_cache.json" "models_dev_cache.json" "true"
backup_item "${HERMES_HOME}/gateway-starts.log" "${BACKUP_DIR}/other/gateway-starts.log" "gateway-starts.log" "true"

# ── Create Manifest ──────────────────────────────────────────────────────
log "Creating manifest..."
FILE_COUNT=$(wc -l < "${BACKUP_DIR}/.file_list.tmp" 2>/dev/null || echo "0")
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
python3 -c "
import json, os, sys
backup_dir = '${BACKUP_DIR}'
timestamp = '${TIMESTAMP}'
files = []
if os.path.exists('${BACKUP_DIR}/.file_list.tmp'):
    with open('${BACKUP_DIR}/.file_list.tmp') as f:
        for line in f:
            line = line.strip()
            if line and '|||' in line:
                parts = line.split('|||')
                if len(parts) >= 3:
                    files.append({
                        'description': parts[0],
                        'source': parts[1],
                        'backup_path': os.path.relpath(parts[2], backup_dir),
                        'size_bytes': int(parts[3]) if len(parts) > 3 else 0
                    })
manifest = {
    'backup_timestamp': timestamp.replace('_', ' ').replace('-', '/', 2),
    'backup_id': timestamp,
    'total_files': len(files),
    'total_size': '${TOTAL_SIZE}',
    'backup_root': backup_dir,
    'categories': {
        'core_config': ['config.yaml', 'SOUL.md', '.env', 'auth.json', 'channel_directory.json', 'gateway_state.json'],
        'memory': ['memories/'],
        'sessions': ['sessions/'],
        'cron_jobs': ['cron/'],
        'skills': ['skills/'],
        'platforms': ['platforms/'],
        'databases': ['state.db', 'kanban.db'],
        'state': ['state/'],
        'runtime': ['runtime/'],
        'hooks': ['hooks/'],
        'logs': ['logs/'],
        'cache_files': ['.skills_prompt_snapshot.json', 'provider_models_cache.json'],
        'metadata': ['.initialized', '.update_check', 'install_id']
    },
    'files': files
}
with open(os.path.join(backup_dir, 'manifest.json'), 'w') as f:
    json.dump(manifest, f, indent=2)
print(f'Manifest created: {len(files)} items cataloged')
" 2>&1 | tee -a "${BACKUP_LOG}"
rm -f "${BACKUP_DIR}/.file_list.tmp"

# ── Create tarball for space efficiency ──────────────────────────────────
log "Creating compressed archive..."
cd "${BACKUP_BASE}"
tar -czf "${BACKUP_BASE}/${TIMESTAMP}.tar.gz" "${TIMESTAMP}/" 2>/dev/null || true
ARCHIVE_SIZE=$(du -sh "${BACKUP_BASE}/${TIMESTAMP}.tar.gz" 2>/dev/null | cut -f1)
log "Archive created: ${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})"
rm -f "${LATEST_SYMLINK}"
ln -s "${TIMESTAMP}" "${LATEST_SYMLINK}"

# ── Generate backup log entry ────────────────────────────────────────────
log "── Backup Summary ──"
log "  Backup ID: ${TIMESTAMP}"
log "  Files backed up: ${FILE_COUNT}"
log "  Total size: ${TOTAL_SIZE}"
log "  Archive: ${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})"

# ── Push to GitHub ───────────────────────────────────────────────────────
log "Pushing to GitHub..."
cd "${BACKUP_REPO}"
git config user.name "${GIT_USER}" 2>/dev/null || true
git config user.email "${GIT_EMAIL}" 2>/dev/null || true
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
git checkout "${DEFAULT_BRANCH}" 2>/dev/null || git checkout -b "${DEFAULT_BRANCH}" 2>/dev/null || true
git add -A
if git diff --cached --quiet 2>/dev/null; then
    log "  No changes to push."
    PUSH_STATUS="no_changes"
else
    git commit -m "🔄 Auto-backup: ${TIMESTAMP}\n\nBackup ID: ${TIMESTAMP}\nFiles: ${FILE_COUNT}\nSize: ${TOTAL_SIZE}\nArchive: ${ARCHIVE_SIZE}\nTriggered by: automated backup script\n" 2>&1 | tee -a "${BACKUP_LOG}"
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null)
    log "  Commit: ${COMMIT_HASH}"
    cat > /tmp/push_helper.sh << 'SCRIPT'
#!/bin/bash
cd "${BACKUP_REPO}"
git config credential.helper '!f() { echo "username=${GIT_USER}"; echo "password=${GITHUB_TOKEN}"; }; f'
GIT_TERMINAL_PROMPT=0 git push origin "${DEFAULT_BRANCH}" 2>&1
SCRIPT
    chmod +x /tmp/push_helper.sh
    if bash /tmp/push_helper.sh 2>&1 | tee -a "${BACKUP_LOG}"; then
        log "  ✓ Push successful!"
        PUSH_STATUS="success"
    else
        log "  ✗ Push failed!"
        PUSH_STATUS="failed"
    fi
    rm -f /tmp/push_helper.sh
fi

# ── Final Log Entry ─────────────────────────────────────────────────────
log "═══════════════════════════════════════════════════════════════"
log "  Backup Complete: ${TIMESTAMP}"
log "  Push Status: ${PUSH_STATUS}"
log "  Commit: ${COMMIT_HASH:-N/A}"
log "═══════════════════════════════════════════════════════════════"
echo ""
echo "BACKUP_RESULT: ${TIMESTAMP}|${FILE_COUNT}|${TOTAL_SIZE}|${ARCHIVE_SIZE}|${PUSH_STATUS}|${COMMIT_HASH:-N/A}"
