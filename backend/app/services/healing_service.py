# backend/app/services/healing_service.py
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.integrations.docker_client import (
    clear_logs,
    docker_prune,
    restart_container,
    restart_process,
    update_container,
)
from app.core.config import TARGET_NODE_MAP
from app.core.events import broadcaster
from app.integrations.slack_client import send_recovery_result
from app.models.schema import (
    ActionTypeEnum,
    ApprovalStatusEnum,
    Incident,
    RecoveryAction,
    StatusEnum,
)
from app.schemas.recovery_action import RecoveryActionListResponse, RecoveryActionRead

logger = logging.getLogger(__name__)


def get_recovery_actions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[ApprovalStatusEnum] = None,
) -> RecoveryActionListResponse:
    base_query = select(RecoveryAction)
    if status is not None:
        base_query = base_query.where(RecoveryAction.approval_status == status)

    total = db.execute(
        select(func.count()).select_from(base_query.subquery())
    ).scalar_one()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    data_query = base_query.order_by(RecoveryAction.id.desc())
    rows = (
        db.execute(data_query.offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )

    return RecoveryActionListResponse(
        items=[RecoveryActionRead.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def approve_recovery_action(
    recovery_action_id: int,
    approved_by: str,
    reason: Optional[str],
    db: Session,
) -> RecoveryActionRead:
    action = db.execute(
        select(RecoveryAction).where(RecoveryAction.id == recovery_action_id)
    ).scalar_one_or_none()
    if action is None:
        raise ValueError(f"RecoveryAction not found: id={recovery_action_id}")

    # TODO: approved_at/approved_by를 reject에도 재사용 중
    # 추후 reviewed_at/reviewed_by로 중립적 필드명으로 개선 필요
    action.approval_status = ApprovalStatusEnum.APPROVED
    action.approved_at = datetime.now(timezone.utc)
    action.approved_by = approved_by
    if reason:
        action.log_snippet = reason
    if action.incident_id:
        incident = db.get(Incident, action.incident_id)
        if incident:
            incident.status = StatusEnum.RECOVERING
    db.commit()

    try:
        broadcaster.broadcast(
            "status_changed",
            {"incident_id": action.incident_id, "status": StatusEnum.RECOVERING.value},
        )
    except Exception:
        logger.warning("SSE broadcast status_changed failed", exc_info=True)

    db.refresh(action)
    return RecoveryActionRead.model_validate(action)


def reject_recovery_action(
    recovery_action_id: int,
    rejected_by: str,
    reason: Optional[str],
    db: Session,
) -> RecoveryActionRead:
    action = db.execute(
        select(RecoveryAction).where(RecoveryAction.id == recovery_action_id)
    ).scalar_one_or_none()
    if action is None:
        raise ValueError(f"RecoveryAction not found: id={recovery_action_id}")

    # TODO: approved_at/approved_by를 reject에도 재사용 중
    # 추후 reviewed_at/reviewed_by로 중립적 필드명으로 개선 필요
    action.approval_status = ApprovalStatusEnum.REJECTED
    action.approved_at = datetime.now(timezone.utc)
    action.approved_by = rejected_by
    if reason:
        action.log_snippet = reason
    db.commit()
    db.refresh(action)
    return RecoveryActionRead.model_validate(action)


def execute_recovery(recovery_action_id: int, db: Session) -> bool:
    # TODO: /heal 엔드포인트 인증/인가 추가 필요 (admin token 등)
    recovery_action = db.execute(
        select(RecoveryAction).where(RecoveryAction.id == recovery_action_id)
    ).scalar_one_or_none()

    if recovery_action is None:
        logger.error("RecoveryAction not found: id=%s", recovery_action_id)
        return False

    if recovery_action.approval_status != ApprovalStatusEnum.APPROVED:
        logger.warning(
            "RecoveryAction id=%s is not approved (status=%s)",
            recovery_action_id,
            recovery_action.approval_status,
        )
        return False

    if recovery_action.executed_at is not None:
        logger.warning("RecoveryAction id=%s already executed", recovery_action_id)
        return False

    incident = recovery_action.incident
    if incident is None:
        logger.error("RecoveryAction id=%s has no linked incident", recovery_action_id)
        return False

    target_node = incident.target_node
    container_name = TARGET_NODE_MAP.get(target_node, target_node) or target_node
    action_type = recovery_action.action_type

    if action_type == ActionTypeEnum.RESTART_CONTAINER:
        is_successful = restart_container(container_name)
    elif action_type == ActionTypeEnum.SCALE_OUT:
        allowed_keys = {"mem_limit", "cpu_quota"}
        safe_params = {
            k: v for k, v in (recovery_action.params or {}).items() if k in allowed_keys
        }
        is_successful = update_container(container_name, **safe_params)
    elif action_type == ActionTypeEnum.CLEAR_LOGS:
        is_successful = clear_logs(container_name)
    elif action_type == ActionTypeEnum.DOCKER_PRUNE:
        is_successful = docker_prune()
    elif action_type == ActionTypeEnum.RESTART_PROCESS:
        allowed_keys = {"process"}
        safe_params = {
            k: v for k, v in (recovery_action.params or {}).items() if k in allowed_keys
        }
        is_successful = restart_process(container_name, **safe_params)
    else:
        logger.error("Unknown action type: %s", action_type)
        is_successful = False

    recovery_action.executed_at = datetime.now(timezone.utc)
    recovery_action.is_successful = is_successful
    new_log = (
        "Recovery executed successfully"
        if is_successful
        else "Recovery execution failed"
    )
    recovery_action.log_snippet = (
        f"{recovery_action.log_snippet}\n{new_log}"
        if recovery_action.log_snippet
        else new_log
    )
    if incident is not None:
        incident.status = StatusEnum.RESOLVED if is_successful else StatusEnum.FAILED
        if is_successful:
            incident.resolved_at = datetime.now(timezone.utc)

    db.commit()

    try:
        broadcaster.broadcast(
            "recovery_completed",
            {
                "incident_id": incident.id,
                "is_successful": is_successful,
                "action_type": action_type.value,
            },
        )
    except Exception:
        logger.warning("SSE broadcast recovery_completed failed", exc_info=True)

    try:
        send_recovery_result(container_name, action_type, is_successful)
    except Exception:
        logger.warning("Slack recovery result notification failed", exc_info=True)

    return is_successful
