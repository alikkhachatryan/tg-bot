from app.services.health import HealthService


class FakeConnection:
    async def execute(self, statement: object) -> None:
        del statement


class FakeConnectContext:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def __aenter__(self) -> FakeConnection:
        if self._fail:
            raise ConnectionError("database unavailable")
        return FakeConnection()

    async def __aexit__(self, *args: object) -> None:
        del args


class FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def connect(self) -> FakeConnectContext:
        return FakeConnectContext(fail=self._fail)


class FakeRedis:
    def __init__(self, *, ready: bool = True) -> None:
        self._ready = ready

    async def ping(self) -> bool:
        if not self._ready:
            raise ConnectionError("redis unavailable")
        return True


async def test_readiness_checks_both_dependencies() -> None:
    service = HealthService(
        engine=FakeEngine(),  # type: ignore[arg-type]
        redis=FakeRedis(),  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    assert await service.readiness() == {"postgres": True, "redis": True}


async def test_readiness_contains_failures() -> None:
    service = HealthService(
        engine=FakeEngine(fail=True),  # type: ignore[arg-type]
        redis=FakeRedis(ready=False),  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    assert await service.readiness() == {"postgres": False, "redis": False}
