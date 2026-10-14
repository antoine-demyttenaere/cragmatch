# Plan for 021: Stage 7, part 2: production-ready settings and a backend container

**Ticket:** `tickets/021-production-config-and-container.md`
**Approach:** Settings grow and nothing is renamed. They gain an optional
`CRAGMATCH_POSTGRES_URL`, which wins over the five `CRAGMATCH_POSTGRES_*` parts, accepts
`postgres://` and `postgresql://` and keeps query options such as `?sslmode=require`, plus a
comma-separated `CRAGMATCH_CORS_ORIGINS`. Every new setting has a default, a blank value counts as
missing, and errors never echo the values. `database_url` stays the one place that builds the URL;
it now escapes special characters in passwords (and Alembic escapes `%`), so a managed database's
generated password works everywhere. A `backend/Dockerfile` (uv from the lock with no dev group,
non-root user with a writable home, one worker on `$PORT`, Alembic inside) runs next to the dev
database through a `prod` compose profile. `web/` reads its API address from `VITE_API_URL` at
build time, falling back to `http://localhost:8000`.

Assumed delivered first, as their plans describe: 017 (`frontend/` is gone, only `web/`), 018
(`.github/workflows/ci.yml` with dummy `CRAGMATCH_` values in the `tests` job), 019 and 020 (planner
flow and diagram; nothing here depends on them). The spending cap, `tzdata`, `daily_spend` and
`TokenCounter` are ticket 022, not here.

**Alternatives considered:**
- *Replace the five database fields with one URL:* simpler in the end, but it breaks the user's
  `backend/.env`, ci.yml's job env and conftest's test URL at once. It would also lose a real AWS
  option: an RDS-managed secret is JSON with separate `username`, `password`, `host`, `port`, `dbname`
  keys, which ECS can inject one by one into the five variables. Keeping both serves both shapes.
- *A field named `database_url`:* clashes with the existing property that four call sites use.
  `postgres_url` matches the five `postgres_*` names (the ticket's open question).
- *An extra `CRAGMATCH_POSTGRES_SSLMODE` setting for the five-part form:* not needed. Every
  connection (SQLAlchemy engine, PGVector, the planner's pool, Alembic) goes through psycopg, i.e.
  libpq, which reads `PGSSLMODE` (and `PGSSLROOTCERT`) from the environment when the URL has no
  `sslmode`. So 025 can ask for TLS with the five parts and no code. Named as a seam below.
- *`SecretStr` for the keys and password:* hides them in `repr`, but every call site would need
  `.get_secret_value()`. `hide_input_in_errors=True` closes the real leak (start-up errors that
  print all input values) with one config line.
- *CMD through `sh -c "... --port ${PORT:-8000}"` (the earlier plan):* not needed. `fastapi run`
  already reads `PORT` (`envvar="PORT"` in `fastapi_cli/cli.py`, default 8000) and binds `0.0.0.0`
  by default, so an exec-form CMD gets the port and the stop signals directly.
- *ENTRYPOINT instead of CMD:* CMD can be replaced by a plain command
  (`docker compose run api alembic upgrade head`, an ECS task's `command` override), which is how
  the same image migrates (AC 7).
- *Download the Voyage tokenizer at build time:* removes the first-search download, but adds network
  to the build and copies the model name into the Dockerfile. The container needs outbound HTTPS to
  Voyage and Anthropic anyway. Instead `HF_HOME` is set explicitly, so a platform with a read-only
  home (Lambda: only `/tmp` is writable) can point it elsewhere. Baking it in stays an option for 025.
- *Multi-stage build to drop uv from the final image:* saves about 40 MB; not worth the extra
  stage for a learning project. 025 can add it if image size matters for its runtime.
- *A frontend Dockerfile (nginx):* static hosting needs only `dist/` (ticket's Out, agreed).
  `npm run preview` serves the build for the local check.
- *`docker run --env-file backend/.env`:* Docker keeps quotes as part of the value and
  `.env.example` writes `KEY=""`. Compose's `env_file` strips them, and the service name `db` solves
  the host-address problem. `host.docker.internal:5433` is still documented for `docker run`.

**Choices on the ticket's open questions:**
- Name: `CRAGMATCH_POSTGRES_URL` (field `postgres_url`).
- One worker: yes, `--workers 1` written out in the CMD with the reason (in-memory rate limits).
- Local production-like run: a compose service `api` under `profiles: ["prod"]`, so a plain
  `docker compose up -d` still starts only `db`. It publishes host port **8001**, so the dev server
  on 8000 can keep running (no process to stop) and the build-time address is visibly not the
  default.

## Ticket check
Checked against the code on 2026-10-14 (`uv run pytest --collect-only -q`: **199 tests**; the suite
was not run, because the test DB is shared right now).
- **Correct:** no backend Dockerfile; `docker-compose.yml` runs only `db` (build from
  `postgres.Dockerfile`, host 5433, `env_file: backend/.env`); `Settings` has five DB fields and two
  keys, all required, prefix `CRAGMATCH_`, `env_file=".env"`; `database_url` is one property;
  `.env.example` lists only the two keys as `KEY=""`; CORS is hardcoded at `backend/app/main.py:39`;
  `web/src/api/client.ts:1` is the only place with the address; `backend/conftest.py:17-20` builds the
  test URL from the five fields with `cragmatch_test`; the rate limiter is per IP in memory;
  `pytest` is in the main `dependencies` as well as in the dev group.
- **Correct:** every Postgres connection reads `settings.database_url`: `core/database.py:5` (engine,
  and through `SessionLocal` every script), `rag/vectorstore.py:25` (PGVector),
  `routers/planner.py:31` (`psycopg_conninfo()`, which uses `make_url().set(drivername=...)` and so
  keeps the query string) and `alembic/env.py:63`. `alembic.ini`'s `sqlalchemy.url` is a placeholder.
- **Missing from the ticket (breaks AC 3 with a managed database):**
  - `database_url` pastes the password into an f-string unescaped. A password with `@`, `:`, `/`,
    `#` or `?` (which generated passwords can contain) gives a wrong URL. Building it with
    `sqlalchemy.engine.URL.create()` and `render_as_string(hide_password=False)` escapes it; the
    result is unchanged for today's plain passwords.
  - `alembic/env.py` passes the URL to `config.set_main_option()`, which goes through
    ConfigParser interpolation: any `%` (a percent-encoded password, `%40` for `@`) fails with
    "invalid interpolation syntax". It must pass `url.replace("%", "%%")`.
- **Missing from the ticket (security, AC 2):** a pydantic `ValidationError` prints the whole input,
  so today a missing setting prints `input_value={... 'anthropic_api_key': '...', 'postgres_password':
  '...'}` to the log. `hide_input_in_errors=True` in `model_config` stops that.
- **Missing from the ticket (trap):** `BaseSettings` forbids extra inputs. The dotenv source skips
  unprefixed names that equal a field (that is why `POSTGRES_USER` / `_PASSWORD` / `_DB` for the `db`
  container are harmless in `backend/.env`, checked in `pydantic_settings/sources/providers/dotenv.py`),
  but any other unprefixed line (`PORT=`, `HF_HOME=`, `PGSSLMODE=`) in `backend/.env` would stop the
  app with "Extra inputs are not permitted". So `.env.example` lists the container variables as
  comments only.
- **Confirmed (earlier plan):** the first vibe search tokenizes with
  `Tokenizer.from_pretrained("voyageai/voyage-3.5")` (`voyageai/_base.py:160`, called from
  `langchain_voyageai` `_build_batches`), downloaded from huggingface.co into `$HF_HOME` (default
  `~/.cache/huggingface`). The image needs a writable home (or `HF_HOME`) and outbound HTTPS.
- **Confirmed:** `fastapi run` turns proxy headers on and leaves `forwarded_allow_ips` to uvicorn,
  which reads the `FORWARDED_ALLOW_IPS` environment variable (default `127.0.0.1,::1`,
  `uvicorn/config.py:363`). So the client-IP question for 025 is environment, not code.
- **Detail:** `backend/pyproject.toml` has no `[build-system]` and points at a `README.md` that does
  not exist in `backend/`; uv treats it as a virtual project, so the image uses
  `uv sync --no-install-project` and runs the code from `/app`.
- **Detail:** `services/overpass.py:37` caches under `backend/.cache/overpass`. In the image that is
  `/app/.cache`, owned by root, so `import_stays` cannot cache inside the container. Not needed here
  (the API never calls Overpass), but 023 and 025 must know (`import_stays` stays on the laptop).
- **Detail:** `web/tsconfig.app.json` has `"types": ["vite/client"]`, so `import.meta.env` already
  type-checks; a `vite-env.d.ts` narrows `VITE_API_URL` from `any` to `string | undefined`.
  `moduleDetection: "force"` only applies to non-declaration files, so the `.d.ts` augments globally.
- **CI (018):** no required setting is renamed or added; the five parts and two keys that ci.yml
  sets still satisfy `Settings`, and conftest's new URL is the same string for them. **ci.yml needs
  no change**; the reviewer checks the job env against the new `Settings`.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. Settings from outside, a backend image that runs anywhere, a build-time API address
**Files** (no migration; backend, container, frontend, docs):

*Settings*
- `backend/app/core/config.py`:
  - `postgres_url: str | None = None`; the five parts become optional (`str | None = None`,
    `postgres_port: int | None = None`). `anthropic_api_key: str` and `voyage_api_key: str` stay
    required with no default (ticket note); remove the trailing spaces on those two lines.
  - `cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]` (`NoDecode` from
    `pydantic_settings`, so the value is not parsed as JSON first).
  - `model_config = SettingsConfigDict(env_file=".env", env_prefix="CRAGMATCH_",
    env_ignore_empty=True, hide_input_in_errors=True)`. One comment each, why: a blank value (as in
    `.env.example`) counts as missing instead of starting with an empty key; errors must never print
    keys or passwords into a platform's logs.
  - `field_validator("cors_origins", mode="before")`: a string is split on commas; each part is
    stripped of spaces and of a trailing `/` (a browser's `Origin` never has one, so
    `https://x.example/` would otherwise never match); empty parts are dropped. Comment why: a comma
    list is easier to type into a platform's settings page than JSON.
  - `field_validator("postgres_url")`: `make_url()` must parse it (turn `ArgumentError` into
    `ValueError`) and `get_backend_name()` must be `postgres` or `postgresql`; otherwise
    `ValueError("CRAGMATCH_POSTGRES_URL must start with postgres:// or postgresql://")`. The message
    never contains the URL (it holds the password).
  - `model_validator(mode="after")`: when `postgres_url` is not set and any of the five parts is
    `None`, raise `ValueError` naming the variables: "Set CRAGMATCH_POSTGRES_URL, or all of
    CRAGMATCH_POSTGRES_USER, CRAGMATCH_POSTGRES_PASSWORD, CRAGMATCH_POSTGRES_DB,
    CRAGMATCH_POSTGRES_HOST, CRAGMATCH_POSTGRES_PORT (missing: ...)" (AC 2).
  - `database_url` property: with `postgres_url`,
    `make_url(self.postgres_url).set(drivername="postgresql+psycopg")`; otherwise
    `URL.create("postgresql+psycopg", username=..., password=..., host=..., port=..., database=...)`.
    Both end in `.render_as_string(hide_password=False)`. The docstring/comment says: still the only
    place that builds the URL; the driver is forced, so both schemes platforms hand out work (AC 4);
    query options such as `sslmode` are kept; `URL.create` escapes special characters in the password.
- `backend/alembic/env.py:63`: `config.set_main_option("sqlalchemy.url",
  settings.database_url.replace("%", "%%"))`, with the why: the option goes through ConfigParser
  interpolation, and a percent-encoded password contains `%`.
- `backend/conftest.py`: `TEST_DATABASE_URL = make_url(settings.database_url).set(
  database="cragmatch_test").render_as_string(hide_password=False)`. Same value as today for the
  five parts; it now also follows `CRAGMATCH_POSTGRES_URL` (AC 11, README says so). Update the comment.
- `backend/.env.example` (Edit tool only: the hook blocks shell commands naming `.env`). Every
  line `KEY=""` (blank means "not set" now) with one comment line per group:
  - database parts, used locally and in CI: the five `CRAGMATCH_POSTGRES_*`;
  - `CRAGMATCH_POSTGRES_URL=""`: one URL instead of the five, for deployments (it wins, and the tests
    would follow it too), example in the comment `postgres://user:password@host:5432/db?sslmode=require`;
  - `CRAGMATCH_ANTHROPIC_API_KEY=""`, `CRAGMATCH_VOYAGE_API_KEY=""`;
  - `CRAGMATCH_CORS_ORIGINS=""`: comma-separated, blank means `http://localhost:5173`;
  - `POSTGRES_USER=""`, `POSTGRES_PASSWORD=""`, `POSTGRES_DB=""`: read only by the `db` container;
  - comment lines only (never uncommented here, see Ticket check): `PORT` (default 8000),
    `FORWARDED_ALLOW_IPS`, `HF_HOME`, `PGSSLMODE`: set on the container, not in this file.
  **Ask the user** to confirm their `backend/.env` already has the three unprefixed lines (no agent
  may read it).

*App*
- `backend/app/main.py`: import `settings`; `allow_origins=settings.cors_origins`, comment: default is
  the Vite dev server, deployments set `CRAGMATCH_CORS_ORIGINS`.

*Container*
- `backend/Dockerfile` (new, build context `backend/`), with short why-comments:
  - `FROM python:3.12-slim` (matches `.python-version`);
    `COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/` (uv 0.11.32 locally).
  - `ENV UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1`: bytecode at build time
    (nothing written at run time, so a read-only filesystem is fine), use the image's Python, logs
    straight to stdout for the platform's log collector.
  - `WORKDIR /app`; `COPY pyproject.toml uv.lock ./`;
    `RUN uv sync --locked --no-dev --no-install-project --no-cache` (exactly the lock, no dev group,
    no uv cache left in the layer; this layer is reused while the lock is unchanged).
  - `COPY alembic.ini ./`, `COPY alembic ./alembic`, `COPY app ./app`. Nothing else: no tests, no
    caches, no `.env`.
  - `ENV PATH="/app/.venv/bin:$PATH"`.
  - `RUN useradd --create-home --uid 10001 --user-group cragmatch`,
    `ENV HF_HOME=/home/cragmatch/.cache/huggingface`, `USER cragmatch`. Comment why: not root, and a
    writable place for the Voyage tokenizer download; a platform with a read-only home overrides
    `HF_HOME`.
  - `EXPOSE 8000`;
    `CMD ["fastapi", "run", "app/main.py", "--workers", "1"]`. Comment: `fastapi run` listens on
    `0.0.0.0` and on `$PORT` (default 8000); one worker because the rate limits live in memory;
    exec form so the server gets the stop signal; CMD (not ENTRYPOINT) so the same image can run
    `alembic upgrade head` instead.
  - No `ENV` or `ARG` with a key, password or URL (AC 2).
- `backend/.dockerignore` (new). First line a comment: secrets and local caches never enter the build
  context. Then `.env`, `.env.*`, `.venv`, `**/__pycache__`, `**/*.pyc`, `.pytest_cache`,
  `.ruff_cache`, `.cache`, `tests`, `conftest.py`, `Dockerfile`, `.dockerignore`. (`**/` matters:
  a bare `__pycache__` only matches at the root.)
- `docker-compose.yml` (Edit tool): a service `api` with a comment (the production image on this
  machine, reaching the database by its service name; not started by a plain `up`):
  `profiles: ["prod"]`, `build: ./backend`, `image: cragmatch-api:local` (a fixed name for the checks),
  `env_file: [backend/.env]`, `environment:` `CRAGMATCH_POSTGRES_HOST: db`,
  `CRAGMATCH_POSTGRES_PORT: "5432"`,
  `CRAGMATCH_CORS_ORIGINS: http://localhost:4173,http://localhost:5173` (in compose, `environment`
  wins over `env_file`), `ports: ["8001:8000"]`, `depends_on: [db]`. `db` is unchanged.

*Frontend*
- `web/src/vite-env.d.ts` (new): `interface ImportMetaEnv { readonly VITE_API_URL?: string }` and
  `interface ImportMeta { readonly env: ImportMetaEnv }`.
- `web/src/api/client.ts:1`: `export const API_URL = import.meta.env.VITE_API_URL ||
  "http://localhost:8000";`. Comment why: Vite bakes it in at build time; `||` (not `??`) so an empty
  value also falls back and development is unchanged; only `VITE_` variables reach the bundle, so no
  backend secret can.

*Docs*
- `README.md`:
  - New section "Production-like run on this machine", after "Running tests" (and 018's "Checks"
    block), PowerShell commands, run by the user:
    1. `docker compose --profile prod build api`
    2. `docker compose --profile prod run --rm api alembic upgrade head` (the image migrates, as a
       deploy will)
    3. `docker compose --profile prod up -d api`, then `http://localhost:8001/health` and `/docs`
    4. in `web/`: `$env:VITE_API_URL = "http://localhost:8001"`, `npm run build`,
       `Remove-Item Env:VITE_API_URL`, `npm run preview` (serves on 4173, which the service allows)
    5. `docker compose --profile prod stop api` when done.
    Plus: without compose, a container reaches the dev database at `host.docker.internal:5433`, not
    `localhost`; `docker run --env-file` keeps quotes, so use compose or `-e`; `VITE_API_URL` has no
    trailing slash.
  - A "Settings" table: each variable, required or default, one line of purpose:
    the five parts (local and CI), `CRAGMATCH_POSTGRES_URL` (deployments only, wins over the five,
    either scheme, keep `?sslmode=require`; **if it is set in a developer's `.env`, the tests use
    `cragmatch_test` on that server**, AC 11), the two keys, `CRAGMATCH_CORS_ORIGINS`, the unprefixed
    `POSTGRES_*` (db container), and the container-only `PORT`, `FORWARDED_ALLOW_IPS`, `HF_HOME`,
    `PGSSLMODE`; `VITE_API_URL` for the web build. One sentence: a blank value counts as not set.
  - Project structure: `config.py` line becomes "Settings from the environment or backend/.env
    (CRAGMATCH_ prefix): DB URL or parts, API keys, CORS origins"; new lines `backend/Dockerfile`
    (API image: one worker on $PORT, non-root, Alembic included), `backend/.dockerignore`,
    `docker-compose.yml` (db; api under the prod profile), `web/src/vite-env.d.ts`; the `api/` line
    mentions `VITE_API_URL`.
- `CLAUDE.md`: not edited by the developer. Suggest to the user in the hand-off two lines they may
  add: Commands `docker compose --profile prod up -d api` (container on :8001), and the Trap
  "an unprefixed line in backend/.env other than POSTGRES_USER/PASSWORD/DB stops Settings".

**Reuses:** `settings.database_url` as the single URL builder (engine, PGVector,
`psycopg_conninfo()`, Alembic, scripts through `SessionLocal`); SQLAlchemy's `make_url` / `URL.create`
(already used in `agent/checkpointer.py`); pydantic-settings' own `env_ignore_empty`, `NoDecode`,
`hide_input_in_errors`; `fastapi run` from `fastapi[standard]` (reads `PORT`); the `client` and
`db_session` fixtures; `postgres.Dockerfile` and the `db` service unchanged; `apiRequest()` unchanged
(only `API_URL` moves).

**Tests:**

*`backend/tests/test_config.py` (new).* An autouse fixture deletes every `CRAGMATCH_*` variable with
`monkeypatch.delenv` (CI sets them); each test sets what it needs with `monkeypatch.setenv` and builds
`Settings(_env_file=None)`, so neither `backend/.env` nor CI's env leaks in. A small helper sets the two
dummy keys.
- `test_database_url_from_the_five_parts`: gives exactly `postgresql+psycopg://u:p@h:5433/d`
  (AC 3, unchanged behaviour).
- `test_special_characters_in_the_password_survive`: password `p@ss:w/rd%#?`; then
  `make_url(s.database_url).password == "p@ss:w/rd%#?"` and the host is still `h` (AC 3).
- `test_postgres_url_wins_and_keeps_ssl[postgres]` and `[postgresql]`, parametrized:
  `postgres://u:p@db.example:5432/app?sslmode=require` and the `postgresql://` form, with the five
  parts also set, both give `postgresql+psycopg://u:p@db.example:5432/app?sslmode=require` (AC 3, 4).
- `test_postgres_url_alone_is_enough`: only the URL and the keys; no error, the five parts are `None`
  (AC 3).
- `test_postgres_url_with_another_scheme_is_rejected`: `mysql://u:p@h/d` gives a `ValidationError`
  naming `CRAGMATCH_POSTGRES_URL` (AC 4).
- `test_missing_database_settings_are_named`: only `CRAGMATCH_POSTGRES_USER` set; the error mentions
  `CRAGMATCH_POSTGRES_URL` and `CRAGMATCH_POSTGRES_HOST` (AC 2).
- `test_missing_api_key_is_named`: no Anthropic key; the error mentions `anthropic_api_key` (AC 2).
- `test_blank_value_counts_as_missing`: `CRAGMATCH_VOYAGE_API_KEY=""` gives a `ValidationError` naming
  `voyage_api_key`, and a blank `CRAGMATCH_POSTGRES_URL=""` with the five parts set falls back to the
  parts (AC 2).
- `test_errors_never_show_secret_values`: password `hunter2-visible` and Anthropic key
  `sk-visible`, Voyage key missing; `str(exc)` contains `voyage_api_key` but neither value. Same for
  the database error (password set, host missing) (AC 2).
- `test_cors_origins_default_to_the_vite_dev_server`: `["http://localhost:5173"]` and
  `postgres_url is None` with only the required settings (AC 5, 10).
- `test_cors_origins_from_a_comma_list`: `" https://a.example , https://b.example/,"` gives
  `["https://a.example", "https://b.example"]` (AC 5).
- `test_tests_use_the_cragmatch_test_database(db_session)`: `db_session.get_bind().url.database ==
  "cragmatch_test"`, and host and port equal `make_url(settings.database_url)`'s (AC 10).

*`backend/tests/test_cors.py` (new),* with the `client` fixture on `/health`:
- `test_cors_allows_the_default_origin`: preflight `OPTIONS /health` with `Origin:
  http://localhost:5173` and `Access-Control-Request-Method: GET` answers 200 with
  `access-control-allow-origin: http://localhost:5173` (AC 5).
- `test_cors_refuses_an_unlisted_origin`: for `https://evil.example` the preflight answers 400, and a
  plain `GET /health` with that `Origin` answers 200 without an `access-control-allow-origin` header,
  so a browser cannot read it (AC 5).
- `test_cors_origins_come_from_settings`: the `CORSMiddleware` entry in `app.user_middleware` has
  `kwargs["allow_origins"] == settings.cors_origins`. The middleware is built at import, so a listed
  non-default origin is shown end to end by hand (check 4) (AC 5).

*`backend/tests/test_planner_checkpointer.py`:*
- `test_psycopg_conninfo_keeps_ssl_options`: `psycopg_conninfo("postgresql+psycopg://u:p@h:5432/db?sslmode=require")
  == "postgresql://u:p@h:5432/db?sslmode=require"`, so the planner's pool gets the same TLS demand
  (AC 3).

**Expected suite:** **219 passed**: 199 today, +0 (017), +0 (018), +3 (019), +0 (020), and 17 new here
(13 in `test_config.py`, counting the parametrized test twice; 3 in `test_cors.py`; 1 in
`test_planner_checkpointer.py`). If the count before 021 differs, it is that count plus 17.
`uv run ruff check .` clean; in `web/`, `npm run lint` and `npm run build` pass.

**Check by hand** (the user, Docker Desktop running; the dev server may keep running on 8000):
1. Image and migrations (AC 1, 7): `docker compose --profile prod build api`,
   `docker compose --profile prod run --rm api alembic upgrade head` (prints the current head, no
   error), `docker compose --profile prod up -d api`. `http://localhost:8001/health` shows
   `"database": "connected"` and `http://localhost:8001/docs` loads. Note the time from `up` to the
   first good `/health` and `docker image ls cragmatch-api` size for the hand-off.
2. What is in the image (AC 2):
   - `docker run --rm --entrypoint sh cragmatch-api:local -c "ls -a /app; id; env"` lists only
     `.venv alembic alembic.ini app`, the user is `cragmatch` (uid 10001), and the env has no key,
     password or URL.
   - `docker history --no-trunc cragmatch-api:local` shows no secret.
   - `docker run --rm -e CRAGMATCH_POSTGRES_PASSWORD=visible-check cragmatch-api:local` exits at once;
     the error names `anthropic_api_key`, `voyage_api_key` and `CRAGMATCH_POSTGRES_URL`, and does not
     show `visible-check`.
3. Port from the environment (platform-neutral): `docker compose --profile prod run --rm -e PORT=9000
   -p 9000:9000 api`, then `http://localhost:9000/health` answers; Ctrl+C.
4. Frontend and CORS (AC 5, 6), in `web/`:
   - Build with `$env:VITE_API_URL = "http://localhost:8001"`, `npm run build`,
     `Remove-Item Env:VITE_API_URL`. `Select-String -Path dist\assets\*.js -Pattern "localhost:8001"`
     finds it; `-Pattern "sk-ant-","CRAGMATCH_"` finds nothing.
   - `npm run preview`, open `http://localhost:4173`: a filter search works and the container log
     (`docker compose logs api`) shows the request.
   - Open the same preview as `http://127.0.0.1:4173` (an unlisted origin): the browser console shows a
     CORS error and the app shows "Can't reach the CragMatch server".
   - Build again without the variable: the bundle contains `localhost:8000`; `npm run dev` works as
     before against the dev server.
5. The "done" check (AC 8), on `http://localhost:4173` against the container: a filter search; create a
   group, add two members, group search with stays and booking links; one vibe search (the first one
   downloads the tokenizer inside the container, so it needs internet; Voyage allows 3 a minute); a
   natural-language search; a planner run on the group screen (019), answered to the end. All behave as
   in development. Then `docker stats --no-stream` and note the container's memory for the hand-off
   (024 and 025 need it), and `docker compose exec api ls /home/cragmatch/.cache/huggingface` shows the
   tokenizer.
6. One URL instead of the five parts (AC 3, 4), with the user's own values typed in the shell, never
   saved: `docker compose --profile prod run --rm -p 8002:8000 -e
   CRAGMATCH_POSTGRES_URL=postgres://USER:PASSWORD@db:5432/DBNAME?sslmode=disable api`, then
   `http://localhost:8002/health` connected and one planner start in its `/docs` works. Run again with
   `?sslmode=require`: `/health` fails with "server does not support SSL, but SSL was required" (the
   local database has no TLS), which proves the option reaches psycopg. And
   `docker compose --profile prod run --rm -e CRAGMATCH_POSTGRES_URL=postgresql://USER:wrong%25pw@db:5432/DBNAME
   api alembic current` fails with "password authentication failed", not "invalid interpolation
   syntax".
7. Unchanged local work (AC 10): `docker compose up -d` alone starts only `db`;
   `uv run fastapi dev app/main.py` and `npm run dev` work as before.

**Commit:** `Ticket 021: production-ready settings (optional CRAGMATCH_POSTGRES_URL that wins over the five parts and keeps sslmode, CORS origins from settings, blank values count as missing, errors never echo secret values, every setting in .env.example), passwords escaped in the URL and for Alembic, backend Dockerfile with one non-root worker on PORT and Alembic inside, run by a prod compose profile, build-time VITE_API_URL for web, README settings table and production-like run`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Manual check 1 (`/health` connected, `/docs` from the container) |
| 2 | `test_config.py::test_missing_database_settings_are_named`, `::test_missing_api_key_is_named`, `::test_blank_value_counts_as_missing`, `::test_errors_never_show_secret_values`; Dockerfile and `.dockerignore` review; manual check 2 |
| 3 | `test_config.py::test_database_url_from_the_five_parts`, `::test_special_characters_in_the_password_survive`, `::test_postgres_url_wins_and_keeps_ssl[*]`, `::test_postgres_url_alone_is_enough`; `test_planner_checkpointer.py::test_psycopg_conninfo_keeps_ssl_options`; review that the four call sites read `database_url`; manual check 6 (API, planner, Alembic) |
| 4 | `test_config.py::test_postgres_url_wins_and_keeps_ssl[postgres]` and `[postgresql]`, `::test_postgres_url_with_another_scheme_is_rejected`; manual check 6 |
| 5 | `test_cors.py` (3 tests); `test_config.py::test_cors_origins_from_a_comma_list`, `::test_cors_origins_default_to_the_vite_dev_server`; manual check 4 (listed and unlisted origin in a browser) |
| 6 | Manual check 4 (built with and without `VITE_API_URL`, no key in `dist/`); `npm run build` |
| 7 | Manual check 1 (`alembic upgrade head` from the image) and 6 (`alembic current`) |
| 8 | Manual check 5 |
| 9 | `.env.example` review (every field of `Settings` plus the db container's three, each with a comment) |
| 10 | `test_config.py::test_cors_origins_default_to_the_vite_dev_server`, `::test_tests_use_the_cragmatch_test_database`; the whole suite green with ci.yml unchanged; manual check 7 |
| 11 | README settings table (reviewer reads it); conftest comment |

No criterion is left uncovered. AC 1, 6, 7 and 8 can only be shown by hand (Docker and a browser).
For AC 5, a listed origin other than the default is shown by hand, because the middleware is built at
import. The vector store's use of `CRAGMATCH_POSTGRES_URL` is shown by review only (one line,
`rag/vectorstore.py:25`), since a vibe search in check 6 would spend a Voyage call for no new
information.

## Risks
- **`env_ignore_empty=True` changes start-up:** a blank value in the user's `backend/.env` now stops the
  start with "Field required" instead of failing on the first call. Intended (AC 2); if the dev server
  won't start after this commit, look there. CI sets non-empty dummies.
- **Escaping changes the URL string only for special characters:** for today's plain password the
  rendered URL is identical (the first config test pins it). Nothing stores the URL.
- **The test URL follows `database_url`:** `CRAGMATCH_POSTGRES_URL` in a developer's `.env` or shell
  (023 will set it on the laptop for the cloud load) makes the tests use `cragmatch_test` on that
  server. README says so; 023's plan must tell the user to unset it before `uv run pytest`.
- **Behaviour that must stay unchanged:** `docker compose up -d` starts only `db`; the dev frontend
  calls `localhost:8000`; CORS default 5173; the rate limits; every existing test passes with the new
  conftest URL.
- **No migration:** nothing to downgrade, no data touched. The image only runs the existing migrations.
- **External services:** no test touches the network (config and CORS tests are offline;
  `/health` uses the test DB). The manual vibe search costs one Voyage request (free tier 3 a minute)
  and downloads the tokenizer from huggingface.co once per container.
- **Windows and Docker:** compose on its own network avoids `host.docker.internal`; the image is built
  as `linux/amd64` on this machine.
- **Hooks:** the developer edits `.env.example` and `docker-compose.yml` with the Edit tool only and
  never names `.env` in a shell command; the user runs the compose commands.
- **Size:** about 12 files and 17 tests, no migration, mostly configuration. One delivery is fine.

## Seams left for 024 to 026 (AWS; nothing here decides them)
- **Port:** `fastapi run` reads `PORT` (App Runner and the Lambda Web Adapter default to 8080; Fargate
  takes any port).
- **Client address behind a load balancer:** proxy headers are on; trust is the uvicorn variable
  `FORWARDED_ALLOW_IPS` (default localhost). 025 sets it for its entry point and states the spoofing
  trade-off.
- **TLS to RDS:** either `CRAGMATCH_POSTGRES_URL=...?sslmode=require`, or the five parts from an
  RDS-managed secret's JSON keys plus `PGSSLMODE=require`. `verify-full` also needs the RDS CA bundle
  in the image and `PGSSLROOTCERT` (an added `COPY`/download line, 025's choice).
- **Secrets as environment variables:** the `CRAGMATCH_*` names are the contract for ECS `secrets`,
  App Runner or Lambda environment from Secrets Manager / SSM. Errors never echo them.
- **Writable paths:** `HF_HOME` (Lambda: only `/tmp` is writable, so `HF_HOME=/tmp/huggingface`, or bake
  the tokenizer into the image); `/app` is read-only for the app user, so `import_stays` stays on the
  laptop (023/025).
- **Migrations:** CMD is replaceable, so `alembic upgrade head` runs from the same image as an ECS
  one-off task or a workflow step. A Lambda runtime would need the Web Adapter extension copied into
  `/opt/extensions` and another way to migrate (025).
- **One process:** one worker per container; on Lambda, concurrency would create several
  environments, each with its own rate-limit memory (025 must cap it at 1 or rule Lambda out).
- **Architecture:** Graviton (`linux/arm64`) is cheaper on Fargate and Lambda; the base image and uv are
  multi-arch, and 025's workflow picks `--platform` (check that every locked wheel exists for arm64).
- **Health checks:** `/health` runs `SELECT 1` (fits a load balancer target check); `/` answers without
  the database (fits a readiness check that must not depend on the DB). No Docker `HEALTHCHECK`: ECS and
  App Runner use their own.
- **Logs:** unbuffered stdout, for the platform's log driver.
- **Numbers for 024/025:** image size, start-up time and memory during the done check, from manual
  checks 1 and 5, reported in the hand-off.

## Out of scope (copied from the ticket)
- The daily spending cap: ticket 022.
- Choosing a platform, accounts, infrastructure: tickets 023 to 026 (AWS).
- A Dockerfile for `web/`: it is deployed as static files, so a build is enough.
- Changing the per-IP rate limits: they stay as they are. How they behave behind a proxy or load
  balancer is a deployment matter (ticket 025).
- CI changes, unless the settings change forces them: it does not (checked above).
