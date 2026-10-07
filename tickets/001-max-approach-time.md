# 001: Members set a maximum walk-in time, group search respects it

**Status:** Needs answers
**Size:** L
**Raw request:** "Members should be able to say how long they're willing to walk to the crag, and the group search should respect that."

## User story
As a group member, I want to say how long I'm willing to walk from the car to the
sector, so that the group search doesn't suggest a sector with an approach I won't do
(tired legs, kids, heavy trad rack, bad knee).

## What exists today
- `Member` (`backend/app/models/member.py`) has grade range, `max_distance_km` and
  `styles`. It has no approach or walking preference.
- `MemberBase` / `MemberCreate` / `MemberRead` (`backend/app/schemas/group.py`) mirror
  these fields. The frontend mirrors them in `frontend/src/types.ts`, `MemberForm.tsx`
  and the member summary in `GroupPage.tsx`.
- Group search (`backend/app/services/group_search.py`) has two modes:
  - strict: `merge_preferences()` intersects preferences into `MergedFilters`
    (the shortest distance limit wins).
  - scored: `score_sectors()` / `why_not()` list every sector with a fit count
    and a reason for each misfit, e.g. "too far (112 km > 80 km)".
  Both live in `backend/app/services/group_matching.py`.
- **Missing: sectors have no structured approach time.** `Sector.approach_notes`
  (`backend/app/models/sector.py`) is free text, at most 500 characters. It is
  only filled by `backend/app/scripts/embed_sectors.py` (not by `seed.py`):
  - some notes give minutes ("15-minute walk", "30-minute approach");
  - some are vague ("short approach", "long approach", "almost no approach");
  - some seeded sectors have no approach note at all.
  Today nothing can be compared with a member's limit. This is the main open question.

## Acceptance criteria
1. Given a group, when a member is added or updated with a maximum approach of 20
   minutes, then reading the group returns that member with that limit.
2. Given a member form, when the maximum approach is 0, negative or not a number,
   then the request is rejected with a validation error and nothing is saved.
3. Given a member who sets no maximum approach, when the group searches, then that
   member's results are not limited by approach time (same as an unset distance).
4. Given members existing before this change, when the group is read, then they have
   no approach limit, and their search results are unchanged.
5. Given a strict search where Ana's limit is 15 minutes and Ben's is 30, when the
   group searches, then the merged filters show a 15-minute limit, and no result has
   an approach longer than 15 minutes.
6. Given a scored search and a sector with a 30-minute approach, when a member with a
   15-minute limit is scored, then the sector is still listed and that member is a
   misfit with a reason like "approach too long (30 min > 15 min)".
7. Given a sector whose approach time is unknown, when any member has a limit, then
   that sector is handled as decided in the open question below (suggested: it fits,
   and isn't excluded).
8. Given a strict search where every sector's approach is over the group's limit,
   when the group searches, then the response says the group agrees on filters but no
   sector matches. It returns no results and no error.
9. Given a group with no members, when it searches, then the response is unchanged:
   "Add at least one member to search."
10. Given no member has set an approach limit, when the group searches in either mode,
    then results and order are the same as before this change.

## Scope
**In:**
- An optional "maximum approach time" preference per member: stored, validated,
  returned, editable in the member form and shown in the member summary.
- A known approach time for every seeded sector that has usable information.
- Group search, strict and scored, uses the limit as it uses `max_distance_km`.

**Out:**
- Solo search (`/search`, Stage 1) filter on approach time: the request is about
  groups. It can be a follow-up ticket.
- Approach difficulty (steepness, scrambling, fixed ropes), e.g. Paretot's "short but
  steep": it's a separate preference and has no data.
- Reading approach times out of `approach_notes` with Claude: guessing data with an
  LLM needs its own reliability discussion. Entering it by hand covers the current
  dataset.
- Natural-language search ("short approach") and the RAG/agent tools: they already
  read the free text and can be aligned later.
- Driving time instead of straight-line distance: unrelated to walking.

## Open questions
- [blocking] Where do sector approach times come from? (suggested default: a
  structured approach time in minutes per sector, entered by hand for the seeded
  sectors from the existing notes. Vague notes are mapped as "almost no approach" =
  2, "short" = 10, "long" = 45. Sectors with no note stay unknown.)
- [blocking] How is a sector with an unknown approach time treated when a member has a
  limit? (suggested default: it fits and is never excluded, so missing data doesn't
  hide sectors. The UI shows "approach unknown".)
- [non-blocking] Unit and meaning: minutes, one way, car park to the foot of the
  sector? (suggested default: yes, whole minutes, one way)
- [non-blocking] Is there an upper bound on the member's limit? (suggested default:
  1–180 minutes. Anything longer is effectively "no limit".)
- [non-blocking] Should sector results show the approach time? (suggested default:
  yes, on the sector card, so members see why a sector was dropped or flagged)

## Notes for the tech lead
- Two migrations are likely: one per new piece of data, on members and on sectors.
  Each must be imported or registered as CLAUDE.md says, and the autogenerated
  migrations must be reviewed, since `alembic/env.py` filters PostGIS tables.
- `group_matching.py` must stay pure. The `Preferences` protocol and the test
  stand-ins will need the new attribute.
- Follow the `max_distance_km` pattern throughout: unset = no restriction, the strict
  limit is the minimum, and the scored misfit reason has the same wording style.
- Schema and `frontend/src/types.ts` change together. `npm run lint` must pass.
- Tests: unit tests for merge and why_not, covering a limit set, a limit unset and an
  unknown sector approach. TestClient tests for member create/update validation and
  both search modes.
- Re-running `embed_sectors.py` isn't needed unless the notes text changes. If it is
  re-run, mind the Voyage 3 requests/minute limit.
- Suggested split (L → three tickets):
  1. Sector approach time: data and migration, filled for seeded sectors, returned
     in `SectorRead`. Backend only, migration.
  2. Member preference and group search: member field, migration, validation, strict
     and scored matching, tests. Backend only, migration.
  3. Frontend: member form field, member summary, approach time on sector cards and
     in the merged-filters line.
