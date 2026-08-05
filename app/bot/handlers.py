from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, Update

from app.bot.keyboards import consent_keyboard, main_menu_keyboard
from app.services.queue import ResumeQueue
from app.services.resumes import ResumeService, ResumeUpload, ResumeValidationError
from app.services.telegram_users import (
    BetaAccessDeniedError,
    TelegramIdentity,
    TelegramUserService,
)

PRIVACY_TEXT = (
    "<b>Политика конфиденциальности</b>\n\n"
    "Бот хранит профиль и приватный файл резюме для персонального поиска вакансий. "
    "После вашего согласия текст резюме передаётся OpenAI для структурированного анализа. "
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
    return router
