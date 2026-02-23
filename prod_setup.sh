#!/usr/bin/env bash
# prod_setup.sh -- Auto-update script for ATLAS K3s deployment
# Called by cron every 15 minutes. Pulls latest from origin/main,
# rebuilds and redeploys only when there are new changes.
#
# This is an example for personal/home server use.
# Review and adjust BRANCH, REMOTE, and DEPLOY_SCRIPT for your setup.
#
# Usage:
#   prod_setup.sh           # Normal: only rebuild if git has new changes
#   prod_setup.sh --force   # Force rebuild and redeploy even if up to date
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="$PROJECT_ROOT/deploy/k3s/run.sh"
LOG_PREFIX="[atlas-auto-update]"
BRANCH="main"
REMOTE="origin"
LOCK_FILE="$PROJECT_ROOT/.auto-update.lock"
FORCE=false

if [ "${1:-}" = "--force" ] || [ "${1:-}" = "-f" ]; then
    FORCE=true
fi

log() {
    echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# ---------------------------------------------------------------------------
# Lock to prevent overlapping runs (build can take several minutes)
# ---------------------------------------------------------------------------
if [ -f "$LOCK_FILE" ]; then
    lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || true)
    if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
        log "Previous update still running (PID $lock_pid). Skipping."
        exit 0
    else
        log "Stale lock file found (PID $lock_pid gone). Removing."
        rm -f "$LOCK_FILE"
    fi
fi

cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT
echo $$ > "$LOCK_FILE"

# ---------------------------------------------------------------------------
# Fetch and check for changes
# ---------------------------------------------------------------------------
cd "$PROJECT_ROOT"

log "Fetching $REMOTE/$BRANCH..."
git fetch "$REMOTE" "$BRANCH" 2>&1

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ] && [ "$FORCE" = false ]; then
    log "Already up to date at $LOCAL_SHA. Nothing to do."
    exit 0
fi

if [ "$FORCE" = true ] && [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    log "Force rebuild requested (already at $LOCAL_SHA)."
else
    log "New changes detected: $LOCAL_SHA -> $REMOTE_SHA"
fi

# ---------------------------------------------------------------------------
# Pull changes (skip if forcing with no new commits)
# ---------------------------------------------------------------------------
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    log "Switching to $BRANCH and pulling..."
    git checkout "$BRANCH" 2>&1
    git pull "$REMOTE" "$BRANCH" 2>&1
fi

NEW_SHA=$(git rev-parse HEAD)
log "Updated to $NEW_SHA"

# ---------------------------------------------------------------------------
# Rebuild and redeploy
# ---------------------------------------------------------------------------
log "Rebuilding container images..."
bash "$DEPLOY_SCRIPT" build 2>&1

log "Redeploying to K3s..."
bash "$DEPLOY_SCRIPT" up 2>&1

log "Auto-update complete. Deployed $NEW_SHA"
