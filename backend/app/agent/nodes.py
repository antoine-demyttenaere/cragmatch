"""Nodes of the trip planner graph (Stage 6, LangGraph).

Each node reads the state, calls an existing service and returns only the keys
it changes. No matching or search logic lives here: the services own it, so the
planner and the API can't drift apart.

LangGraph passes the runtime to any parameter named `runtime`; the database
session is `runtime.context.db`.
"""

from dataclasses import asdict
from datetime import date, timedelta
from types import SimpleNamespace

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy.orm import Session

from app.agent.state import (
    Approval,
    Candidate,
    MemberPrefs,
    PlannerContext,
    TripPlan,
    TripState,
) 
from app.models import Member, Sector
from app.schemas.group import GroupSectorMatch
from app.schemas.stay import BookingLinks, NearbyStay
from app.services.group_matching import FitMode, merge_preferences
from app.services.group_search import SearchMode, search_for_group
from app.services.groups import find_group
from app.services.stays import airbnb_url, booking_url, find_stays_near

# The planner proposes a sector *everyone* can climb, so strict; overlap is the
# app's default fit.
SEARCH_MODE: SearchMode = "strict"
FIT: FitMode = "overlap"

STAY_RADIUS_KM = 10  # the stays endpoint's default
MAX_STAYS = 5  # a plan is a shortlist, and the state stays readable
# The ticket's default: after three rejections the group should change its
# preferences, not keep clicking "no".
MAX_PROPOSALS = 3


def _member_prefs(member: Member) -> MemberPrefs:
    return {
        "name": member.name,
        "grade_min": member.grade_min,
        "grade_max": member.grade_max,
        "max_distance_km": member.max_distance_km,
        "max_approach_minutes": member.max_approach_minutes,
        "styles": list(member.styles),
    }


def _as_members(prefs: list[MemberPrefs]) -> list[SimpleNamespace]:
    # The services read attributes (the Preferences protocol), the state holds dicts.
    return [SimpleNamespace(**p) for p in prefs]


def _candidate(match: GroupSectorMatch) -> Candidate:
    sector = match.sector
    return {
        "sector_id": sector.id,
        "sector_name": sector.name,
        "crag_name": sector.crag.name,
        "style": sector.style.value,
        "grade_min": sector.grade_min,
        "grade_max": sector.grade_max,
        "approach_minutes": sector.approach_minutes,
        "distance_km": match.distance_km,
    }


def merge_group_preferences(state: TripState, runtime: Runtime[PlannerContext]) -> dict:
    group = find_group(runtime.context.db, state["share_code"])
    if group is None:
        # A wrong code is bad input, not "no result" (like find_matching_sectors).
        raise ValueError(f"No group with share code {state['share_code']}")

    members = [_member_prefs(m) for m in group.members]
    update: dict = {"members": members}
    # Same rule as the group stays endpoint: one guest per member, unless the caller said.
    if "guests" not in state:
        update["guests"] = max(len(members), 1)

    if not members:
        # merge_preferences([]) would say "no limits", but there's nobody to plan for.
        update["filters"] = None
        update["conflicts"] = ["The group has no members yet."]
        return update

    merged = merge_preferences(_as_members(members))
    update["filters"] = asdict(merged.filters) if merged.common_ground else None
    update["conflicts"] = merged.conflicts
    return update


def search_sectors(state: TripState, runtime: Runtime[PlannerContext]) -> dict:
    response = search_for_group(
        runtime.context.db, _as_members(state["members"]), SEARCH_MODE, FIT
    )
    candidates = [_candidate(m) for m in response.results]
    update: dict = {"candidates": candidates}
    if not response.results:
        update["message"] = response.message
    return update


def pick_sector(state: TripState) -> dict:
    # Pure: no DB, no runtime. It runs again after every rejection and reads the
    # rejections the state has collected.
    rejected = {r["sector_id"] for r in state.get("rejections", [])}
    if len(rejected) >= MAX_PROPOSALS:
        return {
            "chosen_sector": None,
            "message": f"No plan: the group turned down {len(rejected)} sectors.",
        }

    for candidate in state["candidates"]:
        if candidate["sector_id"] not in rejected:
            return {"chosen_sector": candidate, "approved": None}

    return {
        "chosen_sector": None,
        "message": state.get("message") or "No plan: every candidate was turned down.",
    }


def approve_sector(state: TripState) -> dict:
    chosen = state["chosen_sector"]
    # On resume this function runs again from the top, so nothing before
    # interrupt() may have side effects (no DB writes, no prints that matter).
    decision = interrupt(
        {"question": "Plan the trip around this sector?", "sector": chosen},
        response_schema=Approval,
    )
    if decision.approved:
        return {"approved": True}
    return {
        "approved": False,
        "rejections": [{"sector_id": chosen["sector_id"], "reason": decision.reason or ""}],
    }


def explain_conflicts(state: TripState) -> dict:
    # The conflict strings are already readable; wording them with Claude is out of
    # scope. No `runtime` parameter: LangGraph injects it only if it's declared.
    return {"message": "No common ground, so no search: " + " ".join(state["conflicts"])}


def _sector_with_crag(db: Session, sector_id: int) -> Sector | None:
    return db.get(Sector, sector_id)


def find_stays(state: TripState, runtime: Runtime[PlannerContext]) -> dict:
    chosen = state.get("chosen_sector")
    if chosen is None:
        return {"stays": []}

    db = runtime.context.db
    sector = _sector_with_crag(db, chosen["sector_id"])
    if sector is None:  # deleted since the search
        return {"stays": []}

    nearby = find_stays_near(
        db, sector.crag.latitude, sector.crag.longitude, STAY_RADIUS_KM
    )[:MAX_STAYS]
    return {
        "stays": [
            NearbyStay(stay=stay, distance_km=round(distance, 1)).model_dump(mode="json")
            for stay, distance in nearby
        ]
    }


def propose_plan(state: TripState, runtime: Runtime[PlannerContext]) -> dict:
    chosen = state["chosen_sector"]
    sector = _sector_with_crag(runtime.context.db, chosen["sector_id"])
    if sector is None:  # deleted while the group was deciding
        return {"plan": None, "message": "No plan: the chosen sector no longer exists."}

    crag = sector.crag
    checkin = date.fromisoformat(state["checkin"])
    checkout = checkin + timedelta(days=state["nights"])
    guests = state["guests"]
    # Same arguments as the group stays endpoint, so both give the same links.
    links = BookingLinks(
        airbnb=airbnb_url(crag.latitude, crag.longitude, checkin, checkout, guests),
        booking=booking_url(crag.name, crag.latitude, crag.longitude, checkin, checkout, guests),
    )
    plan: TripPlan = {
        "sector": chosen,
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "nights": state["nights"],
        "guests": guests,
        "stays": state["stays"],
        "links": links.model_dump(),
    }
    return {"plan": plan, "message": None}
