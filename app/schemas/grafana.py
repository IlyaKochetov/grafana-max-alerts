from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AlertStatus = Literal["firing", "resolved"]


class GrafanaAlert(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: AlertStatus
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    generatorURL: str | None = None
    fingerprint: str | None = None
    silenceURL: str | None = None
    dashboardURL: str | None = None
    panelURL: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class GrafanaWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    receiver: str | None = None
    status: AlertStatus
    orgId: int | None = None
    alerts: list[GrafanaAlert] = Field(default_factory=list)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str | None = None
    version: str | None = None
    groupKey: str | None = None
    truncatedAlerts: int = 0
    title: str | None = None
    state: str | None = None
    message: str | None = None
