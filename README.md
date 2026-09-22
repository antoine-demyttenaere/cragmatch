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
