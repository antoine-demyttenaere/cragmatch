# 012: Stage 6.13, tests for the nodes and the approval pause

**Status:** Ready
**Size:** M
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Test individual nodes in isolation (a node is just a function, so this is straightforward). One test that runs the graph and checks it pauses correctly at the human-in-the-loop step."

## User story
As the maintainer, I want tests for each node and for the pause, so that changes to the
planner or to the services it reuses can't silently break it.

## What exists today
- Test setup: `conftest.py` (isolated `cragmatch_test` database, a session per test,
  `client`), and plain stand-ins for members in `tests/test_group_matching.py`.
- Tests never touch the network (CLAUDE.md). The planner nodes call no external services,
  only the database.

## Acceptance criteria
1. Given each node, when it's called directly with a hand-built state, then a test checks
   the partial update it returns (merge with and without common ground, search, stays,
   plan).
2. Given the routing function, when it gets a state with and without common ground, then a
   test checks that it returns the right next node.
3. Given the compiled graph with an in-memory checkpointer, when it runs for a test group,
   then a test checks that it stops at the approval step with a chosen sector and no
   stays.
4. Given that paused run, when it's resumed with an approval, then a test checks that the
   final plan has stays. When it's resumed with a rejection, then no stays are looked up
   for the rejected sector.
5. Given the no-common-ground group, when the graph runs, then a test checks that it ends
   without searching.
6. Given all the tests, when `uv run pytest` runs, then they pass with the existing suite
   (96+ tests) and need no network.

## Scope
**In:** `tests/test_agent_nodes.py` and `tests/test_agent_graph.py` (names to confirm).
**Out:** load testing, and tests of a web API for the planner (none exists in Stage 6).

## Notes for the tech lead
- Build the test group and sectors through the database session, as `test_groups_api.py`
  does, so the nodes read the same tables as in the app.
- Use a fresh thread id in each graph test, so checkpoints can't leak between tests.
