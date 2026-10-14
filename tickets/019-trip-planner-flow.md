# 019: Trip planner screen: start a run, approve or reject, get the plan

**Status:** Ready
**Size:** L (backend and frontend; no migration). Kept as one ticket because the backend change is small and the screen depends on it.
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Prepare tickets for creating the frontend with associating what we've done in the backend and a new frontend. I want to include the AI part with the graphs. Create a nice design. Do the plan." (split from the old ticket 018 on 2026-10-14; this is its first half, the "flow". The diagram is ticket 020.)
**Part of:** the new frontend (015 → 016 → 017 → 019 → 020). Needs 015 (API) and 017 (group page). Independent of 018 (CI).

## Decisions already made by the user (2026-10-13)
- The planner runs from the browser, with a diagram of the graph that highlights the nodes
  as the run goes through them, then the approve or reject step, then the final plan. This
  ticket does everything except the diagram (ticket 020).

## User story
As a group of friends, I want to press "Plan the trip", see the sector the planner proposes,
approve it or turn it down, and get a ready plan with stays and booking links, so that we
decide quickly together, even when we open the same group from different phones.

## What exists today
(Checked against the code on 2026-10-14. Items marked "earlier plan" were found by the tech
lead on 2026-10-13 and not re-checked.)
- The graph (`backend/app/agent/graph.py`, nodes in `nodes.py`): merge preferences, then search
  sectors, or explain conflicts when there is no common ground; then pick a sector; then wait
  for the group's answer; then find stays; then propose the plan. A rejection goes back to
  pick another sector. After three rejections, or when nothing is left, it ends without a plan.
- The planner API from 015 is delivered (`backend/app/routers/planner.py`): start a run
  (`POST /groups/{code}/planner/runs`, 201), the latest run (a run, or `null`), a run by id,
  answer a run (409 when the run is not waiting), and the graph structure.
  - A run says `status` (`waiting_for_approval`, `planned` or `no_plan`), the `proposal`
    while waiting, the `plan`, a `message`, the `rejections` and a `trace`
    (`schemas/planner.py`, `agent/state.py`).
  - Start takes a check-in date (default next Saturday, not in the past), nights (1 to 30,
    default 2) and guests (1 to 30, default the member count; earlier plan).
  - A group with no members can start a run: it ends at once with no plan and the message
    "No common ground, so no search: The group has no members yet." (earlier plan). So, unlike
    the group search of 017, the planner must be offered at 0 members.
  - A plan carries the sector, dates, guests, at most five stays within 10 km and Airbnb and
    Booking.com links (earlier plan).
  - Paused runs survive a restart, because they are kept in Postgres.
- **A gap in the backend (wrong for "two friends answer at the same time").** The answer
  endpoint takes only `approved` and an optional reason (`Approval` in `agent/state.py`).
  `answer_run()` in `services/trip_planner.py` locks the run and checks that it is paused,
  but not **which** proposal is paused. Suppose friend A turns down sector Near while friend
  B, who still sees Near, presses Approve. A is served first and Far becomes the proposal. B's
  answer then finds the run waiting and approves Far, which B never saw, with no "someone
  already answered". The frontend cannot detect this. So the answer needs to name the sector
  it answers, and a late answer for a sector that is no longer proposed must get a 409.
- Two ways to end without a plan that do not go through the conflicts step (earlier plan):
  - the group agrees on filters, but no sector matches: the message is "The group agrees on
    filters, but no sector matches them." (`services/group_search.py`);
  - fewer than three candidates exist and all are turned down: "No plan: every candidate was
    turned down."
  - After three rejections: "No plan: the group turned down 3 sectors." (`agent/nodes.py`).
  A run's `status` is `no_plan` in all of them. Only the `message` and the `trace` tell the
  causes apart.
- The new app: `web/` has the design system, the search pages and a stays panel
  (`web/src/features/stays/StaysPanel.tsx`). The group page is still a placeholder
  (`GroupPlaceholder.tsx`); ticket 017 builds it, with the check-in, nights and guests fields
  and the booking-links line inside its stays panel. `web/src/api/types.ts` has no planner
  types yet.
- The planner response gives a sector in a flat shape (name, crag name, style, grades,
  walk-in minutes, distance) and not the shape the search cards use (earlier plan).
- `web/` has no test runner (016 left it out). Ticket 020 adds one.

## Acceptance criteria
1. Given a group page, when "Plan the trip" is pressed (with optional check-in date, nights
   and guests, same defaults as stays), then a run starts. Given a check-in date in the past,
   then the backend's message shows next to that field.
2. Given a run waiting for the group, then the proposed sector is shown as a card (crag,
   grades, style, distance, walk-in) with "Approve" and "Not this one". "Not this one" asks
   for an optional reason.
3. Given an approval, then the plan is shown: sector, dates, guests, up to five stays with
   distance, and the Airbnb and Booking.com links. Given a plan with no stays, then a normal
   message says the booking links still search the area.
4. Given a rejection, then the next proposal appears. Given the third rejection, then the run
   ends with the message "No plan: the group turned down 3 sectors.", and a way to start again.
5. Given a group with no common ground, or no members, when a run starts, then the reasons
   are shown as a normal outcome (not an error), with a link back to edit members.
6. Given a group that agrees but where no sector matches, or where every candidate is turned
   down with fewer than three, then the backend's message is shown as a normal outcome, with a
   way to start again. The member-edit link is offered only when it helps (no common ground, no
   members, or no matching sector).
7. Given a friend opens the group link while a run is waiting, then they see the same
   proposal and can answer it.
8. Given two friends who both see the same proposal, when one answers and the other then
   answers the old proposal, then the second gets a 409 from the backend, sees "Someone
   already answered. This is where the run is now.", and the current state (the new proposal or
   the outcome) is shown. Nothing was approved or rejected by the late answer.
9. Given an answer that names the sector currently proposed, then it works as before. Given an
   answer that names no sector (existing callers, the terminal script, `/docs` examples), then
   it still works as before.
10. Given a page reload, or the server restarting, while a run is waiting, then the group page
    shows the latest run where it was and it can still be answered.
11. Given a run that already ended, when the group page opens, then the latest outcome (plan
    or no plan) shows, with a way to plan again.
12. Given phone width and both themes, then the new screens stay readable and use the design
    tokens. `npm run lint` and `npm run build` pass, and `uv run pytest` passes.
13. Edge case: given the stays panel on a single sector and on a group sector (017), then they
    behave exactly as before this ticket (dates, guests, links).

## Scope
**In:**
- The "Plan the trip" section on the group page: start with dates, nights and guests; the
  proposal card; approve or "Not this one" with a reason; the plan with stays and booking
  links; all the no-plan outcomes; resuming the latest run.
- The backend change: an answer names the sector it answers, and a stale answer gets a 409.
  It stays optional, so existing callers keep working.
- Sharing the stays pieces (date fields, stay list, booking-links line) between the stays panel
  and the planner, without changing the stays panel's behaviour.
- The planner's response shapes in the new app's `types.ts`.

**Out:**
- The graph diagram, the step-by-step highlight, the plain-word step list and a frontend test
  runner: ticket 020.
- Changes to the graph itself (new nodes, LLM calls in the planner): this ticket shows the
  existing graph's results.
- Real-time push when a friend answers (websockets, polling): a refresh or reopening the page
  shows the new state.
- A history of all past runs: only the latest run is shown.

## Open questions
- [non-blocking] Should the planner section appear on the group page when the group has no
  members? (suggested default: yes, so the "no members" outcome is reachable and explains
  itself, with the link to add members.)
- [non-blocking] After an outcome, show it until the user chooses "Plan again", or start fresh
  on every visit? (suggested default: show the latest outcome, as in criterion 11, so a friend
  who opens the link later sees what was decided.)

## Notes for the tech lead
- This is the first half of the old ticket 018, split as the earlier plan suggested ("018a").
  Check what 017 actually delivered (file names, the stays panel) before planning: this ticket
  describes behaviour, not files.
- Backend change is small but real: it changes the answer body and the 409 text. Keep the new
  field optional, keep the row lock, keep the resume value exactly an `Approval`. New backend
  tests belong in `tests/test_planner_api.py` (a late answer gets 409 with the run unchanged;
  an answer naming the proposed sector works; the existing tests answering without a sector
  stay green).
- No migration. No paid API is called by the planner, and there is no rate limit on these
  endpoints.
- The paused node `approve_sector` is not in a run's trace while waiting. The diagram in 020 will
  need that; this ticket does not.
- Add the planner's response shapes to `web/src/api/types.ts` (mirror the backend schemas, update
  both together, per CLAUDE.md). Reuse the UI kit, `apiRequest()` / `ApiError` and the tokens.
- The first planner request in a fresh process is slow, because the checkpoint tables are set up
  then. Show a loading state; nothing should time out on the client.
- `graph.py`'s docstring and README line about `InMemorySaver` are out of date since 015
  (earlier plan). Not this ticket's to fix unless you are in those files.
- Update `README.md` structure and the frontend commands list (Definition of done 3).
