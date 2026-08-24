from fastapi import FastAPI

from app.api.alerts import router as alerts_router
from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.query import router as query_router

app = FastAPI(
    title="MikroTik VPN Monitor",
    version="0.1.0",
    description="Collects and exposes MikroTik VPN session telemetry.",
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
