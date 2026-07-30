from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "Echo",
        "environment": "development",
    }


def test_cors_allows_crop_put_preflight(client: TestClient) -> None:
    response = client.options(
        "/api/books/book-id/pages/1/crop",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"]
    assert "Authorization" in allowed_headers
    assert "Content-Type" in allowed_headers
