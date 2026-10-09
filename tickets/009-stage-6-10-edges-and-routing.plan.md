# Plan for 009: Stage 6.10, edges and a conditional edge for "no common ground"

**Ticket:** `tickets/009-stage-6-10-edges-and-routing.md`
**Approach:** A new `app/agent/graph.py` builds the real trip-planner graph:
`START → merge_preferences`, then a **conditional edge** whose routing function reads
`state["filters"]` and returns `"search_sectors"` or `"explain_conflicts"`. After that come
normal edges `search_sectors → find_stays → END` and `explain_conflicts → END`. The new
`explain_conflicts` node only joins the conflict strings into a `message`. Playground step
`6.10` prints the Mermaid diagram and runs one group of each kind.

**Alternatives considered:**
- *Route on `state["conflicts"]` (non-empty):* the "no members" case from plan 008 also
  writes a conflict, so both work. `filters is None` is the field the search needs, so
  "can we search?" is asked of exactly that field.
- *A `Command(goto=...)` returned by `merge_preferences`:* that puts routing inside the node.
  The ticket asks for a conditional edge and a pure routing function that can be tested on
  its own.
- *Let `search_for_group` handle it (it already returns `common_ground=False`):* the graph
  would still run the search and stays nodes, which is what AC 2 forbids.

## Ticket check
- `MergeResult.common_ground` / `.conflicts`: correct. In the state (plan 007) they're
  `filters` (`None` = no common ground) and `conflicts`. The example sentence matches
  `merge_preferences`' wording ("No grade everyone climbs: …").
- "Strict mode already returns no common ground as a normal answer": correct
  (`group_search.py:56-60`).
- Diagram: `CompiledStateGraph.get_graph().draw_mermaid()` needs nothing extra.
  **`draw_ascii()` needs the `grandalf` package, which isn't installed** (imported in
  `langchain_core/runnables/graph_ascii.py:13`). The plan uses Mermaid (AC 5 allows either)
  and adds no dependency.
- Test group from the ticket's note (5–6a vs 7a–8a): used as is. In the dev DB, `9JS3VA3C`
  is already such a group.

## Before you start
- Ticket 014 and plans 007 and 008 are delivered (`nodes.py` has the three nodes;
  `tests/conftest.py` has the factories). The "Planner demo" group exists in the dev DB
  (plan 008, ticket check).
- One pytest run at a time (the process check in plan 005), in the foreground. No network.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. The routed graph, explain_conflicts and the diagram
**Files** (in build order: migration, backend, frontend; no migration, no frontend):
- `backend/app/agent/state.py`: new field `message: str | None` with the comment
  "why there's no plan, for the group: `explain_conflicts` (ticket 010: also
  `pick_sector`)".
- `backend/app/agent/nodes.py`: new `def explain_conflicts(state, runtime) -> dict`:
  `{"message": "No common ground, so no search: " + " ".join(state["conflicts"])}`. Comment: the
  conflict strings are already readable; wording them with Claude is out of scope. It takes
  `runtime` only for the uniform signature, or leave it out: LangGraph injects it only if
  it's declared.
- `backend/app/agent/graph.py` (new):
  - **Module docstring**, the explanation (AC 4), about 10 lines: a normal edge
    (`add_edge(a, b)`) always goes from `a` to `b`; a conditional edge
    (`add_conditional_edges(a, route, [...])`) calls `route(state)` after `a` and goes to
    the node it names. The routing function must be pure (read the state, return a name,
    no I/O, no writes) because LangGraph may call it again when it replays or resumes a run
    (ticket 010). Its decision must follow from the saved state alone, so a run can be
    repeated and tested. Anything with side effects belongs in a node, whose output is
    recorded in the state.
  - `def route_after_merge(state: TripState) -> Literal["search_sectors", "explain_conflicts"]`:
    `"search_sectors" if state.get("filters") is not None else "explain_conflicts"`.
  - `def build_trip_planner(checkpointer=None) -> CompiledStateGraph`: `StateGraph(TripState, context_schema=PlannerContext)`,
    with nodes `"merge_preferences"` (`merge_group_preferences`), `"search_sectors"`,
    `"find_stays"` and `"explain_conflicts"`; edges as in the approach; the conditional edge
    with the explicit path list `["search_sectors", "explain_conflicts"]` (comment: the list
    is what makes both branches visible in the diagram). `checkpointer` is passed to
    `compile()` and unused until ticket 010.
- `backend/app/scripts/rag_playground.py`: `step_6_10(*share_codes)` (default `("9JS3VA3C",)`).
  It prints `build_trip_planner().get_graph().draw_mermaid()`. Then, for each code, it runs
  `graph.stream(initial_state(code), context=..., stream_mode="updates")`, prints the path
  (`merge_preferences → explain_conflicts`), and then `message` or the stays. Register
  `"6.10"`.
- `README.md`: `agent/graph.py  build_trip_planner(): nodes, edges, and the "no common ground" branch.`

**Reuses:** the three nodes from plan 008, `TripState`, `PlannerContext`, `initial_state()`.

**Tests:**
- `tests/test_agent_graph.py`:
  - `test_route_after_merge_goes_to_search_when_filters_exist` and
    `test_route_after_merge_goes_to_explain_conflicts_without_filters`: plain dict states, no
    DB. Plus `test_route_after_merge_does_not_change_the_state`: the state dict equals a
    deep copy taken before the call. (AC 3)
  - `test_graph_with_common_ground_runs_merge_search_stays`: a factory group (6a–7a and
    6b–7b), a matching sector and a stay. The node names from
    `stream(..., stream_mode="updates")` are
    `["merge_preferences", "search_sectors", "find_stays"]`, and the final state from
    `invoke` equals the three-node line from plan 008 (built the same way as
    `test_line_of_three_nodes_ends_with_stays`). (AC 1)
  - `test_graph_without_common_ground_skips_search_and_stays`: members 5–6a and 7a–8a; node
    names `["merge_preferences", "explain_conflicts"]`. The final state has no `candidates`
    or `stays` key, and its `message` contains "No grade everyone climbs". Spies on
    `app.agent.nodes.search_for_group` and `app.agent.nodes.find_stays_near` (monkeypatch)
    are never called. (AC 2)
  - `test_diagram_shows_the_branch`: `draw_mermaid()` contains `explain_conflicts`,
    `search_sectors` and the dotted conditional arrow token `-.`. (`langchain_core`
    draws a conditional edge as ` -.-> `, or as ` -. label .-> ` when it has a label, at
    `graph_mermaid.py:203-208`. `-.` matches both.) (AC 5)
- `tests/test_agent_nodes.py::test_explain_conflicts_joins_the_conflicts_into_a_message`.

**Expected suite:** 151 passed (144 after tickets 014, 007 and 008 are delivered as planned +
7 new: 6 in `test_agent_graph.py`, 1 in `test_agent_nodes.py`).

**Check by hand:** `uv run python -m app.scripts.rag_playground 6.10 9JS3VA3C <Planner demo code>`
→ the Mermaid text (paste it into a ` ```mermaid ` block in VS Code to see the branch), then
`merge_preferences → explain_conflicts` with Ana vs Marc for the first group, and
`merge_preferences → search_sectors → find_stays` with stays near Collbató for the second.

**Commit:** `Stage 6.10: trip planner graph with a conditional edge, groups without common ground go to explain_conflicts and skip search and stays; Mermaid diagram in playground 6.10`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_graph_with_common_ground_runs_merge_search_stays` |
| 2 | `test_graph_without_common_ground_skips_search_and_stays` |
| 3 | `test_route_after_merge_*` (three tests) |
| 4 | `graph.py` module docstring, read in review |
| 5 | `test_diagram_shows_the_branch` + playground 6.10 |

## Risks
- *The Mermaid output format changes between versions* (arrow style): the test checks node
  names and only one arrow token. If `-.` changes, check `draw_mermaid()` output and
  update the token, not the graph.
- *A group with common ground but no matching sector* still goes through `find_stays` (with
  `chosen_sector=None`, stays `[]`). That's acceptable here; ticket 010's `pick_sector` adds
  the "nothing to propose" branch.
- *Behaviour of plan 008's playground steps:* unchanged. They keep building their own lines.

## Out of scope (copied from the ticket)
- Using Claude to word the explanation: the conflict strings already exist.
- Suggesting which preference to relax: that was the removed ticket 002 (still in git
  history), not part of Stage 6.
