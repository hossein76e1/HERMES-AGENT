#!/usr/bin/env bash
# =============================================================================
# Hermes Agent Automated Backup Script
# Backs up critical Hermes data and pushes to GitHub repository
# =============================================================================
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKUP_REPO="/data/hermes-backup-repo"
BACKUP_BASE="${BACKUP_REPO}/backups"
LOG_DIR="${BACKUP_REPO}/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
MANIFEST_FILE="${BACKUP_DIR}/manifest.json"
BACKUP_LOG="${LOG_DIR}/backup_${TIMESTAMP}.log"
LATEST_SYMLINK="${BACKUP_BASE}/latest"

# GitHub settings
GITHUB_REPO="https://github.com/hossein76e1/HERMES-AGENT.git"
GITHUB_TOKEN="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"
GIT_USER="hossein76e1"
GIT_EMAIL="hossein76e1@users.noreply.github.com"

# ── Logging ───────────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "${BACKUP_LOG}"
}

# ── Initialize backup directory ───────────────────────────────────────────
log "═══════════════════════════════════════════════════════════════"
log "  Hermes Agent Backup — ${TIMESTAMP}"
log "═══════════════════════════════════════════════════════════════"

mkdir -p "${BACKUP_DIR}"

# ── Configure Git ────────────────────────────────────────────────────────
log "Configuring git..."
git config --global user.name "${GIT_USER}" 2>/dev/null || true
git config --global user.email "${GIT_EMAIL}" 2>/dev/null || true

# ── Initialize / clone backup repo if needed ─────────────────────────────
if [ ! -d "${BACKUP_REPO}/.git" ]; then
    log "Cloning backup repository..."
    cd /data
    rm -rf "${BACKUP_REPO}"
    git clone "https://${GITHUB_TOKEN}@github.com/hossein76e1/HERMES-AGENT.git" "${BACKUP_REPO}"
    log "Repository cloned successfully."
fi

cd "${BACKUP_REPO}"

# Ensure remote uses HTTPS with token
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/hossein76e1/HERMES-AGENT.git" 2>/dev/null || \
    git remote add origin "https://${GITHUB_TOKEN}@github.com/hossein76e1/HERMES-AGENT.git" 2>/dev/null || true

# ── Backup Function ──────────────────────────────────────────────────────
backup_item() {
    local src="$1"
    local dest="$2"
    local desc="$3"
    
    if [ -e "${src}" ]; then
        mkdir -p "$(dirname "${dest}")"
        cp -a "${src}" "${dest}" 2>/dev/null || {
            # If cp -a fails (e.g., on some symlink combos), try cp -rL
            cp -rL "${src}" "${dest}" 2>/dev/null || true
        }
        if [ -e "${dest}" ]; then
            local size=$(du -sb "${dest}" 2>/dev/null | cut -f1)
            log "  ✓ ${desc} (${size} bytes)"
            echo "${desc}|||${src}|||${dest}|||${size}" >> "${BACKUP_DIR}/.file_list.tmp"
            return 0
        fi
    fi
    log "  ✗ ${desc} — not found, skipping"
    return 1
}

# ── Create backup structure ──────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"/{config,memories,sessions,cron,skills,platforms,state,runtime,hooks,logs,databases,cache_files,other}

log "Backing up critical files..."
> "${BACKUP_DIR}/.file_list.tmp"

# 1. Core Configuration
log "── Core Configuration ──"
backup_item "${HERMES_HOME}/config.yaml" "${BACKUP_DIR}/config/config.yaml" "config.yaml"
backup_item "${HERMES_HOME}/SOUL.md" "${BACKUP_DIR}/config/SOUL.md" "SOUL.md"
backup_item "${HERMES_HOME}/.env" "${BACKUP_DIR}/config/.env" ".env (environment variables)"
backup_item "${HERMES_HOME}/auth.json" "${BACKUP_DIR}/config/auth.json" "auth.json"
backup_item "${HERMES_HOME}/channel_directory.json" "${BACKUP_DIR}/config/channel_directory.json" "channel_directory.json"
backup_item "${HERMES_HOME}/gateway_state.json" "${BACKUP_DIR}/config/gateway_state.json" "gateway_state.json"

# 2. Memory & User Data
log "── Memory & User Data ──"
backup_item "${HERMES_HOME}/memories" "${BACKUP_DIR}/memories/memories" "memories/"

# 3. Sessions
log "── Sessions ──"
backup_item "${HERMES_HOME}/sessions" "${BACKUP_DIR}/sessions/sessions" "sessions/"

# 4. Cron & Scheduled Jobs
log "── Cron & Scheduled Jobs ──"
backup_item "${HERMES_HOME}/cron/executions.db" "${BACKUP_DIR}/cron/executions.db" "cron/executions.db"
# Backup all cron jobs (not locks/pipes)
find "${HERMES_HOME}/cron" -maxdepth 1 -name "*.json" -o -name "*.yaml" -o -name "*.yml" 2>/dev/null | while read f; do
    backup_item "$f" "${BACKUP_DIR}/cron/$(basename "$f")" "cron/$(basename "$f")"
done

# 5. Skills (custom + installed)
log "── Skills ──"
backup_item "${HERMES_HOME}/skills" "${BACKUP_DIR}/skills/skills" "skills/"

# 6. Platform Configs
log "── Platform Configurations ──"
backup_item "${HERMES_HOME}/platforms" "${BACKUP_DIR}/platforms/platforms" "platforms/"

# 7. State
log "── State Data ──"
backup_item "${HERMES_HOME}/state.db" "${BACKUP_DIR}/databases/state.db" "state.db"
backup_item "${HERMES_HOME}/kanban.db" "${BACKUP_DIR}/databases/kanban.db" "kanban.db"
backup_item "${HERMES_HOME}/state" "${BACKUP_DIR}/state/state" "state/"

# 8. Runtime
log "── Runtime State ──"
backup_item "${HERMES_HOME}/runtime" "${BACKUP_DIR}/runtime/runtime" "runtime/"

# 9. Hooks
log "── Hooks ──"
backup_item "${HERMES_HOME}/hooks" "${BACKUP_DIR}/hooks/hooks" "hooks/"

# 10. Logs
log "── Logs ──"
backup_item "${HERMES_HOME}/logs" "${BACKUP_DIR}/logs/hermes_logs" "hermes logs"

# 11. Cache files (config/model caches)
log "── Cache/Config Files ──"
backup_item "${HERMES_HOME}/.skills_prompt_snapshot.json" "${BACKUP_DIR}/cache_files/skills_prompt_snapshot.json" ".skills_prompt_snapshot.json"
backup_item "${HERMES_HOME}/provider_models_cache.json" "${BACKUP_DIR}/cache_files/provider_models_cache.json" "provider_models_cache.json"
backup_item "${HERMES_HOME}/ollama_cloud_models_cache.json" "${BACKUP_DIR}/cache_files/ollama_cloud_models_cache.json" "ollama_cloud_models_cache.json"

# 12. Other metadata
log "── Other Metadata ──"
backup_item "${HERMES_HOME}/.initialized" "${BACKUP_DIR}/other/.initialized" ".initialized"
backup_item "${HERMES_HOME}/.update_check" "${BACKUP_DIR}/other/.update_check" ".update_check"
backup_item "${HERMES_HOME}/install_id" "${BACKUP_DIR}/other/install_id" "install_id"
backup_item "${HERMES_HOME}/models_dev_cache.json" "${BACKUP_DIR}/other/models_dev_cache.json" "models_dev_cache.json"
backup_item "${HERMES_HOME}/gateway-starts.log" "${BACKUP_DIR}/other/gateway-starts.log" "gateway-starts.log"

# ── Create Manifest ──────────────────────────────────────────────────────
log "Creating manifest..."

# Count backed up files
FILE_COUNT=$(wc -l < "${BACKUP_DIR}/.file_list.tmp" 2>/dev/null || echo "0")
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)

# Build manifest JSON
python3 -c "
import json, os, sys

backup_dir = '${BACKUP_DIR}'
timestamp = '${TIMESTAMP}'

# Read file list
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
    'hermes_version': '0.21.0',
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

# Clean up temp file
rm -f "${BACKUP_DIR}/.file_list.tmp"

# ── Create tarball for space efficiency ──────────────────────────────────
log "Creating compressed archive..."
cd "${BACKUP_BASE}"
tar -czf "${BACKUP_BASE}/${TIMESTAMP}.tar.gz" "${TIMESTAMP}/" 2>/dev/null || true
ARCHIVE_SIZE=$(du -sh "${BACKUP_BASE}/${TIMESTAMP}.tar.gz" 2>/dev/null | cut -f1)
log "Archive created: ${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})"

# Update latest symlink
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

# Configure git if needed
git config user.name "${GIT_USER}" 2>/dev/null || true
git config user.email "${GIT_EMAIL}" 2>/dev/null || true

# Ensure we're on main branch
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
git checkout "${DEFAULT_BRANCH}" 2>/dev/null || git checkout -b "${DEFAULT_BRANCH}" 2>/dev/null || true

# Stage all changes
git add -A

# Check if there are changes
if git diff --cached --quiet 2>/dev/null; then
    log "  No changes to push."
    PUSH_STATUS="no_changes"
else
    git commit -m "🔄 Auto-backup: ${TIMESTAMP}

Backup ID: ${TIMESTAMP}
Files: ${FILE_COUNT}
Size: ${TOTAL_SIZE}
Archive: ${ARCHIVE_SIZE}
Triggered by: automated backup script
" 2>&1 | tee -a "${BACKUP_LOG}"
    
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null)
    log "  Commit: ${COMMIT_HASH}"
    
    # Push
    if git push origin "${DEFAULT_BRANCH}" 2>&1 | tee -a "${BACKUP_LOG}"; then
        log "  ✓ Push successful!"
        PUSH_STATUS="success"
    else
        log "  ✗ Push failed!"
        PUSH_STATUS="failed"
    fi
fi

# ── Final Log Entry ─────────────────────────────────────────────────────
log "═══════════════════════════════════════════════════════════════"
log "  Backup Complete: ${TIMESTAMP}"
log "  Push Status: ${PUSH_STATUS}"
log "  Commit: ${COMMIT_HASH:-N/A}"
log "═══════════════════════════════════════════════════════════════"

# ── Backup Log rotation (keep last 50 logs) ─────────────────────────────
ls -t "${LOG_DIR}"/backup_*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true

echo ""
echo "BACKUP_RESULT: ${TIMESTAMP}|${FILE_COUNT}|${TOTAL_SIZE}|${ARCHIVE_SIZE}|${PUSH_STATUS}|${COMMIT_HASH:-N/A}"
