# backend/app/models/schema.py
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Enum,
    Float,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
import app.models.alert_event  # noqa: F401, E402 — SQLAlchemy registry 등록용

if TYPE_CHECKING:
    from app.models.alert_event import AlertEvent  # Pylance 타입 힌트용만


# ==========================================
# 1. ENUM 정의
# ==========================================
class IncidentTypeEnum(str, enum.Enum):
    CONTAINER_CRASH = "CONTAINER_CRASH"
    OOM = "OOM"
    DISK_FULL = "DISK_FULL"
    HIGH_CPU = "HIGH_CPU"
    DB_CONNECTION = "DB_CONNECTION"
    NGINX_5XX = "NGINX_5XX"


class StatusEnum(str, enum.Enum):
    DETECTED = "DETECTED"  # proactive: 예측 기반 장애 감지 시 초기 상태
    ANALYZING = "ANALYZING"  # 현재 미사용 (향후 실시간 분석 상태 표시용으로 예약)
    PENDING = "PENDING"  # LLM 분석 완료, Slack 승인 대기 중
    RECOVERING = "RECOVERING"  # 관리자 승인 완료, 복구 실행 중
    RESOLVED = "RESOLVED"  # 복구 성공
    FAILED = "FAILED"  # 복구 실패


class SeverityEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MetricTypeEnum(str, enum.Enum):
    DISK = "DISK"
    MEMORY = "MEMORY"
    CPU = "CPU"


class ActionTypeEnum(str, enum.Enum):
    RESTART_CONTAINER = "RESTART_CONTAINER"
    CLEAR_LOGS = "CLEAR_LOGS"
    DOCKER_PRUNE = "DOCKER_PRUNE"
    RESTART_PROCESS = "RESTART_PROCESS"
    SCALE_OUT = "SCALE_OUT"


class ApprovalStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ==========================================
# 2. 모델 정의
# ==========================================


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 연쇄 장애를 위한 자기 참조 (Self-referencing FK)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id"), index=True, nullable=True
    )

    # 복합 장애를 담는 ARRAY(ENUM)
    incident_types: Mapped[list] = mapped_column(
        ARRAY(Enum(IncidentTypeEnum)), nullable=False
    )
    trigger_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    target_node: Mapped[str] = mapped_column(String(100), index=True)
    detected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum), default=StatusEnum.DETECTED, index=True
    )

    ai_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ai_severity: Mapped[Optional[SeverityEnum]] = mapped_column(
        Enum(SeverityEnum), index=True, nullable=True
    )
    llm_analysis: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 🤝 Relationships (JOIN을 파이썬 객체처럼)
    parent = relationship("Incident", remote_side=[id], backref="children")
    predictions = relationship("Prediction", back_populates="incident")
    actions = relationship("RecoveryAction", back_populates="incident")
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="incident")

    __table_args__ = (
        # 배열(ARRAY) 내부 값을 초고속으로 검색하기 위한 GIN 인덱스!
        Index("idx_incidents_types", "incident_types", postgresql_using="gin"),
        # 대시보드의 '최신순 정렬'을 위한 DESC 인덱스!
        Index("idx_incidents_detected_at", text("detected_at DESC")),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id"), index=True, nullable=True
    )

    target_node: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    metric_type: Mapped[MetricTypeEnum] = mapped_column(
        Enum(MetricTypeEnum), nullable=False
    )
    predicted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expected_breach: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # 🤝 Relationships
    incident = relationship("Incident", back_populates="predictions")
    actions = relationship("RecoveryAction", back_populates="prediction")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id"), index=True, nullable=True
    )
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("predictions.id"), index=True, nullable=True
    )

    action_type: Mapped[ActionTypeEnum] = mapped_column(
        Enum(ActionTypeEnum), nullable=False
    )
    params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 🛡️ 승인 파이프라인 일원화!
    approval_status: Mapped[ApprovalStatusEnum] = mapped_column(
        Enum(ApprovalStatusEnum), default=ApprovalStatusEnum.PENDING, nullable=False
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_successful: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    log_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 🤝 Relationships
    incident = relationship("Incident", back_populates="actions")
    prediction = relationship("Prediction", back_populates="actions")

    __table_args__ = (
        # 둘 중 하나는 무조건 있어야 한다는 CHECK 제약조건
        CheckConstraint(
            "incident_id IS NOT NULL OR prediction_id IS NOT NULL",
            name="check_action_target",
        ),
    )
