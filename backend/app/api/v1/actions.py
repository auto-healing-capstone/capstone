# backend/app/api/v1/actions.py
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

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


@router.get("/recovery-actions", response_model=RecoveryActionListResponse)
def list_recovery_actions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ApprovalStatusEnum] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return healing_service.get_recovery_actions(
            db, page=page, page_size=page_size, status=status
        )
    except Exception:
        logger.exception("Failed to list recovery actions")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/recovery-actions/{id}/approve", response_model=RecoveryActionRead)
def approve_recovery_action(
    id: int,
    body: ApproveRequest,
    db: Session = Depends(get_db),
):
    try:
        return healing_service.approve_recovery_action(
            recovery_action_id=id,
            approved_by=body.approved_by,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to approve recovery action id=%s", id)
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to reject recovery action id=%s", id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/heal")
def heal(
    body: HealRequest,
    db: Session = Depends(get_db),
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
        raise HTTPException(status_code=500, detail="Internal server error")
