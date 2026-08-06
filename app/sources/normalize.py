import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from app.sources.schemas import VacancyRecord

_SPACE_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: object) -> str:
    parser = _TextExtractor()
    parser.feed(value if isinstance(value, str) else "")
    return _SPACE_RE.sub(" ", " ".join(parser.parts)).strip()


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result


def vacancy_fingerprint(record: VacancyRecord) -> str:
    identity = "|".join(
        _normalize(value)
        for value in (
            record.title,
            record.company,
            record.location or "",
            record.description[:2000],
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def vacancy_content_hash(record: VacancyRecord) -> str:
    payload = record.model_dump(mode="json", exclude={"attribution"})
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def country_code_for(location: str | None, explicit: object = None) -> str | None:
    if isinstance(explicit, str) and len(explicit) == 2:
        return explicit.upper()
    normalized = _normalize(location or "")
    if any(name in normalized for name in ("armenia", "yerevan", "армен", "ереван")):
        return "AM"
    return None


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _normalize(value: str) -> str:
    return _SPACE_RE.sub(" ", value.casefold()).strip()
