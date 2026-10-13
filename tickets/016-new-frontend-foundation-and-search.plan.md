# Plan for 016: New frontend, part 1: design, app shell and single-person search

**Ticket:** `tickets/016-new-frontend-foundation-and-search.md`
**Approach:** A new Vite + React 19 + TypeScript app in `web/`. It starts from the same
tool versions and lint config as `frontend/`, so ESLint, TypeScript and Vite behave the
same, but every line of `src/` is new. The design system is plain CSS: one tokens file
(colours, type, spacing, radius, shadow, with light and dark values) and CSS Modules for
the components, so the look lives in one place and needs no runtime library. The app
gets a shell (header, navigation, light/dark), a small UI kit, the search screen (one
page, three modes: Filters, Describe it, Vibe) and a stays panel. The tooling (lint hook,
agents, CLAUDE.md, README) learns about `web/`.

**Alternatives considered:**
- *Tailwind CSS:* fast to write, but the design rules end up spread across class strings
  in every component, and it adds a build plugin and a new vocabulary for a learning
  project. Tokens in CSS custom properties + CSS Modules (built into Vite) keep one
  source of truth and work for 018's SVG diagram too, which can read the same variables.
- *A component library (MUI, Chakra, Mantine):* heavy, and it would look like that
  library, not like CragMatch. The ticket says no heavy component framework.
- *`npm create vite` to scaffold:* it asks questions interactively, which the developer
  agent can't answer. It also brings the template CSS and assets we would delete
  straight away. Copying the four config files from `frontend/` and running
  `npm install` is deterministic and gives the same tool versions.
- *A router library (React Router):* two sections and one query parameter (`?group=`)
  don't need one. App state plus `URLSearchParams` is the pattern `frontend/App.tsx`
  already uses. Revisit if 018 needs deep links per run.

**Choices on the ticket's open questions:**
- Folder and port: `web/`, Vite's default 5173. CORS is unchanged, and the old
  `frontend/` dev server must be stopped while `web/` runs.
- Styling: CSS custom properties + CSS Modules (see above). Typography: one display face
  for headings, `@fontsource-variable/bricolage-grotesque` (self-hosted, no Google Fonts
  request), and the system stack for body text. The developer checks the package exists
  and swaps it for a similar grotesque if not.
- Test runner: none in this ticket. `npm run lint`, `npm run build` and the manual
  checklist below.
- Visual direction, applied as tokens:
  - Light: a warm limestone neutral background (`#F6F3EE`), white cards and dark slate
    text (`#1E2A2F`).
  - One accent for actions, a deep "chalk-bag" teal (`#0F766E`). One warm secondary,
    sandstone orange (`#C2410C`), only for highlights such as the match score.
  - Dark: deep slate background (`#12181B`), raised cards (`#1B2428`), the accent lifted
    to `#2DD4BF`.
  - Grade and style chips. Rounded 12px cards, soft shadow, generous spacing.
  - Every pair is checked for AA contrast in both themes (manual check 3).

## Ticket check
- **Wrong in the ticket, AC 6:** the backend never returns `understood: false`. When the
  query isn't a climbing search, `POST /search/natural` answers **422** with "Couldn't
  understand that as a climbing search — try the search form instead."
  (`routers/search.py:38-42`). The plan treats that 422 as the "didn't understand" state.
  It is shown as a friendly notice with a button to the Filters mode, not as an error.
  The `understood` field never reaches the UI as false.
- **Missing from the ticket:** `/search/natural` and `/search/similar` can also answer
  **503** when Claude or Voyage is down ("The search assistant is unavailable, try the
  search form instead."). The plan gives it the same friendly treatment, with a link to
  Filters.
- **Wrong in the ticket, AC 5:** single-person results carry **no distance**.
  `SectorRead` has crag `{id, name, region}` only, no coordinates and no distance
  (`schemas/sector.py:33`, `schemas/crag.py:23`). Distance only exists in group search
  results (`GroupSectorMatch.distance_km`). To keep this ticket frontend-only, the
  single-person cards show crag, region, grades, style and walk-in time, not distance.
  Showing distance there would need a small backend change, which would be a separate
  ticket if wanted.
- Correct: the 10/minute limits on `/search/natural` and `/search/similar` (429, body
  `{"error": "Rate limit exceeded: ..."}`), the nullable `reason`, the 400 for an invalid
  grade, CORS for `localhost:5173` only, and `API_URL` hardcoded in `api.ts`.
- Correct: `.claude/hooks/lint_after_edit.py:16,33-37` hardcodes `frontend/src` and
  `frontend/node_modules`. `.claude/agents/developer.md:21` and `tech-lead.md:40` say
  "npm run lint in frontend/". `CLAUDE.md:18,26-27` and `README.md:36,138` name
  `frontend/`.
- The vibe search always asks for `limit: 5` today. The new app keeps 5 (an extra control
  would be scope creep).

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. A new, designed CragMatch app with the three searches and stays, next to the old one
**Files** (frontend only. No backend change, so the backend suite is unchanged):

*Project set-up*
- `web/package.json`: copy of `frontend/package.json` with `"name": "cragmatch-web"`.
  Same scripts and the same dependency versions, plus the display font package.
- `web/tsconfig.json`, `web/tsconfig.app.json`, `web/tsconfig.node.json`,
  `web/eslint.config.js`, `web/vite.config.ts`: copied from `frontend/` unchanged (the
  same strictness and the same `react-hooks` rules).
- `web/index.html`: title "CragMatch", `lang="en"`, the viewport meta, a
  `theme-color` meta for light and dark, and an SVG favicon (a simple carabiner or peak
  mark, drawn inline, no image assets).
- `web/package-lock.json`, from `npm install` in `web/`.
- `web/.gitignore`: copied from `frontend/.gitignore`. The root `.gitignore` does **not**
  ignore `node_modules` or `dist`, so without this copy `git status` would show thousands
  of files.

*Design system* (`web/src/styles/`)
- `tokens.css`: all design tokens as CSS custom properties on `:root`. Colours by role:
  `--bg`, `--surface`, `--surface-raised`, `--text`, `--text-muted`, `--border`,
  `--accent`, `--accent-contrast`, `--accent-soft`, `--highlight`, `--danger`,
  `--success`. Type scale (`--step--1` … `--step-3`), spacing (`--space-1` … `--space-8`),
  radius, shadow and focus ring. Dark values go under
  `@media (prefers-color-scheme: dark)` (AC 3). A comment at the top says why (one
  source of truth, 018's diagram reads these too).
- `base.css`: a modern reset, body background and text from tokens, a visible
  `:focus-visible` ring, `prefers-reduced-motion` respected, and base sizes for
  headings, links and form controls.

*API layer* (`web/src/api/`)
- `client.ts`: `API_URL`, `apiRequest<T>()` and `errorMessage()`, rebuilt from
  `frontend/src/api.ts` (same three body shapes). On top of that:
  - an `ApiError` class carrying `status`, so screens can treat 422, 429 and 503 from
    the AI searches as notices rather than errors;
  - a 429 gives "Too many searches. Try again in a minute." (AC 9);
  - a failed `fetch` (a network `TypeError`) becomes "Can't reach the CragMatch server.
    Is the backend running?" (AC 9).
- `types.ts`: the schemas this ticket uses, mirrored from the backend: `Sector`,
  `ParsedFilters`, `NaturalSearchResponse`, `SimilarMatch`, `SimilarSearchResponse`,
  `StayRead`, `NearbyStay`. A header comment says to update them together with
  `backend/app/schemas`. The group types come in 017, the planner types in 018.
- `web/src/constants.ts`: `GRADES` (built the same way as `frontend/src/constants.ts`, in
  backend `GRADE_ORDER` order), `STYLES`, `STAY_TYPES`, `BARCELONA`, plus display labels
  for styles and stay types ("multi-pitch" becomes "Multi-pitch").

*UI kit* (`web/src/components/`, each `X.tsx` + `X.module.css`)
- `Button`: primary, secondary and ghost variants, and a loading state.
- `Field`: label + input/select + hint/error, linked with `id`/`htmlFor`.
- `Chip`: grade, style and neutral tones.
- `Card`.
- `SegmentedControl`: the mode switch, built as radio buttons so arrow keys work.
- `StateMessage`: loading (skeleton cards), empty, notice, and error tones. Each has an
  icon, a title, text and an optional action.
- `Sheet`: the stays panel. A bottom sheet under 768px and a side panel above it. It
  closes with Esc and has a close button. Focus moves into it when it opens.
- `Icon`: a handful of inline SVG icons (search, sparkle, map pin, clock, tent, close,
  external link). No icon library.

*Shell* (`web/src/app/`)
- `App.tsx`: header with the CragMatch wordmark and navigation (`Find crags`,
  `Group trip`). The active section is in state. `?group=CODE` on first load opens
  `Group trip`, the same rule as `frontend/App.tsx`, so 017 can build on it. Both sections
  stay mounted and hidden, as in the old app, so switching tabs keeps form state (AC 1).
- `App.module.css`: layout. A max-width content column with a 16px side gutter on phones,
  and a sticky header that collapses the navigation into a 2-item tab bar under 480px
  (AC 4).
- `web/src/main.tsx`: imports `styles/tokens.css` and `styles/base.css`, then renders
  `App`.

*Search feature* (`web/src/features/search/`)
- `SearchPage.tsx`: a hero line ("Find where to climb from Barcelona"), the
  `SegmentedControl` with Filters, Describe it (AI) and Vibe (AI), the active form, and
  the results.
  - Results state belongs to the search that produced it: one `result` value, a
    discriminated union `{kind: "filters" | "natural" | "vibe", ...}`. So parsed filters
    and scores can never show next to another search's results. This replaces the old
    `startSearch()` clearing of four states, a "derive, don't store" improvement.
  - Sorting stays (relevance, name, grade) and is derived at render time.
- `FilterForm.tsx`: min and max grade selects, style chips (any or one), and a max
  distance slider with a number shown (10-300 km). Submits to `GET /sectors/search` with
  `BARCELONA` as origin. A 400 for an invalid grade is shown under the form.
- `NaturalForm.tsx`: a textarea, two or three example prompts as clickable chips, and an
  "AI" badge. Shows an `UnderstoodFilters` strip with the result: grades, style and
  distance as chips, under "Here's what I understood" (AC 6). A 422 or 503 gives a notice
  `StateMessage` with a "Use filters instead" action that switches the mode (ticket
  check).
- `VibeForm.tsx`: a textarea with example vibes. Results in rank order (relevance is
  forced, as today) (AC 7).
- `SectorCard.tsx`:
  - Sector name, crag and region, grade range chip, style chip, walk-in
    ("25 min walk-in" or "Walk-in unknown"), and a "Stays nearby" button (AC 5, 8).
  - In vibe results, also a match score badge (rounded %, highlight colour) and the
    reason in a quote style. With no reason, the card renders without that block (AC 7).
  - Cards sit in a grid: one column on phones, two or three on wide screens (AC 4).
- `UnderstoodFilters.tsx`.

*Stays feature* (`web/src/features/stays/`)
- `StaysPanel.tsx`: the single-sector version only (group options come in 017).
  - It sits in a `Sheet`, with a type filter (chips) and a radius control.
  - Each stay row shows its type icon, name, distance and price range when known, and an
    external link when `url` is set. With no stays, it says "No stays within N km. Try a
    bigger radius." (AC 8).
  - Loading is derived from "loaded URL ≠ current URL", the same pattern as
    `frontend/src/StaysPanel.tsx`, which the lint rules accept, with the cancelled-flag
    effect.

*Group placeholder* (`web/src/features/group/GroupPlaceholder.tsx`)
- A designed empty state: "Group trips are moving here soon". It shows the `?group=` code
  when present and says the old app at `frontend/` still works. Ticket 017 replaces it
  (AC 1).

*Tooling and docs*
- `.claude/hooks/lint_after_edit.py`: lint `.ts`/`.tsx` under **both** `frontend/src` and
  `web/src`, each with its own `node_modules` ESLint. Use a small loop over the two app
  folders, not a copied block. 017 removes `frontend/` from it.
- `.claude/agents/developer.md:21` and `tech-lead.md:40`: "run `npm run lint` (and
  `npm run build`) in the frontend app you changed (`web/` or `frontend/`)".
- `CLAUDE.md`:
  - Stack: "Frontend: React 19 + TypeScript + Vite in `web/` (new). `frontend/` is the
    old app until ticket 017."
  - Commands: `npm run dev` / `npm run lint` / `npm run build` from `web/`.
  - Reuse: `apiRequest()` / `ApiError` in `web/src/api/client.ts`, the UI kit in
    `web/src/components/`, and design tokens in `web/src/styles/tokens.css` (never
    hardcode a colour).
- `README.md`: "Running locally" step 3 uses `web/` (and notes that the old `frontend/`
  still runs, but not at the same time on 5173). Add a `web/src/` tree to "Project
  structure" with one line per folder (Definition of done 3).

**Reuses:** the logic of `frontend/src/api.ts` (error shapes), the `GRADES` construction in
`frontend/src/constants.ts`, the `?group=` reading in `frontend/src/App.tsx`, the
stale-response and derived-loading pattern in `frontend/src/StaysPanel.tsx`, the
backend's error messages, and the config files of `frontend/`. Nothing is imported
across the two apps: `web/` stands alone so `frontend/` can be deleted in 017.

**Tests:**
- No frontend test runner (decision above). `npm run lint` and `npm run build` in `web/`
  must pass (AC 10).
- Backend: `uv run pytest` is unchanged and green (no backend file changes).

**Expected suite:** backend unchanged: 176 passed, or 199 if ticket 015 was committed
first. `web/`: lint 0 problems, build succeeds.

**Check by hand** (by the user with the backend running and `frontend/` stopped, in `web/`
with `npm run dev`). Use the browser devtools device bar for phone width:
1. Home opens on Find crags. The navigation switches to Group trip and back, and a
   half-filled form is kept. `/?group=9JS3VA3C` opens Group trip with the placeholder
   and the code (AC 1).
2. Every screen uses the same buttons, fields, chips and cards. No purple Vite leftovers
   (AC 2).
3. Switch the OS (or devtools "emulate prefers-color-scheme") between light and dark.
   Both are readable. Spot-check text and accent contrast with the devtools contrast
   picker: AA, 4.5:1 for body text (AC 3).
4. At 375px: no horizontal scroll on any screen, the stays panel is a bottom sheet, and
   targets are big enough to tap. At 1280px: results in a grid (AC 4).
5. Filters 6a–7a, sport, 120 km gives cards with crag, region, grades, style and walk-in.
   9a–9a+ within 10 km gives the empty state with a "widen your filters" hint (AC 5).
6. Describe it: "sport 6b to 7a under 2 hours" shows the understood-filters strip and
   results. "what's the weather in Paris" shows the friendly didn't-understand notice
   with "Use filters instead" (AC 6).
7. Vibe: "quiet crag, short approach" gives ranked cards with a score and a reason (AC 7).
8. "Stays nearby" opens the sheet with stays. Shrink the radius to 1 km to see the empty
   message (AC 8).
9. Eleven quick Describe it searches in a minute: the 11th shows "Too many searches…".
   Stop the backend and search: "Can't reach the CragMatch server…", and the page still
   works (AC 9).
10. `npm run lint` and `npm run build` in `web/` both pass (AC 10).

**Commit:** `Ticket 016: new web app in web/ with a design system (tokens, light and dark, CSS Modules UI kit), app shell, filter, natural-language and vibe search with understood filters, match scores and reasons, stays panel, friendly 422, 429, 503 and offline states; lint hook, agents, CLAUDE.md and README know about web/`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Manual check 1 |
| 2 | Manual check 2; review: every colour comes from `tokens.css` (grep for hex codes outside it) |
| 3 | Manual check 3 |
| 4 | Manual check 4 |
| 5 | Manual check 5 (no distance on single-person cards, see ticket check) |
| 6 | Manual check 6 (`understood: false` is really a 422, see ticket check) |
| 7 | Manual check 7 |
| 8 | Manual check 8 |
| 9 | Manual check 9 |
| 10 | `npm run lint`, `npm run build` in `web/` |

Every criterion except 10 depends on a manual check, because there is no frontend test
runner (the user's decision on the open question). The reviewer should run lint and the
build, and grep `web/src` for hardcoded colours (`#[0-9a-fA-F]{3,6}` outside
`tokens.css`) and inline `style=` attributes.

## Risks
- **Size:** this is the biggest frontend change so far: about 25 new files. It stays one
  delivery because it is all one app with no backend change. If the developer reports it
  is too much, split the ticket (search first, stays second), never the plan.
- **Two apps on one port:** `frontend/` and `web/` both default to 5173, the only origin
  CORS allows. Only one can run at a time until 017 deletes `frontend/`. README says so.
- **The lint hook:** a mistake in `lint_after_edit.py` silently stops linting, or blocks
  every edit. After changing it, edit one `.tsx` file in each app and check the hook
  fires for both.
- **Font package:** if `@fontsource-variable/bricolage-grotesque` is missing or renamed,
  use a similar variable grotesque. The type scale doesn't depend on the exact font.
- **Behaviour that must stay unchanged:** `frontend/` keeps working untouched (no edits
  under `frontend/`), and the backend is untouched.
- **External services:** the AI searches cost Claude and Voyage calls. Manual check 9
  makes 11 natural searches on purpose: run it once.

## Out of scope (copied from the ticket)
- Groups, members, group search, group stays: ticket 017.
- Removing `frontend/`: ticket 017.
- The trip planner screen and diagram: ticket 018.
- A map of crags: a ticket of its own.
- Admin forms to create crags and sectors.
- A production build setup or a configurable `API_URL`: Stage 7 (ticket 013).
