from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.routers import crags, sectors
from app.dependencies import get_db




app = FastAPI(
    title="CragMatch API",
    description=(
        "Find climbing crags and sectors that match a group's grade "
        "range, style, and travel distance from a starting point."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crags.router, prefix="/crags", tags=["crags"])
app.include_router(sectors.router, prefix="/sectors", tags=["sectors"])

@app.get("/")
def root():
    return {"message": "Welcome to CragMatch API"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
