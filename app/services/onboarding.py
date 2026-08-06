from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.onboarding import OnboardingSession, SearchPreference
from app.db.models.profile import CandidateProfile

QuestionKind = Literal["list", "boolean", "integer", "work_modes", "currency"]


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    prompt: str
    kind: QuestionKind
    skippable: bool = False


QUESTIONS = {
    "desired_roles": Question(
        "desired_roles", "Какие роли ищем? Перечислите через запятую.", "list"
    ),
    "preferred_locations": Question(
        "preferred_locations",
        "Приоритетные города и страны? Например: Армения, Ереван.",
        "list",
    ),
    "work_modes": Question("work_modes", "Какой формат работы подходит?", "work_modes"),
    "allow_international_remote": Question(
        "allow_international_remote",
        "Показывать международные remote-вакансии, доступные из Армении?",
        "boolean",
    ),
    "willing_to_relocate": Question(
        "willing_to_relocate", "Готовы рассматривать релокацию?", "boolean"
    ),
    "relocation_locations": Question(
        "relocation_locations",
        "Куда готовы переехать? Перечислите страны или города.",
        "list",
    ),
    "min_salary": Question("min_salary", "Минимальная желаемая зарплата числом.", "integer", True),
    "salary_currency": Question("salary_currency", "В какой валюте?", "currency"),
    "languages": Question("languages", "Рабочие языки через запятую.", "list", True),
}

BASE_ORDER = [
    "desired_roles",
    "preferred_locations",
    "work_modes",
    "allow_international_remote",
    "willing_to_relocate",
    "relocation_locations",
    "min_salary",
    "salary_currency",
    "languages",
]


@dataclass(frozen=True, slots=True)
class OnboardingStep:
    question: Question | None
    can_go_back: bool
    completed: bool = False


class OnboardingValidationError(Exception):
    pass


class OnboardingService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def start(self, user_id: UUID) -> OnboardingStep:
        async with self._sessions.begin() as session:
            profile_roles = await session.scalar(
                select(CandidateProfile.desired_roles)
                .where(
                    CandidateProfile.user_id == user_id,
                    CandidateProfile.status == "confirmed",
                )
                .order_by(CandidateProfile.confirmed_at.desc())
                .limit(1)
            )
            desired_roles = profile_roles[:20] if profile_roles else []
            flow = await session.get(OnboardingSession, user_id)
            if flow is None or flow.status == "completed":
                flow = OnboardingSession(
                    user_id=user_id,
                    current_question=("preferred_locations" if desired_roles else "desired_roles"),
                    answers={"desired_roles": desired_roles} if desired_roles else {},
                    history=["desired_roles"] if desired_roles else [],
                    status="active",
                )
                await session.merge(flow)
            elif (
                flow.status == "active"
                and flow.current_question == "desired_roles"
                and not flow.answers.get("desired_roles")
                and desired_roles
            ):
                flow.current_question = "preferred_locations"
                flow.answers = {**flow.answers, "desired_roles": desired_roles}
                flow.history = [*flow.history, "desired_roles"]
            return _step(flow)

    async def current(self, user_id: UUID) -> OnboardingStep | None:
        async with self._sessions() as session:
            flow = await session.get(OnboardingSession, user_id)
            return _step(flow) if flow is not None and flow.status == "active" else None

    async def answer(
        self, user_id: UUID, raw_value: str, expected_key: str | None = None
    ) -> OnboardingStep | None:
        async with self._sessions.begin() as session:
            flow = await session.get(OnboardingSession, user_id)
            if flow is None or flow.status != "active":
                return None
            if expected_key is not None and flow.current_question != expected_key:
                return _step(flow)
            question = QUESTIONS[flow.current_question]
            value = _parse_answer(question, raw_value)
            answers = dict(flow.answers)
            answers[question.key] = value
            _prune_answers(answers)
            history = [*flow.history, question.key]
            next_key = _next_key(question.key, answers)
            if next_key is None:
                flow.answers = answers
                flow.history = history
                flow.status = "completed"
                await _save_preferences(session, user_id, answers)
                return OnboardingStep(None, can_go_back=True, completed=True)
            flow.answers = answers
            flow.history = history
            flow.current_question = next_key
            return _step(flow)

    async def skip(self, user_id: UUID) -> OnboardingStep | None:
        async with self._sessions() as session:
            flow = await session.get(OnboardingSession, user_id)
            if flow is None or not QUESTIONS[flow.current_question].skippable:
                return None
        return await self.answer(user_id, "")

    async def back(self, user_id: UUID) -> OnboardingStep | None:
        async with self._sessions.begin() as session:
            flow = await session.get(OnboardingSession, user_id)
            if flow is None or flow.status != "active" or not flow.history:
                return None
            history = list(flow.history)
            previous = history.pop()
            answers = dict(flow.answers)
            answers.pop(previous, None)
            flow.current_question = previous
            flow.history = history
            flow.answers = answers
            return _step(flow)


def _active_order(answers: dict[str, Any]) -> list[str]:
    return [
        key
        for key in BASE_ORDER
        if not (key == "relocation_locations" and answers.get("willing_to_relocate") is not True)
        and not (key == "salary_currency" and not answers.get("min_salary"))
    ]


def _next_key(current: str, answers: dict[str, Any]) -> str | None:
    order = _active_order(answers)
    position = order.index(current)
    return order[position + 1] if position + 1 < len(order) else None


def _parse_answer(question: Question, raw: str) -> Any:
    value = raw.strip()
    if not value and question.skippable:
        return None
    if question.kind == "list":
        items = [item.strip() for item in value.split(",") if item.strip()]
        if not items:
            raise OnboardingValidationError("Укажите хотя бы одно значение.")
        return items[:20]
    if question.kind == "integer":
        try:
            number = int(value)
        except ValueError as exc:
            raise OnboardingValidationError("Введите целое число.") from exc
        if number <= 0:
            raise OnboardingValidationError("Значение должно быть больше нуля.")
        return number
    if question.kind == "boolean":
        if value not in {"yes", "no"}:
            raise OnboardingValidationError("Выберите «Да» или «Нет».")
        return value == "yes"
    if question.kind == "work_modes":
        if value not in {"remote", "hybrid", "office", "any"}:
            raise OnboardingValidationError("Выберите формат кнопкой.")
        return ["remote", "hybrid", "office"] if value == "any" else [value]
    if question.kind == "currency":
        if value not in {"AMD", "USD", "EUR", "RUB"}:
            raise OnboardingValidationError("Выберите валюту кнопкой.")
        return value
    raise OnboardingValidationError("Некорректный ответ.")


def _prune_answers(answers: dict[str, Any]) -> None:
    if answers.get("willing_to_relocate") is not True:
        answers.pop("relocation_locations", None)
    if not answers.get("min_salary"):
        answers.pop("salary_currency", None)


def _step(flow: OnboardingSession) -> OnboardingStep:
    return OnboardingStep(QUESTIONS[flow.current_question], can_go_back=bool(flow.history))


async def _save_preferences(session: AsyncSession, user_id: UUID, answers: dict[str, Any]) -> None:
    preference = SearchPreference(
        user_id=user_id,
        desired_roles=answers.get("desired_roles", []),
        preferred_locations=answers.get("preferred_locations", ["Armenia"]),
        work_modes=answers.get("work_modes", ["remote", "hybrid", "office"]),
        allow_international_remote=answers.get("allow_international_remote", True),
        willing_to_relocate=answers.get("willing_to_relocate", False),
        relocation_locations=answers.get("relocation_locations", []),
        min_salary=answers.get("min_salary"),
        salary_currency=answers.get("salary_currency"),
        languages=answers.get("languages") or [],
        status="active",
    )
    await session.merge(preference)
