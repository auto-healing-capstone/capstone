# backend/app/schemas/alert.py
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

PROMETHEUS_NULL_TIME = datetime(1, 1, 1, tzinfo=timezone.utc)


class SingleAlert(BaseModel):
    status: str
    labels: dict[str, str]
    annotations: dict[str, str]
    startsAt: datetime
    endsAt: Optional[datetime] = None
    fingerprint: Optional[str] = None

    @field_validator("endsAt", mode="before")
    @classmethod
    def normalize_ends_at(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            parsed = value
        if parsed.year == 1:
            return None
        return parsed

    @property
    def is_firing(self) -> bool:
        return self.status == "firing"

    @property
    def alert_name(self) -> str:
        return self.labels.get("alertname", "unknown")

    @property
    def severity(self) -> str:
        return self.labels.get("severity", "none")


class AlertmanagerPayload(BaseModel):
    version: str
    groupKey: str
    status: str
    receiver: str
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}
    externalURL: Optional[str] = None
    alerts: list[SingleAlert]

    @model_validator(mode="after")
    def check_alerts_not_empty(self):
        if not self.alerts:
            raise ValueError("alerts must not be empty")
        return self
