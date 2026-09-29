from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.core.rate_limit import limiter
from app.core.dependencies import get_db
from app.models import ClimbingStyle, Sector
from app.schemas.search import (
    NaturalSearchRequest,
    NaturalSearchResponse,
    ParsedFilters,
    SimilarMatch,
    SimilarSearchRequest,
    SimilarSearchResponse,
)
from app.services.embedding import embed_query
from app.services.geo import BARCELONA
from app.services.search import find_matching_sectors

from app.services.llm import LLM_MODEL, client, log_usage
from app.services.explain import explain_matches

import logging
logger = logging.getLogger(__name__)


router = APIRouter()

SYSTEM_PROMPT = """You extract structured climbing search filters from a
natural-language request. The user is in Barcelona, Catalonia, looking for
climbing sectors.
- understood: set this to false if the query has nothing to do with finding
  a climbing sector — no grade, location, distance, or style hint at all
  (e.g. off-topic questions, gibberish, or requests unrelated to climbing).
  Otherwise true, even for vague-but-real requests like "something easy
  near Barcelona".
  Example — understood=false: "what is your favorite color", "asdf asdf",
  "tell me a joke". These have zero climbing content, even if grammatically
  well-formed questions.
- min_grade / max_grade: French climbing grades. Grades 1-5 are a plain
  number with an optional "+" (e.g. "3", "4+", "5"), with NO letter.
  Grades 6-9 always have a letter a/b/c and an optional "+" (e.g. "6a",
  "6a+", "7c+"). Never combine a number 1-5 with a letter. If the user
  doesn't mention a grade, use "4" to "9c+".
- max_distance_km: a straight-line distance in km from Barcelona. If the user
  gives a travel time instead (e.g. "1.5 hours"), convert it assuming
  mountain-road driving at roughly 80 km/h average, then round sensibly.
  If nothing is mentioned, use 200.
- style: "sport", "boulder", "trad", or "multi-pitch" if mentioned, otherwise
  null.
"""


@router.post("/natural", response_model=NaturalSearchResponse)
@limiter.limit("10/minute")
def search_natural(request: Request, body: NaturalSearchRequest, db: Session = Depends(get_db)):
    try:
        response = client.messages.parse(
            model=LLM_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": body.query}],
            output_format=ParsedFilters,
        )
    except Exception:
        logger.exception("Failed to parse natural language query")
        raise HTTPException(
            status_code=503,
            detail="The search assistant is unavailable, try the search form instead.",
        )

    
    log_usage("natural_search", response)
    
    
    filters = response.parsed_output

    if not filters.understood:
        raise HTTPException(
            status_code=422,
            detail="Couldn't understand that as a climbing search — try the search form instead.",
        )

    
    try:
        style = ClimbingStyle(filters.style) if filters.style else None
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Model returned an unrecognized style: {filters.style!r}",
        )

    try:
        results = find_matching_sectors(
            db,
            min_grade=filters.min_grade,
            max_grade=filters.max_grade,
            style=style,
            origin_lat=BARCELONA[0],
            origin_lon=BARCELONA[1],
            max_distance_km=filters.max_distance_km,
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Couldn't understand the grade range in that query: {filters.min_grade}-{filters.max_grade}",
        )

    return NaturalSearchResponse(parsed_filters=filters, results=results)


@router.post(
    "/similar",
    response_model=SimilarSearchResponse,
    summary="Find sectors similar to a free-text description",
    description=(
        "Embeds the query with Voyage and ranks sectors by cosine "
        "similarity to their stored embeddings. For fuzzy asks that don't "
        "map to hard filters, e.g. 'quiet crag, short approach'."
    ),
)
@limiter.limit("10/minute")
def search_similar(request: Request, body: SimilarSearchRequest, db: Session = Depends(get_db)):
    try:
        query_vec = embed_query(body.query)
    except Exception:
        logger.exception("Failed to embed query")
        raise HTTPException(
            status_code=503,
            detail="Couldn't reach the embedding service, try again later.",
        )

    # pgvector's `<=>` operator: Postgres computes and sorts by the distance.
    distance = Sector.embedding.cosine_distance(query_vec)

    rows = (
        db.query(Sector, distance.label("distance"))
        .options(joinedload(Sector.crag))
        .filter(Sector.embedding.is_not(None))
        .order_by(distance)
        .limit(body.limit)
        .all()
    )

    sectors = [sector for sector, _ in rows]

    try:
        reasons = explain_matches(body.query, sectors)
    except Exception:
        logger.exception("explain_matches failed; returning results without reasons")
        reasons = {}

    return SimilarSearchResponse(
        results=[
            SimilarMatch(sector=sector, similarity=1 - dist, reason=reasons.get(sector.id))
            for sector, dist in rows
        ]
    )