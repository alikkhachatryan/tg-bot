import asyncio

from app.bot.factory import create_bot, create_dispatcher
from app.core.config import get_settings
from app.core.logging import configure_logging


async def run_polling() -> None:
    settings = get_settings()
    configure_logging(settings)
    bot = create_bot(settings)
    dispatcher = create_dispatcher()
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_polling())
