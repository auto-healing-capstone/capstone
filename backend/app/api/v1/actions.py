# backend/app/api/v1/actions.py
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.schema import ApprovalStatusEnum
from app.schemas.recovery_action import (
    ApproveRequest,
    HealRequest,
    RecoveryActionListResponse,
    RecoveryActionRead,
    RejectRequest,
)
from app.services import healing_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_heal_key(x_api_key: Optional[str] = Header(None)) -> None:
    if not settings.HEAL_API_KEY or x_api_key != settings.HEAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@router.get("/recovery-actions", response_model=RecoveryActionListResponse)
def list_recovery_actions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    approval_status: Optional[ApprovalStatusEnum] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return healing_service.get_recovery_actions(
            db, page=page, page_size=page_size, status=approval_status
        )
    except Exception:
        logger.exception("Failed to list recovery actions")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/recovery-actions/{id}/approve", response_model=RecoveryActionRead)
def approve_recovery_action(
    id: int,
    body: ApproveRequest,
    db: Session = Depends(get_db),
):
    try:
        return healing_service.approve_recovery_action(
            recovery_action_id=id,
            reviewed_by=body.reviewed_by,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception("Failed to approve recovery action id=%s", id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/recovery-actions/{id}/reject", response_model=RecoveryActionRead)
def reject_recovery_action(
    id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
):
    try:
        return healing_service.reject_recovery_action(
            recovery_action_id=id,
            rejected_by=body.rejected_by,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception("Failed to reject recovery action id=%s", id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/heal")
def heal(
    body: HealRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_heal_key),
):
    try:
        success = healing_service.execute_recovery(body.recovery_action_id, db)
        if success:
            return {"message": "Recovery executed", "success": True}
        return {"message": "Recovery failed", "success": False}
    except Exception:
        logger.exception(
            "Failed to execute recovery action id=%s", body.recovery_action_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
