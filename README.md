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
uv run python -m app.scripts.seed             # crags + sectors
uv run python -m app.scripts.embed_sectors    # approach notes + Voyage embeddings
uv run python -m app.scripts.index_sectors_langchain   # LangChain PGVector index, used by /search/similar
                                                       # (needs the approach notes from embed_sectors; 1 Voyage request)
uv run python -m app.scripts.seed_stays       # hand-picked stays (run before the import)
uv run python -m app.scripts.import_stays     # campsites/hostels/huts from OpenStreetMap
```
`import_stays` calls the free public Overpass API, which is often busy. If a
crag fails, just run it again later: finished crags come from the cache in
`backend/.cache/overpass/` (kept a week; `--no-cache` forces fresh data).

### 3. Frontend
```
cd frontend
npm install                    # first time only
npm run dev
```
Runs at http://localhost:5173.

### Running tests
```
cd backend
uv run pytest
```

## Project structure

```
backend/
  app/
    main.py              FastAPI app: CORS, rate limiter, mounts the routers,
                         defines / and /health.

    core/                App-wide setup, used by everything else.
      config.py          Settings from backend/.env (CRAGMATCH_ prefix): DB
                         credentials, Anthropic and Voyage API keys.
      database.py        SQLAlchemy engine, SessionLocal, and Base.
      dependencies.py    get_db(): one DB session per request, always closed.
      rate_limit.py      slowapi Limiter (per IP), used on the paid endpoints.

    models/              SQLAlchemy ORM models (database tables).
      crag.py            Crag; one crag has many sectors.
      sector.py          Sector + ClimbingStyle, approach_notes, approach_minutes,
                         pgvector embedding.
      group.py           Group (name, unique share_code); has many members.
      member.py          Member of a group, with optional preferences
                         (grade range, max distance, max walk-in minutes, styles; empty = any).
      stay.py            Stay (campsite/hostel/refuge/...), StayType, StaySource.
      __init__.py        Re-exports every model so all tables register on Base.

    schemas/             Pydantic request/response shapes, decoupled from models.
      crag.py, sector.py Crag/Sector create + read shapes (Sector has approach_minutes).
      search.py          Natural-language and similarity search shapes.
      group.py           Members (with grade validators), groups, and the
                         group search response (fits / misfits per sector).
      stay.py            Stays, nearby stays, booking links.

    routers/             HTTP endpoints only; logic lives in services/.
      crags.py           /crags: list, get, create.
      sectors.py         /sectors: CRUD, /sectors/search, /sectors/{id}/stays.
      search.py          /search/natural (Claude) and /search/similar (LangChain PGVector + reasons chain),
                         both rate-limited.
      groups.py          /groups: create, read, add/replace/remove members,
                         /groups/{code}/search, and group-aware stays.

    services/            Plain logic with no HTTP in it, reusable anywhere.
      grades.py          GRADE_ORDER, grade_rank(), ranges_overlap().
      geo.py             haversine_km() and the BARCELONA origin.
      search.py          find_matching_sectors(): the Stage 1 filter logic.
      llm.py             Anthropic client (timeout/retries) + token usage logging.
      similar_search.py  /search/similar logic: PGVector scores, sectors in rank order, reasons chain.
      embedding.py       Voyage client + embed_query().
      groups.py          generate_share_code() (secrets, readable alphabet).
      group_matching.py  PURE (no DB): merge_preferences() for strict mode,
                         score_sectors() for scored mode.
      group_search.py    Group search: fetches sectors, calls the pure logic.
      stays.py           find_stays_near() (bounding box + haversine),
                         Airbnb / Booking.com prefilled search links.
      overpass.py        OpenStreetMap: query, fetch (timeout, retries,
                         fallback server, cache), parse, duplicate detection.

    rag/                 Stage 6 LangChain code.
      loader.py          SectorLoader: sectors as LangChain Documents.
      vectorstore.py     Voyage embeddings + PGVector store, collection "sectors"
                         (built once per process, cosine distance).
      llm.py             get_chat_model(): ChatAnthropic with the Stage 3 settings.
      chain.py           RAG prompt, format_docs(), build_rag_chain().
      reasons.py         Per-sector match reasons: prompt, MatchReasons, build_reasons_chain(), get_reasons_chain().

    scripts/             Run by hand, not part of the API.
      index_sectors_langchain.py  Index sectors into the LangChain PGVector store.
      rag_playground.py  Stage 6 steps, one function per step.
      seed.py            Sample Catalan crags/sectors.
      embed_sectors.py   Approach notes + a Voyage embedding per sector.
      seed_stays.py      Small hand-picked list of stays (illustrative).
      import_stays.py    Stays around every crag from OpenStreetMap.

  tests/                 pytest. External services (Claude, Voyage, Overpass)
                         are always mocked, so tests never use the network.
  conftest.py            Isolated cragmatch_test database, a fresh session per
                         test, TestClient with get_db overridden, limiter off.
  alembic/               Migrations (alembic upgrade head applies them).

postgres.Dockerfile      Postgres image = postgis/postgis + pgvector.

frontend/src/
  main.tsx               Entry point.
  App.tsx                Two tabs, "Find crags" and "Group trip"; keeps
                         ?group=CODE in the URL so the link can be shared.
  SearchPage.tsx         Filter search, natural-language search, vibe search.
  GroupPage.tsx          Create/join a group, members, strict/scored search
                         showing who each sector fits and why not.
  MemberForm.tsx         Add or edit a member's preferences.
  StaysPanel.tsx         Stays near a sector; in a group, dates/guests and
                         Airbnb / Booking.com links.
  SectorCard.tsx         One sector in a result list.
  api.ts                 apiRequest() + readable error messages.
  constants.ts           Grades (same order as the backend), styles, stay types.
  types.ts               TypeScript mirrors of the backend's schemas.
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
