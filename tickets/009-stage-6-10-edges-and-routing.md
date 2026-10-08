# 009: Stage 6.10, edges and a conditional edge for "no common ground"

**Status:** Ready
**Size:** S
**Mode:** guide. The user writes the code (see CLAUDE.local.md). This is a step brief, not for `/deliver-increment`.
**Raw request:** "Now connect the nodes with edges, and only now ask Claude Code to explain the difference between a normal edge and a conditional edge. Add one conditional edge: if the group's merged preferences have no overlap (from Stage 4's 'no common ground' case), route to a different node instead of continuing."

## User story
As a group that can't agree, I want the planner to stop and explain the conflicts instead
of searching anyway, so that we know what to change.

## What exists today
- The straight-line graph from ticket 008 (merge → search → stays).
- `MergeResult.common_ground` and `MergeResult.conflicts`: a readable list such as "No
  grade everyone climbs: Ana wants 7a or harder, but Marc wants 6b or easier."
- Strict mode already returns "no common ground" as a normal answer, not an error.

## Acceptance criteria
1. Given a group with common ground, when the graph runs, then it follows
   merge → search → stays, and the result is the same as in ticket 008.
2. Given a group with no common ground, when the graph runs, then it goes
   merge → `explain_conflicts` → END: no search and no stays are run, and the state holds
   the conflict messages.
3. Given the routing function, then it reads only the state and returns the name of the
   next node. It has no side effects.
4. Given the explanation, then it covers: a normal edge always goes to the same node; a
   conditional edge calls a function on the state to decide; why the routing function
   must stay pure.
5. Given the graph, when its diagram is printed (Mermaid or ASCII), then the branch is
   visible.

## Scope
**In:** the edges, one conditional edge, and an `explain_conflicts` node.
**Out:**
- Using Claude to word the explanation: the conflict strings already exist.
- Suggesting which preference to relax: that was the removed ticket 002 (still in git
  history), not part of Stage 6.

## Notes for the tech lead
- For a test group, give two members grade ranges that don't overlap, for example 5–6a
  and 7a–8a.
