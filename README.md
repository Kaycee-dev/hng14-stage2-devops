# HNG14 Stage 2 - Containerized Job Processing System

A three-service job-processing stack (frontend + API + worker) backed by Redis,
delivered as a production-quality Docker Compose stack with a strict CI/CD
pipeline on GitHub Actions. Built against the HNG14 Stage 2 DevOps brief.

---

## 1. Service map

| Service    | Source       | Host-exposed? | Tech             | Role |
| ---------- | ------------ | ------------- | ---------------- | ---- |
| `frontend` | `frontend/`  | yes (HTTP)    | Node 20, Express | Submits jobs, polls status, serves the dashboard HTML |
| `api`      | `api/`       | no            | Python 3.12, FastAPI | Creates job records in Redis, serves status |
| `worker`   | `worker/`    | no            | Python 3.12, `redis` | Consumes the queue, transitions `queued → processing → completed` |
| `redis`    | `redis:7.2-alpine` | **no** (internal only) | Redis | Shared queue and job-state store |

All inter-service traffic flows over the named Docker network `stage2-internal`.
Redis is never published to the host.

---

## 2. Prerequisites

- Git
- Docker Engine 24+ (or Docker Desktop) with the Compose v2 plugin (`docker compose ...`)
- A public GitHub fork of this repository (required by the task)

That is the full list. No cloud account, no self-hosted runner, no paid service.

---

## 3. Fresh local startup on a clean machine

```bash
# 1. Clone your fork
git clone https://github.com/Kaycee-dev/hng14-stage2-devops.git
cd hng14-stage2-devops

# 2. Materialize a local .env from the tracked placeholder template
cp .env.example .env
# Edit .env and set REDIS_PASSWORD to any non-empty value you like.
# Do NOT commit .env. It is .gitignored.

# 3. Bring the full stack up, gated on health
docker compose up --build -d

# 4. Confirm all four services are healthy
docker compose ps
```

On a healthy boot `docker compose ps` shows **four** services, all with a
`(healthy)` state:

```
NAME        IMAGE                                                   STATUS
redis       redis:7.2-alpine                                        Up (healthy)
api         localhost:5000/hng14-stage2-devops/api:latest           Up (healthy)
worker      localhost:5000/hng14-stage2-devops/worker:latest        Up (healthy)
frontend    localhost:5000/hng14-stage2-devops/frontend:latest      Up (healthy)
```

Open the dashboard at `http://localhost:3000/` and click **Submit New Job**.
The job should reach `completed` within a few seconds.

Tear down:

```bash
docker compose down --volumes --remove-orphans
```

---

## 4. End-to-end smoke test (what "working" looks like)

```bash
# The frontend is the only host-exposed application entrypoint.
curl -s http://127.0.0.1:3000/health

# Submit a job through the frontend.
JOB=$(curl -s -X POST http://127.0.0.1:3000/submit | python -c 'import json,sys;print(json.load(sys.stdin)["job_id"])')
echo "job_id=${JOB}"

# Poll until completed.
for _ in $(seq 1 30); do
  STATUS=$(curl -s http://127.0.0.1:3000/status/${JOB} | python -c 'import json,sys;print(json.load(sys.stdin)["status"])')
  echo "${STATUS}"
  [ "${STATUS}" = "completed" ] && break
  sleep 1
done
```

Expected healthy behavior:

- `GET /health` on the frontend → `200 {"status":"ok","api":"reachable"}`
- `POST /submit` → `200 {"job_id":"<uuid>","status":"queued"}`
- `GET /status/<id>` → eventually `200 {"job_id":"<uuid>","status":"completed"}`

---

## 5. Environment surface

Every service reads its config from environment variables; nothing is hardcoded
in any Compose file or image. The single source of truth for the variable names
is [`.env.example`](.env.example). Copy it to `.env` and fill real values
locally. Grouped variables:

- **Topology / Compose** — `COMPOSE_PROJECT_NAME`, `DEPLOY_NETWORK_NAME`, `DEPLOY_HEALTH_TIMEOUT_SECONDS`
- **Frontend** — `FRONTEND_HOST`, `FRONTEND_PORT`, `FRONTEND_API_BASE_URL`
- **API** — `API_HOST`, `API_PORT`, `JOB_QUEUE_NAME`
- **Redis** (shared by api and worker) — `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`
- **Worker** — `WORKER_POLL_TIMEOUT_SECONDS`, `WORKER_SIMULATED_DELAY_SECONDS`
- **Image publishing (CI + compose image tags)** — `REGISTRY_HOST`, `REGISTRY_PORT`, `IMAGE_NAMESPACE`, `IMAGE_TAG`
- **Deploy target (CI deploy only)** — `DEPLOY_SSH_HOST`, `DEPLOY_SSH_PORT`, `DEPLOY_SSH_USER`, `DEPLOY_APP_DIR`, `DEPLOY_SSH_PRIVATE_KEY`

Rules enforced by `.gitignore`:

- `.env` is **never** committed
- service-local `.env` files (e.g. `api/.env`) are **never** committed
- `.env.example` is the only env file ever tracked, and contains placeholders only

---

## 6. Container guarantees

Each service image satisfies every grading requirement:

- **Multi-stage builds** — dev/build toolchain is dropped from the runtime stage
  for `api` (pip builder → slim runtime) and `frontend` (node builder → slim
  runtime). `worker` uses a builder stage for dependency install so the runtime
  stage has no compilers.
- **Non-root user** — every runtime stage creates UID/GID `10001` and ends with
  `USER app`. No service runs as root.
- **Working HEALTHCHECK** — `api` curls `/health`, `frontend` runs
  `node /app/healthcheck.js`, `worker` runs `python /app/healthcheck.py` (which
  requires a fresh heartbeat file **and** a successful Redis `PING`).
- **No secrets in images** — `.dockerignore` files exclude `.env*` from every
  build context. Configuration is injected only at container start via
  environment variables.

---

## 7. CI/CD contract

GitHub Actions runs on `ubuntu-latest` in strict sequential order, gated via
`needs:` so a failure in any stage blocks everything after it:

```
lint → test → build → security-scan → integration-test → deploy
```

| Stage               | What it does |
| ------------------- | ------------ |
| **lint**            | `flake8` (Python), `eslint` (JavaScript), `hadolint` (all Dockerfiles). |
| **test**            | `pytest` with Redis mocked via `fakeredis`; coverage report (`coverage.xml` + HTML) uploaded as artifact `api-coverage`. |
| **build**           | Spins up a `registry:2` service container on `localhost:5000`, builds all three images with Buildx, pushes each with two tags: `${GITHUB_SHA}` and `latest`. Verifies tag presence via `/v2/.../tags/list`. Saves images to tarballs and uploads as `image-bundle` for downstream stages. |
| **security-scan**   | Loads images from `image-bundle`, runs Trivy against each with `severity=CRITICAL, exit-code=1`, uploads SARIF as artifact `trivy-sarif`. |
| **integration-test**| Loads images, materializes `.env`, runs `tests/integration/run_integration.sh` which brings the stack up health-gated, submits a job through the frontend, polls until `completed`, asserts status, and tears the stack down in a `trap` that runs on success **or** failure. |
| **deploy**          | Runs **only** on `push` to `main`. Starts an initial stack, then runs `scripts/rolling_deploy.sh` which replaces `api`, then `worker`, then `frontend`, waiting up to 60 seconds per candidate for health. If a candidate fails health, it is removed and the old container keeps running. |

Pipeline file: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## 8. Rolling deploy behavior

[`scripts/rolling_deploy.sh`](scripts/rolling_deploy.sh) implements the task's
rolling-update contract:

1. Pull the `${GITHUB_SHA}`-tagged candidate image for the service.
2. Start a new container named `<svc>_candidate` on the deployment network with
   the same `.env`.
3. Poll `docker inspect .State.Health.Status` for up to
   `DEPLOY_HEALTH_TIMEOUT_SECONDS` (default `60`).
4. **Only** when the candidate reports `healthy`, stop and remove the existing
   `<svc>` container and rename the candidate into its place.
5. If the candidate does not become healthy in time, remove the candidate and
   leave the old container running. The deploy job exits non-zero.

Order: `api → worker → frontend`. Redis is never in the rolling-update path.

---

## 9. What to read next

- [FIXES.md](FIXES.md) — every starter-repo defect with file and line numbers
- [docs/PLAN.md](docs/PLAN.md)
- [docs/GUARDRAILS.md](docs/GUARDRAILS.md)
- [docs/CONTRACTS.md](docs/CONTRACTS.md)
- [docs/devops-stage2-sprint/00_system_contract.md](docs/devops-stage2-sprint/00_system_contract.md)
- [docs/devops-stage2-delivery/00_runtime_and_topology_spec.md](docs/devops-stage2-delivery/00_runtime_and_topology_spec.md)
- [docs/devops-stage2-delivery/02_release_and_rollback_runbook.md](docs/devops-stage2-delivery/02_release_and_rollback_runbook.md)

---

## 10. Submission inputs

- GitHub username: `Kaycee-dev`
- Fork URL: `https://github.com/Kaycee-dev/hng14-stage2-devops`
