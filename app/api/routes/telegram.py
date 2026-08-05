import structlog
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.security import secrets_match
from app.services.telegram_users import TelegramUpdateService, TelegramUserService

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = structlog.get_logger()


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = request.app.state.settings
    expected = settings.telegram_webhook_secret
    expected_value = expected.get_secret_value() if expected is not None else ""
    if not expected_value or not secrets_match(x_telegram_bot_api_secret_token, expected_value):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")

    bot: Bot | None = request.app.state.bot
    dispatcher: Dispatcher | None = request.app.state.dispatcher
    if bot is None or dispatcher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot unavailable"
        )

    update = Update.model_validate(await request.json(), context={"bot": bot})
    logger.info("telegram_update_received", telegram_update_id=update.update_id)
    update_service: TelegramUpdateService = request.app.state.telegram_update_service
    if not await update_service.claim(update.update_id):
        return {"ok": True}
    try:
        user_service: TelegramUserService = request.app.state.telegram_user_service
        await dispatcher.feed_update(
            bot,
            update,
            user_service=user_service,
            resume_service=request.app.state.resume_service,
            resume_queue=request.app.state.resume_queue,
        )
        await update_service.complete(update.update_id)
    except Exception:
        await update_service.release(update.update_id)
        raise
    return {"ok": True}
