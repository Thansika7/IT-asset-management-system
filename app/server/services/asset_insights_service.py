from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.server.exceptions.base import ResourceNotFoundError
from app.server.models.asset_insights import (
    AssetFinanceRead,
    AssetFinanceReportRead,
    AssetHealthRead,
    AssetListItem,
    AssetRecommendationRead,
    UtilizationItem,
)
from app.server.schema.asset import Asset
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.category import Category, SubCategory


class AssetInsightsService:
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
            salvage_value=round(salvage_value, 2),
            maintenance_cost=round(maintenance_cost, 2),
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
    def get_finance_report(db: Session, branch: Optional[str] = None) -> AssetFinanceReportRead:
        query = AssetInsightsService._base_asset_query(db)
        if branch:
            query = query.filter(Asset.branch == branch)
        assets = query.all()

        finance_rows = [AssetInsightsService.get_asset_finance(db, asset.asset_id) for asset in assets]
        return AssetFinanceReportRead(
            branch=branch,
            asset_count=len(finance_rows),
            total_purchase_cost=round(sum(row.purchase_cost for row in finance_rows), 2),
            total_maintenance_cost=round(sum(row.maintenance_cost for row in finance_rows), 2),
            total_repair_cost=round(sum(row.repair_cost for row in finance_rows), 2),
            total_license_cost=round(sum(row.sub_license_cost for row in finance_rows), 2),
            total_depreciation=round(sum(row.accumulated_depreciation for row in finance_rows), 2),
            total_cost_of_ownership=round(sum(row.total_cost_of_ownership for row in finance_rows), 2),
        )

    @staticmethod
    def get_asset_health(db: Session, asset_id: str) -> AssetHealthRead:
        asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        asset_age_years = 0
        if asset.purchased_date:
            asset_age_years = max((date.today() - asset.purchased_date).days / 365, 0)

        age_penalty = min(int(asset_age_years * 5), 30)
        repair_penalty = min(int((asset.repair_count or 0) * 10), 30)
        performance_penalty = min(int((asset.performance_issues_count or 0) * 8), 24)
        usage_penalty = 0
        if asset.total_quantity > 0:
            usage_rate = asset.used / asset.total_quantity
            if usage_rate >= 0.9:
                usage_penalty = 10
            elif usage_rate >= 0.75:
                usage_penalty = 5

        warranty_penalty = 0
        warranty_expiry = AssetInsightsService._get_warranty_expiry(db, asset.asset_id)
        if warranty_expiry and warranty_expiry < date.today():
            warranty_penalty = 15

        score = max(0, min(100, 100 - age_penalty - repair_penalty - performance_penalty - usage_penalty - warranty_penalty))
        if score < 40:
            hint = "Replacement should be evaluated soon."
        elif score < 65:
            hint = "Watch this asset closely for service or swap."
        else:
            hint = "Healthy enough for continued usage."

        return AssetHealthRead(
            asset_id=asset.asset_id,
            health_score=score,
            age_penalty=age_penalty,
            repair_penalty=repair_penalty,
            performance_penalty=performance_penalty,
            warranty_penalty=warranty_penalty,
            usage_penalty=usage_penalty,
            recommendation_hint=hint,
        )

    @staticmethod
    def get_replacement_recommendation(db: Session, asset_id: str) -> AssetRecommendationRead:
        asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        repair_cost = float(asset.repair_total_cost or 0.0)
        salvage_value = float(asset.salvage_value or 0.0)
        repair_count = int(asset.repair_count or 0)

        if repair_cost > salvage_value and salvage_value > 0:
            return AssetRecommendationRead(
                asset_id=asset_id,
                recommendation="REPLACE",
                reason="Repair cost has exceeded salvage value.",
            )
        if repair_count >= 3:
            return AssetRecommendationRead(
                asset_id=asset_id,
                recommendation="REPLACE",
                reason="Repair count crossed the threshold.",
            )
        return AssetRecommendationRead(
            asset_id=asset_id,
            recommendation="RETAIN",
            reason="Repair indicators are still within acceptable range.",
        )

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
