from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.main import app


def test_cors_allows_the_default_origin(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_refuses_an_unlisted_origin(client):
    origin = {"Origin": "https://evil.example"}
    preflight = client.options(
        "/health", headers={**origin, "Access-Control-Request-Method": "GET"}
    )
    assert preflight.status_code == 400

    # The request itself works, but a browser cannot read it without the header.
    response = client.get("/health", headers=origin)
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_come_from_settings():
    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors.kwargs["allow_origins"] == settings.cors_origins
