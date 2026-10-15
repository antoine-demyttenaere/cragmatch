## Running locally

### Prerequisites
- Docker Desktop
- Python 3.12+, [uv](https://docs.astral.sh/uv/)
- Node 20+

### 1. Database
```
docker compose up -d
```

### 2. Backend
```
cd backend
uv run alembic upgrade head   # first time only, or after a new migration
uv run fastapi dev app/main.py
```
Runs at http://localhost:8000 — docs at /docs.

First time only, fill the database with sample data:
```
uv run python -m app.scripts.load_data        # all five steps below, in order; safe to re-run
uv run python -m app.scripts.seed             # crags + sectors
uv run python -m app.scripts.seed_notes       # approach notes (no API calls)
uv run python -m app.scripts.index_sectors_langchain   # LangChain PGVector index, used by /search/similar
                                                       # (needs the approach notes from seed_notes; 1 Voyage request)
uv run python -m app.scripts.seed_stays       # hand-picked stays (run before the import)
uv run python -m app.scripts.import_stays     # campsites/hostels/huts from OpenStreetMap
```
The trip planner API needs `alembic upgrade head` for the `planner_runs` table. LangGraph's
own checkpoint tables are created by the library on the first planner request, not by Alembic.

Daily spending cap: today's estimated spend on Claude and Voyage is in `daily_spend`
(`docker compose exec db psql -U <user> -d <db> -c "select * from daily_spend"`). Deleting
today's row resets it. After pulling this change, run `uv run alembic upgrade head`, otherwise the
first AI search fails with "UndefinedTable".

`import_stays` calls the free public Overpass API, which is often busy. If a
crag fails, just run it again later: finished crags come from the cache in
`backend/.cache/overpass/` (kept a week; `--no-cache` forces fresh data).

**Loading into another database.** `load_data` uses the same database settings as the app,
so set them in a new PowerShell window: `CRAGMATCH_POSTGRES_URL`, or the five
`CRAGMATCH_POSTGRES_*` parts (see Settings). It prints `host:port/name` and asks before
writing; `--yes` skips the question and is for runs nobody watches. The load makes 1 Voyage
request (the free tier allows 3 a minute), so wait a minute before a vibe search.
**Never run `uv run pytest` in that window**: `conftest.py` builds the test URL from the same
settings. Afterwards run `Remove-Item Env:CRAGMATCH_POSTGRES_URL` (or the variables you set),
or close the window.

### 3. Frontend
```
cd web
npm install                    # first time only
npm run dev
```
Runs at http://localhost:5173.

### Running tests
```
cd backend
uv run pytest

cd ../web
npm test
```

### Checks (same as CI)
```
cd backend
uv run pytest
uv run ruff check .

cd ../web
npm run lint
npm test
```

On every push and pull request, GitHub Actions runs three jobs: Backend tests, Ruff and
ESLint (lint and Vitest unit tests for web/). The tests run against the image built from `postgres.Dockerfile` with dummy settings
and outbound HTTP blocked, so no real key is used or needed. Dependencies come from `uv.lock`
and `package-lock.json`, so a stale lockfile fails the run. The checks are visible on GitHub
but do not block merging.

### Settings

Set in the environment or in `backend/.env` (see `backend/.env.example`). A blank value counts as
not set.

| Variable | Required / default | Purpose |
|---|---|---|
| `CRAGMATCH_POSTGRES_USER`, `_PASSWORD`, `_DB`, `_HOST`, `_PORT` | all five, unless `CRAGMATCH_POSTGRES_URL` is set | Database connection, used locally and in CI. |
| `CRAGMATCH_POSTGRES_URL` | optional, deployments only | One URL instead of the five parts; it wins over them. `postgres://` and `postgresql://` both work; keep `?sslmode=require`. **If it is set in a developer's `.env`, the tests use `cragmatch_test` on that server.** |
| `CRAGMATCH_ANTHROPIC_API_KEY`, `CRAGMATCH_VOYAGE_API_KEY` | required | Claude and Voyage keys. |
| `CRAGMATCH_CORS_ORIGINS` | `http://localhost:5173` | Allowed browser origins, comma-separated. |
| `CRAGMATCH_CLAUDE_DAILY_CAP_USD` | `0.1` | Claude's estimated spend allowed per day, in USD. 0 switches Claude off. |
| `CRAGMATCH_VOYAGE_DAILY_CAP_USD` | `0.05` | Voyage's estimated spend allowed per day, in USD. 0 switches Voyage off. |
| `CRAGMATCH_CLAUDE_INPUT_USD_PER_MTOK` | `3.0` | Claude input price, USD per million tokens. |
| `CRAGMATCH_CLAUDE_OUTPUT_USD_PER_MTOK` | `15.0` | Claude output price, USD per million tokens (thinking tokens count). |
| `CRAGMATCH_VOYAGE_USD_PER_MTOK` | `0.06` | Voyage price, USD per million tokens; applied to the query's UTF-8 bytes. |
| `CRAGMATCH_SPENDING_TIMEZONE` | `Europe/Madrid` | IANA time zone; the spending day starts at midnight there. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | for the `db` container | Read only by the database container. |
| `PORT` | `8000` | Container only: port the API listens on. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,::1` | Container only: proxies whose client address headers are trusted. |
| `HF_HOME` | `/home/cragmatch/.cache/huggingface` | Container only: where the Voyage tokenizer is downloaded; must be writable. |
| `PGSSLMODE` | unset | Container only: TLS mode for the database connection when the URL has no `sslmode`. |
| `VITE_API_URL` | `http://localhost:8000` | Web build only: the API address baked into the bundle (no trailing slash). |

The caps are estimates in USD, not an invoice (check the prices against the providers' price
lists). A reached cap answers 503 with its own message.

### Production-like run on this machine

The backend image runs next to the dev database through the `prod` compose profile (PowerShell):
```
docker compose --profile prod build api
docker compose --profile prod run --rm api alembic upgrade head
docker compose --profile prod up -d api
```
Then open http://localhost:8001/health and http://localhost:8001/docs. For the frontend:
```
cd web
$env:VITE_API_URL = "http://localhost:8001"
npm run build
Remove-Item Env:VITE_API_URL
npm run preview
```
The preview serves on http://localhost:4173, which the service allows. Stop the container with
`docker compose --profile prod stop api`.

Without compose, a container reaches the dev database at `host.docker.internal:5433`, not
`localhost`. `docker run --env-file` keeps the quotes of `KEY=""` lines, so use compose or `-e`.

## Project structure

```
.github/workflows/ci.yml  CI on every push and pull request: backend tests, ruff,
                         ESLint and Vitest (web/).
docker-compose.yml       The db service; the api service under the prod profile.
backend/
  Dockerfile             API image: one worker on $PORT, non-root, Alembic included.
  .dockerignore          Keeps .env, caches and tests out of the image.
  app/
    main.py              FastAPI app: CORS, rate limiter, mounts the routers,
                         defines / and /health.

    core/                App-wide setup, used by everything else.
      config.py          Settings from the environment or backend/.env
                         (CRAGMATCH_ prefix): DB URL or parts, API keys, CORS origins,
                         daily caps, prices and time zone.
      database.py        SQLAlchemy engine, SessionLocal, and Base.
      dependencies.py    get_db(): one DB session per request, always closed.
      rate_limit.py      slowapi Limiter (per IP), used on the paid endpoints.

    models/              SQLAlchemy ORM models (database tables).
      crag.py            Crag; one crag has many sectors.
      sector.py          Sector + ClimbingStyle, approach_notes, approach_minutes.
      group.py           Group (name, unique share_code); has many members.
      member.py          Member of a group, with optional preferences
                         (grade range, max distance, max walk-in minutes, styles; empty = any).
      stay.py            Stay (campsite/hostel/refuge/...), StayType, StaySource.
      planner_run.py     PlannerRun: one trip planner run of a group (id = LangGraph thread id, creation time, node trace).
      daily_spend.py     DailySpend: estimated spend per day and provider.
      __init__.py        Re-exports every model so all tables register on Base.

    schemas/             Pydantic request/response shapes, decoupled from models.
      crag.py, sector.py Crag/Sector create + read shapes (Sector has approach_minutes).
      search.py          Natural-language and similarity search shapes.
      group.py           Members (with grade validators), groups, and the
                         group search response (fits / misfits per sector).
      stay.py            Stays, nearby stays, booking links.
      planner.py         Trip planner runs: start body, answer body (names the proposal it answers), run status/proposal/plan/trace, graph structure.

    routers/             HTTP endpoints only; logic lives in services/.
      crags.py           /crags: list, get, create.
      sectors.py         /sectors: CRUD, /sectors/search, /sectors/{id}/stays.
      search.py          /search/natural (LangChain structured output) and /search/similar (LangChain PGVector + reasons chain),
                         both rate-limited.
      groups.py          /groups: create, read, add/replace/remove members,
                         /groups/{code}/search, and group-aware stays.
      planner.py         Trip planner over HTTP: /groups/{code}/planner/runs (start, latest, read, answer; a stale answer gets 409)
                         and /planner/graph; get_trip_planner builds the graph on a Postgres checkpointer.

    services/            Plain logic with no HTTP in it, reusable anywhere.
      grades.py          GRADE_ORDER, grade_rank(), ranges_overlap().
      geo.py             haversine_km() and the BARCELONA origin.
      search.py          find_matching_sectors(): the Stage 1 filter logic.
      llm.py             LLM_MODEL + log_tokens(): Claude model name and token usage log line, used by app/rag/.
      natural_search.py  /search/natural logic: Claude's filters (parse chain), then find_matching_sectors().
      similar_search.py  /search/similar logic: PGVector scores, sectors in rank order, reasons chain.
      embedding.py       EMBED_MODEL (voyage-3.5), used by app/rag/vectorstore.py.
      groups.py          find_group() (by share code), generate_share_code() (secrets, readable alphabet).
      group_matching.py  PURE (no DB): merge_preferences() for strict mode,
                         score_sectors() for scored mode.
      group_search.py    Group search: fetches sectors, calls the pure logic.
      stays.py           find_stays_near() (bounding box + haversine),
                         Airbnb / Booking.com prefilled search links.
      overpass.py        OpenStreetMap: query, fetch (timeout, retries,
                         fallback server, cache), parse, duplicate detection.
      trip_planner.py    Trip planner run logic shared by the router and the script: advance(), start_run(),
                         answer_run(), run_view(), graph_structure().
      spending.py        The daily cap: ensure_under_cap() before, record_spend() after every
                         paid call.

    rag/                 Stage 6 LangChain code.
      loader.py          SectorLoader + build_text(): sectors as LangChain Documents.
      vectorstore.py     Voyage embeddings + PGVector store, collection "sectors"
                         (built once per process, cosine distance).
      llm.py             get_chat_model(): ChatAnthropic (timeout, retries);
                         UsageLogger callback (token usage);
                         TokenCounter (one request's Claude tokens, for the cap).
      chain.py           RAG prompt, format_docs(), build_rag_chain().
      reasons.py         Per-sector match reasons: prompt, MatchReasons, build_reasons_chain(), get_reasons_chain().
      query_parsing.py   Natural-language query to ParsedFilters: parse prompt, build_parse_chain(), get_parse_chain().

    agent/               Stage 6 LangGraph trip planner.
      state.py           TripState (what flows through the trip planner), PlannerContext (db session), initial_state()
      nodes.py           One function per trip-planner step; each calls an existing service.
      graph.py           build_trip_planner(): nodes, edges, the "no common ground" branch; pauses at approve_sector (interrupt; the checkpointer is passed in: PostgresSaver in the app, InMemorySaver in tests).
      checkpointer.py    open_postgres_saver(): PostgresSaver on a connection pool (paused runs survive a restart), psycopg_conninfo().

    scripts/             Run by hand, not part of the API.
      index_sectors_langchain.py  Index sectors into the LangChain PGVector store.
      rag_playground.py  Stage 6 steps 6.2, 6.4, 6.5, then the trip planner steps from 6.8 on (6.9a to 6.9c add the nodes, 6.10 the routed graph),
                         one function per step; a step can take an argument (`... 6.8 SHARECODE`).
      load_data.py       Runs seed, seed_notes, index_sectors_langchain, seed_stays, import_stays in order; shows the target first; safe to re-run.
      seed.py            Sample Catalan crags/sectors; skips what is already there.
      trip_planner.py    Run the Stage 6 trip planner on a group in the terminal (trace, approval, final plan).
      seed_notes.py      Illustrative approach notes per sector, only on the sample sectors (run before indexing).
      seed_stays.py      Small hand-picked list of stays (illustrative).
      import_stays.py    Stays around every crag from OpenStreetMap.

  tests/                 pytest. External services (Claude, Voyage, Overpass)
                         are always mocked, so tests never use the network.
    conftest.py          Factories for groups, sectors and stays (trip planner tests).
  conftest.py            Isolated cragmatch_test database, a fresh session per
                         test, TestClient with get_db overridden, limiter off.
  alembic/               Migrations (alembic upgrade head applies them).

postgres.Dockerfile      Postgres image = postgis/postgis + pgvector.

web/src/                 The app (design system, search, groups, stays, trip planner).
  main.tsx               Entry point: font, tokens and base styles, then App.
  styles/                tokens.css (colours, type, spacing; light and dark) and base.css.
  vite-env.d.ts          Types VITE_API_URL for import.meta.env.
  api/                   client.ts (API_URL from VITE_API_URL, apiRequest, ApiError) and types.ts (mirrors the backend schemas).
  constants.ts           Grades (same order as the backend), styles, stay types, labels.
  components/            UI kit, each with a CSS Module: Button, Field, Chip, Card,
                         SegmentedControl, StateMessage, Sheet, Icon.
  app/                   App shell: header, navigation, light/dark layout.
  features/search/       Search page with three modes (filters, describe it, vibe), sector cards,
                         sectorLabels.ts (walk-in and distance strings).
  features/stays/        Stays panel for one sector; in a group, dates, guests and
                         Airbnb / Booking.com links; shared TripFields, StayList,
                         TripLinks (also used by the planner).
  features/group/        Group trip: create, join or reopen a group, share link,
                         members, scored and strict group search.
  features/planner/      Plan the trip on the group page: start a run with dates, nights
                         and guests, the proposed sector with approve or not this one, the
                         plan with stays and booking links, the no-plan outcomes; resumes
                         the group's latest run; live diagram of the planner graph
                         (dagre layout, own SVG), step list in plain words with details,
                         skip and replay; *.test.ts Vitest tests for the pure helpers,
                         planner.fixtures.ts test data.
```

## Where the stay data comes from

There's no legitimate way to *search* Airbnb or Booking.com from our backend:
Airbnb has no public search API (and scraping breaks its terms), and
Booking.com's API is limited to approved partners. So the app combines:

| Source | Good | Limits |
|---|---|---|
| Hand-picked list (`seed_stays.py`) | Best quality: places climbers actually use | Small, maintained by hand. The current entries are illustrative placeholders |
| OpenStreetMap via Overpass (`import_stays.py`) | Free, legal to reuse, real campsites/hostels/huts with coordinates | Messy (missing names, odd tags), no prices or availability, public servers are often busy |
| Airbnb / Booking.com links | Real availability and prices, on their own site | We only prefill a search (area, dates, guests); the user finishes there. The URL parameters aren't a documented API, so check the links now and then |
