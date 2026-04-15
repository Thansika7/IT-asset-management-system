from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.server.database.tenant import apply_tenant_filter
from app.server.models.software import (
    SoftwareAssignPayload,
    SoftwareAssignmentHistoryItem,
    SoftwareAssignmentResponse,
    SoftwareHardwareOption,
    SoftwareRemovePayload,
    SoftwareRemovalResponse,
    SoftwareUsageItem,
)
from app.server.schema.asset import Asset, AssetInstance, AssetStatus, AssetUsageType
from app.server.schema.category import Category, SubCategory
from app.server.schema.employee import Employee
from app.server.schema.request import Request, RequestStatus, RequestType
from app.server.schema.tracking import LifecycleEvent, MovementType, Tracking, AllocationType
from app.server.services.audit_service import AuditService
from app.server.services.lifecycle_service import LifecycleService


class SoftwareService:
    ALLOWED_HARDWARE_SUBCATEGORIES = {"laptop", "desktop"}

    @staticmethod
    def _ensure_employee(db: Session, employee_id: str, current_user: Employee) -> Employee:
        employee = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(
            Employee.employee_id == employee_id
        ).first()
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        return employee

    @staticmethod
    def _ensure_software_asset(db: Session, software_asset_id: str, current_user: Employee) -> Asset:
        software_asset = (
            apply_tenant_filter(db.query(Asset), current_user, Asset)
            .options(joinedload(Asset.category))
            .filter(Asset.asset_id == software_asset_id)
            .with_for_update()
            .first()
        )
        if not software_asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Software asset not found")

        category_name = (software_asset.category.category_name if software_asset.category else "").strip().lower()
        if category_name != "software":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected asset is not a software category asset")

        return software_asset

    @staticmethod
    def _ensure_hardware_instance(
        db: Session,
        instance_id: str,
        employee_id: str,
        current_user: Employee,
    ) -> AssetInstance:
        instance = (
            apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance)
            .options(
                joinedload(AssetInstance.model).joinedload(Asset.category),
                joinedload(AssetInstance.model).joinedload(Asset.sub_category),
            )
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hardware instance not found")

        category_name = (instance.model.category.category_name if instance.model and instance.model.category else "").strip().lower()
        sub_category_name = (
            instance.model.sub_category.sub_category_name
            if instance.model and instance.model.sub_category
            else ""
        ).strip().lower()

        if category_name != "hardware":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instance must belong to Hardware category")
        if sub_category_name not in SoftwareService.ALLOWED_HARDWARE_SUBCATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only Laptop or Desktop instances are allowed",
            )

        if instance.model and instance.model.asset_usage_type == AssetUsageType.SHARED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shared hardware cannot be used for software assignment")

        status_value = instance.status.value if hasattr(instance.status, "value") else str(instance.status)
        if status_value not in {AssetStatus.AVAILABLE.value, AssetStatus.ASSIGNED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hardware must be AVAILABLE or ASSIGNED")
        if status_value == AssetStatus.ASSIGNED.value and instance.assigned_to_id != employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assigned hardware can only be used when assigned to the same employee",
            )

        return instance

    @staticmethod
    def list_hardware_options(
        db: Session,
        employee_id: str,
        current_user: Employee,
    ) -> list[SoftwareHardwareOption]:
        employee = SoftwareService._ensure_employee(db, employee_id, current_user)

        instances = (
            apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance)
            .join(AssetInstance.model)
            .join(Asset.category)
            .outerjoin(Asset.sub_category)
            .options(
                joinedload(AssetInstance.model).joinedload(Asset.category),
                joinedload(AssetInstance.model).joinedload(Asset.sub_category),
            )
            .filter(func.lower(Category.category_name) == "hardware")
            .filter(func.lower(SubCategory.sub_category_name).in_(SoftwareService.ALLOWED_HARDWARE_SUBCATEGORIES))
            .filter(Asset.asset_usage_type != AssetUsageType.SHARED)
            .filter(
                (AssetInstance.status == AssetStatus.AVAILABLE)
                | ((AssetInstance.status == AssetStatus.ASSIGNED) & (AssetInstance.assigned_to_id == employee.employee_id))
            )
            .order_by(AssetInstance.created_at.desc())
            .all()
        )

        return [
            SoftwareHardwareOption(
                instance_id=instance.instance_id,
                asset_id=instance.asset_id,
                asset_name=instance.model.name if instance.model else instance.asset_id,
                sub_category=(instance.model.sub_category.sub_category_name if instance.model and instance.model.sub_category else None),
                status=instance.status.value if hasattr(instance.status, "value") else str(instance.status),
                assigned_to_id=instance.assigned_to_id,
            )
            for instance in instances
        ]

    @staticmethod
    def assign_software(
        db: Session,
        payload: SoftwareAssignPayload,
        current_user: Employee,
    ) -> SoftwareAssignmentResponse:
        with db.begin():
            employee = SoftwareService._ensure_employee(db, payload.employee_id, current_user)
            software_asset = SoftwareService._ensure_software_asset(db, payload.software_asset_id, current_user)
            hardware_instance = SoftwareService._ensure_hardware_instance(db, payload.instance_id, payload.employee_id, current_user)

            req = apply_tenant_filter(db.query(Request), current_user, Request).filter(
                Request.request_id == payload.request_id
            ).with_for_update().first()
            if not req:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
            if req.emp_id != employee.employee_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request employee and payload employee must match")
            if req.status not in [RequestStatus.APPROVED, RequestStatus.APPROVED_FOR_SUPPORT, RequestStatus.READY]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved requests can be fulfilled")
            if req.asset_id and req.asset_id != software_asset.asset_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Request is linked to a different software asset",
                )
            if (req.asset_category or "").strip().lower() != "software":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Software assignment is allowed only for software requests",
                )

            duplicate = (
                apply_tenant_filter(db.query(Tracking), current_user, Tracking)
                .filter(
                    Tracking.asset_id == payload.software_asset_id,
                    Tracking.emp_id == req.emp_id,
                    Tracking.movement_type == MovementType.SOFTWARE_ASSIGNED,
                    Tracking.returned_at.is_(None),
                )
                .first()
            )
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Software is already assigned to this employee")

            duplicate = apply_tenant_filter(db.query(Tracking), current_user, Tracking).filter(
                Tracking.asset_id == payload.software_asset_id,
                Tracking.instance_id == payload.instance_id,
                Tracking.emp_id == payload.employee_id,
                Tracking.movement_type == MovementType.SOFTWARE_ASSIGNED,
                Tracking.returned_at.is_(None),
            ).first()
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Software is already assigned to this hardware for the employee",
                )

            if int(software_asset.unused or 0) <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Software has no available licenses")

            movement_reason = f"SOFTWARE_ASSIGNED_REQ:{req.request_id}"
            if payload.notes:
                movement_reason = f"{movement_reason} | {payload.notes}"

            software_asset.unused = max(0, int(software_asset.unused or 0) - 1)
            software_asset.used = int(software_asset.used or 0) + 1
            if software_asset.unused == 0:
                software_asset.asset_status = AssetStatus.ASSIGNED

            assignment = Tracking(
                organization_id=software_asset.organization_id,
                branch_id=hardware_instance.branch_id,
                asset_id=software_asset.asset_id,
                instance_id=hardware_instance.instance_id,
                emp_id=employee.employee_id,
                asset_name=software_asset.name,
                category=software_asset.category.category_name if software_asset.category else None,
                sub_category=software_asset.sub_category.sub_category_name if software_asset.sub_category else None,
                branch=hardware_instance.branch,
                movement_type=MovementType.SOFTWARE_ASSIGNED,
                allocation_type=AllocationType.PERMANENT,
                movement_reason=movement_reason,
            )
            db.add(assignment)
            db.flush()

            req.status = RequestStatus.COMPLETED
            req.stage = "COMPLETED"
            req.asset_id = software_asset.asset_id
            req.completed_at = datetime.now(timezone.utc)
            req.assigned_at = datetime.now(timezone.utc)

            LifecycleService.log_event(
                db,
                instance_id=hardware_instance.instance_id,
                asset_id=software_asset.asset_id,
                event_type=LifecycleEvent.SOFTWARE_ASSIGNED,
                performed_by=current_user,
                old_status=hardware_instance.status.value if hasattr(hardware_instance.status, "value") else str(hardware_instance.status),
                new_status=hardware_instance.status.value if hasattr(hardware_instance.status, "value") else str(hardware_instance.status),
                notes=payload.notes or "Software assigned",
                tracking_id=assignment.tracking_id,
                organization_id=software_asset.organization_id,
                metadata={
                    "request_id": req.request_id,
                    "employee_id": employee.employee_id,
                    "instance_id": hardware_instance.instance_id,
                    "software_id": software_asset.asset_id,
                    "assigned_by": current_user.employee_id,
                },
            )

            AuditService.log_change(
                db,
                "tracking",
                assignment.tracking_id,
                "CREATE",
                current_user,
                None,
                {
                    "asset_id": assignment.asset_id,
                    "instance_id": assignment.instance_id,
                    "employee_id": assignment.emp_id,
                    "movement_type": assignment.movement_type.value,
                },
                "SOFTWARE_ASSIGNED",
            )
            AuditService.log_change(
                db,
                "assets",
                software_asset.asset_id,
                "UPDATE",
                current_user,
                None,
                {"used": software_asset.used, "unused": software_asset.unused},
                "SOFTWARE_USAGE_UPDATE",
            )
            AuditService.log_change(
                db,
                "requests",
                req.request_id,
                "UPDATE",
                current_user,
                None,
                {"status": req.status.value if hasattr(req.status, "value") else str(req.status)},
                "REQUEST_COMPLETED_SOFTWARE_ASSIGNMENT",
            )

        return SoftwareAssignmentResponse(
            assignment_id=assignment.tracking_id,
            request_id=req.request_id,
            employee_id=employee.employee_id,
            software_asset_id=software_asset.asset_id,
            instance_id=hardware_instance.instance_id,
            request_status=req.status.value if hasattr(req.status, "value") else str(req.status),
            assigned_at=assignment.assigned_date,
        )

    @staticmethod
    def remove_software(
        db: Session,
        payload: SoftwareRemovePayload,
        current_user: Employee,
    ) -> SoftwareRemovalResponse:
        with db.begin():
            assignment = apply_tenant_filter(db.query(Tracking), current_user, Tracking).filter(
                Tracking.tracking_id == payload.assignment_id,
                Tracking.movement_type == MovementType.SOFTWARE_ASSIGNED,
                Tracking.returned_at.is_(None),
            ).with_for_update().first()
            if not assignment:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active software assignment not found")

            software_asset = SoftwareService._ensure_software_asset(db, assignment.asset_id, current_user)
            if not assignment.instance_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove software assignment without hardware instance context",
                )

            assignment.returned_at = datetime.now(timezone.utc)
            software_asset.used = max(0, int(software_asset.used or 0) - 1)
            software_asset.unused = int(software_asset.unused or 0) + 1
            if software_asset.unused > 0 and software_asset.asset_status == AssetStatus.ASSIGNED:
                software_asset.asset_status = AssetStatus.ACTIVE

            removal = Tracking(
                organization_id=assignment.organization_id,
                branch_id=assignment.branch_id,
                asset_id=assignment.asset_id,
                instance_id=assignment.instance_id,
                emp_id=assignment.emp_id,
                asset_name=software_asset.name,
                category=software_asset.category.category_name if software_asset.category else None,
                sub_category=software_asset.sub_category.sub_category_name if software_asset.sub_category else None,
                branch=assignment.branch,
                movement_type=MovementType.SOFTWARE_REMOVED,
                allocation_type=AllocationType.PERMANENT,
                movement_reason=payload.reason,
                parent_tracking_id=assignment.tracking_id,
                returned_at=datetime.now(timezone.utc),
            )
            db.add(removal)
            db.flush()

            LifecycleService.log_event(
                db,
                instance_id=assignment.instance_id,
                asset_id=assignment.asset_id,
                event_type=LifecycleEvent.SOFTWARE_REMOVED,
                performed_by=current_user,
                old_status="ASSIGNED",
                new_status="REMOVED",
                notes=payload.reason,
                tracking_id=removal.tracking_id,
                organization_id=assignment.organization_id,
                metadata={
                    "employee_id": assignment.emp_id,
                    "instance_id": assignment.instance_id,
                    "software_id": assignment.asset_id,
                    "removed_by": current_user.employee_id,
                    "assignment_id": assignment.tracking_id,
                },
            )

            followup_request_id: Optional[str] = None
            if payload.create_service_request:
                followup_reason = payload.service_reason or f"Software removal follow-up: {payload.reason}"
                followup = Request(
                    emp_id=assignment.emp_id,
                    organization_id=assignment.organization_id,
                    branch_id=assignment.branch_id,
                    asset_name=software_asset.name,
                    asset_category="Software",
                    reason=followup_reason,
                    request_type=RequestType.SERVICE,
                    instance_id=assignment.instance_id,
                    status=RequestStatus.SUBMITTED,
                    sla_priority="MEDIUM",
                    severity="MEDIUM",
                    urgency="MEDIUM",
                )
                db.add(followup)
                db.flush()
                followup_request_id = followup.request_id

            AuditService.log_change(
                db,
                "tracking",
                removal.tracking_id,
                "CREATE",
                current_user,
                None,
                {
                    "movement_type": removal.movement_type.value,
                    "asset_id": removal.asset_id,
                    "instance_id": removal.instance_id,
                    "employee_id": removal.emp_id,
                },
                "SOFTWARE_REMOVED",
            )
            AuditService.log_change(
                db,
                "assets",
                software_asset.asset_id,
                "UPDATE",
                current_user,
                None,
                {"used": software_asset.used, "unused": software_asset.unused},
                "SOFTWARE_USAGE_UPDATE",
            )

        return SoftwareRemovalResponse(
            assignment_id=assignment.tracking_id,
            removal_tracking_id=removal.tracking_id,
            software_asset_id=assignment.asset_id,
            instance_id=assignment.instance_id or "",
            employee_id=assignment.emp_id,
            removed_at=removal.assigned_date,
            followup_request_id=followup_request_id,
        )

    @staticmethod
    def assignment_history(
        db: Session,
        current_user: Employee,
        request_id: Optional[str] = None,
        employee_id: Optional[str] = None,
    ) -> list[SoftwareAssignmentHistoryItem]:
        query = (
            apply_tenant_filter(db.query(Tracking), current_user, Tracking)
            .options(joinedload(Tracking.asset), joinedload(Tracking.employee))
            .filter(Tracking.movement_type.in_([MovementType.SOFTWARE_ASSIGNED, MovementType.SOFTWARE_REMOVED]))
        )

        if employee_id:
            query = query.filter(Tracking.emp_id == employee_id)

        if request_id:
            query = query.filter(Tracking.movement_reason.ilike(f"%SOFTWARE_ASSIGNED_REQ:{request_id}%"))

        rows = query.order_by(Tracking.assigned_date.desc()).all()

        return [
            SoftwareAssignmentHistoryItem(
                tracking_id=row.tracking_id,
                assignment_id=row.parent_tracking_id if row.movement_type == MovementType.SOFTWARE_REMOVED else row.tracking_id,
                movement_type=row.movement_type.value if hasattr(row.movement_type, "value") else str(row.movement_type),
                software_asset_id=row.asset_id,
                software_name=(row.asset.name if row.asset else row.asset_name),
                instance_id=row.instance_id,
                employee_id=row.emp_id,
                employee_name=(row.employee.name if row.employee else None),
                notes=row.movement_reason,
                assigned_date=row.assigned_date,
                returned_at=row.returned_at,
            )
            for row in rows
        ]

    @staticmethod
    def usage_summary(db: Session, current_user: Employee) -> list[SoftwareUsageItem]:
        software_assets = (
            apply_tenant_filter(db.query(Asset), current_user, Asset)
            .join(Asset.category)
            .filter(func.lower(Category.category_name) == "software")
            .order_by(Asset.name.asc())
            .all()
        )

        active_counts = {
            row[0]: int(row[1])
            for row in (
                apply_tenant_filter(db.query(Tracking.asset_id, func.count(Tracking.tracking_id)), current_user, Tracking)
                .filter(
                    Tracking.movement_type == MovementType.SOFTWARE_ASSIGNED,
                    Tracking.returned_at.is_(None),
                )
                .group_by(Tracking.asset_id)
                .all()
            )
        }

        results: list[SoftwareUsageItem] = []
        for asset in software_assets:
            total = int(asset.total_quantity or 0)
            assigned = active_counts.get(asset.asset_id, 0)
            available = max(total - assigned, 0)
            results.append(
                SoftwareUsageItem(
                    software_asset_id=asset.asset_id,
                    software_name=asset.name,
                    total=total,
                    assigned=assigned,
                    available=available,
                )
            )

        return results
