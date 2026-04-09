from __future__ import annotations

from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.server.database.tenant import apply_tenant_filter
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.cmdb import CIRelationship, ConfigurationItem
from app.server.schema.employee import Employee
from app.server.schema.request import Request, RequestStatus
from app.server.services.finance_service import FinanceService
from app.server.services.health_service import HealthService


class AnalyticsService:
    """System-wide analytics assembled from existing domain tables."""

    OPEN_REQUEST_STATUSES = {
        RequestStatus.SUBMITTED,
        RequestStatus.HR_VALIDATED,
        RequestStatus.TRIAGED,
        RequestStatus.PENDING,
        RequestStatus.PENDING_SUPPORT,
        RequestStatus.PENDING_SUPPORT_TRIAGE,
        RequestStatus.PENDING_MANAGER,
        RequestStatus.APPROVED_FOR_SUPPORT,
        RequestStatus.READY,
        RequestStatus.WIP_SERVICE,
        RequestStatus.IN_REPAIR,
        RequestStatus.AWAITING_TRANSFER,
    }

    APPROVED_REQUEST_STATUSES = {
        RequestStatus.APPROVED,
        RequestStatus.APPROVED_FOR_SUPPORT,
        RequestStatus.ASSIGNED,
        RequestStatus.COMPLETED,
        RequestStatus.CLOSED,
    }

    REJECTED_REQUEST_STATUSES = {
        RequestStatus.REJECTED,
        RequestStatus.HR_REJECTED,
        RequestStatus.CANCELLED,
    }

    @staticmethod
    def get_asset_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        total_assets = apply_tenant_filter(db.query(func.count(Asset.asset_id)), current_user, Asset).scalar() or 0
        total_instances = apply_tenant_filter(
            db.query(func.count(AssetInstance.instance_id)), current_user, AssetInstance
        ).scalar() or 0

        row = apply_tenant_filter(
            db.query(
                func.sum(case((AssetInstance.status == AssetStatus.ASSIGNED, 1), else_=0)).label("assigned_assets"),
                func.sum(case((AssetInstance.status == AssetStatus.AVAILABLE, 1), else_=0)).label("available_assets"),
                func.sum(case((AssetInstance.status == AssetStatus.RETIRED, 1), else_=0)).label("retired_assets"),
            ),
            current_user,
            AssetInstance,
        ).one()

        return {
            "total_assets": int(total_assets),
            "total_instances": int(total_instances),
            "assigned_assets": int(row.assigned_assets or 0),
            "available_assets": int(row.available_assets or 0),
            "retired_assets": int(row.retired_assets or 0),
        }

    @staticmethod
    def get_health_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        summary = HealthService.get_health_summary(db, current_user)
        assets_in_repair = apply_tenant_filter(
            db.query(func.count(AssetInstance.instance_id)).filter(AssetInstance.status == AssetStatus.IN_REPAIR),
            current_user,
            AssetInstance,
        ).scalar() or 0

        distribution = summary.get("distribution", {})
        return {
            "average_health_score": summary.get("average_score"),
            "critical_assets_count": int(distribution.get("CRITICAL", 0) or 0),
            "assets_needing_replacement": int(distribution.get("REPLACE", 0) or 0),
            "assets_in_repair": int(assets_in_repair),
        }

    @staticmethod
    def get_finance_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        row = apply_tenant_filter(
            db.query(
                func.coalesce(func.sum(Asset.purchase_cost), 0.0).label("total_asset_cost"),
                func.coalesce(func.sum(Asset.repair_total_cost), 0.0).label("total_repair_cost"),
                func.coalesce(func.sum(Asset.maintenance_total_cost), 0.0).label("total_maintenance_cost"),
            ),
            current_user,
            Asset,
        ).one()

        purchase_cost = func.coalesce(Asset.purchase_cost, 0.0)
        salvage_value = func.coalesce(Asset.salvage_value, 0.0)
        useful_life_years = func.greatest(func.coalesce(Asset.useful_life_years, 1), 1)
        annual_depreciation = func.greatest((purchase_cost - salvage_value) / useful_life_years, 0.0)
        asset_age_years = case(
            (Asset.purchased_date.is_(None), 0.0),
            else_=func.greatest((func.current_date() - Asset.purchased_date) / 365.0, 0.0),
        )
        cap = func.greatest(purchase_cost - salvage_value, 0.0)
        accumulated_expr = func.least(annual_depreciation * asset_age_years, cap)

        try:
            total_depreciation = (
                apply_tenant_filter(
                    db.query(func.coalesce(func.sum(accumulated_expr), 0.0)),
                    current_user,
                    Asset,
                ).scalar()
                or 0.0
            )
            total_depreciation = round(float(total_depreciation), 2)
        except Exception:
            # Fallback keeps Module 11 depreciation logic consistent across SQL dialects.
            assets = apply_tenant_filter(db.query(Asset), current_user, Asset).all()
            total_depreciation = round(
                sum(FinanceService.calculate_depreciation(asset).get("accumulated_depreciation", 0.0) for asset in assets),
                2,
            )

        return {
            "total_asset_cost": round(float(row.total_asset_cost or 0.0), 2),
            "total_repair_cost": round(float(row.total_repair_cost or 0.0), 2),
            "total_maintenance_cost": round(float(row.total_maintenance_cost or 0.0), 2),
            "total_depreciation": total_depreciation,
        }

    @staticmethod
    def get_request_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        row = apply_tenant_filter(
            db.query(
                func.count(Request.request_id).label("total_requests"),
                func.sum(
                    case(
                        (Request.status.in_(tuple(AnalyticsService.OPEN_REQUEST_STATUSES)), 1),
                        else_=0,
                    )
                ).label("open_requests"),
                func.sum(
                    case(
                        (Request.status.in_(tuple(AnalyticsService.APPROVED_REQUEST_STATUSES)), 1),
                        else_=0,
                    )
                ).label("approved_requests"),
                func.sum(
                    case(
                        (Request.status.in_(tuple(AnalyticsService.REJECTED_REQUEST_STATUSES)), 1),
                        else_=0,
                    )
                ).label("rejected_requests"),
                func.sum(case((Request.sla_breached.is_(True), 1), else_=0)).label("sla_breached_requests"),
            ),
            current_user,
            Request,
        ).one()

        return {
            "total_requests": int(row.total_requests or 0),
            "open_requests": int(row.open_requests or 0),
            "approved_requests": int(row.approved_requests or 0),
            "rejected_requests": int(row.rejected_requests or 0),
            "sla_breached_requests": int(row.sla_breached_requests or 0),
        }

    @staticmethod
    def get_inventory_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        low_stock_assets = apply_tenant_filter(
            db.query(func.count(Asset.asset_id)).filter(Asset.unused <= Asset.low_stock_threshold),
            current_user,
            Asset,
        ).scalar() or 0

        row = apply_tenant_filter(
            db.query(
                func.sum(case((AssetInstance.status == AssetStatus.AVAILABLE, 1), else_=0)).label("available_stock"),
                func.sum(case((AssetInstance.status == AssetStatus.ASSIGNED, 1), else_=0)).label("assigned_stock"),
            ),
            current_user,
            AssetInstance,
        ).one()

        return {
            "low_stock_assets": int(low_stock_assets),
            "available_stock": int(row.available_stock or 0),
            "assigned_stock": int(row.assigned_stock or 0),
        }

    @staticmethod
    def get_cmdb_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        total_ci = apply_tenant_filter(
            db.query(func.count(ConfigurationItem.ci_id)), current_user, ConfigurationItem
        ).scalar() or 0

        services_count = apply_tenant_filter(
            db.query(func.count(ConfigurationItem.ci_id)).filter(func.upper(ConfigurationItem.ci_type) == "SERVICE"),
            current_user,
            ConfigurationItem,
        ).scalar() or 0

        rel_row = apply_tenant_filter(
            db.query(
                func.count(CIRelationship.relationship_id).label("total_relationships"),
                func.sum(
                    case((func.upper(CIRelationship.relationship_type) == "DEPENDS_ON", 1), else_=0)
                ).label("dependency_count"),
            ),
            current_user,
            CIRelationship,
        ).one()

        return {
            "total_ci": int(total_ci),
            "total_relationships": int(rel_row.total_relationships or 0),
            "services_count": int(services_count or 0),
            "dependency_count": int(rel_row.dependency_count or 0),
        }

    @staticmethod
    def get_dashboard(db: Session, current_user: Employee) -> dict[str, Any]:
        return {
            "assets": AnalyticsService.get_asset_analytics(db, current_user),
            "health": AnalyticsService.get_health_analytics(db, current_user),
            "finance": AnalyticsService.get_finance_analytics(db, current_user),
            "requests": AnalyticsService.get_request_analytics(db, current_user),
            "inventory": AnalyticsService.get_inventory_analytics(db, current_user),
            "cmdb": AnalyticsService.get_cmdb_analytics(db, current_user),
        }
