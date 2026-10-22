"""The client address behind CloudFront (ticket 025).

In the cloud, `fastapi run` wraps the app in uvicorn's ProxyHeadersMiddleware, trusting only
CloudFront's address ranges (FORWARDED_ALLOW_IPS, set in infra/main/api.tf). These tests wrap the
app the same way, with a made-up trusted range, to pin the behaviour the deployment relies on: the
rate limit is per viewer, a forged X-Forwarded-For does not escape it, and redirects keep https.
"""

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.rate_limit import limiter
from app.main import app
from app.schemas.search import ParsedFilters
from app.services import natural_search

TRUSTED_RANGE = "198.18.0.0/15"
CLOUDFRONT_EDGE = "198.18.0.10"
NOT_CLOUDFRONT = "192.0.2.50"
VIEWER = "203.0.113.7"
OTHER_VIEWER = "198.51.100.9"


class FakeParseChain:
    def invoke(self, inputs: dict, config: dict | None = None) -> ParsedFilters:
        return ParsedFilters(
            understood=True, min_grade="4", max_grade="9c+", max_distance_km=200, style=None
        )


@pytest.fixture(autouse=True)
def limited_and_offline(client, monkeypatch):
    # `client` is only needed for its dependency overrides (the test database).
    monkeypatch.setattr(natural_search, "get_parse_chain", lambda: FakeParseChain())
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()


def behind_proxy(peer: str, base_url: str = "http://testserver") -> TestClient:
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts=TRUSTED_RANGE)
    return TestClient(wrapped, client=(peer, 50000), base_url=base_url)


def search(client: TestClient, forwarded_for: str) -> int:
    response = client.post(
        "/search/natural", json={"query": "x"}, headers={"X-Forwarded-For": forwarded_for}
    )
    return response.status_code


def test_behind_cloudfront_each_viewer_has_its_own_limit():
    client = behind_proxy(CLOUDFRONT_EDGE)

    codes = [search(client, VIEWER) for _ in range(11)]

    assert codes == [200] * 10 + [429]
    assert search(client, OTHER_VIEWER) == 200


def test_a_forged_forwarded_for_does_not_escape_the_limit():
    client = behind_proxy(CLOUDFRONT_EDGE)
    for _ in range(10):
        assert search(client, VIEWER) == 200

    # CloudFront appends the real viewer address to what the viewer sent.
    assert search(client, f"192.0.2.1, {VIEWER}") == 429


def test_a_caller_outside_cloudfront_cannot_choose_its_address():
    client = behind_proxy(NOT_CLOUDFRONT)

    codes = [search(client, f"192.0.2.{i}") for i in range(1, 12)]

    assert codes == [200] * 10 + [429]


def test_redirects_keep_the_public_https_address():
    client = behind_proxy(CLOUDFRONT_EDGE, base_url="http://d111.cloudfront.net")

    response = client.get(
        "/crags", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://d111.cloudfront.net/crags/"
