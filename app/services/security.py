import hashlib
import hmac
import time
from collections.abc import Mapping

from app.config import Settings
from app.exceptions import SecurityError

WEBHOOK_SECRET_HEADER = "X-Webhook-Secret"


def verify_shared_secret(received: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not received:
        return False
    return _constant_time_equals(received, expected)


def verify_webhook_security(
    headers: Mapping[str, str],
    raw_body: bytes,
    settings: Settings,
) -> None:
    if settings.grafana_hmac_secret:
        verify_hmac(headers, raw_body, settings)
        return

    received = _get_header(headers, WEBHOOK_SECRET_HEADER)
    if not verify_shared_secret(received, settings.grafana_webhook_secret):
        raise SecurityError("Invalid webhook secret")


def verify_hmac(headers: Mapping[str, str], raw_body: bytes, settings: Settings) -> None:
    if not settings.grafana_hmac_secret:
        return

    received = _get_header(headers, settings.grafana_hmac_header)
    if not received:
        raise SecurityError("Missing webhook signature")

    timestamp_header = settings.grafana_hmac_timestamp_header
    if timestamp_header:
        timestamp = _get_header(headers, timestamp_header)
        if not timestamp:
            raise SecurityError("Missing webhook signature timestamp")
        _verify_timestamp(timestamp, settings.grafana_hmac_max_age_seconds)
        signed = timestamp.encode("utf-8") + b":" + raw_body
    else:
        signed = raw_body

    digest = hmac.new(
        settings.grafana_hmac_secret.encode("utf-8"),
        signed,
        hashlib.sha256,
    ).hexdigest()
    expected_variants = (digest, f"sha256={digest}")
    if not any(_constant_time_equals(received, expected) for expected in expected_variants):
        raise SecurityError("Invalid webhook signature")


def _constant_time_equals(received: str, expected: str) -> bool:
    return hmac.compare_digest(received.encode("utf-8"), expected.encode("utf-8"))


def _verify_timestamp(timestamp: str, max_age_seconds: int) -> None:
    try:
        timestamp_seconds = int(timestamp)
    except ValueError as exc:
        raise SecurityError("Invalid webhook signature timestamp") from exc
    if abs(time.time() - timestamp_seconds) > max_age_seconds:
        raise SecurityError("Webhook signature timestamp is too old")


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None
