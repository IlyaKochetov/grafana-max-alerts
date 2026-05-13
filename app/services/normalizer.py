import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.schemas.grafana import GrafanaAlert, GrafanaWebhookPayload
from app.schemas.normalized import AlertEvent, AlertGroup

ZERO_TIME = datetime(1, 1, 1, tzinfo=UTC)


def stable_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def normalize_grafana_payload(payload: GrafanaWebhookPayload) -> AlertGroup:
    alerts = [_normalize_alert(alert, payload) for alert in payload.alerts]
    group_key = payload.groupKey or stable_hash(
        {
            "receiver": payload.receiver,
            "status": payload.status,
            "group_labels": payload.groupLabels,
            "common_labels": payload.commonLabels,
        }
    )

    return AlertGroup(
        receiver=payload.receiver,
        status=payload.status,
        org_id=payload.orgId,
        group_key=group_key,
        group_labels=payload.groupLabels,
        common_labels=payload.commonLabels,
        common_annotations=payload.commonAnnotations,
        external_url=payload.externalURL,
        truncated_alerts=payload.truncatedAlerts,
        alerts=alerts,
    )


def _normalize_alert(alert: GrafanaAlert, payload: GrafanaWebhookPayload) -> AlertEvent:
    labels = {**payload.commonLabels, **alert.labels}
    annotations = {**payload.commonAnnotations, **alert.annotations}
    starts_at = alert.startsAt
    ends_at = _normalize_ends_at(alert.endsAt)
    fingerprint = alert.fingerprint or stable_hash(
        {
            "status": alert.status,
            "labels": alert.labels,
            "annotations": alert.annotations,
            "starts_at": starts_at,
        }
    )

    return AlertEvent(
        status=alert.status,
        alertname=_first_present(
            alert.labels.get("alertname"),
            payload.commonLabels.get("alertname"),
            payload.title,
            "Unnamed alert",
        ),
        severity=_first_present(alert.labels.get("severity"), payload.commonLabels.get("severity")),
        service=_first_present(
            alert.labels.get("service"),
            alert.labels.get("app"),
            alert.labels.get("job"),
            payload.commonLabels.get("service"),
            payload.commonLabels.get("app"),
            payload.commonLabels.get("job"),
        ),
        instance=labels.get("instance"),
        environment=_first_present(
            alert.labels.get("env"),
            alert.labels.get("environment"),
            payload.commonLabels.get("env"),
            payload.commonLabels.get("environment"),
        ),
        summary=annotations.get("summary"),
        description=annotations.get("description") or payload.message,
        runbook_url=annotations.get("runbook_url") or annotations.get("runbook"),
        starts_at=starts_at,
        ends_at=ends_at,
        fingerprint=fingerprint,
        generator_url=alert.generatorURL,
        dashboard_url=alert.dashboardURL,
        panel_url=alert.panelURL,
        silence_url=alert.silenceURL,
        labels=labels,
        annotations=annotations,
        values=alert.values,
    )


def _first_present(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _normalize_ends_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    comparable = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if comparable == ZERO_TIME:
        return None
    return value
