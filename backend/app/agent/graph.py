"""The trip planner graph (Stage 6, LangGraph).

A normal edge, add_edge(a, b), always goes from a to b. A conditional edge,
add_conditional_edges(a, route, [...]), calls route(state) after a has run and
goes to the node whose name route returns. Here that decides whether a group
with no common ground still gets a search, whether a sector was proposed at
all, and whether the group's answer sends the run on or back to pick_sector.

A routing function must be pure: read the state, return a name, no I/O and no
writes. LangGraph may call it again when it replays or resumes a run, so its
decision has to follow from the saved state alone; that is also what makes a
run repeatable and the function testable on its own. Anything with side
effects belongs in a node, whose output is recorded in the state.

Pausing
-------
The checkpointer saves the state after every step, under the run's thread_id.
interrupt() inside approve_sector stops the node: LangGraph saves a checkpoint
with the pending question and `invoke` returns. "Paused" means the Python call
has finished and nothing keeps running; only the saved checkpoint is left.

A resume is a new `invoke(Command(resume=...))` with the same thread_id.
LangGraph loads the last checkpoint, skips the steps that already ran and
re-runs the interrupted node from its first line; this time interrupt()
returns the answer. So nothing before interrupt() may have side effects.

The state must be serializable because the checkpointer stores it (in memory
here, a database in Stage 7). The context (the db session) isn't stored, so it
is passed again on every call, resumes included.

compile(interrupt_before=["find_stays"]) would also stop the graph, but the
answer would have to be written in with update_state() by the caller, and the
approve/reject branch would be split between caller and graph. interrupt()
sends the question out, gets the answer back as a return value and keeps the
branch inside the graph. Static interrupts are mainly for debugging a graph.
"""

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from app.agent.nodes import (
    approve_sector,
    explain_conflicts,
    find_stays,
    merge_group_preferences,
    pick_sector,
    propose_plan,
    search_sectors,
)
from app.agent.state import PlannerContext, TripState


def route_after_merge(state: TripState) -> Literal["search_sectors", "explain_conflicts"]:
    # filters is None exactly when the group has no common ground (or no members).
    return "search_sectors" if state.get("filters") is not None else "explain_conflicts"


def route_after_pick(state: TripState) -> Literal["approve_sector", "__end__"]:
    # pick_sector sets chosen_sector to None when there is nothing (left) to propose.
    return "approve_sector" if state.get("chosen_sector") else END


def route_after_approval(state: TripState) -> Literal["find_stays", "pick_sector"]:
    return "find_stays" if state.get("approved") else "pick_sector"


def build_trip_planner(checkpointer: Checkpointer = None) -> CompiledStateGraph:
    # Without a checkpointer a run with common ground can't pause: interrupt() needs one.
    builder = StateGraph(TripState, context_schema=PlannerContext)
    builder.add_node("merge_preferences", merge_group_preferences)
    builder.add_node("search_sectors", search_sectors)
    builder.add_node("pick_sector", pick_sector)
    builder.add_node("approve_sector", approve_sector)
    builder.add_node("find_stays", find_stays)
    builder.add_node("propose_plan", propose_plan)
    builder.add_node("explain_conflicts", explain_conflicts)

    builder.add_edge(START, "merge_preferences")
    # The explicit lists are what make the branches visible in the diagram.
    builder.add_conditional_edges(
        "merge_preferences", route_after_merge, ["search_sectors", "explain_conflicts"]
    )
    builder.add_edge("search_sectors", "pick_sector")
    builder.add_conditional_edges("pick_sector", route_after_pick, ["approve_sector", END])
    builder.add_conditional_edges(
        "approve_sector", route_after_approval, ["find_stays", "pick_sector"]
    )
    builder.add_edge("find_stays", "propose_plan")
    builder.add_edge("propose_plan", END)
    builder.add_edge("explain_conflicts", END)
    return builder.compile(checkpointer=checkpointer)
