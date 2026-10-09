# Plan for 006: Stage 6.7, why a graph: sketch the trip-planner agent

**Ticket:** `tickets/006-stage-6-7-why-a-graph.md`
**Approach:** One documentation delivery, with no code. The "Sketch" section of the ticket gets
a Mermaid `flowchart`, a step table (reads / produces / reuses) and a short "why not a
chain" paragraph. The node names in the sketch match the names plans 007–010 use, so that
ticket 011's "built vs sketched" comparison lines up name for name.

**Alternatives considered:**
- *A separate `docs/` file:* the ticket says the sketch lives in the ticket ("In: the diagram
  and notes, in this file"), and ticket 011 appends its comparison there too.
- *An ASCII diagram:* Mermaid renders in VS Code's preview (the ticket's note), and LangGraph's
  `draw_mermaid()` (ticket 009) prints the same notation. So the sketch and the real graph
  can be compared side by side.

## Ticket check
Verified against the code at ticket 005 delivered (`f39f725`). Ticket 014 (removing the
Stage 3 path) is delivered before this one and touches none of the files below.
- `merge_preferences(members) -> MergeResult` with `filters`, `conflicts` and the
  `common_ground` property (`services/group_matching.py:59`): correct.
- `search_for_group(db, members, mode, fit) -> GroupSearchResponse`
  (`services/group_search.py:38`): correct. Note that in strict mode it **runs
  `merge_preferences()` again internally** and returns `common_ground=False` plus a message
  when there's a conflict. The sketch should still show merging as its own step, because
  the graph needs the merge result *before* searching in order to branch.
- `find_stays_near(db, lat, lon, max_distance_km, stay_type=None)` returns
  `list[tuple[Stay, float]]` (`services/stays.py:27`); `airbnb_url()`, `booking_url()` and
  `next_saturday()` are in the same file: correct.
- The 6.5 chain is `build_rag_chain(retriever, llm)` (`rag/chain.py:27`): retriever →
  prompt → model → parser, the same steps for every input. Correct.
- **Found in the dev DB:** the "Checkpoint demo" group (`9JS3VA3C`) has **no common ground**
  (Ana wants 5+–6b, Marc wants 7a–8a). It's the right example for the "no common ground"
  branch, and the wrong one for the happy path. Plans 008 and 011 add a second demo group.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. Write the sketch into ticket 006
**Files** (in build order: migration, backend, frontend; documentation only, no code):
- `tickets/006-stage-6-7-why-a-graph.md`: replace the placeholder under `## Sketch`. Change
  nothing else in the ticket.
  1. A Mermaid `flowchart TD` with these nodes (names used again in plans 007–010):
     `START → merge_preferences`; a decision diamond "common ground?";
     **no** → `explain_conflicts → END`; **yes** → `search_sectors → pick_sector`; a
     decision diamond "a sector left to propose?" (**no** → `END` with no plan);
     **yes** → `approve_sector` drawn as a human checkpoint (a different shape, for example
     `[/approve_sector: group says yes or no/]`); **approved** → `find_stays → propose_plan → END`;
     **rejected** → back to `pick_sector`.
  2. A table with one row per step and the columns *Step*, *Reads*, *Produces*, *Reuses*:
     - `merge_preferences`: reads share code; produces members, merged filters or
       conflicts; reuses `merge_preferences()`.
     - `explain_conflicts`: reads conflicts; produces the "no plan" message; **new** (it
       only joins the existing conflict strings).
     - `search_sectors`: reads members; produces candidate sectors; reuses
       `search_for_group(db, members, "strict", "overlap")`.
     - `pick_sector`: reads candidates and rejections; produces the chosen sector; **new**
       (a rule: the first candidate not yet rejected).
     - `approve_sector` (human): reads the chosen sector; produces approved / rejected plus
       a reason; **new**.
     - `find_stays`: reads the chosen sector; produces nearby stays; reuses
       `find_stays_near()`.
     - `propose_plan`: reads the sector, stays, dates and guests; produces the final plan;
       reuses `airbnb_url()`, `booking_url()` and `next_saturday()`.
  3. Two bullet lists: **Decision points** (common ground?, sector left?, approved?) and
     **Human checkpoint** (`approve_sector`, before any stays are looked up).
  4. A paragraph, "Why a chain can't express this" (2–3 sentences): a chain is a fixed
     pipe, where every input runs every step once, in order. This flow skips steps (no
     common ground), loops back (a rejected sector), and has to stop and wait for a person
     before continuing, possibly much later. All of that needs state shared between steps
     plus edges chosen at run time, which is what a graph provides.

**Reuses:** nothing in code. The facts come from the services listed in the ticket check.

**Tests:** none (no code). The suite must be unchanged.

**Expected suite:** 127 passed (no new tests; assumes ticket 014 is delivered first as
planned: 126 at `f39f725` − 3 + 4).

**Check by hand:** open the ticket in VS Code's Markdown preview: the diagram renders with
both branches, the loop back and the human checkpoint. Every table row has a "Reuses" cell.

**Commit:** `Ticket 006: trip planner sketch, steps with their inputs, outputs and reused services, decision points, the approval checkpoint, and why a chain is not enough`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Step table (Reads / Produces), checked by hand |
| 2 | "Decision points" and "Human checkpoint" lists plus the diamonds in the diagram |
| 3 | "Reuses" column (function name or **new**) |
| 4 | "Why a chain can't express this" paragraph |

## Risks
- *The sketch fixes names before the code exists:* plans 007–010 use the same names, so a
  rename has to be made in both places. Ticket 011 records any difference instead of
  editing the sketch afterwards.
- *Mermaid syntax errors render as a blank block:* check the preview before committing.

## Out of scope (copied from the ticket)
- Any code. LangGraph isn't installed yet: that happens in ticket 007.
