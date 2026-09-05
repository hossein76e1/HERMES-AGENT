#!/usr/bin/env bash
# =============================================================================
# Hermes Projects Backup Script
# Backs up all project code from /data/workspace to GitHub
# =============================================================================
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
WORKSPACE="/data/workspace"
BACKUP_REPO="/data/hermes-backup-repo"
PROJECTS_BACKUP_DIR="${BACKUP_REPO}/projects-backup"
LOG_DIR="${BACKUP_REPO}/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="${PROJECTS_BACKUP_DIR}/${TIMESTAMP}"
BACKUP_LOG="${LOG_DIR}/projects_backup_${TIMESTAMP}.log"
LATEST_SYMLINK="${PROJECTS_BACKUP_DIR}/latest"

# GitHub settings — UPDATE THESE
GITHUB_REPO="https://github.com/hossein76e1/HERMES-AGENT.git"
GITHUB_TOKEN="YOUR_TOKEN_HERE"
GIT_USER="hossein76e1"
GIT_EMAIL="hossein76e1@users.noreply.github.com"

# Projects to backup (relative to WORKSPACE)
PROJECTS=(
    "projects"
    "order-system"
    "smart-scraper"
)

# Lock file
LOCK_FILE="${BACKUP_REPO}/.projects_backup.lock"
LOCK_FD=201

# Retention
MAX_BACKUPS=10

# ── Logging ───────────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
mkdir -p "${PROJECTS_BACKUP_DIR}"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "${BACKUP_LOG}"
}

# ── Acquire lock ───────────────────────────────────────────────────────────
acquire_lock() {
    eval "exec ${LOCK_FD}>${LOCK_FILE}"
    if ! flock -n ${LOCK_FD}; then
        log "⏳ Another projects backup is running, exiting"
        exit 0
    fi
    echo $$ >&${LOCK_FD}
}

# ── Cleanup old backups ────────────────────────────────────────────────────
cleanup_old_backups() {
    log "Cleaning up old project backups (keeping last ${MAX_BACKUPS})..."
    cd "${PROJECTS_BACKUP_DIR}" || return 0
    local dirs=()
    while IFS= read -r -d '' dir; do
        dirs+=("$dir")
    done < <(ls -1dt */ 2>/dev/null | grep -v '^latest$' | tr '\n' '\0')
    
    local count=0
    for dir in "${dirs[@]}"; do
        count=$((count + 1))
        if [ $count -gt $MAX_BACKUPS ]; then
            log "  Removing old backup: ${dir%/}"
            rm -rf "${dir%/}"
            rm -f "${PROJECTS_BACKUP_DIR}/${dir%/}.tar.gz"
        fi
    done
    ls -t "${LOG_DIR}"/projects_backup_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true
}

# ── Backup function ────────────────────────────────────────────────────────
backup_project() {
    local project_name="$1"
    local src="${WORKSPACE}/${project_name}"
    local dest="${BACKUP_DIR}/${project_name}"

    if [ ! -e "${src}" ]; then
        log "  ⊘ ${project_name} — not found, skipping"
        return 0
    fi

    mkdir -p "$(dirname "${dest}")"

    # Exclude patterns
    rsync -a \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.git/' \
        --exclude='.venv/' \
        --exclude='venv/' \
        --exclude='node_modules/' \
        --exclude='*.log' \
        --exclude='*.sqlite' \
        --exclude='*.db' \
        --exclude='.DS_Store' \
        --exclude='*.tmp' \
        --exclude='*.temp' \
        "${src}/" "${dest}/"

    local size=$(du -sb "${dest}" 2>/dev/null | cut -f1)
    log "  ✓ ${project_name} (${size} bytes)"
    echo "${project_name}|||${src}|||${dest}|||${size}" >> "${BACKUP_DIR}/.file_list.tmp"
}

# ── Sanitize sensitive files ───────────────────────────────────────────────
sanitize_backup() {
    log "Sanitizing sensitive files..."

    # Find and redact .env files
    find "${BACKUP_DIR}" -name ".env" -type f | while read env_file; do
        if [ -f "${env_file}" ]; then
            sed -i 's/^\([^=]*\)=.*/\1=***REDACTED***/' "${env_file}" 2>/dev/null || true
            log "  Sanitized: ${env_file}"
        fi
    done

    # Remove any .env files entirely for GitHub (keep .env.example)
    find "${BACKUP_DIR}" -name ".env" -type f -delete 2>/dev/null || true
}

# ── Create manifest ────────────────────────────────────────────────────────
create_manifest() {
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
                        'project': parts[0],
                        'source': parts[1],
                        'backup_path': os.path.relpath(parts[2], backup_dir),
                        'size_bytes': int(parts[3]) if len(parts) > 3 else 0
                    })

manifest = {
    'backup_timestamp': timestamp.replace('_', ' ').replace('-', '/', 2),
    'backup_id': timestamp,
    'total_projects': len(set(f['project'] for f in files)),
    'total_files': len(files),
    'total_size': '${TOTAL_SIZE}',
    'backup_root': backup_dir,
    'projects': list(set(f['project'] for f in files)),
    'files': files
}

with open(os.path.join(backup_dir, 'manifest.json'), 'w') as f:
    json.dump(manifest, f, indent=2)

print(f'Manifest created: {len(files)} items cataloged')
" 2>&1 | tee -a "${BACKUP_LOG}"

    rm -f "${BACKUP_DIR}/.file_list.tmp"
}

# ── Create tarball ─────────────────────────────────────────────────────────
create_tarball() {
    log "Creating compressed archive..."
    cd "${PROJECTS_BACKUP_DIR}"
    tar -czf "${PROJECTS_BACKUP_DIR}/${TIMESTAMP}.tar.gz" "${TIMESTAMP}/" 2>/dev/null || true
    ARCHIVE_SIZE=$(du -sh "${PROJECTS_BACKUP_DIR}/${TIMESTAMP}.tar.gz" 2>/dev/null | cut -f1)
    log "Archive created: ${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})"

    rm -f "${LATEST_SYMLINK}"
    ln -s "${TIMESTAMP}" "${LATEST_SYMLINK}"
}

# ── Push to GitHub ─────────────────────────────────────────────────────────
push_to_github() {
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
        git commit -m "📦 Projects backup: ${TIMESTAMP}\n\nBackup ID: ${TIMESTAMP}\nProjects: ${#PROJECTS[@]}\nFiles: ${FILE_COUNT}\nSize: ${TOTAL_SIZE}\nArchive: ${ARCHIVE_SIZE}\nTriggered by: automated projects backup script\n" 2>&1 | tee -a "${BACKUP_LOG}"

        COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null)
        log "  Commit: ${COMMIT_HASH}"

        # Use credential helper to avoid token in URL
        cat > /tmp/projects_push_helper.sh << EOF
#!/bin/bash
cd "${BACKUP_REPO}"
git config credential.helper '!f() { echo "username=${GIT_USER}"; echo "password=${GITHUB_TOKEN}"; }; f'
GIT_TERMINAL_PROMPT=0 git push origin "${DEFAULT_BRANCH}" 2>&1
EOF
        chmod +x /tmp/projects_push_helper.sh

        if bash /tmp/projects_push_helper.sh 2>&1 | tee -a "${BACKUP_LOG}"; then
            log "  ✓ Push successful!"
            PUSH_STATUS="success"
        else
            log "  ✗ Push failed!"
            PUSH_STATUS="failed"
        fi
        rm -f /tmp/projects_push_helper.sh
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────
main() {
    echo ""
    log "═══════════════════════════════════════════════════════════════"
    log "  Hermes Projects Backup — ${TIMESTAMP}"
    log "═══════════════════════════════════════════════════════════════"
    echo ""

    acquire_lock
    cleanup_old_backups

    mkdir -p "${BACKUP_DIR}"
    > "${BACKUP_DIR}/.file_list.tmp"

    log "Backing up projects..."
    for project in "${PROJECTS[@]}"; do
        backup_project "${project}"
    done

    sanitize_backup
    create_manifest
    create_tarball

    log "── Backup Summary ──"
    log "  Backup ID: ${TIMESTAMP}"
    log "  Projects: ${#PROJECTS[@]}"
    log "  Files backed up: ${FILE_COUNT}"
    log "  Total size: ${TOTAL_SIZE}"
    log "  Archive: ${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})"

    push_to_github

    log "═══════════════════════════════════════════════════════════════"
    log "  Projects Backup Complete: ${TIMESTAMP}"
    log "  Push Status: ${PUSH_STATUS}"
    log "  Commit: ${COMMIT_HASH:-N/A}"
    log "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "PROJECTS_BACKUP_RESULT: ${TIMESTAMP}|${#PROJECTS[@]}|${FILE_COUNT}|${TOTAL_SIZE}|${ARCHIVE_SIZE}|${PUSH_STATUS}|${COMMIT_HASH:-N/A}"
}

# Allow sourcing for testing
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
