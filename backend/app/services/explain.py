from pydantic import BaseModel, Field

from app.models import Sector
from app.services.llm import LLM_MODEL, client


# The shape we ask Claude to return. These live here, not in schemas/,
# because they're never sent to API clients; they're only the format
# of Claude's answer inside this function.
class MatchReason(BaseModel):
    sector_id: int
    reason: str = Field(description="One short sentence explaining the match.")


class MatchReasons(BaseModel):
    reasons: list[MatchReason]


EXPLAIN_PROMPT = """You explain why climbing sectors match a user's search.
You get the search text and a list of sectors, each with an id and its details.
For every sector, write ONE short sentence (max ~20 words) saying why it fits
the search. Use ONLY the details given for that sector; do not add facts from
your own knowledge about these places. If a sector only partly fits, say so
honestly (e.g. "Short approach, but it can get crowded")."""


def _describe(sector: Sector) -> str:
    return f"id={sector.id} | {sector.name} ({sector.crag.name}) | {sector.style.value} | {sector.grade_min} to {sector.grade_max} | {sector.approach_notes}"


def explain_matches(query: str, sectors: list[Sector]) -> dict[int, str]:
    if not sectors:
        return {}

    sector_lines = "\n".join(_describe(s) for s in sectors)
    user_message = f"Search: {query}\n\nSectors:\n{sector_lines}"

    response = client.messages.parse(
        model=LLM_MODEL,
        max_tokens=1024,
        system=EXPLAIN_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        output_format=MatchReasons,
    )

    log_usage("explain", response)

    reasons = response.parsed_output.reasons
    return {reason.sector_id: reason.reason for reason in reasons}

