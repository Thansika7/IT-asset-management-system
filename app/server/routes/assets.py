from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.models.asset_insights import (
    AssetFinanceRead,
    AssetFinanceReportRead,
    AssetHealthRead,
    AssetListItem,
    AssetRecommendationRead,
)
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.asset_insights_service import AssetInsightsService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/", response_model=List[AssetListItem])
def list_assets(
    search: Optional[str] = None,
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    branch: Optional[str] = None,
    status: Optional[str] = None,
    available_only: bool = False,
    allocated_only: bool = False,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
        effective_branch = current_user.branch

    return AssetInsightsService.search_assets(
        db,
        search=search,
        category=category,
        sub_category=sub_category,
        branch=effective_branch,
        status=status,
        available_only=available_only,
        allocated_only=allocated_only,
        low_stock_only=low_stock_only,
    )


@router.get("/{asset_id}/finance", response_model=AssetFinanceRead)
def get_asset_finance(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.get_asset_finance(db, asset_id)


@router.get("/finance/report", response_model=AssetFinanceReportRead)
def get_asset_finance_report(
    branch: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER)),
):
    effective_branch = branch
    if current_user.role == EmployeeRole.MANAGER:
        effective_branch = current_user.branch
    return AssetInsightsService.get_finance_report(db, effective_branch)


@router.get("/{asset_id}/health", response_model=AssetHealthRead)
def get_asset_health(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.get_asset_health(db, asset_id)


@router.get("/{asset_id}/recommendation", response_model=AssetRecommendationRead)
def get_asset_recommendation(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.get_replacement_recommendation(db, asset_id)
