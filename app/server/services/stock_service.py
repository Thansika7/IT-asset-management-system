from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee
from app.server.exceptions.base import InsufficientStockError, InvalidStateError, ResourceNotFoundError
from app.server.services.audit_service import AuditService
from app.server.database.tenant import apply_tenant_filter

class StockService:
    @staticmethod
    def add_stock(
        db: Session, asset_id: str, quantity: int, user: Employee, 
        reason: str = "RESTOCK",
        cost: float | None = None,
        vendor_name: str | None = None,
        vendor_contact: str | None = None,
        invoice_number: str | None = None
    ):
        if quantity <= 0:
            raise InvalidStateError("Stock addition quantity must be greater than zero.")

        asset=apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id==asset_id).with_for_update().first()
        if not asset: raise ResourceNotFoundError("Asset", asset_id)
        
        old_val={
            "total_quantity": asset.total_quantity,
            "unused": asset.unused,
            "asset_status": asset.asset_status.value
        }
        asset.total_quantity += quantity
        asset.unused += quantity
        if asset.asset_status == AssetStatus.ALLOCATED and asset.unused > 0:
            asset.asset_status=AssetStatus.ACTIVE
        new_val={
            "total_quantity": asset.total_quantity,
            "unused": asset.unused,
            "asset_status": asset.asset_status.value
        }
        
        AuditService.log_change(db, "assets", asset_id, "UPDATE", user, old_val, new_val, reason)

        # Integration: Record procurement if financial data provided
        if cost is not None:
            from app.server.services.account_service import AccountService
            AccountService.update_procurement(
                db, asset_id, cost, vendor_name, vendor_contact, invoice_number, user, "PROCUREMENT_VIA_STOCK_ADD"
            )

        return asset

    @staticmethod
    def allocate_asset(db: Session, asset_id: str, emp_id: str, alloc_type: AllocationType, user: Employee, reason: str = "ALLOCATION"):
        asset=apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id==asset_id).with_for_update().first()
        if not asset: raise ResourceNotFoundError("Asset", asset_id)
        if asset.unused <= 0: raise InsufficientStockError(asset.name, 0)

        old_asset_val={
            "unused": asset.unused,
            "used": asset.used,
            "asset_status": asset.asset_status.value
        }
        asset.unused -= 1
        asset.used += 1
        if asset.unused == 0: asset.asset_status=AssetStatus.ALLOCATED
        new_asset_val={
            "unused": asset.unused,
            "used": asset.used,
            "asset_status": asset.asset_status.value
        }
        AuditService.log_change(db, "assets", asset_id, "UPDATE", user, old_asset_val, new_asset_val, reason)

        trk=Tracking(
            asset_id=asset_id, emp_id=emp_id, branch=asset.branch,
            organization_id=asset.organization_id, branch_id=asset.branch_id,
            movement_type=MovementType.ALLOCATE, allocation_type=alloc_type,
            movement_reason=reason
        )
        db.add(trk)
        db.flush() # Get the tracking ID
        AuditService.log_change(
            db,
            "tracking",
            trk.tracking_id,
            "CREATE",
            user,
            None,
            {
                "tracking_id": trk.tracking_id,
                "asset_id": trk.asset_id,
                "emp_id": trk.emp_id,
                "branch": trk.branch,
                "movement_type": trk.movement_type.value,
                "allocation_type": trk.allocation_type.value,
                "movement_reason": trk.movement_reason,
                "is_acknowledged": trk.is_acknowledged
            },
            reason
        )
        # Low stock alert fires whenever inventory is at or below threshold and
        # the allocation moved stock further into the low-stock zone.
        actual_threshold = asset.low_stock_threshold if asset.low_stock_threshold else 10
        previous_unused = old_asset_val["unused"]
        normalized_branch = (asset.branch or "").strip()
        is_low_stock_now = asset.unused <= actual_threshold
        moved_deeper_into_low_stock = previous_unused > actual_threshold or asset.unused < previous_unused

        if normalized_branch and is_low_stock_now and moved_deeper_into_low_stock:
            from app.server.services.email_service import EmailService
            from app.server.schema.employee import EmployeeRole
            support_emails = [
                e.email for e in db.query(Employee).filter(
                    Employee.organization_id == user.organization_id,
                    func.lower(func.trim(Employee.branch)) == normalized_branch.lower(),
                    Employee.role == EmployeeRole.SUPPORT_TEAM,
                    Employee.is_active == True,
                ).all() if e.email
            ]
            manager_emails = [
                e.email for e in db.query(Employee).filter(
                    Employee.organization_id == user.organization_id,
                    func.lower(func.trim(Employee.branch)) == normalized_branch.lower(),
                    Employee.role == EmployeeRole.MANAGER,
                    Employee.is_active == True,
                ).all() if e.email
            ]
            recipients = list(set(support_emails + manager_emails))
            if not recipients:
                recipients = EmailService.collect_hr_admin_emails(db, normalized_branch)

            if recipients:
                EmailService.notify_low_stock(
                    asset_name=asset.name,
                    asset_id=asset.asset_id,
                    branch=normalized_branch,
                    unused=asset.unused,
                    threshold=actual_threshold,
                    recipients=recipients,
                )

        return trk

    @staticmethod
    def return_asset(db: Session, tracking_id: str, user: Employee, reason: str = "RETURN"):
        trk=apply_tenant_filter(db.query(Tracking), user, Tracking).filter(Tracking.tracking_id==tracking_id, Tracking.returned_at==None).with_for_update().first()
        if not trk: raise ResourceNotFoundError("Active Tracking Record", tracking_id)
        
        asset=apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id==trk.asset_id).with_for_update().first()
        old_asset_val={
            "unused": asset.unused,
            "used": asset.used,
            "asset_status": asset.asset_status.value
        }
        asset.unused += 1
        asset.used -= 1
        asset.asset_status=AssetStatus.ACTIVE
        new_asset_val={
            "unused": asset.unused,
            "used": asset.used,
            "asset_status": asset.asset_status.value
        }
        
        trk.returned_at=func.now()
        AuditService.log_change(db, "assets", asset.asset_id, "UPDATE", user, old_asset_val, new_asset_val, reason)
        AuditService.log_change(
            db,
            "tracking",
            trk.tracking_id,
            "UPDATE",
            user,
            {"returned_at": None},
            {"returned_at": "NOW", "asset_id": trk.asset_id},
            reason
        )
        from app.server.services.request_service import RequestService

        RequestService.try_auto_allocate_for_asset(db, asset.asset_id, user, "AUTO_RETURN_REALLOCATION")
        return trk

