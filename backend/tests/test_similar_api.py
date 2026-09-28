"""API tests for POST /search/similar.

The endpoint calls two external services:
  - Voyage, through embed_query(), to turn the query text into a vector
  - Claude, through explain_matches(), to write a "why this matches" note

Tests must never call either one for real: that would cost money on every
`pytest` run, make tests slow, and make them fail offline or when a service
rate-limits us (Voyage's free tier allows 3 requests per minute).

So we use pytest's `monkeypatch` fixture to swap those two functions for
fakes while a test runs. `monkeypatch.setattr(module, "name", fake)` replaces
`module.name` with `fake`, and pytest automatically puts the original back
when the test finishes, so one test's fake never leaks into another test.
"""

import pytest

from app.models import Sector
from app.routers import search as search_router


DIM = 1024  # must match Vector(1024) on Sector.embedding


# --- Fixtures and helpers -------------------------------------------------


@pytest.fixture(autouse=True)
def fake_explain(monkeypatch):
    """Replace Claude with a fake in every test of this file.

    autouse=True means every test here gets this fixture automatically, even
    though no test lists it as a parameter. That's the safe default: a new
    test added later can't accidentally call the real Claude API.

    The fake returns the same shape as the real explain_matches(): a dict
    {sector_id: reason}. A test that needs different behaviour (e.g. Claude
    failing) simply calls monkeypatch.setattr again; the later patch wins.
    """
    def fake_explain_matches(query: str, sectors: list[Sector]) -> dict[int, str]:
        return {sector.id: f"test reason for {sector.name}" for sector in sectors}

    monkeypatch.setattr(search_router, "explain_matches", fake_explain_matches)


def _unit(i: int) -> list[float]:
    """A vector of zeros with a single 1.0 at position i.

    Two different unit vectors are at 90 degrees to each other (cosine
    similarity 0), and a vector compared to itself has similarity 1. That
    makes the expected ranking obvious: whichever sector shares the query's
    axis comes first.
    """
    vec = [0.0] * DIM
    vec[i] = 1.0
    return vec


def _fake_query_vector(monkeypatch, vec: list[float]) -> None:
    """Make embed_query() return `vec` instead of calling Voyage."""
    monkeypatch.setattr(search_router, "embed_query", lambda text: vec)


def _make_sector(client, db_session, name: str, embedding: list[float] | None) -> int:
    """Create a crag + sector through the API, then set its embedding.

    The embedding is written directly through db_session because the API
    deliberately doesn't accept embeddings (they're internal, not part of
    SectorCreate). db_session is the same session the client uses, via the
    get_db override in conftest.py, so the endpoint sees this change.
    """
    crag = client.post("/crags/", json={"name": "C", "region": "R", "latitude": 41.0, "longitude": 1.0})
    sector = client.post("/sectors/", json={
        "name": name, "style": "sport", "grade_min": "6a", "grade_max": "7a",
        "crag_id": crag.json()["id"],
    })
    sector_id = sector.json()["id"]
    db_session.get(Sector, sector_id).embedding = embedding
    db_session.commit()
    return sector_id


# --- Ranking (the pgvector part) -----------------------------------------


def test_similar_ranks_closest_first(client, db_session, monkeypatch):
    _make_sector(client, db_session, "Along axis 0", _unit(0))
    _make_sector(client, db_session, "Along axis 1", _unit(1))
    # The query points along axis 0, so "Along axis 0" must rank first.
    _fake_query_vector(monkeypatch, _unit(0))

    response = client.post("/search/similar", json={"query": "anything"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["sector"]["name"] for r in results] == ["Along axis 0", "Along axis 1"]
    assert results[0]["similarity"] > results[1]["similarity"]
    # The raw 1024-float vector must never leak into the API response.
    assert "embedding" not in results[0]["sector"]


def test_similar_skips_sectors_without_embedding(client, db_session, monkeypatch):
    _make_sector(client, db_session, "Has vector", _unit(0))
    _make_sector(client, db_session, "No vector", None)
    _fake_query_vector(monkeypatch, _unit(0))

    results = client.post("/search/similar", json={"query": "x"}).json()["results"]

    assert [r["sector"]["name"] for r in results] == ["Has vector"]


def test_similar_respects_limit(client, db_session, monkeypatch):
    for i in range(3):
        _make_sector(client, db_session, f"S{i}", _unit(i))
    _fake_query_vector(monkeypatch, _unit(0))

    response = client.post("/search/similar", json={"query": "x", "limit": 2})

    assert len(response.json()["results"]) == 2


def test_similar_returns_503_when_embedding_fails(client, monkeypatch):
    # Without the query vector there is no search at all, so this must be
    # an error (503), unlike an explanation failure below.
    def broken_embed(text):
        raise RuntimeError("Voyage is down")

    monkeypatch.setattr(search_router, "embed_query", broken_embed)

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 503


# --- Explanations (the Claude part) --------------------------------------


def test_similar_attaches_reason_to_each_result(client, db_session, monkeypatch):
    # Proves the wiring: whatever explain_matches returns for a sector id
    # ends up in that sector's "reason" field. Uses the autouse fake.
    _make_sector(client, db_session, "Poble", _unit(0))
    _make_sector(client, db_session, "Agulles", _unit(1))
    _fake_query_vector(monkeypatch, _unit(0))

    results = client.post("/search/similar", json={"query": "x"}).json()["results"]

    assert {r["sector"]["name"]: r["reason"] for r in results} == {
        "Poble": "test reason for Poble",
        "Agulles": "test reason for Agulles",
    }


def test_similar_reason_is_none_for_sector_claude_skipped(client, db_session, monkeypatch):
    # Claude might leave a sector out of its answer. The endpoint uses
    # reasons.get(sector.id), so that sector gets reason=None instead of a
    # KeyError that would turn the whole response into a 500.
    kept_id = _make_sector(client, db_session, "Explained", _unit(0))
    _make_sector(client, db_session, "Skipped", _unit(1))
    _fake_query_vector(monkeypatch, _unit(0))
    monkeypatch.setattr(
        search_router, "explain_matches",
        lambda query, sectors: {kept_id: "only this one"},
    )

    results = client.post("/search/similar", json={"query": "x"}).json()["results"]

    reasons = {r["sector"]["name"]: r["reason"] for r in results}
    assert reasons == {"Explained": "only this one", "Skipped": None}


def test_similar_still_returns_results_when_explain_fails(client, db_session, monkeypatch):
    # The search already succeeded, so a Claude failure must not break the
    # response: same results, just reason=None everywhere.
    _make_sector(client, db_session, "Has vector", _unit(0))
    _fake_query_vector(monkeypatch, _unit(0))

    def broken_explain(query: str, sectors: list[Sector]) -> dict[int, str]:
        raise RuntimeError("Claude is down")

    monkeypatch.setattr(search_router, "explain_matches", broken_explain)

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["reason"] is None
