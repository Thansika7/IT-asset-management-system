from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.schema.asset import Asset
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.tracking import Tracking, MovementType

router = APIRouter(prefix="/assets", tags=["asset-usage"])


def _usage_for_asset(db: Session, asset_id: str) -> Dict[str, Any]:
    asset = db.query(Asset).filter_by(asset_id=asset_id).first()
    if not asset:
        return {}

    records = db.query(Tracking).filter_by(asset_id=asset_id).all()

    allocation_count = sum(1 for r in records if r.movement_type == MovementType.ALLOCATE)
    repair_count = sum(1 for r in records if r.movement_type == MovementType.REPAIR)
    transfer_count = sum(1 for r in records if r.movement_type == MovementType.TRANSFER)

    # usage duration in days (allocated, not yet returned)
    active = [r for r in records if r.movement_type == MovementType.ALLOCATE and r.returned_at is None]
    now = datetime.now(timezone.utc)

    usage_duration_days = 0
    for r in active:
        if r.assigned_date:
            assigned = r.assigned_date
            if assigned.tzinfo is None:
                assigned = assigned.replace(tzinfo=timezone.utc)
            usage_duration_days += (now - assigned).days

    # idle: total_quantity unused * days since purchase
    idle_days = 0
    if asset.purchased_date and asset.unused > 0:
        purchased = datetime.combine(asset.purchased_date, datetime.min.time(), tzinfo=timezone.utc)
        idle_days = (now - purchased).days * asset.unused

    # downtime: time in repair
    downtime_days = 0
    for r in records:
        if r.movement_type == MovementType.REPAIR:
            start = r.assigned_date
            end = r.returned_at or now
            if start:
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                downtime_days += (end - start).days

    return {
        "asset_id": asset.asset_id,
        "asset_name": asset.name,
        "brand": asset.brand,
        "branch": asset.branch,
        "total_quantity": asset.total_quantity,
        "used": asset.used,
        "unused": asset.unused,
        "allocation_count": allocation_count,
        "repair_count": repair_count,
        "transfer_count": transfer_count,
        "usage_duration_days": usage_duration_days,
        "idle_time_unit_days": idle_days,
        "downtime_days": downtime_days,
        "allocation_history": [
            {
                "tracking_id": r.tracking_id,
                "emp_id": r.emp_id,
                "movement_type": r.movement_type.value,
                "assigned_date": r.assigned_date.isoformat() if r.assigned_date else None,
                "returned_at": r.returned_at.isoformat() if r.returned_at else None,
                "reason": r.movement_reason,
                "branch": r.branch,
            }
            for r in sorted(records, key=lambda x: x.assigned_date or datetime.min, reverse=True)
        ],
    }


@router.get("/{asset_id}/usage")
def get_asset_usage(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR)
    ),
):
    return _usage_for_asset(db, asset_id)


@router.get("/usage/report")
def usage_report(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)
    ),
):
    """Summary usage report for all assets visible to this user."""
    query = db.query(Asset)
    if current_user.role == EmployeeRole.MANAGER and current_user.branch:
        query = query.filter(Asset.branch == current_user.branch)

    assets = query.all()
    result = []
    for a in assets:
        allocation_count = (
            db.query(func.count(Tracking.tracking_id))
            .filter(Tracking.asset_id == a.asset_id, Tracking.movement_type == MovementType.ALLOCATE)
            .scalar()
        )
        repair_count_trk = (
            db.query(func.count(Tracking.tracking_id))
            .filter(Tracking.asset_id == a.asset_id, Tracking.movement_type == MovementType.REPAIR)
            .scalar()
        )
        result.append({
            "asset_id": a.asset_id,
            "asset_name": a.name,
            "branch": a.branch,
            "brand": a.brand,
            "total_quantity": a.total_quantity,
            "used": a.used,
            "unused": a.unused,
            "allocation_count": allocation_count,
            "repair_count": repair_count_trk,
            "asset_status": a.asset_status.value,
        })

    return result


@router.get("/usage/analytics")
def usage_analytics(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)
    ),
):
    """Aggregate analytics across all assets."""
    total_assets = db.query(func.count(Asset.asset_id)).scalar()
    total_allocated = db.query(func.sum(Asset.used)).scalar() or 0
    total_unused = db.query(func.sum(Asset.unused)).scalar() or 0
    total_repairs = (
        db.query(func.count(Tracking.tracking_id))
        .filter(Tracking.movement_type == MovementType.REPAIR)
        .scalar()
    )
    total_transfers = (
        db.query(func.count(Tracking.tracking_id))
        .filter(Tracking.movement_type == MovementType.TRANSFER)
        .scalar()
    )
    total_allocations = (
        db.query(func.count(Tracking.tracking_id))
        .filter(Tracking.movement_type == MovementType.ALLOCATE)
        .scalar()
    )

    # Most allocated assets
    top_allocated = (
        db.query(Asset.asset_id, Asset.name, Asset.brand, Asset.branch, Asset.used)
        .order_by(Asset.used.desc())
        .limit(5)
        .all()
    )

    # Most repaired
    repair_counts = (
        db.query(Tracking.asset_id, func.count(Tracking.tracking_id).label("cnt"))
        .filter(Tracking.movement_type == MovementType.REPAIR)
        .group_by(Tracking.asset_id)
        .order_by(func.count(Tracking.tracking_id).desc())
        .limit(5)
        .all()
    )
    top_repaired = []
    for r in repair_counts:
        a = db.query(Asset).filter_by(asset_id=r.asset_id).first()
        top_repaired.append({
            "asset_id": r.asset_id,
            "asset_name": a.name if a else None,
            "repair_count": r.cnt,
        })

    return {
        "total_assets": total_assets,
        "total_allocated_units": total_allocated,
        "total_unused_units": total_unused,
        "total_repairs": total_repairs,
        "total_transfers": total_transfers,
        "total_allocations": total_allocations,
        "utilization_rate_pct": round(total_allocated / (total_allocated + total_unused) * 100, 1) if (total_allocated + total_unused) > 0 else 0,
        "top_allocated_assets": [
            {"asset_id": r.asset_id, "name": r.name, "brand": r.brand, "branch": r.branch, "used": r.used}
            for r in top_allocated
        ],
        "top_repaired_assets": top_repaired,
    }
