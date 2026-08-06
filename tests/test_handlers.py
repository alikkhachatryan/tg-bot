from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.bot.handlers import (
    accept_consent,
    add_job_command,
    apply_profile_edit,
    begin_profile_field_edit,
    cancel_command,
    chat_id_command,
    confirm_profile,
    delete_command,
    document_gate,
    help_command,
    identity_from_message,
    main_menu_callback,
    menu,
    onboarding_callback,
    privacy_callback,
    privacy_command,
    start,
    submission_callback,
    telegram_vacancy_message,
)
from app.services.onboarding import OnboardingStep, Question
from app.services.resumes import DOCX_MEDIA_TYPE, ResumeValidationError
from app.services.submissions import SubmissionResult
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


async def test_chat_id_and_telegram_source_handlers() -> None:
    chat = SimpleNamespace(
        id=-100123,
        type="channel",
        title="Armenia Jobs",
        username="armenia_jobs",
    )
    message = SimpleNamespace(
        chat=chat,
        message_id=42,
        text="Vacancy: PHP Developer. We are hiring. Requirements: PHP and Bitrix. " * 2,
        caption=None,
        date=datetime.now(UTC),
        answer=AsyncMock(),
    )
    service = SimpleNamespace(ingest=AsyncMock())

    await chat_id_command(message)
    await telegram_vacancy_message(message, service)

    assert "-100123" in message.answer.await_args.args[0]
    service.ingest.assert_awaited_once_with(
        chat_id=-100123,
        chat_type="channel",
        chat_title="Armenia Jobs",
        chat_username="armenia_jobs",
        message_id=42,
        text=message.text,
        published_at=message.date,
    )


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
    submission_service = SimpleNamespace(is_awaiting_text=AsyncMock(return_value=False))

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
    await apply_profile_edit(
        message, user_service, profile_service, onboarding_service, submission_service
    )
    profile_service.apply_pending_edit.assert_awaited_once()
    assert "Изменение сохранено" in message.answer.await_args.args[0]


async def test_work_mode_callback_toggles_without_advancing() -> None:
    question = Question("work_modes", "Какой формат работы?", "work_modes")
    message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(
        from_user=fake_sender(),
        message=message,
        data="onboard:wm:remote",
        answer=AsyncMock(),
    )
    user_id = uuid4()
    user_service = SimpleNamespace(
        register=AsyncMock(return_value=user_id),
        has_required_consent=AsyncMock(return_value=True),
    )
    onboarding_service = SimpleNamespace(
        toggle_work_mode=AsyncMock(
            return_value=OnboardingStep(
                question,
                can_go_back=True,
                selected_values=("remote",),
            )
        ),
        submit_work_modes=AsyncMock(),
    )

    await onboarding_callback(callback, user_service, onboarding_service)

    onboarding_service.toggle_work_mode.assert_awaited_once_with(user_id, "remote")
    onboarding_service.submit_work_modes.assert_not_awaited()
    message.edit_reply_markup.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_main_menu_buttons_are_handled() -> None:
    user_id = uuid4()
    message = fake_message()
    callback = SimpleNamespace(
        from_user=fake_sender(),
        message=message,
        data="menu:new_jobs",
        answer=AsyncMock(),
    )
    user_service = SimpleNamespace(
        register=AsyncMock(return_value=user_id),
        has_required_consent=AsyncMock(return_value=True),
    )
    profile_service = SimpleNamespace(
        latest_confirmed=AsyncMock(
            return_value=SimpleNamespace(
                full_name="Test User",
                current_title="Developer",
                desired_roles=["Backend Developer"],
                skills=[{"name": "Python"}],
            )
        )
    )
    onboarding_service = SimpleNamespace(
        start=AsyncMock(
            return_value=OnboardingStep(
                Question("preferred_locations", "Где ищем?", "list"),
                can_go_back=True,
            )
        )
    )
    vacancy_service = SimpleNamespace()
    matching_service = SimpleNamespace(
        new_matches=AsyncMock(
            return_value=[
                SimpleNamespace(
                    vacancy=SimpleNamespace(
                        title="Python Developer",
                        company="Example",
                        location="Yerevan",
                        canonical_url="https://example.com/job",
                    ),
                    match=SimpleNamespace(
                        score=91,
                        explanations=["Совпавшие навыки: Python"],
                    ),
                )
            ]
        )
    )
    submission_service = SimpleNamespace(
        begin=AsyncMock(), latest_private=AsyncMock(return_value=[])
    )

    await main_menu_callback(
        callback,
        user_service,
        profile_service,
        onboarding_service,
        vacancy_service,
        matching_service,
        submission_service,
    )
    assert "Python Developer" in message.answer.await_args.args[0]

    callback.data = "menu:profile"
    await main_menu_callback(
        callback,
        user_service,
        profile_service,
        onboarding_service,
        vacancy_service,
        matching_service,
        submission_service,
    )
    assert "Мой профиль" in message.answer.await_args.args[0]

    callback.data = "menu:settings"
    await main_menu_callback(
        callback,
        user_service,
        profile_service,
        onboarding_service,
        vacancy_service,
        matching_service,
        submission_service,
    )
    onboarding_service.start.assert_awaited_with(user_id)

    callback.data = "menu:add_job"
    await main_menu_callback(
        callback,
        user_service,
        profile_service,
        onboarding_service,
        vacancy_service,
        matching_service,
        submission_service,
    )
    submission_service.begin.assert_awaited_with(user_id)

    callback.data = "menu:personal_jobs"
    await main_menu_callback(
        callback,
        user_service,
        profile_service,
        onboarding_service,
        vacancy_service,
        matching_service,
        submission_service,
    )
    submission_service.latest_private.assert_awaited_with(user_id)


async def test_manual_vacancy_is_reviewed_and_saved_privately() -> None:
    user_id = uuid4()
    submission_id = uuid4()
    message = fake_message()
    message.text = "Vacancy: Python Developer. We are hiring. Requirements: Python and FastAPI."
    user_service = SimpleNamespace(
        register=AsyncMock(return_value=user_id),
        has_required_consent=AsyncMock(return_value=True),
    )
    submission = SimpleNamespace(
        id=submission_id,
        status="awaiting_confirmation",
        title="Python Developer",
        company="Example",
        location="Yerevan",
        workplace_type="hybrid",
    )
    submission_service = SimpleNamespace(
        begin=AsyncMock(),
        is_awaiting_text=AsyncMock(return_value=True),
        submit=AsyncMock(return_value=SubmissionResult(submission)),
        confirm_private=AsyncMock(return_value=True),
    )

    await add_job_command(message, user_service, submission_service)
    submission_service.begin.assert_awaited_once_with(user_id)

    await apply_profile_edit(
        message,
        user_service,
        SimpleNamespace(apply_pending_edit=AsyncMock()),
        SimpleNamespace(answer=AsyncMock()),
        submission_service,
    )
    assert "Проверьте вакансию" in message.answer.await_args.args[0]

    callback = SimpleNamespace(
        from_user=fake_sender(),
        message=message,
        data=f"vacancy:keep:{submission_id}",
        answer=AsyncMock(),
    )
    await submission_callback(callback, user_service, submission_service)
    submission_service.confirm_private.assert_awaited_once_with(user_id, submission_id, True)
