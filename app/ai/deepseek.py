import asyncio
import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai.provider import AIProviderError, AIResult
from app.ai.schemas import CandidateProfileData

PROMPT_VERSION = "resume-profile-v2"
SYSTEM_PROMPT = """You extract facts from resumes. Return one JSON object only.
The JSON must follow the supplied example shape and nested object types exactly. Never invent
experience, dates, skills, education, contacts, achievements, or preferences. Use null or
empty arrays when the resume does not provide a value. Keep evidence concise and derived only
from the resume. In particular, every skill must be an object, never a plain string.
JSON example:
{"full_name":null,"current_title":null,"desired_roles":[],"professional_summary":null,
"total_experience_months":null,
"skills":[{"name":"Python","level":null,"experience_months":null,"evidence":"Listed in skills"}],
"work_experience":[{"company":null,"title":"Software Developer","start_date":null,
"end_date":null,"responsibilities":[],"achievements":[],"technologies":[]}],
"projects":[{"name":"Example project","description":null,"technologies":[]}],
"education":[{"institution":"Example institution","degree":null,"field":null,
"start_date":null,"end_date":null}],
"languages":[{"name":"English","level":null}],"location":null,
"contacts":{"email":null,"phone":null,"linkedin":null,"github":null}}"""


class DeepSeekAIProvider:
    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        max_input_chars: int = 120_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._max_retries = max_retries
        self._max_input_chars = max_input_chars
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def parse_resume(self, text: str) -> AIResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Parse this resume into JSON:\n\n{text[: self._max_input_chars]}",
                },
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 6000,
        }
        for attempt in range(self._max_retries + 1):
            response = await self._request(payload)
            try:
                return self._decode_response(response)
            except AIProviderError as exc:
                if exc.code == "empty_response" and attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise
        raise AIProviderError("empty_response")

    def _decode_response(self, response: httpx.Response) -> AIResult:
        try:
            body: dict[str, Any] = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise AIProviderError("empty_response")
            profile = CandidateProfileData.model_validate(_normalize_profile(json.loads(content)))
            usage = body.get("usage") or {}
            return AIResult(
                profile=profile,
                request_id=str(body.get("id")) if body.get("id") else None,
                input_tokens=_optional_int(usage.get("prompt_tokens")),
                output_tokens=_optional_int(usage.get("completion_tokens")),
            )
        except AIProviderError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise AIProviderError("invalid_response") from exc

    async def _request(self, payload: dict[str, Any]) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.RequestError as exc:
                if attempt == self._max_retries:
                    raise AIProviderError("timeout") from exc
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise AIProviderError("temporarily_unavailable")
            if response.status_code == 402:
                raise AIProviderError("insufficient_balance")
            if response.is_error:
                raise AIProviderError("request_rejected")
            return response
        raise AIProviderError("temporarily_unavailable")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _normalize_profile(value: object) -> object:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    skills = normalized.get("skills")
    if isinstance(skills, list):
        normalized["skills"] = [
            {"name": skill, "level": None, "experience_months": None, "evidence": None}
            if isinstance(skill, str)
            else skill
            for skill in skills
        ]
    return normalized
