import json

import pytest
from langgraph.runtime import Runtime

from app.agent import nodes
from app.agent.nodes import (
    explain_conflicts,
    find_stays,
    merge_group_preferences,
    search_sectors,
)
from app.agent.state import PlannerContext, initial_state
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


def test_search_returns_candidates_best_first_and_picks_the_top(db_session, make_group, make_sector):
    group = make_group(members=[{"name": "Ana", "grade_min": "6a", "grade_max": "7a"}])
    make_sector("Far", "6a", "7a", **SIURANA)
    make_sector("Near", "6a", "7a")
    make_sector("Hard", "7c", "8b")
    state = initial_state(group.share_code)
    state.update(merge_group_preferences(state, runtime(db_session)))

    update = search_sectors(state, runtime(db_session))

    assert [c["sector_name"] for c in update["candidates"]] == ["Near", "Far"]
    assert update["chosen_sector"] == update["candidates"][0]
    assert update["chosen_sector"]["crag_name"] == "Montserrat"
    assert update["chosen_sector"]["style"] == "sport"
    json.dumps(update)


def test_search_without_matching_sectors_chooses_nothing(db_session, make_group, make_sector):
    group = make_group(members=[{"name": "Ana", "grade_min": "6a", "grade_max": "7a"}])
    make_sector("Hard", "7c", "8b")
    state = initial_state(group.share_code)
    state.update(merge_group_preferences(state, runtime(db_session)))

    update = search_sectors(state, runtime(db_session))

    assert update["candidates"] == []
    assert update["chosen_sector"] is None


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


def chosen_state(sector) -> dict:
    return {
        "chosen_sector": {
            "sector_id": sector.id,
            "sector_name": sector.name,
            "crag_name": "Montserrat",
            "style": "sport",
            "grade_min": "6a",
            "grade_max": "7a",
            "approach_minutes": None,
            "distance_km": 37.0,
        }
    }


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
