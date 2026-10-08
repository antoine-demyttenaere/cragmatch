# 013: Stage 7, cloud deployment (to be reworked)

**Status:** Needs answers
**Size:** L (to be split once the plan is written)
**Mode:** to decide with the user.
**Raw request:** "7 cloud deployment (to be reworked)."

## User story
As a group of friends, I want CragMatch reachable on the internet, so that we can use the
shared group link without anyone running it on a laptop.

## What exists today
- Backend: FastAPI and uv, settings from `backend/.env` (`CRAGMATCH_` prefix). Secrets are
  needed for Postgres, Anthropic and Voyage.
- Database: Postgres 17 with PostGIS **and** pgvector (custom image, `postgres.Dockerfile`).
  Alembic migrations. Seed and import scripts are run by hand.
- Frontend: a Vite build, with `API_URL` in `api.ts` (currently pointing at localhost).
- CORS is allowed for `localhost:5173` only. slowapi rate limits are per IP and kept in
  memory.
- No Dockerfile for the backend or frontend. No CI.
- After Stage 6: an agent with a checkpointer (in memory) that may need to persist between
  requests.

## Open questions
- [blocking] The rework itself: what should Stage 7 cover? (suggested default:
  containerize the backend, a managed Postgres that supports PostGIS and pgvector, the
  frontend on static hosting, secrets in the platform's secret store, migrations at
  deploy time, a CI that runs pytest, ruff and lint.)
- [blocking] Which cloud or platform, and what monthly budget?
- [blocking] Who can use it: just your friends via share codes (as today, no login), or
  public? This decides whether rate limits and paid-API cost caps are enough.
- [non-blocking] Should the trip planner (Stage 6) get an API endpoint and a persistent
  checkpointer as part of Stage 7? (suggested default: yes, see ticket 011.)

## Notes for the tech lead
- Check that the chosen managed Postgres offers both `postgis` and `vector` extensions
  before choosing it.
- In-memory rate limiting doesn't work with more than one instance. Decide on one instance
  or a shared store.
