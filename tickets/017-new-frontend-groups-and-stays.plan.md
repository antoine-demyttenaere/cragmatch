# Plan for 017: New frontend, part 2: group trip, then retire the old frontend

**Ticket:** `tickets/017-new-frontend-groups-and-stays.md`
**Approach:** The "Group trip" placeholder in `web/` becomes a real group feature in
`web/src/features/group/`: start (create, join, recent groups), the open group (name, share
link, members) and group search (scored or strict, overlap or cover). It is built only from
016's UI kit, `apiRequest()` / `ApiError` and the existing backend endpoints, so the backend
does not change. `SectorCard` and `StaysPanel` get optional group extras (distance and fit
details; dates, guests and booking links) instead of being copied. Once every old screen
exists in `web/`, `frontend/` is deleted and the hook, agents, CLAUDE.md and README point
only at `web/`.

**Alternatives considered:**
- *Port `frontend/src/GroupPage.tsx` as one file:* it is 250 lines with 11 `useState`s, and
  it clears stale results by hand. Small components plus a single "view" union (the
  `SearchPage` pattern from 016) are easier to review, and they give 019 a clear place to
  add "Plan the trip".
- *A separate `GroupSectorCard` and `GroupStaysPanel`:* these would copy most of the
  existing card and panel. Optional props on the existing ones keep one card and one
  panel (reuse rule).
- *Search on every mode or fit change through an effect (the `StaysPanel` derived-URL
  pattern):* the URL doesn't change when members change, so stale results would need a
  refresh counter. An explicit "Find sectors" button, which also re-runs when the mode or
  fit changes while results are showing, needs no effect and no counter.
- *A frontend test runner (Vitest):* 016 decided against one. Adding it here would mean a
  new dependency and config, which is outside this ticket. See Risks.

**Choices on the ticket's open questions:**
- Default search mode: **scored** (the backend's default, and it always shows something).
  Default fit: **overlap** (also the backend's default).
- Recent groups: **yes**, the last 5 in `localStorage`. Each entry is `{code, name}`. The
  ticket suggested codes only, but a bare "9JS3VA3C" is hard to recognise. The group name
  is not personal data, and no member data is stored.

## Ticket check
Checked against the code on 2026-10-13; ticket numbers updated to the 2026-10-14
renumbering. No backend change is needed.
- **Correct:** every endpoint and field listed in "What exists today"
  (`routers/groups.py`, `schemas/group.py`, `schemas/stay.py`). Group results also carry
  `distance_km` (from Barcelona), and the plan shows it. `find_group()` upper-cases the
  code, so `?group=abcd2345` works too.
- **Incomplete, AC 4:** members also have `max_approach_minutes` (1-180), and the old
  `MemberForm` edits it. The plan shows an empty member as "Any grade, Any distance, Any
  walk-in, Any style".
- **Imprecise, AC 3:** "the backend's message" is not readable as it comes back today:
  - Pydantic puts "Value error, " in front of model-validator messages, e.g.
    "Value error, Half a range makes no sense for matching: set both grades or neither".
  - Field errors such as "Input should be greater than 0" don't say which field they are
    about (the field is only in `loc`).
  - The browser's own validation (`required`, `min`, `max`) would stop most invalid values
    before they reach the backend, so its message would never show.
  The plan: the member form uses `noValidate`. `errorMessage()` drops the "Value error, "
  prefix. `ApiError` carries the field name from `loc`, and the form shows the message
  under that field, or under the form when it is about the whole member.
- **Imprecise, AC 5:** the reasons are fuller than "too easy" / "too far". `why_not()`
  returns "too easy", "too hard", "only covers part of 6a–7a", "too far (112 km > 80 km)",
  "approach too long (40 min > 20 min)" and "wrong style (trad)", joined with ", ". The
  app shows them as they come.
- **Imprecise, AC 7:** the backend never errors on an empty group. `search_for_group()`
  answers 200 with `common_ground: false` and "Add at least one member to search.". The
  app still asks for members before offering search, so that answer is never needed.
- **Missing from the ticket:** strict mode has a third outcome. When the group agrees but
  no sector matches, `common_ground` is true, `filters` is set, `results` is empty and
  `message` is "The group agrees on filters, but no sector matches them." The plan shows
  that as an empty state, with the same "Try scored mode" action.
- **Detail:** stays `guests` defaults to `max(len(members), 1)`, so an empty group gets 1
  guest, not 0.
- **Detail:** the new `App.tsx` only *reads* `?group=`. The old app also *wrote* it back
  with `history.replaceState`, so the address bar was always a shareable link. The plan
  restores that.
- **Detail:** create must POST to `/groups/` (with the slash, the route is `"/"` under the
  `/groups` prefix). `/groups` without the slash answers with a 307 redirect.
- **Leftovers to remove (AC 9), verified:** `.claude/hooks/lint_after_edit.py:16-17`,
  `.claude/agents/developer.md:21-22`, `.claude/agents/tech-lead.md:40-41`,
  `CLAUDE.md:15-16,27`, `README.md:43-44,149,161-175`,
  `web/src/features/group/GroupPlaceholder.tsx`. Nothing in `backend/`,
  `docker-compose.yml`, `.claude/settings.json` or the root `.gitignore` names
  `frontend/`. Tickets 018 and 021 mention `frontend/` in their text. That is the product
  owner's to update, not this delivery's.
- **Delivery order:** CI (ticket 018) is delivered after this ticket and lints `web/` only,
  so `.github/workflows/ci.yml` does not exist yet and has nothing to update here.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. The group trip in the new app, then the old app removed
**Files** (frontend only, no migration, no backend change; build in this order):

*API layer*
- `web/src/api/types.ts`: add the group and group-stays shapes, mirrored from
  `schemas/group.py` and `schemas/stay.py`:
  - `MemberInput` (name, grade_min, grade_max, max_distance_km, max_approach_minutes,
    styles) and `Member` (+ `id`), `Group` (name, share_code, members);
  - `MemberMisfit`, `GroupSectorMatch` (sector, distance_km, fit_count, member_count, fits,
    misfits), `MergedFilters`, and `GroupSearchResponse`, with `mode` / `fit` as the
    literal unions `SearchMode` / `FitMode` that the frontend sends;
  - `BookingLinks` and `GroupStaysResponse` (checkin / checkout as `"YYYY-MM-DD"` strings).
- `web/src/api/client.ts`:
  - `errorMessage()`: for a validation array, drop a leading "Value error, " from `msg`.
    Add a comment saying why: Pydantic adds the prefix to the validators' own messages.
  - `ApiError` gets an optional `field: string | null`: the last `loc` entry when it is a
    field name (not `"body"` or `"query"`). Example: `["body", "max_distance_km"]` gives
    `"max_distance_km"`, `["body"]` gives null.
  - Keep one parse of the body. `errorMessage()` can return `{message, field}` to
    `apiRequest()`, or a small helper can read both. Either way, existing callers
    (`SearchPage`, `StaysPanel`) keep working unchanged.

*Group helpers* (`web/src/features/group/`, plain `.ts` files: the `react-refresh` lint
rule wants component files to export only components)
- `groupLink.ts`: `groupCodeFromUrl()` (moved from `App.tsx`), `syncGroupCodeToUrl(code)`
  (`history.replaceState`, as `frontend/src/App.tsx:19-24` does), and
  `shareLinkFor(code)` (origin + pathname + `?group=CODE`). It is the one place that knows
  the link format, so old links and new links stay the same.
- `recentGroups.ts`: `readRecentGroups()`, `rememberGroup({code, name})` (most recent
  first, no duplicates, at most 5) and `forgetGroup(code)`. Key `cragmatch.recentGroups`.
  Every access is wrapped in try/catch and checks the shape it reads back: storage can be
  disabled, full, or edited by hand, and that must never break the page.
- `memberSummary.ts`: `describeMember(member)` returns four labels: grades ("6a to 7a" or
  "Any grade"), distance ("Up to 80 km" or "Any distance"), walk-in ("Up to 30 min walk-in"
  or "Any walk-in"), and styles (via `styleLabel()`, or "Any style") (AC 4). Also
  `MODE_HELP` and `FIT_HELP`, one plain sentence each (AC 5):
  - scored: "Every sector, best fit first, with who it doesn't suit and why."
  - strict: "Only sectors that suit everyone."
  - overlap: "A sector fits someone when some of its routes are in their grade range."
  - cover: "A sector fits someone only when its grades cover their whole range."

*Group screens* (`web/src/features/group/`, each with a CSS Module where it needs one;
colours only from tokens)
- `GroupPage.tsx`: replaces `GroupPlaceholder`.
  - Takes `initialCode` and holds the open group as one view union, as `SearchPage` does:
    `idle` (no code), `loading`, `open` (with the `Group`), `notFound` (with the code),
    `error` (with the message).
  - It loads `GET /groups/{code}` for `initialCode` in an effect, with the cancelled flag
    and state set only in the promise callbacks (the pattern of
    `frontend/src/GroupPage.tsx:52-67`, which the `react-hooks` rules accept). It also
    loads on join and on picking a recent group (event handlers).
  - When a group opens: `syncGroupCodeToUrl(share_code)` and `rememberGroup()`.
  - A 404 (`ApiError.status === 404`) gives `notFound`: a notice `StateMessage`, "Group
    not found", "No group has the code X. Check the link, or start a new group.", with a
    "Create a group" action back to the start screen. It also calls `forgetGroup(code)`
    (AC 2).
  - Other failures give an error `StateMessage` with "Try again".
  - "Leave group" (ghost button) goes back to the start screen and clears `?group=`.
  - After any member change it re-reads the group, so the list and the member count are
    the backend's (AC 3).
- `GroupStart.tsx`: two cards.
  - "Start a group trip": a name field (placeholder "Siurana weekend"). It POSTs to
    `/groups/` and opens the new group (AC 1).
  - "Join with a code": a code field.
  - Under them, "Your recent groups" as buttons with name and code, read once with
    `useState(readRecentGroups)`. The screen remounts each time a group is left, so the
    list is fresh.
- `ShareLink.tsx`:
  - Shows the link from `shareLinkFor()` in a read-only input, with a "Copy link" button
    next to it (AC 1).
  - The button calls `navigator.clipboard.writeText`. It shows "Copied" for 2 s (a
    timeout in the click handler, not an effect).
  - If the clipboard is missing or refuses, it says "Couldn't copy, select the link and
    copy it" and selects the input text.
- `MemberList.tsx`:
  - Each member is a row: the name, and the `describeMember()` labels as `Chip`s (grade
    tone for grades, style tone for styles), with "Edit" and "Remove" ghost buttons.
  - "Edit" swaps that row for `MemberForm` with the member's values. "Remove" asks with
    `window.confirm`, then sends `DELETE` (as the old app does: no new dialog pattern).
  - The section title shows the count, "Members (3)".
  - The add form sits under the list.
- `MemberForm.tsx`: the fields, laid out with `Field` and `Forms.module.css`'s `row` /
  `chips` classes (imported from `../search/Forms.module.css`, the same visual pattern):
  - Name.
  - Easiest and hardest grade: selects whose first option is "Any", then `GRADES` in
    backend order.
  - Max distance in km and max walk-in in minutes: number inputs with placeholder "Any".
    An empty input becomes `null`.
  - Styles: multi-select `ChipButton`s over `STYLES`, with the hint "None selected = any
    style".
  - The buttons: "Add member" (or "Save" and "Cancel" when editing). It clears itself
    after an add.
  - `noValidate` on the form, so the backend's rules are the only rules (ticket check).
  - On an `ApiError` with a `field`, the message goes to that `Field`'s `error`.
    Otherwise it goes in an error `StateMessage` under the buttons (AC 3).
- `GroupSearch.tsx`:
  - With 0 members it shows only an empty `StateMessage`: "Add members first. Search needs
    at least one person's preferences." No controls and no request (AC 7).
  - Otherwise it shows two `SegmentedControl`s: "Who should it suit?" (Scored, Strict;
    default Scored) and "Grades fit when" (Overlap, Cover; default Overlap). Under each,
    its `MODE_HELP` / `FIT_HELP` sentence (AC 5).
  - A "Find sectors" button. Changing the mode or fit while results are showing runs the
    search again at once.
  - The result is stored together with the `Group` object it was computed for, and shown
    only while that is still the current group. A member change reloads the group (a new
    object), so old results disappear without any clearing code.
  - Results are drawn from the response:
    - scored, `common_ground` false: a one-line notice "No sector fits everyone. Best
      compromises first." above the list.
    - strict, `filters` set: `GroupFilters` above the list (AC 6).
    - strict, `common_ground` false: a notice `StateMessage` "No common ground" with
      `message` as its text and a "Try scored mode" action, which switches to scored and
      searches (AC 6).
    - strict, common ground but no results: an empty `StateMessage` with `message` and
      the same action (ticket check).
    - a list of `SectorCard`s in the same grid as search, each with `distanceKm` and a
      `FitSummary` child.
  - "Stays nearby" opens `StaysPanel` with `groupCode`.
- `FitSummary.tsx`:
  - A "3 of 4" chip, in the highlight tone when everyone fits.
  - "Fits: Ana, Ben" in the success token.
  - One line per misfit, "Carla: too far (112 km > 80 km)", in the danger token. The
    reason is shown exactly as the backend wrote it (AC 5).
- `GroupFilters.tsx`: an "Everyone agrees on" strip. The chips are the grade range,
  "Within N km" or "Any distance", "Max N min walk-in" or "Any walk-in", and the styles or
  "Any style". It reuses `../search/UnderstoodFilters.module.css`, the same strip pattern
  as 016's "Here's what I understood" (AC 6).
- Delete `GroupPlaceholder.tsx` and `GroupPlaceholder.module.css`.

*Shared pieces that gain group options*
- `web/src/features/search/SectorCard.tsx`: an optional `distanceKm?: number`, shown as
  "112 km from Barcelona" next to the walk-in, and an optional `children` rendered above
  the "Stays nearby" button. The search page passes neither, so it doesn't change.
- `web/src/features/stays/StaysPanel.tsx`: an optional `groupCode?: string`.
  - With it, the URL is `/groups/{code}/sectors/{id}/stays`, with `nights`, plus
    `checkin` and `guests` only when the user set them. Empty fields fall back to the
    backend's defaults.
  - The effect stores `{stays, trip}` the same way in both modes. Loading is still
    derived from `loadedUrl !== url`.
  - Extra controls in group mode:
    - Check-in: a date input showing `checkin || trip?.checkin`.
    - Nights: 1-30, default 2.
    - Guests: 1-30, showing `guests ?? trip?.guests`, so the group size comes from the
      backend.
  - Then a line "4 guests, Sat 17 Oct to Mon 19 Oct" and two secondary-styled external
    links, "Search on Airbnb" and "Search on Booking.com", with the `external` icon and
    `rel="noopener noreferrer"` (AC 8).
  - The date input has no `min`: the backend's past-date rule is the only one. Its 422
    message ("checkin can't be in the past") shows in the error state, and the controls
    stay usable (AC 8).
  - Update the "group booking options come with the group screen" comment.
- `web/src/app/App.tsx`: import `groupCodeFromUrl` from `features/group/groupLink.ts` and
  render `<GroupPage initialCode={groupCode} />` instead of the placeholder. The rule
  "`?group=` on load opens Group trip" is unchanged (AC 2).

*Retire the old app (last step)*
- Delete `frontend/`. Run `git rm -r frontend`, then remove the folder itself (its
  untracked `node_modules/` and `dist/` stay behind otherwise). Stop the old dev server
  first if it runs, by its exact PID (CLAUDE.md trap).
- `.claude/hooks/lint_after_edit.py`: replace `FRONTEND_APPS` and its loop with one
  `WEB = ROOT / "web"` and a check that the file is under `WEB / "src"`. Drop the "Ticket
  017 removes frontend/" comment.
- `.claude/agents/developer.md:21-22` and `.claude/agents/tech-lead.md:40-41`: "run
  `npm run lint` (and `npm run build`) in `web/`".
- `CLAUDE.md`:
  - Stack: "Frontend: React 19 + TypeScript + Vite in `web/`."
  - Commands: drop "(stop the old `frontend/` dev server first)".
  - Reuse (frontend line): add "share links and `?group=` in
    `features/group/groupLink.ts`".
- `README.md`:
  - "Running locally" step 3: drop the sentence about the old app.
  - Project structure: the `web/src/` heading says "(design system, search, groups,
    stays)". `features/group/` becomes "Group trip: create, join or reopen a group, share
    link, members, scored and strict group search". `features/stays/` gains "in a group,
    dates, guests and Airbnb / Booking.com links".
  - Delete the whole `frontend/src/` block (Definition of done 3).

**Reuses:**
- From the new app: `apiRequest()`, `ApiError` and `errorMessage()` (`web/src/api/client.ts`),
  and the UI kit: `Button`, `Field`, `Chip` / `ChipButton`, `Card`, `SegmentedControl`,
  `StateMessage`, `Sheet`, `Icon`.
- `GRADES`, `STYLES` and `styleLabel()` (`web/src/constants.ts`).
- `SectorCard`, `StaysPanel`, `Forms.module.css`, `UnderstoodFilters.module.css`, and the
  "view union" and derived-loading patterns of `SearchPage` / `StaysPanel`.
- From the old app (as logic only, nothing imported): `?group=` reading and writing,
  `describePrefs()` and the effect pattern for the first load.
- On the backend, unchanged: `POST /groups/`, `GET /groups/{code}`, the member
  POST/PUT/DELETE, `GET /groups/{code}/search`, `GET /groups/{code}/sectors/{id}/stays`,
  and their messages.

**Tests:**
- No frontend test runner (016's decision, kept). `npm run lint` and `npm run build` in
  `web/` must pass (AC 10).
- Backend: no file changes. The behaviour this screen relies on is already covered:
  - `tests/test_groups_api.py`: `test_create_group_returns_share_code`,
    `test_get_group_is_case_insensitive`, `test_unknown_group_is_404`,
    `test_member_can_join_without_preferences`, `test_invalid_preferences_are_422`,
    `test_update_member_replaces_everything`, `test_delete_member`,
    `test_search_with_no_members_explains_why`, `test_strict_no_common_ground`,
    `test_checkpoint_three_friends_scored`, `test_fit_cover_is_stricter_than_overlap`.
  - `tests/test_stays.py`: `test_group_stays_defaults_guests_and_dates`,
    `test_group_stays_links_carry_dates_and_guests`,
    `test_group_stays_rejects_past_checkin_and_unknowns`.

**Expected suite:** backend unchanged, **199 passed** (199 collected on 2026-10-14).
`web/`: no tests; lint 0 problems, build succeeds. `frontend/` no longer exists.

**Check by hand** (by the user, backend running, `npm run dev` in `web/`). Use the
devtools device bar at 375 px and switch light/dark with "emulate prefers-color-scheme":
1. Group trip, "Start a group trip" with "Siurana weekend": the group opens, the address
   bar shows `?group=CODE`, and the share link is shown. "Copy link" says Copied, and the
   pasted text is the link (AC 1).
2. Open that link in a new tab: it lands on Group trip with the group open. The same with
   the code in lower case. `?group=ZZZZZZZZ` shows "Group not found" with "Create a
   group". Reload the start screen: the group is under "Your recent groups" (AC 2).
3. Add Ana (6a to 7a, 80 km, sport). Edit her to 30 min walk-in. Add Ben, remove Ben. The
   list and the count follow each time. Set only an easiest grade: the half-range
   message shows under the form, with no "Value error," prefix. Max distance 0: "Input
   should be greater than 0" shows under the distance field (AC 3).
4. Add Carla with only a name: her row reads Any grade, Any distance, Any walk-in, Any
   style (AC 4).
5. Scored, Overlap, "Find sectors": every card shows "N of 3", the names it fits, and
   each misfit with a reason. Switch to Cover: the sentence changes and the results
   reload (AC 5).
6. Strict on a group that agrees: "Everyone agrees on" shows above the results. Give Ana
   7c to 8a and Carla 5 to 5+: "No common ground" shows the conflict text and "Try scored
   mode", which switches and shows results (AC 6).
7. A new group with no members: Group trip asks to add members first. There is no search
   button and no error (AC 7).
8. "Stays nearby" on a group result: next Saturday, 2 nights and the group size are
   filled in. Change the dates and guests: the Airbnb and Booking.com links open with
   them. Pick yesterday: "checkin can't be in the past" shows, and picking a future date
   recovers (AC 8).
9. `frontend/` is gone. `git grep -n "frontend/"` outside `tickets/` finds nothing. Edit a
   `.tsx` file in `web/src`: the lint hook still runs (AC 9).
10. Screens 1-8 at 375 px: no horizontal scroll, the stays sheet is a bottom sheet, and
    the member form stacks. Then the same in dark mode. `npm run lint` and
    `npm run build` in `web/` pass (AC 10).

**Commit:** `Ticket 017: group trip in the new app (create, join and recent groups, share link with copy, members with backend messages per field, scored and strict group search with fit counts, misfit reasons and merged filters, group stays with dates, guests and booking links); old frontend removed, hook, agents, CLAUDE.md and README point only at web/`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Manual check 1; backend `test_create_group_returns_share_code` |
| 2 | Manual check 2; backend `test_get_group_is_case_insensitive`, `test_unknown_group_is_404` |
| 3 | Manual check 3; backend `test_invalid_preferences_are_422`, `test_update_member_replaces_everything`, `test_delete_member` |
| 4 | Manual check 4; backend `test_member_can_join_without_preferences` |
| 5 | Manual check 5; backend `test_checkpoint_three_friends_scored`, `test_fit_cover_is_stricter_than_overlap` |
| 6 | Manual check 6; backend `test_strict_no_common_ground` |
| 7 | Manual check 7; backend `test_search_with_no_members_explains_why` |
| 8 | Manual check 8; backend `test_group_stays_defaults_guests_and_dates`, `test_group_stays_links_carry_dates_and_guests`, `test_group_stays_rejects_past_checkin_and_unknowns` |
| 9 | Manual check 9; review: `git grep "frontend/"` outside `tickets/` is empty |
| 10 | `npm run lint`, `npm run build` in `web/`; manual check 10 |

Every frontend behaviour depends on a manual check, because `web/` has no test runner. The
backend tests only prove the data the screens rely on. The reviewer should also grep
`web/src` for hex colours outside `tokens.css` and for inline `style=` attributes.

## Risks
- **No automated frontend tests:** CLAUDE.md asks for unit tests on pure functions, and
  `describeMember()`, `recentGroups.ts` and the `loc` to field mapping are pure. They stay
  untested, as in 016. If that matters, a small follow-up ticket can add Vitest and test
  these first.
- **`errorMessage()` / `ApiError` change:** `SearchPage` and the single-sector
  `StaysPanel` use them. The change is additive (a stripped prefix, an optional field).
  Manual check 3 covers it, and the 016 search checks (400 for a bad grade, 429, offline)
  should still give the same messages.
- **Single-sector `StaysPanel` must stay as it is:** group mode is opt-in through
  `groupCode`. Re-check "Stays nearby" from Find crags (radius, type, empty state).
- **Deleting `frontend/` on OneDrive:** `node_modules` can be locked by a running Vite
  server or an editor's ESLint server, which gives "Access is denied". Stop the old dev
  server by its exact, verified PID, and close editors on `frontend/`. Never kill by
  command-line match.
- **Editing `.claude/` files:** the developer agent may get a permission prompt for
  `.claude/hooks/` and `.claude/agents/`. That is expected, and the user approves it. A
  mistake in `lint_after_edit.py` silently stops linting (manual check 9).
- **Clipboard:** `navigator.clipboard` only works in a secure context. `localhost` is one,
  but a plain-HTTP LAN address on a phone is not. The fallback (select the link) covers
  that case.
- **`localStorage`:** it can be unavailable (private mode) or hold bad data. Every read
  and write is guarded, and a bad entry is ignored.
- **External services:** none. Group search, stays and booking links make no Claude,
  Voyage or Overpass calls, and the booking links only open the sites' own search.
- **Migration / existing data:** none. No model or schema change. Groups and members in
  the dev DB keep working, and old `?group=` links have the same format and port.

## Out of scope (copied from the ticket)
- The trip planner screen: ticket 019 (it adds a "Plan the trip" entry to this group page),
  and its live graph diagram: ticket 020.
- Login or member accounts: the share code stays the only access.
- Several origins per member: all members leave from Barcelona, as in the backend.
