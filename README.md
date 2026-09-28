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
```

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
    main.py              FastAPI app: creates the app, adds CORS middleware,
                         mounts the routers below, defines / and /health.

    core/                App-wide setup, used by everything else.
      config.py          Settings loaded from backend/.env (CRAGMATCH_ prefix)
                         via pydantic-settings: DB credentials, Anthropic and
                         Voyage API keys. Exposes settings.database_url.
      database.py        SQLAlchemy engine, SessionLocal (session factory),
                         and Base (declarative base every model inherits).
      dependencies.py    get_db() — FastAPI dependency that yields a DB
                         session per request and always closes it after.

    models/              SQLAlchemy ORM models (database tables).
      crag.py            Crag table; one crag has many sectors.
      sector.py          Sector table and the ClimbingStyle enum, incl.
                         approach_notes and the pgvector embedding column.
      __init__.py        Re-exports every model, so `from app.models import
                         Crag, Sector` works and all tables register on Base.

    schemas/             Pydantic request/response shapes, decoupled from
                         the ORM models.
      crag.py            CragBase/Create/Read/Summary.
      sector.py          SectorBase/Create/Read.
      search.py          Natural-language search: request, ParsedFilters
                         (what Claude extracts), and the response.

    routers/             HTTP endpoints only; logic lives in services/.
      crags.py           /crags — list, get by id, create.
      sectors.py         /sectors — list, get by id, create, and
                         /sectors/search (filter by grade/style/distance).
      search.py          /search/natural — sends a free-text query to
                         Claude to extract filters, then runs the search.

    services/            Plain logic with no HTTP in it, reusable anywhere.
      grades.py          GRADE_ORDER plus grade_rank() and ranges_overlap().
      geo.py             haversine_km() — straight-line distance.
      search.py          find_matching_sectors() — shared filtering used by
                         both /sectors/search and /search/natural.
      embedding.py       Voyage client, EMBED_MODEL, and embed_query().

    scripts/             Run by hand, not part of the API.
      seed.py            Inserts sample Catalan crags/sectors.
      embed_sectors.py   Writes approach notes and stores a Voyage
                         embedding for every sector.

  tests/
    test_crags_api.py, test_sectors_api.py — API tests using the
                         conftest.py fixtures (isolated test DB + TestClient).
    test_geo.py, test_grades.py — unit tests for services/geo.py and
                         services/grades.py.

  conftest.py            Pytest fixtures: an isolated cragmatch_test
                         database (with pgvector), a fresh db_session per
                         test, and a client fixture that overrides get_db.

  alembic/               Migration scripts (alembic upgrade head applies
                         them). Needed whenever a model's shape changes.

postgres.Dockerfile      Postgres image = postgis/postgis + pgvector.

frontend/
  src/
    main.tsx             Entry point — mounts <App /> into the DOM.
    App.tsx              The whole UI so far: the structured search form,
                         the natural-language search box, sorting, and the
                         results list.
    SectorCard.tsx       Renders a single sector (name, crag, region,
                         style, grade range) as a list item.
    types.ts             Shared frontend TypeScript types (Sector,
                         ParsedFilters) — the TS-side mirror of the
                         backend's Pydantic schemas.
```
