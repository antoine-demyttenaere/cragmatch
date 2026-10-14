"""Run logic of the trip planner, shared by the HTTP router and the terminal script.

The graph lives in app/agent/. This module starts a run, advances it, answers
it and turns a checkpoint into a response. Nothing here knows about HTTP.
"""

from datetime import date
from uuid import UUID

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.state import PlannerContext, initial_state
from app.models import Group, PlannerRun
from app.schemas.planner import (
    PlannerAnswer,
    PlannerEdge,
    PlannerGraphRead,
    PlannerRunRead,
    PlannerRunStart,
)

# The node that calls interrupt(): a run is waiting for an answer when the graph
# is stopped right before (re-running) it.
APPROVAL_NODE = "approve_sector"
INTERRUPT_KEY = "__interrupt__"


class RunNotWaiting(Exception):
    """The run is not waiting for this answer: it finished, or someone answered first
    (the proposal being answered is no longer the one waiting)."""


def thread_config(run: PlannerRun) -> dict:
    return {"configurable": {"thread_id": str(run.id)}}


def advance(
    graph: CompiledStateGraph, graph_input, config: dict, context: PlannerContext
) -> list[dict]:
    """Run the graph until it ends or pauses, and return the trace steps in order."""
    steps: list[dict] = []
    for chunk in graph.stream(graph_input, config, context=context, stream_mode="updates"):
        for node, update in chunk.items():
            if node == INTERRUPT_KEY:
                continue  # the pause itself, not a node that ran
            steps.append({"node": node, "changed": list(update) if update else []})
    return steps


def start_run(
    db: Session, graph: CompiledStateGraph, group: Group, start: PlannerRunStart
) -> PlannerRun:
    run = PlannerRun(group_id=group.id, trace=[])
    db.add(run)
    db.flush()  # the id is the thread id, and the nodes read the group through db
    state = initial_state(group.share_code, start.checkin, start.nights, start.guests)
    run.trace = advance(graph, state, thread_config(run), PlannerContext(db=db))
    db.commit()
    db.refresh(run)
    return run


def _waits_for(snapshot: StateSnapshot, sector_id: int | None) -> bool:
    """Is the run paused at the approval step, on this sector (any sector if None)?"""
    if snapshot.next != (APPROVAL_NODE,):
        return False
    if sector_id is None:
        return True
    return snapshot.values["chosen_sector"]["sector_id"] == sector_id


def answer_run(
    db: Session, graph: CompiledStateGraph, run: PlannerRun, answer: PlannerAnswer
) -> PlannerRun:
    # Lock the row: two friends answering at once are served one after the other,
    # and the second finds the run no longer waiting for its sector.
    db.refresh(run, with_for_update=True)
    config = thread_config(run)
    if not _waits_for(graph.get_state(config), answer.sector_id):
        db.rollback()
        raise RunNotWaiting()

    # The resume value stays exactly an Approval: sector_id only guards the call.
    resume = answer.model_dump(exclude={"sector_id"})
    steps = advance(graph, Command(resume=resume), config, PlannerContext(db=db))
    # A new list, so SQLAlchemy sees the JSONB column change.
    run.trace = [*run.trace, *steps]
    db.commit()
    db.refresh(run)
    return run


def find_run(db: Session, group: Group, run_id: UUID) -> PlannerRun | None:
    # Both ids: a run id alone would let group B read group A's run.
    return db.scalars(
        select(PlannerRun).where(PlannerRun.id == run_id, PlannerRun.group_id == group.id)
    ).first()


def latest_run(db: Session, group: Group) -> PlannerRun | None:
    return db.scalars(
        select(PlannerRun)
        .where(PlannerRun.group_id == group.id)
        .order_by(PlannerRun.created_at.desc())
    ).first()


def run_view(graph: CompiledStateGraph, run: PlannerRun) -> PlannerRunRead:
    snapshot = graph.get_state(thread_config(run))
    values = snapshot.values

    waiting = snapshot.next == (APPROVAL_NODE,)
    if waiting:
        status = "waiting_for_approval"
    elif values.get("plan"):
        status = "planned"
    else:
        status = "no_plan"

    return PlannerRunRead(
        run_id=run.id,
        share_code=values["share_code"],
        status=status,
        checkin=date.fromisoformat(values["checkin"]),
        nights=values["nights"],
        guests=values.get("guests"),
        proposal=values.get("chosen_sector") if waiting else None,
        plan=values.get("plan"),
        message=values.get("message"),
        rejections=values.get("rejections", []),
        trace=run.trace,
        created_at=run.created_at,
    )


def graph_structure(graph: CompiledStateGraph) -> PlannerGraphRead:
    drawable = graph.get_graph()
    return PlannerGraphRead(
        nodes=list(drawable.nodes),
        edges=[
            PlannerEdge(source=edge.source, target=edge.target, conditional=edge.conditional)
            for edge in drawable.edges
        ],
    )
