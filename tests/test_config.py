import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_defaults_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None, app_env="development")

    assert settings.app_env == "development"
    assert settings.ai_provider == "fake"
    assert settings.ai_model == "deepseek-v4-flash"
    assert settings.beta_mode is True


def test_beta_ids_are_parsed() -> None:
    settings = Settings(_env_file=None, beta_telegram_ids="10, 20,30")

    assert settings.beta_user_ids == frozenset({10, 20, 30})


def test_empty_beta_ids_are_supported() -> None:
    assert Settings(_env_file=None).beta_user_ids == frozenset()


def test_vacancy_source_csv_settings_are_parsed() -> None:
    settings = Settings(
        _env_file=None,
        vacancy_sources="hh, remotive",
        hh_focus_locations="Armenia, Yerevan",
        greenhouse_boards="company-one,company-two",
    )

    assert settings.enabled_vacancy_sources == ("hh", "remotive")
    assert settings.hh_location_names == ("Armenia", "Yerevan")
    assert settings.greenhouse_board_tokens == ("company-one", "company-two")


def test_deepseek_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="AI_API_KEY"):
        Settings(_env_file=None, ai_provider="deepseek")


def test_production_rejects_unsafe_defaults() -> None:
    with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
        Settings(_env_file=None, app_env="production")


def test_complete_production_configuration_is_accepted() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_secret_key=SecretStr("a-strong-application-secret"),
        telegram_bot_token=SecretStr("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"),
        telegram_webhook_url="https://bot.example.com/webhook",
        telegram_webhook_secret=SecretStr("x" * 32),
        ai_provider="deepseek",
        ai_api_key=SecretStr("test-api-key"),
        storage_driver="s3",
        s3_endpoint="https://s3.example.com",
        s3_bucket="private-resumes",
        s3_access_key=SecretStr("access"),
        s3_secret_key=SecretStr("secret"),
        admin_password_hash=SecretStr("hashed-password"),
    )

    assert settings.is_production is True
