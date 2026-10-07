# Plan for 001: Members set a maximum walk-in time, group search respects it

**Ticket:** `tickets/001-max-approach-time.md`
**Approach:** Two new nullable integer columns: `Sector.approach_minutes` holds the data, filled
from the existing notes by the migration and by `seed.py`. `Member.max_approach_minutes` holds
the preference, limited to 1–180. The matching rule goes into the pure `why_not()` and
`merge_preferences()` and copies the `max_distance_km` pattern. Strict mode needs no new
filter: it already re-scores its candidates and keeps only sectors that fit every member.
**Alternatives considered:**
- Add an approach parameter to `find_matching_sectors()` (SQL-side filter): it is the solo-search
  service, which is out of scope. Strict mode's scoring step already enforces every member's
  rules, so a second filter would just duplicate `why_not()`.
- Parse `approach_notes` at query time: the notes are vague ("short", "long"). The ticket decided
  on a structured, hand-entered value.
- Put the values only in `seed.py` and re-seed: `seed.py` isn't idempotent (re-running it
  duplicates crags), and existing dev databases would get nothing. The migration backfills
  existing rows, and `seed.py` covers fresh databases.

## Ticket check
- **Wrong:** "some seeded sectors have no approach note at all". In
  `backend/app/scripts/embed_sectors.py`, `NOTES` has a note for all 13 seeded sectors. Only
  El Pati's note has no approach information. Poble ("5 minutes from the car") and Aombra
  ("10 minutes from the car") also give minutes. Mapping that follows the ticket's
  decisions:

  | Sector | Crag | Minutes | From the note |
  |---|---|---|---|
  | Can Marges | Siurana | 5 | "5-minute approach" |
  | Siuranella | Siurana | 15 | "15-minute walk" |
  | El Pati | Siurana | unknown (NULL) | no approach info |
  | Camp de Tir | Margalef | 2 | "almost no approach" |
  | Regall | Margalef | 20 | "20-minute walk" |
  | Poble | Margalef | 5 | "5 minutes from the car" |
  | Agulles | Montserrat | 45 | "long approach" |
  | Collbató | Montserrat | 10 | "short approach" |
  | Roca Regina | Terradets | 10 | "10-minute approach" |
  | Paretot | Terradets | 10 | "short but steep" |
  | Aombra | Terradets | 10 | "10 minutes from the car" |
  | Congost | Vilanova de Meià | 30 | "30-minute approach" |
  | Serrat | Vilanova de Meià | 10 | "10-minute approach" |

- **Wrong:** "Sector cards show the approach time" covers two places. Group search results
  are not drawn with `SectorCard.tsx`: they are inline JSX in `GroupPage.tsx`, in the results
  `<ol>`. `SectorCard` is only used by the solo and "describe the vibe" searches.
  Both need the change.
- **More precise:** strict mode in `services/group_search.py` calls `find_matching_sectors()`
  for grades and distance, then filters styles itself. After that, `score_sectors()` keeps only
  `fit_count == len(members)`. Once `why_not()` knows about approach time, strict mode
  excludes long approaches with no extra code. `MergedFilters` still needs the field so that
  AC 5 can show the 15-minute limit.
- No new model, only new columns, so `app/models/__init__.py` doesn't change.
  `alembic/env.py` already keeps only our own tables, so autogenerate should produce one
  `add_column` per migration.
- Tests build the schema with `Base.metadata.create_all` (`tests/conftest.py`), not with
  Alembic. Migrations are therefore only checked by hand.
- `tests/test_groups_api.py:184` asserts the whole `filters` dict. It will fail once
  `MergedFilters` gets a new key, so it must be updated in increment 3.
- Confirmed: `Sector(**sector.model_dump())` in `routers/sectors.py::create_sector` means a new
  `SectorBase` field is accepted by `POST /sectors/` without router changes. The API tests can
  then create sectors with an approach time.
- Confirmed: nothing in `app/rag/` or `services/explain.py` calls the group-matching functions,
  so no other caller changes.

## Increments

### 1. Sector approach time: column, data, API field (migration)
**Files:**
- `backend/app/models/sector.py`: add `approach_minutes: Mapped[int | None]`, next to
  `approach_notes`, with a short comment: one way, car park to the foot of the sector,
  NULL = unknown.
- `backend/alembic/versions/<rev>_add_approach_minutes_to_sectors.py`: autogenerate it, then
  review it. It must contain one nullable `add_column` on `sectors` and nothing else. Then add,
  by hand, an `UPDATE` per sector from the table above, matched on sector name and crag name
  (via `crag_id`). This backfills existing databases.
  - `downgrade()` only drops the column.
  - Write the values literally. Don't import app code into the migration.
- `backend/app/scripts/seed.py`: add `"approach_minutes": N` to each sector dict, with the same
  values, so a fresh database gets them. Leave it out for El Pati.
- `backend/app/schemas/sector.py`: in `SectorBase`, add `approach_minutes: int | None`,
  `default=None`, `ge=0`, `le=600`, with a description that gives the unit and says
  None = unknown. `SectorRead` and `SectorCreate` inherit it.
- `README.md`: on the `sector.py` lines in the structure (models and schemas), mention
  `approach_minutes`.

**Reuses:** the `approach_notes` column and migration (`178caab75ad8`) as the pattern. The
`create_sector` router needs no change.

**Tests:**
- `tests/test_sectors_api.py::test_create_sector_with_approach_minutes`: POST with 20, the
  response and a GET both return `approach_minutes == 20`. (supports AC 5, 6)
- `tests/test_sectors_api.py::test_approach_minutes_defaults_to_unknown`: POST without the field
  returns `approach_minutes is None`. (supports AC 7)
- `tests/test_sectors_api.py::test_negative_approach_minutes_is_422`: -1 returns 422.

**Check by hand:**
- Run `uv run alembic upgrade head`, then `GET /sectors/`: Regall shows 20, El Pati null.
- Then `uv run alembic downgrade -1` and `upgrade head` again: the column comes back, with the
  values.

**Commit:** `Add Sector.approach_minutes (migration backfills seeded sectors from their approach notes) so group search can compare walk-in times`

### 2. Member preference: column, validation, round-trip (migration)
**Files:**
- `backend/app/models/member.py`: add `max_approach_minutes: Mapped[int | None]` under
  `max_distance_km`. The existing "all optional" comment already covers it.
- `backend/alembic/versions/<rev>_add_max_approach_minutes_to_members.py`: autogenerate, then
  review. It contains one nullable `add_column` on `members`, with no server default, so
  existing members get NULL = no limit (AC 4).
- `backend/app/schemas/group.py`: in `MemberBase`, add `max_approach_minutes: int | None`,
  `default=None`, `ge=1`, `le=180`. `MemberCreate` and `MemberRead` inherit it.
- `README.md`: on the `member.py` line, mention the new preference.

**Reuses:** the `max_distance_km` field as the pattern, in the model and in `Field(gt=0)`.
`get_group` / `get_member` and the add/update routes don't change.

**Tests:**
- `tests/test_groups_api.py::test_member_max_approach_round_trips`: add a member with 20, then
  `GET /groups/{code}` shows 20. PUT with 35, and GET shows 35. (AC 1)
- `tests/test_groups_api.py::test_invalid_max_approach_is_422`, parametrized over 0, -5, 181 and
  "abc": each returns 422, and the group still has no members. (AC 2)
- `tests/test_groups_api.py::test_member_can_join_without_preferences`: extend it to assert
  `max_approach_minutes is None`. (AC 3, 4)

**Check by hand:**
- Run `uv run alembic upgrade head` on the dev database. Open a group created before this
  change: every member shows `max_approach_minutes: null`. (AC 4)
- In `/docs`, add a member with 20.

**Commit:** `Add Member.max_approach_minutes (1–180, optional) so members can say how long they'll walk`

### 3. Group matching respects the limit (backend logic, no migration)
**Files:**
- `backend/app/services/group_matching.py`:
  - `Preferences` protocol: add `max_approach_minutes: int | None`.
  - `SearchFilters`: add `max_approach_minutes: int | None`, with the comment "None = no limit".
  - `merge_preferences()`: the strictest limit is the `min` of the limits that are set, written
    like the distance block. It never creates a conflict.
  - `why_not()`: add a check when all three hold:
    - the member has a limit;
    - `sector.approach_minutes is not None`;
    - the approach is longer than the limit.

    The reason reads `approach too long (30 min > 15 min)`, in the same style as "too far". An
    unknown approach adds no reason, and a comment says why: missing data must not hide a
    sector (ticket decision).
  - Update the module docstring's example reasons.
- `backend/app/schemas/group.py`: in `MergedFilters`, add `max_approach_minutes: int | None`,
  described as "None = no approach limit."
- `backend/app/services/group_search.py`: pass `f.max_approach_minutes` into `MergedFilters`.
  - Add a one-line comment at the scoring step: the approach limit is enforced there, through
    `why_not()`.
  - Nothing else changes: the existing "agrees on filters, but no sector matches" message
    covers AC 8.
- `backend/tests/test_group_matching.py`:
  - stand-ins: `P` gets `max_approach_minutes: int | None = None`;
  - `sector()` gets an `approach=None` argument, stored as `approach_minutes`.
- `backend/tests/test_groups_api.py`:
  - `_add_sector()` gets an optional `approach` argument that it passes through;
  - update the exact `filters` assertion at line 184 with `"max_approach_minutes": None`.

**Reuses:** `merge_preferences()`, `why_not()` and `score_sectors()` (extended, not
duplicated). The `max_distance_km` pattern for the strict minimum and the misfit wording. The
strict re-scoring step in `search_for_group()` acts as the filter.

**Tests:**
- `tests/test_group_matching.py::test_merge_approach_is_the_smallest_limit`: Ana has 15, Ben 30
  and Lia none, so the filter is 15. (AC 5)
- `tests/test_group_matching.py::test_merge_without_approach_limits_means_no_restriction`:
  filter is None and common ground is True. (AC 3, 10)
- `tests/test_group_matching.py::test_score_approach_too_long_is_a_misfit`: a 30-min sector and
  a member with a 15-min limit give the misfit reason
  `"approach too long (30 min > 15 min)"`. (AC 6)
- `tests/test_group_matching.py::test_score_approach_equal_to_limit_fits`: 15 min against a
  15-min limit fits. This is a boundary test.
- `tests/test_group_matching.py::test_score_unknown_approach_fits_everyone`: `approach=None`
  with a 5-min limit fits. (AC 7)
- `tests/test_group_matching.py::test_score_member_without_approach_limit_fits_long_approach`:
  a 45-min sector and no limit fits. (AC 3)
- `tests/test_groups_api.py::test_strict_respects_shortest_approach_limit`:
  - sectors of 10, 30 and unknown minutes; Ana's limit is 15 and Ben's is 30;
  - the results are the 10-min and the unknown sectors;
  - `filters.max_approach_minutes == 15`. (AC 5, 7)
- `tests/test_groups_api.py::test_scored_explains_approach_too_long`: the 30-min sector is still
  listed with `fit_count` 1 of 2, and Ana's reason starts with "approach too long". (AC 6)
- `tests/test_groups_api.py::test_strict_every_sector_has_too_long_an_approach`:
  - every sector is over the limit;
  - `common_ground` is True and `results` is empty;
  - the message is "The group agrees on filters, but no sector matches them.";
  - the status is 200. (AC 8)
- Existing tests that must pass unchanged:
  - `tests/test_groups_api.py::test_search_with_no_members_explains_why` (AC 9);
  - `test_checkpoint_three_friends_scored`, `test_strict_returns_only_sectors_for_everyone`
    (apart from the new key) and every `test_score_*` / `test_merge_*` test (AC 10).

**Check by hand:**
- In `/docs`, give a seeded group's members limits of 15 and 30 and run
  `GET /groups/{code}/search?mode=strict`:
  - no result has `approach_minutes` over 15, but El Pati can appear;
  - `filters.max_approach_minutes` is 15.
- Then run `mode=scored`: Congost lists the 15-min member as "approach too long (30 min > 15 min)".

**Commit:** `Group search respects members' max approach time (strict: shortest limit; scored: "approach too long" misfit); unknown approach never excludes a sector`

### 4. Frontend: member form, member summary, approach time on results
**Files:**
- `frontend/src/types.ts`, kept in step with the backend schemas:
  - `Sector`: add `approach_minutes: number | null`;
  - `MemberInput`: add `max_approach_minutes: number | null`;
  - `GroupSearchResponse.filters`: add `max_approach_minutes: number | null`.
- `frontend/src/MemberForm.tsx`:
  - a "Max walk-in (min)" number input with `min={1}`, `max={180}` and placeholder "any",
    using the same state and submit pattern as `maxDistance` (`""` becomes `null`);
  - reset it after an add.
  - Backend errors are already shown through the existing `error` state.
- `frontend/src/GroupPage.tsx`:
  - `describePrefs()`: add `≤20 min walk` / `any walk-in`;
  - "Everyone agrees on" line: add `, ≤15 min walk` when set;
  - each result line: add `N min walk-in`, or "approach unknown" when null.
- `frontend/src/SectorCard.tsx`: add the same walk-in text, so solo and "describe the vibe"
  results show it too.

**Reuses:** `apiRequest()` / `errorMessage()` in `api.ts` (no new calls). The existing
`maxDistance` input pattern. Values are derived at render time, not stored in state, per the
react-hooks rules.

**Tests:** no frontend test suite exists. `npm run lint` must pass.

**Check by hand:** run `npm run dev`, then:
- add a member with a 15-min limit, and check the summary reads "≤15 min walk";
- edit the member: the field is prefilled;
- enter 0: the backend's 422 message is shown (AC 2, in the UI);
- run a strict search: the filters line shows the limit, and El Pati shows "approach unknown";
- run a scored search: the misfit reason shows;
- run a solo search: the cards show walk-in times.

**Commit:** `Frontend: max walk-in field on members, walk-in time on sector results and in the group's agreed filters`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Increment 2, `tests/test_groups_api.py::test_member_max_approach_round_trips`; manual check in increment 4 (form round-trip) |
| 2 | Increment 2, `tests/test_groups_api.py::test_invalid_max_approach_is_422`; manual check in increment 4 (error shown in form) |
| 3 | Increment 3, `test_group_matching.py::test_merge_without_approach_limits_means_no_restriction`, `::test_score_member_without_approach_limit_fits_long_approach` |
| 4 | Increment 2, the nullable column without a default; extended `test_member_can_join_without_preferences`; manual check after `alembic upgrade head` on the dev database |
| 5 | Increment 3, `test_group_matching.py::test_merge_approach_is_the_smallest_limit`, `test_groups_api.py::test_strict_respects_shortest_approach_limit` |
| 6 | Increment 3, `test_group_matching.py::test_score_approach_too_long_is_a_misfit`, `test_groups_api.py::test_scored_explains_approach_too_long` |
| 7 | Increment 3, `test_group_matching.py::test_score_unknown_approach_fits_everyone`, `test_groups_api.py::test_strict_respects_shortest_approach_limit` (unknown sector kept); manual check in increment 4 ("approach unknown") |
| 8 | Increment 3, `test_groups_api.py::test_strict_every_sector_has_too_long_an_approach` |
| 9 | Existing `test_groups_api.py::test_search_with_no_members_explains_why`, which must stay green |
| 10 | Existing scored and strict tests pass unchanged apart from the new `filters` key; `test_merge_without_approach_limits_means_no_restriction` |

Every criterion is covered. AC 4's "existing members" can only be fully checked by hand, because
tests build the schema with `create_all` and never run a migration.

## Risks
- **Migration downgrade:**
  - `downgrade -1` on increment 2 drops the members' limits, and they can't be recovered.
  - Downgrading increment 1 drops the sector values, but upgrading again restores them through
    the backfill.
  - The downgrade must drop only its own column, so check the autogenerated file for stray
    PostGIS operations.
- **Existing data:**
  - The backfill matches on sector and crag name.
  - A sector created by hand with the same name at the same crag would get the same value.
    That's acceptable.
  - Sectors that aren't in the table stay NULL = unknown, which never excludes them.
- **Duplicated values:** the minutes live in both the migration and `seed.py`. They must match,
  so review them side by side. Migrations must not import app code, which is why they are
  duplicated.
- **Data quality:** `embed_sectors.py` labels the notes "illustrative, not verified beta". The
  minutes inherit that, and the hand mapping of vague notes (short = 10, long = 45) is a
  product guess, not a measurement.
- **Behaviour that must stay unchanged:**
  - when nobody sets a limit, results and order are identical (AC 10);
  - the empty-group message is unchanged (AC 9);
  - strict mode's distance and style handling don't change.

  The only visible API change is additive: the new keys in `SectorRead`, `MemberRead` and
  `MergedFilters`.
- **Strict filtering is indirect:** it relies on the `fit_count == len(members)` step in
  `search_for_group()`. If someone removes that step later, the approach limit silently stops
  applying in strict mode. `test_strict_respects_shortest_approach_limit` guards against this.
- **Pydantic lax mode:** `"20"` is coerced to 20, `20.5` is rejected, and `"abc"` is rejected.
  The frontend sends `Number(...)`, so this is fine.
- **External services:** none are touched. `embed_sectors.py` must not be re-run for this
  ticket, because the notes don't change. Re-running it would spend Voyage calls (free tier: 3
  requests/minute) for nothing. No calls to Claude or Overpass.
- **Dev server on Windows/OneDrive:** no `uv add` is needed, so there's no locked-file risk.

## Out of scope (copied from the ticket)
- Solo search (`/search`, Stage 1) filter on approach time: the request is about groups. It can
  be a follow-up ticket.
- Approach difficulty (steepness, scrambling, fixed ropes), e.g. Paretot's "short but steep":
  it's a separate preference and has no data.
- Reading approach times out of `approach_notes` with Claude: guessing data with an LLM needs
  its own reliability discussion. Entering it by hand covers the current dataset.
- Natural-language search ("short approach") and the RAG/agent tools: they already read the
  free text and can be aligned later.
- Driving time instead of straight-line distance: unrelated to walking.
