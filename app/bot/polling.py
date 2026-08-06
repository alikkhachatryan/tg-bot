import asyncio

from app.bot.factory import create_bot, create_dispatcher
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.onboarding import OnboardingService
from app.services.profiles import ProfileService
from app.services.queue import ArqResumeQueue
from app.services.resumes import ResumeService
from app.services.storage import create_storage
from app.services.telegram_users import TelegramUserService
from app.services.vacancies import VacancyIngestionService


async def run_polling() -> None:
    settings = get_settings()
    configure_logging(settings)
    bot = create_bot(settings)
    dispatcher = create_dispatcher()
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    user_service = TelegramUserService(sessions, settings)
    resume_service = ResumeService(sessions, create_storage(settings), settings)
    resume_queue = ArqResumeQueue(settings.redis_url)
    try:
        await dispatcher.start_polling(
            bot,
            user_service=user_service,
            resume_service=resume_service,
            resume_queue=resume_queue,
            profile_service=ProfileService(sessions),
            onboarding_service=OnboardingService(sessions),
            vacancy_service=VacancyIngestionService(sessions),
        )
    finally:
        await resume_queue.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_polling())
