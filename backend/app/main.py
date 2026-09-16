from fastapi import FastAPI
from app.routers import gyms

app = FastAPI(
    title="CragMatch API",
    version="0.1.0"
)

app.include_router(crags.router, prefix="/crags", tags=["crags"])

@app.get("/health")
def health_check():
    return {"status": "ok"}