# 018: Stage 7, part 1: continuous integration (tests, ruff, ESLint)

**Status:** Ready
**Size:** M (a workflow file, no migration; maybe small fixes if a check fails on the first run)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013, split on 2026-10-13; renumbered on 2026-10-14 to follow the order of execution. This was ticket 021.)
**Part of:** Stage 7 in execution order: 018 CI (this), 019 and 020 trip planner screen, 021 production config and container, 022 daily spending cap, 023 to 026 deploy on AWS.
**Depends on:** 017 (it deletes `frontend/`, so CI lints `web/` only). Nothing else.

## Decisions already made by the user (2026-10-13)
- On every push and every pull request, run `uv run pytest` against a Postgres with PostGIS
  and pgvector, `uv run ruff check .`, and `npm run lint`.
- Tests stay offline, as today.

## User story
As the developer of CragMatch, I want the tests and linters to run on every push and pull
request, so that a broken change is seen on GitHub before it is merged or deployed, not
only on my machine.

## What exists today
(Checked against the code on 2026-10-14.)
- No CI: there is no `.github/` folder. The git remote is on GitHub
  (`antoine-demyttenaere/cragmatch`, as found by the earlier plan; not re-checked today).
- `frontend/` (old app) and `web/` (new app) both still exist. Ticket 017 removes `frontend/`,
  and this ticket comes after it, so ESLint covers `web/` only.
- `web/package.json` has `lint` (`eslint .`) and `build` (`tsc -b && vite build`). It has **no
  test script**: there is no frontend test runner yet. Ticket 020 adds one, and with it the
  CI step `web: npm test`.
- Backend tests: `uv run pytest` from `backend/`. `backend/conftest.py` connects to a database
  named `cragmatch_test` on the host and port from the settings, runs
  `CREATE EXTENSION IF NOT EXISTS vector` and `create_all()`. It does not create the database
  itself, so it must already exist. It does not create `postgis`, and nothing in the backend
  uses PostGIS (the only mention is a comment in `alembic/env.py`).
- `settings = Settings()` is built when the app is imported. The five database fields and both
  API keys are required, with no defaults (`app/core/config.py`). With no `backend/.env`
  (CI has none), the import fails, so CI must supply all seven values. Dummy values are fine,
  because tests never call Claude or Voyage.
- Tests mock Claude, Voyage and Overpass, per CLAUDE.md. Most planner tests use `InMemorySaver`,
  but the earlier plan found one test, `tests/test_planner_checkpointer.py`, that opens a real
  `PostgresSaver` on `cragmatch_test`. So the CI database must be a real Postgres. (Found on
  2026-10-13, not re-checked today.)
- Overpass is a public API with no key. In CI, an unmocked Overpass call would succeed by
  accident, unlike Claude and Voyage, where a dummy key gets refused. So acceptance criterion 7
  needs outbound traffic blocked, not only dummy keys.
- `ruff` is configured in `backend/pyproject.toml` (rules E4, E7, E9, F), and it is not listed
  in CLAUDE.md's Commands. It passed on 2026-10-13 (earlier plan). ESLint passed in both apps
  on that day.
- The local database image is `postgres.Dockerfile` (PostGIS plus pgvector, from
  `postgis/postgis:17-3.5`).

## Acceptance criteria
1. Given a push to any branch, or a pull request, when the workflow runs, then it reports
   three separate results visible on GitHub: backend tests, ruff, and ESLint.
2. Given the backend tests job, then it starts a Postgres 17 with the `postgis` and `vector`
   extensions available and a database `cragmatch_test`, and runs `uv run pytest` in
   `backend/`. Given all tests pass, then the job is green.
3. Given a deliberately failing test, when pushed, then the tests job is red and the failure
   is readable in the log.
4. Given a deliberate ruff violation (an unused import), when pushed, then the ruff job is
   red and names the file and rule.
5. Given a deliberate ESLint violation in `web/`, when pushed, then the ESLint job is red.
6. Given the workflow, then it holds no real secret. The Anthropic and Voyage values it
   provides are dummies, and the repository's secret store is not used for them.
7. Given a test that calls Claude, Voyage or Overpass without a mock, then it fails in CI. The
   suite stays offline, including for Overpass, which needs no key.
8. Given a pull request that changes only the frontend, or only the backend, then all three
   checks still report (simple and predictable; skipping unchanged parts is not needed).
9. Given the current main branch, when the workflow first runs, then all three jobs are
   green. If a check fails because of an existing problem, that is fixed in this ticket,
   without changing behaviour.
10. Given a normal run, then the whole workflow finishes in under about 10 minutes.
11. Given the setup, then the README says how to run the same three checks locally and what
    the workflow runs.
12. Edge case: given a change to `backend/uv.lock` that does not match `pyproject.toml`, then
    the job fails instead of silently resolving new versions. Given `web/` with a lockfile
    that is out of date, the same.

## Scope
**In:**
- A GitHub Actions workflow that runs on push and on pull request, with the three checks,
  for `web/` only.
- A Postgres with PostGIS and pgvector, the `cragmatch_test` database created, and the dummy
  settings the app needs to import.
- Blocking unmocked outbound calls in the test run.
- Fixing existing violations if the first run is red, behaviour unchanged.
- The README note and the structure entry for the new file.

**Out:**
- The `web: npm test` step: ticket 020 adds the test runner and that step. This ticket
  leaves a clear place for it (the ESLint job).
- Deploying from CI: tickets 025 and 026 (AWS). This ticket only runs checks.
- Making the checks mandatory to merge (branch protection): a setting on GitHub, and a solo
  project.
- Type checking with mypy or similar, a coverage report, a build matrix of several Python or
  Node versions: nothing asks for them yet.
- Building or scanning the backend Docker image: ticket 021 creates it. Can be added later.
- Notifications (Slack, email): GitHub's own are enough.

## Open questions
- [non-blocking] Is GitHub Actions the CI? (suggested default: yes. The remote is on GitHub
  and it needs no other account. Tickets 025 and 026 also assume it.)
- [non-blocking] Branches: every push, or only `main` plus pull requests? (suggested default:
  as the user asked, every push and every pull request. A pull request branch will run
  twice; accept it.)
- [non-blocking] Add `npm run build` as a fourth check? It catches TypeScript errors that
  ESLint does not. (suggested default: no, the user named three checks. Ticket 026 builds the
  site on every deploy anyway.)
- [non-blocking] Should failing checks block merging? (suggested default: no, visible only.)

## Notes for the tech lead
- The test database must exist before pytest starts, or `conftest.py` fails on connect. The
  repository's own `postgres.Dockerfile` is the reference for what the database needs
  (`vector`, and `postgis` because the user asked for it). Whether to use that image or an
  equivalent public one is your call.
- Give all seven settings dummy, non-secret values in the workflow. Tickets 021 and 022 add
  settings with defaults, which need no more variables, but 021 also adds a single-URL option
  and a blank-value rule: check the workflow's variables still match after 021.
- Install from the lockfiles (`uv.lock`, `package-lock.json`), never resolve again.
- Reuse the commands in CLAUDE.md as they are, plus `uv run ruff check .` from `backend/`.
  Adding ruff to CLAUDE.md's Commands is the user's call.
- Keep one ESLint job with one step per command and clear step names: ticket 020 adds a
  `web: npm test` step to it, and the later AWS tickets will reuse the workflow's set-up. Keep
  three results visible on GitHub (criterion 1).
- The earlier plan's outbound-block idea was HTTP proxy variables pointing at a closed port.
  That is a suggestion, not a requirement. A socket block in `conftest.py` would also work, but
  changes test code.
- Definition of done: new file listed in the README structure; do not read or print
  `backend/.env`; no real keys anywhere.
