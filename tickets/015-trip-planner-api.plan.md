# Plan for 015: Trip planner over HTTP, with paused runs saved in Postgres

**Ticket:** `tickets/015-trip-planner-api.md`
**Approach:** LangGraph's `PostgresSaver`, from the new `langgraph-checkpoint-postgres`
package, keeps the graph's checkpoints in the project database. Its tables are made by
the library's own idempotent `setup()`. A small table of our own, `planner_runs` (run id =
thread id, group, creation time, trace), records which run belongs to which group, which
run is the latest, and the node-by-node trace. A new service, `services/trip_planner.py`,
starts a run, advances it, answers it and turns a checkpoint into a response. A thin
router exposes it under `/groups/{code}/planner/...`. The terminal script reuses the
service's stepping function.

**Alternatives considered:**
- *No table of our own: keep the group and the trace in checkpoint metadata, and find runs
  with `checkpointer.list(filter=...)`:* "latest run of a group" would mean scanning
  checkpoints across threads, and the trace would have to be rebuilt from checkpoint
  history, whose metadata format has changed between LangGraph versions. A 4-column table
  is simpler, can be queried with plain SQLAlchemy, and gives the ownership check of AC 9
  for free.
- *Put the trace in the graph state, with a reducer:* every node would have to return a
  trace entry. That changes the graph and its 50+ tests only to support a view. The trace
  is a record of the run, not planner data, so it goes in `planner_runs`.
- *Create the checkpoint tables with Alembic:* we would copy the library's DDL and own its
  future schema changes. `setup()` is idempotent and versioned (it keeps its own
  `checkpoint_migrations` table). `alembic/env.py`'s `include_object` already ignores
  every table that isn't in our metadata, so autogenerate won't try to drop them.
- *Build the saver in a FastAPI lifespan:* tests use `TestClient(app)` without `with`, so
  the lifespan never runs in tests, and the planner dependency would need a second set-up
  path anyway. A lazily built, cached `get_trip_planner()` dependency follows the
  `get_vector_store()` pattern (`lru_cache`, built once per process), and tests override it.
- *Stream every node to the browser (SSE):* out of scope in the ticket. The trace in each
  response is enough.

**Choices on the ticket's open questions:**
- Several runs per group: yes. Every start creates a run, and "latest" is the newest
  `created_at`. Older runs can still be fetched by id.
- Who can approve: anyone with the share code (the same `get_group` dependency as every
  group endpoint).
- Rejection reasons: returned in the run's `rejections` list (already in the state). The
  plan itself is unchanged.

## Ticket check
- Correct: `build_trip_planner(checkpointer)`, `initial_state()`, `Approval`,
  `PlannerContext`, the `interrupt()` in `approve_sector` and `MAX_PROPOSALS = 3` are as
  described. `uv.lock` has `langgraph` 1.2.15 and `langgraph-checkpoint` 4.3.0, no
  `langgraph-checkpoint-postgres`. `psycopg` 3.3.5 and `psycopg_pool` 3.3.3 are already
  installed.
- More precise than the ticket: the message after three rejections is "No plan: the group
  turned down 3 sectors." (`nodes.py` `pick_sector`). AC 3's text is a substring of it.
- More precise than the ticket: a group with no members does go through
  `explain_conflicts`, with the conflict "The group has no members yet." (`nodes.py:89`).
  An unknown share code is not a run outcome: `merge_group_preferences` raises
  `ValueError`. The API must answer 404 *before* starting a run, through `get_group`.
- More precise than the ticket: the ticket says to keep Alembic from dropping the
  checkpoint tables. That is already handled: `alembic/env.py:73-80` only compares tables
  in `target_metadata`. No change to `env.py`.
- Missing from the ticket: SQLAlchemy's URL is `postgresql+psycopg://...`
  (`config.py:17-20`), but psycopg and `PostgresSaver` need a plain `postgresql://`
  conninfo. A small conversion helper is needed (step 3).
- Missing from the ticket: `PostgresSaver` on one psycopg connection is not safe across
  FastAPI's threadpool (sync endpoints run in parallel threads). Use a `psycopg_pool`
  `ConnectionPool` with the connection settings the saver requires.
- Missing from the ticket: the 3 script tests in `test_trip_planner_script.py` assert the
  exact trace lines, including that `approve_sector`'s own update is replaced by an
  "approved"/"rejected" line. Sharing the run logic must keep this output unchanged.
- Since commit 104dd64, `tests/conftest.py` has `planner`, `thread_config`,
  `agreeing_group` (Near and Far sectors, a stay near each) and `disagreeing_group`. The
  new tests reuse them. The suite collects **176** tests today.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. A group can start, read and answer trip planner runs over HTTP, and paused runs survive a restart
**Before building:** the user stops the dev server (Windows + OneDrive locks files during
`uv add`). The developer does not touch the dev database: no `alembic upgrade`, no
autogenerate.

**Files** (in build order: dependency, migration, backend):
- `backend/pyproject.toml` / `uv.lock`: `uv add langgraph-checkpoint-postgres`. Then
  check in `uv.lock` that `langgraph` stays 1.2.15 and `langgraph-checkpoint` stays at
  4.x. If uv wants to change either one, stop and report. Read the installed
  `langgraph/checkpoint/postgres/__init__.py`: check the `PostgresSaver` constructor
  (connection or pool), `setup()`, `delete_thread()`, and the connection settings it needs
  (`autocommit=True`, `row_factory=dict_row`, `prepare_threshold=0`). Use what the
  installed version says, not this plan, if they differ.
- `backend/app/models/planner_run.py` (new): `PlannerRun`, table `planner_runs`:
  `id: Mapped[uuid.UUID]` (primary key, `Uuid` type, default `uuid.uuid4`, and also used as
  the LangGraph `thread_id`), `group_id` (FK `groups.id`, `ondelete="CASCADE"`, indexed),
  `created_at` (timezone-aware, `server_default=func.now()`), and `trace` (`JSONB`, not
  null, default empty list). It has no relationship on `Group`: runs are looked up by
  `group_id`, and `Group` stays unchanged. One-line why-comments: the id doubles as the
  thread id, and the trace lives here and not in the graph state.
- `backend/app/models/__init__.py`: import and export `PlannerRun`.
- `backend/alembic/versions/<rev>_add_planner_runs.py` (new): run plain
  `uv run alembic revision -m "add planner_runs"`. This doesn't connect, and plan 014
  explains why autogenerate is not used here. `down_revision` = the current head
  (`uv run alembic heads`, offline). Upgrade creates `planner_runs` and its index.
  Downgrade drops both. The docstring says the LangGraph checkpoint tables are made by
  `PostgresSaver.setup()`, not here.
- `backend/app/agent/checkpointer.py` (new):
  - `psycopg_conninfo(sqlalchemy_url: str) -> str`: uses SQLAlchemy's `make_url(...)`
    `.set(drivername="postgresql")` and renders with the password.
  - `open_postgres_saver(conninfo: str) -> PostgresSaver`: opens a `ConnectionPool`
    with the settings checked above, wraps it in a saver, calls `setup()` and returns it.
  - The module docstring says why a pool (FastAPI's threadpool) and that `setup()` is
    idempotent.
  - Only `psycopg`, `psycopg_pool` and `langgraph` imports, so
    `test_agent_package_imports_no_network_client` still passes.
- `backend/app/schemas/planner.py` (new):
  - `PlannerSector`: the `Candidate` fields.
  - `PlannerPlan`: sector, checkin and checkout (date), nights, guests, `stays:
    list[NearbyStay]`, `links: BookingLinks`.
  - `TraceStep`: `node: str`, `changed: list[str]`.
  - `RejectionRead`: `sector_id`, `reason`.
  - `PlannerRunStart`: checkin `date | None`, nights `Field(2, ge=1, le=30)`, guests
    `int | None = Field(None, ge=1, le=30)`, and a validator that rejects a past checkin,
    giving 422. The rules and wording are the same as the group stays endpoint and the
    script.
  - `PlannerRunRead`: `run_id: UUID`, `share_code`,
    `status: Literal["waiting_for_approval", "planned", "no_plan"]`, `checkin`, `nights`,
    `guests | None`, `proposal: PlannerSector | None`, `plan: PlannerPlan | None`,
    `message: str | None`, `rejections: list[RejectionRead]`, `trace: list[TraceStep]`,
    `created_at`.
  - `PlannerGraphRead`: `nodes: list[str]`, `edges: list[PlannerEdge]`, where
    `PlannerEdge` has `source`, `target`, `conditional: bool`.
  - The answer body reuses `app.agent.state.Approval`, the same model `interrupt()`
    validates the resume value with, so the two can't drift.
- `backend/app/services/trip_planner.py` (new). It holds all the run logic, and the router
  and the script call it:
  - `class RunNotWaiting(Exception)`: answering a run that isn't paused.
  - `advance(graph, graph_input, config, context) -> list[dict]`: runs `graph.stream(...,
    stream_mode="updates")` and returns the trace steps `{"node", "changed"}` in order.
    It skips the `__interrupt__` chunk, and an update of `None` gives `changed=[]`. The
    logic moves here from the loop in `scripts/trip_planner.py`.
  - `start_run(db, graph, group, start: PlannerRunStart) -> PlannerRun`: inserts the
    `PlannerRun` and flushes to get the id. Then it calls `advance` with
    `initial_state(group.share_code, ...)` and `PlannerContext(db)`, stores the trace and
    commits.
  - `answer_run(db, graph, run, approval) -> PlannerRun`: locks the row
    (`with_for_update()`, so two friends answering at once are serialized). It checks
    `graph.get_state(config).next == ("approve_sector",)` and raises `RunNotWaiting`
    otherwise. Then it calls `advance(Command(resume=approval.model_dump()))`, appends to
    the trace (assign a new list, so SQLAlchemy sees the JSONB change) and commits.
  - `find_run(db, group, run_id) -> PlannerRun | None`: filters on **both** `id` and
    `group_id`.
  - `latest_run(db, group) -> PlannerRun | None`: newest `created_at`.
  - `run_view(graph, run) -> PlannerRunRead`: reads `graph.get_state(config)`.
    - Status `waiting_for_approval` when `next == ("approve_sector",)`. The proposal is
      the state's `chosen_sector`.
    - Otherwise `planned` when `values.get("plan")`, else `no_plan`, with `message`.
    - `rejections`, checkin, nights and guests come from the values. The trace comes from
      the row.
  - `graph_structure(graph) -> PlannerGraphRead`: built from `graph.get_graph()`
    (`nodes`, `edges` with their `conditional` flag), so it follows `build_trip_planner()`
    with no list kept by hand.
- `backend/app/routers/planner.py` (new). It stays thin, as CLAUDE.md asks:
  - `get_trip_planner()`: `@lru_cache(maxsize=1)`. Builds
    `build_trip_planner(open_postgres_saver(psycopg_conninfo(settings.database_url)))`
    on first use. Tests override this dependency.
  - `POST /groups/{code}/planner/runs` (201, `PlannerRunRead`, body `PlannerRunStart`).
  - `GET /groups/{code}/planner/runs/latest` (`PlannerRunRead | None`, 200 with `null`
    when there is none: "no run yet" is a normal answer). Declare it **before** the
    `{run_id}` route.
  - `GET /groups/{code}/planner/runs/{run_id}` (404 "Run not found" when `find_run`
    gives None).
  - `POST /groups/{code}/planner/runs/{run_id}/answer` (body `Approval`, 409 "This run is
    not waiting for an answer" on `RunNotWaiting`).
  - `GET /planner/graph` (`PlannerGraphRead`).
  - All group routes use `get_group` from `routers/groups.py`, which gives 404 for an
    unknown code before any run starts. No rate limit: the planner calls no paid API.
- `backend/app/main.py`: `app.include_router(planner.router, tags=["planner"])`. The
  routes carry their full paths, because they span `/groups` and `/planner`.
- `backend/app/scripts/trip_planner.py`: `run_planner` calls `services.trip_planner.advance`
  instead of its own stream loop. It still uses `InMemorySaver` (a terminal run isn't a
  group's saved run), keeps `describe_update` and the "approved / rejected: reason" line,
  and still skips `approve_sector`'s own step. The output stays exactly the same (3
  existing tests). Update the docstring: the API keeps runs in Postgres, the script
  doesn't.
- `backend/conftest.py`: the `client` fixture also overrides `get_trip_planner` with
  `build_trip_planner(InMemorySaver())`, new per test. No API test can then open a
  Postgres saver by accident (AC 10).
- `README.md`: add the new files to the structure (`models/planner_run.py`,
  `schemas/planner.py`, `services/trip_planner.py`, `routers/planner.py`,
  `agent/checkpointer.py`). Under "Running locally", say that the checkpoint tables are
  created on the first planner request, and that `alembic upgrade head` is needed for
  `planner_runs`.
- `CLAUDE.md`, "Reuse before writing": add `advance()` / `start_run()` / `answer_run()` /
  `run_view()` in `services/trip_planner.py` and `get_trip_planner` in
  `routers/planner.py`. Under "Traps": the checkpoint tables come from
  `PostgresSaver.setup()`, not Alembic.
- `tickets/013-stage-7-deployment.md`: its last open question (planner endpoint +
  persistent checkpointer) is answered by ticket 015. Say so in one line.

**Reuses:** `get_group` (`routers/groups.py`), `build_trip_planner`, `initial_state`,
`Approval`, `PlannerContext` (`app/agent`), `NearbyStay` / `BookingLinks`
(`schemas/stay.py`), `settings.database_url` (`core/config.py`), the `lru_cache`
dependency pattern of `get_vector_store()` (`rag/vectorstore.py`), and the fixtures
`agreeing_group`, `disagreeing_group`, `make_group`, `make_sector` (`tests/conftest.py`).

**Tests:**
- `tests/test_planner_api.py` (new; uses `client` with the in-memory planner from conftest):
  - `test_start_run_pauses_with_a_proposal_and_a_trace`: 201,
    `status == "waiting_for_approval"`, `proposal.sector_name == "Near"`, trace nodes
    `[merge_preferences, search_sectors, pick_sector]`, and merge's `changed` includes
    `filters`. (AC 1)
  - `test_approve_returns_a_plan_with_stays_and_links`: `status == "planned"`, plan
    sector Near, `checkout - checkin == nights`, 1 to 5 stays, both links. The trace ends
    with `approve_sector, find_stays, propose_plan`. (AC 2)
  - `test_reject_proposes_the_next_sector_and_keeps_the_reason`: after "too far", status
    is still waiting, proposal is Far, `rejections == [{near_id, "too far"}]`. (AC 3)
  - `test_three_rejections_end_with_no_plan`: two extra sectors via `make_sector`, three
    rejections, then `status == "no_plan"` and "turned down 3 sectors" in the message.
    (AC 3)
  - `test_group_without_common_ground_ends_at_once`: `disagreeing_group`, status
    `no_plan`, trace `[merge_preferences, explain_conflicts]`, "No grade everyone climbs"
    in the message. (AC 4)
  - `test_group_without_members_ends_with_no_plan`: `make_group()` with no members, so
    `no_plan` and "no members" in the message, status 201, not an error. (AC 4)
  - `test_get_run_matches_the_last_answer`: start, then GET by id, also with the share
    code in lower case. The body equals the start response. (AC 5)
  - `test_restart_resumes_on_the_same_checkpointer`: start with graph A, then override
    `get_trip_planner` with a **new** graph built on the same saver (as a new process
    would), answer, and get `planned`. (AC 6)
  - `test_latest_run_is_the_newest`: start twice, latest returns the second run id. (AC 7)
  - `test_latest_run_is_null_without_runs`: 200 and `null`. (AC 7)
  - `test_graph_structure_lists_nodes_and_conditional_edges`: all 7 planner nodes are
    present. `merge_preferences → explain_conflicts` is conditional,
    `find_stays → propose_plan` is not. (AC 8)
  - `test_graph_structure_follows_the_compiled_graph`: override the planner with a small
    two-node `StateGraph`, and the response lists exactly those nodes. Nothing in the
    response is hardcoded. (AC 8)
  - `test_unknown_share_code_is_404`: start and latest on `NOPE2345`. (AC 9)
  - `test_unknown_run_is_404`: a random UUID. (AC 9)
  - `test_run_of_another_group_is_404`: a run started on group A, fetched and answered
    through group B's code. (AC 9)
  - `test_answering_a_finished_run_is_409`: approve, then approve again. (AC 9)
  - `test_start_rejects_bad_input` (parametrized, 5 cases): past checkin, nights 0,
    nights 31, guests 0, guests 31, each giving 422. (AC 9)
- `tests/test_planner_checkpointer.py` (new):
  - `test_psycopg_conninfo_drops_the_driver_name`:
    `postgresql+psycopg://u:p@h:5433/db` becomes `postgresql://u:p@h:5433/db`. (support)
  - `test_postgres_saver_resumes_a_run_after_reopening`: `open_postgres_saver` on the
    **`cragmatch_test`** database (the conninfo comes from conftest's
    `TEST_DATABASE_URL`). Start a run on `agreeing_group` and close the pool. Open a
    **new** saver and graph and resume with approval, then check there is a plan. Finally
    `delete_thread()` and close the pool. (AC 6, AC 10)
- Existing `tests/test_trip_planner_script.py` (3 run tests) and every
  `test_agent_*.py` test pass unchanged. That shows the script still works after the
  refactor.

**Expected suite:** 176 today + 23 new = **199 passed**. The 23 new tests are 16 single
API tests, 5 cases of `test_start_rejects_bad_input`, and 2 checkpointer tests. If the
number differs, the reviewer asks why.

**Check by hand** (after commit, by the user):
1. Stop the dev server. Run `uv sync`, then `uv run alembic upgrade head`, then
   `uv run alembic check`, which must report no drift: the checkpoint tables are ignored.
2. `uv run fastapi dev app/main.py`. In `/docs`, `POST /groups/9JS3VA3C/planner/runs`
   (the "Checkpoint demo" group) returns `waiting_for_approval` and a trace.
3. Stop and restart the server. `POST .../runs/{run_id}/answer` with
   `{"approved": true}` gives `planned` with stays and links (AC 6, for real).
4. `GET /planner/graph` lists the 7 nodes and the conditional edges.
5. `uv run python -m app.scripts.trip_planner 9JS3VA3C` still prints the same trace and
   asks y/n.

**Commit:** `Ticket 015: trip planner over HTTP, start, read and answer runs under /groups/{code}/planner, paused runs saved in Postgres with LangGraph PostgresSaver so they survive a restart, planner_runs table for group ownership, latest run and the node trace, /planner/graph for the diagram, script shares the stepping logic`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_planner_api.py::test_start_run_pauses_with_a_proposal_and_a_trace` |
| 2 | `test_planner_api.py::test_approve_returns_a_plan_with_stays_and_links` |
| 3 | `test_planner_api.py::test_reject_proposes_the_next_sector_and_keeps_the_reason`, `::test_three_rejections_end_with_no_plan` |
| 4 | `test_planner_api.py::test_group_without_common_ground_ends_at_once`, `::test_group_without_members_ends_with_no_plan` |
| 5 | `test_planner_api.py::test_get_run_matches_the_last_answer` |
| 6 | `test_planner_api.py::test_restart_resumes_on_the_same_checkpointer`, `test_planner_checkpointer.py::test_postgres_saver_resumes_a_run_after_reopening`, manual check 3 |
| 7 | `test_planner_api.py::test_latest_run_is_the_newest`, `::test_latest_run_is_null_without_runs` |
| 8 | `test_planner_api.py::test_graph_structure_lists_nodes_and_conditional_edges`, `::test_graph_structure_follows_the_compiled_graph` |
| 9 | `test_planner_api.py::test_unknown_share_code_is_404`, `::test_unknown_run_is_404`, `::test_run_of_another_group_is_404`, `::test_answering_a_finished_run_is_409`, `::test_start_rejects_bad_input` |
| 10 | conftest `client` override (in-memory planner for every API test); the only Postgres saver test uses `cragmatch_test`; whole suite runs offline |

Not covered by an automated test: two friends answering at the *same instant*. The row
lock handles it, but a real race is unreliable to test. `test_answering_a_finished_run_is_409`
covers the sequential case, which gives the same answer.

## Risks
- **Dependency resolution:** `langgraph-checkpoint-postgres` may require a different
  `langgraph-checkpoint`. Mitigation: the developer checks `uv.lock` after `uv add` and
  stops if `langgraph` or `langgraph-checkpoint` would change major version. All agent
  tests must stay green.
- **Library API drift:** the constructor, `setup()`, `delete_thread()` and the required
  connection settings are checked in the installed source, not from memory.
- **Checkpoint tables in the test DB:** `drop_all()` doesn't drop them, so they stay in
  `cragmatch_test` between runs. That is harmless: every test uses a new UUID thread, and
  the one Postgres test deletes its thread.
- **Dev DB:** `planner_runs` needs `alembic upgrade head`. Green tests don't prove it
  (tests use `create_all`). The checkpoint tables appear in the dev DB on the first
  planner request. Downgrade drops `planner_runs` only and leaves the checkpoint tables.
- **Behaviour that must stay unchanged:** the script's output (3 tests), the graph and
  nodes (no change to `app/agent/graph.py`, `nodes.py`, `state.py`), and every existing
  endpoint.
- **External services:** none. The planner calls no Claude, Voyage or Overpass, and
  `test_agent_package_imports_no_network_client` keeps guarding that.
- **Pool connections:** the pool holds a few connections to the dev DB per server
  process. With `fastapi dev` reloads, an old pool closes with its process. Keep the pool
  small (`max_size` around 5).

## Out of scope (copied from the ticket)
- The planner screen and diagram: ticket 018.
- Streaming each node to the browser while it runs (SSE, websockets): the trace in the
  response is enough.
- Cleaning up old runs: revisit in Stage 7.
- Login or per-member identity: the share code stays the only access.
- Rate limiting: the planner calls no paid API.
