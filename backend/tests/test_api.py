from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_reports_process_liveness():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_versioned_status_and_cors():
    response = client.get("/api/v1/status", headers={"Origin": "http://localhost:5173"})
    assert response.json() == {"status": "ok", "phase": "foundation"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
