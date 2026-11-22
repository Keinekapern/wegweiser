#!/usr/bin/env bash
# Rebuild the Wegweiser image with the newest base image (security updates of Debian
# and Python) and restart it. Only touches this project's container and its own old
# images (label org.wegweiser.app, see Dockerfile), never other images. E.g. weekly:
#   30 4 * * 1  /path/to/wegweiser/rebuild.sh >> /path/to/wegweiser/rebuild.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"

log() { echo "$(date '+%F %T') $*"; }

log "Build (with --pull)"
docker compose build --pull --quiet wegweiser
docker compose up -d wegweiser
# old Wegweiser images that no container uses any more (label filter: only ours)
removed=$(docker image prune -f --filter "label=org.wegweiser.app=wegweiser" | tail -1)
log "Cleanup: ${removed:-nothing to remove}"
for _ in $(seq 1 30); do
  status=$(docker inspect -f '{{.State.Health.Status}}' wegweiser 2>/dev/null || echo "?")
  [ "$status" = "healthy" ] && { log "Running, healthy"; exit 0; }
  sleep 5
done
log "WARNING: container not healthy after rebuild (docker logs wegweiser)"
exit 1
