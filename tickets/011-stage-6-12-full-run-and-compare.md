# 011: Stage 6.12, full run on a real group, then compare with the sketch

**Status:** Ready
**Size:** S
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Run the whole graph end to end on a real group scenario. Ask Claude Code to explain, node by node, what happened on this run. Go back to Step 6.7's paper sketch and check it against what you actually built."

## User story
As the learner, I want to run the finished planner on a real group and trace every node,
so that I can explain the graph and see where it differs from my first sketch.

## What exists today
- The full graph from ticket 010 (merge, routing, search, pick, approval pause, stays, plan).
- The sketch in ticket 006.
- The "Checkpoint demo" group (`9JS3VA3C`) in the dev database. Members can now also set
  `max_approach_minutes` (ticket 001).

## Acceptance criteria
1. Given a script `uv run python -m app.scripts.trip_planner <share_code>`, when it runs,
   then it shows the proposed sector, asks for approval in the terminal, and prints the
   final plan (sector, stays, booking links).
2. Given one run with common ground and one without, then both paths are shown working.
3. Given the run, then a node-by-node trace is printed: node name, the fields it changed.
4. Given ticket 006's sketch, then a short "Built vs sketched" note is added to that
   ticket: what matched, what changed, and why.

## Scope
**In:** a run script, a trace, and the comparison note.
**Out:** an API endpoint or UI for the planner (see "Open questions").

## Open questions
- [non-blocking] Should a group run the planner from the web app (an endpoint plus an
  approval screen)? (suggested default: not in Stage 6. Checkpoint B needs "a group can
  run it", and a terminal script meets that. An endpoint fits better with Stage 7, when the
  checkpointer has to persist between requests.)

## Notes for the tech lead
- LangGraph can stream updates per node (`stream_mode="updates"`), which gives the trace
  without extra prints in the nodes. Check this against the installed version.
