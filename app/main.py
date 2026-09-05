from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

from app.db.database import engine, Base
from app.db.models import RoadSegment, SegmentFeature, SegmentRisk, HistoricalIncident  # noqa: F401
from app.api.segments import router as segments_router
from app.api.features import router as features_router
from app.api.reports import router as reports_router
from app.api.ml import router as ml_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure PostGIS extension and tables exist on startup
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Road Risk & Accessibility System — Backend Prototype",
    description="GIS Road Risk & Accessibility backend with feature vectors, Open-Meteo weather sync, field reporting, & ML prediction pipeline for North Eastern Region (NER) of India",
    version="0.4.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


app.include_router(segments_router, prefix="/api/v1")
app.include_router(features_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(ml_router, prefix="/api/v1")
