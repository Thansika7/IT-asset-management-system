from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from sqlalchemy import and_
import os
from app.server.schema.asset import Asset, AssetStatus, AssetInstance
from app.server.schema.tracking import Tracking, MovementType, AllocationType, LifecycleEvent
from app.server.schema.request import Request
from app.server.schema.employee import Employee
from app.server.schema.organization import Branch
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.exceptions.base import InsufficientStockError, InvalidStateError, ResourceNotFoundError
from app.server.services.audit_service import AuditService
from app.server.services.lifecycle_service import LifecycleService
from app.server.services.notification_service import NotificationPriority, NotificationService
from app.server.database.tenant import apply_tenant_filter
from typing import Dict
from app.server.models.stock import AssetAttributeUpdateItem, AssetAttributeUpdateResponse, AssetAttributeUpdateResult

class InventorySnapshot:
    """Read-only snapshot of inventory counts for an asset."""
    def __init__(
        self,
        total: int = 0,
        available: int = 0,
        assigned: int = 0,
        in_repair: int = 0,
        not_usable: int = 0,
        retired: int = 0
    ):
        self.total = total
        self.available = available
        self.assigned = assigned
        self.in_repair = in_repair
        self.not_usable = not_usable
        self.retired = retired

    def allocatable(self) -> int:
        """Count of instances that can be allocated."""
        return self.available

class InstanceStateMachine:
    """Validates state transitions for AssetInstance according to strict state machine rules."""
    
    # Valid transitions: from_state -> [to_state, ...]
    VALID_TRANSITIONS = {
        AssetStatus.NEW: [AssetStatus.AVAILABLE, AssetStatus.NOT_USABLE],
        AssetStatus.AVAILABLE: [AssetStatus.RESERVED, AssetStatus.ASSIGNED, AssetStatus.RETIRED],
        AssetStatus.RESERVED: [AssetStatus.ASSIGNED, AssetStatus.AVAILABLE],
        AssetStatus.ASSIGNED: [AssetStatus.IN_REPAIR, AssetStatus.RETIRED, AssetStatus.AVAILABLE],
        AssetStatus.USED: [AssetStatus.IN_REPAIR, AssetStatus.ASSIGNED, AssetStatus.AVAILABLE],
        AssetStatus.IN_REPAIR: [AssetStatus.AVAILABLE, AssetStatus.NOT_USABLE],
        AssetStatus.NOT_USABLE: [AssetStatus.RETIRED],
        AssetStatus.RETIRED: [],  # Terminal state
        AssetStatus.DAMAGED: [AssetStatus.RETIRED, AssetStatus.IN_REPAIR],
        AssetStatus.LOST: [AssetStatus.RETIRED],
        AssetStatus.WARRANTY: [AssetStatus.AVAILABLE, AssetStatus.IN_REPAIR],
    }
    
    @staticmethod
    def is_valid_transition(from_status: AssetStatus, to_status: AssetStatus) -> bool:
        """Check if transition is allowed."""
        if from_status not in InstanceStateMachine.VALID_TRANSITIONS:
            return False
        allowed = InstanceStateMachine.VALID_TRANSITIONS[from_status]
        return to_status in allowed
    
    @staticmethod
    def validate_transition(from_status: AssetStatus, to_status: AssetStatus) -> None:
        """Raise InvalidStateError if transition not allowed."""
        if not InstanceStateMachine.is_valid_transition(from_status, to_status):
            raise InvalidStateError(
                f"Invalid state transition: {from_status} → {to_status}"
            )

class StockService:
    REPAIR_BUDGET_ALERT_THRESHOLD = float(os.getenv("REPAIR_BUDGET_ALERT_THRESHOLD", "5000"))

    @staticmethod
    def delete_asset(db: Session, asset_id: str, user: Employee) -> None:
        """Delete an asset model only when it has no active usage or historical links."""
        asset = (
            apply_tenant_filter(db.query(Asset), user, Asset)
            .filter(Asset.asset_id == asset_id)
            .with_for_update()
            .first()
        )
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        assigned_count = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(
                AssetInstance.asset_id == asset_id,
                AssetInstance.assigned_to_id.isnot(None),
            )
            .count()
        )
        if assigned_count > 0:
            raise InvalidStateError("Cannot delete asset while one or more instances are assigned")

        active_tracking_count = (
            apply_tenant_filter(db.query(Tracking), user, Tracking)
            .filter(
                Tracking.asset_id == asset_id,
                Tracking.returned_at.is_(None),
            )
            .count()
        )
        if active_tracking_count > 0:
            raise InvalidStateError("Cannot delete asset with active tracking records")

        historical_tracking_count = (
            apply_tenant_filter(db.query(Tracking), user, Tracking)
            .filter(Tracking.asset_id == asset_id)
            .count()
        )
        if historical_tracking_count > 0:
            raise InvalidStateError("Cannot delete asset with historical tracking records")

        linked_request_count = (
            apply_tenant_filter(db.query(Request), user, Request)
            .filter(Request.asset_id == asset_id)
            .count()
        )
        if linked_request_count > 0:
            raise InvalidStateError("Cannot delete asset with linked requests")

        snapshot = {
            "asset_id": asset.asset_id,
            "name": asset.name,
            "category_id": asset.category_id,
            "sub_category_id": asset.sub_category_id,
            "total_quantity": asset.total_quantity,
            "used": asset.used,
            "unused": asset.unused,
            "status": asset.asset_status.value if asset.asset_status else None,
        }

        AuditService.log_change(
            db,
            "assets",
            asset.asset_id,
            "DELETE",
            user,
            snapshot,
            None,
            "ASSET_DELETE",
        )

        db.delete(asset)

    # ============================================================================
    # DYNAMIC INVENTORY CALCULATION HELPERS
    # ============================================================================
    # These methods calculate inventory from AssetInstance statuses instead of
    # relying on static counters that become out of sync.

    @staticmethod
    def get_inventory(db: Session, asset_id: str) -> InventorySnapshot:
        """
        Calculate inventory for an asset by querying AssetInstance statuses.
        
        This is the single source of truth for inventory counts.
        DO NOT trust Asset.total_quantity, Asset.used, Asset.unused.
        
        Returns: InventorySnapshot with counts by status
        """
        grouped = (
            db.query(AssetInstance.status, func.count(AssetInstance.instance_id))
            .filter(AssetInstance.asset_id == asset_id)
            .group_by(AssetInstance.status)
            .all()
        )

        snapshot = InventorySnapshot()

        for status, count in grouped:
            if status in {AssetStatus.AVAILABLE, AssetStatus.NEW}:
                snapshot.available += int(count)
            elif status in {AssetStatus.ASSIGNED, AssetStatus.USED}:
                snapshot.assigned += int(count)
            elif status in {AssetStatus.IN_REPAIR, AssetStatus.WARRANTY}:
                snapshot.in_repair += int(count)
            elif status in {AssetStatus.NOT_USABLE, AssetStatus.DAMAGED, AssetStatus.LOST}:
                snapshot.not_usable += int(count)
            elif status == AssetStatus.RETIRED:
                snapshot.retired += int(count)

        snapshot.total = snapshot.available + snapshot.assigned + snapshot.in_repair + snapshot.not_usable
        return snapshot

    @staticmethod
    def get_inventory_for_branch(db: Session, asset_id: str, branch_id: str) -> InventorySnapshot:
        """Get inventory filtered to a specific branch."""
        grouped = (
            db.query(AssetInstance.status, func.count(AssetInstance.instance_id))
            .filter(
                AssetInstance.asset_id == asset_id,
                AssetInstance.branch_id == branch_id,
            )
            .group_by(AssetInstance.status)
            .all()
        )

        snapshot = InventorySnapshot()

        for status, count in grouped:
            if status in {AssetStatus.AVAILABLE, AssetStatus.NEW}:
                snapshot.available += int(count)
            elif status in {AssetStatus.ASSIGNED, AssetStatus.USED}:
                snapshot.assigned += int(count)
            elif status in {AssetStatus.IN_REPAIR, AssetStatus.WARRANTY}:
                snapshot.in_repair += int(count)
            elif status in {AssetStatus.NOT_USABLE, AssetStatus.DAMAGED, AssetStatus.LOST}:
                snapshot.not_usable += int(count)
            elif status == AssetStatus.RETIRED:
                snapshot.retired += int(count)

        snapshot.total = snapshot.available + snapshot.assigned + snapshot.in_repair + snapshot.not_usable
        return snapshot

    @staticmethod
    def find_available_instance(db: Session, asset_id: str, branch_id: str = None) -> AssetInstance:
        """
        Find any AVAILABLE instance for allocation.
        
        Enforces strict availability (status == AVAILABLE).
        If branch_id specified, filters to that branch.
        
        Raises: InsufficientStockError if no available instance found
        """
        query = db.query(AssetInstance).filter(
            AssetInstance.asset_id == asset_id,
            AssetInstance.status == AssetStatus.AVAILABLE
        )
        
        if branch_id:
            query = query.filter(AssetInstance.branch_id == branch_id)
        
        instance = query.first()
        
        if not instance:
            asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
            raise InsufficientStockError(
                asset.name if asset else asset_id,
                0
            )
        
        return instance

    # ============================================================================
    # INSTANCE-DRIVEN OPERATIONS (NEW)
    # ============================================================================

    @staticmethod
    def mark_in_repair(
        db: Session,
        instance_id: str,
        user: Employee,
        reason: str = "SENT_FOR_REPAIR",
        repair_cost: float = 0.0,
    ):
        """Mark an instance as IN_REPAIR. Validates state transition."""
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        
        # Validate state transition
        InstanceStateMachine.validate_transition(instance.status, AssetStatus.IN_REPAIR)

        if repair_cost < 0:
            raise InvalidStateError("repair_cost cannot be negative")
        
        old_status = instance.status
        old_instance_repair_cost = float(instance.repair_cost_total or 0.0)
        instance.status = AssetStatus.IN_REPAIR
        instance.repair_started_at = func.now()
        instance.repair_cost_total = old_instance_repair_cost + float(repair_cost)

        if instance.model:
            instance.model.repair_total_cost = float(instance.model.repair_total_cost or 0.0) + float(repair_cost)
            if repair_cost > 0:
                instance.model.repair_count = int(instance.model.repair_count or 0) + 1
        
        AuditService.log_change(
            db, "asset_instances", instance_id, "UPDATE", user,
            {"status": old_status.value, "repair_cost_total": old_instance_repair_cost},
            {"status": AssetStatus.IN_REPAIR.value, "repair_cost_total": float(instance.repair_cost_total or 0.0)},
            reason
        )

        if instance.model and repair_cost > 0:
            AuditService.log_change(
                db,
                "assets",
                instance.asset_id,
                "UPDATE",
                user,
                {"repair_total_cost": float(instance.model.repair_total_cost or 0.0) - float(repair_cost)},
                {"repair_total_cost": float(instance.model.repair_total_cost or 0.0)},
                "REPAIR_COST_UPDATE",
            )
        
        # Log lifecycle event
        LifecycleService.log_event(
            db,
            instance_id=instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.REPAIR_STARTED,
            performed_by=user,
            old_status=old_status.value,
            new_status=AssetStatus.IN_REPAIR.value,
            notes=reason,
            organization_id=instance.organization_id,
            metadata={"repair_cost": float(repair_cost)},
        )

        if repair_cost > StockService.REPAIR_BUDGET_ALERT_THRESHOLD:
            from app.server.services.email_service import EmailService

            recipients = EmailService.collect_hr_admin_emails(db, instance.branch)
            if recipients:
                EmailService.notify_budget_alert(
                    recipients=recipients,
                    asset_name=instance.model.name if instance.model else instance.asset_id,
                    instance_id=instance.instance_id,
                    repair_cost=float(repair_cost),
                    threshold=float(StockService.REPAIR_BUDGET_ALERT_THRESHOLD),
                    branch=instance.branch or "-",
                )
            NotificationService.emit(
                db,
                actor=user,
                recipient_scope=f"BRANCH:{instance.branch_id or '-'}",
                event_type="BUDGET_EXCEEDED",
                title="Repair Budget Exceeded",
                message=f"Repair cost for instance {instance.instance_id} exceeded threshold.",
                priority=NotificationPriority.CRITICAL,
                dedup_key=f"budget_exceeded:{instance.instance_id}",
                cooldown_hours=24,
                metadata={
                    "instance_id": instance.instance_id,
                    "asset_id": instance.asset_id,
                    "repair_cost": float(repair_cost),
                    "threshold": float(StockService.REPAIR_BUDGET_ALERT_THRESHOLD),
                },
            )
        
        return instance

    @staticmethod
    def mark_repaired(db: Session, instance_id: str, user: Employee, reason: str = "REPAIR_COMPLETED"):
        """Mark an instance as AVAILABLE after repair. Validates state transition."""
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        
        # Validate state transition
        InstanceStateMachine.validate_transition(instance.status, AssetStatus.AVAILABLE)
        
        old_status = instance.status
        instance.status = AssetStatus.AVAILABLE
        instance.repair_completed_at = func.now()
        instance.assigned_to_id = None
        
        AuditService.log_change(
            db, "asset_instances", instance_id, "UPDATE", user,
            {"status": old_status.value},
            {"status": AssetStatus.AVAILABLE.value},
            reason
        )
        
        # Log lifecycle event
        LifecycleService.log_event(
            db,
            instance_id=instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.REPAIR_COMPLETED,
            performed_by=user,
            old_status=old_status.value,
            new_status=AssetStatus.AVAILABLE.value,
            notes=reason,
            organization_id=instance.organization_id
        )

        # Keep CMDB in sync with lifecycle: retiring an asset instance retires mapped CIs.
        from app.server.services.cmdb_service import CMDBService

        CMDBService.mark_asset_cis_retired(
            db,
            current_user=user,
            asset_id=instance.asset_id,
            reason="ASSET_RETIRE_CI_SYNC",
        )
        
        return instance

    @staticmethod
    def mark_damaged(db: Session, instance_id: str, user: Employee, reason: str = "MARKED_DAMAGED"):
        """Mark an instance as DAMAGED/NOT_USABLE. Validates state transition."""
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        
        # Validate state transition
        InstanceStateMachine.validate_transition(instance.status, AssetStatus.DAMAGED)
        
        old_status = instance.status
        instance.status = AssetStatus.DAMAGED
        instance.assigned_to_id = None
        
        AuditService.log_change(
            db, "asset_instances", instance_id, "UPDATE", user,
            {"status": old_status.value},
            {"status": AssetStatus.DAMAGED.value},
            reason
        )
        
        # Log lifecycle event
        LifecycleService.log_event(
            db,
            instance_id=instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.DAMAGED,
            performed_by=user,
            old_status=old_status.value,
            new_status=AssetStatus.DAMAGED.value,
            notes=reason,
            organization_id=instance.organization_id
        )
        
        return instance

    @staticmethod
    def retire_instance(db: Session, instance_id: str, user: Employee, reason: str = "RETIRED"):
        """Mark an instance as RETIRED (end of life). Validates state transition."""
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        
        # Validate state transition
        InstanceStateMachine.validate_transition(instance.status, AssetStatus.RETIRED)
        
        old_status = instance.status
        instance.status = AssetStatus.RETIRED
        instance.retired_at = func.now()
        instance.assigned_to_id = None
        
        AuditService.log_change(
            db, "asset_instances", instance_id, "UPDATE", user,
            {"status": old_status.value},
            {"status": AssetStatus.RETIRED.value},
            reason
        )
        
        # Log lifecycle event
        LifecycleService.log_event(
            db,
            instance_id=instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.RETIRED,
            performed_by=user,
            old_status=old_status.value,
            new_status=AssetStatus.RETIRED.value,
            notes=reason,
            organization_id=instance.organization_id
        )
        
        return instance

    @staticmethod
    def transfer_asset(
        db: Session,
        instance_id: str,
        from_emp_id: str,
        to_emp_id: str,
        user: Employee,
        reason: str = "TRANSFER"
    ) -> Tracking:
        """
        Transfer asset from one employee to another.
        Updates instance assigned_to, creates new tracking record.
        """
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        
        if instance.status != AssetStatus.ASSIGNED:
            raise InvalidStateError(
                f"Cannot transfer instance in {instance.status} status. "
                f"Only ASSIGNED instances can be transferred."
            )

        from_employee = (
            apply_tenant_filter(db.query(Employee), user, Employee)
            .filter(Employee.employee_id == from_emp_id)
            .first()
        )
        to_employee = (
            apply_tenant_filter(db.query(Employee), user, Employee)
            .filter(Employee.employee_id == to_emp_id)
            .first()
        )
        if not from_employee:
            raise ResourceNotFoundError("Employee", from_emp_id)
        if not to_employee:
            raise ResourceNotFoundError("Employee", to_emp_id)
        if to_employee.organization_id != instance.organization_id:
            raise InvalidStateError("Cross-organization ownership transfer is not allowed")

        target_branch_id = to_employee.branch_id or instance.branch_id
        
        # Create return tracking for original employee
        old_tracking = Tracking(
            asset_id=instance.asset_id,
            instance_id=instance.instance_id,
            emp_id=from_emp_id,
            organization_id=instance.organization_id,
            branch_id=instance.branch_id,
            movement_type=MovementType.TRANSFER,
            movement_reason=reason
        )
        old_tracking.returned_at = func.now()
        db.add(old_tracking)
        db.flush()
        
        # Create new allocation tracking for new employee
        new_tracking = Tracking(
            asset_id=instance.asset_id,
            instance_id=instance.instance_id,
            emp_id=to_emp_id,
            organization_id=instance.organization_id,
            branch_id=target_branch_id,
            movement_type=MovementType.TRANSFER,
            allocation_type=AllocationType.PERMANENT,
            movement_reason=reason,
            parent_tracking_id=old_tracking.tracking_id
        )
        db.add(new_tracking)
        
        # Update instance assignment
        instance.assigned_to_id = to_emp_id
        instance.branch_id = target_branch_id
        
        AuditService.log_change(
            db, "asset_instances", instance_id, "UPDATE", user,
            {"assigned_to": from_emp_id},
            {"assigned_to": to_emp_id},
            reason
        )
        
        # Log lifecycle event
        LifecycleService.log_event(
            db,
            instance_id=instance.instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.TRANSFERRED,
            performed_by=user,
            old_status=AssetStatus.ASSIGNED.value,
            new_status=AssetStatus.ASSIGNED.value,
            notes=f"{reason}: {from_emp_id} → {to_emp_id}",
            tracking_id=new_tracking.tracking_id,
            organization_id=instance.organization_id
        )

        from app.server.services.email_service import EmailService

        NotificationService.emit(
            db,
            actor=user,
            recipient_scope=to_emp_id,
            event_type="ASSET_TRANSFERRED",
            title="Asset Transferred",
            message=f"Instance {instance.instance_id} has been transferred to you.",
            priority=NotificationPriority.HIGH,
            dedup_key=f"asset_transferred:{instance.instance_id}:{to_emp_id}",
            cooldown_hours=1,
            metadata={"instance_id": instance.instance_id, "asset_id": instance.asset_id},
            email_to=EmailService.delivery_email(to_employee),
            email_subject=f"Asset Transferred: {instance.instance_id}",
            email_html=EmailService._wrap_email(
                "Asset Transferred",
                instance.model.name if instance.model else instance.asset_id,
                f"<p>Asset instance <strong>{instance.instance_id}</strong> has been transferred to you.</p>",
                accent_color="#2563eb",
            ),
        )
        
        return new_tracking

    # ============================================================================
    # ORIGINAL METHODS (REFACTORED TO USE INSTANCE-DRIVEN LOGIC)
    # ============================================================================

    @staticmethod
    def add_stock(
        db: Session, asset_id: str, quantity: int, user: Employee, 
        reason: str = "RESTOCK",
        cost: float | None = None,
        vendor_name: str | None = None,
        invoice_number: str | None = None,
        instances: list = None
    ):
        """
        Add stock to an asset.
        
        If instances are provided, creates AssetInstance entities.
        If quantity is provided without instances, creates that many generic instances.
        
        INSTANCE-DRIVEN: Uses UUID-based IDs for concurrency safety.
        All counts are derived from AssetInstance statuses,
        NOT from the static Asset.total_quantity, Asset.used, Asset.unused.
        """
        from uuid import uuid4
        
        asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(
            Asset.asset_id == asset_id
        ).with_for_update().first()
        
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        employee = (
            apply_tenant_filter(db.query(Employee), user, Employee)
            .filter(Employee.employee_id == emp_id)
            .first()
        )
        if not employee:
            raise ResourceNotFoundError("Employee", emp_id)
        if employee.organization_id != asset.organization_id:
            raise InvalidStateError("Employee and asset must belong to same organization")
        
        # Get current inventory (before adding)
        old_inventory = StockService.get_inventory(db, asset_id)
        old_val = {
            "available": old_inventory.available,
            "assigned": old_inventory.assigned,
            "total": old_inventory.total,
        }
        
        # Create instances
        if instances:
            for inst_data in instances:
                # Use UUID-based instance ID for concurrency safety
                new_inst = AssetInstance(
                    instance_id=f"INS-{uuid4().hex[:12].upper()}",
                    asset_id=asset_id,
                    organization_id=asset.organization_id,
                    branch_id=inst_data.branch_id or asset.branch_id,
                    serial_number=inst_data.serial_number,
                    asset_tag=inst_data.asset_tag,
                    # Vendor data per instance
                    vendor_name=vendor_name or (inst_data.vendor_name if hasattr(inst_data, 'vendor_name') else None),
                    vendor_contact=inst_data.vendor_contact if hasattr(inst_data, 'vendor_contact') else None,
                    invoice_number=invoice_number or (inst_data.invoice_number if hasattr(inst_data, 'invoice_number') else None),
                    status=AssetStatus.AVAILABLE,  # New stock is always AVAILABLE
                    purchase_date=inst_data.purchase_date,
                    purchase_cost=cost or inst_data.purchase_cost,
                    warranty_expiry=inst_data.warranty_expiry,
                    condition_notes=inst_data.condition_notes
                )
                db.add(new_inst)
            quantity = len(instances)
        else:
            # Create generic instances if no specific instances provided
            for i in range(quantity):
                new_inst = AssetInstance(
                    # Use UUID-based instance ID for concurrency safety
                    instance_id=f"INS-{uuid4().hex[:12].upper()}",
                    asset_id=asset_id,
                    organization_id=asset.organization_id,
                    branch_id=asset.branch_id,
                    vendor_name=vendor_name,
                    vendor_contact=None,
                    invoice_number=invoice_number,
                    status=AssetStatus.AVAILABLE,
                    purchase_cost=cost
                )
                db.add(new_inst)
        
        db.flush()
        
        # Get new inventory (after adding)
        new_inventory = StockService.get_inventory(db, asset_id)
        new_val = {
            "available": new_inventory.available,
            "assigned": new_inventory.assigned,
            "total": new_inventory.total,
        }
        
        # Keep legacy counters in sync for backward compatibility
        asset.total_quantity = new_inventory.total
        asset.used = new_inventory.assigned
        asset.unused = new_inventory.available
        
        # Update asset status based on available quantity
        if new_inventory.available > 0:
            asset.asset_status = AssetStatus.ACTIVE
        elif new_inventory.assigned > 0:
            asset.asset_status = AssetStatus.ASSIGNED
        else:
            asset.asset_status = AssetStatus.NOT_USABLE
        
        AuditService.log_change(
            db, "assets", asset_id, "UPDATE", user, old_val, new_val, reason
        )
        
        return asset

    @staticmethod
    def allocate_asset(db: Session, asset_id: str, emp_id: str, alloc_type: AllocationType, user: Employee, reason: str = "ALLOCATION", instance_id: str = None) -> Tracking:
        """
        Allocate an asset instance to an employee.
        
        INSTANCE-DRIVEN: Uses AssetInstance.status to determine availability.
        Finds any AVAILABLE instance and marks it as ASSIGNED with state validation.
        
        Returns: Tracking record for the allocation
        """
        asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(
            Asset.asset_id == asset_id
        ).with_for_update().first()
        
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)
        
        # Find an available instance
        target_instance = None
        
        if instance_id:
            # User requesting specific instance
            target_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(
                AssetInstance.instance_id == instance_id,
                AssetInstance.asset_id == asset_id,
                AssetInstance.status == AssetStatus.AVAILABLE,
            ).with_for_update().first()
            
            if not target_instance:
                raise InvalidStateError(
                    f"Instance {instance_id} not found or not available for allocation."
                )
        else:
            # Find ANY available instance
            target_instance = StockService.find_available_instance(db, asset_id)
        
        # Validate state transition before changing
        InstanceStateMachine.validate_transition(target_instance.status, AssetStatus.ASSIGNED)
        
        # Mark instance as ASSIGNED
        old_status = target_instance.status
        target_instance.status = AssetStatus.ASSIGNED
        target_instance.assigned_to_id = emp_id
        target_instance.assigned_at = func.now()
        
        # Log instance status change
        AuditService.log_change(
            db, "asset_instances", target_instance.instance_id, "UPDATE", user,
            {"status": old_status.value, "assigned_to": None},
            {"status": AssetStatus.ASSIGNED.value, "assigned_to": emp_id},
            reason
        )
        
        # Update legacy counters for backward compatibility
        inventory = StockService.get_inventory(db, asset_id)
        old_val = {
            "available": inventory.available - 1,  # Will have one less after allocation
            "assigned": inventory.assigned + 1
        }
        
        asset.unused = max(0, asset.unused - 1)
        asset.used += 1
        asset.total_quantity = inventory.total
        
        if asset.unused <= 0:
            asset.asset_status = AssetStatus.ASSIGNED
        
        new_val = {
            "available": inventory.available - 1,
            "assigned": inventory.assigned + 1
        }
        
        AuditService.log_change(
            db, "assets", asset_id, "UPDATE", user, old_val, new_val, reason
        )
        
        # Create tracking record
        trk = Tracking(
            asset_id=asset_id,
            instance_id=target_instance.instance_id,
            emp_id=emp_id,
            branch=asset.branch,
            organization_id=asset.organization_id,
            branch_id=asset.branch_id,
            movement_type=MovementType.ALLOCATE,
            allocation_type=alloc_type,
            movement_reason=reason
        )
        db.add(trk)
        db.flush()
        
        # Log lifecycle event
        LifecycleService.log_event(
            db,
            instance_id=target_instance.instance_id,
            asset_id=asset_id,
            event_type=LifecycleEvent.ASSIGNED,
            performed_by=user,
            old_status=old_status.value,
            new_status=AssetStatus.ASSIGNED.value,
            notes=reason,
            tracking_id=trk.tracking_id,
            organization_id=asset.organization_id
        )

        from app.server.services.email_service import EmailService

        recipient = (
            apply_tenant_filter(db.query(Employee), user, Employee)
            .filter(Employee.employee_id == emp_id)
            .first()
        )
        recipient_email = EmailService.delivery_email(recipient) if recipient else None
        NotificationService.emit(
            db,
            actor=user,
            recipient_scope=emp_id,
            event_type="ASSET_ASSIGNED",
            title="Asset Assigned",
            message=f"Asset {asset.name} ({target_instance.instance_id}) has been assigned to you.",
            priority=NotificationPriority.HIGH,
            dedup_key=f"asset_assigned:{target_instance.instance_id}:{emp_id}",
            cooldown_hours=1,
            metadata={"asset_id": asset_id, "instance_id": target_instance.instance_id},
            email_to=recipient_email,
            email_subject=f"Asset Assigned: {asset.name}",
            email_html=EmailService._wrap_email(
                "Asset Assigned",
                asset.name,
                f"<p>Asset instance <strong>{target_instance.instance_id}</strong> has been assigned to you.</p>",
                accent_color="#0ea5e9",
            ),
        )
        
        return trk

    @staticmethod
    def return_asset(db: Session, tracking_id: str, user: Employee, reason: str = "RETURN", status_override: AssetStatus = AssetStatus.AVAILABLE) -> Tracking:
        """
        Return an allocated asset from an employee.
        
        INSTANCE-DRIVEN: Updates AssetInstance status with state validation.
        Updates legacy counters for backward compatibility.
        
        Returns: Updated Tracking record
        """
        trk = apply_tenant_filter(db.query(Tracking), user, Tracking).filter(
            Tracking.tracking_id == tracking_id,
            Tracking.returned_at == None
        ).with_for_update().first()
        
        if not trk:
            raise ResourceNotFoundError("Active Tracking Record", tracking_id)
        
        asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(
            Asset.asset_id == trk.asset_id
        ).with_for_update().first()
        
        # Update legacy counters
        old_asset_val = {
            "unused": asset.unused,
            "used": asset.used,
            "asset_status": asset.asset_status.value
        }
        
        asset.unused += 1
        asset.used = max(0, asset.used - 1)
        asset.asset_status = AssetStatus.ACTIVE
        
        new_asset_val = {
            "unused": asset.unused,
            "used": asset.used,
            "asset_status": AssetStatus.ACTIVE.value
        }
        
        AuditService.log_change(
            db, "assets", trk.asset_id, "UPDATE", user,
            old_asset_val, new_asset_val, reason
        )
        
        # Update instance status
        if trk.instance_id:
            instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(
                AssetInstance.instance_id == trk.instance_id
            ).with_for_update().first()
            
            if instance:
                old_inst_status = instance.status
                # Validate state transition
                InstanceStateMachine.validate_transition(old_inst_status, status_override)
                
                instance.status = status_override
                instance.returned_at = func.now()
                instance.assigned_to_id = None
                
                AuditService.log_change(
                    db, "asset_instances", instance.instance_id, "UPDATE", user,
                    {"status": old_inst_status.value},
                    {"status": status_override.value},
                    reason
                )
                
                # Log lifecycle event
                LifecycleService.log_event(
                    db,
                    instance_id=instance.instance_id,
                    asset_id=trk.asset_id,
                    event_type=LifecycleEvent.RETURNED,
                    performed_by=user,
                    old_status=old_inst_status.value,
                    new_status=status_override.value,
                    notes=reason,
                    tracking_id=trk.tracking_id,
                    organization_id=instance.organization_id
                )
        
        # Mark tracking as returned
        trk.returned_at = func.now()
        db.flush()
        
        return trk

    @staticmethod
    def transfer_instance_branch(
        db: Session,
        instance_id: str,
        target_branch_id: str,
        user: Employee,
        reason: str = "BRANCH_TRANSFER",
    ) -> Tracking:
        """
        Transfer an unassigned instance from one branch to another inside the same organization.
        """
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        if instance.assigned_to_id:
            raise InvalidStateError("Assigned assets cannot be branch-transferred")
        if instance.status != AssetStatus.AVAILABLE:
            raise InvalidStateError("Only AVAILABLE assets can be branch-transferred")

        source_branch_id = instance.branch_id
        source_branch = (
            apply_tenant_filter(db.query(Branch), user, Branch)
            .filter(Branch.branch_id == source_branch_id)
            .first()
            if source_branch_id
            else None
        )
        target_branch = (
            apply_tenant_filter(db.query(Branch), user, Branch)
            .filter(Branch.branch_id == target_branch_id)
            .first()
        )
        if not target_branch:
            raise ResourceNotFoundError("Branch", target_branch_id)
        if target_branch.organization_id != instance.organization_id:
            raise InvalidStateError("Cross-organization branch transfer is not allowed")

        instance.branch_id = target_branch_id

        transfer_tracking = Tracking(
            asset_id=instance.asset_id,
            instance_id=instance.instance_id,
            emp_id=user.employee_id,
            organization_id=instance.organization_id,
            branch_id=target_branch_id,
            movement_type=MovementType.TRANSFER,
            movement_reason=reason,
            from_branch=source_branch.branch_name if source_branch else None,
            to_branch=target_branch.branch_name,
            allocation_type=AllocationType.PERMANENT,
        )
        db.add(transfer_tracking)
        db.flush()

        AuditService.log_change(
            db,
            "asset_instances",
            instance_id,
            "UPDATE",
            user,
            {"branch_id": source_branch_id},
            {"branch_id": target_branch_id},
            "BRANCH_TRANSFER",
        )

        LifecycleService.log_event(
            db,
            instance_id=instance.instance_id,
            asset_id=instance.asset_id,
            event_type=LifecycleEvent.TRANSFERRED,
            performed_by=user,
            old_status=AssetStatus.AVAILABLE.value,
            new_status=AssetStatus.AVAILABLE.value,
            notes=f"{reason}: {source_branch_id or '-'} -> {target_branch_id}",
            tracking_id=transfer_tracking.tracking_id,
            organization_id=instance.organization_id,
            metadata={
                "source_branch_id": source_branch_id,
                "target_branch_id": target_branch_id,
            },
        )

        return transfer_tracking

    @staticmethod
    def update_instance_status(db: Session, instance_id: str, new_status: AssetStatus, user: Employee, reason: str = "STATUS_UPDATE"):
        """
        Update an instance's status. Handles all status transitions.
        
        Automatically:
        - Updates Asset legacy counters
        - Removes assignment if moving to non-usable states
        - Logs audit entries
        """
        instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(
            AssetInstance.instance_id == instance_id
        ).with_for_update().first()
        
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)
        
        old_status = instance.status
        instance.status = new_status
        
        # Clear assignment if moving to non-usable state
        if new_status in [AssetStatus.RETIRED, AssetStatus.DAMAGED, AssetStatus.NOT_USABLE, AssetStatus.LOST]:
            instance.assigned_to_id = None
        
        # Update asset legacy counters
        asset = db.query(Asset).filter(Asset.asset_id == instance.asset_id).with_for_update().first()
        if asset:
            inventory = StockService.get_inventory(db, instance.asset_id)
            asset.total_quantity = inventory.total
            asset.used = inventory.assigned
            asset.unused = inventory.available
        
        AuditService.log_change(
            db, "asset_instances", instance_id, "UPDATE", user,
            {"status": old_status.value},
            {"status": new_status.value},
            reason
        )
        
        return instance

    @staticmethod
    def update_asset_attributes(
        db: Session,
        instance_id: str,
        updates: list[AssetAttributeUpdateItem],
        user: Employee,
        event_type: LifecycleEvent = LifecycleEvent.ATTRIBUTE_UPDATED,
        reason: str | None = None,
    ) -> AssetAttributeUpdateResponse:
        """Update tracked asset attribute values and record lifecycle/audit entries."""
        instance = (
            apply_tenant_filter(db.query(AssetInstance), user, AssetInstance)
            .filter(AssetInstance.instance_id == instance_id)
            .with_for_update()
            .first()
        )
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)

        asset = (
            apply_tenant_filter(db.query(Asset), user, Asset)
            .filter(Asset.asset_id == instance.asset_id)
            .with_for_update()
            .first()
        )
        if not asset:
            raise ResourceNotFoundError("Asset", instance.asset_id)
        if not asset.sub_category_id:
            raise InvalidStateError("Asset must have a sub-category before attribute updates can be tracked")

        resolved_reason = reason or event_type.value
        update_results: list[AssetAttributeUpdateResult] = []

        for update in updates:
            attribute_query = apply_tenant_filter(
                db.query(AssetAttribute),
                user,
                AssetAttribute,
                allow_cross_branch=True,
            ).filter(AssetAttribute.sub_category_id == asset.sub_category_id)

            attribute = None
            if update.attribute_id:
                attribute = attribute_query.filter(AssetAttribute.attribute_id == update.attribute_id).first()
            elif update.attribute_name:
                attribute = attribute_query.filter(AssetAttribute.attribute_name.ilike(update.attribute_name)).first()

            if not attribute:
                target = update.attribute_id or update.attribute_name or "unknown"
                raise ResourceNotFoundError("AssetAttribute", target)

            value_row = (
                db.query(AssetAttributeValue)
                .filter(
                    AssetAttributeValue.asset_id == asset.asset_id,
                    AssetAttributeValue.attribute_id == attribute.attribute_id,
                )
                .with_for_update()
                .first()
            )

            old_value = value_row.value if value_row else None
            new_value = update.new_value
            if old_value == new_value:
                continue

            if value_row:
                value_row.value = new_value
            else:
                value_row = AssetAttributeValue(
                    organization_id=asset.organization_id,
                    branch_id=asset.branch_id,
                    asset_id=asset.asset_id,
                    attribute_id=attribute.attribute_id,
                    value=new_value,
                )
                db.add(value_row)

            db.flush()

            AuditService.log_change(
                db,
                "asset_attribute_values",
                value_row.value_id,
                "UPDATE",
                user,
                {
                    "asset_id": asset.asset_id,
                    "instance_id": instance.instance_id,
                    "attribute_id": attribute.attribute_id,
                    "attribute_name": attribute.attribute_name,
                    "value": old_value,
                },
                {
                    "asset_id": asset.asset_id,
                    "instance_id": instance.instance_id,
                    "attribute_id": attribute.attribute_id,
                    "attribute_name": attribute.attribute_name,
                    "value": new_value,
                },
                resolved_reason,
            )

            lifecycle_event = LifecycleService.log_event(
                db,
                instance_id=instance.instance_id,
                asset_id=asset.asset_id,
                event_type=event_type,
                performed_by=user,
                old_status=instance.status.value if instance.status else None,
                new_status=instance.status.value if instance.status else None,
                notes=resolved_reason,
                organization_id=instance.organization_id,
                metadata={
                    "attribute_id": attribute.attribute_id,
                    "attribute_name": attribute.attribute_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "instance_id": instance.instance_id,
                    "asset_id": asset.asset_id,
                },
            )

            update_results.append(
                AssetAttributeUpdateResult(
                    attribute_id=attribute.attribute_id,
                    attribute_name=attribute.attribute_name,
                    old_value=old_value,
                    new_value=new_value,
                    value_id=value_row.value_id,
                    lifecycle_id=lifecycle_event.lifecycle_id,
                    event_type=event_type.value,
                )
            )

        if not update_results:
            raise InvalidStateError("No attribute values changed")

        return AssetAttributeUpdateResponse(
            instance_id=instance.instance_id,
            asset_id=asset.asset_id,
            event_type=event_type.value,
            reason=resolved_reason,
            updated_count=len(update_results),
            updates=update_results,
        )


