import copy
import json
from datetime import date
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agent import nodes
from app.agent.graph import build_trip_planner, route_after_merge
from app.agent.nodes import (
    find_stays,
    merge_group_preferences,
    pick_sector,
    search_sectors,
)
from app.agent.state import PlannerContext, TripState, initial_state
from app.services.stays import next_saturday


MERGE = ("merge_preferences", merge_group_preferences)
SEARCH = ("search_sectors", search_sectors)
PICK = ("pick_sector", pick_sector)
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

    # A reducer field starts as an empty list even if no node writes it.
    assert result == {**state, "rejections": []}


MEMBER = {"name": "Ana", "grade_min": "6a", "grade_max": "7a"}


def test_line_merge_then_search_keeps_merge_fields(db_session, make_group, make_sector):
    group = make_group(members=[MEMBER])
    make_sector("Near", "6a", "7a")

    result = run_line(db_session, group.share_code, MERGE, SEARCH)

    assert result["filters"] is not None
    assert len(result["members"]) == 1
    assert [c["sector_name"] for c in result["candidates"]] == ["Near"]


def test_line_of_four_nodes_ends_with_stays(db_session, make_group, make_sector, make_stay):
    group = make_group(members=[MEMBER])
    make_sector("Near", "6a", "7a")
    make_stay("Close", 41.61, 1.82)

    result = run_line(db_session, group.share_code, MERGE, SEARCH, PICK, STAYS)

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
    graph = build_trip_planner(InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}}
    context = PlannerContext(db=db_session)

    # The first stream stops at the pause; the resume carries approve_sector's update.
    first = graph.stream(
        initial_state(group.share_code), config, context=context, stream_mode="updates"
    )
    second = graph.stream(
        Command(resume={"approved": True}), config, context=context, stream_mode="updates"
    )
    updates = [u for u in [*first, *second] if "__interrupt__" not in u]
    names = [name for update in updates for name in update]
    result = graph.get_state(config).values

    assert names == [
        "merge_preferences",
        "search_sectors",
        "pick_sector",
        "approve_sector",
        "find_stays",
        "propose_plan",
    ]
    line = run_line(db_session, group.share_code, MERGE, SEARCH, PICK, STAYS)
    for key in ("filters", "candidates", "stays"):
        assert result[key] == line[key]
    assert result["plan"]["sector"]["sector_name"] == "Near"
    assert [s["stay"]["name"] for s in result["plan"]["stays"]] == ["Close"]


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


@pytest.fixture()
def call_counts(monkeypatch):
    # Counting wrappers around the real functions, installed before any invoke.
    counts = {"merge": 0, "search": 0}
    real_find_group = nodes.find_group
    real_search = nodes.search_for_group

    def counting_find_group(*args, **kwargs):
        counts["merge"] += 1
        return real_find_group(*args, **kwargs)

    def counting_search(*args, **kwargs):
        counts["search"] += 1
        return real_search(*args, **kwargs)

    monkeypatch.setattr(nodes, "find_group", counting_find_group)
    monkeypatch.setattr(nodes, "search_for_group", counting_search)
    return counts


@pytest.fixture()
def paused_run(db_session, make_group, make_sector, make_stay, call_counts):
    # Two matching sectors at different crags (Near is closer to Barcelona), a stay near each.
    group = make_group(members=AGREEING)
    make_sector("Near", "6a", "7a")
    make_sector("Far", "6a", "7a", lat=41.26, lon=0.93, crag="Siurana")
    make_stay("Close", 41.61, 1.82)
    make_stay("Siurana camp", 41.27, 0.94)
    graph = build_trip_planner(InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}}
    context = PlannerContext(db=db_session)

    first_output = graph.invoke(initial_state(group.share_code), config, context=context)
    return graph, config, context, first_output


def proposed_sector(output) -> dict:
    return output["__interrupt__"][0].value["sector"]


def test_run_pauses_at_approval_with_the_proposed_sector(paused_run):
    _, _, _, output = paused_run

    assert "__interrupt__" in output
    assert proposed_sector(output)["sector_name"] == "Near"


def test_paused_state_has_the_sector_and_no_stays(paused_run):
    graph, config, _, _ = paused_run

    snapshot = graph.get_state(config)

    assert snapshot.next == ("approve_sector",)
    assert snapshot.values["chosen_sector"]["sector_name"] == "Near"
    assert "stays" not in snapshot.values
    assert "plan" not in snapshot.values


def test_approve_resumes_and_produces_a_plan(paused_run):
    graph, config, context, output = paused_run
    proposed = proposed_sector(output)

    result = graph.invoke(Command(resume={"approved": True}), config, context=context)

    assert "__interrupt__" not in result
    assert result["plan"]["sector"]["sector_id"] == proposed["sector_id"]
    assert result["plan"]["stays"]


def test_resume_does_not_run_merge_or_search_again(paused_run, call_counts):
    graph, config, context, _ = paused_run

    graph.invoke(Command(resume={"approved": True}), config, context=context)

    assert call_counts == {"merge": 1, "search": 1}


def test_reject_proposes_the_next_sector(paused_run):
    graph, config, context, output = paused_run
    first = proposed_sector(output)

    second_output = graph.invoke(
        Command(resume={"approved": False, "reason": "too far"}), config, context=context
    )

    assert proposed_sector(second_output)["sector_name"] == "Far"
    values = graph.get_state(config).values
    assert values["rejections"] == [{"sector_id": first["sector_id"], "reason": "too far"}]
    assert "stays" not in values
