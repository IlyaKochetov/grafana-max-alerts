from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MAX_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MAX_DEFAULT_CHAT_ID", "123456")
    monkeypatch.setenv("GRAFANA_WEBHOOK_SECRET", "change-me")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
