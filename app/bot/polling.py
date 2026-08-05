import asyncio

from app.bot.factory import create_bot, create_dispatcher
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.telegram_users import TelegramUserService


async def run_polling() -> None:
    settings = get_settings()
    configure_logging(settings)
    bot = create_bot(settings)
    dispatcher = create_dispatcher()
    engine = create_engine(settings)
    user_service = TelegramUserService(create_session_factory(engine), settings)
    try:
        await dispatcher.start_polling(bot, user_service=user_service)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_polling())
