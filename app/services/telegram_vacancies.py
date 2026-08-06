from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.services.vacancies import VacancyIngestionService
from app.services.vacancy_text import parse_vacancy_text
from app.sources.normalize import country_code_for
from app.sources.schemas import VacancyRecord


@dataclass(frozen=True, slots=True)
class TelegramVacancyResult:
    stored: bool
    reason: str | None = None


class TelegramVacancyService:
    def __init__(self, ingestion: VacancyIngestionService, settings: Settings) -> None:
        self._ingestion = ingestion
        self._allowed_ids = settings.telegram_vacancy_chat_id_set
        self._allowed_usernames = settings.telegram_vacancy_chat_username_set

    def is_allowed(self, chat_id: int, username: str | None) -> bool:
        normalized_username = (username or "").removeprefix("@").casefold()
        return chat_id in self._allowed_ids or normalized_username in self._allowed_usernames

    async def ingest(
        self,
        *,
        chat_id: int,
        chat_type: str,
        chat_title: str | None,
        chat_username: str | None,
        message_id: int,
        text: str | None,
        published_at: datetime,
    ) -> TelegramVacancyResult:
        if not self.is_allowed(chat_id, chat_username):
            return TelegramVacancyResult(False, "not_allowed")
        if text is None or len(text) > 100_000:
            return TelegramVacancyResult(False, "invalid_text")
        parsed = parse_vacancy_text(text, strict=True)
        if parsed is None:
            return TelegramVacancyResult(False, "not_a_vacancy")
        source_url = telegram_message_url(
            chat_id=chat_id,
            chat_type=chat_type,
            username=chat_username,
            message_id=message_id,
        )
        if source_url is None:
            return TelegramVacancyResult(False, "message_url_unavailable")
        attribution = (
            f"Telegram @{chat_username.removeprefix('@')}"
            if chat_username
            else f"Telegram {chat_title or 'approved group'}"
        )
        await self._ingestion.store(
            [
                VacancyRecord(
                    source="telegram",
                    external_id=f"{chat_id}:{message_id}",
                    title=parsed.title,
                    company=parsed.company or chat_title or "Telegram source",
                    description=parsed.normalized_text,
                    location=parsed.location,
                    country_code=country_code_for(parsed.location),
                    workplace_type=parsed.workplace_type,
                    canonical_url=source_url,
                    apply_url=parsed.first_url or source_url,
                    published_at=published_at,
                    attribution=attribution[:255],
                )
            ]
        )
        return TelegramVacancyResult(True)


def telegram_message_url(
    *, chat_id: int, chat_type: str, username: str | None, message_id: int
) -> str | None:
    if username:
        return f"https://t.me/{username.removeprefix('@')}/{message_id}"
    raw_id = str(chat_id)
    if chat_type in {"channel", "supergroup"} and raw_id.startswith("-100"):
        return f"https://t.me/c/{raw_id.removeprefix('-100')}/{message_id}"
    return None
