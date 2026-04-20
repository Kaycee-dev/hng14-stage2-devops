import os

import redis as redis_pkg


def test_health_returns_200_when_redis_reachable(client, fake_redis):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["redis"] == "reachable"


def test_health_returns_503_when_redis_unreachable(monkeypatch, client):
    import main

    class BrokenRedis:
        def ping(self):
            raise redis_pkg.RedisError("connection refused")

    monkeypatch.setattr(main, "r", BrokenRedis())
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["redis"] == "unreachable"


def test_create_job_returns_job_id_and_queues_in_redis(client, fake_redis):
    queue = os.environ["JOB_QUEUE_NAME"]
    resp = client.post("/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"

    job_id = body["job_id"]
    assert fake_redis.llen(queue) == 1
    assert fake_redis.hget(f"job:{job_id}", "status") == b"queued"


def test_get_job_returns_status_after_worker_marks_it_complete(client, fake_redis):
    resp = client.post("/jobs")
    job_id = resp.json()["job_id"]

    fake_redis.hset(f"job:{job_id}", "status", "completed")

    status_resp = client.get(f"/jobs/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"job_id": job_id, "status": "completed"}


def test_get_job_returns_404_when_job_missing(client):
    resp = client.get("/jobs/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "job_not_found"
