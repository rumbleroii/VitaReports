from fastapi import FastAPI

from app.dependencies import get_settings
from app.routers import health

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(health.router)


@app.get("/")
def root() -> dict:
    return {"message": "VitaReports"}
