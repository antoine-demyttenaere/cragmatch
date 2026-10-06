from app.core.database import SessionLocal
from app.rag.loader import SectorLoader
from app.rag.vectorstore import get_vector_store


def main():
    db = SessionLocal()
    try:
        docs = SectorLoader(db).load()   # 13 Documents, unsplit (see Step 6.2)
    finally:
        db.close()

    store = get_vector_store()
    # Stable ids ("sector-1", ...) make this an upsert: re-running updates
    # the 13 rows instead of adding 13 more each time.
    ids = [f"sector-{doc.metadata['sector_id']}" for doc in docs]
    store.add_documents(docs, ids=ids)
    print(f"Indexed {len(docs)} sectors into the '{store.collection_name}' collection.")


if __name__ == "__main__":
    main()
