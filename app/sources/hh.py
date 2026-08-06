from typing import Any

import httpx

from app.sources.base import HttpVacancySource, VacancySourceError
from app.sources.normalize import country_code_for, optional_int, parse_datetime, plain_text
from app.sources.schemas import VacancyRecord


class HHVacancySource(HttpVacancySource):
    name = "hh"

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        access_token: str | None,
        focus_locations: tuple[str, ...],
        search_terms: tuple[str, ...],
        per_page: int,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not user_agent.strip():
            raise VacancySourceError("missing_user_agent")
        if not access_token:
            raise VacancySourceError("missing_access_token")
        headers = {"HH-User-Agent": user_agent, "User-Agent": user_agent}
        headers["Authorization"] = f"Bearer {access_token}"
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            headers=headers,
            client=client,
        )
        self._focus_locations = focus_locations
        self._search_terms = search_terms or ("",)
        self._per_page = per_page

    async def fetch(self) -> list[VacancyRecord]:
        areas_payload = await self._get_json("areas", params={"locale": "EN"})
        area_ids = _find_area_ids(areas_payload, self._focus_locations)
        if self._focus_locations and not area_ids:
            raise VacancySourceError("areas_not_found")
        records: dict[str, VacancyRecord] = {}
        for term in self._search_terms:
            params: list[tuple[str, object]] = [
                ("page", 0),
                ("per_page", self._per_page),
                ("period", 7),
                ("order_by", "publication_time"),
            ]
            if term:
                params.append(("text", term))
            params.extend(("area", area_id) for area_id in area_ids)
            payload = await self._get_json("vacancies", params=params)
            if not isinstance(payload, dict):
                raise VacancySourceError("invalid_payload")
            for item in payload.get("items", []):
                if isinstance(item, dict):
                    record = _parse_hh_vacancy(item)
                    records[record.external_id] = record
        return list(records.values())


def _find_area_ids(payload: Any, names: tuple[str, ...]) -> tuple[str, ...]:
    wanted = {name.casefold() for name in names}
    found: list[str] = []

    def visit(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            identifier = node.get("id")
            if isinstance(name, str) and name.casefold() in wanted and isinstance(identifier, str):
                found.append(identifier)
            visit(node.get("areas"))

    visit(payload)
    return tuple(dict.fromkeys(found))


def _parse_hh_vacancy(item: dict[str, Any]) -> VacancyRecord:
    area: dict[str, Any] = _mapping(item.get("area"))
    employer: dict[str, Any] = _mapping(item.get("employer"))
    salary: dict[str, Any] = _mapping(item.get("salary"))
    snippet: dict[str, Any] = _mapping(item.get("snippet"))
    schedule: dict[str, Any] = _mapping(item.get("schedule"))
    location = area.get("name") if isinstance(area.get("name"), str) else None
    workplace_type = "remote" if schedule.get("id") == "remote" else "unspecified"
    url = str(item.get("alternate_url") or item.get("url") or "")
    return VacancyRecord(
        source="hh",
        external_id=str(item["id"]),
        title=str(item["name"]),
        company=str(employer.get("name") or "Unknown employer"),
        description=plain_text(
            f"{snippet.get('requirement') or ''} {snippet.get('responsibility') or ''}"
        ),
        location=location,
        country_code=country_code_for(location),
        workplace_type=workplace_type,
        employment_type=_nested_name(item.get("employment")),
        salary_min=optional_int(salary.get("from")),
        salary_max=optional_int(salary.get("to")),
        salary_currency=salary.get("currency") if isinstance(salary.get("currency"), str) else None,
        canonical_url=url,
        apply_url=url,
        published_at=parse_datetime(item.get("published_at")),
        attribution="HeadHunter",
    )


def _nested_name(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    return name if isinstance(name, str) else None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
