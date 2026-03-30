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
    if current_user.role in [EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM]:
        return TrackingService.get_all_tracking(db)
    
    # Simple employees only see their own tracking history
    return TrackingService.get_all_tracking(db, emp_id=current_user.employee_id)

@router.get("/{asset_id}", response_model=List[TrackingRead])
def get_asset_tracking(
    asset_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    return TrackingService.get_asset_history(db, asset_id)
