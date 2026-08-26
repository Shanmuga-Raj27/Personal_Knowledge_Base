from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_ping_endpoint():
    """Verify that the system health check /system/ping endpoint works correctly."""
    response = client.get("/system/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "pong"}
