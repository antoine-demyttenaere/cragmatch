# 002: When a group search finds nothing, suggest which preference to relax

**Status:** Needs answers
**Size:** L
**Raw request:** "When a group search finds nothing, the app should suggest which preference to relax."

## User story
As a member of a group planning a trip, I want the app to tell me which preference
(and whose) is blocking the search and what relaxing it would unlock, so that I can
decide who gives in instead of guessing and re-running the search by hand.

## What exists today
- Group search is `GET /groups/{code}/search?mode=strict|scored&fit=overlap|cover`
  (`backend/app/routers/groups.py`), a thin call to `search_for_group()` in
  `backend/app/services/group_search.py`. It returns `GroupSearchResponse`
  (`backend/app/schemas/group.py`), mirrored in `frontend/src/types.ts`.
- "Nothing found" happens in three different ways today:
  1. **Strict, no common ground** (grades don't overlap, or no shared style):
     `merge_preferences()` (`backend/app/services/group_matching.py`) returns
     `conflicts`, and `common_ground=false`, `filters=null`, `results=[]`. `message` is
     the conflicts joined in one string, e.g. "No grade everyone climbs: Marc wants 7a
     or harder, but Ana wants 6a or easier." So this case already says WHO clashes and
     on WHAT, but gives no advice on what to change.
  2. **Strict, common ground but no sector**: `common_ground=true`, `filters` set,
     `results=[]`, `message` = "The group agrees on filters, but no sector matches
     them." There is no hint of which filter caused it.
  3. **Scored, nobody fits everyone**: `common_ground=false` but `results` is not
     empty: every sector is listed, best first. The frontend (`GroupPage.tsx`) shows
     "No sector fits everyone. Best compromises first:" and, per sector, who fits
     (`fits`) and who doesn't with a reason (`misfits`, from `why_not()`, e.g. "too far
     (112 km > 80 km)"). Also: an empty sector table gives an empty result with no
     message (I did not check whether that can occur outside tests).
- Also unchanged: a group with no members gets "Add at least one member to search."
- `why_not()` explains why ONE sector fails ONE member. It is not a suggestion: it does
  not say what to change, and nothing aggregates across sectors ("relaxing Marc's
  distance would unlock 4 sectors").
- **Missing:** any response field or UI element for suggestions; any logic that
  simulates a relaxed preference.
- Preferences a member has today: grade range (`grade_min`/`grade_max`), `max_distance_km`,
  `styles` (`Member` model, `backend/app/models/member.py`). Ticket 001 may add a max
  approach time; this ticket must not depend on it.
- `fit` (overlap vs cover) is a search option, not a member preference, but "cover"
  can also cause an empty result.
- I did not check test coverage of `group_search.py` beyond `test_group_matching.py`
  and `test_groups_api.py` existing.

## Acceptance criteria
1. Given a strict search with common ground and no matching sector, when the group
   searches, then the response still has no results and no error, and also lists at
   least one suggestion naming the member, the preference and the change.
2. Given a suggestion, when it is shown, then it states how many sectors it would
   unlock (e.g. "If Marc accepts up to 120 km instead of 80 km, 3 sectors match").
3. Given a suggestion for a single relaxation, when the search is re-run by hand with
   that change applied, then the number of results equals the number the suggestion
   promised.
4. Given a strict search with no common ground on grades (Ana 5-6a, Marc 7a-8a), when
   the group searches, then `conflicts` text stays as today, and suggestions name which
   member's range would need to move and to what grade to create overlap (exact
   behaviour per open question 3).
5. Given a strict search with no common ground on styles, when the group searches,
   then a suggestion names a member who would need to add a style.
6. Given a scored search where no sector fits everyone, when the group searches, then
   the ranked list is unchanged and suggestions are added (if open question 1 says
   scored is in scope).
7. Given a search where relaxing any single preference would still leave zero sectors,
   when the group searches, then the response has no suggestions and says so (it
   doesn't invent one). No error.
8. Given a search that already has results that fit everyone, when the group searches,
   then there are no suggestions and the response is otherwise the same as before.
9. Given a member with no preferences set, when suggestions are computed, then that
   member is never named in a suggestion (nothing to relax).
10. Given a group with no members, when it searches, then the response is unchanged:
    "Add at least one member to search."
11. Given a suggestion that relaxes a grade or distance, when it is shown, then it uses
    the same units and wording style as `why_not()` reasons (grades like "6b", km).
12. Given a climber on the group page, when a search returns suggestions, then they are
    visible near the "no result" message, without needing to open any sector.
13. Given the suggestions, when the same group and data are searched twice, then they
    come in the same order.

## Scope
**In (smallest useful version):**
- Suggestions on an empty strict result (cases 1 and 2 above), covering the relaxable
  preferences chosen in open question 2, one preference at a time.
- Each suggestion says who, which preference, to what, and how many sectors it unlocks.
- Shown in the group search view.

**Out:**
- Scored mode suggestions (unless answered otherwise): the scored list already shows
  who misfits and why. Revisit if users still ask "who should give in?".
- Combinations of several relaxations at once: harder to explain and much more to
  compute. Follow-up if single suggestions often leave zero.
- Applying a suggestion in one click (edit the member and re-run): nice, but it needs
  member editing from the search view. Follow-up ticket.
- Suggestions for the solo search (`/search`): the request is about groups.
- Suggesting a different date, area or origin (everything departs from Barcelona).
- Relaxing the `fit` option (overlap/cover): it is a search setting, not a person's
  preference. See open question 2.
- Natural-language explanations written with Claude: the suggestions are facts, no
  LLM needed, and tests must not hit the network.

## Open questions
- [blocking] Which preferences count as relaxable: grade range, max distance, styles,
  and `fit=cover` -> `overlap`? (suggested default: grade range, max distance and styles;
  not `fit`, which is shown as a hint only if you want it)
- [blocking] Which search modes get suggestions: strict only, scored only, or both?
  (suggested default: strict only, since scored mode already lists compromises)
- [blocking] For "no common ground" (cases of conflicting grades or styles), do
  suggestions replace the current conflict text or add to it? And for grades, is a
  suggestion "member X lowers their max to Y" at the minimum change that creates
  overlap, even if it then yields zero sectors? (suggested default: keep the conflict
  text, add suggestions after it, and only suggest changes that unlock at least one
  sector)
- [non-blocking] One suggestion or several? (suggested default: up to 3)
- [non-blocking] Ranked by how many sectors they unlock, ties by smallest change?
  (suggested default: yes, most sectors first, then smallest change, then member name)
- [non-blocking] How is "smallest change" measured across different units (grade steps
  vs km vs a style)? (suggested default: do not compare across units; rank by sectors
  unlocked only, then member name)
- [non-blocking] Should a suggestion name the single member whose relaxation unlocks the
  most, even if another member is "more flexible"? (suggested default: yes, list per
  member, no judgement about who should give in)
- [non-blocking] What step size for distance suggestions: the exact distance of the
  nearest sector that would unlock, or rounded up (e.g. to the next 10 km)? (suggested
  default: rounded up to the next 10 km)
- [non-blocking] Should the response keep the free-text `message` and add a structured
  list of suggestions, or is a text-only suggestion enough? (suggested default:
  structured list, so the frontend and Stage 6 agent tools can use it, message kept)

## Notes for the tech lead
- Reuse, don't duplicate: `merge_preferences()`, `score_sectors()`, `why_not()`,
  `grade_rank()`, `GRADE_ORDER`, `haversine_km()`. `group_matching.py` must stay pure;
  any code that needs sectors from the database stays in `group_search.py`.
- "No result" is a normal answer: suggestions are part of a 200 response, never an
  error (CLAUDE.md).
- Schema and `frontend/src/types.ts` change together; `npm run lint` must pass.
- No migration expected (no new stored data), so this is not L because of that: it is
  L only because it touches backend and frontend with a non-trivial new calculation.
  Check this when planning, since I did not design the solution.
- Tests: unit tests for the new pure logic with stand-in objects (cases: one relaxation
  unlocks sectors, none does, member without preferences, grades/styles with no common
  ground); TestClient tests for strict mode with common ground but no sector, strict
  with no common ground, and the unchanged no-members and has-results responses.
- Performance: the number of sectors is small today, but the tech lead should confirm
  that trying relaxations per member and preference doesn't need a query per attempt.
- Suggested split (L -> two tickets):
  1. Backend: relaxation suggestions in the group search response for strict mode,
     with tests. Backend only, no migration.
  2. Frontend: show the suggestions in `GroupPage.tsx` and mirror the types.
- Ticket 001 (approach time) touches the same files; whichever lands second must add
  or skip the approach-time preference as a relaxable one.
