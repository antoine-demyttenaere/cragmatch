# 007: Stage 6.8, the trip planner's state, and nothing else

**Status:** Ready
**Size:** S
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Define the graph's state object first, before any nodes: what data flows through the whole process (group prefs, candidate sectors, chosen sector, candidate stays, final plan). Have Claude Code explain what 'state' means in LangGraph and why it's shared, before you write a single node."

## User story
As the learner, I want to define the state that flows through the trip planner before
writing any node, so that every later node only reads and writes known fields.

## What exists today
- The data the state will hold already has types: `Member` and `Preferences`,
  `MergeResult` and `SearchFilters`, `GroupSearchResponse` and `GroupSectorMatch`, and
  `(Stay, distance_km)` pairs from `find_stays_near()`.
- **Missing:** `langgraph` isn't installed, and there's no folder for agent code.

## Acceptance criteria
1. Given the backend dev server is stopped, when `uv add langgraph` runs, then it installs
   without breaking the `pgvector<0.4` pin, and `uv run pytest` still passes.
2. Given the state definition, when it's read, then it has fields for: the group
   (code or members), merged preferences or conflicts, candidate sectors, the chosen
   sector, candidate stays, the trip dates and number of guests, and the final plan.
3. Given each field, then a comment says which node writes it.
4. Given the state, when a graph with zero nodes (START → END) is compiled and invoked with
   an initial state, then the same state comes back, printed.
5. Given the explanation, then it covers: state is the shared input and output of every
   node, nodes return partial updates that LangGraph merges, and what a reducer is (even
   if none is needed yet).

## Scope
**In:** `langgraph` dependency, the state definition, the empty-graph run.
**Out:** nodes (ticket 008) and edges (ticket 009).

## Decisions
- Agent code lives in a new `backend/app/agent/` package, separate from `app/rag/`
  (retrieval). Add it to the README structure.

## Notes for the tech lead
- Check the state style against the INSTALLED `langgraph` version: `TypedDict` (the usual
  default) vs a Pydantic model. Prefer `TypedDict` unless there's a reason.
- Keep database sessions and ORM objects out of the state, because state must be
  serializable for the checkpointer in ticket 010. Store ids and plain values, and pass
  the db session to nodes another way (for example through the graph's runtime config).
