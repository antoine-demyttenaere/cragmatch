from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.agent.checkpointer import open_postgres_saver, psycopg_conninfo
from app.agent.graph import build_trip_planner
from app.core.config import settings
from app.core.dependencies import get_db
from app.models import Group, PlannerRun
from app.routers.groups import get_group
from app.schemas.planner import (
    PlannerAnswer,
    PlannerGraphRead,
    PlannerRunRead,
    PlannerRunStart,
)
from app.services import trip_planner

# No prefix: the routes span /groups/{code}/planner and /planner, so each one
# carries its full path. No rate limit: the planner calls no paid API.
router = APIRouter()


@lru_cache(maxsize=1)
def get_trip_planner() -> CompiledStateGraph:
    # Cached like get_vector_store(): the pool and the table set-up happen once per
    # process, on the first planner request. Tests override this dependency.
    # setup() builds indexes CONCURRENTLY, which waits for every open transaction,
    # including the request's own db session. So every endpoint declares this
    # dependency *before* the ones that use the db (the session only opens its
    # transaction on its first query).
    saver = open_postgres_saver(psycopg_conninfo(settings.database_url))
    return build_trip_planner(saver)


def get_run(
    run_id: UUID, group: Group = Depends(get_group), db: Session = Depends(get_db)
) -> PlannerRun:
    """Dependency: a run of *this* group, or 404 (like get_member)."""
    run = trip_planner.find_run(db, group, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post(
    "/groups/{code}/planner/runs",
    response_model=PlannerRunRead,
    status_code=201,
    summary="Start a trip planner run for a group",
    description=(
        "Runs the planner until it needs the group's answer, or ends. A group "
        "with no common ground (or no members) ends at once with status no_plan."
    ),
)
def start_planner_run(
    body: PlannerRunStart,
    graph: CompiledStateGraph = Depends(get_trip_planner),
    group: Group = Depends(get_group),
    db: Session = Depends(get_db),
):
    run = trip_planner.start_run(db, graph, group, body)
    return trip_planner.run_view(graph, run)


# Declared before {run_id}, so "latest" is never read as a run id.
@router.get(
    "/groups/{code}/planner/runs/latest",
    response_model=PlannerRunRead | None,
    summary="The group's newest run, or null when there is none",
)
def read_latest_run(
    graph: CompiledStateGraph = Depends(get_trip_planner),
    group: Group = Depends(get_group),
    db: Session = Depends(get_db),
):
    run = trip_planner.latest_run(db, group)
    return trip_planner.run_view(graph, run) if run else None


@router.get(
    "/groups/{code}/planner/runs/{run_id}",
    response_model=PlannerRunRead,
    summary="Read a run: status, proposal or plan, and the trace",
)
def read_run(
    graph: CompiledStateGraph = Depends(get_trip_planner),
    run: PlannerRun = Depends(get_run),
):
    return trip_planner.run_view(graph, run)


@router.post(
    "/groups/{code}/planner/runs/{run_id}/answer",
    response_model=PlannerRunRead,
    summary="Approve or reject the proposed sector",
    description=(
        "Name the proposal with sector_id: if someone already answered it, the answer "
        "gets 409 and changes nothing."
    ),
)
def answer_planner_run(
    body: PlannerAnswer,
    graph: CompiledStateGraph = Depends(get_trip_planner),
    run: PlannerRun = Depends(get_run),
    db: Session = Depends(get_db),
):
    try:
        run = trip_planner.answer_run(db, graph, run, body)
    except trip_planner.RunNotWaiting:
        raise HTTPException(status_code=409, detail="This proposal is no longer waiting for an answer")
    return trip_planner.run_view(graph, run)


@router.get(
    "/planner/graph",
    response_model=PlannerGraphRead,
    summary="Nodes and edges of the trip planner graph",
)
def read_graph(graph: CompiledStateGraph = Depends(get_trip_planner)):
    return trip_planner.graph_structure(graph)
