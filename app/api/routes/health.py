from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.services.health import HealthService

router = APIRouter(tags=["operations"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def ready(request: Request) -> JSONResponse:
    service: HealthService = request.app.state.health_service
    checks = await service.readiness()
    is_ready = all(checks.values())
    payload: dict[str, Any] = {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
    }
    return JSONResponse(
        payload,
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
