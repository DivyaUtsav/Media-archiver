def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_provider_health_endpoint(client):
    response = client.get("/health/providers")
    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "checks" in payload
    assert "text" in payload["checks"]
    assert "content_rating" in payload["checks"]
    assert "art_type" in payload["checks"]
