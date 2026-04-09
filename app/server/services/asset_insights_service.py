from __future__ import annotations

from datetime import date, datetime, timedelta
from difflib import SequenceMatcher, get_close_matches
from typing import Optional

from sqlalchemy import String, func, or_
from sqlalchemy.orm import Session, joinedload

from app.server.exceptions.base import ResourceNotFoundError
from app.server.models.asset_insights import (
    AssetDetailRead,
    AssetFinanceRead,
    AssetFinanceMonitorItem,
    AssetFinanceReportRead,
    AssetFinanceOptionsRead,
    FinanceSortOption,
    AssetHealthRead,
    AssetHealthReportItem,
    AssetHealthReportRead,
    AssetHealthFilterOptions,
    HealthRangeOption,
    AssetListItem,
    AssetRecommendationRead,
    CategoryRead,
    SearchResultsRead,
    SearchSuggestionItem,
    SubCategoryRead,
    UtilizationItem,
)
from app.server.schema.employee import Employee
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.category import Category, SubCategory
from app.server.schema.organization import Branch
from app.server.schema.tracking import Tracking, MovementType


class AssetInsightsService:
    NON_HARDWARE_CATEGORIES = {"software", "furniture", "accessories", "network"}

    @staticmethod
    def _is_hardware_asset(asset: Asset) -> bool:
        category_name = (asset.category.category_name if asset.category else "") or ""
        return category_name.strip().lower() not in AssetInsightsService.NON_HARDWARE_CATEGORIES

    @staticmethod
    def _is_hardware_category_name(category_name: str | None) -> bool:
        return (category_name or "").strip().lower() not in AssetInsightsService.NON_HARDWARE_CATEGORIES

    @staticmethod
    def _apply_role_scope(query, current_user):
        from app.server.schema.employee import EmployeeRole
        from app.server.database.tenant import apply_tenant_filter

        # Apply strict organization isolation
        query = apply_tenant_filter(query, current_user, Asset)

        if current_user.role == EmployeeRole.SUPER_ADMIN:
            return query
        if current_user.role == EmployeeRole.ORG_ADMIN:
            return query
        if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
            return query.filter(Asset.branch_id == current_user.branch_id)
        if current_user.role == EmployeeRole.EMPLOYEE and current_user.branch_id:
            return query.filter(Asset.branch_id == current_user.branch_id)
        return query

    @staticmethod
    def _classify_health(score: int) -> str:
        if score >= 80:
            return "Healthy"
        if score >= 60:
            return "Good"
        if score >= 40:
            return "Warning"
        if score >= 20:
            return "Critical"
        return "Replace Immediately"

    @staticmethod
    def _get_usage_duration_days(db: Session, asset_id: str) -> int:
        records = db.query(Tracking).filter(Tracking.asset_id == asset_id).all()
        total_days = 0
        now = datetime.now()
        for record in records:
            if not record.assigned_date:
                continue
            start_time = record.assigned_date.replace(tzinfo=None) if record.assigned_date.tzinfo else record.assigned_date
            end_time = record.returned_at.replace(tzinfo=None) if record.returned_at and record.returned_at.tzinfo else (record.returned_at or now)
            total_days += max((end_time - start_time).days, 0)
        return total_days

    @staticmethod
    def _get_instance_usage_duration_days(db: Session, instance_id: str) -> int:
        records = db.query(Tracking).filter(Tracking.instance_id == instance_id).order_by(Tracking.assigned_date.asc()).all()
        total_days = 0
        now = datetime.now()
        for record in records:
            if not record.assigned_date:
                continue
            start_time = record.assigned_date.replace(tzinfo=None) if record.assigned_date.tzinfo else record.assigned_date
            end_time = record.returned_at.replace(tzinfo=None) if record.returned_at and record.returned_at.tzinfo else (record.returned_at or now)
            total_days += max((end_time - start_time).days, 0)
        return total_days

    @staticmethod
    def _instance_failure_count(db: Session, instance_id: str) -> int:
        return (
            db.query(Tracking)
            .filter(
                Tracking.instance_id == instance_id,
                Tracking.movement_type.in_([MovementType.REPAIR, MovementType.REPLACE, MovementType.WARRANTY]),
            )
            .count()
        )

    @staticmethod
    def _instance_repair_count(db: Session, instance_id: str) -> int:
        return (
            db.query(Tracking)
            .filter(
                Tracking.instance_id == instance_id,
                Tracking.movement_type.in_([MovementType.REPAIR, MovementType.WARRANTY]),
            )
            .count()
        )

    @staticmethod
    def _instance_health_score(db: Session, instance: AssetInstance) -> dict:
        model = instance.model
        category_name = model.category.category_name if model and model.category else ""
        if not AssetInsightsService._is_hardware_category_name(category_name):
            return {
                "health_score": 100,
                "classification": "Not Applicable",
                "asset_age_years": 0.0,
                "usage_duration_days": 0,
                "repair_count": 0,
                "failure_count": 0,
                "performance_issues_count": 0,
                "warranty_expired": False,
                "age_penalty": 0,
                "repair_penalty": 0,
                "failure_penalty": 0,
                "performance_penalty": 0,
                "warranty_penalty": 0,
                "usage_penalty": 0,
                "recommendation_hint": "Health score is not applicable for non-hardware assets.",
            }

        purchase_date = instance.purchase_date or (model.purchased_date if model else None)
        asset_age_years = 0.0
        if purchase_date:
            asset_age_years = max((date.today() - purchase_date).days / 365, 0)

        if asset_age_years >= 4:
            age_penalty = 25
        elif asset_age_years >= 3:
            age_penalty = 15
        elif asset_age_years >= 2:
            age_penalty = 10
        elif asset_age_years >= 1:
            age_penalty = 5
        else:
            age_penalty = 0

        usage_duration_days = AssetInsightsService._get_instance_usage_duration_days(db, instance.instance_id)
        if usage_duration_days >= 1460:
            usage_penalty = 15
        elif usage_duration_days >= 1095:
            usage_penalty = 12
        elif usage_duration_days >= 730:
            usage_penalty = 8
        elif usage_duration_days >= 365:
            usage_penalty = 5
        else:
            usage_penalty = 0

        repair_count = AssetInsightsService._instance_repair_count(db, instance.instance_id)
        failure_count = AssetInsightsService._instance_failure_count(db, instance.instance_id)
        performance_issues_count = failure_count
        repair_penalty = repair_count * 8
        failure_penalty = failure_count * 10
        performance_penalty = performance_issues_count * 5

        warranty_expiry = instance.warranty_expiry or AssetInsightsService._get_warranty_expiry(db, instance.asset_id)
        warranty_expired = bool(warranty_expiry is None or warranty_expiry < date.today())
        warranty_penalty = 10 if warranty_expired else 0

        status_penalty_map = {
            AssetStatus.NEW.value: 0,
            AssetStatus.AVAILABLE.value: 0,
            AssetStatus.ASSIGNED.value: 0,
            AssetStatus.USED.value: 5,
            AssetStatus.IN_REPAIR.value: 20,
            AssetStatus.NOT_USABLE.value: 30,
            AssetStatus.RETIRED.value: 60,
        }
        status_value = instance.status.value if hasattr(instance.status, "value") else str(instance.status)
        status_penalty = status_penalty_map.get(status_value, 0)

        purchase_cost = float(instance.purchase_cost or (model.purchase_cost if model else 0.0) or 0.0)
        maintenance_cost = float(model.maintenance_total_cost if model else 0.0)
        repair_cost = float(model.repair_total_cost if model else 0.0)
        spend_ratio_penalty = 0
        if purchase_cost > 0:
            ratio = (maintenance_cost + repair_cost) / purchase_cost
            if ratio >= 0.20:
                spend_ratio_penalty = 10
            elif ratio >= 0.10:
                spend_ratio_penalty = 5

        score = max(
            0,
            min(
                100,
                100
                - age_penalty
                - repair_penalty
                - failure_penalty
                - performance_penalty
                - usage_penalty
                - warranty_penalty
                - status_penalty
                - spend_ratio_penalty,
            ),
        )

        return {
            "health_score": score,
            "classification": AssetInsightsService._classify_health(score),
            "asset_age_years": round(asset_age_years, 2),
            "usage_duration_days": usage_duration_days,
            "repair_count": repair_count,
            "failure_count": failure_count,
            "performance_issues_count": performance_issues_count,
            "warranty_expired": warranty_expired,
            "age_penalty": age_penalty,
            "repair_penalty": repair_penalty,
            "failure_penalty": failure_penalty,
            "performance_penalty": performance_penalty,
            "warranty_penalty": warranty_penalty,
            "usage_penalty": usage_penalty,
            "recommendation_hint": (
                "Replace asset immediately." if score < 20 else
                "Urgent repair/replacement evaluation required." if score < 40 else
                "Inspect and maintain soon." if score < 60 else
                "Healthy for continued use and reallocation."
            ),
        }

    @staticmethod
    def _instance_health_read(db: Session, instance: AssetInstance) -> AssetHealthRead:
        model = instance.model
        metrics = AssetInsightsService._instance_health_score(db, instance)
        asset_name = model.name if model else instance.asset_id
        return AssetHealthRead(
            asset_id=instance.asset_id,
            instance_id=instance.instance_id,
            serial_number=instance.serial_number,
            asset_name=asset_name,
            status=instance.status.value if hasattr(instance.status, "value") else str(instance.status),
            health_score=metrics["health_score"],
            classification=metrics["classification"],
            asset_age_years=metrics["asset_age_years"],
            usage_duration_days=metrics["usage_duration_days"],
            repair_count=metrics["repair_count"],
            failure_count=metrics["failure_count"],
            performance_issues_count=metrics["performance_issues_count"],
            warranty_expired=metrics["warranty_expired"],
            age_penalty=metrics["age_penalty"],
            repair_penalty=metrics["repair_penalty"],
            failure_penalty=metrics["failure_penalty"],
            performance_penalty=metrics["performance_penalty"],
            warranty_penalty=metrics["warranty_penalty"],
            usage_penalty=metrics["usage_penalty"],
            recommendation_hint=metrics["recommendation_hint"],
        )

    @staticmethod
    def _base_instance_query(db: Session, current_user: Employee):
        from app.server.schema.employee import EmployeeRole

        query = db.query(AssetInstance).options(
            joinedload(AssetInstance.model).joinedload(Asset.category),
            joinedload(AssetInstance.model).joinedload(Asset.sub_category),
            joinedload(AssetInstance.branch_rel),
        )
        from app.server.database.tenant import apply_tenant_filter

        query = apply_tenant_filter(query, current_user, AssetInstance)
        if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
            query = query.filter(AssetInstance.branch_id == current_user.branch_id)
        return query.join(AssetInstance.model).outerjoin(Category).outerjoin(Branch)

    @staticmethod
    def _base_asset_query(db: Session, current_user: Employee):
        query = db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category))
        return AssetInsightsService._apply_role_scope(query, current_user)

    @staticmethod
    def search_assets(
        db: Session,
        current_user: Employee,
        *,
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
    ) -> dict:
        from sqlalchemy import or_
        query = AssetInsightsService._base_asset_query(db, current_user).join(Category).outerjoin(SubCategory).outerjoin(Branch)
        
        if category_id:
            query = query.filter(Asset.category_id == category_id)
        if category:
            query = query.filter(Category.category_name.ilike(f"%{category.strip()}%"))
        if sub_category_id:
            query = query.filter(Asset.sub_category_id == sub_category_id)
        if sub_category:
            query = query.filter(SubCategory.sub_category_name.ilike(f"%{sub_category.strip()}%"))
        if branch_id:
            query = query.filter(Asset.branch_id == branch_id)
        if branch:
            query = query.filter(Branch.branch_name.ilike(f"%{branch.strip()}%"))

        if status:
            normalized = status.strip().lower()
            if normalized == "available":
                query = query.filter(Asset.unused > 0)
            elif normalized == "allocated":
                query = query.filter(Asset.used > 0)
            elif normalized == "low_stock":
                query = query.filter(Asset.unused <= Asset.low_stock_threshold)
            else:
                query = query.filter(Asset.asset_status == status.strip().upper())

        if available_only:
            query = query.filter(Asset.unused > 0)
        if allocated_only:
            query = query.filter(Asset.used > 0)
        if low_stock_only:
            query = query.filter(Asset.unused <= Asset.low_stock_threshold)

        if search:
            needle = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Asset.name.ilike(needle),
                    Asset.asset_id.ilike(needle),
                    Asset.brand.ilike(needle),
                    Asset.model.ilike(needle),
                    Category.category_name.ilike(needle),
                    SubCategory.sub_category_name.ilike(needle),
                    Branch.branch_name.ilike(needle),
                    func.cast(Asset.asset_status, String).ilike(needle),
                )
            )

        total = query.count()
        assets = query.order_by(Asset.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        items = [
            AssetListItem(
                asset_id=asset.asset_id,
                name=asset.name,
                brand=asset.brand,
                model=asset.model,
                category_id=asset.category_id,
                category=asset.category.category_name if asset.category else None,
                sub_category_id=asset.sub_category_id,
                sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                branch_id=asset.branch_id,
                branch=asset.branch,
                status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
                total_quantity=asset.total_quantity,
                used=asset.used,
                unused=asset.unused,
                low_stock=asset.unused <= (asset.low_stock_threshold or 0),
            )
            for asset in assets
        ]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page
        }

    @staticmethod
    def list_asset_options(db: Session, current_user: Employee) -> list[AssetListItem]:
        query = AssetInsightsService._base_asset_query(db, current_user)
        assets = query.order_by(Asset.name.asc(), Asset.asset_id.asc()).all()
        return [
            AssetListItem(
                asset_id=asset.asset_id,
                name=asset.name,
                brand=asset.brand,
                model=asset.model,
                category_id=asset.category_id,
                category=asset.category.category_name if asset.category else None,
                sub_category_id=asset.sub_category_id,
                sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                branch_id=asset.branch_id,
                branch=asset.branch,
                status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
                total_quantity=asset.total_quantity,
                used=asset.used,
                unused=asset.unused,
                low_stock=asset.unused <= (asset.low_stock_threshold or 0),
            )
            for asset in assets
        ]


    @staticmethod
    def _matches_asset_filters(
        asset: Asset,
        *,
        search: Optional[str] = None,
        category: Optional[str] = None,
        sub_category: Optional[str] = None,
        branch: Optional[str] = None,
        status: Optional[str] = None,
        available_only: bool = False,
        allocated_only: bool = False,
        low_stock_only: bool = False,
    ) -> bool:
        category_name = asset.category.category_name if asset.category else ""
        sub_category_name = asset.sub_category.sub_category_name if asset.sub_category else ""
        asset_status = asset.asset_status.value if asset.asset_status else ""

        if category and category.strip().lower() not in category_name.lower():
            return False
        if sub_category and sub_category.strip().lower() not in sub_category_name.lower():
            return False
        if branch and branch.strip().lower() not in (asset.branch or "").lower():
            return False

        if status:
            normalized = status.strip().lower()
            if normalized == "available" and asset.unused <= 0:
                return False
            if normalized == "allocated" and asset.used <= 0:
                return False
            if normalized == "low_stock" and asset.unused > (asset.low_stock_threshold or 0):
                return False
            if normalized not in {"available", "allocated", "low_stock"} and normalized != asset_status.lower():
                return False

        if available_only and asset.unused <= 0:
            return False
        if allocated_only and asset.used <= 0:
            return False
        if low_stock_only and asset.unused > (asset.low_stock_threshold or 0):
            return False

        if search:
            needle = search.strip().lower()
            haystacks = [
                asset.asset_id or "",
                asset.name or "",
                category_name,
                sub_category_name,
                asset.branch or "",
                asset_status,
                asset.brand or "",
                asset.vendor_name or "",
                asset.vendor_contact or "",
                asset.invoice_number or "",
            ]
            if not any(needle in value.lower() for value in haystacks):
                return False

        return True

    @staticmethod
    def _get_warranty_expiry(db: Session, asset_id: str) -> Optional[date]:
        rows = (
            db.query(AssetAttribute.attribute_name, AssetAttributeValue.value)
            .join(AssetAttributeValue, AssetAttribute.attribute_id == AssetAttributeValue.attribute_id)
            .filter(AssetAttributeValue.asset_id == asset_id)
            .all()
        )
        for attr_name, value in rows:
            name = (attr_name or "").strip().lower()
            if "warranty" in name and value:
                try:
                    return datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    return None
        return None

    @staticmethod
    def get_asset_finance(db: Session, asset_id: str, current_user: Employee) -> AssetFinanceRead:
        asset = AssetInsightsService._base_asset_query(db, current_user).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        purchase_cost = float(asset.purchase_cost or 0.0)
        salvage_value = float(asset.salvage_value or 0.0)
        maintenance_cost = float(asset.maintenance_total_cost or 0.0)
        repair_cost = float(asset.repair_total_cost or 0.0)
        sub_license_cost = float(asset.sub_license_cost or 0.0)
        useful_life = int(asset.useful_life_years or 5)
        purchased_date = asset.purchased_date
        today = date.today()
        asset_age_days = max((today - purchased_date).days, 0) if purchased_date else 0
        annual_depreciation = (purchase_cost - salvage_value) / useful_life if useful_life else 0.0
        accumulated_depreciation = min(annual_depreciation * (asset_age_days / 365), max(purchase_cost - salvage_value, 0.0))
        book_value = max(purchase_cost - accumulated_depreciation, salvage_value)
        tco = purchase_cost + maintenance_cost + repair_cost + sub_license_cost

        return AssetFinanceRead(
            asset_id=asset.asset_id,
            asset_name=asset.name,
            branch=asset.branch,
            purchased_date=asset.purchased_date,
            purchase_cost=round(purchase_cost, 2),
            buying_value=round(purchase_cost, 2),
            salvage_value=round(salvage_value, 2),
            reselling_value=round(salvage_value, 2),
            maintenance_cost=round(maintenance_cost, 2),
            service_cost=round(repair_cost, 2),
            maintenance_service_value=round(maintenance_cost + repair_cost, 2),
            repair_cost=round(repair_cost, 2),
            sub_license_cost=round(sub_license_cost, 2),
            asset_age_days=asset_age_days,
            useful_life_years=useful_life,
            annual_depreciation=round(annual_depreciation, 2),
            accumulated_depreciation=round(accumulated_depreciation, 2),
            book_value=round(book_value, 2),
            total_cost_of_ownership=round(tco, 2),
        )

    @staticmethod
    def _build_finance_monitor_item(db: Session, asset: Asset, current_user: Employee) -> AssetFinanceMonitorItem:
        finance = AssetInsightsService.get_asset_finance(db, asset.asset_id, current_user)
        health = AssetInsightsService.get_asset_health(db, asset.asset_id, current_user)
        recommendation = AssetInsightsService.get_replacement_recommendation(db, asset.asset_id, current_user)
        return AssetFinanceMonitorItem(
            asset_id=asset.asset_id,
            asset_name=asset.name,
            category=asset.category.category_name if asset.category else None,
            sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
            branch=asset.branch,
            status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
            total_quantity=asset.total_quantity,
            used=asset.used,
            unused=asset.unused,
            low_stock=asset.unused <= (asset.low_stock_threshold or 0),
            purchased_date=finance.purchased_date,
            purchase_cost=finance.purchase_cost,
            buying_value=finance.buying_value,
            salvage_value=finance.salvage_value,
            reselling_value=finance.reselling_value,
            maintenance_cost=finance.maintenance_cost,
            service_cost=finance.service_cost,
            maintenance_service_value=finance.maintenance_service_value,
            repair_cost=finance.repair_cost,
            sub_license_cost=finance.sub_license_cost,
            asset_age_days=finance.asset_age_days,
            useful_life_years=finance.useful_life_years,
            annual_depreciation=finance.annual_depreciation,
            accumulated_depreciation=finance.accumulated_depreciation,
            book_value=finance.book_value,
            total_cost_of_ownership=finance.total_cost_of_ownership,
            health_score=health.health_score,
            health_classification=health.classification,
            replacement_recommendation=recommendation.recommendation,
            recommendation_reason=recommendation.reason,
        )

    @staticmethod
    def get_asset_detail(db: Session, asset_id: str, current_user: Employee) -> AssetDetailRead:
        asset = AssetInsightsService._base_asset_query(db, current_user).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        finance = AssetInsightsService.get_asset_finance(db, asset_id, current_user)
        health = AssetInsightsService.get_asset_health(db, asset_id, current_user)
        recommendation = AssetInsightsService.get_replacement_recommendation(db, asset_id, current_user)

        return AssetDetailRead(
            asset_id=asset.asset_id,
            name=asset.name,
            category=asset.category.category_name if asset.category else None,
            sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
            brand=asset.brand,
            branch=asset.branch,
            status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
            total_quantity=asset.total_quantity,
            used=asset.used,
            unused=asset.unused,
            low_stock=asset.unused <= (asset.low_stock_threshold or 0),
            low_stock_threshold=asset.low_stock_threshold or 0,
            purchased_date=finance.purchased_date,
            purchase_cost=finance.purchase_cost,
            buying_value=finance.buying_value,
            salvage_value=finance.salvage_value,
            reselling_value=finance.reselling_value,
            maintenance_cost=finance.maintenance_cost,
            service_cost=finance.service_cost,
            maintenance_service_value=finance.maintenance_service_value,
            repair_cost=finance.repair_cost,
            sub_license_cost=finance.sub_license_cost,
            asset_age_days=finance.asset_age_days,
            useful_life_years=finance.useful_life_years,
            annual_depreciation=finance.annual_depreciation,
            accumulated_depreciation=finance.accumulated_depreciation,
            book_value=finance.book_value,
            total_cost_of_ownership=finance.total_cost_of_ownership,
            health_score=health.health_score,
            recommendation=recommendation.recommendation,
            recommendation_reason=recommendation.reason,
            vendor_name=asset.vendor_name,
            vendor_contact=asset.vendor_contact,
            invoice_number=asset.invoice_number,
        )

    @staticmethod
    def get_finance_report(
        db: Session,
        current_user: Employee,
        branch: Optional[str] = None,
        *,
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
    ) -> AssetFinanceReportRead:
        query = AssetInsightsService._base_asset_query(db, current_user)
        assets = [
            asset for asset in query.all()
            if AssetInsightsService._matches_asset_filters(
                asset,
                search=search,
                category=category,
                sub_category=sub_category,
                branch=branch,
                status=status,
                available_only=available_only,
                allocated_only=allocated_only,
                low_stock_only=low_stock_only,
            )
        ]

        all_items = [AssetInsightsService._build_finance_monitor_item(db, asset, current_user) for asset in assets]
        if recommendation:
            desired = recommendation.strip().upper()
            all_items = [item for item in all_items if item.replacement_recommendation.upper() == desired]
        if min_tco is not None:
            all_items = [item for item in all_items if item.total_cost_of_ownership >= min_tco]
        if max_tco is not None:
            all_items = [item for item in all_items if item.total_cost_of_ownership <= max_tco]
        if min_health_score is not None:
            all_items = [item for item in all_items if item.health_score >= min_health_score]
        if max_health_score is not None:
            all_items = [item for item in all_items if item.health_score <= max_health_score]

        if sort_by == "health":
            all_items = sorted(all_items, key=lambda item: (item.health_score, -item.total_cost_of_ownership))
        elif sort_by == "tco":
            all_items = sorted(all_items, key=lambda item: item.total_cost_of_ownership, reverse=True)
        elif sort_by == "maintenance":
            all_items = sorted(all_items, key=lambda item: item.maintenance_cost, reverse=True)
        elif sort_by == "repair":
            all_items = sorted(all_items, key=lambda item: item.repair_cost, reverse=True)
        elif sort_by == "depreciation":
            all_items = sorted(all_items, key=lambda item: item.accumulated_depreciation, reverse=True)
        else:
            all_items = sorted(
                all_items,
                key=lambda item: (
                    item.replacement_recommendation == "REPLACE",
                    item.low_stock,
                    -item.health_score,
                    item.total_cost_of_ownership,
                ),
                reverse=True,
            )

        total = len(all_items)
        items = all_items[(page - 1) * per_page : page * per_page]

        return AssetFinanceReportRead(
            branch=branch,
            asset_count=total,
            total_purchase_cost=round(sum(row.purchase_cost for row in all_items), 2),
            total_maintenance_cost=round(sum(row.maintenance_cost for row in all_items), 2),
            total_repair_cost=round(sum(row.repair_cost for row in all_items), 2),
            total_license_cost=round(sum(row.sub_license_cost for row in all_items), 2),
            total_depreciation=round(sum(row.accumulated_depreciation for row in all_items), 2),
            total_cost_of_ownership=round(sum(row.total_cost_of_ownership for row in all_items), 2),
            items=items,
            page=page,
            per_page=per_page,
            total=total
        )

    @staticmethod
    def get_finance_options() -> AssetFinanceOptionsRead:
        return AssetFinanceOptionsRead(
            sort_options=[
                FinanceSortOption(value="priority_cost", label="Priority monitoring"),
                FinanceSortOption(value="tco", label="Highest TCO"),
                FinanceSortOption(value="maintenance", label="Highest maintenance"),
                FinanceSortOption(value="repair", label="Highest repair cost"),
                FinanceSortOption(value="depreciation", label="Highest depreciation"),
                FinanceSortOption(value="health", label="Lowest health first"),
            ]
        )


    @staticmethod
    def get_asset_health(db: Session, asset_id: str, current_user: Employee) -> AssetHealthRead:
        asset = AssetInsightsService._base_asset_query(db, current_user).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        instances = (
            AssetInsightsService._base_instance_query(db, current_user)
            .filter(AssetInstance.asset_id == asset_id)
            .order_by(AssetInstance.created_at.asc())
            .all()
        )
        if not instances:
            # Fallback for legacy model-only records.
            if not AssetInsightsService._is_hardware_asset(asset):
                return AssetHealthRead(
                    asset_id=asset.asset_id,
                    health_score=100,
                    classification="Not Applicable",
                    asset_age_years=0.0,
                    usage_duration_days=0,
                    repair_count=0,
                    failure_count=0,
                    performance_issues_count=0,
                    warranty_expired=False,
                    age_penalty=0,
                    repair_penalty=0,
                    failure_penalty=0,
                    performance_penalty=0,
                    warranty_penalty=0,
                    usage_penalty=0,
                    recommendation_hint="Health score is not applicable for non-hardware assets.",
                )
            pseudo = AssetInstance(
                instance_id=asset.asset_id,
                asset_id=asset.asset_id,
                branch_id=asset.branch_id,
                organization_id=asset.organization_id,
                status=asset.asset_status,
                purchase_date=asset.purchased_date,
                purchase_cost=asset.purchase_cost,
            )
            pseudo.model = asset
            return AssetInsightsService._instance_health_read(db, pseudo)

        # Return the most at-risk active instance first; keeps the endpoint instance-centric.
        ranked_instances = sorted(
            instances,
            key=lambda item: (
                0 if (item.status and getattr(item.status, "value", str(item.status)) == AssetStatus.ASSIGNED.value) else 1,
                0 if (item.status and getattr(item.status, "value", str(item.status)) == AssetStatus.AVAILABLE.value) else 1,
                item.created_at or datetime.min,
            ),
        )
        return AssetInsightsService._instance_health_read(db, ranked_instances[0])

    @staticmethod
    def get_replacement_recommendation(db: Session, asset_id: str, current_user: Employee) -> AssetRecommendationRead:
        asset = AssetInsightsService._base_asset_query(db, current_user).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)
        if not AssetInsightsService._is_hardware_asset(asset):
            return AssetRecommendationRead(
                asset_id=asset_id,
                recommendation="RETAIN",
                reason="Replacement recommendation is not applicable for non-hardware assets.",
            )

        health = AssetInsightsService.get_asset_health(db, asset_id, current_user)
        if health.health_score < 30:
            return AssetRecommendationRead(
                asset_id=asset_id,
                recommendation="REPLACE",
                reason="Health score is below 30; replacement is recommended.",
            )
        if 30 <= health.health_score <= 50:
            return AssetRecommendationRead(
                asset_id=asset_id,
                recommendation="REPAIR",
                reason="Health score is between 30 and 50; repair is preferred over replacement.",
            )
        # Good/Healthy assets are retained for reallocation
        return AssetRecommendationRead(
            asset_id=asset_id,
            recommendation="RETAIN",
            reason="Health score is above 50; asset can continue in use or be reallocated.",
        )

    @staticmethod
    def _build_health_item(db: Session, instance: AssetInstance, current_user: Employee) -> AssetHealthReportItem:
        metrics = AssetInsightsService._instance_health_score(db, instance)
        model = instance.model
        category = model.category.category_name if model and model.category else None
        sub_category = model.sub_category.sub_category_name if model and model.sub_category else None
        return AssetHealthReportItem(
            asset_id=instance.asset_id,
            instance_id=instance.instance_id,
            serial_number=instance.serial_number,
            asset_name=model.name if model else instance.asset_id,
            category=category,
            sub_category=sub_category,
            branch=instance.branch or (model.branch if model else None),
            status=instance.status.value if hasattr(instance.status, "value") else str(instance.status),
            health_score=metrics["health_score"],
            classification=metrics["classification"],
            recommendation=("REPLACE" if metrics["health_score"] < 30 else "REPAIR" if metrics["health_score"] <= 50 else "RETAIN"),
            recommendation_reason=metrics["recommendation_hint"],
            asset_age_years=metrics["asset_age_years"],
            usage_duration_days=metrics["usage_duration_days"],
            repair_count=metrics["repair_count"],
            failure_count=metrics["failure_count"],
            performance_issues_count=metrics["performance_issues_count"],
            warranty_expired=metrics["warranty_expired"],
            purchase_cost=float(instance.purchase_cost or (model.purchase_cost if model else 0.0) or 0.0),
            maintenance_cost=float(model.maintenance_total_cost if model else 0.0),
            repair_cost=float(model.repair_total_cost if model else 0.0),
            reselling_value=float(model.salvage_value if model and model.salvage_value is not None else 0.0),
            failure_penalty=metrics["failure_penalty"],
        )

    @staticmethod
    def get_health_report(
        db: Session,
        current_user: Employee,
        *,
        branch: Optional[str] = None,
        search: Optional[str] = None,
        category: Optional[str] = None,
        min_health_score: Optional[int] = None,
        max_health_score: Optional[int] = None,
        health_range: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        critical_only: bool = False,
    ) -> AssetHealthReportRead:
        query = AssetInsightsService._base_instance_query(db, current_user)
        if branch:
            query = query.filter(func.lower(func.coalesce(Branch.branch_name, "")) == branch.strip().lower())
        if category:
            query = query.filter(Category.category_name.ilike(f"%{category.strip()}%"))
        if search:
            needle = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    AssetInstance.instance_id.ilike(needle),
                    AssetInstance.serial_number.ilike(needle),
                    Asset.name.ilike(needle),
                )
            )

        items: list[AssetHealthReportItem] = []
        for instance in query.all():
            if not instance.model or not AssetInsightsService._is_hardware_asset(instance.model):
                continue
            report_item = AssetInsightsService._build_health_item(db, instance, current_user)
            if health_range:
                try:
                    start_str, end_str = health_range.split("-", 1)
                    start_value = int(start_str)
                    end_value = int(end_str)
                    if not (start_value <= report_item.health_score <= end_value):
                        continue
                except ValueError:
                    pass
            if min_health_score is not None and report_item.health_score < min_health_score:
                continue
            if max_health_score is not None and report_item.health_score > max_health_score:
                continue
            if critical_only and report_item.health_score > 39:
                continue
            items.append(report_item)

        items.sort(key=lambda item: (item.health_score, item.failure_penalty, item.repair_count, item.asset_name.lower()))
        total = len(items)
        page = max(1, page)
        per_page = max(1, min(per_page, 10000))
        paged_items = items[(page - 1) * per_page : (page - 1) * per_page + per_page]
        return AssetHealthReportRead(
            asset_count=total,
            healthy_assets=sum(1 for item in items if item.classification == "Healthy"),
            good_assets=sum(1 for item in items if item.classification == "Good"),
            warning_assets=sum(1 for item in items if item.classification == "Warning"),
            critical_assets=sum(1 for item in items if item.classification in {"Critical", "Replace Immediately"}),
            replacement_candidates=sum(1 for item in items if item.recommendation == "REPLACE"),
            items=paged_items,
            total=total,
            page=page,
            per_page=per_page,
        )

    @staticmethod
    def get_health_filter_options(db: Session, current_user: Employee) -> AssetHealthFilterOptions:
        query = AssetInsightsService._base_instance_query(db, current_user)
        instances = query.all()
        branches = sorted({(instance.branch or instance.branch_id or "").strip() for instance in instances if (instance.branch or instance.branch_id)})
        categories = sorted({(instance.model.category.category_name if instance.model and instance.model.category else "").strip() for instance in instances if instance.model and instance.model.category and AssetInsightsService._is_hardware_category_name(instance.model.category.category_name)})

        health_ranges = [
            HealthRangeOption(label="Critical (0-39)", value="0-39"),
            HealthRangeOption(label="Warning (40-59)", value="40-59"),
            HealthRangeOption(label="Good (60-79)", value="60-79"),
            HealthRangeOption(label="Healthy (80-100)", value="80-100"),
        ]
        statuses = [status.value for status in [AssetStatus.NEW, AssetStatus.AVAILABLE, AssetStatus.ASSIGNED, AssetStatus.IN_REPAIR, AssetStatus.NOT_USABLE, AssetStatus.RETIRED]]
        return AssetHealthFilterOptions(branches=branches, categories=categories, health_ranges=health_ranges, statuses=statuses)

    @staticmethod
    def get_health_classification(db: Session, current_user: Employee) -> dict[str, int]:
        report = AssetInsightsService.get_health_report(db, current_user, page=1, per_page=10000)
        return {
            "Healthy": report.healthy_assets,
            "Good": report.good_assets,
            "Warning": report.warning_assets,
            "Critical": report.critical_assets,
            "ReplaceImmediately": report.replacement_candidates,
        }

    @staticmethod
    def get_utilization_summary(db: Session, current_user: Employee) -> list[UtilizationItem]:
        assets = AssetInsightsService._base_asset_query(db, current_user).all()
        branch_category_map: dict[tuple[str | None, str | None], dict[str, float]] = {}
        for asset in assets:
            key = (asset.branch, asset.category.category_name if asset.category else None)
            bucket = branch_category_map.setdefault(
                key,
                {"asset_count": 0, "total_quantity": 0, "used_quantity": 0, "unused_quantity": 0},
            )
            bucket["asset_count"] += 1
            bucket["total_quantity"] += asset.total_quantity
            bucket["used_quantity"] += asset.used
            bucket["unused_quantity"] += asset.unused

        items: list[UtilizationItem] = []
        for (branch, category), bucket in branch_category_map.items():
            total_quantity = int(bucket["total_quantity"])
            used_quantity = int(bucket["used_quantity"])
            unused_quantity = int(bucket["unused_quantity"])
            usage_rate = round((used_quantity / total_quantity), 2) if total_quantity else 0.0
            suggestion = None
            if unused_quantity >= 10 and usage_rate < 0.4:
                suggestion = f"Consider shifting idle {category or 'assets'} from {branch or 'unassigned branch'} to a higher-demand branch."
            elif usage_rate > 0.85:
                suggestion = f"{branch or 'This branch'} is heavily utilized for {category or 'assets'}; plan replenishment."
            items.append(
                UtilizationItem(
                    branch=branch,
                    category=category,
                    asset_count=int(bucket["asset_count"]),
                    total_quantity=total_quantity,
                    used_quantity=used_quantity,
                    unused_quantity=unused_quantity,
                    usage_rate=usage_rate,
                    suggestion=suggestion,
                )
            )
        return items

    @staticmethod
    def get_branch_analytics(db: Session, current_user: Employee, branch: Optional[str] = None) -> list[UtilizationItem]:
        items = AssetInsightsService.get_utilization_summary(db, current_user)
        if branch:
            branch_lower = branch.strip().lower()
            return [item for item in items if (item.branch or "").lower() == branch_lower]
        return items

    @staticmethod
    def search_discovery(
        db: Session,
        *,
        current_user,
        q: str,
        limit: int = 10,
    ) -> SearchResultsRead:
        query = AssetInsightsService._apply_role_scope(
            db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category)),
            current_user,
        )
        assets = query.all()
        needle = (q or "").strip().lower()
        if not needle:
            return SearchResultsRead(query="", total=0, did_you_mean=[], items=[])

        # Sort tiers: 0 = category/subcategory substring match (highest), 1 = asset name substring,
        # 2 = fuzzy / similarity only. Keeps e.g. "laptop" matches in Laptop category above weak fuzzy hits on names.
        ranked_rows: list[tuple[int, float, SearchSuggestionItem]] = []
        names_for_spell = []
        for asset in assets:
            cat = asset.category.category_name if asset.category else ""
            sub = asset.sub_category.sub_category_name if asset.sub_category else ""
            names_for_spell.extend([asset.name or "", cat, sub])

            cat_l = cat.lower()
            sub_l = sub.lower()
            name_l = (asset.name or "").lower()
            tier = 2
            best = 0.0

            if needle in cat_l or needle in sub_l:
                tier = 0
                best = 1.0 if (cat_l.startswith(needle) or sub_l.startswith(needle)) else 0.95
            elif needle in name_l:
                tier = 1
                best = 1.0 if name_l.startswith(needle) else 0.9
            else:
                fields = [asset.name or "", cat, sub]
                for field in fields:
                    low = field.lower()
                    if not low:
                        continue
                    if needle in low:
                        score = 1.0 if low.startswith(needle) else 0.9
                    else:
                        score = SequenceMatcher(None, needle, low).ratio()
                    if score > best:
                        best = score
                if best < 0.45:
                    continue

            ranked_rows.append(
                (
                    tier,
                    -best,
                    SearchSuggestionItem(
                        asset_id=asset.asset_id,
                        asset_name=asset.name,
                        category=cat or None,
                        sub_category=sub or None,
                        branch=asset.branch,
                        score=round(best, 3),
                    ),
                )
            )

        ranked_rows.sort(key=lambda t: (t[0], t[1], (t[2].asset_name or "").lower()))
        ranked = [t[2] for t in ranked_rows]
        did_you_mean = []
        if not ranked:
            did_you_mean = get_close_matches(needle, [n.lower() for n in names_for_spell if n], n=5, cutoff=0.6)

        return SearchResultsRead(
            query=q,
            total=len(ranked),
            did_you_mean=did_you_mean,
            items=ranked[: max(1, min(limit, 10))],
        )

    @staticmethod
    def search_suggestions(db: Session, *, current_user, q: str, limit: int = 10) -> list[SearchSuggestionItem]:
        return AssetInsightsService.search_discovery(db, current_user=current_user, q=q, limit=limit).items

    @staticmethod
    def popular_assets(db: Session, *, current_user, limit: int = 10) -> list[SearchSuggestionItem]:
        scoped = AssetInsightsService._apply_role_scope(
            db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category)),
            current_user,
        ).all()
        req_counts = dict(
            db.query(Request.asset_name, func.count(Request.request_id))
            .group_by(Request.asset_name)
            .all()
        )
        ranked = []
        for asset in scoped:
            ranked.append(
                (
                    int(req_counts.get(asset.name, 0)),
                    asset,
                )
            )
        ranked.sort(key=lambda r: (-r[0], -(r[1].used or 0), r[1].name.lower()))
        items = []
        for _, asset in ranked[: max(1, min(limit, 10))]:
            items.append(
                SearchSuggestionItem(
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    category=asset.category.category_name if asset.category else None,
                    sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                    branch=asset.branch,
                    score=1.0,
                )
            )
        return items

    @staticmethod
    def recent_requested_assets(db: Session, *, current_user, limit: int = 10) -> list[SearchSuggestionItem]:
        scoped_assets = AssetInsightsService._apply_role_scope(
            db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category)),
            current_user,
        ).all()
        by_name = {a.name.lower(): a for a in scoped_assets if a.name}
        rows = (
            db.query(Request.asset_name)
            .order_by(Request.req_date.desc())
            .limit(max(10, limit * 4))
            .all()
        )
        out = []
        seen = set()
        for (name,) in rows:
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            asset = by_name.get(key)
            if not asset:
                continue
            out.append(
                SearchSuggestionItem(
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    category=asset.category.category_name if asset.category else None,
                    sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                    branch=asset.branch,
                    score=1.0,
                )
            )
            if len(out) >= max(1, min(limit, 10)):
                break
        return out

    @staticmethod
    def list_categories(db: Session) -> list[CategoryRead]:
        rows = db.query(Category).order_by(Category.category_name.asc()).all()
        return [
            CategoryRead(
                category_id=r.category_id,
                category_name=r.category_name,
                description=r.description,
            )
            for r in rows
        ]

    @staticmethod
    def list_subcategories(db: Session, category_id: str) -> list[SubCategoryRead]:
        rows = (
            db.query(SubCategory)
            .filter(SubCategory.category_id == category_id)
            .order_by(SubCategory.sub_category_name.asc())
            .all()
        )
        return [
            SubCategoryRead(
                sub_category_id=r.sub_category_id,
                category_id=r.category_id,
                sub_category_name=r.sub_category_name,
                description=r.description,
            )
            for r in rows
        ]

    @staticmethod
    def list_assets_by_subcategory(db: Session, *, current_user, sub_category_id: str) -> list[AssetListItem]:
        query = AssetInsightsService._apply_role_scope(
            db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category)),
            current_user,
        )
        assets = query.filter(Asset.sub_category_id == sub_category_id).all()
        return [
            AssetListItem(
                asset_id=asset.asset_id,
                name=asset.name,
                brand=asset.brand,
                model=asset.model,
                category_id=asset.category_id,
                category=asset.category.category_name if asset.category else None,
                sub_category_id=asset.sub_category_id,
                sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                branch_id=asset.branch_id,
                branch=asset.branch,
                status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
                total_quantity=asset.total_quantity,
                used=asset.used,
                unused=asset.unused,
                low_stock=asset.unused <= (asset.low_stock_threshold or 0),
            )
            for asset in assets
        ]
