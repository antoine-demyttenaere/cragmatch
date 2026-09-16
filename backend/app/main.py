from fastapi import FastAPI
from app.routers import gyms

app = FastAPI(
    title="Climbing Log API",
    version="0.1.0"
)

app.include_router(gyms.router, prefix="/gyms", tags=["gyms"])

@app.get("/health")
def health_check():
    return {"status": "ok"}