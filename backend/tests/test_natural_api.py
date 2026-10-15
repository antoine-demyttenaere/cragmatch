"""API tests for POST /search/natural.

The endpoint's only external call is Claude, through get_parse_chain() in
app.services.natural_search. An autouse fixture swaps it for a fake in every
test, so a new test can't reach Claude (and cost money) by accident.
"""

from datetime import UTC, datetime

import pytest
from langchain_core.exceptions import OutputParserException

from app.core.config import settings
from app.core.rate_limit import limiter
from app.routers.search import DAILY_LIMIT_DETAIL
from app.schemas.search import ParsedFilters
from app.services import natural_search, spending
from app.services.spending import Provider

CLEAR = ParsedFilters(
    understood=True, min_grade="6b", max_grade="6b", max_distance_km=200, style="sport"
)

UNAVAILABLE = "The search assistant is unavailable, try the search form instead."


class FakeParseChain:
    def __init__(self, report_claude_usage) -> None:
        self.answer = ParsedFilters(
            understood=True, min_grade="4", max_grade="9c+", max_distance_km=200, style=None
        )
        self.error: Exception | None = None
        self.usage: tuple[int, int] | None = None  # (input, output) tokens to report
        self.calls: list[dict] = []
        self._report = report_claude_usage

    def invoke(self, inputs: dict, config: dict | None = None) -> ParsedFilters:
        self.calls.append(inputs)
        if self.usage is not None:
            self._report(config, *self.usage)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture(autouse=True)
def chain(monkeypatch, report_claude_usage) -> FakeParseChain:
    fake = FakeParseChain(report_claude_usage)
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


# --- Daily spending cap ----------------------------------------------------

AT_THE_CAP = 0.5


def test_natural_counts_claude_spend(client, chain, db_session):
    chain.usage = (1000, 500)

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 200
    assert spending.spent(db_session, Provider.CLAUDE) == pytest.approx(
        spending.claude_cost(1000, 500)
    )


def test_natural_counts_the_tokens_of_an_unusable_answer(client, chain, db_session):
    chain.usage = (1000, 500)
    chain.error = OutputParserException("not JSON")

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 503
    assert response.json()["detail"] == UNAVAILABLE
    assert spending.spent(db_session, Provider.CLAUDE) == pytest.approx(
        spending.claude_cost(1000, 500)
    )


def test_natural_rejects_at_the_daily_limit_without_calling_claude(
    client, chain, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", AT_THE_CAP)
    spending.record_spend(db_session, Provider.CLAUDE, AT_THE_CAP)

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == DAILY_LIMIT_DETAIL
    assert "spending limit" in detail and "tomorrow" in detail
    assert chain.calls == []


def test_natural_ignores_the_voyage_cap(client, chain, monkeypatch):
    monkeypatch.setattr(settings, "voyage_daily_cap_usd", 0)

    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 200
    assert len(chain.calls) == 1


def test_natural_daily_limit_comes_after_the_rate_limit(client, chain, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 0)

    responses = [client.post("/search/natural", json={"query": "x"}) for _ in range(11)]

    assert [r.status_code for r in responses] == [503] * 10 + [429]
    assert responses[0].json()["detail"] == DAILY_LIMIT_DETAIL
    assert chain.calls == []


def test_natural_works_again_the_next_day(client, chain, db_session, monkeypatch, set_clock):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", AT_THE_CAP)
    set_clock(datetime(2026, 10, 13, 12, 0, tzinfo=UTC))
    spending.record_spend(db_session, Provider.CLAUDE, AT_THE_CAP)
    assert client.post("/search/natural", json={"query": "x"}).status_code == 503

    set_clock(datetime(2026, 10, 14, 12, 0, tzinfo=UTC))
    response = client.post("/search/natural", json={"query": "x"})

    assert response.status_code == 200
    assert len(chain.calls) == 1
