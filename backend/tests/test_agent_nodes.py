import ast
import json
from pathlib import Path

import pytest
from langgraph.runtime import Runtime

from app.agent import nodes
from app.agent.nodes import (
    approve_sector,
    explain_conflicts,
    find_stays,
    merge_group_preferences,
    pick_sector,
    propose_plan,
    search_sectors,
)
from app.agent.state import Approval, PlannerContext, initial_state
from app.schemas.group import GroupSearchResponse

AGREEING = [
    {"name": "Ana", "grade_min": "6a", "grade_max": "7a", "max_distance_km": 100},
    {"name": "Marc", "grade_min": "6b", "grade_max": "7b", "max_distance_km": 80},
]
DISAGREEING = [
    {"name": "Ana", "grade_min": "5", "grade_max": "6a"},
    {"name": "Marc", "grade_min": "7a", "grade_max": "8a"},
]
SIURANA = {"lat": 41.26, "lon": 0.93, "crag": "Siurana"}


def runtime(db) -> Runtime[PlannerContext]:
    return Runtime(context=PlannerContext(db=db))


def test_merge_writes_filters_for_a_group_that_agrees(db_session, make_group):
    group = make_group(members=AGREEING)

    update = merge_group_preferences(initial_state(group.share_code), runtime(db_session))

    assert update["filters"] == {
        "grade_min": "6b",
        "grade_max": "7a",
        "max_distance_km": 80,
        "max_approach_minutes": None,
        "styles": None,
    }
    assert update["conflicts"] == []
    assert len(update["members"]) == 2
    assert update["guests"] == 2


def test_merge_writes_conflicts_when_there_is_no_common_ground(db_session, make_group):
    group = make_group(members=DISAGREEING)

    update = merge_group_preferences(initial_state(group.share_code), runtime(db_session))

    assert update["filters"] is None
    assert len(update["conflicts"]) == 1
    assert "Ana" in update["conflicts"][0]
    assert "Marc" in update["conflicts"][0]


def test_merge_keeps_guests_set_by_the_caller(db_session, make_group):
    group = make_group(members=AGREEING)

    update = merge_group_preferences(initial_state(group.share_code, guests=6), runtime(db_session))

    assert "guests" not in update


def test_merge_returns_only_its_own_keys(db_session, make_group):
    group = make_group(members=AGREEING)

    update = merge_group_preferences(initial_state(group.share_code), runtime(db_session))

    assert set(update) <= {"members", "filters", "conflicts", "guests"}


def test_merge_unknown_share_code_raises_value_error(db_session):
    with pytest.raises(ValueError, match="NOPE"):
        merge_group_preferences(initial_state("nope"), runtime(db_session))


def test_merge_group_without_members_is_a_conflict(db_session, make_group):
    group = make_group(members=[])

    update = merge_group_preferences(initial_state(group.share_code), runtime(db_session))

    assert update["filters"] is None
    assert update["conflicts"] == ["The group has no members yet."]
    assert update["guests"] == 1


def test_search_returns_candidates_best_first(db_session, make_group, make_sector):
    group = make_group(members=[{"name": "Ana", "grade_min": "6a", "grade_max": "7a"}])
    make_sector("Far", "6a", "7a", **SIURANA)
    make_sector("Near", "6a", "7a")
    make_sector("Hard", "7c", "8b")
    state = initial_state(group.share_code)
    state.update(merge_group_preferences(state, runtime(db_session)))

    update = search_sectors(state, runtime(db_session))

    assert [c["sector_name"] for c in update["candidates"]] == ["Near", "Far"]
    assert update["candidates"][0]["crag_name"] == "Montserrat"
    assert update["candidates"][0]["style"] == "sport"
    assert "chosen_sector" not in update
    json.dumps(update)


def test_search_without_matching_sectors_chooses_nothing(db_session, make_group, make_sector):
    group = make_group(members=[{"name": "Ana", "grade_min": "6a", "grade_max": "7a"}])
    make_sector("Hard", "7c", "8b")
    state = initial_state(group.share_code)
    state.update(merge_group_preferences(state, runtime(db_session)))

    update = search_sectors(state, runtime(db_session))

    assert update["candidates"] == []
    assert "chosen_sector" not in update
    assert update["message"] == "The group agrees on filters, but no sector matches them."


def test_search_calls_the_group_search_service(db_session, make_group, monkeypatch):
    group = make_group(members=AGREEING)
    state = initial_state(group.share_code)
    state.update(merge_group_preferences(state, runtime(db_session)))
    calls = []

    def spy(db, members, mode, fit):
        calls.append((mode, fit, [m.name for m in members]))
        return GroupSearchResponse(
            mode=mode, fit=fit, member_count=len(members), common_ground=True, results=[]
        )

    monkeypatch.setattr(nodes, "search_for_group", spy)

    search_sectors(state, runtime(db_session))

    assert calls == [("strict", "overlap", ["Ana", "Marc"])]


def candidate(sector_id: int, name: str = "Sector") -> dict:
    return {
        "sector_id": sector_id,
        "sector_name": name,
        "crag_name": "Montserrat",
        "style": "sport",
        "grade_min": "6a",
        "grade_max": "7a",
        "approach_minutes": None,
        "distance_km": 37.0,
    }


def chosen_state(sector) -> dict:
    return {"chosen_sector": candidate(sector.id, sector.name)}


def rejection(sector_id: int) -> dict:
    return {"sector_id": sector_id, "reason": "no"}


def test_pick_sector_takes_the_first_candidate():
    state = {"candidates": [candidate(1), candidate(2)]}

    update = pick_sector(state)

    assert update == {"chosen_sector": candidate(1), "approved": None}


def test_pick_sector_skips_rejected_sectors():
    state = {
        "candidates": [candidate(1), candidate(2), candidate(3)],
        "rejections": [rejection(1)],
    }

    update = pick_sector(state)

    assert update["chosen_sector"]["sector_id"] == 2


def test_pick_sector_stops_after_three_rejections():
    state = {
        "candidates": [candidate(i) for i in range(1, 6)],
        "rejections": [rejection(1), rejection(2), rejection(3)],
    }

    update = pick_sector(state)

    assert update["chosen_sector"] is None
    assert update["message"] == "No plan: the group turned down 3 sectors."


def test_pick_sector_with_nothing_left_keeps_the_search_message():
    state = {
        "candidates": [candidate(1)],
        "rejections": [rejection(1)],
        "message": "The group agrees on filters, but no sector matches them.",
    }

    update = pick_sector(state)

    assert update["chosen_sector"] is None
    assert update["message"] == "The group agrees on filters, but no sector matches them."


def test_approve_sector_records_a_rejection(monkeypatch):
    monkeypatch.setattr(nodes, "interrupt", lambda *a, **k: Approval(approved=False, reason="x"))

    update = approve_sector({"chosen_sector": candidate(7)})

    assert update == {"approved": False, "rejections": [{"sector_id": 7, "reason": "x"}]}


def test_approve_sector_records_an_approval(monkeypatch):
    monkeypatch.setattr(nodes, "interrupt", lambda *a, **k: Approval(approved=True))

    update = approve_sector({"chosen_sector": candidate(7)})

    assert update == {"approved": True}


def test_propose_plan_has_dates_guests_stays_and_links(db_session, make_sector):
    sector = make_sector("Near", "6a", "7a")
    state = {
        **chosen_state(sector),
        "checkin": "2026-11-07",
        "nights": 2,
        "guests": 3,
        "stays": [{"stay": {"name": "Close"}, "distance_km": 1.0}],
    }

    update = propose_plan(state, runtime(db_session))

    plan = update["plan"]
    assert plan["checkout"] == "2026-11-09"
    assert plan["guests"] == 3
    assert plan["sector"]["sector_id"] == sector.id
    assert plan["stays"] == state["stays"]
    assert "checkin=2026-11-07" in plan["links"]["airbnb"]
    assert "adults=3" in plan["links"]["airbnb"]
    assert "group_adults=3" in plan["links"]["booking"]
    assert update["message"] is None
    json.dumps(plan)


def test_find_stays_returns_closest_stays_as_plain_dicts(db_session, make_sector, make_stay):
    sector = make_sector("Near", "6a", "7a")
    make_stay("Mid", 41.64, 1.81)
    make_stay("Close", 41.61, 1.82)
    make_stay("Far", 41.87, 1.81)

    update = find_stays(chosen_state(sector), runtime(db_session))

    assert [s["stay"]["name"] for s in update["stays"]] == ["Close", "Mid"]
    assert update["stays"][0]["stay"]["type"] == "campsite"
    json.dumps(update)


def test_find_stays_keeps_at_most_five(db_session, make_sector, make_stay):
    sector = make_sector("Near", "6a", "7a")
    for i in range(7):
        make_stay(f"Stay {i}", 41.60 + i * 0.005, 1.81)

    update = find_stays(chosen_state(sector), runtime(db_session))

    assert len(update["stays"]) == 5


def test_find_stays_without_a_chosen_sector_is_empty(db_session):
    update = find_stays({"chosen_sector": None}, runtime(db_session))

    assert update == {"stays": []}


def test_explain_conflicts_joins_the_conflicts_into_a_message():
    state = {"conflicts": ["No grade everyone climbs: Ana vs Marc.", "Second problem."]}

    update = explain_conflicts(state)

    assert update == {
        "message": "No common ground, so no search: "
        "No grade everyone climbs: Ana vs Marc. Second problem."
    }


def test_agent_package_imports_no_network_client():
    """The planner must stay offline; a Claude step would need its own mocked tests first.

    Since ticket 014 the clients live in app.rag; the two app.services model-name
    modules stay on the list because a node that needs a model name is about to
    call a model.
    """
    forbidden = (
        "anthropic", "voyageai", "httpx", "langchain_anthropic", "langchain_voyageai",
        "app.rag", "app.services.llm", "app.services.embedding", "app.services.overpass",
    )
    imported = []
    for path in Path(nodes.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported += [(path.name, alias.name) for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append((path.name, node.module))

    offenders = [
        (file, module) for file, module in imported
        if any(module == bad or module.startswith(bad + ".") for bad in forbidden)
    ]
    assert offenders == []
