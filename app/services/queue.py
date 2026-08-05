import asyncio
from typing import Protocol
from uuid import UUID

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class ResumeQueue(Protocol):
    async def enqueue(self, resume_id: UUID) -> None: ...


class ArqResumeQueue:
    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._redis: ArqRedis | None = None
        self._lock = asyncio.Lock()

    async def _pool(self) -> ArqRedis:
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    self._redis = await create_pool(self._settings)
        return self._redis

    async def enqueue(self, resume_id: UUID) -> None:
        redis = await self._pool()
        job = await redis.enqueue_job("process_resume", str(resume_id), _job_id=str(resume_id))
        if job is None:
            raise RuntimeError("Resume job could not be enqueued")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
