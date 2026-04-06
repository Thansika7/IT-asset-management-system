from __future__ import annotations

from datetime import date, datetime, timedelta
from difflib import SequenceMatcher, get_close_matches
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.server.exceptions.base import ResourceNotFoundError
from app.server.models.asset_insights import (
    AssetDetailRead,
    AssetFinanceRead,
    AssetFinanceMonitorItem,
    AssetFinanceReportRead,
    AssetHealthRead,
    AssetHealthReportItem,
    AssetHealthReportRead,
    AssetListItem,
    AssetRecommendationRead,
    CategoryRead,
    SearchResultsRead,
    SearchSuggestionItem,
    SubCategoryRead,
    UtilizationItem,
)
from app.server.schema.request import Request
from app.server.schema.asset import Asset
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.category import Category, SubCategory
from app.server.schema.tracking import Tracking


class AssetInsightsService:
    @staticmethod
    def _apply_role_scope(query, current_user):
        from app.server.schema.employee import EmployeeRole

        if current_user.role in [EmployeeRole.ADMIN, EmployeeRole.MANAGER]:
            return query
        if current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
            return query.filter(Asset.branch == current_user.branch)
        if current_user.role == EmployeeRole.EMPLOYEE and current_user.branch:
            return query.filter(Asset.branch == current_user.branch)
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
    def _base_asset_query(db: Session):
        return db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category))

    @staticmethod
    def search_assets(
        db: Session,
        *,
        search: Optional[str] = None,
        category: Optional[str] = None,
        sub_category: Optional[str] = None,
        branch: Optional[str] = None,
        status: Optional[str] = None,
        available_only: bool = False,
        allocated_only: bool = False,
        low_stock_only: bool = False,
    ) -> list[AssetListItem]:
        query = AssetInsightsService._base_asset_query(db).join(Category)
        if sub_category:
            query = query.outerjoin(SubCategory)

        if category:
            query = query.filter(Category.category_name.ilike(f"%{category.strip()}%"))
        if sub_category:
            query = query.filter(SubCategory.sub_category_name.ilike(f"%{sub_category.strip()}%"))
        if branch:
            query = query.filter(Asset.branch.ilike(f"%{branch.strip()}%"))

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

        assets = query.all()
        if search:
            needle = search.strip().lower()
            assets = [
                asset for asset in assets
                if needle in (asset.name or "").lower()
                or needle in ((asset.category.category_name if asset.category else "")).lower()
                or needle in ((asset.sub_category.sub_category_name if asset.sub_category else "")).lower()
                or needle in ((asset.branch or "")).lower()
                or needle in ((asset.asset_status.value if asset.asset_status else "")).lower()
            ]

        return [
            AssetListItem(
                asset_id=asset.asset_id,
                name=asset.name,
                category=asset.category.category_name if asset.category else None,
                sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
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
    def get_asset_finance(db: Session, asset_id: str) -> AssetFinanceRead:
        asset = AssetInsightsService._base_asset_query(db).filter(Asset.asset_id == asset_id).first()
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
    def _build_finance_monitor_item(db: Session, asset: Asset) -> AssetFinanceMonitorItem:
        finance = AssetInsightsService.get_asset_finance(db, asset.asset_id)
        health = AssetInsightsService.get_asset_health(db, asset.asset_id)
        recommendation = AssetInsightsService.get_replacement_recommendation(db, asset.asset_id)
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
    def get_asset_detail(db: Session, asset_id: str) -> AssetDetailRead:
        asset = AssetInsightsService._base_asset_query(db).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        finance = AssetInsightsService.get_asset_finance(db, asset_id)
        health = AssetInsightsService.get_asset_health(db, asset_id)
        recommendation = AssetInsightsService.get_replacement_recommendation(db, asset_id)

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
    ) -> AssetFinanceReportRead:
        query = AssetInsightsService._base_asset_query(db)
        if branch:
            query = query.filter(Asset.branch == branch)
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

        items = [AssetInsightsService._build_finance_monitor_item(db, asset) for asset in assets]
        if recommendation:
            desired = recommendation.strip().upper()
            items = [item for item in items if item.replacement_recommendation.upper() == desired]
        if min_tco is not None:
            items = [item for item in items if item.total_cost_of_ownership >= min_tco]
        if max_tco is not None:
            items = [item for item in items if item.total_cost_of_ownership <= max_tco]
        if min_health_score is not None:
            items = [item for item in items if item.health_score >= min_health_score]
        if max_health_score is not None:
            items = [item for item in items if item.health_score <= max_health_score]

        if sort_by == "health":
            items = sorted(items, key=lambda item: (item.health_score, -item.total_cost_of_ownership))
        elif sort_by == "tco":
            items = sorted(items, key=lambda item: item.total_cost_of_ownership, reverse=True)
        elif sort_by == "maintenance":
            items = sorted(items, key=lambda item: item.maintenance_cost, reverse=True)
        elif sort_by == "repair":
            items = sorted(items, key=lambda item: item.repair_cost, reverse=True)
        elif sort_by == "depreciation":
            items = sorted(items, key=lambda item: item.accumulated_depreciation, reverse=True)
        else:
            items = sorted(
                items,
                key=lambda item: (
                    item.replacement_recommendation == "REPLACE",
                    item.low_stock,
                    -item.health_score,
                    item.total_cost_of_ownership,
                ),
                reverse=True,
            )

        return AssetFinanceReportRead(
            branch=branch,
            asset_count=len(items),
            total_purchase_cost=round(sum(row.purchase_cost for row in items), 2),
            total_maintenance_cost=round(sum(row.maintenance_cost for row in items), 2),
            total_repair_cost=round(sum(row.repair_cost for row in items), 2),
            total_license_cost=round(sum(row.sub_license_cost for row in items), 2),
            total_depreciation=round(sum(row.accumulated_depreciation for row in items), 2),
            total_cost_of_ownership=round(sum(row.total_cost_of_ownership for row in items), 2),
            items=items,
        )

    @staticmethod
    def get_asset_health(db: Session, asset_id: str) -> AssetHealthRead:
        asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        asset_age_years = 0.0
        if asset.purchased_date:
            asset_age_years = max((date.today() - asset.purchased_date).days / 365, 0)

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

        repair_count = int(asset.repair_count or 0)
        performance_issues_count = int(asset.performance_issues_count or 0)
        usage_duration_days = AssetInsightsService._get_usage_duration_days(db, asset.asset_id)

        if usage_duration_days >= 1460:
            usage_penalty = 10
        elif usage_duration_days >= 1095:
            usage_penalty = 10
        elif usage_duration_days >= 730:
            usage_penalty = 5
        elif usage_duration_days >= 365:
            usage_penalty = 5
        else:
            # No tracking history often means old stock/inventory not being rotated.
            # Apply a mild lifecycle penalty from purchase age to keep long-lived assets visible.
            if asset_age_years >= 4:
                usage_penalty = 10
            elif asset_age_years >= 3:
                usage_penalty = 5
            else:
                usage_penalty = 0

        repair_penalty = repair_count * 8
        performance_penalty = performance_issues_count * 5

        warranty_expiry = AssetInsightsService._get_warranty_expiry(db, asset.asset_id)
        warranty_expired = (warranty_expiry is None) or bool(warranty_expiry < date.today())
        warranty_penalty = 10 if warranty_expired else 0

        purchase_cost = float(asset.purchase_cost or 0.0)
        maintenance_cost = float(asset.maintenance_total_cost or 0.0)
        repair_cost = float(asset.repair_total_cost or 0.0)
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
                - performance_penalty
                - usage_penalty
                - warranty_penalty
                - spend_ratio_penalty,
            ),
        )
        classification = AssetInsightsService._classify_health(score)
        if classification == "Replace Immediately":
            hint = "Replace asset immediately."
        elif classification == "Critical":
            hint = "Urgent repair/replacement evaluation required."
        elif classification == "Warning":
            hint = "Inspect and maintain soon."
        else:
            hint = "Healthy for continued use and reallocation."

        return AssetHealthRead(
            asset_id=asset.asset_id,
            health_score=score,
            classification=classification,
            asset_age_years=round(asset_age_years, 2),
            usage_duration_days=usage_duration_days,
            repair_count=repair_count,
            performance_issues_count=performance_issues_count,
            warranty_expired=warranty_expired,
            age_penalty=age_penalty,
            repair_penalty=repair_penalty,
            performance_penalty=performance_penalty,
            warranty_penalty=warranty_penalty,
            usage_penalty=usage_penalty,
            recommendation_hint=hint,
        )

    @staticmethod
    def get_replacement_recommendation(db: Session, asset_id: str) -> AssetRecommendationRead:
        health = AssetInsightsService.get_asset_health(db, asset_id)
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
    def get_health_report(
        db: Session,
        *,
        branch: Optional[str] = None,
        critical_only: bool = False,
    ) -> AssetHealthReportRead:
        query = AssetInsightsService._base_asset_query(db)
        if branch:
            query = query.filter(Asset.branch == branch)

        items: list[AssetHealthReportItem] = []
        for asset in query.all():
            health = AssetInsightsService.get_asset_health(db, asset.asset_id)
            if critical_only and health.health_score > 39:
                continue
            recommendation = AssetInsightsService.get_replacement_recommendation(db, asset.asset_id)
            items.append(
                AssetHealthReportItem(
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    category=asset.category.category_name if asset.category else None,
                    sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                    branch=asset.branch,
                    status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
                    health_score=health.health_score,
                    classification=health.classification,
                    recommendation=recommendation.recommendation,
                    recommendation_reason=recommendation.reason,
                    purchase_cost=round(float(asset.purchase_cost or 0.0), 2),
                    maintenance_cost=round(float(asset.maintenance_total_cost or 0.0), 2),
                    repair_cost=round(float(asset.repair_total_cost or 0.0), 2),
                    reselling_value=round(float(asset.salvage_value or 0.0), 2),
                    usage_duration_days=health.usage_duration_days,
                    asset_age_years=health.asset_age_years,
                    repair_count=health.repair_count,
                    performance_issues_count=health.performance_issues_count,
                    warranty_expired=health.warranty_expired,
                )
            )

        items.sort(key=lambda item: (item.health_score, -item.repair_cost, -item.maintenance_cost))
        return AssetHealthReportRead(
            asset_count=len(items),
            healthy_assets=sum(1 for item in items if item.classification == "Healthy"),
            good_assets=sum(1 for item in items if item.classification == "Good"),
            warning_assets=sum(1 for item in items if item.classification == "Warning"),
            critical_assets=sum(1 for item in items if item.classification in {"Critical", "Replace Immediately"}),
            replacement_candidates=sum(1 for item in items if item.recommendation == "REPLACE"),
            items=items,
        )

    @staticmethod
    def get_health_classification(db: Session) -> dict[str, int]:
        report = AssetInsightsService.get_health_report(db)
        return {
            "Healthy": report.healthy_assets,
            "Good": report.good_assets,
            "Warning": report.warning_assets,
            "Critical": report.critical_assets,
            "ReplaceImmediately": report.replacement_candidates,
        }

    @staticmethod
    def get_utilization_summary(db: Session) -> list[UtilizationItem]:
        assets = AssetInsightsService._base_asset_query(db).all()
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
    def get_branch_analytics(db: Session, branch: Optional[str] = None) -> list[UtilizationItem]:
        items = AssetInsightsService.get_utilization_summary(db)
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
                category=asset.category.category_name if asset.category else None,
                sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                branch=asset.branch,
                status=asset.asset_status.value if asset.asset_status else "UNKNOWN",
                total_quantity=asset.total_quantity,
                used=asset.used,
                unused=asset.unused,
                low_stock=asset.unused <= (asset.low_stock_threshold or 0),
            )
            for asset in assets
        ]
