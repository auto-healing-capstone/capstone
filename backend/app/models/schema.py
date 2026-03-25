import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, 
    ForeignKey, Enum, Float, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.models.base import Base

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
    DETECTED = "DETECTED"
    ANALYZING = "ANALYZING"
    PENDING = "PENDING"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"

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

    id = Column(Integer, primary_key=True, index=True)
    # 연쇄 장애를 위한 자기 참조 (Self-referencing FK)
    parent_id = Column(Integer, ForeignKey("incidents.id"), index=True, nullable=True)

    # 복합 장애를 담는 ARRAY(ENUM)
    incident_types = Column(ARRAY(Enum(IncidentTypeEnum)), nullable=False)
    trigger_metrics = Column(JSONB, nullable=False)
    
    target_node = Column(String(100), index=True, nullable=False)
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status = Column(Enum(StatusEnum), default=StatusEnum.DETECTED, index=True, nullable=False)
    
    ai_title = Column(String(200), nullable=True)
    ai_severity = Column(Enum(SeverityEnum), index=True, nullable=True)
    llm_analysis = Column(JSONB, nullable=True)
    
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # 🤝 Relationships (JOIN을 파이썬 객체처럼)
    parent = relationship("Incident", remote_side=[id], backref="children")
    predictions = relationship("Prediction", back_populates="incident")
    actions = relationship("RecoveryAction", back_populates="incident")

    __table_args__ = (
        # 배열(ARRAY) 내부 값을 초고속으로 검색하기 위한 GIN 인덱스!
        Index('idx_incidents_types', 'incident_types', postgresql_using='gin'),
        # 대시보드의 '최신순 정렬'을 위한 DESC 인덱스!
        Index('idx_incidents_detected_at', detected_at.desc()),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), index=True, nullable=True)

    target_node = Column(String(100), index=True, nullable=False)
    metric_type = Column(Enum(MetricTypeEnum), nullable=False)
    predicted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expected_breach = Column(DateTime(timezone=True), index=True, nullable=False)
    
    confidence = Column(Float, nullable=True)
    is_verified = Column(Boolean, default=False)

    # 🤝 Relationships
    incident = relationship("Incident", back_populates="predictions")
    actions = relationship("RecoveryAction", back_populates="prediction")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), index=True, nullable=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), index=True, nullable=True)

    action_type = Column(Enum(ActionTypeEnum), nullable=False)
    
    # 🛡️ 승인 파이프라인 일원화!
    approval_status = Column(Enum(ApprovalStatusEnum), default=ApprovalStatusEnum.PENDING, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(100), nullable=True)
    
    executed_at = Column(DateTime(timezone=True), nullable=True)
    is_successful = Column(Boolean, nullable=True)
    log_snippet = Column(Text, nullable=True)

    # 🤝 Relationships
    incident = relationship("Incident", back_populates="actions")
    prediction = relationship("Prediction", back_populates="actions")

    __table_args__ = (
        # 둘 중 하나는 무조건 있어야 한다는 CHECK 제약조건
        CheckConstraint(
            'incident_id IS NOT NULL OR prediction_id IS NOT NULL', 
            name='check_action_target'
        ),
    )