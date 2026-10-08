"""Vector store factory tests. The real PGVector connects to the dev DB, so it is faked."""

import pytest
from langchain_postgres.vectorstores import DistanceStrategy

from app.rag import vectorstore


class FakePGVector:
    instances: list["FakePGVector"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        FakePGVector.instances.append(self)


@pytest.fixture
def clean_store_cache():
    # A fake must never stay cached for later tests.
    vectorstore.get_vector_store.cache_clear()
    FakePGVector.instances = []
    yield
    vectorstore.get_vector_store.cache_clear()


def test_vector_store_is_cosine_and_built_once(monkeypatch, clean_store_cache):
    monkeypatch.setattr(vectorstore, "PGVector", FakePGVector)
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: "fake-embeddings")

    first = vectorstore.get_vector_store()
    second = vectorstore.get_vector_store()

    assert first is second
    assert len(FakePGVector.instances) == 1
    kwargs = first.kwargs
    assert kwargs["distance_strategy"] == DistanceStrategy.COSINE
    assert kwargs["collection_name"] == "sectors"
    assert kwargs["embedding_length"] == 1024
