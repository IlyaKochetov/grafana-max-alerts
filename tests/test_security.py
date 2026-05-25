import pytest

from app.config import Settings
from app.exceptions import SecurityError
from app.services.security import verify_hmac, verify_shared_secret


def test_shared_secret_supports_non_ascii_values() -> None:
    assert verify_shared_secret("секрет", "секрет") is True
    assert verify_shared_secret("другой", "секрет") is False


def test_hmac_signature_with_non_ascii_header_returns_security_error() -> None:
    settings = Settings(
        app_env="test",
        grafana_hmac_secret="secret",
        grafana_hmac_timestamp_header=None,
    )

    with pytest.raises(SecurityError, match="Invalid webhook signature"):
        verify_hmac({"X-Grafana-Alerting-Signature": "подпись"}, b"{}", settings)
