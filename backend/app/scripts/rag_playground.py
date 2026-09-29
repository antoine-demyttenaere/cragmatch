"""Stage 6 learning playground: one function per step.

Run a single step:
    uv run python -m app.scripts.rag_playground 6.2
    uv run python -m app.scripts.rag_playground 6.4

Steps that call Voyage say how many requests they make: the free tier
allows 3 per minute.
"""

import sys

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.database import SessionLocal
from app.models import Sector
from app.rag.loader import SectorLoader
from app.rag.vectorstore import get_embeddings, get_vector_store


def show(title, docs):
    print(f"\n=== {title}: {len(docs)} documents ===")
    for doc in docs:
        print(f"[{len(doc.page_content):>3} chars] {doc.metadata}")
        print(f"            {doc.page_content!r}")


def step_6_2():
    """Load sectors as Documents, then split them. No Voyage calls."""
    db = SessionLocal()
    try:
        docs = SectorLoader(db).load()
    finally:
        db.close()
    print(f"Loaded {len(docs)} sectors")
    show("First 3 loaded", docs[:3])

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    print(f"\nchunk_size=1000: {len(docs)} documents in -> {len(chunks)} chunks out")

    tiny = RecursiveCharacterTextSplitter(chunk_size=60, chunk_overlap=15, add_start_index=True)
    tiny_chunks = tiny.split_documents(docs)
    print(f"chunk_size=60:   {len(docs)} documents in -> {len(tiny_chunks)} chunks out")
    show("Sector 1 in tiny chunks", [c for c in tiny_chunks if c.metadata["sector_id"] == 1])


def step_6_3(query: str = "quiet crag, short approach", k: int = 5):
    """Same query vector through LangChain PGVector and Stage 3's raw SQL. 1 Voyage call."""
    print(f"\n=== Step 6.3: '{query}' ===")
    query_vec = get_embeddings().embed_query(query)   # ONE Voyage call, shared by both

    store = get_vector_store()
    print("LangChain PGVector:")
    for doc, distance in store.similarity_search_with_score_by_vector(query_vec, k=k):
        print(f"  {1 - distance:.3f}  {doc.metadata['name']}  (distance {distance:.4f})")

    db = SessionLocal()
    try:
        distance_col = Sector.embedding.cosine_distance(query_vec)
        rows = (
            db.query(Sector, distance_col.label("distance"))
            .filter(Sector.embedding.is_not(None))
            .order_by(distance_col)
            .limit(k)
            .all()
        )
    finally:
        db.close()
    print("Stage 3 raw pgvector:")
    for sector, distance in rows:
        print(f"  {1 - distance:.3f}  {sector.name}  (distance {distance:.4f})")


def step_6_4():
    """Three retriever modes. 3 Voyage calls (one per invoke)."""
    store = get_vector_store()

    retriever = store.as_retriever(search_kwargs={"k": 5})
    docs = retriever.invoke("somewhere good for kids and beginners")
    print("\n=== Step 6.4a: plain retriever ===")
    print("returns:", type(docs).__name__, "of", type(docs[0]).__name__)
    for doc in docs:
        print(f"  {doc.id:<10} {doc.metadata['name']:<12} ({doc.metadata['crag']})")

    siurana_only = store.as_retriever(search_kwargs={"k": 3, "filter": {"crag": {"$eq": "Siurana"}}})
    print("\n=== Step 6.4b: filtered to crag = Siurana ===")
    for doc in siurana_only.invoke("quiet crag, short approach"):
        print(f"  {doc.metadata['name']}")

    confident = store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 5, "score_threshold": 0.5},
    )
    print("\n=== Step 6.4c: only relevance >= 0.5 ===")
    for doc in confident.invoke("shady spot for a hot summer day"):
        print(f"  {doc.metadata['name']}")


STEPS = {"6.2": step_6_2, "6.3": step_6_3, "6.4": step_6_4}


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else None
    if step not in STEPS:
        print(f"Usage: python -m app.scripts.rag_playground <step>   (steps: {', '.join(STEPS)})")
        sys.exit(1)
    STEPS[step]()
