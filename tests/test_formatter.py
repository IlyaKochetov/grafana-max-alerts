from datetime import UTC, datetime

from app.schemas.normalized import AlertEvent, AlertGroup
from app.services.formatter import MessageFormatter, truncate_message


def make_alert(status: str = "firing") -> AlertEvent:
    return AlertEvent(
        status=status,  # type: ignore[arg-type]
        alertname="High CPU usage",
        severity="critical",
        service="samolet",
        instance="app-01",
        description="CPU usage is above 90% for 5 minutes",
        starts_at=datetime(2026, 5, 13, 15, 20, tzinfo=UTC),
        ends_at=datetime(2026, 5, 13, 15, 32, tzinfo=UTC) if status == "resolved" else None,
        fingerprint="abc123",
        labels={"service": "samolet", "severity": "critical"},
    )


def test_firing_message_contains_marker() -> None:
    text = MessageFormatter().format_single(make_alert("firing"))

    assert "🔥 FIRING" in text
    assert "High CPU usage" in text


def test_resolved_message_contains_marker_and_duration() -> None:
    text = MessageFormatter().format_single(make_alert("resolved"))

    assert "✅ RESOLVED" in text
    assert "12m 0s" in text


def test_group_message_contains_count_and_truncated_alerts() -> None:
    group = AlertGroup(
        status="firing",
        group_key="group",
        truncated_alerts=2,
        alerts=[make_alert(), make_alert()],
    )

    text = MessageFormatter().format_group(group)

    assert "2 alerts" in text
    assert "Grafana truncated 2 alerts" in text


def test_truncate_message() -> None:
    text = truncate_message("x" * 100, 30)

    assert len(text) <= 30
    assert text.endswith("... truncated")
