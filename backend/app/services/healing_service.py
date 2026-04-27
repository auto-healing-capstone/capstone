# backend/app/services/healing_service.py
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.integrations.docker_client import restart_container, update_container
from app.integrations.slack_client import send_recovery_result
from app.models.schema import ActionTypeEnum, ApprovalStatusEnum, RecoveryAction
from app.schemas.recovery_action import RecoveryActionListResponse, RecoveryActionRead

logger = logging.getLogger(__name__)


def get_recovery_actions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[ApprovalStatusEnum] = None,
) -> RecoveryActionListResponse:
    query = select(RecoveryAction)
    if status is not None:
        query = query.where(RecoveryAction.approval_status == status)
    query = query.order_by(RecoveryAction.id.desc())

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    rows = (
        db.execute(query.offset((page - 1) * page_size).limit(page_size))
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

    action.approval_status = ApprovalStatusEnum.APPROVED
    action.approved_at = datetime.now(timezone.utc)
    action.approved_by = approved_by
    if reason:
        action.log_snippet = reason
    db.commit()
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

    action.approval_status = ApprovalStatusEnum.REJECTED
    action.approved_at = datetime.now(timezone.utc)
    action.approved_by = rejected_by
    if reason:
        action.log_snippet = reason
    db.commit()
    db.refresh(action)
    return RecoveryActionRead.model_validate(action)


def execute_recovery(recovery_action_id: int, db: Session) -> bool:
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

    incident = recovery_action.incident
    if incident is None:
        logger.error("RecoveryAction id=%s has no linked incident", recovery_action_id)
        return False

    target_node = incident.target_node
    action_type = recovery_action.action_type

    if action_type == ActionTypeEnum.RESTART_CONTAINER:
        is_successful = restart_container(target_node)
    elif action_type == ActionTypeEnum.SCALE_OUT:
        is_successful = update_container(target_node, **(recovery_action.params or {}))
    elif action_type in (
        ActionTypeEnum.CLEAR_LOGS,
        ActionTypeEnum.DOCKER_PRUNE,
        ActionTypeEnum.RESTART_PROCESS,
    ):
        logger.warning("Action type not implemented: %s", action_type)
        is_successful = False
    else:
        logger.error("Unknown action type: %s", action_type)
        is_successful = False

    recovery_action.executed_at = datetime.now(timezone.utc)
    recovery_action.is_successful = is_successful
    recovery_action.log_snippet = (
        "Recovery executed successfully"
        if is_successful
        else "Recovery execution failed"
    )

    db.commit()

    try:
        send_recovery_result(target_node, action_type, is_successful)
    except Exception:
        logger.warning("Slack recovery result notification failed", exc_info=True)

    return is_successful
