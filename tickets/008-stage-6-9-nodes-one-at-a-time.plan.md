# Plan for 008: Stage 6.9, add nodes one at a time

**Ticket:** `tickets/008-stage-6-9-nodes-one-at-a-time.md`
**Approach:** A new `app/agent/nodes.py` gets three nodes, built in this order:
`merge_preferences`, then `search_sectors`, then `find_stays`. Each one is a thin wrapper
that reads the state, calls the existing service with plain values and returns a partial
update. Playground steps `6.9a`, `6.9b` and `6.9c` each build a straight-line graph with one,
two and three nodes and print the state. A short refactor comes first, so the merge node can
load a group by share code without copying the router's query.

**Alternatives considered:**
- *Nodes reload the group from the database every time they need members:* that's
  simpler, but the state wouldn't show what the group asked for. Also, a group edited
  while a run is paused (ticket 010) would change under the run. Members are copied into
  the state once, as `MemberPrefs` dicts.
- *Putting the straight-line graph in `app/agent/graph.py` now:* ticket 009 replaces it with
  the routed graph. The three partial graphs are teaching steps, so they live in the
  playground, built by one helper.
- *A fourth `pick_sector` node now:* the ticket says three nodes, with "pick" as a fixed
  rule. `search_sectors` writes `chosen_sector = candidates[0]` and ticket 010 moves that
  rule into its own node.

## Ticket check
Verified against the code and the dev database (through the `cragmatch-db` MCP).
- `merge_preferences(members)`, `search_for_group(db, members, mode, fit)` and
  `find_stays_near(db, lat, lon, max_distance_km, stay_type=None)`: signatures correct.
  All three only *read attributes*, so `types.SimpleNamespace(**member_prefs)` works as a
  member.
- **Wrong: "a real group to run on: Checkpoint demo (`9JS3VA3C`)".** That group has **no
  common ground**: Ana 5+–6b, Marc 7a–8a, Lia 6a–7a, Antonio 6a–7a+. So AC 1 shows
  conflicts, and AC 2/3 would show *no* candidates and *no* stays. The happy path needs a
  second group. **The user creates it** in the web app ("Group trip" tab) or in `/docs`
  before the hand checks of this delivery (the tests don't need it):
  "Planner demo" with **Ana** 6a–6c, 130 km; **Lia** 6a–7a, 150 km, sport;
  **Antonio** 6b–7a+, 150 km, max walk-in 30 min, sport.
  The merge gives 6b–6c, ≤130 km, ≤30 min, sport. Strict search on today's dev data gives
  Collbató (Montserrat, 37 km, 9 stays within ~10 km) first, then Can Marges and Siuranella
  (Siurana, 106 km). Keep `9JS3VA3C` for the "no common ground" runs.
- `search_for_group` in strict mode **runs `merge_preferences()` again** and returns its own
  `common_ground` / `message`. The merge node is still needed: it's what ticket 009 routes on.
  The duplicate merge is cheap and pure.
- The router's `get_group` (`routers/groups.py:25`) is a FastAPI dependency that raises
  `HTTPException`, so a node can't use it. Its query moves to `services/groups.py` (the
  first step of this delivery).
- `find_stays_near` returns ORM pairs: they're converted with the existing `NearbyStay`
  schema (`schemas/stay.py:20`) and `.model_dump(mode="json")`, so enums become strings.

## Before you start
- Ticket 014 and plan 007 are delivered: `app/agent/state.py` (`TripState`, `MemberPrefs`,
  `Candidate`, `PlannerContext`, `initial_state`) exists, playground steps take arguments,
  and the playground `STEPS` test no longer pins an exact list (plan 007).
- One pytest run at a time (the process check in plan 005), in the foreground. No network.
- Nodes have the signature `def node(state: TripState, runtime: Runtime[PlannerContext]) -> dict`.
  LangGraph injects any parameter **named** `runtime` (`langgraph/_internal/_runnable.py:214`
  in 1.2.14). In tests, call a node directly with `Runtime(context=PlannerContext(db=db_session))`
  (`from langgraph.runtime import Runtime`; every field has a default).

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. Three nodes (merge, search, stays) on a reusable group lookup, one playground step per node
**Files** (in build order: migration, backend, frontend; no migration, no frontend):
- `backend/app/services/groups.py`: new `find_group(db: Session, code: str) -> Group | None`,
  the query from `get_group` (with `selectinload(Group.members)` and `code.upper()`).
  Docstring: `None` = no such group; the caller decides whether that's a 404 or a message.
- `backend/app/routers/groups.py`: `get_group` calls `find_group()` and keeps raising 404 on
  `None`. Behaviour unchanged.
- `backend/app/agent/nodes.py` (new). Module docstring: each node reads the state, calls an
  existing service and returns only the keys it changes; no matching or search logic lives
  here (AC 4).
  - **Helpers:**
    - `def _member_prefs(member: Member) -> MemberPrefs`: copies the six preference fields
      (`list(member.styles)`).
    - `def _as_members(prefs: list[MemberPrefs]) -> list[SimpleNamespace]`: why-comment: the
      services read attributes (the `Preferences` protocol), the state holds dicts.
    - `def _candidate(match: GroupSectorMatch) -> Candidate`: from `match.sector` (`id`,
      `name`, `crag.name`, `style.value`, grades, `approach_minutes`) and `match.distance_km`.
  - **Constants:**
    - `SEARCH_MODE: SearchMode = "strict"` and `FIT: FitMode = "overlap"`. Comment: the
      planner proposes a sector *everyone* can climb, so strict; overlap is the app's
      default fit.
    - `STAY_RADIUS_KM = 10` (the stays endpoint's default) and `MAX_STAYS = 5` (comment: a
      plan is a shortlist, and the state stays readable).
  - **Node 1:** `def merge_group_preferences(state, runtime) -> dict`:
    - `group = find_group(runtime.context.db, state["share_code"])`; `None` →
      `raise ValueError(f"No group with share code {state['share_code']}")`. A wrong code
      is bad input, not "no result", which matches `find_matching_sectors`.
    - `members = [_member_prefs(m) for m in group.members]`.
    - The update always has `members` and `conflicts`. It has `guests = max(len(members), 1)`
      only if `"guests" not in state` (same rule as the group stays endpoint).
    - No members → `filters=None`, `conflicts=["The group has no members yet."]` (comment:
      `merge_preferences([])` would say "no limits", but there's nobody to plan for).
    - Otherwise `merged = merge_preferences(_as_members(members))`;
      `filters = asdict(merged.filters) if merged.common_ground else None`,
      `conflicts = merged.conflicts`.
  - **Node 2:** `def search_sectors(state, runtime) -> dict`:
    `response = search_for_group(runtime.context.db, _as_members(state["members"]), SEARCH_MODE, FIT)`;
    `candidates = [_candidate(m) for m in response.results]`; returns `candidates` and
    `chosen_sector = candidates[0] if candidates else None`. Comment: picking the top result
    is a fixed rule until ticket 010 (approval) moves it into `pick_sector`.
  - **Node 3:** `def find_stays(state, runtime) -> dict`: `chosen = state.get("chosen_sector")`;
    `None` → `{"stays": []}`. Otherwise `sector = db.get(Sector, chosen["sector_id"])`
    (deleted since → `{"stays": []}`), then
    `find_stays_near(db, sector.crag.latitude, sector.crag.longitude, STAY_RADIUS_KM)[:MAX_STAYS]`,
    each as `NearbyStay(stay=stay, distance_km=round(d, 1)).model_dump(mode="json")`.
- `backend/tests/conftest.py` (new). Factory fixtures on the existing `db_session`, so agent
  tests build rows the way the nodes read them:
  - `make_group(name="Trip", members=[dict(...), ...]) -> Group`, with a generated share code
    (`generate_share_code(db_session)`).
  - `make_sector(name, grade_min, grade_max, style="sport", lat=41.60, lon=1.81, approach=None, crag="Montserrat") -> Sector`
    (one crag per distinct crag name).
  - `make_stay(name, lat, lon, type="campsite") -> Stay` (source `curated`).
- `backend/app/scripts/rag_playground.py`:
  - `def _run_line(share_code: str, *nodes: tuple[str, Callable]) -> dict`: builds
    `StateGraph(TripState, context_schema=PlannerContext)`, adds the nodes in order with
    `START → n1 → … → END`, invokes with `initial_state(share_code)` and
    `context=PlannerContext(db=db)` (`SessionLocal()` in a `with`), and returns the result.
  - `step_6_9a(share_code="9JS3VA3C")`: `_run_line(code, ("merge_preferences", merge_group_preferences))`,
    then `pprint` the state.
  - `step_6_9b(share_code=...)`: `_run_line(code, merge, search)`, then prints the state with
    the candidates shortened to one line each (`name (crag, km)`).
  - `step_6_9c(share_code=...)`: the three-node line; prints the state (stays as
    `name (type, km)`).
  - Register `"6.9a"`, `"6.9b"` and `"6.9c"`.
- `README.md`: `agent/nodes.py  One function per trip-planner step; each calls an existing service.`;
  under `tests/`, `conftest.py  Factories for groups, sectors and stays (trip planner tests).`;
  in `services/groups.py`'s line, add `find_group()`.

**Reuses:** the existing `get_group` query (moved, not rewritten) as `find_group()`;
`merge_preferences()`, `dataclasses.asdict`; `search_for_group()` (results already ranked and
filtered), `GroupSectorMatch`; `find_stays_near()`, `NearbyStay`, the `Sector` crag
relationship (as `load_sector`).

**Tests:**
- Existing `tests/test_groups_api.py::test_get_group_is_case_insensitive` and
  `::test_unknown_group_is_404` pass unchanged (the `find_group` refactor keeps behaviour; the
  node tests below exercise `find_group` directly).
- `tests/test_agent_nodes.py` (new):
  - `test_merge_writes_filters_for_a_group_that_agrees`: two members 6a–7a and 6b–7b, 100 and
    80 km → `filters == {"grade_min": "6b", "grade_max": "7a", "max_distance_km": 80, "max_approach_minutes": None, "styles": None}`,
    `conflicts == []`, two `members`, `guests == 2`. (AC 1)
  - `test_merge_writes_conflicts_when_there_is_no_common_ground`: 5–6a vs 7a–8a →
    `filters is None`, one conflict naming both members. (AC 1)
  - `test_merge_keeps_guests_set_by_the_caller`: state with `guests=6` → no `"guests"` key in
    the update.
  - `test_merge_returns_only_its_own_keys`: `set(update) <= {"members", "filters", "conflicts", "guests"}`.
    (partial update)
  - `test_merge_unknown_share_code_raises_value_error`.
  - `test_merge_group_without_members_is_a_conflict`.
  - `test_search_returns_candidates_best_first_and_picks_the_top`: two sectors fitting a 6a–7a
    group at 37 km and 106 km plus one 7c–8b sector → two candidates, the closer one first,
    `chosen_sector == candidates[0]`, all values plain (`json.dumps(update)`). (AC 2, AC 3 rule)
  - `test_search_without_matching_sectors_chooses_nothing`: no sector in range →
    `candidates == []`, `chosen_sector is None`.
  - `test_search_calls_the_group_search_service`: monkeypatch
    `app.agent.nodes.search_for_group` with a spy that returns an empty `GroupSearchResponse`;
    assert it got `"strict"` and `"overlap"` and members with attribute access. (AC 4)
  - `test_find_stays_returns_closest_stays_as_plain_dicts`: one sector and three stays (two
    within 10 km, one 30 km away) → two stays, closest first, `stay.type` a string,
    `json.dumps` works. (AC 3)
  - `test_find_stays_keeps_at_most_five`: seven stays nearby → five.
  - `test_find_stays_without_a_chosen_sector_is_empty`.
- `tests/test_agent_graph.py`:
  - `test_line_merge_then_search_keeps_merge_fields`: a two-node `StateGraph` invoked on a
    factory group → the result still has `filters` and `members`, and now has `candidates`.
    (AC 2 "nothing from step 1 is lost")
  - `test_line_of_three_nodes_ends_with_stays`: the full line on a factory group with a
    sector and a stay → `filters`, `candidates`, `chosen_sector` and `stays` all present.
    (AC 2, 3)

**Expected suite:** 144 passed (130 after tickets 014 and 007 are delivered as planned + 14
new: 12 in `test_agent_nodes.py`, 2 in `test_agent_graph.py`).

**Check by hand** (needs the "Planner demo" group, see the ticket check):
- `GET /groups/9js3va3c` in `/docs` still returns "Checkpoint demo" (refactor unchanged).
- `uv run python -m app.scripts.rag_playground 6.9a 9JS3VA3C` → `filters: None` and the grade
  conflict (Ana vs Marc). `… 6.9a <Planner demo code>` → filters 6b–6c, 130 km, 30 min,
  `['sport']`. (AC 1)
- `… 6.9b <Planner demo code>` → Collbató first, then Can Marges and Siuranella; `filters`
  still there. `… 6.9b 9JS3VA3C` → `candidates: []`: the line searches even when the group
  disagrees. That's the problem ticket 009 fixes. (AC 2)
- `… 6.9c <Planner demo code>` → up to five stays near Montserrat. (AC 3)
- Run 6.9a, 6.9b and 6.9c one after the other: each adds keys and none disappears. (AC 5)
- `grep -n "grade_rank\|haversine\|between(" app/agent/nodes.py` prints nothing (AC 4: no
  copied logic).

**Commit:** `Stage 6.9: merge_preferences, search_sectors and find_stays nodes as thin wrappers over the existing services (members as plain dicts, top result as the chosen sector for now, five closest stays within 10 km), group lookup moved to services/groups.py, test factories, playground 6.9a to 6.9c`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_merge_writes_filters_*`, `test_merge_writes_conflicts_*`, playground 6.9a |
| 2 | `test_search_returns_candidates_*`, `test_line_merge_then_search_keeps_merge_fields` |
| 3 | `test_find_stays_*`, `test_line_of_three_nodes_ends_with_stays`; "top result" rule in `test_search_returns_candidates_best_first_and_picks_the_top` |
| 4 | `test_search_calls_the_group_search_service`; grep check; review |
| 5 | Playground steps 6.9a / 6.9b / 6.9c, checked by hand |

## Risks
- *The demo group doesn't exist yet:* without "Planner demo", the hand checks for 6.9b and
  6.9c show empty lists. The user creates it before the hand checks. The tests don't
  depend on it.
- *Dev data changes the top sector* (new seeds, edited sectors): the hand checks name
  Collbató for today's data only; the tests use their own rows.
- *Lazy loading on a closed session:* `sector.crag` is read inside the node while the
  session is open. Don't keep ORM rows past the node (the state never holds them).
- *Ticket 010 changes `search_sectors`* (it stops writing `chosen_sector`): the tests on
  `chosen_sector` from search, and the three-node line, are updated there. That's expected
  churn, already in plan 010.
- *A large single diff (a refactor plus three nodes):* build it in the order of the files
  list and run `tests/test_groups_api.py` right after the `find_group` move, so a refactor
  regression shows up before the node code is written.

## Out of scope (copied from the ticket)
- Conditional routing (ticket 009) and the pause for approval (ticket 010).
