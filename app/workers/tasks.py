from typing import Any


async def worker_healthcheck(ctx: dict[str, Any]) -> str:
    """Small task used by deployment health checks and queue smoke tests."""

    return "ok"


async def scheduler_heartbeat(ctx: dict[str, Any]) -> str:
    """Placeholder periodic task; domain schedules are added with their owning stage."""

    return "ok"
