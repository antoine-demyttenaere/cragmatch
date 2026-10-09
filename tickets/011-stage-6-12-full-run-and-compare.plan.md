# Plan for 011: Stage 6.12, full run on a real group, then compare with the sketch

**Ticket:** `tickets/011-stage-6-12-full-run-and-compare.md`
**Approach:** A new script, `app/scripts/trip_planner.py`, runs the planner from plan 010 with
`graph.stream(..., stream_mode="updates")`, which yields one `{node: partial_update}` per
step. Those chunks drive both the node-by-node trace and the approval prompt (a
`"__interrupt__"` chunk). The logic sits in a `run_planner()` function that receives its
"ask the group" function as a parameter, so tests can answer without a terminal. Once the
script works, it's run on both demo groups and "Built vs sketched" is written into ticket 006,
in the same delivery.

**Alternatives considered:**
- *Print statements inside the nodes for the trace:* the nodes would mix logging with logic,
  and the trace would show up in tests too. `stream_mode="updates"` already reports which
  node ran and what it changed (ticket note).
- *An API endpoint plus an approval screen:* the ticket's suggested default is no endpoint in
  Stage 6 (non-blocking open question). A terminal script is enough for "a group can run
  it", and an endpoint needs the persistent checkpointer from Stage 7. This plan follows
  that default.
- *`input()` called directly inside `run_planner`:* that can't be tested without
  monkeypatching `builtins.input`. Passing the function in (`ask=`) keeps it simple.

## Ticket check
- "The full graph from ticket 010": as planned in 010. Nodes `merge_preferences`,
  `explain_conflicts`, `search_sectors`, `pick_sector`, `approve_sector`, `find_stays`,
  `propose_plan`; the run pauses inside `approve_sector`.
- **"Checkpoint demo (`9JS3VA3C`)" can show only one of the two paths of AC 2:** it has no
  common ground (Ana 5+–6b vs Marc 7a–8a). The common-ground run uses the "Planner demo"
  group from plan 008 (Ana 6a–6c/130 km, Lia 6a–7a/150 km/sport, Antonio
  6b–7a+/150 km/30 min/sport).
- `max_approach_minutes` on members (ticket 001): correct. It's in `MemberPrefs` (plan 007)
  and used by `search_for_group` through `why_not()`, so Antonio's 30-minute limit really
  filters (Agulles, 45 min, would be out even if its style matched).
- `stream_mode="updates"` in 1.2.14: each chunk is `{node_name: update}`. A pause arrives
  as a chunk `{"__interrupt__": (Interrupt(value=...),)}` (the example in the `interrupt()`
  docstring, `langgraph/types.py`). The node that paused emits no update of its own.

## Before you start
- Ticket 014 and plans 007–010 are delivered; "Planner demo" exists in the dev DB.
- One pytest run at a time (the process check in plan 005), in the foreground. No network.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. The trip_planner script with a node-by-node trace, full runs, and "Built vs sketched" in ticket 006
**Files** (in build order: migration, backend, frontend; no migration, no frontend; the
ticket 006 section last, because it needs the script's output):
- `backend/app/scripts/trip_planner.py` (new). Module docstring: usage,
  `uv run python -m app.scripts.trip_planner <share_code> [--checkin YYYY-MM-DD] [--nights N] [--guests N]`,
  and the fact that the paused run lives in memory only (Ctrl+C loses it).
  - `def describe_update(node: str, update: dict | None) -> str`: pure; returns
    `"merge_preferences: members, filters, conflicts, guests"`, or `"<node>: (no change)"`
    for an empty or `None` update.
  - `def run_planner(db: Session, share_code: str, ask: Callable[[dict], Approval], out: Callable[[str], None] = print, checkin: date | None = None, nights: int = 2, guests: int | None = None) -> dict`:
    - `graph = build_trip_planner(InMemorySaver())`;
      `config = {"configurable": {"thread_id": str(uuid4())}}`;
      `context = PlannerContext(db=db)`;
      `next_input = initial_state(share_code, checkin, nights, guests)`.
    - Loop: stream `next_input` with `stream_mode="updates"`. For each chunk, either keep
      the interrupt value (`chunk["__interrupt__"][0].value`) or `out(describe_update(node, update))`.
      When the stream ends without an interrupt, stop. Otherwise call
      `decision = ask(question)`, `out(f"approve_sector: {'approved' if decision.approved else 'rejected: ' + (decision.reason or '')}")`,
      and set `next_input = Command(resume=decision.model_dump())`.
    - Return `graph.get_state(config).values`.
    - Comment: one thread id per run, and `context` passed on every resume (see plan 010).
  - `def ask_in_terminal(question: dict) -> Approval`: prints the sector on one line
    (`name, crag, grades, style, distance, walk-in`), `input("Approve this sector? [y/n] ")`;
    on "n", `input("Why not? ")`. Anything other than `y`/`yes` counts as no.
  - `def format_plan(state: dict) -> str`: if there's a `plan`, show the sector and crag,
    check-in to check-out, guests, up to five stays (`name, type, km`) and both links.
    Otherwise `state["message"]`.
  - `main()`: `argparse` (`share_code`; `--checkin` parsed with `date.fromisoformat`; a past
    date → exit with "checkin can't be in the past", same rule as the stays endpoint;
    `--nights` 1–30; `--guests` ≥ 1). Inside `with SessionLocal() as db`, call
    `run_planner(db, ..., ask=ask_in_terminal)`, then print `format_plan`. A `ValueError`
    (unknown share code from `merge_group_preferences`) → print it and `sys.exit(1)`.
- `README.md`: under `scripts/`, `trip_planner.py  Run the Stage 6 trip planner on a group in the terminal (trace, approval, final plan).`
- `tickets/006-stage-6-7-why-a-graph.md`: a new section `## Built vs sketched` after
  `## Sketch` (leave the sketch itself unchanged). It contains:
  - The `draw_mermaid()` output of `build_trip_planner()` in a mermaid block, so the two
    diagrams sit next to each other.
  - **Matched:** the steps and decision points that ended up as nodes and conditional edges
    under the same names.
  - **Changed, and why:** at least these points, if they hold for the delivered code:
    `search_sectors` stopped picking a sector (it moved into `pick_sector` so a rejection
    can loop back); the pause sits *inside* `approve_sector` (`interrupt()`) instead of
    being a separate wait; members are copied into the state (a paused run doesn't change
    if the group is edited); there's an extra stop when nothing is left to propose; the
    database session lives in the runtime context, not the state; strict search merges the
    preferences again internally.
  - **The two traces** (from the full runs below, shortened): one with common ground and a
    rejection, one without.

**Reuses:** `build_trip_planner()`, `initial_state()`, `PlannerContext`, `Approval`
(`app/agent/`), `SessionLocal`, `InMemorySaver`, `Command`;
`build_trip_planner().get_graph().draw_mermaid()` for the ticket 006 diagram.

**Tests:** `tests/test_trip_planner_script.py` (new; factory fixtures from `tests/conftest.py`).
The ticket 006 section is documentation and adds no test.
- `test_describe_update_lists_the_changed_fields` and `test_describe_update_without_changes`.
  (AC 3)
- `test_run_planner_approves_and_returns_a_plan`: a group with common ground, two sectors,
  stays; `ask` returns `Approval(approved=True)`. The result has a `plan` with stays; `ask`
  was called once; the `out` lines, in order, start with `merge_preferences:`,
  `search_sectors:`, `pick_sector:`, `approve_sector: approved`, `find_stays:`,
  `propose_plan:`. (AC 1, 3)
- `test_run_planner_reject_then_approve_uses_the_second_sector`: `ask` answers no, then
  yes → `plan["sector"]` is the second sector. (AC 1)
- `test_run_planner_without_common_ground_never_asks`: members 5–6a vs 7a–8a. `ask` is
  never called, there's no `plan`, the `message` contains the conflict, and the trace is
  `merge_preferences:`, `explain_conflicts:`. (AC 2)
- `test_format_plan_shows_links_or_the_message`: a hand-built state with a `plan`, and one
  with only a `message`.

**Expected suite:** 169 passed (163 after tickets 014 and 007–010 are delivered as planned +
6 new in `test_trip_planner_script.py`).

**Check by hand:**
- `uv run python -m app.scripts.trip_planner <Planner demo code>`: the trace lines, a
  prompt about Collbató; answer `n`, then `too close to the city`. Next, a prompt about Can
  Marges; answer `y`. Then the plan with Siurana stays and two links. (AC 1, 3)
- `uv run python -m app.scripts.trip_planner 9JS3VA3C`: `merge_preferences`, then
  `explain_conflicts`, then the conflict message, and no prompt. (AC 2)
- `uv run python -m app.scripts.trip_planner NOPE1234` → "No group with share code
  NOPE1234", exit code 1.
- The traces of the first two runs go (shortened) into "Built vs sketched". Ticket 006's
  Markdown preview shows both diagrams, and every "changed" bullet has a "why". (AC 2, AC 4)

**Commit:** `Stage 6.12: trip_planner script runs the planner in the terminal with a node-by-node trace from stream updates, asks the group to approve and prints the final plan; ticket 006 gets built vs sketched with the delivered diagram, what changed and why, and traces with and without common ground`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_run_planner_approves_and_returns_a_plan`, `test_run_planner_reject_then_approve_*`, hand run |
| 2 | `test_run_planner_without_common_ground_never_asks` + hand runs on both groups; traces in ticket 006 |
| 3 | `test_describe_update_*`, trace order in `test_run_planner_approves_*` |
| 4 | "Built vs sketched" in ticket 006, read in review |

## Risks
- *Interactive `input()` in the developer agent's shell:* the agent can't answer a prompt.
  The terminal hand runs are for the **user**. The agent relies on the tests (which
  inject `ask`), and for the ticket 006 traces the user pastes their two traces, or the
  agent produces them with a short `run_planner(..., ask=...)` call in `uv run python -c`.
- *The chunk format of `stream_mode="updates"` differs from what the plan expects:* print
  one raw chunk in a scratch run before writing `run_planner` and adjust the unpacking. The
  test on the trace order catches any mismatch. One known case: on a resume,
  `approve_sector` re-runs and emits its own update (`{"approved": ...}`), which
  `describe_update` would print as a second `approve_sector:` line next to the decision
  line. Skip `approve_sector` chunks in the trace (the decision line already reports them,
  with the reason), so the expected order in `test_run_planner_approves_*` holds.
- *Dev data drift:* the hand checks name Collbató / Can Marges for today's data only.
- *Ticket 006 written in the same commit as the code:* write it last, from the delivered
  graph, so the comparison describes the code being committed.

## Out of scope (copied from the ticket)
- An API endpoint or UI for the planner (see "Open questions").

## Decision taken on the open question
- **No web endpoint in Stage 6** (the ticket's suggested default): the terminal script meets
  "a group can run it". An endpoint fits Stage 7, together with a persistent checkpointer
  (ticket 013's non-blocking question).
