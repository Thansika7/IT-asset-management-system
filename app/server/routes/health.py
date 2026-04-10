from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.health_service import HealthService
from app.server.database.tenant import apply_tenant_filter
from app.server.schema.asset import AssetInstance


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/instances/{instance_id}")
def get_instance_health(
    instance_id: str,
    emit_alerts: bool = True,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(
            EmployeeRole.SUPER_ADMIN,
            EmployeeRole.ORG_ADMIN,
            EmployeeRole.MANAGER,
            EmployeeRole.HR,
            EmployeeRole.SUPPORT_TEAM,
        )
    ),
):
    return HealthService.get_instance_health(db, current_user, instance_id, emit_alerts=emit_alerts)


@router.get("/assets/{asset_id}")
def get_asset_health(
    asset_id: str,
    emit_alerts: bool = True,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(
            EmployeeRole.SUPER_ADMIN,
            EmployeeRole.ORG_ADMIN,
            EmployeeRole.MANAGER,
            EmployeeRole.HR,
            EmployeeRole.SUPPORT_TEAM,
        )
    ),
):
    return HealthService.get_asset_health(db, current_user, asset_id, emit_alerts=emit_alerts)


@router.get("/summary")
def get_health_summary(
    branch_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(
            EmployeeRole.SUPER_ADMIN,
            EmployeeRole.ORG_ADMIN,
            EmployeeRole.MANAGER,
            EmployeeRole.HR,
            EmployeeRole.SUPPORT_TEAM,
        )
    ),
):
    return HealthService.get_health_summary(db, current_user, branch_id=branch_id)


@router.post("/rebuild")
def rebuild_health_scores_background(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(
            EmployeeRole.SUPER_ADMIN,
            EmployeeRole.ORG_ADMIN,
            EmployeeRole.MANAGER,
            EmployeeRole.HR,
            EmployeeRole.SUPPORT_TEAM,
        )
    ),
):
    def _job(user: Employee) -> None:
        worker_db = next(get_db())
        try:
            ids = [
                row[0]
                for row in apply_tenant_filter(
                    worker_db.query(AssetInstance.instance_id),
                    user,
                    AssetInstance,
                ).all()
            ]
            for instance_id in ids:
                HealthService.get_instance_health(worker_db, user, instance_id, emit_alerts=False)
        finally:
            worker_db.close()

    background_tasks.add_task(_job, current_user)
    return {"status": "scheduled", "task": "health_rebuild"}
