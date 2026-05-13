import json
from pathlib import Path

from app.schemas.grafana import GrafanaWebhookPayload
from app.services.normalizer import normalize_grafana_payload

FIXTURES = Path(__file__).parent / "fixtures"


def load_payload(name: str) -> GrafanaWebhookPayload:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return GrafanaWebhookPayload.model_validate(raw)


def test_normalizes_firing_payload() -> None:
    group = normalize_grafana_payload(load_payload("grafana_webhook_firing.json"))

    assert group.status == "firing"
    assert group.alerts[0].alertname == "High CPU usage"
    assert group.alerts[0].service == "samolet"
    assert group.alerts[0].ends_at is None


def test_normalizes_resolved_payload() -> None:
    group = normalize_grafana_payload(load_payload("grafana_webhook_resolved.json"))

    assert group.status == "resolved"
    assert group.alerts[0].ends_at is not None
    assert group.alerts[0].fingerprint == "abc123"


def test_missing_alertname_and_fingerprint_are_deterministic() -> None:
    payload = load_payload("grafana_webhook_firing.json")
    payload.alerts[0].labels.pop("alertname")
    payload.alerts[0].fingerprint = None
    payload.title = None

    first = normalize_grafana_payload(payload)
    second = normalize_grafana_payload(payload)

    assert first.alerts[0].alertname == "Unnamed alert"
    assert first.alerts[0].fingerprint == second.alerts[0].fingerprint


def test_multiple_alerts_are_normalized() -> None:
    payload = load_payload("grafana_webhook_firing.json")
    payload.alerts.append(payload.alerts[0].model_copy(deep=True))
    payload.alerts[1].labels["alertname"] = "Redis down"
    payload.alerts[1].fingerprint = "redis123"

    group = normalize_grafana_payload(payload)

    assert len(group.alerts) == 2
    assert group.alerts[1].alertname == "Redis down"
