from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.models.asset_insights import UtilizationItem
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.analytics_service import AnalyticsService
from app.server.services.asset_insights_service import AssetInsightsService

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_module_access("analytics"))],
)


class _AnalyticsAccess:
    ROLES = (
        EmployeeRole.SUPER_ADMIN,
        EmployeeRole.ORG_ADMIN,
        EmployeeRole.MANAGER,
        EmployeeRole.HR,
        EmployeeRole.SUPPORT_TEAM,
        EmployeeRole.EMPLOYEE,
    )


@router.get("/utilization", response_model=List[UtilizationItem])
def get_utilization(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    items = AssetInsightsService.get_utilization_summary(db)
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
        return [item for item in items if item.branch == current_user.branch]
    return items


@router.get("/branch", response_model=List[UtilizationItem])
def get_branch_analytics(
    branch: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
        effective_branch = current_user.branch
    return AssetInsightsService.get_branch_analytics(db, effective_branch)


@router.get("/dashboard")
def get_dashboard_analytics(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_dashboard(db, current_user)


@router.get("/assets")
def get_asset_analytics_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_asset_analytics(db, current_user)


@router.get("/health")
def get_health_analytics_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_health_analytics(db, current_user)


@router.get("/finance")
def get_finance_analytics_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_finance_analytics(db, current_user)


@router.get("/requests")
def get_request_analytics_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_request_analytics(db, current_user)


@router.get("/inventory")
def get_inventory_analytics_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_inventory_analytics(db, current_user)


@router.get("/cmdb")
def get_cmdb_analytics_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(*_AnalyticsAccess.ROLES)),
):
    return AnalyticsService.get_cmdb_analytics(db, current_user)
