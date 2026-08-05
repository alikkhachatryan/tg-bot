from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import (
    accept_consent,
    cancel_command,
    delete_command,
    document_gate,
    help_command,
    identity_from_message,
    menu,
    privacy_callback,
    privacy_command,
    start,
)
from app.services.telegram_users import BetaAccessDeniedError


def fake_sender(user_id: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username="tester",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )


def fake_message(user_id: int = 100) -> SimpleNamespace:
    return SimpleNamespace(from_user=fake_sender(user_id), answer=AsyncMock())


async def test_start_registers_user_and_shows_consent() -> None:
    message = fake_message()
    service = SimpleNamespace(register=AsyncMock(return_value="user-id"))

    await start(message, service)

    service.register.assert_awaited_once()
    message.answer.assert_awaited_once()


async def test_start_handles_beta_denial_and_missing_sender() -> None:
    denied_message = fake_message(999)
    service = SimpleNamespace(register=AsyncMock(side_effect=BetaAccessDeniedError))
    await start(denied_message, service)
    denied_message.answer.assert_awaited_once_with("Бот пока работает в закрытой beta-версии.")

    missing = SimpleNamespace(from_user=None, answer=AsyncMock())
    assert identity_from_message(missing) is None
    await start(missing, service)
    missing.answer.assert_not_awaited()


async def test_consent_callback_persists_update_id() -> None:
    message = fake_message()
    callback = SimpleNamespace(
        from_user=fake_sender(),
        message=message,
        answer=AsyncMock(),
    )
    service = SimpleNamespace(
        register=AsyncMock(return_value="user-id"),
        grant_required_consent=AsyncMock(),
    )

    await accept_consent(callback, SimpleNamespace(update_id=77), service)

    service.grant_required_consent.assert_awaited_once_with("user-id", 77)
    callback.answer.assert_awaited_once_with("Готово")


async def test_document_requires_consent() -> None:
    message = fake_message()
    service = SimpleNamespace(
        register=AsyncMock(return_value="user-id"),
        has_required_consent=AsyncMock(return_value=False),
    )
    await document_gate(message, service)
    assert "Сначала" in message.answer.await_args.args[0]

    message.answer.reset_mock()
    service.has_required_consent.return_value = True
    await document_gate(message, service)
    assert "следующем этапе" in message.answer.await_args.args[0]


async def test_basic_commands_and_privacy_callbacks() -> None:
    message = fake_message()
    await privacy_command(message)
    await menu(message)
    await help_command(message)
    await cancel_command(message)
    await delete_command(message)
    assert message.answer.await_count == 5

    callback = SimpleNamespace(message=message, answer=AsyncMock())
    await privacy_callback(callback)
    callback.answer.assert_awaited_once()
