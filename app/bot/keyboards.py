from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Принять и продолжить", callback_data="consent:accept")],
            [InlineKeyboardButton(text="Политика конфиденциальности", callback_data="privacy")],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новые вакансии", callback_data="menu:new_jobs")],
            [InlineKeyboardButton(text="Мой профиль", callback_data="menu:profile")],
            [InlineKeyboardButton(text="Настройки", callback_data="menu:settings")],
        ]
    )


def profile_review_keyboard(profile_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data=f"profile:confirm:{profile_id}"
                ),
                InlineKeyboardButton(text="Исправить", callback_data=f"profile:edit:{profile_id}"),
            ]
        ]
    )


def profile_edit_keyboard(profile_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Имя", callback_data=f"profile:field:n:{profile_id}")],
            [
                InlineKeyboardButton(
                    text="Текущая должность",
                    callback_data=f"profile:field:t:{profile_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Желаемые роли",
                    callback_data=f"profile:field:r:{profile_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Описание",
                    callback_data=f"profile:field:s:{profile_id}",
                )
            ],
        ]
    )
