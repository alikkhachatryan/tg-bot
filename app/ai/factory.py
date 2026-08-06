from app.ai.deepseek import DeepSeekAIProvider
from app.ai.fake import FakeAIProvider
from app.ai.provider import AIProvider
from app.core.config import Settings


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "deepseek":
        if settings.ai_api_key is None:
            raise RuntimeError("AI_API_KEY is required for DeepSeek")
        return DeepSeekAIProvider(
            api_key=settings.ai_api_key.get_secret_value(),
            model=settings.ai_model,
            base_url=settings.ai_base_url,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
            max_input_chars=settings.ai_max_input_chars,
        )
    return FakeAIProvider()
