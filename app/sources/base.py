import asyncio
from typing import Any, Protocol

import httpx

from app.sources.schemas import VacancyRecord


class VacancySourceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VacancySource(Protocol):
    name: str

    async def fetch(self) -> list[VacancyRecord]: ...

    async def close(self) -> None: ...


class HttpVacancySource:
    name: str

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._headers = headers
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds, headers=headers
        )

    async def _get_json(
        self, path: str, *, params: dict[str, Any] | list[tuple[str, Any]] | None = None
    ) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(path, params=params, headers=self._headers)
            except httpx.RequestError as exc:
                if attempt == self._max_retries:
                    raise VacancySourceError("network_error") from exc
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise VacancySourceError("temporarily_unavailable")
            if response.is_error:
                raise VacancySourceError(f"http_{response.status_code}")
            try:
                return response.json()
            except ValueError as exc:
                raise VacancySourceError("invalid_json") from exc
        raise VacancySourceError("temporarily_unavailable")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
