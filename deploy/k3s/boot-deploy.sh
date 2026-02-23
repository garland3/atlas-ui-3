#!/usr/bin/env bash
# boot-deploy.sh -- Waits for K3s to be ready, then deploys ATLAS.
# Called by the atlas-deploy.service systemd unit on boot.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_SCRIPT="$SCRIPT_DIR/run.sh"
LOG_PREFIX="[atlas-boot-deploy]"
MAX_WAIT=120

log() {
    echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# ---------------------------------------------------------------------------
# Wait for K3s API to be responsive
# ---------------------------------------------------------------------------
log "Waiting for K3s API server (up to ${MAX_WAIT}s)..."
elapsed=0
while ! sudo k3s kubectl get nodes &>/dev/null; do
    if [ "$elapsed" -ge "$MAX_WAIT" ]; then
        log "ERROR: K3s API not ready after ${MAX_WAIT}s. Aborting."
        exit 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done
log "K3s API ready after ${elapsed}s."

# ---------------------------------------------------------------------------
# Deploy ATLAS
# ---------------------------------------------------------------------------
log "Deploying ATLAS..."
bash "$DEPLOY_SCRIPT" up

log "Boot deploy complete."
