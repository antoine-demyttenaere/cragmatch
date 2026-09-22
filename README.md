## Running locally

### Prerequisites
- Docker Desktop
- Python 3.12+, [uv](https://docs.astral.sh/uv/)
- Node 20+

### 1. Database
​```
docker compose up -d
​```

### 2. Backend
​```
cd backend
uv run alembic upgrade head   # first time only, or after a new migration
uv run fastapi dev app/main.py
​```
Runs at http://localhost:8000 — docs at /docs.

### 3. Frontend
​```
cd frontend
npm install                    # first time only
npm run dev
​```
Runs at http://localhost:5173.

### Running tests
​```
cd backend
uv run pytest
​```

## Project structure

```
backend/
  app/
    main.py             FastAPI app: creates the app, adds CORS middleware,
                         mounts the routers below, defines / and /health.

    config.py           Settings loaded from backend/.env (CRAGMATCH_ prefix)
                         via pydantic-settings, incl. DB credentials and
                         ANTHROPIC_API_KEY. Exposes settings.database_url.

    database.py         SQLAlchemy engine, SessionLocal (session factory),
                         and Base (declarative base every model inherits).

    dependencies.py     get_db() — FastAPI dependency that yields a DB
                         session per request and always closes it after.

    models.py           SQLAlchemy ORM models: ClimbingStyle (enum) and the
                         Crag / Sector tables, with the crag<->sectors
                         relationship (one crag has many sectors).

    grades.py           GRADE_ORDER (French grades, easiest to hardest) plus
                         grade_rank() and ranges_overlap(), used to match a
                         sector's grade range against a search range.

    geo.py               haversine_km() — straight-line distance between
                         two lat/lon points, used for the distance filter.

    search.py            find_matching_sectors() — the shared filtering
                         logic (grade range, style, distance) used by both
                         the plain search endpoint and the natural one.

    seed.py               One-off script that inserts a handful of real
                         Catalan crags/sectors (Siurana, Margalef, ...) for
                         local testing.
    routers/
      crags.py           /crags — list, get by id, create.
      sectors.py         /sectors — list, get by id, create, and
                         /sectors/search — the main filter-by-grade/
                         style/distance endpoint used by the frontend form.

      natural_search.py  /search/natural — sends a free-text query to
                         Claude (Anthropic API) to extract grade/style/
                         distance filters, then calls find_matching_sectors().

    schemas/
      crag.py            Pydantic schemas for Crag: CragBase/Create/Read/
                         Summary — request/response shapes, decoupled from
                         the ORM model.

      sector.py          Same pattern for Sector: SectorBase/Create/Read.

  tests/
    test_crags_api.py, test_sectors_api.py — API tests using the
                         conftest.py fixtures (isolated test DB + TestClient).

    test_geo.py, test_grades.py — unit tests for the pure-logic helpers in
                         geo.py / grades.py.

  conftest.py           Pytest fixtures: an isolated cragmatch_test
                         database, a fresh db_session per test, and a
                         client fixture that overrides get_db so API tests
                         hit that DB instead of the real one.

  alembic/               Migration scripts (alembic upgrade head applies
                         them). Needed whenever models.py's shape changes.

frontend/
  src/
    main.tsx            Entry point — mounts <App /> into the DOM.
    App.tsx              The whole UI so far: search form (grade/style/
                         distance), calls /sectors/search, sorts and
                         renders results via SectorCard.

    SectorCard.tsx       Renders a single sector (name, crag, region,
                         style, grade range) as a list item.
                         
    types.ts             Shared frontend TypeScript types (Sector, incl.
                         its nested crag summary) — the TS-side mirror of
                         the backend's Pydantic schemas.
```
