# Plan for 020: Live graph diagram of the trip planner, with a frontend test runner

**Ticket:** `tickets/020-live-graph-diagram.md`
**Approach:** Inside 019's `RunView`, a `TraceReplay` block shows the planner graph from
`GET /planner/graph` as the app's own SVG and a step list beside it. `@dagrejs/dagre` does the
layout and every colour is a token. The highlight, the visit counts, the "waiting for you" /
"plan ready" / "no plan" mark and the plain-word steps all come from pure helpers that read
`run.trace`, `run.status` and the run's rejections, proposal and plan, plus one "steps shown"
counter. Vitest (node environment, no DOM) tests those helpers and 019's `plannerOutcome.ts` and
`tripDates.ts`. `npm test` runs it, and CI runs it as one new step in the ESLint job. No backend
behaviour changes; the only backend edit is a comment next to `APPROVAL_NODE`.

**Alternatives considered:**
- *Mermaid from LangGraph's `draw_mermaid()`:* it needs a new endpoint and a large library that
  renders asynchronously. Every highlight step would mean a full re-render, and theming means
  handing it fixed colours instead of our tokens.
- *React Flow (`@xyflow/react`) or a canvas library:* a pan/zoom canvas with its own CSS (or
  pixels that can't read CSS variables) is more than a read-only diagram of 9 nodes needs.
  React Flow has no layout of its own, so it would still need dagre. On a canvas, the text is
  not in the DOM either.
- *Our own layout code:* the graph has a cycle (`approve_sector -> pick_sector`) and two long
  edges into `__end__`. Breaking cycles, ranking nodes and routing long edges is what dagre
  already does (reuse over new code). We keep only the drawing. dagre 3.1.1 ships its own
  `index.d.ts` and an ESM build (checked on npm).
- *Left to right instead of top to bottom:* 8 ranks side by side is about 1,500 px wide, which
  means scrolling sideways on a phone. Top to bottom is about 400 px wide and fits.
- *Load the graph together with the latest run in `PlannerSection`'s mount effect (the earlier
  plan):* on a fresh backend process, both requests would hit `get_trip_planner()` at once.
  `lru_cache` does not lock, so two `open_postgres_saver()` / `setup()` calls could run side by
  side (see Risks). `RunView` only mounts after a run response, when the planner is already
  built, so the graph is loaded there. A failed graph load then only affects the diagram: the
  step list and the approve buttons still work.
- *One counter in `RunView` that lives across answers (019's seam as written):* a 409 re-read
  (not animated) grows the trace under the same `run_id`. The counter would then have to be
  pushed forward by an effect, and the `react-hooks` rules forbid that synchronous setState.
  Keying the replay block by `run.trace.length` gives a fresh counter whenever the trace grows.
  Where it starts is derived (see `firstNewStep()`). 019's `animate: boolean` stays exactly as
  its seam says.
- *Keep `APPROVAL_NODE` in step with a pytest that reads the `.ts` file, or by adding the pause
  node to `/planner/graph`:* the first couples the backend suite to frontend source. The second
  is an API change the ticket puts out of scope. Instead: a comment on both sides plus a
  CLAUDE.md trap line. If the names drift anyway, nothing breaks: the "waiting" mark just
  doesn't show, and the proposal still does.
- *Jest, or component tests with jsdom / Testing Library:* Vitest reuses `vite.config.ts` and
  needs no Babel or TS setup. Component tests are out of scope (ticket).

**Choices on the ticket's open questions:**
- Speed: **one step every 500 ms**. "Skip" jumps to the end; "Replay" plays the whole run again
  from the first step. With `prefers-reduced-motion: reduce`, everything shows at once, there is
  no Skip or Replay, and nothing pulses.
- Raw fields: **yes, collapsed**. Each step has a `<details>` "Details" with its `changed` names
  as they are, or "No fields changed" when the list is empty.
- Small screens: **always shown**. The diagram shrinks to fit, and below 300 px of drawing width
  it scrolls inside its own box.

## Ticket check
Checked against the code on 2026-10-14 (015 at d649584, 016 at 5fc33b3). 017, 018 and 019 are
not delivered yet, so this plan names their files the way their plans describe them.
`uv run pytest --collect-only -q`: 199 collected. `npm run lint` in `web/`: clean.
- **Correct, re-checked by running `graph_structure(build_trip_planner(None))` today:** 9 nodes
  (`__start__`, `merge_preferences`, `search_sectors`, `pick_sector`, `approve_sector`,
  `find_stays`, `propose_plan`, `explain_conflicts`, `__end__`) and 11 edges. Conditional (c):
  `__start__->merge_preferences`; `merge_preferences->search_sectors` (c), `->explain_conflicts`
  (c); `search_sectors->pick_sector`; `pick_sector->approve_sector` (c), `->__end__` (c);
  `approve_sector->find_stays` (c), `->pick_sector` (c, the loop);
  `find_stays->propose_plan`; `propose_plan->__end__`; `explain_conflicts->__end__`. This is
  the same list as the earlier plan.
- **Imprecise, "sorted by source name":** the first nine edges are in source-name order, but
  `explain_conflicts->__end__` and `propose_plan->__end__` come last. The order means nothing
  either way, and the frontend must not rely on it.
- **Correct, and more detail, what each trace step's `changed` holds** (from `agent/nodes.py`;
  the step wording depends on it):
  - `merge_preferences`: `members`, `guests` (only when the start body left guests out),
    `filters`, `conflicts`. It is the same with or without common ground, so the **next node**
    decides the wording.
  - `search_sectors`: `candidates`, plus `message` when no sector matches.
  - `pick_sector`: `chosen_sector`, `approved` when it proposes; `chosen_sector`, `message`
    when nothing is (left) to propose.
  - `approve_sector`: `approved`, plus `rejections` when the group says no.
  - `find_stays`: `stays`. `explain_conflicts`: `message`.
  - `propose_plan`: `plan`, `message` **both on success and when the sector was deleted**, so
    its wording must come from `run.status`, not from `changed`.
- **Correct, the paused node is not in the trace:** `advance()` skips `__interrupt__`, the API
  has no `next`, `status` is `waiting_for_approval`, and `APPROVAL_NODE = "approve_sector"`
  is in `services/trip_planner.py:26`. A resume always re-runs `approve_sector` first, so the
  steps of the latest answer start at the **last** `approve_sector` in the trace. That is how
  `firstNewStep()` knows which steps are new without storing a second copy of the run.
- **Correct, rejections:** `{sector_id, reason}`. The reason is `""` when none was given (never
  `null`: `decision.reason or ""`). The k-th rejecting `approve_sector` step matches
  `rejections[k]`. Only the sector proposed **now** (`run.proposal`) or the planned one
  (`run.plan.sector`) can be named. The ticket's example "Proposed Siurana, Can Marges" is crag,
  then sector (seed data).
- **Correct, AC 8 and 9 paths:** no common ground and no members both give
  `merge_preferences, explain_conflicts`. Strict no match gives `merge_preferences,
  search_sectors (message), pick_sector (message)`. Three rejections end on the fourth
  `pick_sector`, with `message` changed (so ×4 picks and ×3 group decides).
- **Correct:** `web/package.json` has only `dev`, `build`, `lint` and `preview`. Vitest 5.0.4
  supports Vite `^8` and Node 24 (local Node is 24.18; 018's CI uses 24). `tsconfig.app.json`
  includes all of `src/`, so `tsc -b` type-checks the test files. They must import
  `describe` / `it` / `expect` from `"vitest"` (no globals) and use no Node globals
  (`types` is only `vite/client`).
- **Out of date, `web/src/styles/tokens.css` header:** it says "Ticket 018's SVG diagram reads
  them". After the renumbering this is ticket 020. Fix the comment.
- **Not in the ticket, found while planning (Risks):** concurrent first requests to
  `get_trip_planner()` are not serialised. That is why the graph loads after the run.
- **Nothing in the ticket is wrong** apart from the edge-order wording above.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

Before starting: `git log --oneline -6` must show 017, 018 and 019 committed. Read what 019
actually delivered: `PlannerSection`'s view union, `RunView`, the `PlannerRun` / `TraceStep` /
`Rejection` types, `plannerOutcome.ts` (`noPlanTitle`, `offersMemberEdit`), the formatter's
export name in `features/stays/tripDates.ts`, and the exact form of the `web: npm run lint`
step in `.github/workflows/ci.yml`. If a name differs from this plan, use the delivered name
and say so in the hand-off. Stop `npm run dev` in `web/` before `npm install` (OneDrive locks;
exact, verified PID only).

### 1. A live diagram and plain-word steps for every planner run, tested with Vitest
**Files** (no migration; backend comment, then tooling, then frontend, docs and CI):

*Backend (comment only, no behaviour change)*
- `backend/app/services/trip_planner.py`: on `APPROVAL_NODE`, add "Mirrored in
  web/src/features/planner/plannerNodes.ts: the diagram marks this node as waiting, because the
  paused node is not in the trace."

*Tooling* (`web/package.json`, `web/package-lock.json`, both committed)
- `npm install @dagrejs/dagre` (dependency, `^3.1.1`) and `npm install -D vitest` (`^5.0.4`).
- Script `"test": "vitest run"`: it runs once and exits non-zero on a failure. No watch mode,
  locally or in CI.
- No `vite.config.ts` change: Vitest reads it, and its default node environment is what pure
  helpers need. Its default pattern only picks up `*.test.ts`, so `planner.fixtures.ts` is not
  run as a test.

*Types* (`web/src/api/types.ts`, in 019's `// schemas/planner.py` block)
- `PlannerEdge` (`source`, `target`, `conditional: boolean`) and `PlannerGraph` (`nodes:
  string[]`, `edges: PlannerEdge[]`), mirroring `PlannerEdge` / `PlannerGraphRead`.

*Pure helpers* (`web/src/features/planner/`, plain `.ts`, each with a `*.test.ts` next to it)
- `plannerNodes.ts`:
  - `START_NODE = "__start__"`, `END_NODE = "__end__"` (LangGraph's names) and
    `APPROVAL_NODE = "approve_sector"`, with a comment that it mirrors
    `services/trip_planner.py`.
  - `nodeLabel(node)`: "Merge preferences", "Search sectors", "Pick a sector", "Group decides",
    "Find stays", "Propose plan", "Explain conflicts", "Start", "End". Any other name comes back
    as it is (AC 2).
- `graphLayout.ts`:
  - `layoutGraph(graph: PlannerGraph): GraphLayout` runs dagre top to bottom (`rankdir: "TB"`,
    around `nodesep: 24`, `ranksep: 40`, margins 8). Use the import form dagre's `index.d.ts`
    declares.
  - Box sizes are computed without the DOM, so the function stays pure and testable:
    - Start and End are pills, 96 × 28 (End also has to fit "Plan ready").
    - Step boxes are 44 px high (room for a second line, "Waiting for you"), and
      `max(136, 8 × label length + 32)` px wide, so a long unknown name still fits.
    - One comment says why the widths are estimated.
  - It returns `{width, height, nodes, edges}`:
    - each node is `{id, label: nodeLabel(id), kind: "start" | "end" | "step", x, y, width,
      height}`, where `x` and `y` are the top-left corner (dagre gives the centre);
    - each edge is `{source, target, conditional, points}`, in the API's order.
    - A comment says why dagre: it breaks the cycle and routes the long edges into the end.
  - `edgePath(points): string` turns the points into `"M x,y L x,y ..."`.
- `runPath.ts`:
  - `edgeKey(source, target)`.
  - `runPath(run: Pick<PlannerRun, "trace" | "status">, shown: number): RunPath` clamps `shown`
    to `0..trace.length` and returns:
    - `visits: Map<string, number>`: how often each node ran among the first `shown` steps.
      `__start__` counts once as soon as one step is shown, and `__end__` counts once when the
      run is finished and fully shown.
    - `taken: Set<string>`: `__start__->trace[0]` and every `trace[i]->trace[i+1]` inside the
      shown steps. When everything is shown, it also has `last->APPROVAL_NODE` while waiting,
      and `last->__end__` when finished.
    - `current`: the last shown node while revealing, `null` when done or when nothing is shown
      yet.
    - `stop`: `null` while revealing or when the trace is empty (AC 13). When everything is
      shown: `{node: APPROVAL_NODE, outcome: "waiting"}`, or `{node: END_NODE, outcome:
      "planned" | "no_plan"}`.
    - A node the graph doesn't have is counted like any other. The diagram simply has no box
      for it (AC 2).
  - `firstNewStep(trace): number`: the index of the last `APPROVAL_NODE` step, or 0. A start
    runs from step 0, and an answer resumes at the approval node. The comment says that is why
    nothing else needs to remember the old trace.
- `plannerText.ts`:
  - `describeSteps(run): StepLine[]`, one per trace step, `{node, title: nodeLabel(node), text,
    changed}`, with `changed` exactly as in the trace. The texts:
    - `merge_preferences`: "Compared everyone's preferences: no common ground." when the next
      step is `explain_conflicts`; "Compared everyone's preferences: they have common ground."
      when it is `search_sectors`; otherwise "Compared everyone's preferences."
    - `search_sectors`: "Searched for sectors everyone can climb: none found." with `message`
      in `changed`, else "Searched for sectors everyone can climb."
    - `pick_sector` with `message` in `changed`: "No sector to propose, so the run ends." when
      there are no rejections, else "No sector left to propose, so the run ends."
    - `pick_sector` proposing (the k-th proposing pick, counting from 0):
      - if `k < rejections.length`, that proposal was turned down: "Proposed a sector." for
        k = 0, "Proposed another sector." after that;
      - otherwise it is the latest proposal: "Proposed {crag_name}, {sector_name}." from
        `run.proposal ?? run.plan?.sector`;
      - with neither (the sector was deleted), the unnamed wording.
    - `approve_sector` with `rejections` in `changed` (the k-th rejecting step): "The group said
      not this one: {reason}" with `rejections[k].reason`, or "The group said not this one."
      when the reason is empty. Otherwise "The group approved it."
    - `find_stays`: with a plan, "Found N places to stay near the crag." ("1 place", "no
      places"); without one, "Looked for places to stay near the crag."
    - `propose_plan`: "Put the plan together." when `status === "planned"`, else "Couldn't put
      a plan together."
    - `explain_conflicts`: "Wrote down why the group has no common ground."
    - any other node: "Ran {node}." (AC 2).
  - `stopLabel(outcome)`: "Waiting for you", "Plan ready", "No plan" (AC 4).
- `planner.fixtures.ts` (imported only by tests):
  - `PLANNER_GRAPH`: the 11-edge graph above.
  - `makeRun(partial)`, with defaults for every `PlannerRun` field.
  - Step constants with the real `changed` lists from the Ticket check (`MERGE`,
    `SEARCH_FOUND`, `SEARCH_NONE`, `PICK_PROPOSE`, `PICK_NONE`, `APPROVE_YES`, `APPROVE_NO`,
    `FIND_STAYS`, `PROPOSE_PLAN`, `EXPLAIN`).
  - These runs:
    - `waitingRun`: proposal Can Marges at Siurana;
    - `rejectedOnceRun`: reason "too far", next proposal waiting;
    - `plannedRun`: two stays;
    - `noCommonGroundRun`;
    - `noMatchRun`;
    - `threeRejectionsRun`: reasons "too far", "", "too hard".

*Components* (`web/src/features/planner/`, CSS Modules, tokens only, no hex, no inline `style=`)
- `usePlannerGraph.ts`: a hook that loads `GET /planner/graph` with `apiRequest<PlannerGraph>()`.
  - It returns `{state: "loading"} | {state: "ready", graph} | {state: "error", message}` and
    `reload()`.
  - Use the `StaysPanel` pattern: an `attempt` number in state and in the effect's deps, the
    result stored with the attempt it belongs to, and "loading" derived as `result?.attempt !==
    attempt`. A cancelled flag; setState only in the promise callbacks. `reload()` bumps
    `attempt` from the click handler.
- `TraceReplay.tsx` + `.module.css`: props `run`, `graph` (the hook's state), `onRetryGraph`,
  `animate`, `children` (the outcome).
  - State: `reducedMotion`, read once with
    `useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)`, and
    `shown`, which starts at `animate && !reducedMotion ? firstNewStep(run.trace) :
    run.trace.length`.
  - One effect: while `shown < trace.length`, a 500 ms `setTimeout` calls
    `setShown(n => n + 1)`, and the cleanup clears it. setState only in the timer callback.
  - Derived values: `done = shown >= trace.length` and `path = runPath(run, shown)`.
  - Controls (ghost `Button`s): "Skip" while not done (sets `trace.length`); "Replay" when done,
    the trace isn't empty and motion is allowed (sets 0). Neither shows under reduced motion
    (AC 6).
  - Layout: diagram and step list side by side from 760 px (`grid-template-columns:
    minmax(0, 1fr) minmax(0, 1fr)`), stacked below that, so nothing pushes the page wider.
  - Diagram area by graph state: loading, a loading `StateMessage` "Loading the diagram";
    error, an error `StateMessage` with the message and a "Try again" button
    (`onRetryGraph`); ready, `PlannerDiagram`.
  - `children` sit in `<div hidden={!done}>`. The outcome appears when the replay ends, and
    stays mounted during a Replay, so a typed reason survives.
- `PlannerDiagram.tsx` + `.module.css`: props `graph`, `path`.
  - `layout = useMemo(() => layoutGraph(graph), [graph])`.
  - It is drawn in a `.scroller` box (`overflow: auto`). The `<svg>` gets `width`, `height`
    and `viewBox` from the layout, and CSS `max-width: 100%; height: auto; min-width: 300px`.
    So it shrinks to fit, and below that it scrolls inside its own box, never the page
    (AC 10).
  - Edges: `<path d={edgePath(points)}>` with arrow markers (fixed ids `planner-arrow` and
    `planner-arrow-taken`; there is one diagram per page). Conditional edges are dashed;
    taken edges are `--accent` and thicker (AC 1, 3).
  - Nodes: a rounded `rect`, the label, and a `<title>` with the raw node name. Classes come
    from `path`:
    - visited: `--accent-soft` fill, `--accent` stroke;
    - current: a thicker stroke and a pulse, with `animation: none` under
      `prefers-reduced-motion`;
    - paused: `--highlight-soft` / `--highlight`, plus a second line "Waiting for you";
    - End when planned: `--success`, label "Plan ready";
    - End with no plan: `--text-muted`, label "No plan" (both from `stopLabel()`);
    - a node visited 2 or more times gets a "×N" badge (AC 3, 7).
  - Unvisited boxes are `--surface` with a `--border` stroke and `--text` labels, so dark mode
    has no white boxes (AC 10).
  - Legend under it, in HTML with small token-coloured line samples: "Solid: always the next
    step. Dashed: the run decides. Highlighted: the path this run took." (AC 1).
  - `<svg role="img">` with a `<title>` such as "Planner diagram, 5 steps, waiting for you". The
    step list is the readable version.
- `StepList.tsx` + `.module.css`: an `<ol aria-live="polite">` of the first `shown` lines of
  `describeSteps(run)`.
  - Each line has its number, its `title`, its `text`, the current one marked, and a
    `<details>` "Details" listing `changed` (or "No fields changed").
  - When done and the trace isn't empty, a last line with `stopLabel()`.
  - An empty trace gives "No steps recorded for this run." (AC 5, 13).

*Wiring into 019's files*
- `PlannerSection.tsx`: add `animate: boolean` to the `run` view. It is `true` after start and
  after answer, and `false` after the mount load and after the 409 re-read. That is 019's seam;
  nothing else changes there.
- `RunView.tsx`: it gets `animate` and calls `usePlannerGraph()` (here and not in
  `PlannerSection`, see Alternatives and Risks). The notice stays on top. 019's
  status-to-outcome choice becomes the `children` of
  `<TraceReplay key={run.trace.length} ...>`. One comment: a longer trace is a new thing to
  play, and the key gives it a fresh counter without an effect.

*Docs* (Definition of done 3)
- `web/src/styles/tokens.css`: the header comment "Ticket 018's SVG diagram" becomes "The
  planner diagram's SVG (ticket 020)".
- `CLAUDE.md`:
  - Commands: "`npm run lint`, `npm test` and `npm run build`: must pass for frontend changes
    (`npm test` runs Vitest once, no watch mode)".
  - Tests: add "Frontend: pure `.ts` helpers in `web/src/` get a `*.test.ts` next to them
    (Vitest, node environment, no DOM, no network); components are checked by hand."
  - Reuse, frontend line: add "planner diagram helpers `layoutGraph()` / `edgePath()`
    (`graphLayout.ts`), `runPath()` / `firstNewStep()` (`runPath.ts`), `describeSteps()` /
    `stopLabel()` (`plannerText.ts`), node names and labels (`plannerNodes.ts`), test data in
    `planner.fixtures.ts`, all in `features/planner/`".
  - Traps: add "`APPROVAL_NODE` is mirrored in `web/src/features/planner/plannerNodes.ts`
    (the paused node is not in the trace); rename both together."
  - Definition of done 1: "...and `npm run lint` and `npm test` pass for frontend changes".
- `.claude/agents/developer.md` (017's "run `npm run lint` (and `npm run build`) in `web/`")
  and `.claude/agents/tech-lead.md` (same line, plus the "Bash is for reading and checking
  only" list): "`npm run lint`, `npm test` and `npm run build` in `web/`". This may trigger a
  permission prompt.
- `README.md`:
  - "Running tests": add `cd web` / `npm test` under the backend block.
  - 018's "Checks (same as CI)": add `npm test` in `web/`.
  - 018's CI paragraph: "ESLint (lint and Vitest unit tests for web/)".
  - Structure: the `.github/workflows/ci.yml` line ends "...ESLint and Vitest (web/)". The
    `features/planner/` line gains "live diagram of the planner graph (dagre layout, own SVG),
    step list in plain words with details, skip and replay; `*.test.ts` Vitest tests for the
    pure helpers, `planner.fixtures.ts` test data".

*CI* (`.github/workflows/ci.yml`, exactly one step, nothing else)
- In job `eslint` (name `ESLint`), right after the step named `web: npm run lint`: a step named
  `web: npm test`, with `working-directory: web` and `run: npm test`. Copy the lint step's exact
  form (quoting of the name included).
- It reuses the job's Node set-up, npm cache and `web: npm ci`.
- No new job, no renamed job or step, no trigger, cache or env change. The workflow still
  reports three checks (AC 12).

**Reuses:**
- 019: `PlannerSection`'s view union and its `animate` seam, `RunView` (keyed by `run_id`) and
  its outcome choice, the `PlannerRun` / `TraceStep` / `Rejection` types, `plannerOutcome.ts`,
  `tripDates.ts`.
- 016: `apiRequest()` / `ApiError`, `Button` (ghost), `StateMessage` (loading, error with
  `action`), the tokens and base.css's `[hidden]` rule, and the cancelled-flag effect from
  `StaysPanel`.
- 018: the ESLint job's Node set-up and `web: npm ci`.
- Backend, unchanged: `GET /planner/graph` (`graph_structure()`), `run_view()`'s `status` and
  `trace`.
- New libraries: `@dagrejs/dagre` (layout only) and `vitest` (dev only).

**Tests** (Vitest, `npm test` in `web/`; all use `planner.fixtures.ts`; the paths are under
`web/src/features/`):
- `planner/plannerNodes.test.ts`:
  - `labels known nodes in plain words and unknown nodes by their raw name` (AC 2)
- `planner/graphLayout.test.ts`:
  - `gives every node a box inside the drawing`: all 9 nodes, finite numbers, each box within
    `0..width` × `0..height` (AC 1, 10)
  - `keeps every edge with its conditional flag and at least two points`: 11 edges, the same
    `(source, target, conditional)` as the input, the loop `approve_sector->pick_sector`
    included (AC 1, 7)
  - `draws the start above the first step and the end below the last`: `y` of `__start__` <
    `merge_preferences` < `propose_plan` < `__end__` (AC 1)
  - `lays out a node it has never seen, labelled with its raw name and wide enough`: a graph
    with `"mystery_node"` gets a box labelled `"mystery_node"`, wider than a short label's box
    (AC 2)
  - `edgePath draws a line through the points`: `[{x:0,y:0},{x:10,y:5},{x:20,y:10}]` gives
    `"M0,0 L10,5 L20,10"` (AC 1)
- `planner/runPath.test.ts`:
  - `a waiting run goes merge, search, pick and stops at the approval node`: visits and taken
    edges include `pick_sector->approve_sector`; stop is `waiting` at `approve_sector` (AC 3, 4)
  - `a rejection takes the loop back to pick_sector and counts the visits`:
    `approve_sector->pick_sector` is taken, pick_sector ×2 (AC 3, 7)
  - `an approved run ends at the end with a plan`: `find_stays->propose_plan` and
    `propose_plan->__end__` are taken; stop is `planned` at `__end__` (AC 4)
  - `no common ground goes through explain_conflicts and never visits search`:
    `merge_preferences->explain_conflicts` is taken; `search_sectors` has no visit and no
    taken edge; stop is `no_plan` (AC 8)
  - `strict search with no sector ends after pick_sector without a plan`:
    `pick_sector->__end__` is taken, `approve_sector` has no visit, stop is `no_plan` (AC 9)
  - `three rejections end without a plan after four picks`: pick_sector ×4, approve_sector ×3,
    stop is `no_plan` (AC 9)
  - `a partial reveal shows only the first steps`: `shown = 2` of 3 gives 2 visited steps,
    `current === "search_sectors"`, stop null, and no edge to `pick_sector` (AC 3, 6)
  - `shown is clamped to the trace`: 99 gives the same as `trace.length`, and -1 the same as 0
    (AC 6, Skip)
  - `an empty trace highlights nothing and has no stop` (AC 13)
  - `a node the graph does not know is still counted`: a trace with `"mystery_node"`, nothing
    throws (AC 2)
  - `firstNewStep starts a new run at 0 and an answer at the last approval step`: `waitingRun`
    gives 0, `rejectedOnceRun` gives 3, `plannedRun` gives 3, `threeRejectionsRun` gives 7
    (AC 6)
- `planner/plannerText.test.ts`:
  - `gives one line per step with the changed field names as they are` (AC 5)
  - `merge_preferences says whether the group has common ground` (AC 5, 8)
  - `pick_sector names only the sector proposed now`: in `rejectedOnceRun`, "Proposed a
    sector." then "Proposed {crag}, {sector}." for the proposal (AC 5, 7)
  - `each rejection quotes its own reason and an empty reason adds none`: in
    `threeRejectionsRun`, "The group said not this one: too far", "The group said not this
    one.", "...: too hard" (AC 5, 7)
  - `search and pick say when there is nothing to propose`: `noMatchRun` and
    `threeRejectionsRun` (AC 9)
  - `an approved run describes the stays and the plan`: "Found 2 places to stay near the
    crag.", "Put the plan together." (AC 5)
  - `an unknown node says it ran`: "Ran mystery_node." (AC 2)
  - `stopLabel names the three endings` (AC 4)
- `planner/plannerOutcome.test.ts` (019's helpers):
  - `noPlanTitle tells no common ground, no matching sector and the other endings apart` (AC 8,
    9)
  - `offersMemberEdit only when changing the members can help` (AC 8, 9)
- `stays/tripDates.test.ts` (019's formatter):
  - `reads YYYY-MM-DD as a local date`: `"2026-10-17"` to `"2026-10-19"` reads "Sat 17 Oct" to
    "Mon 19 Oct" (whatever exact sentence 019's formatter builds)

**Expected suite:**
- Backend: **202 passed** (199 collected today, plus 019's 3; 017, 018 and this ticket add
  none). If 017 or 018 were delivered with extra tests, use the count collected before this
  ticket; 020 adds 0. `uv run ruff check .` is clean.
- `web/`: **28 passed** with `npm test` (1 + 5 + 11 + 8 + 2 + 1). `npm run lint`: 0 problems.
  `npm run build` succeeds.
- CI: three checks (Backend tests, Ruff, ESLint), all green. The ESLint log shows the step
  `web: npm test` with 28 passed.

**Check by hand** (by the user: `docker compose up -d`, `uv run alembic upgrade head`,
`uv run fastapi dev app/main.py`, `npm run dev` in `web/`; devtools device bar at 375 px;
"emulate prefers-color-scheme" and "prefers-reduced-motion"):
1. Group of 2 who agree, "Plan the trip". The diagram shows Start, the 7 steps and End, with
   dashed branches and the legend. Merge, search and pick light up about every half second while
   the step list grows. Then "Group decides" says "Waiting for you" and the proposal card
   appears. "Details" shows the field names (AC 1, 3, 4, 5, 6).
2. Start another run and press "Skip" at once: everything shows. Press "Replay": it plays again,
   and the proposal stays (or comes back at the end) (AC 6).
3. "Not this one", reason "too far". Only the new steps animate: the loop back to "Pick a
   sector" with "×2", the line "The group said not this one: too far", and the next proposal
   (AC 3, 7).
4. Approve. The path goes on through Find stays and Propose plan, and End says "Plan ready"
   (AC 4).
5. Reload the page: the run shows fully revealed, no animation. Open the share link in a second
   browser: the same (AC 6).
6. A group whose members share no grade, and a new group with no members: the path is merge,
   explain conflicts, End "No plan"; Search sectors is not highlighted (AC 8).
7. A group that agrees but matches no sector: merge, search, pick, End "No plan". A group with
   three matching sectors, rejected three times: ×4 on pick, End "No plan" (AC 9).
8. 375 px in light and dark: the diagram shrinks or scrolls inside its box, the page never
   scrolls sideways, there are no white boxes, and the text stays readable. With reduced motion:
   everything shows at once, no Skip or Replay, no pulse (AC 6, 10).
9. Stop the backend after a run is shown, then start a new run (it fails as 019 shows it).
   Start the backend, reload: with the backend up, everything works. To see the diagram's own
   error, block `/planner/graph` in devtools ("Block request URL") and reload: "Try again" under
   the diagram, while the step list and the proposal still work.
10. CI: `git diff .github/workflows/ci.yml` shows only the `web: npm test` step under
    `web: npm run lint`. After the user pushes, there are three checks, all green. Optionally,
    on a throwaway branch that is never merged, break one expectation in `runPath.test.ts` and
    push: ESLint goes red at `web: npm test` and names the test (AC 12).

**Commit:** `Ticket 020: live diagram of the trip planner graph from /planner/graph, laid out with dagre and drawn as token-coloured SVG, with the path a run took, loop counts, a waiting, plan ready or no plan mark, plain-word steps with field details, animated for runs started or answered in this tab with skip and replay, no motion when reduced; Vitest for the pure planner helpers, run as npm test and by the CI ESLint job; docs and agents know npm test`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `graphLayout.test.ts` (all five); manual check 1; backend `test_graph_structure_lists_nodes_and_conditional_edges`, `test_graph_structure_follows_the_compiled_graph` |
| 2 | `plannerNodes.test.ts::labels known nodes...`; `graphLayout.test.ts::lays out a node it has never seen...`; `runPath.test.ts::a node the graph does not know...`; `plannerText.test.ts::an unknown node says it ran` |
| 3 | `runPath.test.ts::a waiting run...`, `::a rejection takes the loop...`, `::a partial reveal...`; manual checks 1, 3 |
| 4 | `runPath.test.ts::a waiting run...`, `::an approved run...`; `plannerText.test.ts::stopLabel...`; manual checks 1, 4 |
| 5 | `plannerText.test.ts` (one line per step, merge, pick, rejection, approved); manual check 1 |
| 6 | `runPath.test.ts::firstNewStep...`, `::shown is clamped...`, `::a partial reveal...`; manual checks 1, 2, 3, 5, 8 (timer, buttons and reduced motion are DOM: by hand) |
| 7 | `runPath.test.ts::a rejection takes the loop...`; `plannerText.test.ts::pick_sector names...`, `::each rejection quotes...`; `graphLayout.test.ts::keeps every edge...`; manual check 3 |
| 8 | `runPath.test.ts::no common ground...`; `plannerText.test.ts::merge_preferences...`; `plannerOutcome.test.ts` (both); manual check 6 |
| 9 | `runPath.test.ts::strict search...`, `::three rejections...`; `plannerText.test.ts::search and pick...`; `plannerOutcome.test.ts` (both); manual check 7 |
| 10 | `npm run lint`, `npm run build`; `graphLayout.test.ts::gives every node a box...`; manual check 8; reviewer grep below |
| 11 | All 28 Vitest tests, run with `npm test` in `web/`, node environment, no network (fixtures only) |
| 12 | The `ci.yml` step; manual check 10 |
| 13 | `runPath.test.ts::an empty trace...`; `StepList`'s empty line (by hand, with a fixture run if needed) |

The components (timer, Skip and Replay, the hidden outcome, the layout at 375 px, the graph error
state) are checked by hand only: Vitest covers the pure helpers, not the DOM (ticket). The
reviewer should grep `web/src` for hex colours outside `tokens.css` and for `style=`, and check
that the `ci.yml` diff is the one step.

## Risks
- **Concurrent first planner requests (existing backend behaviour, not changed here):**
  `get_trip_planner()` is an `lru_cache`, which doesn't lock. Two requests that both arrive
  before it is built would each open a pool and run `setup()`, which builds indexes
  CONCURRENTLY. The diagram's graph request is therefore made only from `RunView`, which mounts
  after a planner response. By then the planner is built. Do not move the graph load into
  `PlannerSection`'s mount effect. A lock in the backend would be its own ticket.
- **The approval node's name drifts:** comment on both sides, CLAUDE.md trap. If it drifts, the
  "waiting" mark silently doesn't show, and the run still works.
- **Replay hides the outcome for a few seconds:** the outcome stays mounted (`hidden`), so a
  typed reason is kept, and Skip brings it back at once.
- **Hooks lint and timers:** setState only in the timeout callback; the counter is reset by the
  `key`, never by an effect. Reduced motion is read once in a `useState` initializer. If the
  `react-hooks` purity rule flags it, move the `matchMedia` call into a small non-exported
  function in the same file. Do not disable the rule.
- **New dependencies:** dagre adds some tens of kB to the bundle; `vitest` is dev only.
  `package-lock.json` must be committed, because CI uses `npm ci`. If `tsc -b` can't find
  dagre's types, stop and report; don't write a `.d.ts` by hand.
- **Text widths are estimated:** labels at `--step--1` in the body font fit the estimate.
  A wide fallback font could overflow a box slightly (cosmetic). Manual check 8 looks at it.
- **Behaviour that must stay unchanged:** 019's flow (start, answer, 409 re-read, Plan again,
  Start over) and `StaysPanel`. Only `animate` and the `TraceReplay` wrapper are added. The
  backend is untouched apart from one comment, so the 202 tests are unchanged.
- **Agents, CLAUDE.md and the workflow file:** the edits to `.claude/agents/*.md` and
  `.github/workflows/ci.yml` may need the user's permission.
- **External services:** none. `/planner/graph` calls no Claude, Voyage or Overpass, and has no
  rate limit. Vitest makes no network calls (fixtures only).
- **Migration / existing data:** none. Existing runs and their traces show as they are.

## Out of scope (copied from the ticket)
- Changes to the graph itself (new nodes, LLM calls in the planner): this ticket only shows the
  existing graph.
- Component tests with a DOM (the animation timer, buttons, layout at 375 px): checked by hand.
- Real-time push when a friend answers, and a history of past runs.
- Making the API return values of the changed fields or the paused node: if the plain words
  turn out too thin, that is a new ticket.
- Also not here: tests for older pure helpers (017's `groupLink.ts`, 019's `sectorLabels.ts`);
  having `.claude/hooks/tests_on_stop.py` run `npm test`; a lock around `get_trip_planner()`.
