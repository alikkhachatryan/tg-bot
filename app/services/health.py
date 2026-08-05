import asyncio

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class HealthService:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        redis: Redis,
        timeout_seconds: float,
    ) -> None:
        self._engine = engine
        self._redis = redis
        self._timeout_seconds = timeout_seconds

    async def readiness(self) -> dict[str, bool]:
        database_ok, redis_ok = await asyncio.gather(
            self._database_ready(),
            self._redis_ready(),
        )
        return {"postgres": database_ok, "redis": redis_ok}

    async def _database_ready(self) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def _redis_ready(self) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return bool(await self._redis.ping())
        except Exception:
            return False
