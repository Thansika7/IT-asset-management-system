from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.models.asset_insights import UtilizationItem
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.asset_insights_service import AssetInsightsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/utilization", response_model=List[UtilizationItem])
def get_utilization(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    items = AssetInsightsService.get_utilization_summary(db)
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
        return [item for item in items if item.branch == current_user.branch]
    return items


@router.get("/branch", response_model=List[UtilizationItem])
def get_branch_analytics(
    branch: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
        effective_branch = current_user.branch
    return AssetInsightsService.get_branch_analytics(db, effective_branch)
