# Plan for 010: Stage 6.11, human-in-the-loop: pause for the group's approval

**Ticket:** `tickets/010-stage-6-11-human-in-the-loop.md`
**Approach:** The graph is completed and gets its pause in one go. Choosing a sector becomes
its own `pick_sector` node (first candidate not yet rejected, at most 3 proposals), and a
`propose_plan` node builds the final plan with booking links. A new `approve_sector` node,
placed between `pick_sector` and `find_stays`, calls LangGraph's `interrupt()`. The graph is
compiled with an `InMemorySaver` checkpointer, and the run is resumed with
`Command(resume={"approved": ..., "reason": ...})` on the same thread id. A rejection is
recorded through the state's first **reducer** and loops back to `pick_sector`.

**Alternatives considered:**
- *`compile(interrupt_before=["find_stays"])` (a static interrupt):* the graph would stop,
  but the group's answer would have to be written in with `graph.update_state(...)` before
  resuming, and the approve/reject branch would be split across the caller and the graph.
  `interrupt()` inside a node sends the sector to the caller, receives the answer as the
  function's return value, and keeps the branch in the graph. In LangGraph 1.x, static
  interrupts are mainly meant for debugging (stepping through a graph); `interrupt()` is the
  human-in-the-loop tool. The difference goes into the `graph.py` docstring (ticket note).
- *Ending the run on the first rejection:* the ticket's suggested default is "next candidate,
  at most 3, then end with no plan". This plan follows that default (the open question is
  non-blocking). The limit is one constant, `MAX_PROPOSALS`.
- *Placing the pause before `propose_plan` (the raw request's wording):* AC 1 and AC 4 say
  "before stays are looked up", so the pause goes before `find_stays`. Otherwise stays
  would be fetched for a sector that is later rejected.

## Ticket check
Read in the source of the version that `uv add langgraph` resolves to (1.2.14, checkpoint
4.2.0; see plan 007):
- In-memory checkpointer: `from langgraph.checkpoint.memory import InMemorySaver`
  (`MemorySaver` is kept only as a backwards-compatible alias, `memory/__init__.py:625`).
- `interrupt(value, *, response_schema=None)` (`langgraph/types.py:893`). The first call
  raises `GraphInterrupt` and the run stops. On resume, **the node runs again from its first
  line**, and `interrupt()` returns the resume value. With a Pydantic `response_schema`, the
  resume value is validated and returned as that model. It requires a checkpointer.
- `Command(resume=...)` (`types.py:833`) is passed as the *input* of `invoke` / `stream`.
- A paused `invoke` returns the state plus the key `"__interrupt__"`, a tuple of
  `Interrupt(value=..., id=...)`. `graph.get_state(config)` returns a `StateSnapshot` with
  `.values` and `.next` (the node that will run on resume).
- The checkpoint serializer allows any module by default and warns, unless
  `LANGGRAPH_STRICT_MSGPACK=true` (`serde/jsonplus.py:92-114`). Our state is plain dicts,
  lists, strings and numbers, so this never comes into play. The `Approval` model is a
  resume value, never put in the state.
- "No checkpointer" today: correct. `build_trip_planner(checkpointer=None)` from plan 009
  already passes it to `compile()`.
- Booking links: `airbnb_url()`, `booking_url()` and `next_saturday()`
  (`services/stays.py:59-89`): correct. `BookingLinks` (`schemas/stay.py:25`) already has
  the shape `{airbnb, booking}`.

## Before you start
- Ticket 014 and plans 007–009 are delivered. The "Planner demo" group exists in the dev DB
  (plan 008).
- One pytest run at a time (the process check in plan 005), in the foreground. No network.
- Every graph test with a checkpointer uses a **new** `InMemorySaver()` and a new
  `thread_id = str(uuid4())`, so checkpoints can't leak between tests.
- `PlannerContext` isn't saved in checkpoints: **pass `context=` again on every call**, and
  on a resume too. A resume without it fails in the first node that touches `runtime.context.db`.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. pick_sector, approve_sector (interrupt + checkpointer) and propose_plan: the graph pauses for approval and ends with a plan
**Files** (in build order: migration, backend, frontend; no migration, no frontend):
- `backend/app/agent/state.py`:
  - `class Rejection(TypedDict)`: `sector_id: int`, `reason: str`.
  - New fields:
    - `rejections: Annotated[list[Rejection], operator.add]`: `approve_sector`. Comment:
      **the first reducer**. A node returns only the *new* rejection, and `operator.add`
      appends it to the list instead of replacing it.
    - `approved: bool | None`: `approve_sector`.
  - Update comments: `chosen_sector` is now written by `pick_sector`; `message` also by
    `pick_sector`; `plan` by `propose_plan`.
  - Module docstring: the reducer paragraph now points at `rejections`.
  - `class Approval(BaseModel)` with `approved: bool` and `reason: str | None = None`.
    Docstring: the group's answer, i.e. the resume value. It's validated by
    `interrupt(response_schema=Approval)` and never stored in the state.
- `backend/app/agent/nodes.py`:
  - `search_sectors` stops writing `chosen_sector` (it returns only `candidates`). When
    `response.results` is empty, it also writes `message = response.message` ("The group
    agrees on filters, but no sector matches them.").
  - `MAX_PROPOSALS = 3`. Comment: the ticket's default; after three rejections, the group
    should change its preferences, not keep clicking "no".
  - `def pick_sector(state) -> dict`. Pure: no DB, no `runtime`.
    - `rejected = {r["sector_id"] for r in state.get("rejections", [])}`.
    - If `len(rejected) >= MAX_PROPOSALS`: `{"chosen_sector": None, "message": f"No plan: the group turned down {len(rejected)} sectors."}`.
    - Otherwise, the first candidate whose id isn't in `rejected` →
      `{"chosen_sector": c, "approved": None}`.
    - Otherwise (nothing left): `{"chosen_sector": None}` plus
      `"message": state.get("message") or "No plan: every candidate was turned down."`.
  - `def approve_sector(state) -> dict`:
    - `chosen = state["chosen_sector"]`.
    - `decision = interrupt({"question": "Plan the trip around this sector?", "sector": chosen}, response_schema=Approval)`.
    - Approved → `{"approved": True}`; rejected →
      `{"approved": False, "rejections": [{"sector_id": chosen["sector_id"], "reason": decision.reason or ""}]}`.
    - **Why-comment:** on resume, this function runs again from the top, so nothing before
      `interrupt()` may have side effects (no DB writes, no prints that matter).
  - `def _sector_with_crag(db, sector_id) -> Sector | None`: `db.get(Sector, sector_id)`.
    `find_stays` uses it (refactor, same behaviour) and so does `propose_plan`.
  - `def propose_plan(state, runtime) -> dict`: loads the sector (`None` →
    `{"plan": None, "message": "No plan: the chosen sector no longer exists."}`), then
    `checkin = date.fromisoformat(state["checkin"])` and
    `checkout = checkin + timedelta(days=state["nights"])`. The links are
    `BookingLinks(airbnb=airbnb_url(lat, lon, checkin, checkout, guests), booking=booking_url(crag.name, lat, lon, checkin, checkout, guests)).model_dump()`,
    exactly the arguments of `group_sector_stays`. Returns `{"plan": TripPlan(...), "message": None}`.
- `backend/app/agent/graph.py`:
  - `def route_after_pick(state) -> Literal["approve_sector", "__end__"]`:
    `"approve_sector"` if `state.get("chosen_sector")` else `END`.
  - `def route_after_approval(state) -> Literal["find_stays", "pick_sector"]`:
    `"find_stays" if state.get("approved") else "pick_sector"`.
  - Edges: the plan 009 edge `search_sectors → find_stays` is replaced by
    `search_sectors → pick_sector`; then `pick_sector -(route_after_pick)→ approve_sector | END`;
    `approve_sector -(route_after_approval)→ find_stays | pick_sector`;
    `find_stays → propose_plan → END`. The `merge_preferences` branch and
    `explain_conflicts → END` stay as in plan 009.
  - **Docstring, a "Pausing" section** (AC 5), about 12 lines:
    - The checkpointer saves the state after every step, under the run's `thread_id`.
    - `interrupt()` stops the node; LangGraph saves a checkpoint with the pending question,
      and `invoke` **returns**. "Paused" means that the Python call has finished and
      nothing keeps running; only the saved checkpoint is left.
    - A resume is a new `invoke(Command(resume=...))` with the same `thread_id`: LangGraph
      loads the last checkpoint, skips the steps that already ran, and **re-runs the
      interrupted node from its first line**; this time `interrupt()` returns the answer.
    - The state must be serializable because the checkpointer stores it (in memory here,
      a database in Stage 7). The context (db session) isn't stored, so it's passed again.
    - `interrupt()` vs `interrupt_before` (see Alternatives).
- `backend/app/scripts/rag_playground.py`:
  - `step_6_9c`: its line becomes `merge → search → pick_sector → find_stays`, with a printed
    note that picking moved out of search in 6.11. Without it, `find_stays` gets no
    `chosen_sector` and the step shows no stays.
  - `step_6_10`: compiles `build_trip_planner(InMemorySaver())` and uses a new thread id per
    share code. When the stream yields `__interrupt__`, it prints
    `paused at approve_sector (step 6.11 answers it)`. Without a checkpointer, a group with
    common ground would now reach `interrupt()` and fail.
  - `step_6_11(share_code, *answers)`, for example `6.11 <code> "no:too far" yes`. It builds
    `build_trip_planner(InMemorySaver())` with a new thread id, invokes, and prints the
    `__interrupt__` value. It prints `graph.get_state(config).next` and
    `.values["chosen_sector"]`, notes that there's no `stays` key, then resumes with each
    answer in turn (`yes` → approved; `no:<reason>` → rejected) and prints what happened
    after each. It prints `plan` or `message` at the end. Register `"6.11"`.
- `README.md`: in the `agent/graph.py` line, add "pauses at approve_sector (interrupt +
  InMemorySaver)".

**Reuses:** `airbnb_url()`, `booking_url()`, `BookingLinks`, `find_stays_near()` (via
`find_stays`); `build_trip_planner(checkpointer)`, `route_after_merge` and
`explain_conflicts` from plan 009; the factories in `tests/conftest.py` (plan 008).

**Tests:**
- `tests/test_agent_nodes.py`:
  - Update `test_search_returns_candidates_best_first_and_picks_the_top` →
    `test_search_returns_candidates_best_first`: no `chosen_sector` key any more.
    `test_search_without_matching_sectors_chooses_nothing` now asserts no `chosen_sector`
    key and the search's `message`.
  - `test_pick_sector_takes_the_first_candidate`, `test_pick_sector_skips_rejected_sectors`,
    `test_pick_sector_stops_after_three_rejections` (5 candidates, 3 rejections → `None` and
    the message), `test_pick_sector_with_nothing_left_keeps_the_search_message`. All on plain
    dicts. (AC 4 rule)
  - `test_propose_plan_has_dates_guests_stays_and_links`: checkin `2026-11-07`, 2 nights, 3
    guests → `checkout == "2026-11-09"`; `links["airbnb"]` contains `checkin=2026-11-07` and
    `adults=3`; `links["booking"]` contains `group_adults=3`; `json.dumps(plan)` works.
  - `test_approve_sector_records_a_rejection`: patch `app.agent.nodes.interrupt` to return
    `Approval(approved=False, reason="x")` → the update has one rejection
    (`{"sector_id": ..., "reason": "x"}`) and `approved=False`. (AC 4, node in isolation)
  - `test_approve_sector_records_an_approval`: the same patch returning
    `Approval(approved=True)` → the update is `{"approved": True}`, no `rejections` key. (AC 3,
    node in isolation)
- `tests/test_agent_graph.py`:
  - Update `test_line_of_three_nodes_ends_with_stays` → `test_line_of_four_nodes_ends_with_stays`:
    the line is `merge → search → pick_sector → find_stays` (search no longer picks); same
    assertions.
  - Update `test_graph_with_common_ground_runs_merge_search_stays`: compile with a new
    `InMemorySaver()` and thread id; stream until the pause, then resume with
    `Command(resume={"approved": True})`. The node names across both streams (ignoring the
    `__interrupt__` chunk; `approve_sector`'s update arrives on the resume) are
    `[merge_preferences, search_sectors, pick_sector, approve_sector, find_stays, propose_plan]`,
    and `plan` has the sector and the stays. **Its comparison with the plan 008 line no
    longer holds** (the graph has more nodes). Compare the shared keys (`filters`,
    `candidates`, `stays`) with `test_line_of_four_nodes_ends_with_stays`' line instead.
  - Fixture `paused_run` (a factory group with common ground, two matching sectors at
    different crags, a stay near each; a new `InMemorySaver` and `thread_id`). It returns
    `(graph, config, context, first_output)`:
    - `test_run_pauses_at_approval_with_the_proposed_sector`: `"__interrupt__"` in the
      output; the interrupt value's `sector["sector_id"]` is the closer sector. (AC 1)
    - `test_paused_state_has_the_sector_and_no_stays`: `get_state(config).next == ("approve_sector",)`;
      `values["chosen_sector"]` is set; `"stays"` and `"plan"` are not in `values`. (AC 2)
    - `test_approve_resumes_and_produces_a_plan`: `invoke(Command(resume={"approved": True}), config, context=context)`
      → `plan["sector"]["sector_id"]` is the proposed sector, `plan["stays"]` isn't empty,
      and there's no `"__interrupt__"`. (AC 3)
    - `test_resume_does_not_run_merge_or_search_again`: monkeypatch
      `app.agent.nodes.find_group` and `app.agent.nodes.search_for_group` with counting
      wrappers around the real functions *before* the first invoke. After pause + approve,
      each was called exactly once. (AC 3)
    - `test_reject_proposes_the_next_sector`: resume with
      `{"approved": False, "reason": "too far"}` → pauses again; the new interrupt's sector
      is the second sector; `values["rejections"] == [{"sector_id": first, "reason": "too far"}]`;
      no `stays`. (AC 4)

**Expected suite:** 163 passed (151 after tickets 014 and 007–009 are delivered as planned +
12 new: 7 in `test_agent_nodes.py`, 5 in `test_agent_graph.py`; the four updated tests keep
the count).

**Check by hand:**
- `uv run python -m app.scripts.rag_playground 6.11 <Planner demo code> "no:too crowded" yes`
  → pauses on Collbató, prints `next=('approve_sector',)` and no stays; after the "no" it
  pauses on Can Marges; after "yes" it prints a plan with stays near Siurana and links for
  next Saturday. (AC 1–4)
- Open both links from that plan in a browser: Airbnb and Booking open on the Siurana area,
  next Saturday, 3 adults.
- `… 6.11 9JS3VA3C` → no pause: it goes through `explain_conflicts`.
- `… 6.10 9JS3VA3C <Planner demo code>` → the diagram shows `approve_sector` and the loop back
  to `pick_sector`; the second group stops with `paused at approve_sector`.
- `… 6.9c <Planner demo code>` still ends with stays near Montserrat.
- Read the "Pausing" section of the `graph.py` docstring. (AC 5)

**Commit:** `Stage 6.11: the trip planner pauses for the group's approval before stays are looked up (interrupt in approve_sector, InMemorySaver checkpointer), pick_sector proposes the first candidate not rejected (at most three), a rejection loops back through a reducer, propose_plan builds dates, guests, stays and booking links`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_run_pauses_at_approval_with_the_proposed_sector` |
| 2 | `test_paused_state_has_the_sector_and_no_stays` |
| 3 | `test_approve_resumes_and_produces_a_plan`, `test_resume_does_not_run_merge_or_search_again`, `test_approve_sector_records_an_approval` |
| 4 | `test_pick_sector_*`, `test_reject_proposes_the_next_sector`, `test_approve_sector_records_a_rejection` |
| 5 | "Pausing" section of the `graph.py` docstring, read in review |

## Risks
- *Code before `interrupt()` runs twice:* the node reads state only. Review checks for this.
- *Forgotten `context=` on resume:* it fails loudly (an `AttributeError` on `None`). The
  tests always pass it, and the docstring says why.
- *Tests and playground steps from plans 008/009 change* (search no longer picks; the graph
  pauses, so a run with common ground needs a checkpointer): the four updated tests and the
  6.9c / 6.10 playground changes are listed above. They're updated, not deleted.
- *The `response_schema` argument is new in recent versions:* if the installed langgraph
  doesn't have it, validate by hand with `Approval.model_validate(interrupt(...))`. The
  behaviour is the same.
- *An in-memory checkpointer loses paused runs when the process exits:* expected; a
  persistent one is Stage 7.
- *Size:* the largest of the Stage 6 deliveries (three nodes, two routing functions, a
  checkpointer, 12 new and 4 updated tests). Build in the files-list order and run
  `tests/test_agent_nodes.py` once the nodes exist, before wiring the graph, so node bugs and
  graph bugs show up separately.

## Out of scope (copied from the ticket)
- A persistent checkpointer (Postgres): a Stage 7 question.
- An API or UI to approve: ticket 011 decides how a group runs it.

## Decision taken on the open question
- On rejection: **next candidate, at most 3 proposals, then end with "no plan"** (the
  ticket's suggested default; `MAX_PROPOSALS = 3`). Change the constant if the user decides
  otherwise.
