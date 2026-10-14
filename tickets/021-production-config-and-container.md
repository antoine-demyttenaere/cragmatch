# 021: Stage 7, part 2: production-ready settings and a backend container

**Status:** Ready
**Size:** L (backend, container and frontend build; no migration). It is mostly configuration. The daily spending cap, which needs a migration, is its own ticket (022).
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013, split on 2026-10-13; renumbered on 2026-10-14. This is the first half of the old ticket 019. The second half is ticket 022.)
**Part of:** Stage 7 in execution order: 018 CI, 019 and 020 trip planner screen, 021 (this), 022 daily spending cap, 023 to 026 deploy on AWS.
**Depends on:** 017 (the old `frontend/` is gone, so the build-time API address goes in `web/` only). Best after 018, so CI covers the settings change.

## Decisions already made by the user (2026-10-13)
- Scope of Stage 7: containerize the backend, managed Postgres with PostGIS and pgvector,
  frontend on static hosting, secrets in the platform's secret store, migrations at deploy
  time, CI.
- Users: friends via share codes, no login. Paid endpoints keep their rate limits.
- Decision of 2026-10-14: the target platform is AWS (tickets 023 to 026), but **this ticket
  stays platform-neutral**: the container and settings must run anywhere.

## User story
As the owner of CragMatch, I want the app to run from a container with all its
environment-specific settings coming from outside the code, so that I can run the same build
on my machine now and on the internet later, without secrets in the code or the image.

## What exists today
(Checked against the code on 2026-10-14. "Earlier plan" means found by the tech lead on
2026-10-13 and not re-checked.)
- No Dockerfile for the backend. The only containers are `postgres.Dockerfile` (PostGIS image
  plus pgvector) and `docker-compose.yml`, which runs the database only (service `db`, host
  port 5433, reads `backend/.env`).
- Settings, `backend/app/core/config.py`: five database fields (user, password, db, host, port),
  `anthropic_api_key` and `voyage_api_key`, all required, no defaults, env prefix `CRAGMATCH_`,
  file `.env`. The database URL is always built from the five fields, in one property
  (`database_url`). There is no setting for CORS or for a single database URL.
- `backend/.env.example` lists only the two API keys (`CRAGMATCH_ANTHROPIC_API_KEY`,
  `CRAGMATCH_VOYAGE_API_KEY`), blank. It does not list the five database fields.
- CORS, `backend/app/main.py`: `allow_origins=["http://localhost:5173"]`, written in the code.
- `web/src/api/client.ts`: `export const API_URL = "http://localhost:8000";`, the only place the
  address is used. Ticket 016 deferred a configurable address to Stage 7.
- `backend/conftest.py` builds the test database URL from the same settings with the database
  name `cragmatch_test`. This must keep working.
- Everything that connects to Postgres goes through `settings.database_url`: the app's engine
  (`core/database.py`), Alembic, the vector store and the planner's checkpointer (which turns the
  URL into a plain connection string). So one URL with SSL options would reach all of them (earlier
  plan).
- The planner's paused runs live in Postgres, so nothing needs to persist on the container's
  disk. Alembic is run by hand today (`uv run alembic upgrade head`).
- The first vibe search needs a tokenizer that Voyage's client downloads from huggingface.co into
  the user's home cache (earlier plan, from the library code). A container therefore needs a
  writable home directory and outbound HTTPS to that host as well as to Voyage.
- Rate limits live in memory (slowapi, per client IP, 10 per minute on `/search/natural` and
  `/search/similar`: `routers/search.py`, `core/rate_limit.py`). That means one server process.

## Acceptance criteria
1. Given the backend image, when it is built and started with its settings supplied from outside
   (environment), then `GET /health` answers `database: connected` and `/docs` loads.
2. Given the image, then it contains no `.env` file and no API key, password or personal data. A
   missing required setting stops the start with an error that names the setting. Given a blank
   value (as in `.env.example`), then it counts as missing, not as an empty key.
3. Given one database URL setting that includes SSL options, when the app starts, then the API,
   the vector search, the planner and Alembic all connect with it. Given that URL is not set, then
   the five separate database settings still work exactly as today. Given both, then the URL wins.
4. Given a database URL in either common scheme (`postgres://` or `postgresql://`), then it is
   accepted.
5. Given an allowed-origins setting with one or more origins, when a browser calls the API from a
   listed origin, then the call works. Given an origin that is not listed, then the browser may not
   read the answer. Given no setting, then `http://localhost:5173` is still allowed, as today.
6. Given a production build of the web app with the API address set at build time, when the built
   site is served and opened, then its calls reach that API. Given no address set, then it points
   at `http://localhost:8000`, so local development is unchanged. The built files contain no key.
7. Given the image, then it can run Alembic migrations as well as serve the API, so a deploy can
   migrate with the same image.
8. Given the production build (backend container plus built `web/`) on this machine against the
   dev database, when the user does a filter search, a group, a vibe search, a natural-language
   search and a planner run, then they all work as in development. This is the "done" check.
9. Given `backend/.env.example`, then it lists every setting with a blank or default value and one
   line saying what it is, so a new machine or a platform knows what to provide.
10. Given the test suite and CI, then they run as today, with no new required variable: every new
    setting has a default. Given the test database, then the tests still use `cragmatch_test`.
11. Edge case: given the single database URL is set in a developer's `.env` by mistake, then the
    README says tests would follow it, so it is meant for deployments only.

## Scope
**In:**
- A backend Dockerfile (and what it must ignore, so no secret or cache enters the image).
- One optional database URL setting (with SSL options), keeping the five existing settings.
- CORS origins from settings.
- Blank values count as missing; `.env.example` lists every setting.
- A build-time API address for `web/`.
- A way to run the production-like setup locally (container next to the dev database), and the
  README for it, including how a container reaches the database on this Windows machine.

**Out:**
- The daily spending cap: ticket 022.
- Choosing a platform, accounts, infrastructure: tickets 023 to 026 (AWS).
- A Dockerfile for `web/`: it is deployed as static files, so a build is enough (the tech lead may
  disagree in the plan).
- Changing the per-IP rate limits: they stay as they are. How they behave behind a proxy or load
  balancer is a deployment matter (ticket 025).
- CI changes, unless the settings change forces them: say so in the plan.

## Open questions
- [non-blocking] What name for the single database URL setting? (suggested default: the tech lead
  picks one that matches the existing `CRAGMATCH_POSTGRES_*` names and does not clash with the
  existing `database_url` property.)
- [non-blocking] Does the image run one worker? (suggested default: yes, because the rate limits are
  in memory; write why in the Dockerfile.)
- [non-blocking] How does the local production-like run start: a compose profile next to the `db`
  service, or plain `docker run`? (suggested default: compose profile, so a plain
  `docker compose up -d` still starts only the database.)

## Notes for the tech lead
- **Ticket 023 targets AWS.** Keep every choice here platform-neutral: the port comes from the
  environment, secrets come as environment variables, the image runs as a non-root user and listens
  on the port it is given, and nothing assumes a specific provider. Check that the same image would
  run unchanged on AWS container services (you choose which in ticket 025).
- A managed Postgres usually gives one URL and may require SSL. Keep `database_url` as the one place
  that builds the URL, and check the planner's checkpointer works with whatever form you choose.
  Do not break `cragmatch_test` in `backend/conftest.py`.
- `settings = Settings()` runs at import time and both API keys are required. Do not make real keys
  optional just to satisfy tests; CI gives dummy values (ticket 018). If you rename or add required
  settings, CI's variables change in the same commit.
- Image needs: Python 3.12 (`backend/.python-version`), install from `uv.lock` with no dev group,
  non-root user with a writable home (see the tokenizer fact above), Alembic and `alembic.ini` in
  the image, no tests or caches, no `.env`. Keep `pytest` out of the way if it is cheap, but the
  earlier plan found it is also in the main dependencies; that cleanup is not required here.
- Windows + OneDrive: stop the dev server before `uv add` / `uv sync`. A container reaching the dev
  database on host port 5433 cannot use `localhost`; document the host address (or use compose
  service names). `docker run --env-file` keeps quotes in values, and `.env.example` writes
  `KEY=""`, so a quoted key would break: compose strips them (earlier plan).
- Hooks block any shell command that names `.env`: use the Edit tool for `.env.example`, and the user
  runs compose.
- Frontend: Vite only exposes variables prefixed `VITE_`, so no backend secret can reach the bundle.
  Empty value should fall back to `http://localhost:8000`.
- Tests: config tests must not read the real `backend/.env` or CI's variables; CORS behaviour needs a
  test with the `client` fixture. Everything stays offline.
- Definition of done: README structure (Dockerfile, `.dockerignore`, compose service, settings table);
  `npm run lint` and `npm run build` for `web/`; `uv run pytest`.
