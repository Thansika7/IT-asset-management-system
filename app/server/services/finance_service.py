from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.server.database.tenant import apply_tenant_filter
from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.asset import Asset, AssetInstance
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.tracking import AssetLifecycle, LifecycleEvent


class FinanceService:
    @staticmethod
    def calculate_depreciation(asset: Asset) -> dict[str, float]:
        purchase_cost = float(asset.purchase_cost or 0.0)
        salvage_value = float(asset.salvage_value or 0.0)
        useful_life_years = int(asset.useful_life_years or 1)
        useful_life_years = max(useful_life_years, 1)

        annual = max((purchase_cost - salvage_value) / useful_life_years, 0.0)

        age_years = 0.0
        if asset.purchased_date:
            age_years = max((date.today() - asset.purchased_date).days / 365.0, 0.0)

        accumulated = min(annual * age_years, max(purchase_cost - salvage_value, 0.0))
        book_value = max(purchase_cost - accumulated, salvage_value if purchase_cost > 0 else 0.0)
        return {
            "annual_depreciation": round(annual, 2),
            "accumulated_depreciation": round(accumulated, 2),
            "book_value": round(book_value, 2),
            "asset_age_years": round(age_years, 2),
        }

    @staticmethod
    def _asset_tco(asset: Asset) -> float:
        return round(
            float(asset.purchase_cost or 0.0)
            + float(asset.repair_total_cost or 0.0)
            + float(asset.maintenance_total_cost or 0.0),
            2,
        )

    @staticmethod
    def _instance_tco(instance: AssetInstance) -> float:
        return round(
            float(instance.purchase_cost or 0.0)
            + float(instance.repair_cost_total or 0.0)
            + float(instance.maintenance_cost_total or 0.0),
            2,
        )

    @staticmethod
    def _lifecycle_cost_trend(db: Session, asset_id: str, current_user: Employee) -> list[dict[str, Any]]:
        events = (
            apply_tenant_filter(db.query(AssetLifecycle), current_user, AssetLifecycle)
            .filter(AssetLifecycle.asset_id == asset_id)
            .order_by(AssetLifecycle.timestamp.asc())
            .all()
        )

        monthly: dict[str, dict[str, float]] = defaultdict(lambda: {"repair_cost": 0.0, "maintenance_cost": 0.0})
        for event in events:
            meta = event.event_metadata or {}
            stamp = event.timestamp
            month_key = f"{stamp.year:04d}-{stamp.month:02d}" if stamp else "unknown"
            monthly[month_key]["repair_cost"] += float(meta.get("repair_cost", 0.0) or 0.0)
            monthly[month_key]["maintenance_cost"] += float(meta.get("maintenance_cost", 0.0) or 0.0)

        return [
            {
                "month": month,
                "repair_cost": round(vals["repair_cost"], 2),
                "maintenance_cost": round(vals["maintenance_cost"], 2),
                "total_cost": round(vals["repair_cost"] + vals["maintenance_cost"], 2),
            }
            for month, vals in sorted(monthly.items())
        ]

    @staticmethod
    def list_assets_finance(
        db: Session,
        current_user: Employee,
        branch_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        query = apply_tenant_filter(db.query(Asset), current_user, Asset)

        if current_user.role in {EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE} and current_user.branch_id:
            query = query.filter(Asset.branch_id == current_user.branch_id)
        elif branch_id:
            query = query.filter(Asset.branch_id == branch_id)

        page = max(1, page)
        per_page = max(1, per_page)
        total = query.count()
        rows = query.order_by(Asset.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        items: list[dict[str, Any]] = []
        for asset in rows:
            depreciation = FinanceService.calculate_depreciation(asset)
            lifecycle_stats = (
                apply_tenant_filter(db.query(AssetLifecycle), current_user, AssetLifecycle)
                .filter(
                    AssetLifecycle.asset_id == asset.asset_id,
                    AssetLifecycle.event_type == LifecycleEvent.REPAIR_STARTED,
                )
                .count()
            )
            items.append(
                {
                    "asset_id": asset.asset_id,
                    "asset_name": asset.name,
                    "branch_id": asset.branch_id,
                    "purchase_cost": float(asset.purchase_cost or 0.0),
                    "repair_cost_total": float(asset.repair_total_cost or 0.0),
                    "maintenance_cost_total": float(asset.maintenance_total_cost or 0.0),
                    "salvage_value": float(asset.salvage_value or 0.0),
                    "useful_life_years": int(asset.useful_life_years or 1),
                    "depreciation": depreciation,
                    "tco": FinanceService._asset_tco(asset),
                    "repair_frequency": lifecycle_stats,
                    "cost_trend": FinanceService._lifecycle_cost_trend(db, asset.asset_id, current_user),
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    @staticmethod
    def list_instance_finance(
        db: Session,
        current_user: Employee,
        branch_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        query = apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance)

        if current_user.role in {EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE} and current_user.branch_id:
            query = query.filter(AssetInstance.branch_id == current_user.branch_id)
        elif branch_id:
            query = query.filter(AssetInstance.branch_id == branch_id)

        page = max(1, page)
        per_page = max(1, per_page)
        total = query.count()
        rows = query.order_by(AssetInstance.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        items: list[dict[str, Any]] = []
        for inst in rows:
            model = inst.model
            depreciation = FinanceService.calculate_depreciation(model) if model else {
                "annual_depreciation": 0.0,
                "accumulated_depreciation": 0.0,
                "book_value": 0.0,
                "asset_age_years": 0.0,
            }
            repair_frequency = (
                apply_tenant_filter(db.query(AssetLifecycle), current_user, AssetLifecycle)
                .filter(
                    AssetLifecycle.instance_id == inst.instance_id,
                    AssetLifecycle.event_type == LifecycleEvent.REPAIR_STARTED,
                )
                .count()
            )
            items.append(
                {
                    "instance_id": inst.instance_id,
                    "asset_id": inst.asset_id,
                    "asset_name": model.name if model else inst.asset_id,
                    "branch_id": inst.branch_id,
                    "purchase_cost": float(inst.purchase_cost or 0.0),
                    "repair_cost_total": float(inst.repair_cost_total or 0.0),
                    "maintenance_cost_total": float(inst.maintenance_cost_total or 0.0),
                    "status": inst.status.value if hasattr(inst.status, "value") else str(inst.status),
                    "depreciation": depreciation,
                    "tco": FinanceService._instance_tco(inst),
                    "repair_frequency": repair_frequency,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    @staticmethod
    def add_instance_maintenance_cost(
        db: Session,
        current_user: Employee,
        instance_id: str,
        amount: float,
        reason: str = "MAINTENANCE_COST_UPDATE",
    ) -> dict[str, Any]:
        if amount < 0:
            raise ValueError("maintenance_cost must be non-negative")

        instance = (
            apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)

        old_val = float(instance.maintenance_cost_total or 0.0)
        instance.maintenance_cost_total = old_val + amount

        if instance.model:
            instance.model.maintenance_total_cost = float(instance.model.maintenance_total_cost or 0.0) + amount

        from app.server.services.audit_service import AuditService
        from app.server.services.lifecycle_service import LifecycleService

        AuditService.log_change(
            db,
            table_name="asset_instances",
            record_id=instance.instance_id,
            action="UPDATE",
            user=current_user,
            old_values={"maintenance_cost_total": old_val},
            new_values={"maintenance_cost_total": float(instance.maintenance_cost_total or 0.0)},
            reason=reason,
        )

        LifecycleService.log_event(
            db,
            instance_id=instance.instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.SERVICED,
            performed_by=current_user,
            old_status=instance.status.value if hasattr(instance.status, "value") else str(instance.status),
            new_status=instance.status.value if hasattr(instance.status, "value") else str(instance.status),
            notes=reason,
            organization_id=instance.organization_id,
            metadata={"maintenance_cost": amount},
        )

        return {
            "instance_id": instance.instance_id,
            "maintenance_cost_total": float(instance.maintenance_cost_total or 0.0),
        }
