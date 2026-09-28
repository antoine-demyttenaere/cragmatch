import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_db
from app.models import ClimbingStyle
from app.schemas.search import NaturalSearchRequest, NaturalSearchResponse, ParsedFilters
from app.services.search import find_matching_sectors

router = APIRouter()

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

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
def search_natural(request: NaturalSearchRequest, db: Session = Depends(get_db)):
    try:
        response = client.messages.parse(
            model="claude-sonnet-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": request.query}],
            output_format=ParsedFilters,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse natural language query: {str(e)}",
        )
    
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
            origin_lat=41.3874,
            origin_lon=2.1686,
            max_distance_km=filters.max_distance_km,
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Couldn't understand the grade range in that query: {filters.min_grade}-{filters.max_grade}",
        )

    return NaturalSearchResponse(parsed_filters=filters, results=results)
