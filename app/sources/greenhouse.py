from typing import Any

import httpx

from app.sources.base import HttpVacancySource, VacancySourceError
from app.sources.normalize import country_code_for, parse_datetime, plain_text
from app.sources.schemas import VacancyRecord


class GreenhouseVacancySource(HttpVacancySource):
    name = "greenhouse"

    def __init__(
        self,
        *,
        board_tokens: tuple[str, ...],
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url="https://boards-api.greenhouse.io/v1",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
        )
        self._board_tokens = board_tokens

    async def fetch(self) -> list[VacancyRecord]:
        records: list[VacancyRecord] = []
        for token in self._board_tokens:
            board_payload = await self._get_json(f"boards/{token}")
            company_value = board_payload.get("name") if isinstance(board_payload, dict) else None
            company = (
                company_value if isinstance(company_value, str) else token.replace("-", " ").title()
            )
            payload = await self._get_json(f"boards/{token}/jobs", params={"content": "true"})
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise VacancySourceError("invalid_payload")
            records.extend(
                _parse_greenhouse(item, token, company)
                for item in payload["jobs"]
                if isinstance(item, dict)
            )
        return records


def _parse_greenhouse(item: dict[str, Any], board: str, company: str) -> VacancyRecord:
    raw_location = item.get("location")
    location_data: dict[str, Any] = raw_location if isinstance(raw_location, dict) else {}
    location = location_data.get("name") if isinstance(location_data.get("name"), str) else None
    location_lower = (location or "").casefold()
    workplace = "remote" if "remote" in location_lower else "unspecified"
    url = str(item.get("absolute_url") or "")
    return VacancyRecord(
        source="greenhouse",
        external_id=f"{board}:{item['id']}",
        title=str(item["title"]),
        company=company,
        description=plain_text(item.get("content")),
        location=location,
        country_code=country_code_for(location),
        workplace_type=workplace,
        canonical_url=url,
        apply_url=url,
        published_at=parse_datetime(item.get("updated_at")),
        attribution=f"{board} via Greenhouse",
    )
