import os
import uuid

import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse


def _build_redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "0"))
    password = os.getenv("REDIS_PASSWORD") or None
    return redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


app = FastAPI(title="hng14-stage2-devops-api")
r = _build_redis_client()
JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "jobs")


@app.get("/health")
def health():
    try:
        if r.ping():
            return {"status": "ok", "redis": "reachable"}
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "redis": "no_pong"},
        )
    except redis.RedisError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "redis": "unreachable", "error": str(exc)},
        )


@app.post("/jobs")
def create_job():
    job_id = str(uuid.uuid4())
    try:
        pipe = r.pipeline()
        pipe.hset(f"job:{job_id}", mapping={"status": "queued"})
        pipe.lpush(JOB_QUEUE_NAME, job_id)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail=f"redis_error: {exc}")
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        status = r.hget(f"job:{job_id}", "status")
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail=f"redis_error: {exc}")
    if not status:
        raise HTTPException(status_code=404, detail="job_not_found")
    return {"job_id": job_id, "status": status.decode()}
