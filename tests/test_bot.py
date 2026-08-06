from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from pydantic import SecretStr

from app.bot import polling
from app.bot.factory import create_bot, create_dispatcher
from app.core.config import Settings


def test_create_bot_requires_token() -> None:
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        create_bot(Settings(_env_file=None, telegram_bot_token=None))


async def test_create_bot_and_dispatcher() -> None:
    bot = create_bot(
        Settings(
            _env_file=None,
            telegram_bot_token=SecretStr("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"),
        )
    )
    try:
        assert bot.token.startswith("123456:")
        assert create_dispatcher() is not None
    finally:
        await bot.session.close()


async def test_polling_entrypoint_closes_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(close=AsyncMock())
    bot = SimpleNamespace(session=session)
    dispatcher = SimpleNamespace(start_polling=AsyncMock())
    engine = SimpleNamespace(dispose=AsyncMock())
    settings = Settings(_env_file=None)

    monkeypatch.setattr(polling, "get_settings", lambda: settings)
    monkeypatch.setattr(polling, "configure_logging", lambda value: None)
    monkeypatch.setattr(polling, "create_bot", lambda value: bot)
    monkeypatch.setattr(polling, "create_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(polling, "create_engine", lambda value: engine)
    monkeypatch.setattr(polling, "create_session_factory", lambda value: SimpleNamespace())

    await polling.run_polling()

    dispatcher.start_polling.assert_awaited_once_with(
        bot,
        user_service=ANY,
        resume_service=ANY,
        resume_queue=ANY,
        profile_service=ANY,
    )
    session.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()
