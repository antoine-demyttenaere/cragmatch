"""Index every sector into the LangChain PGVector store (used by /search/similar).

    uv run python -m app.scripts.index_sectors_langchain

Makes 1 Voyage request. Safe to re-run: the ids are stable, so it updates in place.
Run seed_notes first, because the index embeds the notes.
"""

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

from app.core.database import SessionLocal
from app.rag.loader import SectorLoader
from app.rag.vectorstore import get_vector_store


def index_sectors(docs: list[Document], store: VectorStore) -> tuple[int, int]:
    """Upsert the documents; return (added, already there)."""
    # Stable ids ("sector-1", ...) make this an upsert: re-running updates
    # the rows instead of adding new ones each time.
    ids = [f"sector-{doc.metadata['sector_id']}" for doc in docs]
    already_there = len(store.get_by_ids(ids))  # a database read, no Voyage
    store.add_documents(docs, ids=ids)  # the single Voyage request
    return len(docs) - already_there, already_there


def main() -> None:
    with SessionLocal() as db:
        docs = SectorLoader(db).load()  # closed before the Voyage call

    added, already_there = index_sectors(docs, get_vector_store())
    print(f"Index: {added} added, {already_there} already there (updated in place)")


if __name__ == "__main__":
    main()
