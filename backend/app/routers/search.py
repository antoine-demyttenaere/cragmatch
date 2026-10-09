from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.core.dependencies import get_db
from app.schemas.search import (
    NaturalSearchRequest,
    NaturalSearchResponse,
    SimilarSearchRequest,
    SimilarSearchResponse,
)
from app.services.natural_search import (
    AssistantUnavailableError,
    QueryNotUnderstoodError,
    UnusableFiltersError,
    find_sectors_from_query,
)
from app.services.similar_search import EmbeddingUnavailableError, find_similar_sectors

import logging
logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/natural", response_model=NaturalSearchResponse)
@limiter.limit("10/minute")
def search_natural(request: Request, body: NaturalSearchRequest, db: Session = Depends(get_db)):
    try:
        return find_sectors_from_query(db, body.query)
    except AssistantUnavailableError:
        logger.exception("Failed to parse natural language query")
        raise HTTPException(
            status_code=503,
            detail="The search assistant is unavailable, try the search form instead.",
        )
    except QueryNotUnderstoodError:
        raise HTTPException(
            status_code=422,
            detail="Couldn't understand that as a climbing search — try the search form instead.",
        )
    except UnusableFiltersError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/similar",
    response_model=SimilarSearchResponse,
    summary="Find sectors similar to a free-text description",
    description=(
        "Embeds the query with Voyage and ranks sectors by cosine "
        "similarity in the LangChain PGVector store, then a LangChain chain "
        "asks Claude for a reason per sector. For fuzzy asks that don't "
        "map to hard filters, e.g. 'quiet crag, short approach'."
    ),
)
@limiter.limit("10/minute")
def search_similar(request: Request, body: SimilarSearchRequest, db: Session = Depends(get_db)):
    try:
        return find_similar_sectors(db, body.query, body.limit)
    except EmbeddingUnavailableError:
        logger.exception("Failed to embed query")
        raise HTTPException(
            status_code=503,
            detail="Couldn't reach the embedding service, try again later.",
        )