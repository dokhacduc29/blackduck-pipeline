import pytest
from app import app

@pytest.fixture
def client():
    # Flask test client — không cần start server thật
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_health(client):
    # Test /health trả 200 + JSON đúng format
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "version" in data

def test_hello(client):
    # Test / trả 200 + có text
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"DevSecOps" in resp.data
