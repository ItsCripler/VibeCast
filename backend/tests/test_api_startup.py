from fastapi.testclient import TestClient

from app.main import app


def test_health_route_and_catalog_api_are_registered() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "/api/v1/catalog/songs" in app.openapi()["paths"]
