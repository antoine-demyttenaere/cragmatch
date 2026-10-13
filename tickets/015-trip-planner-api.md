# 015: Trip planner over HTTP, with paused runs saved in Postgres

**Status:** Ready
**Size:** L (new dependency and persistent tables; backend only)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Prepare tickets for creating the frontend with associating what we've done in the backend and a new frontend. I want to include the AI part with the graphs. Create a nice design. Do the plan."
**Part of:** the new frontend (015 → 016 → 017 → 018). This ticket gives 018 its API.

## Decisions already made by the user (2026-10-13)
- The web app runs the LangGraph trip planner, with a live diagram of the graph (ticket 018).
- Paused runs are saved in Postgres, so they survive a server restart (not in memory).
- Delivery mode, one delivery per ticket.

## User story
As a group of friends, I want to start the trip planner from the web app and answer its
proposal later, maybe from another phone, so that we can plan a trip without anyone running
a script in a terminal.

## What exists today
(Checked against the code on 2026-10-13.)
- The graph: `backend/app/agent/graph.py` `build_trip_planner(checkpointer)`, with nodes in
  `agent/nodes.py` and the state in `agent/state.py` (`TripState`, `initial_state()`,
  `Approval`, `PlannerContext`). It pauses in `approve_sector` with `interrupt()`. A
  rejection loops back to `pick_sector`, which proposes at most three sectors.
- The only way to run it is `backend/app/scripts/trip_planner.py` (`run_planner()`): an
  `InMemorySaver`, one `uuid4` thread id per run, a trace built from
  `stream(..., stream_mode="updates")`, and approval typed in the terminal.
- The same input rules exist in two places: `trip_planner.py` `main()` and
  `GET /groups/{code}/sectors/{id}/stays` (checkin not in the past, nights 1-30,
  guests 1-30, default checkin next Saturday).
- Group lookup by share code: `services/groups.py` `find_group()`, `routers/groups.py`
  `get_group`.
- **Missing:** an HTTP endpoint for the planner, a run id the frontend can keep, and a
  persistent checkpointer. `langgraph-checkpoint-postgres` is not installed: `uv.lock` has
  only `langgraph-checkpoint`.
- **Missing:** a way for the frontend to get the graph's nodes and edges. Today the Mermaid
  diagram is only printed by playground step 6.10 (`graph.get_graph().draw_mermaid()`).
- Ticket 013 (Stage 7) had "planner endpoint + persistent checkpointer" as an open
  question. This ticket answers it.

## Acceptance criteria
1. Given a group with common ground, when a run is started for its share code, then the
   response has a run id, the status "waiting for approval", the proposed sector (name,
   crag, grades, style, distance, walk-in), and the trace so far: each node that ran, in
   order, with the state fields it changed.
2. Given a paused run, when the group approves it, then the run finishes with the status
   "planned" and the plan (sector, check-in and check-out, guests, up to five stays with
   their distance, Airbnb and Booking.com links). The trace now also has `approve_sector`,
   `find_stays` and `propose_plan`.
3. Given a paused run, when the group rejects it with a reason, then the next candidate is
   proposed and the reason is kept with the run. Given a third rejection, then the run ends
   with the status "no plan" and the message "the group turned down 3 sectors".
4. Given a group with no common ground (or no members), when a run is started, then it ends
   at once with the status "no plan", the conflicts as a message, and a trace that went
   through `explain_conflicts`. This is a normal answer, not an error.
5. Given a run id, when its run is fetched, then the response has the same status, proposal,
   plan or message, and trace as the last answer. This works for anyone with the group's
   share code.
6. Given a paused run, when the API server is restarted and the run is answered, then the
   run continues where it stopped.
7. Given a group's share code, when its latest run is asked for, then that run is returned,
   or "no run yet" when there is none.
8. Given the API, when the planner's structure is asked for, then it returns the graph's
   nodes and edges, and marks which edges are conditional. They match `build_trip_planner()`.
   Adding a node to the graph changes this response without any other change.
9. Error cases: an unknown share code gives 404. An unknown run id, or a run of another
   group, gives 404. Answering a run that is not waiting gives 409: it already finished, or
   a friend answered first. A past checkin date, or nights or guests outside 1-30, gives 422.
10. Given the test suite, then it runs without the network and without a Postgres
    checkpointer outside the `cragmatch_test` database.

## Scope
**In:**
- Endpoints to start a run, fetch a run, fetch a group's latest run, answer a paused run,
  and get the graph structure.
- A persistent checkpointer in the project's Postgres database.
- The `trip_planner` script and the API share the same run logic. The script keeps working.
- Tests for each criterion above.

**Out:**
- The planner screen and diagram: ticket 018.
- Streaming each node to the browser while it runs (server-sent events, websockets): the
  graph makes no LLM calls and finishes in well under a second. The trace in the response is
  enough to animate the diagram.
- Cleaning up old runs: there are a handful of groups. Revisit in Stage 7.
- Login or per-member identity: the share code stays the only access, as for every group endpoint.
- Rate limiting: the planner calls no paid API (no Claude, no Voyage).

## Open questions
- [non-blocking] Can a group have several runs at once? (suggested default: yes, every
  start creates a new run. "Latest run" is the one the group page shows. Older runs can
  still be fetched by id.)
- [non-blocking] Who can approve? (suggested default: anyone with the share code. There is
  no login, the same as for editing members.)
- [non-blocking] Does the reason given for a rejection show in the final plan? (suggested
  default: it shows in the run's history, and the plan itself stays as it is.)

## Notes for the tech lead
- Check `langgraph-checkpoint-postgres` against the INSTALLED `langgraph` version before
  choosing it. It uses psycopg 3, which is already a dependency. Its tables are made by the
  library's own `setup()`, not by Alembic. Decide how they are created, and keep
  `alembic/env.py` from trying to drop them (it only compares our own tables).
- Windows + OneDrive: stop the dev server before `uv add`.
- The context (the db session) is not saved by the checkpointer. It must be passed on every
  call, resumes included. Nothing before `interrupt()` may have side effects (see the
  `graph.py` docstring).
- A run must not be readable through another group's share code (criterion 9). The run id
  is a thread id, so check that it belongs to the group.
- Tests: `backend/tests/conftest.py` has the group, sector and stay factories, and
  `test_agent_graph.py` / `test_trip_planner_script.py` show how the graph is driven. The
  checkpointer has to be swappable in tests (test DB or `InMemorySaver`). Criterion 6 can be
  tested by building a fresh graph on the same checkpointer.
- Rate-limited endpoints need `request: Request`. Not needed here, see Out.
- Follow the routers/services split: the router stays thin, the run logic is a service.
- After this ticket, update ticket 013's open question about the planner endpoint.
