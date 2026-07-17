from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.dependencies import get_settings
from app.routers import health, manual_entries, profile

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(profile.router)
app.include_router(manual_entries.router)


@app.get("/")
def root() -> dict:
    return {"message": "VitaReports"}
