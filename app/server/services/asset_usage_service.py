"""Aggregate allocation, repair, transfer, and downtime metrics from tracking and assets."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.asset import Asset
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.tracking import MovementType, Tracking


class AssetUsageService:
    @staticmethod
    def _scope_organization(current_user: Employee) -> Optional[str]:
        if current_user.role == EmployeeRole.SUPER_ADMIN:
            return None
        return current_user.organization_id

    @staticmethod
    def _scope_employee(db: Session, current_user: Employee) -> Optional[str]:
        if current_user.role == EmployeeRole.SUPER_ADMIN:
            return None
        if current_user.role in (EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            return current_user.branch
        return None

    @staticmethod
    def get_asset_usage(db: Session, asset_id: str, current_user: Employee) -> dict[str, Any]:
        asset = db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category)).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        org_scope = AssetUsageService._scope_organization(current_user)
        if org_scope and asset.organization_id != org_scope:
            raise ResourceNotFoundError("Asset", asset_id)

        branch_scope = AssetUsageService._scope_employee(db, current_user)
        if branch_scope and (asset.branch or "") != (branch_scope or ""):
            raise ResourceNotFoundError("Asset", asset_id)

        rows_query = db.query(Tracking).filter(Tracking.asset_id == asset_id)
        if org_scope:
            rows_query = rows_query.filter(Tracking.organization_id == org_scope)
        rows = rows_query.order_by(Tracking.assigned_date.asc()).all()

        allocations = []
        repairs = []
        transfers = []
        now = datetime.now(timezone.utc)
        active_seconds = 0.0
        downtime_seconds = 0.0

        for tr in rows:
            entry = {
                "tracking_id": tr.tracking_id,
                "movement_type": tr.movement_type.value if tr.movement_type else None,
                "emp_id": tr.emp_id,
                "branch": tr.branch,
                "from_branch": tr.from_branch,
                "to_branch": tr.to_branch,
                "assigned_date": tr.assigned_date.isoformat() if tr.assigned_date else None,
                "returned_at": tr.returned_at.isoformat() if tr.returned_at else None,
                "allocation_type": tr.allocation_type.value if tr.allocation_type else None,
                "movement_reason": tr.movement_reason,
            }
            mt = tr.movement_type.value if tr.movement_type else ""
            if mt == MovementType.REPAIR.value:
                repairs.append(entry)
            elif mt == MovementType.TRANSFER.value:
                transfers.append(entry)
            else:
                allocations.append(entry)

            if tr.assigned_date:
                start = tr.assigned_date
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                end = tr.returned_at or now
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                delta = (end - start).total_seconds()
                if mt == MovementType.REPAIR.value:
                    downtime_seconds += max(delta, 0)
                elif mt in (MovementType.ALLOCATE.value, MovementType.ONBOARD.value, MovementType.TRANSFER.value):
                    active_seconds += max(delta, 0)

        idle_units = max(asset.unused or 0, 0)
        repair_cnt = asset.repair_count or 0
        allocation_count = len([r for r in rows if (r.movement_type and r.movement_type.value in (MovementType.ALLOCATE.value, MovementType.ONBOARD.value, MovementType.TRANSFER.value))])

        return {
            "asset_id": asset.asset_id,
            "name": asset.name,
            "branch": asset.branch,
            "category": asset.category.category_name if asset.category else None,
            "sub_category": asset.sub_category.sub_category_name if asset.sub_category else None,
            "metrics": {
                "usage_duration_hours": round(active_seconds / 3600.0, 2),
                "repair_count": repair_cnt,
                "downtime_hours": round(downtime_seconds / 3600.0, 2),
                "allocation_count": allocation_count,
                "idle_units": idle_units,
            },
            "allocation_history": allocations[-50:],
            "repair_history": repairs[-50:],
            "transfer_history": transfers[-50:],
        }

    @staticmethod
    def usage_report(db: Session, current_user: Employee, branch: Optional[str] = None) -> dict[str, Any]:
        org_scope = AssetUsageService._scope_organization(current_user)
        branch_scope = AssetUsageService._scope_employee(db, current_user)
        effective = branch or branch_scope
        q = db.query(Asset)
        if org_scope:
            q = q.filter(Asset.organization_id == org_scope)
        if effective:
            q = q.filter(Asset.branch == effective)
        assets = q.all()
        items = []
        for a in assets[:500]:
            tr_q = db.query(func.count(Tracking.tracking_id)).filter(Tracking.asset_id == a.asset_id)
            if org_scope:
                tr_q = tr_q.filter(Tracking.organization_id == org_scope)
            tr_count = tr_q.scalar() or 0
            items.append(
                {
                    "asset_id": a.asset_id,
                    "name": a.name,
                    "branch": a.branch,
                    "repair_count": a.repair_count or 0,
                    "downtime_hours": round((a.repair_total_cost or 0) / max(a.purchase_cost or 1, 1) * 10, 2),
                    "allocation_events": int(tr_count),
                    "unused": a.unused,
                    "used": a.used,
                }
            )
        return {"branch": effective, "count": len(items), "items": items}

    @staticmethod
    def usage_analytics(db: Session, current_user: Employee) -> dict[str, Any]:
        org_scope = AssetUsageService._scope_organization(current_user)
        branch_scope = AssetUsageService._scope_employee(db, current_user)
        q = db.query(Tracking)
        if org_scope:
            q = q.filter(Tracking.organization_id == org_scope)
        if branch_scope:
            q = q.filter(Tracking.branch == branch_scope)
        total_movements = q.count()
        by_type = {}
        for mt in MovementType:
            c = db.query(func.count(Tracking.tracking_id)).filter(Tracking.movement_type == mt)
            if org_scope:
                c = c.filter(Tracking.organization_id == org_scope)
            if branch_scope:
                c = c.filter(Tracking.branch == branch_scope)
            by_type[mt.value] = c.scalar() or 0
        assets = db.query(Asset)
        if org_scope:
            assets = assets.filter(Asset.organization_id == org_scope)
        if branch_scope:
            assets = assets.filter(Asset.branch == branch_scope)
        total_repairs = sum(a.repair_count or 0 for a in assets.all())
        return {
            "total_tracking_events": total_movements,
            "events_by_movement_type": by_type,
            "sum_repair_count_catalog": total_repairs,
        }
