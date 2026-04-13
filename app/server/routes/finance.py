from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.services.finance_service import FinanceService


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
    dependencies=[Depends(require_module_access("finance"))],
)


def _can_view_finance(user: Employee) -> bool:
    if user.role in {EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM}:
        return True
    if not user.permissions:
        return False
    perms_json = user.permissions.permissions_json
    if isinstance(perms_json, dict):
        finance_scope = perms_json.get("finance")
        if isinstance(finance_scope, dict):
            return bool(finance_scope.get("view") or finance_scope.get("manage"))
    return False


@router.get("/assets")
def list_assets_finance(
    branch_id: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if not _can_view_finance(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to view finance assets report")
    return FinanceService.list_assets_finance(
        db=db,
        current_user=current_user,
        branch_id=branch_id,
        page=page,
        per_page=per_page,
    )


@router.get("/instances")
def list_instances_finance(
    branch_id: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if not _can_view_finance(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to view finance instances report")
    return FinanceService.list_instance_finance(
        db=db,
        current_user=current_user,
        branch_id=branch_id,
        page=page,
        per_page=per_page,
    )


@router.post("/instances/{instance_id}/maintenance")
def add_instance_maintenance(
    instance_id: str,
    maintenance_cost: float,
    reason: str = "MAINTENANCE_COST_UPDATE",
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    try:
        result = FinanceService.add_instance_maintenance_cost(
            db=db,
            current_user=current_user,
            instance_id=instance_id,
            amount=maintenance_cost,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"status": "success", **result}
