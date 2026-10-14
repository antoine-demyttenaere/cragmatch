from datetime import date, timedelta
from typing import TypedDict
from uuid import uuid4

import pytest
from langgraph.graph import END, START, StateGraph

from app.agent.graph import build_trip_planner
from app.main import app
from app.routers.planner import get_trip_planner

APPROVE = {"approved": True}


def reject(reason: str) -> dict:
    return {"approved": False, "reason": reason}


def start(client, share_code: str, **body):
    return client.post(f"/groups/{share_code}/planner/runs", json=body)


def answer(client, share_code: str, run_id: str, body: dict):
    return client.post(f"/groups/{share_code}/planner/runs/{run_id}/answer", json=body)


def trace_nodes(run: dict) -> list[str]:
    return [step["node"] for step in run["trace"]]


def test_start_run_pauses_with_a_proposal_and_a_trace(client, agreeing_group):
    response = start(client, agreeing_group.share_code)

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "waiting_for_approval"
    assert run["proposal"]["sector_name"] == "Near"
    assert run["plan"] is None
    assert trace_nodes(run) == ["merge_preferences", "search_sectors", "pick_sector"]
    assert "filters" in run["trace"][0]["changed"]


def test_approve_returns_a_plan_with_stays_and_links(client, agreeing_group):
    run = start(client, agreeing_group.share_code).json()

    response = answer(client, agreeing_group.share_code, run["run_id"], APPROVE)

    assert response.status_code == 200
    done = response.json()
    assert done["status"] == "planned"
    assert done["proposal"] is None
    plan = done["plan"]
    assert plan["sector"]["sector_name"] == "Near"
    checkin = date.fromisoformat(plan["checkin"])
    checkout = date.fromisoformat(plan["checkout"])
    assert (checkout - checkin).days == plan["nights"]
    assert 1 <= len(plan["stays"]) <= 5
    assert plan["links"]["airbnb"]
    assert plan["links"]["booking"]
    assert trace_nodes(done)[-3:] == ["approve_sector", "find_stays", "propose_plan"]


def test_reject_proposes_the_next_sector_and_keeps_the_reason(client, agreeing_group):
    run = start(client, agreeing_group.share_code).json()

    response = answer(client, agreeing_group.share_code, run["run_id"], reject("too far"))

    assert response.status_code == 200
    after = response.json()
    assert after["status"] == "waiting_for_approval"
    assert after["proposal"]["sector_name"] == "Far"
    assert after["rejections"] == [{"sector_id": agreeing_group.near_id, "reason": "too far"}]


def test_three_rejections_end_with_no_plan(client, agreeing_group, make_sector):
    make_sector("Extra one", "6a", "7a", lat=41.30, lon=1.00, crag="Extra crag one")
    make_sector("Extra two", "6a", "7a", lat=41.40, lon=1.10, crag="Extra crag two")
    code = agreeing_group.share_code
    run = start(client, code).json()

    for _ in range(3):
        run = answer(client, code, run["run_id"], reject("no")).json()

    assert run["status"] == "no_plan"
    assert run["proposal"] is None
    assert "turned down 3 sectors" in run["message"]
    assert len(run["rejections"]) == 3


def test_group_without_common_ground_ends_at_once(client, disagreeing_group):
    response = start(client, disagreeing_group)

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "no_plan"
    assert trace_nodes(run) == ["merge_preferences", "explain_conflicts"]
    assert "No grade everyone climbs" in run["message"]


def test_group_without_members_ends_with_no_plan(client, make_group):
    group = make_group()

    response = start(client, group.share_code)

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "no_plan"
    assert "no members" in run["message"]


def test_get_run_matches_the_last_answer(client, agreeing_group):
    code = agreeing_group.share_code
    started = start(client, code).json()
    answered = answer(client, code, started["run_id"], reject("too far")).json()

    fetched = client.get(f"/groups/{code.lower()}/planner/runs/{started['run_id']}")

    assert fetched.status_code == 200
    assert fetched.json() == answered


def test_restart_resumes_on_the_same_checkpointer(client, agreeing_group):
    code = agreeing_group.share_code
    run = start(client, code).json()

    # A new process builds a new graph, but the checkpoints are in the saver.
    saver = app.dependency_overrides[get_trip_planner]().checkpointer
    restarted = build_trip_planner(saver)
    app.dependency_overrides[get_trip_planner] = lambda: restarted

    response = answer(client, code, run["run_id"], APPROVE)

    assert response.status_code == 200
    assert response.json()["status"] == "planned"


def test_latest_run_is_the_newest(client, agreeing_group):
    code = agreeing_group.share_code
    start(client, code)
    second = start(client, code).json()

    response = client.get(f"/groups/{code}/planner/runs/latest")

    assert response.status_code == 200
    assert response.json()["run_id"] == second["run_id"]


def test_latest_run_is_null_without_runs(client, agreeing_group):
    response = client.get(f"/groups/{agreeing_group.share_code}/planner/runs/latest")

    assert response.status_code == 200
    assert response.json() is None


def test_graph_structure_lists_nodes_and_conditional_edges(client):
    response = client.get("/planner/graph")

    assert response.status_code == 200
    body = response.json()
    assert {
        "merge_preferences", "search_sectors", "pick_sector", "approve_sector",
        "find_stays", "propose_plan", "explain_conflicts",
    } <= set(body["nodes"])
    edges = {(e["source"], e["target"]): e["conditional"] for e in body["edges"]}
    assert edges[("merge_preferences", "explain_conflicts")] is True
    assert edges[("find_stays", "propose_plan")] is False


def test_graph_structure_follows_the_compiled_graph(client):
    class Small(TypedDict, total=False):
        value: int

    builder = StateGraph(Small)
    builder.add_node("first", lambda state: {})
    builder.add_node("second", lambda state: {})
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    small = builder.compile()
    app.dependency_overrides[get_trip_planner] = lambda: small

    body = client.get("/planner/graph").json()

    # START and END are drawn too, edges point at them.
    assert set(body["nodes"]) == {"__start__", "first", "second", "__end__"}
    assert {(e["source"], e["target"]) for e in body["edges"]} == {
        ("__start__", "first"),
        ("first", "second"),
        ("second", "__end__"),
    }


def test_unknown_share_code_is_404(client):
    assert start(client, "NOPE2345").status_code == 404
    assert client.get("/groups/NOPE2345/planner/runs/latest").status_code == 404


def test_unknown_run_is_404(client, agreeing_group):
    code = agreeing_group.share_code
    unknown = uuid4()

    assert client.get(f"/groups/{code}/planner/runs/{unknown}").status_code == 404
    assert answer(client, code, str(unknown), APPROVE).status_code == 404


def test_run_of_another_group_is_404(client, agreeing_group, make_group):
    other = make_group(name="Other")
    run = start(client, agreeing_group.share_code).json()

    fetched = client.get(f"/groups/{other.share_code}/planner/runs/{run['run_id']}")
    answered = answer(client, other.share_code, run["run_id"], APPROVE)

    assert fetched.status_code == 404
    assert answered.status_code == 404


def test_answering_a_finished_run_is_409(client, agreeing_group):
    code = agreeing_group.share_code
    run = start(client, code).json()
    assert answer(client, code, run["run_id"], APPROVE).status_code == 200

    again = answer(client, code, run["run_id"], APPROVE)

    assert again.status_code == 409


def test_answer_for_a_sector_no_longer_proposed_is_409(client, agreeing_group):
    code = agreeing_group.share_code
    near_id = agreeing_group.near_id
    run = start(client, code).json()
    moved = answer(client, code, run["run_id"], {**reject("too far"), "sector_id": near_id})
    assert moved.json()["proposal"]["sector_name"] == "Far"

    late_approve = answer(client, code, run["run_id"], {**APPROVE, "sector_id": near_id})
    late_reject = answer(client, code, run["run_id"], {**reject("no"), "sector_id": near_id})

    assert late_approve.status_code == 409
    assert late_reject.status_code == 409
    current = client.get(f"/groups/{code}/planner/runs/{run['run_id']}").json()
    assert current["status"] == "waiting_for_approval"
    assert current["proposal"]["sector_name"] == "Far"
    assert current["rejections"] == [{"sector_id": near_id, "reason": "too far"}]


def test_answer_naming_the_proposed_sector_goes_through(client, agreeing_group):
    code = agreeing_group.share_code
    run = start(client, code).json()

    response = answer(
        client, code, run["run_id"], {**APPROVE, "sector_id": agreeing_group.near_id}
    )

    assert response.status_code == 200
    done = response.json()
    assert done["status"] == "planned"
    assert done["plan"]["sector"]["sector_id"] == agreeing_group.near_id


def test_docs_example_answer_goes_through(client, agreeing_group):
    schema = client.get("/openapi.json").json()["components"]["schemas"]["PlannerAnswer"]
    example = schema["examples"][0]
    assert "sector_id" not in example
    code = agreeing_group.share_code
    run = start(client, code).json()

    response = answer(client, code, run["run_id"], example)

    assert response.status_code == 200
    assert response.json()["proposal"]["sector_name"] == "Far"


@pytest.mark.parametrize(
    "body",
    [
        {"checkin": (date.today() - timedelta(days=1)).isoformat()},
        {"nights": 0},
        {"nights": 31},
        {"guests": 0},
        {"guests": 31},
    ],
)
def test_start_rejects_bad_input(client, agreeing_group, body):
    assert start(client, agreeing_group.share_code, **body).status_code == 422
