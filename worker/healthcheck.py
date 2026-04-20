import os
import sys
import time
from pathlib import Path

import redis


def main() -> int:
    health_file = Path(os.getenv("WORKER_HEALTH_FILE", "/tmp/worker_alive"))
    stale_after = int(os.getenv("WORKER_HEALTH_STALE_SECONDS", "15"))

    if not health_file.exists():
        print("health_file_missing", file=sys.stderr)
        return 1

    try:
        last_beat = float(health_file.read_text().strip() or "0")
    except ValueError:
        print("health_file_unreadable", file=sys.stderr)
        return 1

    if (time.time() - last_beat) > stale_after:
        print("health_file_stale", file=sys.stderr)
        return 1

    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD") or None,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    try:
        if not client.ping():
            print("redis_no_pong", file=sys.stderr)
            return 1
    except redis.RedisError as exc:
        print(f"redis_unreachable: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
