# Plan for 018: Stage 7, part 1: continuous integration (tests, ruff, ESLint)

**Ticket:** `tickets/018-ci-pipeline.md`
**Approach:** One GitHub Actions workflow, `.github/workflows/ci.yml` (workflow name `CI`), runs
on every push and every pull request. It has three jobs: `tests` (Backend tests), `ruff` (Ruff)
and `eslint` (ESLint, `web/` only). The tests job builds the repo's own `postgres.Dockerfile`
(PostGIS plus pgvector, the same image as local work), starts it with a `cragmatch_test`
database and runs `uv run pytest` with dummy `CRAGMATCH_` settings. Outbound HTTP points at a
closed local port, so an unmocked Claude, Voyage or Overpass call fails. Everything installs
from the lockfiles. No application or test code changes: ruff and ESLint are green today.
This plan assumes ticket 017 is delivered as its plan says, so `frontend/` no longer exists.

**Alternatives considered:**
- A `services:` container with `pgvector/pgvector:pg17`: it has no PostGIS, and AC 2 asks for
  it.
- A `services:` container with `postgis/postgis:17-3.5`, then `docker exec ... apt-get install
  postgresql-17-pgvector`: works, but it copies the Dockerfile's install line into the
  workflow, and the two would drift. Building `postgres.Dockerfile` reuses the recipe as it
  is. (`docker compose up` is not an option: `docker-compose.yml` reads `backend/.env`, which
  CI does not have and must never have.)
- An autouse fixture in `backend/conftest.py` that blocks sockets, to keep the suite offline:
  stronger, and it would work locally too, but it changes test code in a ticket that is meant
  to be a workflow file. The proxy variables (pytest step below) do the job in CI with no code
  change. It can be a later ticket.
- A pytest test that parses `ci.yml` and asserts the three jobs and no `secrets.`: the workflow
  is configuration, not app logic, and its behaviour only shows on GitHub. The reviewer reads
  it, and a YAML parse is part of the hand check instead.
- A matrix or a separate job per frontend command: more than the three results AC 1 asks for.
  One ESLint job with one step per command keeps three results and gives ticket 020 its slot.

## Ticket check
Verified against the code on 2026-10-14 (`uv run ruff check .`, `npm run lint` in `web/`,
`uv lock --check` and `uv run pytest --collect-only -q` run; the full suite was not run,
because the test DB is shared with other planning work right now).
- No `.github/` folder: correct. Remote `antoine-demyttenaere/cragmatch` on GitHub: correct
  (re-checked with `git remote -v`).
- `frontend/` still exists today: correct. Plan 017 deletes it, the hook, agents, CLAUDE.md and
  README with it, and has a "CI leftovers" part that is skipped when `ci.yml` does not exist
  yet. In the order 017 then 018 nothing of that applies, so this plan never mentions
  `frontend/` in the workflow or the README.
- `web/package.json`: `lint` is `eslint .`, `build` is `tsc -b && vite build`, no `test`
  script: correct. `web/package-lock.json` is tracked in git, so `npm ci` works. `npm run lint`
  in `web/` passes today with no problems.
- `backend/conftest.py`: builds `TEST_DATABASE_URL` from the five settings with the database
  name `cragmatch_test` hardcoded, runs `CREATE EXTENSION IF NOT EXISTS vector`, then
  `create_all()`, and never creates the database: correct. PostGIS is used nowhere (only
  mentioned in `alembic/env.py`): correct. The `postgis/postgis` image's own init script
  creates the `postgis` extension in `POSTGRES_DB` on first start anyway.
- `Settings()` at import, five database fields and two keys, all required, no defaults:
  correct. `env_file=".env"` is relative to the working directory, so in CI the environment
  variables are the only source. `backend/.env.example` lists only the two keys, which is why
  the workflow has to spell out all seven.
- `tests/test_planner_checkpointer.py::test_postgres_saver_resumes_a_run_after_reopening` opens
  a real `PostgresSaver` on `cragmatch_test` (`open_postgres_saver()` calls `setup()`, which
  builds indexes `CONCURRENTLY`): correct, re-checked. A plain Postgres container supports
  this. Every other planner test uses `InMemorySaver` (`backend/conftest.py`'s `client`,
  `backend/tests/conftest.py`, `app/scripts/trip_planner.py`).
- Nothing in the suite reaches the dev database: `get_vector_store()` (which would connect
  through `settings.database_url`) is faked in `tests/test_rag_vectorstore.py`,
  `seed_notes.SessionLocal` is patched in `tests/test_rag_loader.py`, and `get_db` /
  `get_trip_planner` are overridden in the `client` fixture. `create_engine()` in
  `app/core/database.py` does not connect at import. So CI can leave the dev database
  uncreated on purpose (see the env below).
- Overpass needs no key (AC 7): correct. `fetch_overpass()` uses `httpx.post`; the Anthropic
  SDK and LangChain use httpx; Voyage's sync client uses `requests`. httpx and requests honour
  `HTTP_PROXY` / `HTTPS_PROXY`. Checked in the installed httpx: `allow_env_proxies = trust_env
  and transport is None`, and Starlette's `TestClient` passes its own transport, so the proxy
  variables do not touch TestClient requests. psycopg uses libpq, which ignores HTTP proxies.
- `ruff`: configured in `backend/pyproject.toml` (E4, E7, E9, F), in the `dev` group, not in
  CLAUDE.md's Commands: correct. "All checks passed!" today.
- `uv lock --check`: the lockfile matches `pyproject.toml` today, so `uv sync --locked` will
  pass on main.
- Local versions CI should match: Python 3.12 (`backend/.python-version`, uv picks it up),
  uv 0.11, Node 24.18 (README says "Node 20+"; Vite 8 needs 20.19+ or 22.12+, so 24 is safe).
- `pytest --collect-only -q`: **199 tests collected**.
- Nothing in the ticket is wrong. Two claims it marked "not re-checked today" (the remote and
  the checkpointer test) are now re-checked and correct.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. A CI workflow with three checks, documented in the README
**Files** (no migration, no backend or frontend code):
- `.github/workflows/ci.yml` (new):
  - `name: CI`; `on: push` (all branches) and `pull_request`. No `paths:` filters (AC 8).
    `permissions: contents: read` (the workflow only reads the code; 025/026 add their own).
  - Use the current major tag of each action, checked on its release page at build time:
    `actions/checkout`, `astral-sh/setup-uv` (with `enable-cache: true` and
    `cache-dependency-glob: backend/uv.lock`) and `actions/setup-node` (`node-version: 24`,
    `cache: npm`, `cache-dependency-path: web/package-lock.json`).
  - Every job: `runs-on: ubuntu-latest`, `timeout-minutes: 10` (AC 10; the jobs run in
    parallel), and the `name:` below, which is what GitHub shows as the check. Keep the job
    ids `tests`, `ruff`, `eslint` and the names exactly: tickets 020, 025 and 026 refer to them.
  - **Job `tests`, name `Backend tests`:**
    - Job-level `env`, all dummy and labelled as such in one comment, no `secrets.` anywhere
      (AC 6):
      - `CRAGMATCH_POSTGRES_USER: cragmatch`
      - `CRAGMATCH_POSTGRES_PASSWORD: ci-only-not-a-secret`
      - `CRAGMATCH_POSTGRES_DB: cragmatch`: the dev database name. It is deliberately **not**
        created in CI, so a test that reaches the dev database instead of `cragmatch_test`
        fails loudly instead of passing. Say so in the comment.
      - `CRAGMATCH_POSTGRES_HOST: 127.0.0.1` (not `localhost`, so libpq never tries IPv6
        first), `CRAGMATCH_POSTGRES_PORT: 5433` (same as local)
      - `CRAGMATCH_ANTHROPIC_API_KEY: ci-dummy-not-a-key`
      - `CRAGMATCH_VOYAGE_API_KEY: ci-dummy-not-a-key`
    - Steps:
      1. Checkout.
      2. `Build the database image`, from the repo root:
         `docker build -f postgres.Dockerfile -t cragmatch-db .`
      3. `Start the database`: `docker run -d --name db -p 5433:5432` with `POSTGRES_USER`
         and `POSTGRES_PASSWORD` taken from the `CRAGMATCH_` variables above (one source for
         the values) and `POSTGRES_DB=cragmatch_test`. The image's entrypoint creates that
         database, so `conftest.py` can connect (AC 2).
      4. `Wait for the database`, with a time limit:
         `timeout 60 bash -c 'until docker exec db pg_isready -h 127.0.0.1 -U "$CRAGMATCH_POSTGRES_USER" -d cragmatch_test; do sleep 1; done'`.
         Comment why `-h 127.0.0.1`: during first-start init the image runs a temporary
         server on the Unix socket only, so a socket check can say "ready" too early. TCP
         only answers once init is done.
      5. `Check the extensions`, so a broken image fails here with a clear message and not
         deep inside pytest: `docker exec db psql -U "$CRAGMATCH_POSTGRES_USER" -d
         cragmatch_test -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS postgis;
         CREATE EXTENSION IF NOT EXISTS vector;'` (AC 2).
      6. Set up uv (cache on `backend/uv.lock`), then in `backend/`: `uv sync --locked`. It
         installs exactly what the lock pins, dev group included, and fails if `uv.lock` is
         out of date with `pyproject.toml`; it never re-resolves (AC 12).
      7. `Run pytest`, in `backend/`: `uv run pytest`. Step-level env:
         - `HTTP_PROXY` and `HTTPS_PROXY`: `http://127.0.0.1:9` (a closed port)
         - `NO_PROXY: localhost,127.0.0.1`
         - `UV_OFFLINE: "1"`: `uv run` must not reach the network either; the sync step has
           already installed everything, so this changes nothing on a good run and fails
           fast on a bad one.
         Comment why: httpx (Anthropic SDK, LangChain, `fetch_overpass`) and requests (Voyage)
         honour these, so any unmocked outbound call fails at once with a proxy or connect
         error. This matters for Overpass, which needs no key (AC 7). Postgres is unaffected
         (libpq ignores HTTP proxies), and TestClient uses an in-process transport that
         ignores proxy variables. Pytest's default output names the failing test and its
         assertion (AC 3).
  - **Job `ruff`, name `Ruff`:** checkout, set up uv (same cache), in `backend/`:
    `uv sync --locked` (AC 12), then `uv run ruff check .`. No settings env: ruff does not
    import the app. Its default output prints `path:line:col: F401 ...` (AC 4).
  - **Job `eslint`, name `ESLint`:** checkout, set up Node 24 with the npm cache, then exactly
    these two steps, each with `working-directory: web` and exactly this step `name:`:
    1. `web: npm ci`: installs from `package-lock.json` and fails if it is out of sync with
       `package.json` (AC 12).
    2. `web: npm run lint` (AC 5).
    Keep `web: npm run lint` the **last step** of the job. Ticket 020 adds a `web: npm test`
    step right after it, in this job, and the job keeps the name `ESLint` (020 AC 12). Do
    not add a `test` step or a placeholder here.
- `README.md`:
  - Under "Running tests", add a short "Checks (same as CI)" block with the commands to run
    locally: in `backend/`, `uv run pytest` and `uv run ruff check .`; in `web/`,
    `npm run lint`.
  - Then one paragraph on what the workflow runs: on every push and pull request, three jobs
    (Backend tests, Ruff, ESLint). The tests run against the image built from
    `postgres.Dockerfile` with dummy settings and outbound HTTP blocked, so no real key is used
    or needed. Dependencies come from `uv.lock` and `package-lock.json`, so a stale lockfile
    fails the run. The checks are visible on GitHub but do not block merging (AC 11).
  - Project structure: add `.github/workflows/ci.yml  CI on every push and pull request:
    backend tests, ruff, ESLint (web/).` above `backend/` (DoD 3).

**Reuses:** the repo's `postgres.Dockerfile` (no second image recipe); the exact commands from
CLAUDE.md and `pyproject.toml` (`uv run pytest`, `uv run ruff check .`, `npm run lint`);
`backend/uv.lock` and `web/package-lock.json` (`uv sync --locked`, `npm ci`); `conftest.py` as
it is (it creates `vector` and the schema, and switches the limiter off).

**Tests:** no new pytest tests (see Alternatives). The existing suite must pass unchanged in CI.
If the first CI run finds a test that only passes locally (it reaches the dev database, the
network or a local file), fix that test in this commit by pointing it at `db_session` or a
mock, behaviour unchanged (AC 9), and report the fix in the hand-off. None was found in the
code (see Ticket check).

**Expected suite:** **199 passed** (199 collected today; plan 017 changes no backend test, and
this ticket adds none). Ruff: all checks passed. ESLint in `web/`: 0 problems.

**Check by hand.** The developer prepares the commit; the user pushes.
0. Before committing (developer and reviewer), from `backend/`:
   `uv run python -c "import yaml; d = yaml.safe_load(open('../.github/workflows/ci.yml')); print({k: v['name'] for k, v in d['jobs'].items()})"`
   prints `{'tests': 'Backend tests', 'ruff': 'Ruff', 'eslint': 'ESLint'}` (PyYAML is
   already in the lock). `git grep -n "secrets\." .github` finds nothing, and
   `git grep -n "frontend" .github README.md` finds nothing (AC 6).
1. Push the commit to `main`. In the Actions tab: three checks named Backend tests, Ruff and
   ESLint, all green. The run takes under about 10 minutes, the tests log shows
   `199 passed`, and the "Check the extensions" step shows `postgis` and `vector` created or
   already there (AC 1, 2, 9, 10).
2. Throwaway branch `ci-check`, one commit, never merged:
   - `backend/tests/test_ci_check.py` with `def test_fails(): assert 1 == 2`. The tests job
     goes red, and the log names the test and shows `assert 1 == 2` (AC 3).
   - Two more tests in that file, without mocks: one calls
     `httpx.get("https://overpass-api.de/api/status")`, one calls
     `get_chat_model().invoke("hi")`. Both fail with a proxy or connect error, never a
     success (AC 7).
   - An unused `import os` at the top of that file. Ruff goes red with
     `tests/test_ci_check.py:1:8: F401` (AC 4).
   - `const unused = 1` in `web/src/main.tsx`. ESLint goes red (AC 5).
   Push it: all three checks go red, each for its own reason.
3. Throwaway branch `ci-lock-check`, one commit: add `"rich>=13"` to `dependencies` in
   `backend/pyproject.toml` without running `uv lock`, and `"left-pad": "^1.3.0"` to
   `dependencies` in `web/package.json` without running `npm install`. Push: Backend tests and
   Ruff fail at `uv sync --locked` (lockfile needs to be updated), ESLint fails at `npm ci`
   (package.json and package-lock.json are not in sync) (AC 12).
4. Pull request from a third throwaway branch that changes one line in `web/` only: all three
   checks report on the PR, and the push run runs as well (AC 1, 8). Close the PR and delete
   the three branches; nothing from them is merged.
5. Read the README "Checks (same as CI)" block and run the three commands locally; they
   match what the CI logs show (AC 11).

**Commit:** `Ticket 018: CI on GitHub Actions for every push and pull request, three checks: backend tests against the repo postgres.Dockerfile image (PostGIS plus pgvector) with dummy settings and outbound HTTP blocked, ruff, and ESLint for web; installs only from the lockfiles; README says how to run the same checks locally`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Hand checks 1 (push, three named checks) and 4 (pull request) |
| 2 | Tests job steps 2 to 7; hand check 1 (extension step log, `199 passed`) |
| 3 | Hand check 2, failing test |
| 4 | Hand check 2, unused import names file and F401 |
| 5 | Hand check 2, ESLint violation in `web/src` |
| 6 | Hand check 0 (no `secrets.`); reviewer reads the env block: only dummy values |
| 7 | Dummy keys plus proxy variables on the pytest step; hand check 2, unmocked Overpass and Claude calls fail |
| 8 | No `paths:` filter; hand check 4, a web-only PR shows all three checks |
| 9 | Hand check 1 on main. Locally today: ruff and ESLint green, `uv lock --check` clean, 199 tests collect |
| 10 | `timeout-minutes: 10` per job, jobs in parallel; hand check 1 run time |
| 11 | README "Checks" block, CI paragraph and structure line; hand check 5 |
| 12 | `uv sync --locked` in both Python jobs, `npm ci` in ESLint; hand check 3 |

No criterion is left uncovered, but all except 6 and part of 9 can only be shown on GitHub
after the user pushes. Locally there is only the YAML parse, the greps and the three commands.

## Risks
- **Later tickets change the settings (021, 022, 023):** 021 may add required settings, a
  single database URL setting, or a "blank counts as missing" rule. Then `ci.yml`'s job `env`
  must change in the same commit: new required fields need dummy, non-blank values; renamed
  fields need renamed variables. Otherwise `Settings()` fails at import and the tests job is
  red at collection. If 021 or 023 make `conftest.py` build the test URL from the new URL
  setting, the CI env must give a URL that points at `cragmatch_test` on `127.0.0.1:5433`
  (and the dev name stays uncreated). Settings with defaults (021, 022) need nothing. Plans
  021 and 023 must list `.github/workflows/ci.yml` as a file to check.
- **Later tickets add jobs or workflows (024, 025, 026):** a Terraform `fmt`/`validate` job
  (024's option) or deploy jobs (025, 026) must add jobs or a separate workflow, not rewrite
  these three. They must keep the workflow name `CI`, the job ids `tests`, `ruff`, `eslint`,
  the three check names, and `permissions: contents: read` for these jobs (deploy jobs ask for
  `id-token: write` on their own). A deploy gate uses `needs: [tests, ruff, eslint]` in this
  workflow or `workflow_run` on `CI`. Ticket 020 adds only the `web: npm test` step after
  `web: npm run lint`.
- **Plan 017 not delivered as planned:** if `frontend/` still exists when this is built, stop
  and ask the main session; this plan does not lint it.
- **The suite may pass locally but not in CI:** a test that quietly uses the dev database, the
  network or `backend/.cache`. None found in the code. If one shows up it is a real bug: fix the
  test, not the workflow (AC 9). The full suite was not run for this plan (shared test DB);
  the developer runs it, and the first CI run confirms it.
- **Readiness race:** without `-h 127.0.0.1`, `pg_isready` can pass during the image's init
  phase and the first connect fails. The wait step uses TCP and a 60 second limit.
- **Image build depends on apt.postgresql.org:** pulling `postgis/postgis:17-3.5` and installing
  pgvector takes about a minute. A failure there is a red build step, not a test failure.
  Caching the image can be a later improvement.
- **External services:** none are called. GitHub Actions minutes: about 3 to 5 minutes per run,
  within the free tier. A pull request branch runs twice (push and PR); the ticket accepts it.
- **Behaviour that must stay unchanged:** no app, test or frontend code changes unless the
  first CI run forces a fix. `backend/.env` is never read, created or printed.
  `docker-compose.yml` and `postgres.Dockerfile` are untouched. CLAUDE.md is not edited
  (adding ruff to its Commands is the user's call).
- **No migration:** nothing to downgrade.

## Out of scope (copied from the ticket)
- The `web: npm test` step: ticket 020 adds the test runner and that step. This ticket leaves a
  clear place for it (the ESLint job).
- Deploying from CI: tickets 025 and 026 (AWS). This ticket only runs checks.
- Making the checks mandatory to merge (branch protection): a setting on GitHub, and a solo
  project.
- Type checking with mypy or similar, a coverage report, a build matrix of several Python or
  Node versions: nothing asks for them yet.
- Building or scanning the backend Docker image: ticket 021 creates it. Can be added later.
- Notifications (Slack, email): GitHub's own are enough.
- Also not in this plan: `npm run build` as a fourth check (the ticket's open question,
  default no). It is one more step in the ESLint job once the user wants it.
