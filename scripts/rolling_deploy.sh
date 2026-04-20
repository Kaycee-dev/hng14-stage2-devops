#!/usr/bin/env bash
# Scripted rolling update.
# For each service, start a new candidate, wait up to DEPLOY_HEALTH_TIMEOUT_SECONDS
# for it to become healthy, then retire the old container. If health fails, abort
# and leave the old container running.
#
# Usage: ./scripts/rolling_deploy.sh
#
# Required environment:
#   IMAGE_TAG                        - candidate image tag (typically ${GITHUB_SHA})
#   REGISTRY_HOST, REGISTRY_PORT     - local registry
#   IMAGE_NAMESPACE                  - image namespace
# Optional:
#   DEPLOY_HEALTH_TIMEOUT_SECONDS    - default 60
#   DEPLOY_NETWORK_NAME              - default stage2-internal
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
REGISTRY_HOST="${REGISTRY_HOST:-localhost}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-hng14-stage2-devops}"
DEPLOY_HEALTH_TIMEOUT_SECONDS="${DEPLOY_HEALTH_TIMEOUT_SECONDS:-60}"
DEPLOY_NETWORK_NAME="${DEPLOY_NETWORK_NAME:-stage2-internal}"

SERVICES_ORDER=(api worker frontend)

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

wait_for_healthy() {
  local name="$1"
  local deadline=$(( $(date +%s) + DEPLOY_HEALTH_TIMEOUT_SECONDS ))
  while (( $(date +%s) < deadline )); do
    local status
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}nohealth{{end}}' "${name}" 2>/dev/null || echo "missing")
    case "${status}" in
      healthy) return 0 ;;
      missing) log "candidate ${name} disappeared"; return 1 ;;
      *) log "candidate ${name} status=${status}, waiting..." ;;
    esac
    sleep 2
  done
  return 1
}

deploy_service() {
  local service="$1"
  local image="${REGISTRY_HOST}:${REGISTRY_PORT}/${IMAGE_NAMESPACE}/${service}:${IMAGE_TAG}"
  local current="${service}"
  local candidate="${service}_candidate"

  log "pulling ${image}"
  docker pull "${image}"

  log "removing any stale candidate ${candidate}"
  docker rm -f "${candidate}" >/dev/null 2>&1 || true

  log "starting candidate ${candidate} from ${image}"
  docker run -d \
    --name "${candidate}" \
    --network "${DEPLOY_NETWORK_NAME}" \
    --env-file .env \
    --restart unless-stopped \
    "${image}"

  if wait_for_healthy "${candidate}"; then
    log "candidate ${candidate} healthy, retiring old ${current}"
    if docker ps --format '{{.Names}}' | grep -Fxq "${current}"; then
      docker stop "${current}" || true
      docker rm "${current}" || true
    fi
    docker rename "${candidate}" "${current}"
    log "${service} promoted"
    return 0
  fi

  log "ABORT: candidate ${candidate} did not become healthy in ${DEPLOY_HEALTH_TIMEOUT_SECONDS}s"
  log "keeping old ${current} running"
  docker logs --tail 100 "${candidate}" || true
  docker rm -f "${candidate}" || true
  return 1
}

for svc in "${SERVICES_ORDER[@]}"; do
  if ! deploy_service "${svc}"; then
    log "rolling update failed at service=${svc}"
    exit 1
  fi
done

log "rolling update complete"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
