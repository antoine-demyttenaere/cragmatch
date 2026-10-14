# 020: Live graph diagram of the trip planner, with a frontend test runner

**Status:** Ready
**Size:** M (frontend only, plus a test runner and one CI step; no backend change expected)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Prepare tickets for creating the frontend with associating what we've done in the backend and a new frontend. I want to include the AI part with the graphs. Create a nice design. Do the plan." (second half of the old ticket 018, split on 2026-10-14; the "flow" is ticket 019.)
**Part of:** the new frontend (015 → 016 → 017 → 019 → 020). Needs 019 (planner section) and 018 (CI, for the test step).

## Decisions already made by the user (2026-10-13)
- The planner runs from the browser, with a diagram of the graph that highlights the nodes
  as the run goes through them, then the approve or reject step, then the final plan.

## User story
As a group of friends, I want to watch the planner work through its steps on a diagram and
read each step in plain words, so that we can see how the AI planner got to its proposal.

## What exists today
(Checked against the code on 2026-10-14. "Earlier plan" means found by the tech lead on
2026-10-13 and not re-checked.)
- The graph structure is served by `GET /planner/graph` (`routers/planner.py`,
  `services/trip_planner.py` `graph_structure()`): `nodes` and `edges` with a `conditional`
  flag. Nodes include LangGraph's `__start__` and `__end__`. Edges carry no labels and are
  sorted by source name, not run order. The real output today (earlier plan): start to merge
  preferences; merge to search sectors or to explain conflicts (both conditional); search to
  pick; pick to approve or to end (conditional); approve to find stays or back to pick
  (conditional, the loop); find stays to propose plan; propose plan to end; explain conflicts
  to end.
- A run carries a `trace`: for each step that ran, the node name and the **names** of the
  fields it changed, never their values (`advance()` in `services/trip_planner.py`). A
  rejection stores only the sector id and the reason, so a turned-down sector cannot be named
  from the run.
- **The paused node is not in the trace.** While a run waits, the trace ends at pick sector.
  The approval node appears only after the answer, because `advance()` skips the pause. The
  API does not expose LangGraph's `next` either. The run's `status` is what says "waiting".
  The name of the approval node is a constant in `services/trip_planner.py` (`APPROVAL_NODE`).
- After ticket 019: the planner section on the group page (start, proposal, plan, no-plan
  outcomes, latest run). Planner types are in `web/src/api/types.ts`.
- `web/` has no test runner: `web/package.json` has `dev`, `build`, `lint` and `preview`.
  016's ticket said to revisit this if the diagram logic got complex. It does: the path
  through a cycle, the paused node, the per-step wording and the layout are pure logic with
  many branches (strict no match, three rejections, a partial reveal) that manual checks
  cover badly.
- CI (ticket 018) will have one ESLint job that lints `web/`. It runs no frontend tests,
  because none exist.

## Acceptance criteria
1. Given a run on the group page, then a diagram of the planner graph is shown with every node
   and edge. The conditional branches look different from the fixed ones, with a short legend.
   The diagram comes from the backend's graph structure, not from a drawing kept by hand in the
   frontend.
2. Given a graph with a node the frontend has never seen, then the diagram still draws it with
   its raw name, and the step list says it ran, instead of breaking.
3. Given a run, then the diagram highlights the nodes one after another in the order they ran,
   showing the path actually taken. A node that ran more than once (the loop back to pick a
   sector) shows how many times.
4. Given the run stopped at the approval step, then that node is marked "waiting for you". Given
   a finished run, then the end is marked "plan ready" or "no plan".
5. Given a run, then a step list beside the diagram names each step and says what it did in
   plain words, from what the trace and the run tell (for example "Proposed Siurana, Can
   Marges", "The group said not this one: too far"). A collapsible detail shows each step's
   changed field names as they are.
6. Given a run started or answered in this browser tab, then the highlight is animated about one
   step every half second, with "Skip" to jump to the result and "Replay" to play it again.
   Given a run loaded when the page opens (reload, a friend's link), then it shows fully
   revealed, where it was. Given the system asks for reduced motion, then nothing animates or
   pulses.
7. Given a rejection, then the diagram shows the loop back to pick a sector and the step list
   quotes the reason, and the next proposal appears as in 019.
8. Given a group with no common ground, or no members, then the path through explain conflicts
   is highlighted and the sector search is not.
9. Given the strict search finds no sector, or three sectors are turned down, then the path
   shows how the run ended without a plan.
10. Given phone width and both themes, then the diagram stays readable: it fits, or scrolls
    inside its own area, never the page. Colours come from the design tokens (no white boxes in
    dark mode). `npm run lint` and `npm run build` pass.
11. Given the pure logic behind the diagram (layout, path taken, step wording, outcome text),
    then it has unit tests that run with `npm test` in `web/`, with no browser and no network.
    The tests cover the cases in criteria 2 to 9.
12. Given the CI workflow from ticket 018, then it runs the frontend tests as a `web: npm test`
    step in the existing ESLint job, and still reports three checks. The step ends on its own
    (no watch mode) and fails the job when a test fails.
13. Edge case: given a run with an empty trace, then the diagram shows with nothing highlighted
    and no error.

## Scope
**In:**
- The diagram of the graph from the backend, the step-by-step highlight, the plain-word step
  list with details, and the outcome marks, on the planner section of the group page.
- A frontend test runner for pure `.ts` helpers, with tests for them, and the `npm test` command.
- The `web: npm test` step in the CI workflow (the only workflow change).
- CLAUDE.md, README and the agents' lines that list the frontend commands, so `npm test` is
  known.

**Out:**
- Changes to the graph itself (new nodes, LLM calls in the planner): this ticket only shows the
  existing graph.
- Component tests with a DOM (the animation timer, buttons, layout at 375 px): checked by hand.
- Real-time push when a friend answers, and a history of past runs.
- Making the API return values of the changed fields or the paused node: if the plain words turn
  out too thin, that is a new ticket.

## Open questions
- [non-blocking] How fast should the highlight move? (suggested default: one node about every
  0.5 s, with "Skip" and "Replay". The real run is instant.)
- [non-blocking] Show the raw changed fields as a learning view? (suggested default: the step
  list uses plain words, and a collapsible "details" shows each step's changed field names, as
  in criterion 5.)
- [non-blocking] Should the diagram be shown always, or behind a "How the planner decided"
  toggle on small screens? (suggested default: always, inside its own scrolling area.)

## Notes for the tech lead
- This is the second half of the old ticket 018 (the earlier plan's "018b"). Check what 019
  actually delivered before planning.
- How to draw the diagram is your call. Options to compare: the app's own SVG with a graph-layout
  library; a diagram string from LangGraph rendered by a library; a canvas library. It must use
  the design tokens so it works in both themes, and the backend graph structure must be the only
  source of nodes and edges (criterion 1). The earlier plan found the graph has a cycle and two
  long edges into the end, which is why a layout library may be worth it.
- The paused node is not in the trace (see above). The frontend can mark it from the run's
  status plus the node's name. Say how you keep the name in step with the backend's constant.
- The highlight timing is presentation only: derive it from the trace and one counter, do not
  store a second copy of the run (CLAUDE.md frontend rules). Mind the `react-hooks` lint rules
  for timers.
- Test runner: Vitest is the natural fit with Vite (the earlier plan chose it, node environment,
  no DOM library). The decision is yours. Test files must type-check under `tsc -b`.
- CI: this ticket changes the workflow by exactly one step, `web: npm test`, placed right after
  `web: npm run lint` in the ESLint job from ticket 018. The check keeps the name ESLint.
- No backend change is expected. If one turns out to be needed, say so in the plan, since it
  changes the size.
- Definition of done: README structure, CLAUDE.md commands and tests line, and the two agent files
  that list the frontend commands.
