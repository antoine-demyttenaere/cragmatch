"""State of the trip planner graph (Stage 6, LangGraph).

The state is the one dict every node reads and writes. A node returns only the
keys it changes (a partial update) and LangGraph merges that into the state;
the keys it leaves out keep their value.

By default a new value replaces the old one. A reducer says "combine instead":
`Annotated[list[int], operator.add]` appends to the list rather than
overwriting it. `rejections` is the first one.

The state must be plain data (ids, strings, numbers, lists, dicts) because the
checkpointer saves it between steps. Things that are not data, like the
database session, travel in the runtime context (PlannerContext).
"""

import operator
from dataclasses import dataclass
from datetime import date
from typing import Annotated, TypedDict

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.stays import next_saturday


class MemberPrefs(TypedDict):
    # Same fields as the Preferences protocol in group_matching.py, so
    # SimpleNamespace(**prefs) can be passed to merge_preferences().
    name: str
    grade_min: str | None
    grade_max: str | None
    max_distance_km: float | None
    max_approach_minutes: int | None
    styles: list[str]


class Candidate(TypedDict):
    # The part of a GroupSectorMatch the planner needs: ids and values, no ORM row.
    sector_id: int
    sector_name: str
    crag_name: str
    style: str
    grade_min: str
    grade_max: str
    approach_minutes: int | None
    distance_km: float


class Rejection(TypedDict):
    sector_id: int
    reason: str


class Approval(BaseModel):
    """The group's answer, i.e. the resume value.

    Validated by `interrupt(response_schema=Approval)` and never stored in the state.
    """

    approved: bool
    reason: str | None = None


class TripPlan(TypedDict):
    # Written by propose_plan.
    sector: Candidate
    checkin: str
    checkout: str
    nights: int
    guests: int
    stays: list[dict]
    links: dict[str, str]


class TripState(TypedDict, total=False):
    # total=False: nodes fill the state in over time.
    share_code: str  # the caller (initial state)
    checkin: str  # the caller; an ISO date string, plain data for the checkpointer
    nights: int  # the caller
    guests: int  # the caller, or merge_preferences (number of members) when not set
    members: list[MemberPrefs]  # merge_preferences
    filters: dict | None  # merge_preferences (asdict(SearchFilters)); None = no common ground
    conflicts: list[str]  # merge_preferences
    candidates: list[Candidate]  # search_sectors
    chosen_sector: Candidate | None  # pick_sector
    # The first reducer, written by approve_sector. A node returns only the *new*
    # rejection and operator.add appends it to the list instead of replacing it.
    rejections: Annotated[list[Rejection], operator.add]
    approved: bool | None  # approve_sector
    stays: list[dict]  # find_stays (NearbyStay dumped to JSON-safe dicts)
    plan: TripPlan | None  # propose_plan
    # Why there's no plan, for the group: explain_conflicts, search_sectors (no
    # match), pick_sector (nothing left to propose) and propose_plan
    message: str | None


@dataclass
class PlannerContext:
    """Runtime context, given to every node as `runtime.context`.

    Never saved by the checkpointer, so it has to be passed again on every
    `invoke`, including a resume.
    """

    db: Session


def initial_state(
    share_code: str,
    checkin: date | None = None,
    nights: int = 2,
    guests: int | None = None,
) -> TripState:
    # Same defaults as GET /groups/{code}/sectors/{id}/stays; upper() like get_group.
    state: TripState = {
        "share_code": share_code.upper(),
        "checkin": (checkin or next_saturday()).isoformat(),
        "nights": nights,
    }
    if guests is not None:
        state["guests"] = guests
    return state
