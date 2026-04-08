from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.models.asset_insights import (
    AssetListItem,
    CategoryRead,
    SearchResultsRead,
    SearchSuggestionItem,
    SubCategoryRead,
)
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.services.asset_insights_service import AssetInsightsService

router = APIRouter(tags=["discovery"])


@router.get("/search", response_model=SearchResultsRead)
def search_assets(
    q: str = Query(default="", min_length=0),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return AssetInsightsService.search_discovery(db, current_user=current_user, q=q, limit=10)


@router.get("/search/suggestions", response_model=List[SearchSuggestionItem])
def search_suggestions(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return AssetInsightsService.search_suggestions(db, current_user=current_user, q=q, limit=10)


@router.get("/search/popular", response_model=List[SearchSuggestionItem])
def popular_assets(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return AssetInsightsService.popular_assets(db, current_user=current_user, limit=10)


@router.get("/search/recent", response_model=List[SearchSuggestionItem])
def recent_assets(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return AssetInsightsService.recent_requested_assets(db, current_user=current_user, limit=10)


@router.get("/categories", response_model=List[CategoryRead])
def list_categories(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)
    ),
):
    return AssetInsightsService.list_categories(db)


@router.get("/categories/{category_id}/subcategories", response_model=List[SubCategoryRead])
def list_subcategories(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)
    ),
):
    return AssetInsightsService.list_subcategories(db, category_id)


@router.get("/subcategories/{sub_category_id}/assets", response_model=List[AssetListItem])
def list_assets_by_subcategory(
    sub_category_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)
    ),
):
    return AssetInsightsService.list_assets_by_subcategory(db, current_user=current_user, sub_category_id=sub_category_id)
