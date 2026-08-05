from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app


class StubUpdateService:
    def __init__(self, *, claimed: bool = True) -> None:
        self.claim = AsyncMock(return_value=claimed)
        self.complete = AsyncMock()
        self.release = AsyncMock()


class StubDispatcher:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def feed_update(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        if self._fail:
            raise RuntimeError("handler failed")


def webhook_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        beta_mode=False,
        telegram_bot_token=SecretStr("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"),
        telegram_webhook_secret=SecretStr("webhook-secret"),
    )


def test_webhook_rejects_invalid_secret() -> None:
    app = create_app(webhook_settings())

    with TestClient(app) as client:
        response = client.post("/telegram/webhook", json={"update_id": 1})

    assert response.status_code == 401


def test_webhook_processes_and_completes_update() -> None:
    app = create_app(webhook_settings())
    updates = StubUpdateService()

    with TestClient(app) as client:
        app.state.telegram_update_service = updates
        app.state.dispatcher = StubDispatcher()
        response = client.post(
            "/telegram/webhook",
            json={"update_id": 2},
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

    assert response.status_code == 200
    updates.claim.assert_awaited_once_with(2)
    updates.complete.assert_awaited_once_with(2)
    updates.release.assert_not_awaited()


def test_webhook_ignores_duplicate_update() -> None:
    app = create_app(webhook_settings())
    updates = StubUpdateService(claimed=False)

    with TestClient(app) as client:
        app.state.telegram_update_service = updates
        response = client.post(
            "/telegram/webhook",
            json={"update_id": 3},
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

    assert response.json() == {"ok": True}
    updates.complete.assert_not_awaited()


def test_webhook_releases_claim_when_handler_fails() -> None:
    app = create_app(webhook_settings())
    updates = StubUpdateService()

    with TestClient(app) as client:
        app.state.telegram_update_service = updates
        app.state.dispatcher = StubDispatcher(fail=True)
        with pytest.raises(RuntimeError, match="handler failed"):
            client.post(
                "/telegram/webhook",
                json={"update_id": 4},
                headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
            )

    updates.release.assert_awaited_once_with(4)
