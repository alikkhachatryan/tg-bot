from typing import Any

import httpx

from app.sources.base import HttpVacancySource, VacancySourceError
from app.sources.normalize import parse_datetime, plain_text
from app.sources.schemas import VacancyRecord


class RemotiveVacancySource(HttpVacancySource):
    name = "remotive"

    def __init__(
        self,
        *,
        api_url: str,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_url = api_url
        super().__init__(
            base_url=api_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            headers={"User-Agent": "tg-job-match-bot/0.1"},
            client=client,
        )

    async def fetch(self) -> list[VacancyRecord]:
        payload = await self._get_json(self._api_url)
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise VacancySourceError("invalid_payload")
        return [_parse_remotive(item) for item in payload["jobs"] if isinstance(item, dict)]


def _parse_remotive(item: dict[str, Any]) -> VacancyRecord:
    url = str(item.get("url") or "")
    return VacancyRecord(
        source="remotive",
        external_id=str(item["id"]),
        title=str(item["title"]),
        company=str(item["company_name"]),
        description=plain_text(item.get("description")),
        location="Remote",
        workplace_type="remote",
        employment_type=_string(item.get("job_type")),
        remote_scope=_string(item.get("candidate_required_location")),
        canonical_url=url,
        apply_url=url,
        published_at=parse_datetime(item.get("publication_date")),
        attribution="Remotive",
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
