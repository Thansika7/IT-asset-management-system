from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.server.database.tenant import apply_tenant_filter
from app.server.exceptions.base import ResourceNotFoundError
from app.server.models.api import EmployeeAssetHistoryItem, EmployeeAssetItem
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.category import Category
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.organization import Branch
from app.server.schema.tracking import AllocationType, MovementType, Tracking
from app.server.services.stock_service import StockService


class EmployeeAssetService:
    MOVEMENT_ALIAS = {
        MovementType.ALLOCATE.value: "ASSIGNED",
        MovementType.RETURN.value: "RETURNED",
        MovementType.TRANSFER.value: "TRANSFERRED",
    }

    @staticmethod
    def _normalize_movement(movement: Optional[MovementType]) -> Optional[str]:
        if not movement:
            return None
        value = movement.value if hasattr(movement, "value") else str(movement)
        return EmployeeAssetService.MOVEMENT_ALIAS.get(value, value)

    @staticmethod
    def _employee_exists(db: Session, current_user: Employee, employee_id: str) -> Employee:
        employee = (
            apply_tenant_filter(db.query(Employee), current_user, Employee)
            .filter(Employee.employee_id == employee_id)
            .first()
        )
        if not employee:
            raise ResourceNotFoundError("Employee", employee_id)
        return employee

    @staticmethod
    def get_employee_assets(
        db: Session,
        current_user: Employee,
        employee_id: str,
        search: Optional[str] = None,
        status: Optional[str] = None,
        branch: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        EmployeeAssetService._employee_exists(db, current_user, employee_id)

        query = (
            apply_tenant_filter(db.query(Tracking), current_user, Tracking, allow_cross_branch=True)
            .join(AssetInstance, Tracking.instance_id == AssetInstance.instance_id)
            .join(Asset, AssetInstance.asset_id == Asset.asset_id)
            .join(Category, Asset.category_id == Category.category_id, isouter=True)
            .join(Branch, AssetInstance.branch_id == Branch.branch_id, isouter=True)
            .filter(Tracking.emp_id == employee_id, Tracking.returned_at.is_(None), Tracking.instance_id.isnot(None))
        )

        if search:
            needle = f"%{search.strip()}%"
            query = query.filter(
                Tracking.instance_id.ilike(needle)
                | AssetInstance.serial_number.ilike(needle)
                | Asset.name.ilike(needle)
            )

        if status:
            query = query.filter(AssetInstance.status == status.strip().upper())

        if branch:
            branch_value = branch.strip()
            query = query.filter((AssetInstance.branch_id == branch_value) | (Branch.branch_name == branch_value))

        if category:
            category_value = category.strip()
            query = query.filter((Asset.category_id == category_value) | (Category.category_name == category_value))

        page = max(1, page)
        per_page = max(1, per_page)
        total = query.count()
        rows = query.order_by(Tracking.assigned_date.desc()).offset((page - 1) * per_page).limit(per_page).all()

        items: list[EmployeeAssetItem] = []
        for tracking in rows:
            instance = tracking.instance
            model = instance.model if instance else None
            items.append(
                EmployeeAssetItem(
                    tracking_id=tracking.tracking_id,
                    instance_id=instance.instance_id if instance else tracking.instance_id,
                    serial_number=instance.serial_number if instance else None,
                    asset_name=model.name if model else (tracking.asset_name or tracking.asset_id),
                    brand=model.brand if model else None,
                    model=model.model if model else None,
                    branch=instance.branch if instance else tracking.branch,
                    status=(instance.status.value if instance and instance.status else AssetStatus.ASSIGNED.value),
                    assigned_date=tracking.assigned_date,
                    category=model.category.category_name if model and model.category else tracking.category,
                    is_acknowledged=bool(tracking.is_acknowledged),
                )
            )

        return {
            "employee_id": employee_id,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    @staticmethod
    def get_employee_asset_history(
        db: Session,
        current_user: Employee,
        employee_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        EmployeeAssetService._employee_exists(db, current_user, employee_id)

        query = (
            apply_tenant_filter(db.query(Tracking), current_user, Tracking, allow_cross_branch=True)
            .join(AssetInstance, Tracking.instance_id == AssetInstance.instance_id)
            .join(Asset, AssetInstance.asset_id == Asset.asset_id)
            .join(Category, Asset.category_id == Category.category_id, isouter=True)
            .join(Branch, AssetInstance.branch_id == Branch.branch_id, isouter=True)
            .filter(Tracking.emp_id == employee_id, Tracking.instance_id.isnot(None))
        )

        page = max(1, page)
        per_page = max(1, per_page)
        total = query.count()
        rows = query.order_by(Tracking.assigned_date.desc()).offset((page - 1) * per_page).limit(per_page).all()

        items: list[EmployeeAssetHistoryItem] = []
        for tracking in rows:
            movement = tracking.movement_type.value if tracking.movement_type else None
            reason = (tracking.movement_reason or "").upper()
            repair_history = movement in {"REPAIR", "WARRANTY"} or "REPAIR" in reason
            replacement_history = movement == "REPLACE" or "REPLACE" in reason
            previous_assignment = bool(tracking.returned_at is not None or movement in {"RETURN", "TRANSFER", "OFFBOARD"})
            instance = tracking.instance
            model = instance.model if instance else None
            items.append(
                EmployeeAssetHistoryItem(
                    tracking_id=tracking.tracking_id,
                    instance_id=instance.instance_id if instance else tracking.instance_id,
                    serial_number=instance.serial_number if instance else None,
                    asset_name=model.name if model else (tracking.asset_name or tracking.asset_id),
                    brand=model.brand if model else None,
                    model=model.model if model else None,
                    branch=instance.branch if instance else tracking.branch,
                    category=model.category.category_name if model and model.category else tracking.category,
                    assigned_date=tracking.assigned_date,
                    returned_at=tracking.returned_at,
                    movement_type=EmployeeAssetService._normalize_movement(tracking.movement_type),
                    previous_assignment=previous_assignment,
                    repair_history=repair_history,
                    replacement_history=replacement_history,
                )
            )

        return {
            "employee_id": employee_id,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    @staticmethod
    def get_asset_owner(db: Session, current_user: Employee, instance_id: str) -> dict[str, Any]:
        instance = (
            apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance, allow_cross_branch=True)
            .outerjoin(AssetInstance.assigned_to)
            .filter(AssetInstance.instance_id == instance_id)
            .first()
        )
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)

        if current_user.role == EmployeeRole.EMPLOYEE and instance.assigned_to_id != current_user.employee_id:
            raise ResourceNotFoundError("AssetInstance", instance_id)

        active_tracking = (
            apply_tenant_filter(db.query(Tracking), current_user, Tracking, allow_cross_branch=True)
            .filter(
                Tracking.instance_id == instance_id,
                Tracking.returned_at.is_(None),
            )
            .order_by(Tracking.assigned_date.desc())
            .first()
        )

        owner = instance.assigned_to
        return {
            "instance_id": instance.instance_id,
            "asset_id": instance.asset_id,
            "asset_name": instance.model.name if instance.model else instance.asset_id,
            "status": instance.status.value if hasattr(instance.status, "value") else str(instance.status),
            "owner_id": owner.employee_id if owner else None,
            "owner_name": owner.name if owner else None,
            "owner_email": owner.email if owner else None,
            "assigned_at": instance.assigned_at,
            "tracking_id": active_tracking.tracking_id if active_tracking else None,
            "movement_type": EmployeeAssetService._normalize_movement(active_tracking.movement_type if active_tracking else None),
            "is_assigned": bool(instance.assigned_to_id),
        }

    @staticmethod
    def bulk_assign_assets(
        db: Session,
        current_user: Employee,
        employee_id: str,
        instance_ids: list[str],
        reason: str = "BULK_ASSIGNMENT",
        allocation_type: AllocationType = AllocationType.PERMANENT,
    ) -> dict[str, Any]:
        EmployeeAssetService._employee_exists(db, current_user, employee_id)

        unique_instance_ids = list(dict.fromkeys(instance_ids))
        success: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []

        for instance_id in unique_instance_ids:
            try:
                with db.begin_nested():
                    instance = (
                        apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance)
                        .filter(AssetInstance.instance_id == instance_id)
                        .with_for_update()
                        .first()
                    )
                    if not instance:
                        raise ResourceNotFoundError("AssetInstance", instance_id)
                    if instance.assigned_to_id:
                        raise ValueError("Asset is already assigned")
                    if instance.status != AssetStatus.AVAILABLE:
                        raise ValueError("Only AVAILABLE assets can be assigned")

                    tracking = StockService.allocate_asset(
                        db,
                        instance.asset_id,
                        employee_id,
                        allocation_type,
                        current_user,
                        reason,
                        instance_id=instance.instance_id,
                    )
                    success.append(
                        {
                            "instance_id": instance.instance_id,
                            "asset_id": instance.asset_id,
                            "tracking_id": tracking.tracking_id,
                        }
                    )
            except Exception as exc:
                failed.append({"instance_id": instance_id, "reason": str(exc)})

        db.commit()
        return {
            "employee_id": employee_id,
            "assigned_count": len(success),
            "failed_count": len(failed),
            "assigned_items": success,
            "failed_items": failed,
        }

    @staticmethod
    def get_ownership_analytics(
        db: Session,
        current_user: Employee,
        employee_id: str,
        overdue_days: int = 30,
    ) -> dict[str, Any]:
        EmployeeAssetService._employee_exists(db, current_user, employee_id)

        active_tracking_query = (
            apply_tenant_filter(db.query(Tracking), current_user, Tracking, allow_cross_branch=True)
            .filter(
                Tracking.emp_id == employee_id,
                Tracking.instance_id.isnot(None),
                Tracking.returned_at.is_(None),
            )
        )

        total_assets = (
            apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance, allow_cross_branch=True)
            .filter(AssetInstance.assigned_to_id == employee_id)
            .count()
        )

        unreturned_assets = active_tracking_query.count()
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, overdue_days))
        overdue_assets = active_tracking_query.filter(Tracking.assigned_date < cutoff).count()

        by_status_rows = (
            apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance, allow_cross_branch=True)
            .filter(AssetInstance.assigned_to_id == employee_id)
            .all()
        )

        by_status: dict[str, int] = {}
        for row in by_status_rows:
            key = row.status.value if hasattr(row.status, "value") else str(row.status)
            by_status[key] = by_status.get(key, 0) + 1

        return {
            "employee_id": employee_id,
            "total_assets": total_assets,
            "unreturned_assets": unreturned_assets,
            "overdue_assets": overdue_assets,
            "overdue_days_threshold": max(1, overdue_days),
            "assets_by_status": by_status,
        }
