from pydantic import BaseModel, Field

from app.schemas.sector import SectorRead


class NaturalSearchRequest(BaseModel):
    query: str


class ParsedFilters(BaseModel):
    understood: bool = Field(
        description=(
            "False if the query has no discernible connection to a "
            "climbing search — no grade, location, or style "
            "signal at all (e.g. off-topic, gibberish, or a completely "
            "unrelated question). True otherwise, even for vague queries "
            "like 'something easy near Barcelona'."
        )
    )
    min_grade: str = Field(description="Easiest French grade, e.g. '6a'.")
    max_grade: str = Field(description="Hardest French grade, e.g. '7a'.")
    max_distance_km: float = Field(description="Estimated straight-line km from Barcelona.")
    style: str | None = Field(default=None, description="Climbing style, or null.")


class NaturalSearchResponse(BaseModel):
    parsed_filters: ParsedFilters
    results: list[SectorRead]


class SimilarSearchRequest(BaseModel):
    query: str = Field(description="Free-text description, e.g. 'quiet crag, short approach'.")
    limit: int = Field(default=5, ge=1, le=20, description="How many sectors to return.")


class SimilarMatch(BaseModel):
    sector: SectorRead
    similarity: float = Field(description="1 - cosine distance; closer to 1 is more similar.")


class SimilarSearchResponse(BaseModel):
    results: list[SimilarMatch]
