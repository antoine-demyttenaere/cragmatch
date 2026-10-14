# 017: New frontend, part 2: group trip, then retire the old frontend

**Status:** Ready
**Size:** M (frontend only, no migration)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Prepare tickets for creating the frontend with associating what we've done in the backend and a new frontend. I want to include the AI part with the graphs. Create a nice design. Do the plan."
**Part of:** the new frontend (015 → 016 → 017 → 019 → 020). Needs 016. Tickets 019 and 020 were 018 before the Stage 7 renumbering of 2026-10-14; the CI ticket 018 comes after this one and lints `web/` only.

## User story
As a group of friends, I want to create a group, share its link, add everyone's
preferences and see which sectors suit all of us and where to stay, in the new app, so that
we plan the trip together from our phones.

## What exists today
(Checked against the code on 2026-10-13.)
- Old frontend: `frontend/src/GroupPage.tsx` (create or join, members, strict and scored
  search), `MemberForm.tsx` (grade range, max distance, max walk-in, styles), `StaysPanel.tsx`
  (group stays with dates, guests and booking links), `App.tsx` (keeps `?group=CODE` in the
  URL so the link can be shared).
- Backend, `backend/app/routers/groups.py`:
  - `POST /groups`, `GET /groups/{code}`, `POST /groups/{code}/members`,
    `PUT /groups/{code}/members/{id}`, `DELETE /groups/{code}/members/{id}`.
  - `GET /groups/{code}/search?mode=strict|scored&fit=overlap|cover` returns
    `GroupSearchResponse` (`schemas/group.py`): `common_ground`, `message`, merged `filters`
    (strict), and per sector `fit_count` / `member_count`, `fits`, and `misfits` with reasons.
  - `GET /groups/{code}/sectors/{id}/stays?checkin&nights&guests&type&max_distance_km`
    returns stays and Airbnb / Booking.com links (guests defaults to the number of
    members, checkin to next Saturday, 422 for a past checkin).
- Member rules from `MemberBase`: set both grades or neither (a half range is rejected).
  Every preference is optional: empty means "any".
- After ticket 016: the new app, its design system and the shell, with "Group trip" as a
  placeholder.

## Acceptance criteria
1. Given the Group trip section, when a name is entered, then a group is created and its
   share link is shown, with a one-tap copy.
2. Given a share link `?group=CODE`, when it is opened, then the group opens directly, in
   the new app too, so old links keep working. Given an unknown code, then a clear "group
   not found" message offers to create one.
3. Given a group, when a member is added, edited or removed, then the member list updates.
   Given a half grade range or an invalid value, then the backend's message is shown next
   to the form.
4. Given a member who sets no preferences at all, then they are shown as "any grade, any
   distance, any style", not as blanks.
5. Given scored search, then each sector shows how many members it fits ("3 of 4"), who it
   fits, and for each misfit the reason ("too easy", "too far"). The fit choice, overlap or
   cover, is explained in one plain sentence.
6. Given strict search on a group with common ground, then the merged filters are shown
   above the results. Given a group with no common ground, then the conflicts message is
   shown as a normal result, with a hint to try scored mode.
7. Given an empty group (no members), when search is opened, then the app asks to add
   members first, instead of showing an error.
8. Given a sector in the group results, when its stays are opened, then the check-in date,
   nights and guests can be chosen (defaults: next Saturday, 2 nights, group size). Nearby
   stays and the Airbnb / Booking.com links for those dates show. A past date shows the
   backend's message.
9. Given the new app covers every screen of the old one, then `frontend/` is removed, and
   README, CLAUDE.md, the lint hook and the agents point only at the new app.
10. Given the new app, then `npm run lint` and `npm run build` pass, and the screens meet
    016's design criteria (both themes, phone width).

## Scope
**In:** groups, members, strict and scored group search, group stays and booking links,
share links, and removing the old frontend.

**Out:**
- The trip planner screen: ticket 019 (it adds a "Plan the trip" entry to this group page),
  and its live graph diagram: ticket 020.
- Login or member accounts: the share code stays the only access.
- Several origins per member: all members leave from Barcelona, as in the backend.

## Open questions
- [non-blocking] Default search mode on the group page? (suggested default: scored, as the
  backend's default, because it always shows something useful.)
- [non-blocking] Keep a list of groups this browser has opened, for quick access?
  (suggested default: yes, the last few in `localStorage`, codes only. It is a convenience,
  not data.)

## Notes for the tech lead
- Reuse the design system and API helpers from 016. No new visual patterns without a reason.
- The member form uses the grades and styles from the shared constants, in backend order.
- Removing `frontend/` is the last step of this delivery. Check the README structure, the
  "Running locally" steps and every path in `.claude/` (hooks and agents) for leftovers.
- No backend change is expected. If one turns out to be needed, say so in the plan, since
  it changes the size.
