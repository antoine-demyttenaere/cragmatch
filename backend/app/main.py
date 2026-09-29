from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.routers import crags, groups, search, sectors

import logging

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


app = FastAPI(
    title="CragMatch API",
    description=(
        "Find climbing crags and sectors that match a group's grade "
        "range, style, and travel distance from a starting point."
    ),
    version="0.1.0",
)


app.state.limiter = limiter
# Turns a RateLimitExceeded exception into a proper 429 response.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crags.router, prefix="/crags", tags=["crags"])
app.include_router(sectors.router, prefix="/sectors", tags=["sectors"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(groups.router, prefix="/groups", tags=["groups"])


@app.get("/")
def root():
    return {"message": "Welcome to CragMatch API"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
