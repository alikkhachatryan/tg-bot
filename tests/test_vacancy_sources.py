from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import Settings
from app.sources.base import VacancySourceError
from app.sources.factory import create_vacancy_sources
from app.sources.greenhouse import GreenhouseVacancySource
from app.sources.hh import HHVacancySource
from app.sources.lever import LeverVacancySource
from app.sources.remotive import RemotiveVacancySource


async def test_hh_uses_area_directory_and_required_user_agent() -> None:
    seen_vacancy_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_vacancy_request
        if request.url.path == "/areas":
            assert request.url.params["locale"] == "EN"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "am",
                        "name": "Armenia",
                        "areas": [{"id": "evn", "name": "Yerevan", "areas": []}],
                    }
                ],
            )
        seen_vacancy_request = request
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "42",
                        "name": "Python Developer",
                        "alternate_url": "https://hh.example/42",
                        "published_at": "2026-08-06T10:00:00+04:00",
                        "area": {"name": "Yerevan"},
                        "employer": {"name": "Acme AM"},
                        "salary": {"from": 1000, "to": 2000, "currency": "USD"},
                        "schedule": {"id": "remote"},
                        "employment": {"name": "Full time"},
                        "snippet": {
                            "requirement": "<b>Python</b>",
                            "responsibility": "Build APIs",
                        },
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        base_url="https://api.hh.test", transport=httpx.MockTransport(handler)
    )
    source = HHVacancySource(
        base_url="https://api.hh.test",
        user_agent="tg-job-match-bot/0.1 (dev@example.com)",
        access_token="test-access-token",  # noqa: S106
        focus_locations=("Armenia", "Yerevan"),
        search_terms=("Python",),
        per_page=50,
        timeout_seconds=1,
        max_retries=0,
        client=client,
    )

    records = await source.fetch()

    assert len(records) == 1
    assert records[0].country_code == "AM"
    assert records[0].workplace_type == "remote"
    assert records[0].description == "Python Build APIs"
    assert seen_vacancy_request is not None
    assert seen_vacancy_request.headers["HH-User-Agent"].startswith("tg-job-match-bot")
    assert seen_vacancy_request.headers["Authorization"].startswith("Bearer ")
    assert seen_vacancy_request.url.params.get_list("area") == ["am", "evn"]
    await client.aclose()


def test_hh_requires_identifying_user_agent() -> None:
    with pytest.raises(VacancySourceError, match="missing_user_agent"):
        HHVacancySource(
            base_url="https://api.hh.test",
            user_agent="",
            access_token=None,
            focus_locations=("Armenia",),
            search_terms=(),
            per_page=20,
            timeout_seconds=1,
            max_retries=0,
        )


def test_hh_requires_oauth_token() -> None:
    with pytest.raises(VacancySourceError, match="missing_access_token"):
        HHVacancySource(
            base_url="https://api.hh.test",
            user_agent="tg-job-match-bot/0.1 (dev@example.com)",
            access_token=None,
            focus_locations=("Armenia",),
            search_terms=(),
            per_page=20,
            timeout_seconds=1,
            max_retries=0,
        )


async def test_remotive_preserves_attribution_and_remote_scope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/remote-jobs"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 7,
                        "url": "https://remotive.com/jobs/7",
                        "title": "Backend Engineer",
                        "company_name": "Remote Co",
                        "job_type": "full_time",
                        "publication_date": "2026-08-05T10:00:00",
                        "candidate_required_location": "Europe",
                        "description": "<p>Python and PostgreSQL</p>",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        base_url="https://remotive.test/api/remote-jobs",
        transport=httpx.MockTransport(handler),
    )
    source = RemotiveVacancySource(
        api_url="https://remotive.test/api/remote-jobs",
        timeout_seconds=1,
        max_retries=0,
        client=client,
    )

    record = (await source.fetch())[0]

    assert record.attribution == "Remotive"
    assert record.remote_scope == "Europe"
    assert record.published_at == datetime(2026, 8, 5, 10, tzinfo=UTC)
    await client.aclose()


async def test_greenhouse_and_lever_are_normalized() -> None:
    def greenhouse_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/boards/acme-am":
            return httpx.Response(200, json={"name": "Acme Armenia"})
        assert request.url.path == "/v1/boards/acme-am/jobs"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 1,
                        "title": "QA Engineer",
                        "absolute_url": "https://boards.example/1",
                        "location": {"name": "Yerevan, Armenia"},
                        "content": "<p>Test software</p>",
                        "updated_at": "2026-08-06T00:00:00Z",
                    }
                ]
            },
        )

    greenhouse_client = httpx.AsyncClient(
        base_url="https://boards-api.greenhouse.io/v1",
        transport=httpx.MockTransport(greenhouse_handler),
    )
    greenhouse = GreenhouseVacancySource(
        board_tokens=("acme-am",),
        timeout_seconds=1,
        max_retries=0,
        client=greenhouse_client,
    )
    greenhouse_record = (await greenhouse.fetch())[0]
    assert greenhouse_record.company == "Acme Armenia"
    assert greenhouse_record.country_code == "AM"

    def lever_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v0/postings/acme-am"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "abc",
                    "text": "DevOps Engineer",
                    "categories": {"location": "Remote", "commitment": "Full-time"},
                    "country": "AM",
                    "descriptionPlain": "Operate infrastructure",
                    "hostedUrl": "https://jobs.lever.co/acme/abc",
                    "applyUrl": "https://jobs.lever.co/acme/abc/apply",
                    "workplaceType": "remote",
                    "salaryRange": {"min": 50000, "max": 70000, "currency": "USD"},
                }
            ],
        )

    lever_client = httpx.AsyncClient(
        base_url="https://api.lever.co/v0/postings", transport=httpx.MockTransport(lever_handler)
    )
    lever = LeverVacancySource(
        sites=("acme-am",),
        timeout_seconds=1,
        max_retries=0,
        client=lever_client,
    )
    lever_record = (await lever.fetch())[0]
    assert lever_record.country_code == "AM"
    assert lever_record.salary_min == 50000
    assert lever_record.apply_url.endswith("/apply")
    await greenhouse_client.aclose()
    await lever_client.aclose()


async def test_factory_skips_unconfigured_company_boards() -> None:
    settings = Settings(
        _env_file=None,
        vacancy_sources="remotive,greenhouse,lever",
        greenhouse_boards="",
        lever_sites="",
    )

    sources = create_vacancy_sources(settings)

    assert [source.name for source in sources] == ["remotive"]
    for source in sources:
        await source.close()
