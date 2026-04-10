from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.tracking import TrackingRead, TrackingFilterOptionsResponse, TrackingListResponse
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import get_current_user
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.services.tracking_service import TrackingService
from app.server.services.analytics_service import AnalyticsService

router=APIRouter(
    prefix="/tracking",
    tags=["tracking"],
    dependencies=[Depends(require_module_access("tracking"))],
)

@router.get("/", response_model=TrackingListResponse)
def get_tracking_records(
    search: Optional[str] = None,
    status: Optional[str] = None,
    branch_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    category_id: Optional[str] = None,
    movement_type: Optional[str] = None,
    transfer_status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    # Pass all filter/search/pagination params to the service
    return TrackingService.get_all_tracking(
        db, 
        current_user, 
        search=search,
        status=status,
        branch_id=branch_id,
        employee_id=employee_id,
        category_id=category_id,
        movement_type=movement_type,
        transfer_status=transfer_status,
        page=page,
        per_page=per_page
    )



@router.get("/options", response_model=TrackingFilterOptionsResponse)
def get_tracking_options(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return TrackingService.get_filter_options(db, current_user)

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


@router.post("/jobs/license-expiry")
def run_license_expiry_job(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM)),
):
    def _job(user: Employee) -> None:
        worker_db = next(get_db())
        try:
            TrackingService.check_expirations_and_notify_support(worker_db, user)
            worker_db.commit()
        finally:
            worker_db.close()

    background_tasks.add_task(_job, current_user)
    return {"status": "scheduled", "task": "license_expiry"}


@router.post("/jobs/analytics-rebuild")
def run_analytics_rebuild_job(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER)),
):
    def _job(user: Employee) -> None:
        worker_db = next(get_db())
        try:
            AnalyticsService.get_dashboard(worker_db, user)
        finally:
            worker_db.close()

    background_tasks.add_task(_job, current_user)
    return {"status": "scheduled", "task": "analytics_rebuild"}
