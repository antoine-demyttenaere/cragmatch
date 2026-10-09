"""Natural search: Claude turns the text into filters, then the Stage 1 filter runs.

The parse chain lives in app/rag; this module applies the rules around its answer
(understood, style, grades) and filters sectors from Barcelona. The router only
turns errors into HTTP codes.
"""

from sqlalchemy.orm import Session

from app.models import ClimbingStyle
from app.rag.query_parsing import get_parse_chain
from app.schemas.search import NaturalSearchResponse, ParsedFilters
from app.services.geo import BARCELONA
from app.services.search import find_matching_sectors


class AssistantUnavailableError(Exception):
    """Claude couldn't be reached or gave an unusable answer."""


class QueryNotUnderstoodError(Exception):
    """Claude says the text isn't a climbing search (an exception because the API answers 422)."""


class UnusableFiltersError(Exception):
    """The parsed filters can't be applied; str(exc) is the message for the user."""


def _parse(query: str) -> ParsedFilters:
    # Building the chain is inside the try too: a missing key or bad config is
    # also "assistant unavailable". This catches OutputParserException as well,
    # where Stage 3 crashed with a 500 on parsed_output=None.
    try:
        return get_parse_chain().invoke({"query": query})
    except Exception as exc:
        raise AssistantUnavailableError from exc


def _style(filters: ParsedFilters) -> ClimbingStyle | None:
    if not filters.style:
        return None
    try:
        return ClimbingStyle(filters.style)
    except ValueError:
        raise UnusableFiltersError(f"Model returned an unrecognized style: {filters.style!r}")


def find_sectors_from_query(db: Session, query: str) -> NaturalSearchResponse:
    filters = _parse(query)
    if not filters.understood:
        raise QueryNotUnderstoodError

    style = _style(filters)

    # Only this call is in the try, so a database error stays a 500.
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
        raise UnusableFiltersError(
            f"Couldn't understand the grade range in that query: {filters.min_grade}-{filters.max_grade}"
        )

    return NaturalSearchResponse(parsed_filters=filters, results=results)
