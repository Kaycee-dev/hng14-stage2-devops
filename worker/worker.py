import os
import signal
import sys
import time
from pathlib import Path

import redis


REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "jobs")
POLL_TIMEOUT = int(os.getenv("WORKER_POLL_TIMEOUT_SECONDS", "5"))
SIMULATED_DELAY = int(os.getenv("WORKER_SIMULATED_DELAY_SECONDS", "2"))
HEALTH_FILE = Path(os.getenv("WORKER_HEALTH_FILE", "/tmp/worker_alive"))
HEALTH_STALE_SECONDS = int(os.getenv("WORKER_HEALTH_STALE_SECONDS", "15"))


_shutdown = False


def _touch_health_file() -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(str(time.time()))


def _handle_signal(signum, _frame):
    global _shutdown
    print(f"[worker] received signal {signum}, shutting down after current job", flush=True)
    _shutdown = True


def _build_redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        socket_connect_timeout=2,
    )


def process_job(client: redis.Redis, job_id: str) -> None:
    print(f"[worker] processing job {job_id}", flush=True)
    client.hset(f"job:{job_id}", "status", "processing")
    time.sleep(SIMULATED_DELAY)
    client.hset(f"job:{job_id}", "status", "completed")
    print(f"[worker] done: {job_id}", flush=True)


def run() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    client = _build_redis_client()
    print(
        f"[worker] starting queue={JOB_QUEUE_NAME} redis={REDIS_HOST}:{REDIS_PORT}",
        flush=True,
    )
    while not _shutdown:
        try:
            _touch_health_file()
            job = client.brpop(JOB_QUEUE_NAME, timeout=POLL_TIMEOUT)
        except redis.RedisError as exc:
            print(f"[worker] redis error: {exc}", flush=True)
            time.sleep(1)
            continue
        if job is None:
            continue
        _, job_id = job
        try:
            process_job(client, job_id.decode())
        except redis.RedisError as exc:
            print(f"[worker] failed to update job state: {exc}", flush=True)
            time.sleep(1)
    print("[worker] exited cleanly", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
