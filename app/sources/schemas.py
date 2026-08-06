from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VacancyRecord(BaseModel):
    """Canonical data returned by every approved vacancy source adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=32)
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=200_000)
    location: str | None = Field(default=None, max_length=500)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    workplace_type: str = Field(default="unspecified", max_length=32)
    employment_type: str | None = Field(default=None, max_length=64)
    remote_scope: str | None = Field(default=None, max_length=255)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    canonical_url: str = Field(min_length=1, max_length=2000)
    apply_url: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    expires_at: datetime | None = None
    attribution: str | None = Field(default=None, max_length=255)
