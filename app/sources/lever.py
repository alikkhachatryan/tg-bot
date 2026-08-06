from typing import Any

import httpx

from app.sources.base import HttpVacancySource, VacancySourceError
from app.sources.normalize import country_code_for, optional_int
from app.sources.schemas import VacancyRecord


class LeverVacancySource(HttpVacancySource):
    name = "lever"

    def __init__(
        self,
        *,
        sites: tuple[str, ...],
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url="https://api.lever.co/v0/postings",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
        )
        self._sites = sites

    async def fetch(self) -> list[VacancyRecord]:
        records: list[VacancyRecord] = []
        for site in self._sites:
            payload = await self._get_json(site, params={"mode": "json"})
            if not isinstance(payload, list):
                raise VacancySourceError("invalid_payload")
            records.extend(_parse_lever(item, site) for item in payload if isinstance(item, dict))
        return records


def _parse_lever(item: dict[str, Any], site: str) -> VacancyRecord:
    raw_categories = item.get("categories")
    raw_salary = item.get("salaryRange")
    categories: dict[str, Any] = raw_categories if isinstance(raw_categories, dict) else {}
    salary: dict[str, Any] = raw_salary if isinstance(raw_salary, dict) else {}
    location = categories.get("location") if isinstance(categories.get("location"), str) else None
    workplace = str(item.get("workplaceType") or "unspecified")
    hosted_url = str(item.get("hostedUrl") or "")
    return VacancyRecord(
        source="lever",
        external_id=f"{site}:{item['id']}",
        title=str(item["text"]),
        company=site.replace("-", " ").title(),
        description=str(item.get("descriptionPlain") or item.get("openingPlain") or ""),
        location=location,
        country_code=country_code_for(location, item.get("country")),
        workplace_type=workplace,
        employment_type=(
            categories.get("commitment") if isinstance(categories.get("commitment"), str) else None
        ),
        salary_min=optional_int(salary.get("min")),
        salary_max=optional_int(salary.get("max")),
        salary_currency=(
            salary.get("currency") if isinstance(salary.get("currency"), str) else None
        ),
        canonical_url=hosted_url,
        apply_url=str(item.get("applyUrl") or hosted_url),
        attribution=f"{site} via Lever",
    )
