# Plan for 019: Trip planner screen: start a run, approve or reject, get the plan

**Ticket:** `tickets/019-trip-planner-flow.md`
**Approach:** A "Plan the trip" section on 017's group page (`web/src/features/planner/`)
loads the group's latest run from 015's API and shows it: the start form, the proposal card
with Approve / "Not this one", the plan, or a no-plan outcome. It is built from 016's UI kit and
from the stays pieces that 017 puts in `StaysPanel`, which this ticket moves into small shared
components (`TripFields`, `StayList`, `TripLinks`) without changing the panel. The backend gets
one small guard: an answer may name the sector it answers (`sector_id`, optional), and an
answer for a sector that is no longer proposed gets a 409 like an answer to a finished run.

**Alternatives considered:**
- *Leave the stale answer to the frontend:* it can't detect it. The backend applies an answer to
  whichever proposal is waiting *now* (see Ticket check), so only the backend can refuse it.
- *Guard with a version (LangGraph's checkpoint id, or the number of rejections) instead of the
  sector id:* also works, but exposes graph internals to the client. The sector id is what the
  friend actually saw, and within a run a rejected sector is never proposed again
  (`pick_sector` skips rejected ids), so it identifies the proposal.
- *Make `sector_id` required:* breaks the existing tests, `/docs` "Try it out" and any caller
  that posts `Approval` (AC 9).
- *A standalone `PlannerAnswer` (copying `approved` and `reason`):* two definitions of the same
  answer. Subclassing `Approval` keeps one, and the resume value is still built from it.
- *Reuse `SectorCard` for the proposal:* it takes a `Sector` (crag object with region, ids,
  approach notes, a "Stays nearby" button). `PlannerSector` is flat and has no region, so it
  would need an adapter that invents data. A small `PlannerSectorCard` reuses
  `SectorCard.module.css` and the label helpers instead.
- *Load `/planner/graph` now, for 020:* nothing in 019 uses it. 020 loads it (see "Seams left
  for 020").
- *Polling so a friend's page follows along:* out of scope (ticket). The guard plus the re-read
  on 409 make a stale page safe.

**Choices on the ticket's open questions:**
- Planner section at 0 members: **yes, shown**. The "no members" outcome explains itself and
  offers "Edit members".
- After an outcome: **show the latest outcome** until someone presses "Plan again" (AC 11), so a
  friend who opens the link later sees what was decided.

## Ticket check
Checked against the code on 2026-10-14 (015 at d649584, 016 at 5fc33b3). 017 is not delivered
yet: this plan names 017's files as `tickets/017-new-frontend-groups-and-stays.plan.md`
describes them. 018 (CI) changes nothing this ticket touches.
- **Correct, the gap (AC 8):** `answer_run()` (`services/trip_planner.py:64-80`) locks the row
  and checks only `graph.get_state(config).next != (APPROVAL_NODE,)`. It never looks at *which*
  sector is waiting, so a late "Approve" lands on the next proposal. Under the lock, A's
  checkpoint is already written when B gets the row (the saver writes through its own pool
  before A's `db.commit()` releases the lock), so comparing B's `sector_id` with
  `snapshot.values["chosen_sector"]["sector_id"]` after the lock is enough.
- **Correct:** start body `PlannerRunStart` (`schemas/planner.py:42-53`): `checkin` (None =
  next Saturday, past date gives 422 "checkin can't be in the past" with `loc`
  `["body", "checkin"]`), `nights` 1-30 default 2, `guests` 1-30 or None. A guest count left out
  becomes `max(len(members), 1)` in `merge_group_preferences` (`agent/nodes.py:86-87`), so a run
  of an empty group has 1 guest.
- **Correct:** no members ends at once with "No common ground, so no search: The group has no
  members yet." (`nodes.py:89-93` and `151`); three rejections end with "No plan: the group
  turned down 3 sectors." (`nodes.py:116-120`); a plan has at most 5 stays within 10 km and both
  links (`nodes.py:40-41`, `179-203`).
- **Imprecise, "two ways to end without a plan":** a run can end with `no_plan` in five ways,
  four of them not through explain_conflicts:
  1. no common ground or no members: trace `merge_preferences, explain_conflicts`;
  2. agrees but no sector matches: `search_sectors` changes `message` ("The group agrees on
     filters, but no sector matches them.", kept by `pick_sector`);
  3. three rejections: "No plan: the group turned down 3 sectors.";
  4. fewer than three candidates, all rejected: "No plan: every candidate was turned down.";
  5. missing from the ticket: the approved sector was deleted while the group decided,
     "No plan: the chosen sector no longer exists." (`propose_plan`, `nodes.py:182-183`).
  The screen tells 1 and 2 apart from the **trace** (node names and changed field names), never
  by matching message text; 3, 4 and 5 are "No plan this time" with the backend's message.
- **Missing, AC 9 and `/docs`:** with an optional `sector_id: int | None`, Swagger's generated
  example body is `{"approved": true, "reason": "string", "sector_id": 0}`. Sector 0 is never
  proposed, so "Try it out" would get a 409, and `/docs` would no longer "work as before". The
  schema gets an explicit example without `sector_id`.
- **Imprecise, AC 1 "same defaults as stays":** `<input type="date">` shows no placeholder text,
  so "next Saturday" can't be a placeholder. It is a hint under the field ("Empty: next
  Saturday"); guests gets the placeholder `max(memberCount, 1)` and the hint "Empty: one per
  member".
- **Detail, a name clash:** 017 adds the type `BookingLinks` to `types.ts`. A shared component
  also named `BookingLinks` can't import that type in its own file (TypeScript: import conflicts
  with local declaration, `verbatimModuleSyntax` is on). The shared component is `TripLinks`.
- **Wrong for this ticket, Notes "update the frontend commands list":** that came from the old
  combined ticket (it added `npm test`). 019 adds no command; the commands lists in README and
  CLAUDE.md stay as they are. `npm test` is 020's.
- **Confirmed out of date:** README line 127 ("interrupt + InMemorySaver") and `graph.py`'s
  docstring ("in memory here"). This delivery edits README, so it fixes that line; `graph.py`
  is not touched (ticket note).

## Delivery
One build, one review, one commit for the whole ticket (no increments).

Before starting: `git log --oneline -5` must show 017 (and 018) committed. This plan names 017's
files as its plan describes them (`GroupPage`, `MemberList`, `StaysPanel` group mode,
`SectorCard` `distanceKm`, `ApiError.field`, the `BookingLinks` type). If 017 was delivered
differently, adapt the names and say so in the hand-off.

### 1. Plan the trip from the group page, and refuse a stale answer
**Files** (in build order: no migration; backend, then frontend, then docs):

*Backend: an answer names the sector it answers (AC 8, 9)*
- `backend/app/schemas/planner.py`:
  - `class PlannerAnswer(Approval)` (import `Approval` from `app.agent.state`; no import cycle:
    `agent/state.py` imports only `services/stays.py`) with
    `sector_id: int | None = Field(default=None, description="The proposal being answered. If
    the run has moved on to another sector, the answer is refused with 409.")`.
  - `model_config = ConfigDict(json_schema_extra={"examples": [{"approved": False, "reason":
    "too far"}]})`, with a one-line comment: without it, `/docs` fills in `sector_id: 0` and
    "Try it out" gets a 409.
  - A short comment on the class: friends answer *a* proposal; without the id a late answer
    applies to the next one.
- `backend/app/services/trip_planner.py`:
  - `answer_run(db, graph, run, answer: PlannerAnswer)`. Keep the row lock and its comment.
    Read `snapshot = graph.get_state(config)` once. Raise `RunNotWaiting` (after
    `db.rollback()`) when the snapshot is not paused at `APPROVAL_NODE`, **or** when
    `answer.sector_id` is set and differs from `snapshot.values["chosen_sector"]["sector_id"]`.
    Put that test in a small helper, e.g. `_waits_for(snapshot, sector_id: int | None) -> bool`.
  - Resume with `answer.model_dump(exclude={"sector_id"})`, so the resume value stays exactly an
    `Approval` (ticket note; `interrupt(response_schema=Approval)` sees the same dict as before).
  - `RunNotWaiting` docstring: "...it finished, or someone answered first (the proposal being
    answered is no longer the one waiting)."
  - Import `PlannerAnswer`; `Approval` stays imported only if still used (ruff F401).
- `backend/app/routers/planner.py`: the answer endpoint takes `body: PlannerAnswer`; drop the
  `Approval` import. The 409 detail becomes "This proposal is no longer waiting for an answer"
  (it covers both cases; no test asserts the old text). Add a `description`: "Name the
  proposal with sector_id: if someone already answered it, the answer gets 409 and changes
  nothing."
- `backend/app/scripts/trip_planner.py`: **no change** (it calls `advance()` with `Approval`
  directly, not `answer_run()`).

*Frontend: types* (`web/src/api/types.ts`, a new `// schemas/planner.py` block)
- `PlannerSector` (sector_id, sector_name, crag_name, style, grade_min, grade_max,
  `approach_minutes: number | null`, distance_km), `PlannerPlan` (`sector`, `checkin` /
  `checkout` as `"YYYY-MM-DD"` strings, nights, guests, `stays: NearbyStay[]`,
  `links: BookingLinks`), `TraceStep` (node, changed), `Rejection` (sector_id, reason),
  `PlannerRunStatus = "waiting_for_approval" | "planned" | "no_plan"`, `PlannerRun` (`run_id:
  string`, share_code, status, checkin, nights, `guests: number | null`, `proposal:
  PlannerSector | null`, `plan: PlannerPlan | null`, `message: string | null`, rejections,
  trace, `created_at: string`), `PlannerRunStart` (`checkin?`, `nights`, `guests?`),
  `PlannerAnswer` (`approved`, `reason?: string | null`, `sector_id?: number`).
- The graph types (`PlannerEdge`, `PlannerGraph`) are 020's: nothing in 019 reads them.

*Frontend: shared pieces out of 017's `SectorCard` and `StaysPanel`* (no behaviour change there,
AC 13; keep 017's markup, wording and classes exactly)
- `web/src/features/search/sectorLabels.ts`: `walkInLabel(minutes: number | null)` ("40 min
  walk-in" / "Walk-in unknown", today's string in `SectorCard.tsx:18`) and `distanceLabel(km)`
  (the "112 km from Barcelona" string 017 adds, same rounding). `SectorCard` uses both.
- `web/src/features/stays/tripDates.ts`: the date formatter 017 writes for "Sat 17 Oct to Mon
  19 Oct", moved here (a plain `.ts`: the `react-refresh` rule wants component files to export
  only components). If 017 parses `"YYYY-MM-DD"` with `new Date(string)` (that is UTC
  midnight), parse the parts as a local date instead, so no time zone shows the day before.
- `web/src/features/stays/TripFields.tsx` (+ CSS only if `Forms.module.css`'s `row` class
  doesn't fit): 017's check-in / nights / guests inputs from `StaysPanel`'s group mode.
  - `export type TripValues = { checkin: string; nights: number; guests: number | null }`.
  - Props: `value: TripValues` (what to display), `onChange(patch: Partial<TripValues>)`
    (only the field the user changed, so `StaysPanel` still sends nothing it didn't send
    before), `errors?: Partial<Record<keyof TripValues, string>>`,
    `hints?: Partial<Record<keyof TripValues, string>>`, `guestsPlaceholder?: string`.
  - Uses `Field` (its `error` / `hint`). No `min` on the date input (017's choice: the
    backend's rule is the only one).
  - `StaysPanel` passes 017's displayed values (`checkin || trip?.checkin`, `guests ??
    trip?.guests`) and no errors or hints, so it looks and behaves as before.
- `web/src/features/stays/TripLinks.tsx` + `.module.css`: 017's "4 guests, Sat 17 Oct to Mon 19
  Oct" line and the two external links "Search on Airbnb" / "Search on Booking.com"
  (`external` icon, `target="_blank"`, `rel="noopener noreferrer"`). Props `checkin`,
  `checkout`, `guests`, `links: BookingLinks`. Moved with its CSS from `StaysPanel`.
- `web/src/features/stays/StayList.tsx` + `StayList.module.css`: the `<ul>` of stays
  (`StaysPanel.tsx:89-108`: tent icon, name, type · km · price, "Hand-picked" chip, website
  link), with the classes `list`, `stay`, `icon`, `info`, `name`, `meta`, `link` moved out of
  `StaysPanel.module.css`. Prop `stays: NearbyStay[]`. `StaysPanel` keeps its own loading,
  error and empty states.

*Frontend: planner helpers* (`web/src/features/planner/plannerOutcome.ts`, plain `.ts`, pure)
- `noPlanTitle(run: PlannerRun): string`:
  - "No common ground" when `explain_conflicts` is in the trace (no common ground, no members);
  - "No sector suits everyone" when a `search_sectors` step has `message` in `changed`;
  - else "No plan this time" (three rejections, every candidate turned down, sector deleted).
- `offersMemberEdit(run): boolean`: true for the first two (AC 6: only when it helps).
- Why from the trace and not the message text: the trace is structure, the message is wording
  that may change (one comment line).

*Frontend: the planner screens* (`web/src/features/planner/`, CSS Modules, tokens only, no
inline `style=`, no hex)
- `PlannerSection.tsx` + `.module.css`: a `<section aria-labelledby>` with the heading "Plan the
  trip" and one sentence: "The planner proposes a sector everyone can climb. Approve it, and it
  finds places to stay."
  - Props `shareCode`, `memberCount`.
  - One view union (the `SearchPage` pattern): `{state: "loading"}`, `{state: "start"}`,
    `{state: "run"; run: PlannerRun; notice: string | null}`, `{state: "error"; message}`.
  - On mount, one effect loads `GET /groups/{code}/planner/runs/latest` with the cancelled flag,
    setting state only in the promise callbacks (the `StaysPanel` / 017 `GroupPage` pattern the
    `react-hooks` rules accept). `null` gives `start`; a run gives `run` with no notice
    (AC 10, 11). While loading: a loading `StateMessage` "Loading the planner" (the first
    planner request in a fresh process is slow, ticket note; no client timeout).
  - A load error shows an error `StateMessage` with a "Try again" button that loads again from
    the click handler.
  - `start(body)`: `POST /groups/{code}/planner/runs`, gives `run` (no notice). Errors go back
    to `PlannerStart`, which shows them.
  - `answer(approved, reason)`: `POST .../runs/{run_id}/answer` with `{approved, reason,
    sector_id: run.proposal.sector_id}`, then `run` with no notice (AC 2, 3, 4).
    - On `ApiError` 409: `GET .../runs/{run_id}` and show it with notice "Someone already
      answered. This is where the run is now." (AC 8). If that re-read fails, throw an Error
      "Someone already answered, and the run couldn't be reloaded. Reload the page."
    - Any other error is thrown to `ProposalPanel`, which shows it; the run stays as it was.
  - "Plan again" / "Start over" set `start`.
- `PlannerStart.tsx`: a `noValidate` form (backend rules only, as 017's member form):
  `TripFields` with `hints={{checkin: "Empty: next Saturday", guests: "Empty: one per
  member"}}` and `guestsPlaceholder={String(Math.max(memberCount, 1))}`, nights starting at 2,
  and a primary "Plan the trip" `Button` in its loading state while the request runs.
  - Body: `nights`, plus `checkin` and `guests` only when set (empty means the backend's
    default).
  - A 422 with `ApiError.field` in `checkin` / `nights` / `guests` goes to that field's error
    ("checkin can't be in the past" under check-in, AC 1). Any other error goes in an error
    `StateMessage` under the button.
  - Offered at 0 members too (AC 5).
- `RunView.tsx` + `.module.css`: one run. `PlannerSection` renders it with `key={run.run_id}`.
  - The notice, if any, as a notice `StateMessage` on top.
  - Then by status: waiting with a proposal: `ProposalPanel` (`key={proposal.sector_id}`, so the
    reason box resets for each new proposal) plus a ghost "Start over" button; planned:
    `PlanResult`; no_plan: `NoPlan`.
- `PlannerSectorCard.tsx`: `Card` + `Chip` + `Icon` with the classes of
  `../search/SectorCard.module.css` (017 already imports search CSS Modules this way): sector
  name, `pin` crag name, grade chip "6a to 7a", style chip (`styleLabel()`), the
  `distanceLabel()` line and the `clock` `walkInLabel()` line, and a `children` slot for the
  actions (AC 2).
- `ProposalPanel.tsx`: heading "Proposed sector", a `PlannerSectorCard` with "Approve"
  (primary) and "Not this one" (secondary).
  - "Not this one" opens a `Field` "Why not? (optional)" with a textarea, plus "Send" and
    "Cancel". The reason is sent trimmed, or `null` when empty (AC 2).
  - Local state: `rejecting`, `reason`, `busy: "approve" | "reject" | null`, `error`. While
    busy both actions are disabled and the pressed one shows its loading state; an error
    shows in an error `StateMessage` under the buttons.
- `PlanResult.tsx`: heading "Your trip", then `PlannerSectorCard`, `TripLinks` with the plan's
  checkin, checkout, guests and links, and `StayList` with `plan.stays`. With no stays, an empty
  `StateMessage` "No stays found near the crag" with "The booking links still search the
  area." (AC 3). A ghost "Plan again" button.
- `NoPlan.tsx`: a **notice** `StateMessage` (a normal outcome, not an error): title
  `noPlanTitle(run)`, text `run.message` exactly as the backend wrote it. Actions: "Plan again"
  and, when `offersMemberEdit(run)`, a ghost "Edit members" button that scrolls to
  `document.getElementById("members")` (a button, not `href="#members"`, so the address bar
  stays 017's clean share link) (AC 4, 5, 6).

*Frontend: wiring into 017's group page*
- `web/src/features/group/GroupPage.tsx`: in the `open` view, under group search, render
  `<PlannerSection key={group.share_code} shareCode={group.share_code}
  memberCount={group.members.length} />`. The key is the code, not the group object: a member
  change re-reads the group (a new object) and must not reset the planner. Check that 017's
  re-read after a member change keeps the `open` view (no pass through `loading`); otherwise the
  section remounts and loses a typed reason. If it does pass through `loading`, change the
  re-read to replace the group in place and say so in the hand-off.
- `web/src/features/group/MemberList.tsx`: `id="members"` on its section root, the target of
  "Edit members".

*Docs*
- `README.md`:
  - The `web/src/` heading: "(design system, search, groups, stays, trip planner)".
  - Add `features/planner/`: "Plan the trip on the group page: start a run with dates, nights
    and guests, the proposed sector with approve or not this one, the plan with stays and
    booking links, the no-plan outcomes; resumes the group's latest run."
  - `features/stays/`: add "shared `TripFields`, `StayList`, `TripLinks` (also used by the
    planner)". `features/search/`: add "`sectorLabels.ts` (walk-in and distance strings)".
  - `schemas/planner.py` line: "...start body, answer body (names the proposal it answers),
    ...". `routers/planner.py` line: "(start, latest, read, answer; a stale answer gets 409)".
  - Line 127 (`graph.py`): replace "(interrupt + InMemorySaver)" with "(interrupt; the
    checkpointer is passed in: PostgresSaver in the app, InMemorySaver in tests)".
  - No change to the commands lists (019 adds no command).
- `CLAUDE.md`, "Reuse before writing", the frontend line: add "stays pieces `TripFields` /
  `StayList` / `TripLinks` in `features/stays/`; `walkInLabel()` / `distanceLabel()` in
  `features/search/sectorLabels.ts`".

**Reuses:**
- Backend, unchanged: `start_run`, `advance`, `run_view`, `latest_run`, `find_run`, `get_run`,
  `get_trip_planner`, `RunNotWaiting`, `APPROVAL_NODE` and the row lock in `answer_run()`;
  `Approval` becomes the base of `PlannerAnswer`.
- From 016: `apiRequest()` / `ApiError`, `Button` (`loading`), `Card`, `Chip`, `Field`
  (`error`, `hint`), `StateMessage` (loading, empty, notice, error, `action`), `Icon` (`pin`,
  `clock`, `tent`, `external`), `styleLabel()`, tokens, `SectorCard.module.css`,
  `Forms.module.css`, the view-union pattern of `SearchPage` and the cancelled-flag effect of
  `StaysPanel`.
- From 017: `ApiError.field`, the stripped "Value error, " prefix, the `BookingLinks` /
  `NearbyStay` types, `GroupPage`'s open view, `MemberList`, and `StaysPanel`'s group fields,
  booking line and stay list (now `TripFields`, `TripLinks`, `StayList`).
- Backend tests: `agreeing_group` (with `near_id`, `far_id`), `start()`, `answer()`, `reject()`,
  `APPROVE` in `tests/test_planner_api.py`.

**Tests** (`backend/tests/test_planner_api.py`):
- `test_answer_for_a_sector_no_longer_proposed_is_409`: start, reject with
  `sector_id=near_id` (Far is now proposed). Then both a stale approve and a stale reject naming
  `near_id` get 409. A GET of the run still shows `waiting_for_approval`, proposal Far, and
  exactly one rejection, for Near (AC 8: nothing was approved or rejected by the late answer).
- `test_answer_naming_the_proposed_sector_goes_through`: start, approve with
  `sector_id=near_id`: 200, `status == "planned"`, `plan.sector.sector_id == near_id` (AC 9).
- `test_docs_example_answer_goes_through`: read the `PlannerAnswer` example from
  `/openapi.json` (`components.schemas.PlannerAnswer.examples[0]`), assert it has no
  `sector_id`, post it to a fresh run's answer: 200 and the proposal moved to Far (AC 9, the
  `/docs` part).
- Unchanged and still green, proving the field is optional (AC 9): every 015 test that answers
  without `sector_id` (`test_approve_returns_a_plan_with_stays_and_links`,
  `test_reject_proposes_the_next_sector_and_keeps_the_reason`,
  `test_three_rejections_end_with_no_plan`, `test_answering_a_finished_run_is_409`,
  `test_restart_resumes_on_the_same_checkpointer`, `test_get_run_matches_the_last_answer`), and
  `tests/test_trip_planner_script.py`, `tests/test_planner_checkpointer.py`.
- Frontend: no test runner (020 adds Vitest). `npm run lint` and `npm run build` in `web/`.

**Expected suite:** **202 passed** if 017 and 018 add no backend tests (199 collected on
2026-10-14 with `--collect-only`, plus 3). In general: the count collected on the delivery day
before this ticket, plus 3. `ruff check .` clean. `web/`: lint 0 problems, build succeeds. CI
(018): the three checks green.

**Check by hand** (by the user: `docker compose up -d`, `uv run alembic upgrade head`,
`uv run fastapi dev app/main.py`, `npm run dev` in `web/`; devtools device bar at 375 px,
"emulate prefers-color-scheme" for light and dark):
1. A group of 2 who agree. "Plan the trip" shows check-in (hint "Empty: next Saturday"),
   nights 2, guests (placeholder 2). Pick yesterday and press the button: "checkin can't be in
   the past" shows under check-in. Clear it, press again: a proposal appears (AC 1).
2. The card shows sector, crag, grades, style, "N km from Barcelona" and the walk-in, with
   Approve and "Not this one". "Not this one" opens "Why not? (optional)" with Send and
   Cancel (AC 2).
3. Send "too far": the next sector is proposed and the reason box is empty again. Reject until
   the run ends (a group with three matching sectors): "No plan this time" with "No plan: the
   group turned down 3 sectors.", "Plan again" and **no** "Edit members" (AC 4, 6).
4. Plan again, Approve: "Your trip" shows the sector, "2 guests, Sat … to Mon …", up to five
   stays with km, and the Airbnb and Booking.com links open with those dates and guests. On a
   crag with no stays within 10 km: the "booking links still search the area" message (AC 3).
5. A group whose members share no grade: "No common ground" with the backend's reasons and
   "Edit members", which scrolls to the member list. The same for a new group with no members.
   A group that agrees on filters no sector matches: "No sector suits everyone" with "Edit
   members" (AC 5, 6).
6. Start a run and leave it waiting. Open the share link in a second browser: the same proposal
   shows and can be answered (AC 7). In A, reject. In B, without reloading, press Approve:
   "Someone already answered. This is where the run is now." with the *new* proposal; in A,
   reload: nothing was approved (AC 8).
7. In `/docs`, "Try it out" on the answer endpoint with the shown example: 200 (AC 9).
8. With a run waiting, reload: it is there and can be answered. Stop the backend (Ctrl+C),
   start it again, reload: still there, Approve works (AC 10). After it ends, reload: the plan
   (or no plan) shows with "Plan again" (AC 11).
9. At 375 px in both themes: the form fields stack, cards and buttons fit, no sideways scroll,
   no white boxes in dark mode (AC 12).
10. Regression: "Stays nearby" from Find crags (radius, type, empty state) and from a group
    result (dates, nights, guests, booking line, links, past-date message) behave as before
    (AC 13).

**Commit:** `Ticket 019: plan the trip from the group page (start with dates, nights and guests, proposed sector with approve or not this one and a reason, plan with stays and booking links, no-plan outcomes with edit members when it helps, latest run resumed); an answer names the proposal it answers so a late answer gets 409 instead of landing on the next sector; stays fields, list and booking line shared with the stays panel`

## Seams left for 020
- **Where the diagram goes:** in `RunView`, above the outcome. `RunView` is keyed by
  `run.run_id`, so 020's "steps shown" counter lives there and resets on a new run with no reset
  code; an answer keeps the same `run_id`, so only the new steps animate.
- **What 020 reads:** `run.trace`, `run.status`, `run.rejections`, `run.proposal`, `run.plan`
  and `run.message` (all in the `PlannerRun` type), plus `GET /planner/graph`, which 020 loads
  and types (`PlannerGraph`, `PlannerEdge`).
- **Animate or not:** 020 adds `animate: boolean` to the `run` view in `PlannerSection`: true
  after `start` / `answer` in this tab, false after the mount load and the 409 re-read.
- **Pure helpers to test:** `plannerOutcome.ts` (and `tripDates.ts`) are plain `.ts` files, so
  020's Vitest can cover them next to its own helpers.

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Manual check 1; backend `test_start_rejects_bad_input`, `test_start_run_pauses_with_a_proposal_and_a_trace` |
| 2 | Manual check 2 |
| 3 | Manual check 4; backend `test_approve_returns_a_plan_with_stays_and_links` |
| 4 | Manual check 3; backend `test_reject_proposes_the_next_sector_and_keeps_the_reason`, `test_three_rejections_end_with_no_plan` |
| 5 | Manual check 5; backend `test_group_without_common_ground_ends_at_once`, `test_group_without_members_ends_with_no_plan` |
| 6 | Manual checks 3 and 5 |
| 7 | Manual check 6; backend `test_get_run_matches_the_last_answer`, `test_latest_run_is_the_newest` |
| 8 | `test_answer_for_a_sector_no_longer_proposed_is_409`; backend `test_answering_a_finished_run_is_409`; manual check 6 |
| 9 | `test_answer_naming_the_proposed_sector_goes_through`, `test_docs_example_answer_goes_through`, the unchanged 015 answer tests; manual check 7 |
| 10 | Manual check 8; backend `test_restart_resumes_on_the_same_checkpointer` |
| 11 | Manual check 8; backend `test_latest_run_is_the_newest` |
| 12 | `npm run lint`, `npm run build`, `uv run pytest`; manual check 9 |
| 13 | Manual check 10 |

Every frontend behaviour is checked by hand: `web/` has no test runner until 020. The backend
tests prove the data and the guard the screens rely on. The reviewer should grep `web/src` for
hex colours outside `tokens.css` and for inline `style=`.

## Risks
- **The answer body changes:** `sector_id` is optional and excluded from the resume value, so
  the script, the 015 tests, `test_planner_checkpointer.py` and anyone posting `Approval` keep
  working. The 409 detail text changes; no test or screen reads it (the screen shows its own
  sentence).
- **A true race is not unit-tested:** two simultaneous requests are serialised by the row lock
  (015). The new test covers the sequential case, which is the one the lock alone can't catch.
  Manual check 6 covers the user-visible flow.
- **Refactoring 017's `StaysPanel`:** moving the fields, list and booking line must not change
  single-sector or group stays (AC 13). `TripFields` reports only the changed field, so the
  panel's request URLs stay the same. Manual check 10. If 017 was delivered differently from its
  plan, adapt and report.
- **Abandoned waiting runs:** "Start over" while waiting leaves the old run paused (no endpoint
  cancels a run). The group page always shows the latest run, so it is invisible; a friend with
  a stale tab could still answer the old run and see its result until a reload. Same "no push"
  limit the ticket accepts; a cancel endpoint would be a new ticket.
- **First planner request is slow:** `get_trip_planner` sets up the checkpoint tables on first
  use. The section shows its loading state; nothing times out client-side.
- **Shared test database:** the three new tests use the existing fixtures and the test DB like
  the 015 tests. Nothing new about isolation.
- **External services:** none. The planner calls no Claude, Voyage or Overpass (stays come from
  the database), and these endpoints have no rate limit. 018's outbound block in CI stays
  satisfied.
- **Migration / existing data:** none. Existing runs in `planner_runs` and the checkpoint tables
  show as they are; their shape is unchanged.

## Out of scope (copied from the ticket)
- The graph diagram, the step-by-step highlight, the plain-word step list and a frontend test
  runner: ticket 020.
- Changes to the graph itself (new nodes, LLM calls in the planner): this ticket shows the
  existing graph's results.
- Real-time push when a friend answers (websockets, polling): a refresh or reopening the page
  shows the new state.
- A history of all past runs: only the latest run is shown.
