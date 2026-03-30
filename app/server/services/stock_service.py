from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee
from app.server.exceptions.base import InsufficientStockError, InvalidStateError, ResourceNotFoundError
from app.server.services.audit_service import AuditService

class StockService:
    @staticmethod
    def add_stock(db: Session, asset_id: str, quantity: int, user: Employee, reason: str = "RESTOCK"):
        if quantity <= 0:
            raise InvalidStateError("Stock addition quantity must be greater than zero.")

        asset=db.query(Asset).filter(Asset.asset_id==asset_id).with_for_update().first()
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
        return asset

    @staticmethod
    def allocate_asset(db: Session, asset_id: str, emp_id: str, alloc_type: AllocationType, user: Employee, reason: str = "ALLOCATION"):
        asset=db.query(Asset).filter(Asset.asset_id==asset_id).with_for_update().first()
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
        return trk

    @staticmethod
    def return_asset(db: Session, tracking_id: str, user: Employee, reason: str = "RETURN"):
        trk=db.query(Tracking).filter(Tracking.tracking_id==tracking_id, Tracking.returned_at==None).with_for_update().first()
        if not trk: raise ResourceNotFoundError("Active Tracking Record", tracking_id)
        
        asset=db.query(Asset).filter(Asset.asset_id==trk.asset_id).with_for_update().first()
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
        return trk
