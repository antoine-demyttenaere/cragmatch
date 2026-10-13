# 016: New frontend, part 1: design, app shell and single-person search

**Status:** Ready
**Size:** M by the size rules (frontend only, no migration), but a large M: a new project and a design system
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Prepare tickets for creating the frontend with associating what we've done in the backend and a new frontend. I want to include the AI part with the graphs. Create a nice design. Do the plan."
**Part of:** the new frontend (015 → 016 → 017 → 018). This ticket sets the look and the
structure that 017 and 018 build on.

## Decisions already made by the user (2026-10-13)
- A fresh frontend app built from scratch, not a restyle of `frontend/`. The old app stays
  until the new one covers everything it does (ticket 017), then it is removed.
- "A nice design" is a goal of its own, not just a port of the features.
- Delivery mode, one delivery per ticket.

## User story
As a climber planning a trip from Barcelona, I want a good-looking, easy app to search for
sectors (by filters, in my own words, or by vibe), so that I can find where to climb and
where to sleep without reading raw lists.

## What exists today
(Checked against the code on 2026-10-13.)
- Old frontend `frontend/` (React 19 + TypeScript + Vite, about 1,000 lines). It still uses
  the Vite template's CSS (`index.css`: purple accent, a centred 1126px column), with
  inline styles and plain buttons as tabs.
  - `SearchPage.tsx`: filter search (`GET /sectors/search`), natural-language search
    (`POST /search/natural`, which shows the filters Claude understood), and vibe search
    (`POST /search/similar`, with a similarity score and a "why it matches" reason per sector).
  - `StaysPanel.tsx`: stays near a sector (`GET /sectors/{id}/stays`).
  - `api.ts` `apiRequest()` / `errorMessage()`, `API_URL` hardcoded to `localhost:8000`.
    `constants.ts` holds grades and styles. `types.ts` mirrors the backend schemas.
- Backend behaviour the UI must handle:
  - `/search/natural` and `/search/similar` are rate-limited to 10 per minute (429).
  - `/search/natural` can come back with `understood: false` (off-topic query).
  - A vibe `reason` can be null, when Claude's explanation failed.
  - `/sectors/search` answers 400 for an invalid grade.
- CORS allows only `http://localhost:5173`.
- The tooling expects `frontend/`: the lint hook `.claude/hooks/lint_after_edit.py`, the
  developer and tech-lead agents (`npm run lint` in frontend/), CLAUDE.md and README.
- No frontend test runner. Checks today are `npm run lint` and `npm run build` (tsc).

## Acceptance criteria
1. Given the new app is running, when it opens, then it shows a CragMatch home with clear
   navigation to "Find crags" and "Group trip". The group section can be a placeholder
   until ticket 017.
2. Given the design, then it has one consistent visual system, used by every screen:
   colours, type scale, spacing, and the same components for buttons, inputs, cards, grade
   and style chips, and the loading, empty and error states. It reads as a climbing and
   outdoor product, not the Vite template.
3. Given the system's light or dark setting, when the app loads, then it follows that
   setting, and both themes are readable (text contrast at least WCAG AA).
4. Given a phone-width screen (375 px), then every screen in this ticket fits without
   horizontal scrolling and works by touch. Given a laptop screen, then results use the
   extra width (e.g. a grid or a list and detail).
5. Given filter search, when a grade range, style and max distance are submitted, then
   matching sectors show as cards with crag, grades, style, distance and walk-in time.
   Given no match, then a friendly empty state suggests widening the filters.
6. Given natural-language search, when a query is submitted, then the results show along
   with the filters Claude understood (grades, distance, style). Given an off-topic query
   (`understood: false`), then the app says it didn't understand, instead of showing an
   empty list.
7. Given vibe search, when a description is submitted, then results are shown in rank order
   with a visible match score and the "why it matches" reason. Given a null reason, then
   the card still shows, without a reason.
8. Given any sector card, when its stays are opened, then nearby stays show with type,
   distance and a link when there is one. Given none within range, then the panel says so.
9. Given a 429 from a rate-limited search, then the app shows "too many searches, try again
   in a minute", not a raw error. Given the API is down, then a clear error is shown and
   the page doesn't break.
10. Given the new app, then `npm run lint` and `npm run build` pass.

## Scope
**In:**
- A new frontend project with the same stack (React 19, TypeScript, Vite), alongside
  `frontend/`.
- The design system and app shell (header, navigation, layout, light and dark).
- Filter, natural-language and vibe search, and the single-sector stays panel.
- The tooling for the new folder: lint hook, agents' lint step, CLAUDE.md commands, README
  run steps and structure.

**Out:**
- Groups, members, group search, group stays: ticket 017.
- Removing `frontend/`: ticket 017, once the new app covers everything.
- The trip planner screen and diagram: ticket 018.
- A map of crags: nice, but not something the old app has. It would be a ticket of its own.
- Admin forms to create crags and sectors (`POST /crags`, `POST /sectors`): the old app
  doesn't have them either, and seed scripts cover them.
- A production build setup or a configurable `API_URL`: Stage 7 (ticket 013).

## Open questions
- [non-blocking] Folder name and dev port of the new app? (suggested default: `web/` on
  Vite's default 5173. Stop the old `frontend/` dev server while using it, so CORS needs no
  change.)
- [non-blocking] A styling approach or a UI library? (suggested default: the tech lead
  picks one that keeps the visual system in one place. No heavy component framework.)
- [non-blocking] A frontend test runner? (suggested default: not in this ticket. Keep lint,
  build and the manual check, as today. Revisit if 018's diagram logic gets complex.)
- [non-blocking] A visual direction? (suggested default: calm and outdoorsy, with a
  limestone, warm-neutral base, one strong accent for actions, and grade and style shown as
  chips. Clean, not decorative.)

## Notes for the tech lead
- `types.ts` mirrors the backend schemas: bring it across and keep it in sync (CLAUDE.md:
  update both together). The same goes for the grades and styles in `constants.ts` (backend
  order, never compare grade strings).
- Reuse the ideas of `apiRequest()` / `errorMessage()`, including the readable 429 and
  FastAPI 422 messages.
- `react-hooks` lint rules, function components, derive values instead of storing them in
  state (CLAUDE.md).
- Update `.claude/hooks/lint_after_edit.py` (it hardcodes `frontend/src`) and the developer
  and tech-lead agent files, or edits in the new folder go unlinted.
- Definition of done: new folders go in the README structure.
- Plan the manual check at phone width and in both themes, since there are no frontend tests.
