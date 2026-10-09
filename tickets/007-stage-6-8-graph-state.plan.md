# Plan for 007: Stage 6.8, the trip planner's state, and nothing else

**Ticket:** `tickets/007-stage-6-8-graph-state.md`
**Approach:** Add `langgraph` (the user runs `uv add`), then a new `app/agent/` package whose
`state.py` defines `TripState` as a `TypedDict`. The state holds only plain, JSON-safe values
(ids, strings, numbers, lists and dicts). The database session travels outside the state, in
LangGraph's **runtime context** (`StateGraph(TripState, context_schema=PlannerContext)`, passed
with `graph.invoke(..., context=PlannerContext(db=db))`). Playground step `6.8` compiles a
zero-node graph (`START → END`), invokes it with an initial state and prints the state that
comes back.

**Alternatives considered:**
- *Pydantic `BaseModel` state:* it validates every update, but it puts model instances into
  the checkpoint (ticket 010), and the checkpointer then has to deserialize our classes. A
  `TypedDict` is a plain dict at run time, which is LangGraph's default style and what the
  ticket prefers.
- *The db session in `config["configurable"]`:* that works, but it's the pre-1.0 way.
  `config_schema` is deprecated since LangGraph 1.0 in favour of `context_schema`
  (`langgraph/graph/state.py:225-228` in 1.2.14), and context is typed (`Runtime[PlannerContext]`).
- *A Session inside the state:* this is ruled out by the ticket. It's not serializable, so
  the checkpointer in ticket 010 can't save it.

## Ticket check
LangGraph has been checked **before installing**: `uv add langgraph` was resolved in a
scratch copy of `backend/` (`pyproject.toml` + `uv.lock`), not in the repo.
- It resolves to **langgraph 1.2.14** (+ `langgraph-checkpoint` 4.2.0, `langgraph-prebuilt`
  1.1.0, `langgraph-sdk` 0.4.6). `pgvector` stays at **0.3.6** and `langchain-core` stays at
  **1.6.8**, so the `pgvector<0.4` pin isn't touched (AC 1). If `uv add` picks a newer
  version on the day, check the APIs below again.
- In 1.2.14 (read from the installed source): `StateGraph(state_schema, context_schema=None, *, input_schema, output_schema)`;
  `compile(checkpointer=None, *, interrupt_before, interrupt_after, ...)`;
  `invoke(input, config=None, *, context=None, ...)`; `Runtime` (`langgraph.runtime`) has
  `.context`, `.store` and `.stream_writer`; `START` and `END` come from `langgraph.graph`.
  An edge `START → END` passes `validate()` (an edge can end at `END`, `state.py:1167`).
- The types the ticket lists exist as described: `Member` (model), `Preferences` (Protocol),
  `SearchFilters` and `MergeResult` (dataclasses), `GroupSearchResponse` and
  `GroupSectorMatch` (Pydantic), and `find_stays_near()` → `list[tuple[Stay, float]]`.
  **None of them goes into the state as is.** ORM rows and dataclasses become plain dicts
  (see `MemberPrefs` and `Candidate` below).
- "No folder for agent code": correct. `app/agent/` is new (ticket decision).
- Baseline: **127 tests** once ticket 014 is delivered (it goes in before this ticket:
  126 at `f39f725` − 3 deleted + 4 new). Count again before starting with
  `uv run pytest --collect-only -q`.
- Ticket 014 changes the playground this ticket extends: steps 6.3 and 6.6 are gone,
  `STEPS` is `{"6.2", "6.4", "6.5"}`, and the new
  `tests/test_rag_chain.py::test_playground_offers_only_the_langchain_steps` asserts that
  exact list. Registering `"6.8"` breaks that assertion, so this ticket updates the test
  (see Tests).

## Before you start
- Ticket 014 is delivered (see the ticket check).
- **The user runs `uv add langgraph`** in `backend/` with the dev server stopped (the
  OneDrive "Access is denied" trap) before the developer agent starts. The developer agent
  doesn't run `uv add` / `uv sync`; the resulting `pyproject.toml` / `uv.lock` changes go
  into this ticket's single commit.
- Never run two pytest runs at once (they deadlock on `cragmatch_test`). Use the process
  check from plan 005 ("Before you start"); it must print nothing. Run pytest in the
  foreground.
- No network: these nodes and graphs call no Claude, Voyage or Overpass.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. langgraph installed, the trip planner's state and a zero-node graph
**Files** (in build order: migration, backend, frontend; no migration, no frontend):
- `backend/pyproject.toml`, `backend/uv.lock`: written by the user's `uv add langgraph`
  (see "Before you start"). Nothing else changes in them.
- `backend/app/agent/__init__.py` (new, empty).
- `backend/app/agent/state.py` (new):
  - **Module docstring**, the explanation (AC 5), about 12 lines: the state is the one dict
    every node reads and writes; a node returns **only the keys it changes** (a partial
    update) and LangGraph merges it into the state; by default a new value **replaces** the
    old one, and a *reducer* (`Annotated[list[int], operator.add]`) says "combine instead",
    e.g. append to a list (none is needed yet, ticket 010 adds the first); the state must be
    plain data because the checkpointer (ticket 010) saves it between steps; things that
    aren't data, like the database session, travel in the runtime context instead.
  - `class MemberPrefs(TypedDict)`: `name: str`, `grade_min: str | None`,
    `grade_max: str | None`, `max_distance_km: float | None`,
    `max_approach_minutes: int | None`, `styles: list[str]`. The same fields as the
    `Preferences` protocol, so `SimpleNamespace(**prefs)` satisfies it (comment: why).
  - `class Candidate(TypedDict)`: `sector_id: int`, `sector_name: str`, `crag_name: str`,
    `style: str`, `grade_min: str`, `grade_max: str`, `approach_minutes: int | None`,
    `distance_km: float`. Comment: the part of a `GroupSectorMatch` the planner needs; ids
    and values, no ORM row.
  - `class TripPlan(TypedDict)`: `sector: Candidate`, `checkin: str`, `checkout: str`,
    `nights: int`, `guests: int`, `stays: list[dict]`, `links: dict[str, str]`. Written by
    `propose_plan` (ticket 010).
  - `class TripState(TypedDict, total=False)`. Each field has a comment saying **who writes
    it** (AC 3); `total=False` because nodes fill it in over time:
    - `share_code: str`: the caller (initial state).
    - `checkin: str`: the caller. An ISO date: plain data for the checkpointer.
    - `nights: int`: the caller.
    - `guests: int`: the caller, or `merge_preferences` (number of members) when not set.
    - `members: list[MemberPrefs]`: `merge_preferences`.
    - `filters: dict | None`: `merge_preferences` (`dataclasses.asdict(SearchFilters)`);
      `None` = no common ground.
    - `conflicts: list[str]`: `merge_preferences`.
    - `candidates: list[Candidate]`: `search_sectors`.
    - `chosen_sector: Candidate | None`: `search_sectors` (top result, a fixed rule until
      ticket 010 moves it to `pick_sector`).
    - `stays: list[dict]`: `find_stays` (`NearbyStay` dumped to JSON-safe dicts).
    - `plan: TripPlan | None`: `propose_plan`.
  - `@dataclass class PlannerContext`: `db: Session`. Docstring: runtime context, given
    to every node as `runtime.context`, **never saved by the checkpointer**, so it has to
    be passed again on every `invoke` (including a resume in ticket 010).
  - `def initial_state(share_code: str, checkin: date | None = None, nights: int = 2, guests: int | None = None) -> TripState`:
    returns `{"share_code": share_code.upper(), "checkin": (checkin or next_saturday()).isoformat(), "nights": nights}`,
    plus `"guests"` only when it's given. Same defaults as `GET /groups/{code}/sectors/{id}/stays`
    (2 nights, next Saturday; `.upper()` like `get_group`).
- `backend/app/scripts/rag_playground.py`:
  - `__main__`: `STEPS[step](*sys.argv[2:])`, so steps can take an argument (a share code
    from ticket 008 on). Keep the unknown-step branch as it is (usage line listing `STEPS`,
    exit code 1): ticket 014 relies on it for 6.3 / 6.6. Update the usage line (`<step> [args]`)
    and the module docstring examples.
  - New `step_6_8(share_code: str = "9JS3VA3C")`: build
    `StateGraph(TripState, context_schema=PlannerContext)`, add `START → END`, compile,
    then `with SessionLocal() as db: result = graph.invoke(initial_state(share_code), context=PlannerContext(db=db))`.
    Print the initial state and the result with `pprint`, plus one line: "Same dict: no
    node ran, so nothing changed." Register `"6.8"` in `STEPS`.
- `README.md`: add `agent/` with the line `state.py  TripState (what flows through the trip planner), PlannerContext (db session), initial_state()`.
  Put it under `rag/` with a heading line "Stage 6 LangGraph trip planner.". In the
  `rag_playground.py` line (after ticket 014: "Stage 6 steps 6.2, 6.4, 6.5, one function per
  step"), add the trip planner steps from 6.8 on and mention that steps can take an argument.

**Reuses:** `next_saturday()` (`services/stays.py`), `SessionLocal` (as in the playground's
other steps), the `Preferences` field list (`services/group_matching.py`).

**Tests:** `tests/test_agent_graph.py` (new, no DB fixture needed), plus the existing suite,
which must stay green with langgraph installed (AC 1):
- `test_initial_state_defaults_to_next_saturday_and_two_nights`: `initial_state("ab12")` gives
  `share_code == "AB12"`, `nights == 2`, `checkin == next_saturday().isoformat()`, and no
  `guests` key. (AC 2)
- `test_initial_state_is_plain_json`: `json.dumps(initial_state("x", date(2026, 11, 7), 3, 4))`
  doesn't raise. This is the guard for "no ORM objects in the state". (AC 2, ticket note)
- `test_empty_graph_returns_the_initial_state`: a `START → END` graph on `TripState` with
  `context_schema=PlannerContext`, invoked with `context=PlannerContext(db=None)`, returns
  a dict equal to the input. (AC 4)
- Update `tests/test_rag_chain.py::test_playground_offers_only_the_langchain_steps` (from
  ticket 014): instead of `list(STEPS) == ["6.2", "6.4", "6.5"]`, assert that `"6.3"` and
  `"6.6"` are not in `STEPS` and that `{"6.2", "6.4", "6.5"} <= set(STEPS)`. That keeps 014's
  point (the comparison steps stay gone) without having to edit the test again in 008–010,
  which each add playground steps. Same name, same count.

**Expected suite:** 130 passed (127 after ticket 014 is delivered as planned + 3 new).

**Check by hand:**
- `uv run python -c "import importlib.metadata as m; print(m.version('langgraph'), m.version('pgvector'), m.version('langchain-core'))"`
  → `1.2.14 0.3.6 1.6.8` (or a newer langgraph, with pgvector still 0.3.x). (AC 1)
- `git diff backend/uv.lock` adds only the `langgraph*` packages (plus `ormsgpack` /
  `xxhash` if they're new); no existing pin changes. (AC 1)
- `uv run python -m app.scripts.rag_playground 6.8` prints the same dict twice. (AC 4)
- `uv run python -m app.scripts.rag_playground 6.6` still prints the usage line (now
  listing 6.8) and exits with code 1.
- Read `state.py`: every field has a "who writes it" comment, and the docstring covers
  partial updates, merging and reducers. (AC 3, AC 5)

**Commit:** `Stage 6.8: add langgraph (pgvector pin unchanged) and the trip planner state (TypedDict of plain values, writer of each field), db session in the runtime context, zero-node graph in playground 6.8`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Full suite green with langgraph installed + version and `uv.lock` checks by hand |
| 2 | `TripState` fields; `test_initial_state_*` |
| 3 | "Who writes it" comments, read in review |
| 4 | `test_empty_graph_returns_the_initial_state` + playground 6.8 |
| 5 | `state.py` module docstring, read in review |

## Risks
- *`uv add` picks a langgraph newer than 1.2.14:* check the signatures listed in the ticket
  check against the installed source (`.venv/Lib/site-packages/langgraph/graph/state.py`)
  before writing `state.py`.
- *A `START → END` graph returning something other than the input* (for example `None` or
  only some keys): `validate()` accepts it, but it hasn't been run. If it doesn't return the
  input, use one pass-through node (`lambda state: {}`) and say so in the docstring of step
  6.8. AC 4 still holds ("no node changes anything").
- *`total=False` hides typos in keys:* nodes in 008 read with `state["key"]` for keys an
  earlier node must have written, so a typo fails loudly in tests.
- *Windows MAX_PATH:* `langsmith` has very long file names. The repo's `.venv` path is
  short enough (the project already imports it); don't move the venv deeper.
- *The dependency and the code land in one commit:* if the suite fails, check first whether
  it fails without `app/agent/` too (a dependency problem, AC 1) before debugging the new code.
- *Ticket 014's exact-list playground test:* it fails as soon as `"6.8"` is registered.
  Loosen it as described under Tests; don't delete it.

## Out of scope (copied from the ticket)
- Nodes (ticket 008) and edges (ticket 009).
