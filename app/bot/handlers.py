from html import escape
from io import BytesIO
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InaccessibleMessage, Message, Update

from app.bot.keyboards import (
    consent_keyboard,
    main_menu_keyboard,
    onboarding_keyboard,
    profile_edit_keyboard,
    profile_review_keyboard,
)
from app.services.onboarding import OnboardingService, OnboardingStep, OnboardingValidationError
from app.services.profiles import ProfileService
from app.services.queue import ResumeQueue
from app.services.resumes import ResumeService, ResumeUpload, ResumeValidationError
from app.services.telegram_users import (
    BetaAccessDeniedError,
    TelegramIdentity,
    TelegramUserService,
)
from app.services.vacancies import VacancyIngestionService

PRIVACY_TEXT = (
    "<b>Политика конфиденциальности</b>\n\n"
    "Бот хранит профиль и приватный файл резюме для персонального поиска вакансий. "
    "После вашего согласия текст резюме передаётся DeepSeek для структурированного анализа. "
    "Данные не используются для автоматической отправки откликов. Вы сможете удалить "
    "резюме и аккаунт, отключить AI-обработку и уведомления."
)


def identity_from_message(message: Message) -> TelegramIdentity | None:
    sender = message.from_user
    if sender is None:
        return None
    return TelegramIdentity(
        telegram_user_id=sender.id,
        username=sender.username,
        first_name=sender.first_name,
        last_name=sender.last_name,
        locale=sender.language_code,
    )


async def start(message: Message, user_service: TelegramUserService) -> None:
    identity = identity_from_message(message)
    if identity is None:
        return
    try:
        await user_service.register(identity)
    except BetaAccessDeniedError:
        await message.answer("Бот пока работает в закрытой beta-версии.")
        return
    await message.answer(
        "<b>Персональный поиск вакансий</b>\n\n"
        "Я анализирую резюме, уточняю предпочтения и присылаю объяснимые совпадения. "
        "Перед загрузкой резюме необходимо принять условия обработки данных.",
        reply_markup=consent_keyboard(),
    )


async def privacy_command(message: Message) -> None:
    await message.answer(PRIVACY_TEXT, reply_markup=consent_keyboard())


async def privacy_callback(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(PRIVACY_TEXT, reply_markup=consent_keyboard())
    await callback.answer()


async def accept_consent(
    callback: CallbackQuery,
    event_update: Update,
    user_service: TelegramUserService,
) -> None:
    sender = callback.from_user
    if callback.message is None:
        await callback.answer()
        return
    identity = TelegramIdentity(
        telegram_user_id=sender.id,
        username=sender.username,
        first_name=sender.first_name,
        last_name=sender.last_name,
        locale=sender.language_code,
    )
    try:
        user_id = await user_service.register(identity)
    except BetaAccessDeniedError:
        await callback.answer("Доступ ограничен beta-списком", show_alert=True)
        return
    await user_service.grant_required_consent(user_id, event_update.update_id)
    await callback.message.answer("Согласие сохранено. Теперь отправьте резюме в PDF или DOCX.")
    await callback.answer("Готово")


async def document_gate(
    message: Message,
    user_service: TelegramUserService,
    resume_service: ResumeService,
    resume_queue: ResumeQueue,
) -> None:
    identity = identity_from_message(message)
    if identity is None:
        return
    try:
        user_id = await user_service.register(identity)
    except BetaAccessDeniedError:
        await message.answer("Бот пока работает в закрытой beta-версии.")
        return
    if not await user_service.has_required_consent(user_id):
        await message.answer(
            "Сначала примите условия обработки данных.", reply_markup=consent_keyboard()
        )
        return
    document = message.document
    if document is None:
        return
    if document.file_size is None or document.file_size > resume_service.max_bytes:
        await message.answer("Файл слишком большой.")
        return
    bot = message.bot
    if bot is None:
        return
    buffer = BytesIO()
    await bot.download(document.file_id, destination=buffer)
    try:
        resume_id = await resume_service.save(
            user_id,
            ResumeUpload(
                telegram_file_id=document.file_id,
                filename=document.file_name or "resume",
                declared_media_type=document.mime_type,
                declared_size=document.file_size,
                data=buffer.getvalue(),
            ),
        )
    except ResumeValidationError:
        await message.answer(
            "Файл не принят. Отправьте корректный PDF или DOCX установленного размера."
        )
        return
    await resume_service.mark_queued(resume_id)
    await resume_queue.enqueue(resume_id)
    await message.answer("Резюме принято и поставлено в очередь на обработку.")


async def menu(message: Message) -> None:
    await message.answer("Главное меню", reply_markup=main_menu_keyboard())


async def help_command(message: Message) -> None:
    await message.answer("Команды: /start, /menu, /privacy, /help, /cancel, /delete_me")


async def cancel_command(message: Message) -> None:
    await message.answer("Текущее действие отменено.", reply_markup=main_menu_keyboard())


async def delete_command(message: Message) -> None:
    await message.answer("Безопасное удаление данных будет добавлено в этапе 12.")


async def main_menu_callback(
    callback: CallbackQuery,
    user_service: TelegramUserService,
    profile_service: ProfileService,
    onboarding_service: OnboardingService,
    vacancy_service: VacancyIngestionService,
) -> None:
    identity = TelegramIdentity(
        telegram_user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        locale=callback.from_user.language_code,
    )
    try:
        user_id = await user_service.register(identity)
    except BetaAccessDeniedError:
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    if callback.message is None:
        await callback.answer()
        return

    action = (callback.data or "").removeprefix("menu:")
    if action == "new_jobs":
        vacancies = await vacancy_service.latest()
        await callback.message.answer(
            _vacancy_list(vacancies),
            reply_markup=main_menu_keyboard(),
            disable_web_page_preview=True,
        )
    elif action == "profile":
        profile = await profile_service.latest_confirmed(user_id)
        text = (
            _confirmed_profile_summary(profile)
            if profile is not None
            else "Подтверждённый профиль пока не найден. Отправьте резюме для обработки."
        )
        await callback.message.answer(text, reply_markup=main_menu_keyboard())
    elif action == "settings":
        await callback.message.answer("Изменим настройки поиска.")
        await _send_onboarding_step(callback.message, await onboarding_service.start(user_id))
    else:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return
    await callback.answer()


async def confirm_profile(
    callback: CallbackQuery,
    user_service: TelegramUserService,
    profile_service: ProfileService,
    onboarding_service: OnboardingService,
) -> None:
    identity = TelegramIdentity(
        telegram_user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        locale=callback.from_user.language_code,
    )
    try:
        user_id = await user_service.register(identity)
        profile_id = UUID((callback.data or "").rsplit(":", 1)[-1])
    except (BetaAccessDeniedError, ValueError):
        await callback.answer("Профиль недоступен", show_alert=True)
        return
    if not await profile_service.confirm(user_id, profile_id):
        await callback.answer("Профиль уже изменён или недоступен", show_alert=True)
        return
    if callback.message is not None:
        step = await onboarding_service.start(user_id)
        await callback.message.answer("Профиль подтверждён. Настроим поиск вакансий.")
        await _send_onboarding_step(callback.message, step)
    await callback.answer("Готово")


async def edit_profile_menu(callback: CallbackQuery) -> None:
    try:
        profile_id = UUID((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Профиль недоступен", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(
            "Что нужно исправить?", reply_markup=profile_edit_keyboard(str(profile_id))
        )
    await callback.answer()


async def begin_profile_field_edit(
    callback: CallbackQuery,
    user_service: TelegramUserService,
    profile_service: ProfileService,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Некорректное действие", show_alert=True)
        return
    field_codes = {
        "n": "full_name",
        "t": "current_title",
        "r": "desired_roles",
        "s": "professional_summary",
    }
    field, raw_profile_id = field_codes.get(parts[2]), parts[3]
    if field is None:
        await callback.answer("Некорректное поле", show_alert=True)
        return
    identity = TelegramIdentity(
        telegram_user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        locale=callback.from_user.language_code,
    )
    try:
        user_id = await user_service.register(identity)
        profile_id = UUID(raw_profile_id)
    except (BetaAccessDeniedError, ValueError):
        await callback.answer("Профиль недоступен", show_alert=True)
        return
    if not await profile_service.begin_edit(user_id, profile_id, field):
        await callback.answer("Поле недоступно", show_alert=True)
        return
    prompts = {
        "full_name": "Отправьте правильное имя одним сообщением.",
        "current_title": "Отправьте текущую должность одним сообщением.",
        "desired_roles": "Отправьте желаемые роли через запятую.",
        "professional_summary": "Отправьте исправленное профессиональное описание.",
    }
    if callback.message is not None:
        await callback.message.answer(prompts[field])
    await callback.answer()


async def apply_profile_edit(
    message: Message,
    user_service: TelegramUserService,
    profile_service: ProfileService,
    onboarding_service: OnboardingService,
) -> None:
    identity = identity_from_message(message)
    if identity is None or message.text is None:
        return
    try:
        user_id = await user_service.register(identity)
    except BetaAccessDeniedError:
        return
    profile = await profile_service.apply_pending_edit(user_id, message.text)
    if profile is not None:
        await message.answer(
            "Изменение сохранено. Подтвердите профиль или исправьте другое поле.",
            reply_markup=profile_review_keyboard(str(profile.id)),
        )
        return
    try:
        step = await onboarding_service.answer(user_id, message.text)
    except OnboardingValidationError as exc:
        await message.answer(str(exc))
        return
    if step is not None:
        await _send_onboarding_step(message, step)


async def onboarding_command(
    message: Message,
    user_service: TelegramUserService,
    onboarding_service: OnboardingService,
) -> None:
    identity = identity_from_message(message)
    if identity is None:
        return
    try:
        user_id = await user_service.register(identity)
    except BetaAccessDeniedError:
        return
    await _send_onboarding_step(message, await onboarding_service.start(user_id))


async def onboarding_callback(
    callback: CallbackQuery,
    user_service: TelegramUserService,
    onboarding_service: OnboardingService,
) -> None:
    identity = TelegramIdentity(
        telegram_user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        locale=callback.from_user.language_code,
    )
    try:
        user_id = await user_service.register(identity)
    except BetaAccessDeniedError:
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    data = callback.data or ""
    try:
        if data.startswith("onboard:wm:"):
            action = data.removeprefix("onboard:wm:")
            if action == "done":
                step = await onboarding_service.submit_work_modes(user_id)
            else:
                step = await onboarding_service.toggle_work_mode(user_id, action)
                if (
                    callback.message is not None
                    and not isinstance(callback.message, InaccessibleMessage)
                    and step is not None
                    and step.question is not None
                ):
                    await callback.message.edit_reply_markup(
                        reply_markup=onboarding_keyboard(
                            step.question, step.can_go_back, step.selected_values
                        )
                    )
                await callback.answer()
                return
        elif data == "onboard:back":
            step = await onboarding_service.back(user_id)
        elif data == "onboard:skip":
            step = await onboarding_service.skip(user_id)
        else:
            parts = data.split(":", 3)
            if len(parts) != 4 or parts[1] != "a":
                await callback.answer("Некорректное действие", show_alert=True)
                return
            step = await onboarding_service.answer(user_id, parts[3], expected_key=parts[2])
    except OnboardingValidationError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message is not None and step is not None:
        await _send_onboarding_step(callback.message, step)
    await callback.answer()


def _confirmed_profile_summary(profile: Any) -> str:
    roles = ", ".join(profile.desired_roles) or "не указаны"
    skills = ", ".join(item.get("name", "") for item in profile.skills[:12]) or "не указаны"
    return (
        "<b>Мой профиль</b>\n\n"
        f"Имя: {escape(profile.full_name or 'не указано')}\n"
        f"Текущая должность: {escape(profile.current_title or 'не указана')}\n"
        f"Желаемые роли: {escape(roles)}\n"
        f"Навыки: {escape(skills)}"
    )


def _vacancy_list(vacancies: list[Any]) -> str:
    if not vacancies:
        return "Новых вакансий пока нет. Источники будут проверены по расписанию."
    items = []
    for vacancy in vacancies:
        location = f" — {escape(vacancy.location)}" if vacancy.location else ""
        items.append(
            f'<a href="{escape(vacancy.canonical_url, quote=True)}">'
            f"{escape(vacancy.title)}</a> — {escape(vacancy.company)}{location}"
        )
    return (
        "<b>Последние собранные вакансии</b>\n\n"
        + "\n\n".join(items)
        + "\n\nПерсональное ранжирование будет добавлено на следующем этапе."
    )


async def _send_onboarding_step(
    message: Message | InaccessibleMessage, step: OnboardingStep
) -> None:
    if step.completed:
        await message.answer(
            "Настройки поиска сохранены. Приоритет: Армения и доступная международная удалёнка.",
            reply_markup=main_menu_keyboard(),
        )
        return
    if step.question is not None:
        await message.answer(
            step.question.prompt,
            reply_markup=onboarding_keyboard(step.question, step.can_go_back, step.selected_values),
        )


def create_router() -> Router:
    router = Router(name="core")
    router.message.register(start, CommandStart())
    router.message.register(privacy_command, Command("privacy"))
    router.callback_query.register(privacy_callback, F.data == "privacy")
    router.callback_query.register(accept_consent, F.data == "consent:accept")
    router.message.register(document_gate, F.document)
    router.message.register(menu, Command("menu"))
    router.message.register(help_command, Command("help"))
    router.message.register(cancel_command, Command("cancel"))
    router.message.register(delete_command, Command("delete_me"))
    router.message.register(onboarding_command, Command("onboarding"))
    router.callback_query.register(main_menu_callback, F.data.startswith("menu:"))
    router.callback_query.register(confirm_profile, F.data.startswith("profile:confirm:"))
    router.callback_query.register(edit_profile_menu, F.data.startswith("profile:edit:"))
    router.callback_query.register(begin_profile_field_edit, F.data.startswith("profile:field:"))
    router.message.register(apply_profile_edit, F.text)
    router.callback_query.register(onboarding_callback, F.data.startswith("onboard:"))
    return router
