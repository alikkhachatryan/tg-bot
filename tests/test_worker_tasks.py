from app.workers.tasks import scheduler_heartbeat, worker_healthcheck


async def test_worker_healthcheck() -> None:
    assert await worker_healthcheck({}) == "ok"


async def test_scheduler_heartbeat() -> None:
    assert await scheduler_heartbeat({}) == "ok"
