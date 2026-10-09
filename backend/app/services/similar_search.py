"""Similar search: glue between the LangChain pieces in app/rag and the database.

The PGVector store ranks sectors by cosine distance and the reasons chain asks
Claude why each one fits; this module loads the real Sector rows in the store's
order and packages the answer. The router only turns errors into HTTP codes.
"""

import logging

from langchain_core.documents import Document
from sqlalchemy.orm import Session, joinedload

from app.models import Sector
from app.rag.reasons import format_sectors, get_reasons_chain
from app.rag.vectorstore import get_vector_store
from app.schemas.search import SimilarMatch, SimilarSearchResponse

logger = logging.getLogger(__name__)


class EmbeddingUnavailableError(Exception):
    """Voyage couldn't embed the query, so there is no search at all."""


def _attach_sectors(
    db: Session, scored: list[tuple[Document, float]]
) -> list[tuple[Sector, Document, float]]:
    ids = [doc.metadata["sector_id"] for doc, _ in scored]
    sectors = (
        db.query(Sector)
        .options(joinedload(Sector.crag))
        .filter(Sector.id.in_(ids))
        .all()
    )
    by_id = {sector.id: sector for sector in sectors}

    # SQL IN doesn't keep order, so walk the store's list to keep its ranking.
    ranked = []
    for doc, distance in scored:
        sector = by_id.get(doc.metadata["sector_id"])
        if sector is None:
            logger.warning(
                "Sector %s is in the vector store but not in the database; "
                "re-run index_sectors_langchain",
                doc.metadata["sector_id"],
            )
            continue
        ranked.append((sector, doc, distance))
    return ranked


def _explain(query: str, docs: list[Document]) -> dict[int, str]:
    if not docs:
        return {}
    # Building the chain is inside the try too: a missing key or bad config
    # should only cost the reasons, not the search results.
    try:
        answer = get_reasons_chain().invoke({"query": query, "sectors": format_sectors(docs)})
        return {r.sector_id: r.reason for r in answer.reasons}
    except Exception:
        logger.exception("reasons chain failed; returning results without reasons")
        return {}


def find_similar_sectors(db: Session, query: str, limit: int) -> SimilarSearchResponse:
    store = get_vector_store()

    # Only the Voyage call is in the try, so a database error stays a 500.
    try:
        query_vec = store.embeddings.embed_query(query)
    except Exception as exc:
        raise EmbeddingUnavailableError from exc

    scored = store.similarity_search_with_score_by_vector(query_vec, k=limit)
    ranked = _attach_sectors(db, scored)
    reasons = _explain(query, [doc for _, doc, _ in ranked])

    return SimilarSearchResponse(
        results=[
            SimilarMatch(sector=sector, similarity=1 - distance, reason=reasons.get(sector.id))
            for sector, _, distance in ranked
        ]
    )
