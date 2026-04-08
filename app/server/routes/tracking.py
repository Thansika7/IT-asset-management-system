from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.server.database.database import get_db
from app.server.models.tracking import TrackingRead
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import get_current_user
from app.server.middlewares.auth import require_roles
from app.server.services.tracking_service import TrackingService

router=APIRouter(prefix="/tracking", tags=["tracking"])

@router.get("/", response_model=List[TrackingRead])
def get_tracking_records(
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    if current_user.role in [EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM]:
        return TrackingService.get_all_tracking(db, current_user)

    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR]:
        return TrackingService.get_all_tracking(db, current_user, branch=current_user.branch)

    # Simple employees only see their own tracking history
    return TrackingService.get_all_tracking(db, current_user, emp_id=current_user.employee_id)

@router.get("/{asset_id}", response_model=List[TrackingRead])
def get_asset_tracking(
    asset_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    return TrackingService.get_asset_history(db, asset_id, current_user)

@router.post("/check-expirations")
def trigger_expiration_check(
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """
    Manually trigger the 30-day expiration check.
    This can also be hit by an automated CRON job using an Admin token.
    """
    expiring_items = TrackingService.check_expirations_and_notify_support(db, current_user)
    return {
        "status": "success",
        "message": f"Expiration check completed. Found {len(expiring_items)} expiring items.",
        "data": expiring_items
    }
