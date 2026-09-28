from app.models import Sector
from app.routers import search as search_router

DIM = 1024


def _unit(i: int) -> list[float]:
    """A vector pointing along axis i, so similarity is easy to predict."""
    vec = [0.0] * DIM
    vec[i] = 1.0
    return vec


def _make_sector(client, db_session, name: str, embedding: list[float] | None) -> int:
    crag = client.post("/crags/", json={"name": "C", "region": "R", "latitude": 41.0, "longitude": 1.0})
    sector = client.post("/sectors/", json={
        "name": name, "style": "sport", "grade_min": "6a", "grade_max": "7a",
        "crag_id": crag.json()["id"],
    })
    sector_id = sector.json()["id"]
    db_session.get(Sector, sector_id).embedding = embedding
    db_session.commit()
    return sector_id


def test_similar_ranks_closest_first(client, db_session, monkeypatch):
    _make_sector(client, db_session, "Along axis 0", _unit(0))
    _make_sector(client, db_session, "Along axis 1", _unit(1))
    # The "query" points along axis 0, so that sector must come first.
    monkeypatch.setattr(search_router, "embed_query", lambda text: _unit(0))

    response = client.post("/search/similar", json={"query": "anything"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["sector"]["name"] for r in results] == ["Along axis 0", "Along axis 1"]
    assert results[0]["similarity"] > results[1]["similarity"]
    assert "embedding" not in results[0]["sector"]


def test_similar_skips_sectors_without_embedding(client, db_session, monkeypatch):
    _make_sector(client, db_session, "Has vector", _unit(0))
    _make_sector(client, db_session, "No vector", None)
    monkeypatch.setattr(search_router, "embed_query", lambda text: _unit(0))

    names = [r["sector"]["name"] for r in client.post("/search/similar", json={"query": "x"}).json()["results"]]

    assert names == ["Has vector"]


def test_similar_respects_limit(client, db_session, monkeypatch):
    for i in range(3):
        _make_sector(client, db_session, f"S{i}", _unit(i))
    monkeypatch.setattr(search_router, "embed_query", lambda text: _unit(0))

    response = client.post("/search/similar", json={"query": "x", "limit": 2})

    assert len(response.json()["results"]) == 2


def test_similar_returns_503_when_embedding_fails(client, monkeypatch):
    def broken(text):
        raise RuntimeError("Voyage is down")

    monkeypatch.setattr(search_router, "embed_query", broken)

    response = client.post("/search/similar", json={"query": "x"})

    assert response.status_code == 503
