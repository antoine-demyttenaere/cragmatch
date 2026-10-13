import json
from datetime import date

from langgraph.graph import END, START, StateGraph

from app.agent.state import PlannerContext, TripState, initial_state
from app.services.stays import next_saturday


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
