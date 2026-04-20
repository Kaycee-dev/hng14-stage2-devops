#!/usr/bin/env bash
# Full-stack integration test: bring stack up, submit a job through the frontend,
# poll until completion, assert final status, tear down regardless of outcome.
set -euo pipefail

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"
TIMEOUT_SECONDS="${INTEGRATION_TIMEOUT_SECONDS:-90}"

cleanup() {
  local status=$?
  echo ""
  echo "=== Integration teardown (exit=${status}) ==="
  docker compose ps || true
  docker compose logs --tail=200 || true
  docker compose down --volumes --remove-orphans || true
  exit "${status}"
}
trap cleanup EXIT INT TERM

echo "=== Bringing full stack up ==="
docker compose up -d --wait --wait-timeout "${TIMEOUT_SECONDS}"

echo "=== docker compose ps ==="
docker compose ps

echo "=== Waiting for frontend /health ==="
deadline=$(( $(date +%s) + TIMEOUT_SECONDS ))
while :; do
  if curl --fail --silent --show-error "${FRONTEND_URL}/health" > /dev/null; then
    echo "frontend healthy"
    break
  fi
  if (( $(date +%s) >= deadline )); then
    echo "ERROR: frontend did not become healthy in ${TIMEOUT_SECONDS}s" >&2
    exit 1
  fi
  sleep 2
done

echo "=== Submitting a job through the frontend ==="
submit_body=$(curl --fail --silent --show-error -X POST "${FRONTEND_URL}/submit")
echo "submit response: ${submit_body}"

job_id=$(printf '%s' "${submit_body}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["job_id"])')
if [[ -z "${job_id}" ]]; then
  echo "ERROR: did not receive a job_id from /submit" >&2
  exit 1
fi
echo "job_id=${job_id}"

echo "=== Polling /status/${job_id} until completed ==="
status="unknown"
deadline=$(( $(date +%s) + TIMEOUT_SECONDS ))
while :; do
  poll_body=$(curl --fail --silent --show-error "${FRONTEND_URL}/status/${job_id}")
  status=$(printf '%s' "${poll_body}" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))')
  echo "poll: ${poll_body}"
  if [[ "${status}" == "completed" ]]; then
    echo "job reached completed state"
    break
  fi
  if (( $(date +%s) >= deadline )); then
    echo "ERROR: job ${job_id} did not reach completed in ${TIMEOUT_SECONDS}s (last status=${status})" >&2
    exit 1
  fi
  sleep 2
done

echo "=== Integration test PASS ==="
