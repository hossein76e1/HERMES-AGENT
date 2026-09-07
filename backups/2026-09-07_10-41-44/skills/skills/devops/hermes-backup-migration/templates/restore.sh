#!/usr/bin/env bash
# =============================================================================
# Hermes Agent Restore Script
# Restores Hermes state from GitHub backup repository to a fresh VPS
# =============================================================================
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
BACKUP_REPO="${BACKUP_REPO:-/data/hermes-backup-repo}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/hossein76e1/HERMES-AGENT.git}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
GIT_USER="${GIT_USER:-hossein76e1}"
GIT_EMAIL="${GIT_EMAIL:-hossein76e1@users.noreply.github.com}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    local level="$1"
    shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    case "$level" in
        INFO)  echo -e "${BLUE}$msg${NC}" ;;
        OK)    echo -e "${GREEN}$msg${NC}" ;;
        WARN)  echo -e "${YELLOW}$msg${NC}" ;;
        ERROR) echo -e "${RED}$msg${NC}" ;;
    esac
}

# ── Step 1: Clone backup repo ──────────────────────────────────────────────
clone_repo() {
    log INFO "Cloning backup repository..."
    if [ -n "$GITHUB_TOKEN" ]; then
        REPO_URL="https://${GITHUB_TOKEN}@${GITHUB_REPO#https://}"
    else
        REPO_URL="$GITHUB_REPO"
    fi

    rm -rf "$BACKUP_REPO"
    git clone "$REPO_URL" "$BACKUP_REPO" 2>&1 | while read line; do log INFO "  $line"; done
    log OK "Repository cloned to $BACKUP_REPO"
}

# ── Step 2: Find latest backup ─────────────────────────────────────────────
find_latest_backup() {
    log INFO "Finding latest backup..."
    LATEST_DIR=$(readlink -f "$BACKUP_REPO/backups/latest" 2>/dev/null || true)
    if [ -z "$LATEST_DIR" ] || [ ! -d "$LATEST_DIR" ]; then
        # Fallback: find most recent backup directory
        LATEST_DIR=$(ls -1dt "$BACKUP_REPO/backups"/*/ 2>/dev/null | head -1 | sed 's/\/$//')
    fi

    if [ -z "$LATEST_DIR" ] || [ ! -d "$LATEST_DIR" ]; then
        log ERROR "No backup found in $BACKUP_REPO/backups/"
        exit 1
    fi

    log OK "Latest backup: $LATEST_DIR"
    echo "$LATEST_DIR"
}

# ── Step 3: Restore files ──────────────────────────────────────────────────
restore_files() {
    local backup_dir="$1"
    log INFO "Restoring files to $HERMES_HOME..."

    mkdir -p "$HERMES_HOME"/{config,memories,sessions,cron,skills,platforms,state,runtime,hooks,logs,databases,cache_files,other}

    # Tier 1: Critical files (must restore)
    log INFO "Restoring Tier 1 (Critical)..."
    for item in config.yaml SOUL.md auth.json channel_directory.json gateway_state.json; do
        if [ -f "$backup_dir/config/$item" ]; then
            cp -a "$backup_dir/config/$item" "$HERMES_HOME/$item"
            log OK "  Restored: $item"
        fi
    done

    # .env - restore from .env.example and warn
    if [ -f "$backup_dir/config/.env.example" ]; then
        cp -a "$backup_dir/config/.env.example" "$HERMES_HOME/.env"
        log WARN "  Restored .env from .env.example — YOU MUST EDIT IT WITH REAL VALUES"
    elif [ -f "$backup_dir/config/.env" ]; then
        cp -a "$backup_dir/config/.env" "$HERMES_HOME/.env"
        log WARN "  Restored .env — VERIFY ALL TOKENS ARE VALID"
    fi

    # Directories
    for dir in memories sessions skills platforms state runtime hooks logs databases cache_files other cron; do
        if [ -d "$backup_dir/$dir" ]; then
            # Special handling for nested structure
            if [ -d "$backup_dir/$dir/$dir" ]; then
                rsync -a "$backup_dir/$dir/$dir/" "$HERMES_HOME/$dir/"
            else
                rsync -a "$backup_dir/$dir/" "$HERMES_HOME/$dir/"
            fi
            log OK "  Restored directory: $dir/"
        fi
    done

    # Cron jobs.json
    if [ -f "$backup_dir/cron/jobs.json" ]; then
        cp -a "$backup_dir/cron/jobs.json" "$HERMES_HOME/cron/jobs.json"
        log OK "  Restored: cron/jobs.json"
    fi
    if [ -f "$backup_dir/cron/executions.db" ]; then
        cp -a "$backup_dir/cron/executions.db" "$HERMES_HOME/cron/executions.db"
        log OK "  Restored: cron/executions.db"
    fi
}

# ── Step 4: Handle sensitive files ─────────────────────────────────────────
handle_secrets() {
    log INFO "Handling sensitive files..."

    # state.db - not in GitHub backup, must be provided manually
    if [ ! -f "$HERMES_HOME/state.db" ]; then
        log WARN "  state.db NOT restored (excluded from GitHub for security)"
        log WARN "  → You must copy state.db manually from a local backup"
    else
        log OK "  state.db exists"
    fi

    # kanban.db
    if [ ! -f "$HERMES_HOME/kanban.db" ]; then
        log WARN "  kanban.db NOT restored (excluded from GitHub)"
        log WARN "  → Copy manually if needed"
    else
        log OK "  kanban.db exists"
    fi

    # auth.json - not in GitHub backup
    if [ ! -f "$HERMES_HOME/auth.json" ]; then
        log WARN "  auth.json NOT restored (excluded from GitHub)"
        log WARN "  → Copy manually from local backup"
    else
        log OK "  auth.json exists"
    fi

    # gateway_state.json
    if [ ! -f "$HERMES_HOME/gateway_state.json" ]; then
        log WARN "  gateway_state.json NOT restored (excluded from GitHub)"
    fi
}

# ── Step 5: Verify bot tokens ──────────────────────────────────────────────
verify_bot_tokens() {
    log INFO "Checking bot tokens in .env..."
    if [ -f "$HERMES_HOME/.env" ]; then
        grep -E "_TOKEN=" "$HERMES_HOME/.env" | while read line; do
            var=$(echo "$line" | cut -d= -f1)
            val=$(echo "$line" | cut -d= -f2-)
            if [[ "$val" == "***REDACTED***" ]] || [[ -z "$val" ]] || [[ "$val" == "your_token_here" ]]; then
                log WARN "  $var = [NEEDS REAL TOKEN]"
            else
                log OK "  $var = [SET]"
            fi
        done
    else
        log ERROR "  .env not found!"
    fi
}

# ── Step 6: Copy backup script for future backups ──────────────────────────
copy_backup_script() {
    log INFO "Installing backup script for future runs..."
    mkdir -p "$HERMES_HOME/scripts"
    if [ -f "$BACKUP_REPO/templates/backup.sh" ]; then
        cp -a "$BACKUP_REPO/templates/backup.sh" "$HERMES_HOME/scripts/backup.sh"
        chmod +x "$HERMES_HOME/scripts/backup.sh"
        log OK "  backup.sh installed to $HERMES_HOME/scripts/"
    elif [ -f "$HERMES_HOME/scripts/backup.sh" ]; then
        log OK "  backup.sh already exists"
    else
        log WARN "  No backup.sh template found — you'll need to add it manually"
    fi
}

# ── Step 7: Verify restore ─────────────────────────────────────────────────
verify_restore() {
    log INFO "Verifying restore..."
    local issues=0

    for file in config.yaml SOUL.md; do
        if [ ! -f "$HERMES_HOME/$file" ]; then
            log ERROR "  Missing critical file: $file"
            issues=$((issues + 1))
        fi
    done

    for dir in memories sessions skills cron; do
        if [ ! -d "$HERMES_HOME/$dir" ] || [ -z "$(ls -A "$HERMES_HOME/$dir" 2>/dev/null)" ]; then
            log WARN "  Directory empty or missing: $dir/"
        fi
    done

    if [ ! -f "$HERMES_HOME/.env" ]; then
        log ERROR "  .env missing"
        issues=$((issues + 1))
    fi

    if [ $issues -eq 0 ]; then
        log OK "All critical files present"
    else
        log ERROR "$issues critical issues found"
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────
main() {
    echo ""
    log INFO "═══════════════════════════════════════════════════════════════"
    log INFO "  Hermes Agent Restore — $(date)"
    log INFO "═══════════════════════════════════════════════════════════════"
    echo ""

    clone_repo
    LATEST_BACKUP=$(find_latest_backup)
    restore_files "$LATEST_BACKUP"
    handle_secrets
    verify_bot_tokens
    copy_backup_script
    verify_restore

    echo ""
    log INFO "═══════════════════════════════════════════════════════════════"
    log INFO "  Restore Complete"
    log INFO "═══════════════════════════════════════════════════════════════"
    echo ""
    log WARN "NEXT STEPS:"
    log WARN "  1. Edit $HERMES_HOME/.env with ALL real tokens"
    log WARN "  2. Copy state.db, auth.json, gateway_state.json from local backup"
    log WARN "  3. Verify no other instance is polling the same bot tokens (409 Conflict)"
    log WARN "  4. Start Hermes: hermes start"
    echo ""
}

# Allow sourcing for testing
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
