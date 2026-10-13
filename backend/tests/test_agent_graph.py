import copy
import json
from datetime import date

from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.graph import build_trip_planner, route_after_merge
from app.agent.nodes import find_stays, merge_group_preferences, search_sectors
from app.agent.state import PlannerContext, TripState, initial_state
from app.services.stays import next_saturday


MERGE = ("merge_preferences", merge_group_preferences)
SEARCH = ("search_sectors", search_sectors)
STAYS = ("find_stays", find_stays)


def run_line(db, share_code, *steps):
    # Node names are the ones the plans and the playground use, not the function names.
    builder = StateGraph(TripState, context_schema=PlannerContext)
    previous = START
    for name, node in steps:
        builder.add_node(name, node)
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    return builder.compile().invoke(initial_state(share_code), context=PlannerContext(db=db))


def test_initial_state_defaults_to_next_saturday_and_two_nights():
    state = initial_state("ab12")

    assert state["share_code"] == "AB12"
    assert state["nights"] == 2
    assert state["checkin"] == next_saturday().isoformat()
    assert "guests" not in state


def test_initial_state_is_plain_json():
    # Guard for "no ORM objects in the state": the checkpointer needs plain data.
    json.dumps(initial_state("x", date(2026, 11, 7), 3, 4))


def test_empty_graph_returns_the_initial_state():
    builder = StateGraph(TripState, context_schema=PlannerContext)
    builder.add_edge(START, END)
    graph = builder.compile()
    state = initial_state("ab12", date(2026, 11, 7))

    result = graph.invoke(state, context=PlannerContext(db=None))

    assert result == state


MEMBER = {"name": "Ana", "grade_min": "6a", "grade_max": "7a"}


def test_line_merge_then_search_keeps_merge_fields(db_session, make_group, make_sector):
    group = make_group(members=[MEMBER])
    make_sector("Near", "6a", "7a")

    result = run_line(db_session, group.share_code, MERGE, SEARCH)

    assert result["filters"] is not None
    assert len(result["members"]) == 1
    assert [c["sector_name"] for c in result["candidates"]] == ["Near"]


def test_line_of_three_nodes_ends_with_stays(db_session, make_group, make_sector, make_stay):
    group = make_group(members=[MEMBER])
    make_sector("Near", "6a", "7a")
    make_stay("Close", 41.61, 1.82)

    result = run_line(db_session, group.share_code, MERGE, SEARCH, STAYS)

    assert result["filters"] is not None
    assert len(result["candidates"]) == 1
    assert result["chosen_sector"]["sector_name"] == "Near"
    assert [s["stay"]["name"] for s in result["stays"]] == ["Close"]


def test_route_after_merge_goes_to_search_when_filters_exist():
    assert route_after_merge({"filters": {"grade_min": "6a"}}) == "search_sectors"


def test_route_after_merge_goes_to_explain_conflicts_without_filters():
    assert route_after_merge({"filters": None}) == "explain_conflicts"


def test_route_after_merge_does_not_change_the_state():
    state = {"filters": None, "conflicts": ["x"], "members": [{"name": "Ana"}]}
    before = copy.deepcopy(state)

    route_after_merge(state)

    assert state == before


AGREEING = [
    {"name": "Ana", "grade_min": "6a", "grade_max": "7a"},
    {"name": "Marc", "grade_min": "6b", "grade_max": "7b"},
]
DISAGREEING = [
    {"name": "Ana", "grade_min": "5", "grade_max": "6a"},
    {"name": "Marc", "grade_min": "7a", "grade_max": "8a"},
]


def node_names(graph, db, share_code):
    updates = graph.stream(
        initial_state(share_code), context=PlannerContext(db=db), stream_mode="updates"
    )
    return [name for update in updates for name in update]


def test_graph_with_common_ground_runs_merge_search_stays(db_session, make_group, make_sector, make_stay):
    group = make_group(members=AGREEING)
    make_sector("Near", "6a", "7a")
    make_stay("Close", 41.61, 1.82)
    graph = build_trip_planner()

    names = node_names(graph, db_session, group.share_code)
    result = graph.invoke(initial_state(group.share_code), context=PlannerContext(db=db_session))

    assert names == ["merge_preferences", "search_sectors", "find_stays"]
    assert result == run_line(db_session, group.share_code, MERGE, SEARCH, STAYS)
    assert [s["stay"]["name"] for s in result["stays"]] == ["Close"]


def test_graph_without_common_ground_skips_search_and_stays(
    db_session, make_group, make_sector, make_stay, monkeypatch
):
    group = make_group(members=DISAGREEING)
    make_sector("Near", "6a", "7a")
    make_stay("Close", 41.61, 1.82)
    calls = []
    monkeypatch.setattr(nodes, "search_for_group", lambda *a, **k: calls.append("search"))
    monkeypatch.setattr(nodes, "find_stays_near", lambda *a, **k: calls.append("stays"))
    graph = build_trip_planner()

    names = node_names(graph, db_session, group.share_code)
    result = graph.invoke(initial_state(group.share_code), context=PlannerContext(db=db_session))

    assert names == ["merge_preferences", "explain_conflicts"]
    assert "candidates" not in result
    assert "stays" not in result
    assert "No grade everyone climbs" in result["message"]
    assert calls == []


def test_diagram_shows_the_branch():
    diagram = build_trip_planner().get_graph().draw_mermaid()

    assert "explain_conflicts" in diagram
    assert "search_sectors" in diagram
    assert "-." in diagram
