from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.onboarding import Question


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


def onboarding_keyboard(
    question: Question, can_go_back: bool, selected_values: tuple[str, ...] = ()
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if question.kind == "boolean":
        rows.append(
            [
                InlineKeyboardButton(text="Да", callback_data=f"onboard:a:{question.key}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"onboard:a:{question.key}:no"),
            ]
        )
    elif question.kind == "work_modes":
        for value, label in (("remote", "Remote"), ("hybrid", "Hybrid"), ("office", "Office")):
            marker = "✅ " if value in selected_values else ""
            rows.append(
                [InlineKeyboardButton(text=f"{marker}{label}", callback_data=f"onboard:wm:{value}")]
            )
        rows.append([InlineKeyboardButton(text="Продолжить", callback_data="onboard:wm:done")])
    elif question.kind == "currency":
        rows.append(
            [
                InlineKeyboardButton(text=value, callback_data=f"onboard:a:{question.key}:{value}")
                for value in ("AMD", "USD", "EUR", "RUB")
            ]
        )
    controls: list[InlineKeyboardButton] = []
    if can_go_back:
        controls.append(InlineKeyboardButton(text="Назад", callback_data="onboard:back"))
    if question.skippable:
        controls.append(InlineKeyboardButton(text="Пропустить", callback_data="onboard:skip"))
    if controls:
        rows.append(controls)
    return InlineKeyboardMarkup(inline_keyboard=rows)
