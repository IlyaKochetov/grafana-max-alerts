from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AlertStatus = Literal["firing", "resolved"]


class AlertEvent(BaseModel):
    status: AlertStatus
    alertname: str
    severity: str | None = None
    service: str | None = None
    instance: str | None = None
    environment: str | None = None
    summary: str | None = None
    description: str | None = None
    runbook_url: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    fingerprint: str
    generator_url: str | None = None
    dashboard_url: str | None = None
    panel_url: str | None = None
    silence_url: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)


class AlertGroup(BaseModel):
    receiver: str | None = None
    status: AlertStatus
    org_id: int | None = None
    group_key: str
    group_labels: dict[str, str] = Field(default_factory=dict)
    common_labels: dict[str, str] = Field(default_factory=dict)
    common_annotations: dict[str, str] = Field(default_factory=dict)
    external_url: str | None = None
    truncated_alerts: int = 0
    alerts: list[AlertEvent]
