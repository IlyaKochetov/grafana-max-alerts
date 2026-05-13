from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "production"]
MessageFormat = Literal["markdown", "html"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "grafana-max-alerts"
    app_env: AppEnv = "development"
    log_level: str = "INFO"

    grafana_webhook_secret: str | None = None
    grafana_hmac_secret: str | None = None
    grafana_hmac_header: str = "X-Grafana-Alerting-Signature"
    grafana_hmac_timestamp_header: str | None = "X-Grafana-Alerting-Timestamp"
    grafana_hmac_max_age_seconds: int = 300

    max_api_base_url: str = "https://platform-api.max.ru"
    max_bot_token: str | None = None
    max_default_chat_id: int | None = None
    max_message_format: MessageFormat = "markdown"
    max_message_max_length: int = 3900
    max_request_timeout_seconds: float = 10
    max_retry_attempts: int = 3
    max_retry_backoff_seconds: float = 1

    routes_config_path: Path = Path("config.yaml")

    dedup_enabled: bool = True
    dedup_backend: Literal["memory"] = "memory"
    dedup_ttl_seconds: int = 300

    request_body_max_bytes: int = 1_048_576

    @field_validator(
        "grafana_webhook_secret",
        "grafana_hmac_secret",
        "max_bot_token",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @field_validator("grafana_hmac_timestamp_header", mode="before")
    @classmethod
    def optional_header(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    if not isinstance(loaded, dict):
        msg = f"Config file {path} must contain a YAML mapping"
        raise ValueError(msg)
    return loaded


@lru_cache
def get_settings() -> Settings:
    return Settings()
