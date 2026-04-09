from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.exceptions.base import UnauthorizedActionError
from app.server.models.asset_insights import (
    AssetDetailRead,
    AssetFinanceRead,
    AssetFinanceOptionsRead,
    AssetFinanceReportRead,
    AssetHealthFilterOptions,
    AssetHealthRead,
    AssetHealthReportRead,
    AssetListItem,
    AssetListResponse,
    AssetRecommendationRead,

)
from app.server.models.api import EmployeeAssetOwnerResponse
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.asset import AssetStatus
from app.server.services.asset_insights_service import AssetInsightsService
from app.server.services.asset_usage_service import AssetUsageService
from app.server.services.employee_asset_service import EmployeeAssetService
from app.server.services.request_necessity_ai_service import recommend_request_necessity
from app.server.models.request import AssetNecessityRecommendationInput, RequestNecessityRecommendationResponse

router = APIRouter(
    prefix="/assets",
    tags=["assets"],
    dependencies=[Depends(require_module_access("assets"))],
)


def _has_finance_permission(user: Employee) -> bool:
    if not user.permissions:
        return False
    if user.permissions.can_view_finance or user.permissions.can_manage_finance:
        return True
    perms_json = user.permissions.permissions_json
    if isinstance(perms_json, dict):
        finance_scope = perms_json.get("finance")
        if isinstance(finance_scope, dict):
            return bool(finance_scope.get("view") or finance_scope.get("manage"))
    return False


@router.get("/", response_model=AssetListResponse)
def list_assets(
    search: Optional[str] = None,
    category: Optional[str] = None,
    category_id: Optional[str] = None,
    sub_category: Optional[str] = None,
    sub_category_id: Optional[str] = None,
    branch: Optional[str] = None,
    branch_id: Optional[str] = None,
    status: Optional[str] = None,
    available_only: bool = False,
    allocated_only: bool = False,
    low_stock_only: bool = False,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
        effective_branch = current_user.branch

    return AssetInsightsService.search_assets(
        db,
        current_user,
        search=search,
        category=category,
        category_id=category_id,
        sub_category=sub_category,
        sub_category_id=sub_category_id,
        branch=effective_branch,
        branch_id=branch_id,
        status=status,
        available_only=available_only,
        allocated_only=allocated_only,
        low_stock_only=low_stock_only,
        page=page,
        per_page=per_page
    )


@router.get("/statuses", response_model=list[str])
def list_asset_statuses():
    return [status.value for status in AssetStatus]


@router.get("/options", response_model=list[AssetListItem])
def list_asset_options(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.list_asset_options(db, current_user)


@router.get("/{instance_id}/owner", response_model=EmployeeAssetOwnerResponse)
def get_asset_instance_owner(
    instance_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)),
):
    return EmployeeAssetService.get_asset_owner(db, current_user, instance_id)



@router.get("/{asset_id}/finance", response_model=AssetFinanceRead)
def get_asset_finance(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    role_allowed = current_user.role in [
        EmployeeRole.SUPER_ADMIN,
        EmployeeRole.ORG_ADMIN,
        EmployeeRole.MANAGER,
        EmployeeRole.HR,
        EmployeeRole.SUPPORT_TEAM,
    ]
    permission_allowed = _has_finance_permission(current_user)
    if not role_allowed and not permission_allowed:
        raise UnauthorizedActionError()

    return AssetInsightsService.get_asset_finance(db, asset_id, current_user)


@router.get("/{asset_id}/detail", response_model=AssetDetailRead)
def get_asset_detail(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    role_allowed = current_user.role in [
        EmployeeRole.SUPER_ADMIN,
        EmployeeRole.ORG_ADMIN,
        EmployeeRole.MANAGER,
        EmployeeRole.HR,
        EmployeeRole.SUPPORT_TEAM,
    ]
    permission_allowed = _has_finance_permission(current_user)
    if not role_allowed and not permission_allowed:
        raise UnauthorizedActionError()

    return AssetInsightsService.get_asset_detail(db, asset_id, current_user)


@router.get("/finance/report", response_model=AssetFinanceReportRead)
def get_asset_finance_report(
    branch: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    status: Optional[str] = None,
    available_only: bool = False,
    allocated_only: bool = False,
    low_stock_only: bool = False,
    recommendation: Optional[str] = None,
    min_tco: Optional[float] = None,
    max_tco: Optional[float] = None,
    min_health_score: Optional[int] = None,
    max_health_score: Optional[int] = None,
    sort_by: str = "priority_cost",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    role_allowed = current_user.role in [EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER]
    permission_allowed = _has_finance_permission(current_user)
    if not role_allowed and not permission_allowed:
        raise HTTPException(status_code=403, detail="Not authorized to view finance report")

    effective_branch = branch
    if current_user.role == EmployeeRole.SUPPORT_TEAM:
        effective_branch = current_user.branch
    if current_user.role == EmployeeRole.HR:
        effective_branch = current_user.branch
    if not role_allowed and permission_allowed:
        effective_branch = current_user.branch
        
    return AssetInsightsService.get_finance_report(
        db,
        current_user,
        effective_branch,
        search=search,
        category=category,
        sub_category=sub_category,
        status=status,
        available_only=available_only,
        allocated_only=allocated_only,
        low_stock_only=low_stock_only,
        recommendation=recommendation,
        min_tco=min_tco,
        max_tco=max_tco,
        min_health_score=min_health_score,
        max_health_score=max_health_score,
        sort_by=sort_by,
        page=page,
        per_page=per_page
    )


@router.get("/finance/options", response_model=AssetFinanceOptionsRead)
def get_asset_finance_options():
    return AssetInsightsService.get_finance_options()


@router.get("/health/report", response_model=AssetHealthReportRead)
@router.get("/health", response_model=AssetHealthReportRead, include_in_schema=False)
def get_asset_health_report(
    branch: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    min_health_score: Optional[int] = None,
    max_health_score: Optional[int] = None,
    health_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role == EmployeeRole.SUPPORT_TEAM:
        effective_branch = current_user.branch
    return AssetInsightsService.get_health_report(
        db,
        current_user,
        branch=effective_branch,
        search=search,
        category=category,
        min_health_score=min_health_score,
        max_health_score=max_health_score,
        health_range=health_range,
        page=page,
        per_page=per_page,
    )


@router.get("/health/critical", response_model=AssetHealthReportRead)
def get_critical_asset_health_report(
    branch: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    min_health_score: Optional[int] = None,
    max_health_score: Optional[int] = None,
    health_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role == EmployeeRole.SUPPORT_TEAM:
        effective_branch = current_user.branch
    return AssetInsightsService.get_health_report(
        db,
        current_user,
        branch=effective_branch,
        search=search,
        category=category,
        min_health_score=min_health_score,
        max_health_score=max_health_score,
        health_range=health_range,
        page=page,
        per_page=per_page,
        critical_only=True,
    )


@router.get("/health/options", response_model=AssetHealthFilterOptions)
def get_asset_health_options(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.get_health_filter_options(db, current_user)


@router.get("/health/classification")
def get_asset_health_classification(
    branch: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    effective_branch = branch
    if current_user.role == EmployeeRole.SUPPORT_TEAM:
        effective_branch = current_user.branch
    # Report includes this branch filter as per health report semantics
    return AssetInsightsService.get_health_classification(db, current_user)


@router.get("/usage/report")
def asset_usage_report(
    branch: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetUsageService.usage_report(db, current_user, branch=branch)


@router.get("/usage/analytics")
def asset_usage_analytics(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetUsageService.usage_analytics(db, current_user)


@router.get("/{asset_id}/usage")
def asset_usage_detail(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetUsageService.get_asset_usage(db, asset_id, current_user)


@router.get("/{asset_id}/health", response_model=AssetHealthRead)
def get_asset_health(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.get_asset_health(db, asset_id, current_user)


@router.get("/{asset_id}/recommendation", response_model=AssetRecommendationRead)
def get_asset_recommendation(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    return AssetInsightsService.get_replacement_recommendation(db, asset_id, current_user)


@router.post("/{asset_id}/recommend-necessity", response_model=RequestNecessityRecommendationResponse)
def recommend_necessity_for_asset(
    asset_id: str,
    payload: AssetNecessityRecommendationInput,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN)),
):
    """
    Gemini necessity recommendation for HR/Admin while reviewing inventory:
    whether the requested asset is likely needed or redundant for the given requester.
    """
    from app.server.schema.employee import Employee as EmployeeSchema
    from app.server.schema.employee import EmployeeRole as EmployeeRoleSchema
    from app.server.schema.asset import Asset as AssetSchema
    from app.server.schema.category import Category

    requester: EmployeeSchema | None = (
        db.query(EmployeeSchema).filter(EmployeeSchema.employee_id == payload.requester_employee_id).first()
    )
    if not requester:
        raise HTTPException(status_code=404, detail="Requester employee not found.")

    if current_user.role == EmployeeRoleSchema.HR and (requester.branch or "").strip() != (current_user.branch or "").strip():
        raise HTTPException(status_code=403, detail="HR can only run necessity recommendations for their own branch.")

    asset = (
        db.query(AssetSchema)
        .options()
        .filter(AssetSchema.asset_id == asset_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")

    asset_category = None
    try:
        asset_category = asset.category.category_name  # type: ignore[attr-defined]
    except Exception:
        asset_category = None
    if not asset_category:
        # Fallback: join category by category_id if relationship wasn't loaded.
        cat_row = db.query(Category).filter(Category.category_id == asset.category_id).first()
        asset_category = cat_row.category_name if cat_row else None
    if not asset_category:
        raise HTTPException(status_code=400, detail="Asset category not found.")

    try:
        out = recommend_request_necessity(
            db,
            requester,
            asset_name=asset.name,
            asset_category=asset_category,
            reason=payload.reason,
            ticket_context=None,
        )
        return RequestNecessityRecommendationResponse(**out)
    except ValueError as e:
        msg = str(e)
        if "GEMINI_API_KEY" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
