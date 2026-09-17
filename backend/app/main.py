from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.routers import crags, sectors
from app.dependencies import get_db


app = FastAPI(
    title="CragMatch API",
    version="0.1.0"
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
