from sqlalchemy.orm import Session
from app.server.schema.asset import Asset
from app.server.schema.tracking import Tracking
from app.server.schema.employee import Employee
from app.server.exceptions.base import InvalidStateError, ResourceNotFoundError
from app.server.services.audit_service import AuditService
from sqlalchemy.sql import func

class AccountService:
    @staticmethod
    def update_procurement(
        db: Session, asset_id: str, cost: float, vendor_name: str, 
        vendor_contact: str, invoice: str, user: Employee, reason: str = "PROCUREMENT_UPDATE"
    ):
        asset=db.query(Asset).filter(Asset.asset_id==asset_id).with_for_update().first()
        if not asset: raise ResourceNotFoundError("Asset", asset_id)
        
        old_val={
            "purchase_cost": asset.purchase_cost,
            "vendor_name": asset.vendor_name,
            "vendor_contact": asset.vendor_contact,
            "invoice_number": asset.invoice_number
        }
        if cost < 0:
            raise InvalidStateError("Purchase cost cannot be negative.")

        asset.purchase_cost=cost
        asset.vendor_name=vendor_name
        asset.vendor_contact=vendor_contact
        asset.invoice_number=invoice
        
        AuditService.log_change(db, "assets", asset_id, "UPDATE", user, old_val, {
            "purchase_cost": cost,
            "vendor_name": vendor_name,
            "vendor_contact": vendor_contact,
            "invoice_number": invoice
        }, reason)
        return asset

    @staticmethod
    def get_asset_tco(db: Session, asset_id: str):
        asset=db.query(Asset).filter(Asset.asset_id==asset_id).first()
        if not asset: raise ResourceNotFoundError("Asset", asset_id)
        purchase_cost=asset.purchase_cost or 0.0
        maintenance_cost=asset.maintenance_total_cost or 0.0
        sub_license_cost=asset.sub_license_cost or 0.0
        return purchase_cost + maintenance_cost + sub_license_cost

    @staticmethod
    def acknowledge_asset(db: Session, tracking_id: str, user: Employee):
        trk=db.query(Tracking).filter(Tracking.tracking_id==tracking_id, Tracking.emp_id==user.employee_id).with_for_update().first()
        if not trk: raise ResourceNotFoundError("Tracking Record", tracking_id)
        if trk.is_acknowledged:
            raise InvalidStateError("This asset handoff has already been acknowledged.")
        
        trk.is_acknowledged=True
        trk.acknowledged_at=func.now()
        
        AuditService.log_change(
            db,
            "tracking",
            tracking_id,
            "UPDATE",
            user,
            {"is_acknowledged": False, "acknowledged_at": None},
            {"is_acknowledged": True, "acknowledged_at": "NOW"},
            "EMPLOYEE_ACK"
        )
        return trk
