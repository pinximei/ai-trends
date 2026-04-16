import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_dashboard_page_accessible(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json().get("service") == "aisoul-api"


def test_trend_to_evidence_flow(client):
    resp = client.get("/api/v1/trends")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) >= 1
    trend_key = items[0]["trend_key"]
    detail = client.get(f"/api/v1/trends/{trend_key}")
    assert detail.status_code == 200
    ev = client.get("/api/v1/evidences/sig_001")
    assert ev.status_code == 200


def test_removal_request_submit_and_query(client):
    created = client.post(
        "/api/v1/compliance/removal-requests",
        json={"requester_contact": "user@example.com", "target_signal_id": "sig_001", "reason": "test"},
    )
    assert created.status_code == 200
    data = created.json()["data"]
    ticket = data["ticket_id"]
    token = data["token"]
    queried = client.get(f"/api/v1/compliance/removal-requests/{ticket}", params={"token": token})
    assert queried.status_code == 200
