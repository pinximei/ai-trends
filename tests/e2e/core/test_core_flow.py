import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_public_version_endpoint(client):
    resp = client.get("/api/public/v1/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("code") == 0
    data = body.get("data") or {}
    assert "release" in data
    assert isinstance(data["release"], str)
    assert len(data["release"]) >= 1


def test_api_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json().get("service") == "aitrends-api"
