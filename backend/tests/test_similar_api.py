"""API tests for POST /search/similar.

The endpoint's external calls come through two seams in
app.services.similar_search:
  - get_vector_store(): Voyage (query embedding) + the PGVector store
  - get_reasons_chain(): Claude, which writes a "why this matches" note

Tests must never use the real ones: the real store would connect to the dev
database and Voyage (free tier: 3 requests per minute), and the real chain
would call Claude and cost money on every `pytest` run.

So an autouse fixture swaps both for fakes with monkeypatch, which puts the
originals back when the test finishes. It returns the fakes so a test can
configure them (what the store returns, whether Claude fails, ...).
"""

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.core.rate_limit import limiter
from app.rag.reasons import MatchReason, MatchReasons
from app.services import similar_search


class FakeStore:
    def __init__(self) -> None:
        self.scored: list[tuple[Document, float]] = []
        self.embed_error: Exception | None = None
        self.search_calls: list[int] = []  # the k of every search
        self.embeddings = SimpleNamespace(embed_query=self._embed_query)

    def _embed_query(self, text: str) -> list[float]:
        if self.embed_error is not None:
            raise self.embed_error
        return [0.0]

    def similarity_search_with_score_by_vector(self, embedding, k: int):
        self.search_calls.append(k)
        return self.scored[:k]


class FakeChain:
    def __init__(self) -> None:
        self.answer = MatchReasons(reasons=[])
        self.error: Exception | None = None
        self.calls: list[dict] = []

    def invoke(self, inputs: dict) -> MatchReasons:
        self.calls.append(inputs)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture(autouse=True)
def store(monkeypatch) -> FakeStore:
    fake = FakeStore()
    monkeypatch.setattr(similar_search, "get_vector_store", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def chain(monkeypatch) -> FakeChain:
    fake = FakeChain()
    monkeypatch.setattr(similar_search, "get_reasons_chain", lambda: fake)
    return fake


def _make_sector(client, name: str) -> int:
    crag = client.post("/crags/", json={"name": "C", "region": "R", "latitude": 41.0, "longitude": 1.0})
    sector = client.post("/sectors/", json={
        "name": name, "style": "sport", "grade_min": "6a", "grade_max": "7a",
        "crag_id": crag.json()["id"],
    })
    return sector.json()["id"]


def _doc(sector_id: int, name: str) -> Document:
    return Document(
        page_content=f"{name} text",
        metadata={"sector_id": sector_id, "name": name},
    )


# --- Ranking and sector loading ------------------------------------------


def test_similar_keeps_the_store_ranking_order(client, store):
    a_id = _make_sector(client, "A")
    b_id = _make_sector(client, "B")
    # B is the closer match even though A has the lower id.
    store.scored = [(_doc(b_id, "B"), 0.1), (_doc(a_id, "A"), 0.4)]

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["sector"]["name"] for r in results] == ["B", "A"]
    assert results[0]["similarity"] == pytest.approx(0.9)
    assert results[1]["similarity"] == pytest.approx(0.6)
    # The raw vector must never leak into the API response.
    assert "embedding" not in results[0]["sector"]


def test_similar_skips_documents_whose_sector_is_gone(client, store, chain):
    a_id = _make_sector(client, "A")
    store.scored = [(_doc(a_id, "A"), 0.1), (_doc(999999, "Gone"), 0.2)]

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 200
    assert [r["sector"]["name"] for r in response.json()["results"]] == ["A"]
    assert "id=999999" not in chain.calls[0]["sectors"]


def test_similar_passes_limit_to_the_store(client, store):
    ids = [_make_sector(client, f"S{i}") for i in range(3)]
    store.scored = [(_doc(sector_id, f"S{i}"), 0.1 * i) for i, sector_id in enumerate(ids)]

    response = client.post("/search/similar", json={"query": "x", "limit": 2})

    assert store.search_calls == [2]
    assert len(response.json()["results"]) == 2


def test_similar_returns_503_when_embedding_fails(client, store, chain):
    # Without the query vector there is no search at all, so this must be
    # an error (503), unlike a reasons failure below.
    store.embed_error = RuntimeError("Voyage is down")

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Couldn't reach the embedding service, try again later."
    assert store.search_calls == []
    assert chain.calls == []


def test_similar_with_no_matches_returns_empty_and_skips_claude(client, store, chain):
    store.scored = []

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert chain.calls == []


# --- Reasons (the Claude part) -------------------------------------------


def test_similar_attaches_reason_to_each_result(client, store, chain):
    a_id = _make_sector(client, "A")
    b_id = _make_sector(client, "B")
    store.scored = [(_doc(a_id, "A"), 0.1), (_doc(b_id, "B"), 0.2)]
    chain.answer = MatchReasons(reasons=[
        MatchReason(sector_id=a_id, reason="reason A"),
        MatchReason(sector_id=b_id, reason="reason B"),
    ])

    results = client.post("/search/similar", json={"query": "x"}).json()["results"]

    assert {r["sector"]["name"]: r["reason"] for r in results} == {"A": "reason A", "B": "reason B"}
    assert chain.calls[0]["query"] == "x"
    assert f"id={a_id} | A text" in chain.calls[0]["sectors"]
    assert f"id={b_id} | B text" in chain.calls[0]["sectors"]


def test_similar_reason_is_none_for_sector_claude_skipped(client, store, chain):
    # Claude might leave a sector out of its answer. The service uses
    # reasons.get(sector.id), so that sector gets reason=None instead of a
    # KeyError that would turn the whole response into a 500.
    a_id = _make_sector(client, "A")
    b_id = _make_sector(client, "B")
    store.scored = [(_doc(a_id, "A"), 0.1), (_doc(b_id, "B"), 0.2)]
    chain.answer = MatchReasons(reasons=[MatchReason(sector_id=a_id, reason="only this one")])

    results = client.post("/search/similar", json={"query": "x"}).json()["results"]

    assert {r["sector"]["name"]: r["reason"] for r in results} == {"A": "only this one", "B": None}


def test_similar_still_returns_results_when_reasons_chain_fails(client, store, chain):
    # The search already succeeded, so a Claude failure must not break the
    # response: same results, just reason=None everywhere.
    a_id = _make_sector(client, "A")
    store.scored = [(_doc(a_id, "A"), 0.1)]
    chain.error = RuntimeError("Claude is down")

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["reason"] is None


def test_similar_still_returns_results_when_reasons_chain_cannot_be_built(client, store, monkeypatch):
    a_id = _make_sector(client, "A")
    store.scored = [(_doc(a_id, "A"), 0.1)]

    def broken_build():
        raise RuntimeError("missing API key")

    monkeypatch.setattr(similar_search, "get_reasons_chain", broken_build)

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["reason"] is None


# -----------------Rate limit test-----------------

def test_similar_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)   # restored automatically after the test
    limiter.reset()                                  # start from a clean count

    # Collect every status code first, then compare the whole list: if this
    # ever fails, pytest shows both lists side by side, so you see exactly
    # which call was the first to be limited.
    codes = [client.post("/search/similar", json={"query": "x"}).status_code for _ in range(11)]

    assert codes == [200] * 10 + [429]
