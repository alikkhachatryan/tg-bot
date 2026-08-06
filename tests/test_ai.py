import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.ai.deepseek import DeepSeekAIProvider
from app.ai.factory import create_ai_provider
from app.ai.fake import FakeAIProvider
from app.ai.provider import AIProviderError
from app.core.config import Settings


def deepseek_response(content: str, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={
            "id": "request-123",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40},
        },
    )


async def test_deepseek_returns_validated_profile() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        return deepseek_response(
            json.dumps(
                {
                    "full_name": "Test User",
                    "current_title": "Python Developer",
                    "skills": [{"name": "Python", "evidence": "Used at work"}],
                }
            )
        )

    client = httpx.AsyncClient(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handler)
    )
    provider = DeepSeekAIProvider(
        api_key="secret",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        timeout_seconds=10,
        max_retries=0,
        client=client,
    )
    try:
        result = await provider.parse_resume("Python developer resume")
    finally:
        await client.aclose()

    assert result.profile.current_title == "Python Developer"
    assert result.request_id == "request-123"
    assert result.input_tokens == 100


async def test_deepseek_rejects_invalid_or_empty_json() -> None:
    for content, code in [("not-json", "invalid_response"), ("", "empty_response")]:
        client = httpx.AsyncClient(
            base_url="https://api.deepseek.com",
            transport=httpx.MockTransport(lambda request, value=content: deepseek_response(value)),
        )
        provider = DeepSeekAIProvider(
            api_key="secret",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            timeout_seconds=10,
            max_retries=0,
            client=client,
        )
        try:
            with pytest.raises(AIProviderError) as error:
                await provider.parse_resume("resume")
            assert error.value.code == code
        finally:
            await client.aclose()


async def test_deepseek_retries_temporary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return deepseek_response('{"current_title":"Backend Developer"}')

    sleep = AsyncMock()
    monkeypatch.setattr("app.ai.deepseek.asyncio.sleep", sleep)
    client = httpx.AsyncClient(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handler)
    )
    provider = DeepSeekAIProvider(
        api_key="secret",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        timeout_seconds=10,
        max_retries=1,
        client=client,
    )
    try:
        result = await provider.parse_resume("resume")
    finally:
        await client.aclose()
    assert result.profile.current_title == "Backend Developer"
    sleep.assert_awaited_once_with(1)


def test_ai_factory_defaults_to_fake_and_builds_deepseek() -> None:
    fake = create_ai_provider(Settings(_env_file=None))
    assert isinstance(fake, FakeAIProvider)
    deepseek = create_ai_provider(
        Settings(
            _env_file=None,
            ai_provider="deepseek",
            ai_api_key=SecretStr("test-key"),
        )
    )
    assert isinstance(deepseek, DeepSeekAIProvider)
