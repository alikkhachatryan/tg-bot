import re
from dataclasses import dataclass

from app.sources.normalize import plain_text

_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_VACANCY_TERMS = (
    "vacancy",
    "job",
    "hiring",
    "position",
    "requirements",
    "ваканси",
    "работ",
    "ищем",
    "требован",
    "должност",
    "աշխատանք",
    "թափուր",
    "պահանջ",
)
_STRONG_VACANCY_TERMS = (
    "vacancy",
    "hiring",
    "job opening",
    "we are looking",
    "ваканси",
    "ищем",
    "требуется",
    "приглашаем в команду",
    "թափուր",
    "աշխատանքի հնարավորություն",
)


@dataclass(frozen=True, slots=True)
class ParsedVacancyText:
    normalized_text: str
    title: str
    company: str | None
    location: str | None
    workplace_type: str
    first_url: str | None


def parse_vacancy_text(text: str, *, strict: bool = False) -> ParsedVacancyText | None:
    normalized = plain_text(text)
    if (
        len(normalized) < 60
        or not _looks_like_vacancy(normalized)
        or (strict and not _looks_like_public_vacancy(normalized))
    ):
        return None
    lines = [plain_text(line) for line in text.splitlines() if plain_text(line)]
    if not lines:
        return None
    return ParsedVacancyText(
        normalized_text=normalized,
        title=_extract_title(lines),
        company=_extract_labeled_value(text, ("company", "компания", "ընկերություն")),
        location=_extract_labeled_value(text, ("location", "локация", "город", "место", "վայր")),
        workplace_type=_workplace_type(normalized),
        first_url=_first_url(normalized),
    )


def _looks_like_vacancy(text: str) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in _VACANCY_TERMS)


def _looks_like_public_vacancy(text: str) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in _STRONG_VACANCY_TERMS)


def _extract_title(lines: list[str]) -> str:
    for line in lines[:5]:
        match = re.match(
            r"^(?:vacancy|job title|position|вакансия|должность|պաշտոն)\s*[:—-]\s*(.+)$",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)[:500]
    return lines[0][:500]


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    pattern = "|".join(re.escape(label) for label in labels)
    for line in text.splitlines():
        match = re.match(rf"^(?:{pattern})\s*[:—-]\s*(.+)$", line.strip(), re.IGNORECASE)
        if match:
            return plain_text(match.group(1))[:500]
    return None


def _workplace_type(text: str) -> str:
    normalized = text.casefold()
    if any(term in normalized for term in ("remote", "удален", "дистанц", "հեռավար")):
        return "remote"
    if any(term in normalized for term in ("hybrid", "гибрид", "հիբրիդ")):
        return "hybrid"
    if any(term in normalized for term in ("office", "офис", "գրասենյակ")):
        return "office"
    return "unspecified"


def _first_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0).rstrip(".,);]")[:2000] if match else None
