from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.bot.handlers import (
    accept_consent,
    apply_profile_edit,
    begin_profile_field_edit,
    cancel_command,
    confirm_profile,
    delete_command,
    document_gate,
    help_command,
    identity_from_message,
    menu,
    privacy_callback,
    privacy_command,
    start,
)
from app.services.onboarding import OnboardingStep, Question
from app.services.resumes import DOCX_MEDIA_TYPE, ResumeValidationError
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
    await document_gate(message, service, SimpleNamespace(), SimpleNamespace())
    assert "Сначала" in message.answer.await_args.args[0]


async def test_document_is_downloaded_saved_and_queued() -> None:
    data = b"valid-document-bytes"

    def download(_file_id, destination) -> None:
        destination.write(data)

    message = SimpleNamespace(
        from_user=fake_sender(),
        answer=AsyncMock(),
        bot=SimpleNamespace(download=AsyncMock(side_effect=download)),
        document=SimpleNamespace(
            file_id="file-id",
            file_name="resume.docx",
            mime_type=DOCX_MEDIA_TYPE,
            file_size=len(data),
        ),
    )
    user_service = SimpleNamespace(
        register=AsyncMock(return_value="user-id"),
        has_required_consent=AsyncMock(return_value=True),
    )
    resume_id = uuid4()
    resume_service = SimpleNamespace(
        max_bytes=1024,
        save=AsyncMock(return_value=resume_id),
        mark_queued=AsyncMock(),
    )
    queue = SimpleNamespace(enqueue=AsyncMock())

    await document_gate(message, user_service, resume_service, queue)

    resume_service.save.assert_awaited_once()
    resume_service.mark_queued.assert_awaited_once_with(resume_id)
    queue.enqueue.assert_awaited_once_with(resume_id)
    assert "очередь" in message.answer.await_args.args[0]


async def test_document_rejects_large_and_invalid_uploads() -> None:
    message = SimpleNamespace(
        from_user=fake_sender(),
        answer=AsyncMock(),
        document=SimpleNamespace(file_size=2048),
    )
    user_service = SimpleNamespace(
        register=AsyncMock(return_value="user-id"),
        has_required_consent=AsyncMock(return_value=True),
    )
    await document_gate(
        message,
        user_service,
        SimpleNamespace(max_bytes=1024),
        SimpleNamespace(),
    )
    assert "большой" in message.answer.await_args.args[0]

    data = b"invalid"
    message.document = SimpleNamespace(
        file_id="file-id",
        file_name="resume.pdf",
        mime_type="application/pdf",
        file_size=len(data),
    )

    def download(_file_id, destination) -> None:
        destination.write(data)

    message.bot = SimpleNamespace(download=AsyncMock(side_effect=download))
    resume_service = SimpleNamespace(
        max_bytes=1024,
        save=AsyncMock(side_effect=ResumeValidationError("invalid_pdf")),
        mark_queued=AsyncMock(),
    )
    queue = SimpleNamespace(enqueue=AsyncMock())
    await document_gate(message, user_service, resume_service, queue)
    queue.enqueue.assert_not_awaited()
    resume_service.mark_queued.assert_not_awaited()
    assert "не принят" in message.answer.await_args.args[0]


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


async def test_profile_confirmation_and_edit_flow() -> None:
    profile_id = uuid4()
    callback = SimpleNamespace(
        from_user=fake_sender(),
        message=fake_message(),
        data=f"profile:confirm:{profile_id}",
        answer=AsyncMock(),
    )
    user_service = SimpleNamespace(register=AsyncMock(return_value=uuid4()))
    profile_service = SimpleNamespace(
        confirm=AsyncMock(return_value=True),
        begin_edit=AsyncMock(return_value=True),
        apply_pending_edit=AsyncMock(return_value=SimpleNamespace(id=profile_id)),
    )
    onboarding_service = SimpleNamespace(
        start=AsyncMock(
            return_value=OnboardingStep(
                Question("desired_roles", "Какие роли?", "list"),
                can_go_back=False,
            )
        ),
        answer=AsyncMock(return_value=None),
    )

    await confirm_profile(callback, user_service, profile_service, onboarding_service)
    profile_service.confirm.assert_awaited_once()
    callback.answer.assert_awaited_with("Готово")

    callback.data = f"profile:field:t:{profile_id}"
    callback.answer.reset_mock()
    await begin_profile_field_edit(callback, user_service, profile_service)
    profile_service.begin_edit.assert_awaited_once()
    callback.message.answer.assert_awaited()

    message = fake_message()
    message.text = "Senior Backend Developer"
    await apply_profile_edit(message, user_service, profile_service, onboarding_service)
    profile_service.apply_pending_edit.assert_awaited_once()
    assert "Изменение сохранено" in message.answer.await_args.args[0]
