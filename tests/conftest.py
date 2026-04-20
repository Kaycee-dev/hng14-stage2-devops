import os
import sys
from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis()


@pytest.fixture
def client(monkeypatch, fake_redis):
    os.environ.setdefault("JOB_QUEUE_NAME", "jobs")
    import main

    monkeypatch.setattr(main, "r", fake_redis)
    return TestClient(main.app)
