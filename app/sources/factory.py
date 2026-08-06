from app.core.config import Settings
from app.sources.base import VacancySource, VacancySourceError
from app.sources.greenhouse import GreenhouseVacancySource
from app.sources.hh import HHVacancySource
from app.sources.lever import LeverVacancySource
from app.sources.remotive import RemotiveVacancySource


def create_vacancy_sources(settings: Settings) -> list[VacancySource]:
    sources: list[VacancySource] = []
    for name in settings.enabled_vacancy_sources:
        if name == "hh":
            sources.append(
                HHVacancySource(
                    base_url=settings.hh_api_url,
                    user_agent=settings.hh_user_agent,
                    access_token=(
                        settings.hh_access_token.get_secret_value()
                        if settings.hh_access_token is not None
                        else None
                    ),
                    focus_locations=settings.hh_location_names,
                    search_terms=settings.hh_terms,
                    per_page=settings.hh_per_page,
                    timeout_seconds=settings.source_http_timeout_seconds,
                    max_retries=settings.source_max_retries,
                )
            )
        elif name == "remotive":
            sources.append(
                RemotiveVacancySource(
                    api_url=settings.remotive_api_url,
                    timeout_seconds=settings.source_http_timeout_seconds,
                    max_retries=settings.source_max_retries,
                )
            )
        elif name == "greenhouse":
            if settings.greenhouse_board_tokens:
                sources.append(
                    GreenhouseVacancySource(
                        board_tokens=settings.greenhouse_board_tokens,
                        timeout_seconds=settings.source_http_timeout_seconds,
                        max_retries=settings.source_max_retries,
                    )
                )
        elif name == "lever":
            if settings.lever_site_names:
                sources.append(
                    LeverVacancySource(
                        sites=settings.lever_site_names,
                        timeout_seconds=settings.source_http_timeout_seconds,
                        max_retries=settings.source_max_retries,
                    )
                )
        else:
            raise VacancySourceError(f"unsupported_source:{name}")
    return sources
