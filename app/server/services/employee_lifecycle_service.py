"""Shared employee offboarding: deactivate account and recover allocated assets."""

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.tracking import Tracking
from app.server.services.stock_service import StockService


class EmployeeLifecycleService:
    @staticmethod
    def deactivate_and_recover_assets(db: Session, emp_id: str, actor: Employee, movement_reason: str = "OFFBOARDING_RECOVERY") -> dict:
        target = db.query(Employee).filter(Employee.employee_id == emp_id).first()
        if not target:
            raise ResourceNotFoundError("Employee", emp_id)
        if target.role == EmployeeRole.ADMIN:
            raise HTTPException(status_code=403, detail="The Global System Administrator cannot be deactivated.")

        target.is_active = False
        active = db.query(Tracking).filter(Tracking.emp_id == emp_id, Tracking.returned_at == None).all()
        for trk in active:
            StockService.return_asset(db, trk.tracking_id, actor, movement_reason)

        db.commit()
        return {"status": "deactivated", "employee_id": emp_id, "recovered_hardware": len(active)}
