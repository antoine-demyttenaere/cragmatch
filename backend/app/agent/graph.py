"""The trip planner graph (Stage 6, LangGraph).

A normal edge, add_edge(a, b), always goes from a to b. A conditional edge,
add_conditional_edges(a, route, [...]), calls route(state) after a has run and
goes to the node whose name route returns. Here that decides whether a group
with no common ground still gets a search.

A routing function must be pure: read the state, return a name, no I/O and no
writes. LangGraph may call it again when it replays or resumes a run (ticket
010), so its decision has to follow from the saved state alone; that is also
what makes a run repeatable and the function testable on its own. Anything
with side effects belongs in a node, whose output is recorded in the state.
"""

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from app.agent.nodes import (
    explain_conflicts,
    find_stays,
    merge_group_preferences,
    search_sectors,
)
from app.agent.state import PlannerContext, TripState


def route_after_merge(state: TripState) -> Literal["search_sectors", "explain_conflicts"]:
    # filters is None exactly when the group has no common ground (or no members).
    return "search_sectors" if state.get("filters") is not None else "explain_conflicts"


def build_trip_planner(checkpointer: Checkpointer = None) -> CompiledStateGraph:
    # checkpointer is unused until ticket 010.
    builder = StateGraph(TripState, context_schema=PlannerContext)
    builder.add_node("merge_preferences", merge_group_preferences)
    builder.add_node("search_sectors", search_sectors)
    builder.add_node("find_stays", find_stays)
    builder.add_node("explain_conflicts", explain_conflicts)

    builder.add_edge(START, "merge_preferences")
    # The explicit list is what makes both branches visible in the diagram.
    builder.add_conditional_edges(
        "merge_preferences", route_after_merge, ["search_sectors", "explain_conflicts"]
    )
    builder.add_edge("search_sectors", "find_stays")
    builder.add_edge("find_stays", END)
    builder.add_edge("explain_conflicts", END)
    return builder.compile(checkpointer=checkpointer)
