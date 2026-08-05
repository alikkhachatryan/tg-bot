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
