import json
from datetime import date

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import find_stays, merge_group_preferences, search_sectors
from app.agent.state import PlannerContext, TripState, initial_state
from app.services.stays import next_saturday


MERGE = ("merge_preferences", merge_group_preferences)
SEARCH = ("search_sectors", search_sectors)
STAYS = ("find_stays", find_stays)


def run_line(db, share_code, *nodes):
    # Node names are the ones the plans and the playground use, not the function names.
    builder = StateGraph(TripState, context_schema=PlannerContext)
    previous = START
    for name, node in nodes:
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
