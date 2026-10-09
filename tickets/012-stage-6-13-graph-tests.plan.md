# Plan for 012: Stage 6.13, tests for the nodes and the approval pause

**Ticket:** `tickets/012-stage-6-13-graph-tests.md`
**Approach:** Plans 007–011 already add a test with every node and edge, because CLAUDE.md
requires new logic to come with tests in the same green commit. So this ticket is an
**audit and gap-filling** pass, in one delivery. First, the repeated graph-test setup (a new
checkpointer and thread id per test, the "paused run" group) moves into shared fixtures, with
no change to any existing assertion. Then the guards the earlier plans don't have are added:
the other two routing functions, "a rejected sector never gets a stay lookup", "three
rejections end without a plan", "threads don't share checkpoints", and a static check that
the agent package imports no network client.

**Alternatives considered:**
- *Writing every planner test here, none in 007–011:* each of those tickets would then be
  committed with untested logic, against CLAUDE.md ("New logic needs tests") and the "tests
  green per commit" rule. The ticket's acceptance criteria are still met: the coverage
  table below maps each one to a named test, old or new.
- *A socket-blocking fixture for "no network" (AC 6):* the planner never opens a connection
  except to Postgres, which the tests need. Blocking sockets would have to whitelist the
  database. A static import check is simpler and catches the real risk: someone wiring
  Claude or Voyage into a node.

## Ticket check
- **Wrong: "Build the test group and sectors through the database session, as
  `test_groups_api.py` does".** `test_groups_api.py` builds everything **through the API**
  (`_create_group(client, …)`, `_add_member(client, …)`, `_add_sector(client, …)`, lines
  16–37). The agent tests use the `db_session` factories in `tests/conftest.py` (plan 008)
  instead. Nodes take a `Session`, so the tests read the same tables the nodes read, which
  is the ticket's intent.
- **Stale: "the existing suite (96+ tests)".** HEAD at ticket 005 delivered (`f39f725`) has
  **126** tests, ticket 014 (delivered before 007) brings it to **127**, and with tickets
  007–011 delivered as planned it's **169**. Count again at the start.
- Test file names: `tests/test_agent_nodes.py` and `tests/test_agent_graph.py` (as the ticket
  suggests), plus `tests/test_trip_planner_script.py` from plan 011.
- "Plain stand-ins for members in `test_group_matching.py`": correct (`class P`, line 17).
  The node tests don't need them: nodes read members from the database.
- "The planner nodes call no external services": true by design in plans 008–010. AC 6's
  guard is added in this delivery.
- After ticket 014, `app.services.llm` and `app.services.embedding` no longer hold any
  client: only `LLM_MODEL` / `log_tokens()` and `EMBED_MODEL`. The Claude and Voyage clients
  are now created in `app/rag/` (`get_chat_model()` in `rag/llm.py` through
  `langchain_anthropic`, `get_embeddings()` in `rag/vectorstore.py` through
  `langchain_voyageai`). The import check below is written for that layout.

## Before you start
- Ticket 014 and plans 007–011 are delivered.
- One pytest run at a time (the process check in plan 005), in the foreground. No network.
- Count the planner tests before touching anything:
  `uv run pytest tests/test_agent_nodes.py tests/test_agent_graph.py tests/test_trip_planner_script.py --collect-only -q`.
  With 007–011 delivered as planned that's **42**. At the end it must be exactly that
  number + 7 (no existing planner test lost in the fixture refactor).

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. Shared fixtures for planner tests, then the missing guards (routing, rejection, thread isolation, no network)
**Files** (in build order: migration, backend, frontend; tests only, no app code changes):
- `backend/tests/conftest.py`:
  - `thread_config()` fixture: returns `{"configurable": {"thread_id": str(uuid4())}}`.
    Docstring: a new thread per test, so checkpoints can't leak between tests (ticket note).
  - `planner(db_session)` fixture: returns `(build_trip_planner(InMemorySaver()), PlannerContext(db=db_session))`.
    A new saver every time.
  - `agreeing_group(make_group, make_sector, make_stay)` fixture: the group used by plan
    010's `paused_run`. It has two members who agree (6a–7a / 6b–7b, 100 / 80 km), two
    matching sectors at two crags (near: 37 km, far: 106 km), two stays near each, and one
    sector out of range. It returns the share code and the two sector ids.
  - `disagreeing_group(make_group)` fixture: members 5–6a and 7a–8a (the ticket 009 note).
- `backend/tests/test_agent_graph.py`, `backend/tests/test_trip_planner_script.py`: existing
  tests use these fixtures instead of their own copies of the setup (the `paused_run`
  fixture becomes a thin wrapper over `planner` + `thread_config` + `agreeing_group`).
  **No assertion changes in existing tests.**
- `backend/tests/test_agent_graph.py`, new tests:
  - `test_route_after_pick_asks_for_approval_when_a_sector_is_chosen` and
    `test_route_after_pick_ends_when_nothing_is_chosen` (plain dicts). (AC 2)
  - `test_route_after_approval_goes_to_stays_or_back_to_pick` (both values, plain dicts).
    (AC 2)
  - `test_rejected_sector_never_gets_a_stay_lookup`: spy on `app.agent.nodes.find_stays_near`
    that records `(lat, lon)` and calls the real function. Pause, reject the near sector,
    approve the far one → every recorded point is the far crag's. (AC 4)
  - `test_three_rejections_end_without_a_plan`: a group with four matching sectors; reject
    three times. The run ends with no `"__interrupt__"`, `plan` absent, the message says 3
    sectors were turned down, and the `find_stays_near` spy was never called. (AC 4)
  - `test_threads_do_not_share_checkpoints`: the same `planner` graph, two thread ids
    (`thread_config` for thread A, a second `uuid4()` config for thread B); pause both,
    reject on thread A only → `get_state` on thread B still has its first sector and no
    rejections. (ticket note on thread ids)
- `backend/tests/test_agent_nodes.py`, new test:
  - `test_agent_package_imports_no_network_client`: parse every `app/agent/*.py` with `ast`
    and collect imported modules. None starts with `anthropic`, `voyageai`, `httpx`,
    `langchain_anthropic`, `langchain_voyageai`, `app.rag`, `app.services.llm`,
    `app.services.embedding` or `app.services.overpass`. Docstring: the planner must stay
    offline; a Claude step would need its own mocked tests first. Since ticket 014 the
    clients live in `app.rag`; the two `app.services` model-name modules stay on the list
    because a node that needs a model name is about to call a model. (AC 6)

**Reuses:** the factories from plan 008, `build_trip_planner`, `InMemorySaver`; the spy
pattern of plan 009 (`monkeypatch.setattr("app.agent.nodes.find_stays_near", spy)`).

**Tests:** the seven new tests above, plus every existing planner test passing unchanged on
the shared fixtures. The full suite passes with no network.

**Expected suite:** 176 passed (169 after tickets 014 and 007–011 are delivered as planned +
7 new: 6 in `test_agent_graph.py`, 1 in `test_agent_nodes.py`). The three planner test files
collect 49.

**Check by hand:**
- `git diff --stat` touches only `tests/`.
- Every `InMemorySaver(` and `uuid4(` in the planner tests sits in `tests/conftest.py`:
  `grep -n "InMemorySaver(\|uuid4(" tests/test_agent_*.py tests/test_trip_planner_script.py`
  prints only thread B's config in `test_threads_do_not_share_checkpoints`.
- `uv run pytest tests/test_agent_nodes.py tests/test_agent_graph.py tests/test_trip_planner_script.py -v`
  lists one test per row of the coverage table below.

**Commit:** `Stage 6.13: shared fixtures for trip planner tests (fresh checkpointer and thread id per test, agreeing and disagreeing groups) and the missing guards, every routing function, a rejected sector never gets a stay lookup, three rejections end with no plan, threads are isolated, agent code imports no network client`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_agent_nodes.py`: `test_merge_writes_filters_for_a_group_that_agrees`, `test_merge_writes_conflicts_when_there_is_no_common_ground` (008), `test_search_returns_candidates_best_first` (008/010), `test_find_stays_returns_closest_stays_as_plain_dicts` (008), `test_propose_plan_has_dates_guests_stays_and_links` (010) |
| 2 | `test_route_after_merge_*` (009); `test_route_after_pick_*`, `test_route_after_approval_*` (this ticket) |
| 3 | `test_run_pauses_at_approval_with_the_proposed_sector`, `test_paused_state_has_the_sector_and_no_stays` (010) |
| 4 | `test_approve_resumes_and_produces_a_plan`, `test_reject_proposes_the_next_sector` (010); `test_rejected_sector_never_gets_a_stay_lookup`, `test_three_rejections_end_without_a_plan` (this ticket) |
| 5 | `test_graph_without_common_ground_skips_search_and_stays` (009) |
| 6 | Full `uv run pytest` run; `test_agent_package_imports_no_network_client` (this ticket) |

If a test named here from 008–011 was renamed during delivery, the tech lead updates this
table during review. It must not be left pointing at a missing name.

## Risks
- *The fixture refactor quietly drops an assertion, hidden among the new tests in the same
  diff:* the planner test count must be exactly the starting count + 7, and the tech lead
  reads the diff of the existing test functions separately from the new ones (only setup
  lines may change there).
- *Spies that replace instead of wrapping:* each spy calls the real function, so the graph
  still sees real stays and the paths stay realistic.
- *The import check produces false positives* (e.g. an `app.rag` helper that's really
  offline): change the allowlist in the test deliberately, with a comment. Don't delete the
  test.

## Out of scope (copied from the ticket)
- Load testing, and tests of a web API for the planner (none exists in Stage 6).
