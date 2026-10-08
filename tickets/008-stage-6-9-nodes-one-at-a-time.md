# 008: Stage 6.9, add nodes one at a time

**Status:** Ready
**Size:** M
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Add exactly one node: 'merge group preferences' (reusing your Stage 4 function). Run the graph with just that one node and inspect the resulting state. Add the 'search sectors' node next. Repeat for 'find stays' (Stage 5). At each addition, run the graph and print the state before moving to the next node. Resist wiring everything at once."

## User story
As the learner, I want to add the planner's nodes one by one, running the graph and
printing the state after each, so that I see exactly what every node adds.

## What exists today
- The state and the empty graph from ticket 007.
- Functions to reuse, unchanged:
  - `merge_preferences(members)` (pure, `services/group_matching.py`);
  - `search_for_group(db, members, mode, fit)` (`services/group_search.py`);
  - `find_stays_near(db, lat, lon, max_distance_km, stay_type=None)` (`services/stays.py`).
- A real group to run on: "Checkpoint demo" (share code `9JS3VA3C`) in the dev database.

## Acceptance criteria
1. Given the graph with only `merge_preferences` (START → merge → END), when it runs on a
   real group, then the printed state shows the merged filters (or the conflicts).
2. Given the `search_sectors` node added after it, when it runs, then the state shows the
   candidate sectors. Nothing from step 1 is lost.
3. Given the `find_stays` node added after it, for the top candidate, when it runs, then
   the state shows nearby stays. "Pick a sector" stays a fixed rule for now (the top
   result), until ticket 010 adds approval.
4. Given every node, then it calls the existing service function and contains no copied
   matching or search logic.
5. Given each run, then it's a separate playground step (for example `6.9a`, `6.9b`,
   `6.9c`), so each stage can be run again on its own.

## Scope
**In:** three nodes, connected in a straight line, with a printed state after each.
**Out:** conditional routing (ticket 009) and the pause for approval (ticket 010).

## Notes for the tech lead
- Nodes return only the fields they change, as partial updates.
- `find_stays_near` returns `(Stay, distance)` ORM pairs. Convert them to plain dicts or
  ids before putting them in the state (see ticket 007's note on serializable state).
- No Claude or Voyage calls are needed in these nodes: they're plain services.
