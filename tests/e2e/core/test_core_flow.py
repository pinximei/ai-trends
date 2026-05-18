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


def test_public_articles_feed_heat_shape(client):
    r = client.get("/api/public/v1/articles/feed?feed=news&paginate_by=heat&published_within_days=3650&heat_offset=0&heat_page_size=20")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    data = body.get("data") or {}
    assert data.get("paginate_by") == "heat"
    assert data.get("page_size") == 20
    assert data.get("offset") == 0
    assert data.get("heat_max") == 100
    assert "has_more" in data
    assert isinstance(data.get("items"), list)
    assert len(data["items"]) <= 20
    assert isinstance(data.get("total"), int)
