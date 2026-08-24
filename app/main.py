from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(
    title="MikroTik VPN Monitor",
    version="0.1.0",
    description="Collects and exposes MikroTik VPN session telemetry.",
)

app.include_router(health_router, prefix="/api/v1")
