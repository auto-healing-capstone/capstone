# backend/app/models/alert_event.py
from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.schema import Incident


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Alertmanager raw 값을 그대로 저장 (String)
    # ENUM 정규화는 AI 분석 후 incidents 테이블에서 수행
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="none")

    # Alertmanager raw 값을 그대로 저장 (String)
    # ENUM 정규화는 AI 분석 후 incidents 테이블에서 수행
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    instance: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # AI 분석 완료 전까지 NULL, 분석 완료 후 incidents.id 연결
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    incident: Mapped[Optional["Incident"]] = relationship(back_populates="alert_events")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_alert_events_fingerprint_status", "fingerprint", "status"),
    )
