"""API tests for POST /search/natural.

The endpoint's only external call is Claude, through get_parse_chain() in
app.services.natural_search. An autouse fixture swaps it for a fake in every
test, so a new test can't reach Claude (and cost money) by accident.
"""

import pytest
from langchain_core.exceptions import OutputParserException

from app.core.rate_limit import limiter
from app.schemas.search import ParsedFilters
from app.services import natural_search

CLEAR = ParsedFilters(
    understood=True, min_grade="6b", max_grade="6b", max_distance_km=200, style="sport"
)

UNAVAILABLE = "The search assistant is unavailable, try the search form instead."


class FakeParseChain:
    def __init__(self) -> None:
        self.answer = ParsedFilters(
            understood=True, min_grade="4", max_grade="9c+", max_distance_km=200, style=None
        )
        self.error: Exception | None = None
        self.calls: list[dict] = []

    def invoke(self, inputs: dict) -> ParsedFilters:
        self.calls.append(inputs)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture(autouse=True)
def chain(monkeypatch) -> FakeParseChain:
    fake = FakeParseChain()
    monkeypatch.setattr(natural_search, "get_parse_chain", lambda: fake)
    return fake


def _make_sector(client, name: str, style: str, lat: float, lon: float) -> int:
    crag = client.post("/crags/", json={"name": f"{name} crag", "region": "R", "latitude": lat, "longitude": lon})
    sector = client.post("/sectors/", json={
        "name": name, "style": style, "grade_min": "6a", "grade_max": "7a",
        "crag_id": crag.json()["id"],
    })
    return sector.json()["id"]


def test_natural_returns_parsed_filters_and_matching_sectors(client, chain):
    _make_sector(client, "Sporty", "sport", 41.4, 2.0)
    _make_sector(client, "Blocs", "boulder", 41.4, 2.0)
    chain.answer = CLEAR
    query = "something around 6b, not too far, sport"

    response = client.post("/search/natural", json={"query": query})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"parsed_filters", "results"}
    assert body["parsed_filters"] == CLEAR.model_dump()
    assert [r["name"] for r in body["results"]] == ["Sporty"]
    assert chain.calls == [{"query": query}]


def test_natural_measures_distance_from_barcelona(client, chain):
    _make_sector(client, "Near", "sport", 41.4, 2.0)  # ~14 km from Barcelona
    _make_sector(client, "Far", "sport", 41.0, 1.0)  # ~107 km from Barcelona
    chain.answer = chain.answer.model_copy(update={"max_distance_km": 50, "style": None})

    response = client.post("/search/natural", json={"query": "close to Barcelona"})

    assert response.status_code == 200
    assert [r["name"] for r in response.json()["results"]] == ["Near"]


def test_natural_returns_422_when_query_not_understood(client, chain):
    chain.answer = chain.answer.model_copy(update={"understood": False})

    response = client.post("/search/natural", json={"query": "what is your favorite color"})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Couldn't understand that as a climbing search — try the search form instead."
    )


def test_natural_returns_400_for_unrecognized_style(client, chain):
    chain.answer = chain.answer.model_copy(update={"style": "ice"})

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Model returned an unrecognized style: 'ice'"


def test_natural_returns_400_for_unknown_grade(client, chain):
    chain.answer = chain.answer.model_copy(update={"min_grade": "6z", "max_grade": "6b"})

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Couldn't understand the grade range in that query: 6z-6b"
    )


def test_natural_returns_503_when_claude_fails(client, chain):
    chain.error = RuntimeError("Claude is down")

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 503
    assert response.json()["detail"] == UNAVAILABLE


def test_natural_returns_503_when_answer_is_unusable(client, chain):
    # Stage 3 crashed with a 500 here (parsed_output was None).
    chain.error = OutputParserException("not JSON")

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 503
    assert response.json()["detail"] == UNAVAILABLE


def test_natural_returns_503_when_chain_cannot_be_built(client, monkeypatch):
    def broken_build():
        raise RuntimeError("missing API key")

    monkeypatch.setattr(natural_search, "get_parse_chain", broken_build)

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 503
    assert response.json()["detail"] == UNAVAILABLE


def test_natural_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)  # restored automatically after the test
    limiter.reset()

    codes = [client.post("/search/natural", json={"query": "x"}).status_code for _ in range(11)]

    assert codes == [200] * 10 + [429]
