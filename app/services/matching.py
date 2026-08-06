from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.matching import VacancyMatch
from app.db.models.onboarding import SearchPreference
from app.db.models.profile import CandidateProfile
from app.db.models.vacancy import Vacancy

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?|лет|года?)\b", re.IGNORECASE)
_GENERIC_ROLE_WORDS = {
    "developer",
    "engineer",
    "разработчик",
    "инженер",
    "specialist",
    "специалист",
}
_SENIORITY_MONTHS = {"junior": 0, "middle": 18, "mid": 18, "senior": 36, "lead": 60}
_TECHNOLOGIES = {
    "python",
    "django",
    "fastapi",
    "flask",
    "php",
    "laravel",
    "java",
    "kotlin",
    "javascript",
    "typescript",
    "react",
    "vue",
    "angular",
    "node.js",
    "nodejs",
    "sql",
    "postgresql",
    "mysql",
    "redis",
    "docker",
    "kubernetes",
    "aws",
    "azure",
    "gcp",
    "git",
    "linux",
    "selenium",
}
_LANGUAGE_ALIASES = {
    "english": {"english", "английский", "անգլերեն"},
    "armenian": {"armenian", "армянский", "հայերեն"},
    "russian": {"russian", "русский", "ռուսերեն"},
    "german": {"german", "немецкий", "գերմաներեն"},
    "french": {"french", "французский", "ֆրանսերեն"},
    "spanish": {"spanish", "испанский", "իսպաներեն"},
}
_ARMENIA_TERMS = {"am", "armenia", "armenian", "yerevan", "ереван", "армения", "հայաստան", "երևան"}
_REMOTE_ALLOWED_TERMS = {
    "worldwide",
    "anywhere",
    "global",
    "europe",
    "emea",
    "armenia",
    "european timezones",
}
_REMOTE_BLOCKED_TERMS = {
    "us only",
    "usa only",
    "united states only",
    "canada only",
    "americas only",
    "latin america only",
    "apac only",
}


class MatchingUnavailableError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MatchCalculation:
    eligible: bool
    score: int
    components: dict[str, int]
    explanations: list[str]
    filter_reasons: list[str]


@dataclass(frozen=True, slots=True)
class RankedVacancy:
    vacancy: Vacancy
    match: VacancyMatch


class MatchingService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = sessions
        self._settings = settings

    async def refresh(self, user_id: UUID) -> int:
        async with self._sessions.begin() as session:
            profile = await session.scalar(
                select(CandidateProfile)
                .where(
                    CandidateProfile.user_id == user_id,
                    CandidateProfile.status == "confirmed",
                )
                .order_by(CandidateProfile.confirmed_at.desc())
                .limit(1)
            )
            if profile is None:
                raise MatchingUnavailableError("profile_missing")
            preference = await session.get(SearchPreference, user_id)
            if preference is None or preference.status != "active":
                raise MatchingUnavailableError("preferences_missing")
            vacancies = list(await session.scalars(select(Vacancy)))
            for vacancy in vacancies:
                calculation = calculate_match(
                    profile, preference, vacancy, self._settings.matching_weights
                )
                fingerprint = _input_hash(profile, preference, vacancy)
                match = await session.scalar(
                    select(VacancyMatch).where(
                        VacancyMatch.user_id == user_id,
                        VacancyMatch.vacancy_id == vacancy.id,
                    )
                )
                if match is None:
                    match = VacancyMatch(
                        user_id=user_id,
                        vacancy_id=vacancy.id,
                        profile_id=profile.id,
                        eligible=calculation.eligible,
                        score=calculation.score,
                        components=calculation.components,
                        explanations=calculation.explanations,
                        filter_reasons=calculation.filter_reasons,
                        input_hash=fingerprint,
                    )
                    session.add(match)
                else:
                    if match.input_hash != fingerprint:
                        match.presented_at = None
                    match.profile_id = profile.id
                    match.eligible = calculation.eligible
                    match.score = calculation.score
                    match.components = calculation.components
                    match.explanations = calculation.explanations
                    match.filter_reasons = calculation.filter_reasons
                    match.input_hash = fingerprint
                    match.calculated_at = datetime.now(UTC)
            return len(vacancies)

    async def new_matches(self, user_id: UUID, limit: int = 5) -> list[RankedVacancy]:
        await self.refresh(user_id)
        async with self._sessions.begin() as session:
            rows = (
                await session.execute(
                    select(VacancyMatch, Vacancy)
                    .join(Vacancy, Vacancy.id == VacancyMatch.vacancy_id)
                    .where(
                        VacancyMatch.user_id == user_id,
                        VacancyMatch.eligible.is_(True),
                        VacancyMatch.score >= self._settings.default_match_threshold,
                        VacancyMatch.presented_at.is_(None),
                    )
                    .order_by(
                        VacancyMatch.score.desc(),
                        Vacancy.published_at.desc().nullslast(),
                        Vacancy.last_seen_at.desc(),
                    )
                    .limit(limit)
                )
            ).all()
            now = datetime.now(UTC)
            result = []
            for match, vacancy in rows:
                match.presented_at = now
                result.append(RankedVacancy(vacancy=vacancy, match=match))
            return result


def calculate_match(
    profile: CandidateProfile,
    preference: SearchPreference,
    vacancy: Vacancy,
    weights: dict[str, int],
    *,
    now: datetime | None = None,
) -> MatchCalculation:
    current_time = now or datetime.now(UTC)
    text = f"{vacancy.title}\n{vacancy.description}"
    filter_reasons: list[str] = []

    if vacancy.expires_at is not None and _as_utc(vacancy.expires_at) <= current_time:
        filter_reasons.append("Вакансия уже истекла")

    role_score = _role_score(profile, preference, vacancy)
    if preference.desired_roles and role_score == 0:
        filter_reasons.append("Роль не соответствует выбранным направлениям")

    location_score, location_reason = _location_score(preference, vacancy)
    if location_reason is not None:
        filter_reasons.append(location_reason)

    salary_score, salary_reason = _salary_score(preference, vacancy)
    if salary_reason is not None:
        filter_reasons.append(salary_reason)

    skill_score, matched_skills, missing_skills = _skill_score(profile, text)
    experience_score = _experience_score(profile.total_experience_months, text)
    language_score, missing_languages = _language_score(profile, preference, text)
    components = {
        "skills": skill_score,
        "experience": experience_score,
        "role": role_score,
        "location": location_score,
        "language": language_score,
        "salary": salary_score,
    }
    score = round(sum(components[name] * weights[name] for name in components) / 100)

    explanations: list[str] = []
    if role_score >= 75:
        explanations.append("Роль соответствует выбранному направлению")
    if matched_skills:
        explanations.append(f"Совпавшие навыки: {', '.join(matched_skills[:6])}")
    if missing_skills:
        explanations.append(f"Не найдены в профиле: {', '.join(missing_skills[:4])}")
    if location_score >= 80:
        explanations.append("Локация и формат работы подходят")
    if missing_languages:
        explanations.append(f"Нужно проверить языки: {', '.join(missing_languages)}")
    if vacancy.salary_min is None and vacancy.salary_max is None:
        explanations.append("Зарплата в вакансии не указана")
    return MatchCalculation(
        eligible=not filter_reasons,
        score=score,
        components=components,
        explanations=explanations[:6],
        filter_reasons=filter_reasons,
    )


def _role_score(profile: CandidateProfile, preference: SearchPreference, vacancy: Vacancy) -> int:
    title_tokens = set(_tokens(vacancy.title))
    roles = [*preference.desired_roles, *profile.desired_roles]
    if profile.current_title:
        roles.append(profile.current_title)
    if not roles:
        return 70
    best = 0
    for role in roles:
        role_tokens = set(_tokens(role))
        if not role_tokens:
            continue
        meaningful = role_tokens - _GENERIC_ROLE_WORDS
        if role_tokens <= title_tokens:
            best = max(best, 100)
        elif meaningful & title_tokens:
            best = max(best, 85)
        elif role_tokens & title_tokens:
            best = max(best, 60)
    candidate_skills = {_normalize(str(item.get("name", ""))) for item in profile.skills}
    if any(skill and _contains_phrase(vacancy.title, skill) for skill in candidate_skills):
        best = max(best, 75)
    return best


def _skill_score(profile: CandidateProfile, vacancy_text: str) -> tuple[int, list[str], list[str]]:
    candidate = {
        _normalize(str(item.get("name", ""))): str(item.get("name", "")).strip()
        for item in profile.skills
        if str(item.get("name", "")).strip()
    }
    mentioned = {
        skill
        for skill in {*_TECHNOLOGIES, *candidate}
        if skill and _contains_phrase(vacancy_text, skill)
    }
    if not mentioned:
        return 65, [], []
    matched_keys = sorted(mentioned & set(candidate))
    missing = sorted(mentioned - set(candidate))
    score = round(100 * len(matched_keys) / len(mentioned))
    return score, [candidate[key] for key in matched_keys], missing


def _experience_score(months: int | None, vacancy_text: str) -> int:
    requirements = [int(value) * 12 for value in _YEARS_RE.findall(vacancy_text)]
    if not requirements:
        seniority = next(
            (
                required
                for word, required in _SENIORITY_MONTHS.items()
                if word in _tokens(vacancy_text)
            ),
            None,
        )
        if seniority is None:
            return 75
        required_months = seniority
    else:
        required_months = max(requirements)
    if required_months == 0:
        return 100
    if months is None:
        return 40
    return min(100, round(100 * months / required_months))


def _location_score(preference: SearchPreference, vacancy: Vacancy) -> tuple[int, str | None]:
    workplace = _normalize(vacancy.workplace_type)
    if (
        preference.work_modes
        and workplace not in {"", "unspecified"}
        and workplace not in {_normalize(mode) for mode in preference.work_modes}
    ):
        return 0, "Формат работы не выбран в настройках"

    location_text = _normalize(f"{vacancy.location or ''} {vacancy.country_code or ''}")
    preferred = [_normalize(item) for item in preference.preferred_locations]
    relocation = [_normalize(item) for item in preference.relocation_locations]
    location_matches = any(item and item in location_text for item in [*preferred, *relocation])
    in_armenia = vacancy.country_code == "AM" or bool(set(_tokens(location_text)) & _ARMENIA_TERMS)

    if workplace == "remote":
        scope = _normalize(vacancy.remote_scope or "")
        if scope and any(term in scope for term in _REMOTE_BLOCKED_TERMS):
            return 0, "Remote-вакансия недоступна из Армении"
        if scope and not (
            any(term in scope for term in _REMOTE_ALLOWED_TERMS)
            or bool(set(_tokens(scope)) & _ARMENIA_TERMS)
        ):
            return 0, "Remote-зона не подтверждает доступность из Армении"
        if not preference.allow_international_remote and not in_armenia:
            return 0, "Международная удалённая работа отключена"
        return (100 if in_armenia or not scope else 90), None

    if in_armenia or location_matches:
        return 100, None
    if preference.willing_to_relocate and any(item in location_text for item in relocation):
        return 80, None
    if workplace in {"office", "hybrid"}:
        return 0, "Офис или hybrid находятся вне выбранной локации"
    return 55, None


def _language_score(
    profile: CandidateProfile, preference: SearchPreference, vacancy_text: str
) -> tuple[int, list[str]]:
    candidate_text = " ".join(
        [*preference.languages, *(str(item.get("name", "")) for item in profile.languages)]
    )
    candidate = {
        canonical
        for canonical, aliases in _LANGUAGE_ALIASES.items()
        if any(_contains_phrase(candidate_text, alias) for alias in aliases)
    }
    required = {
        canonical
        for canonical, aliases in _LANGUAGE_ALIASES.items()
        if any(_contains_phrase(vacancy_text, alias) for alias in aliases)
    }
    if not required:
        return 100, []
    missing = sorted(required - candidate)
    return round(100 * len(required & candidate) / len(required)), missing


def _salary_score(preference: SearchPreference, vacancy: Vacancy) -> tuple[int, str | None]:
    if preference.min_salary is None:
        return 100, None
    if vacancy.salary_min is None and vacancy.salary_max is None:
        return 65, None
    if not preference.salary_currency or not vacancy.salary_currency:
        return 65, None
    if preference.salary_currency.casefold() != vacancy.salary_currency.casefold():
        return 65, None
    maximum = vacancy.salary_max if vacancy.salary_max is not None else vacancy.salary_min
    if maximum is not None and maximum < preference.min_salary:
        return 0, "Максимальная зарплата ниже указанного минимума"
    minimum = vacancy.salary_min if vacancy.salary_min is not None else maximum
    if minimum is not None and minimum >= preference.min_salary:
        return 100, None
    return 80, None


def _input_hash(profile: CandidateProfile, preference: SearchPreference, vacancy: Vacancy) -> str:
    data = {
        "profile": {
            "id": str(profile.id),
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            "roles": profile.desired_roles,
            "title": profile.current_title,
            "experience": profile.total_experience_months,
            "skills": profile.skills,
            "languages": profile.languages,
        },
        "preference": {
            "updated_at": preference.updated_at.isoformat() if preference.updated_at else None,
            "roles": preference.desired_roles,
            "locations": preference.preferred_locations,
            "modes": preference.work_modes,
            "remote": preference.allow_international_remote,
            "relocation": preference.relocation_locations,
            "salary": preference.min_salary,
            "currency": preference.salary_currency,
            "languages": preference.languages,
        },
        "vacancy": {
            "fingerprint": vacancy.fingerprint,
            "last_seen_at": vacancy.last_seen_at.isoformat() if vacancy.last_seen_at else None,
        },
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _tokens(value: str) -> list[str]:
    return _WORD_RE.findall(_normalize(value))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = _normalize(text)
    wanted = _normalize(phrase)
    return bool(wanted) and re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", normalized) is not None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
