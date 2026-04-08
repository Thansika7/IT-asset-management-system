"""Shared employee offboarding: recover allocated assets and remove the employee row from the database."""

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.request import Request
from app.server.schema.tracking import Tracking
from app.server.services.stock_service import StockService


class EmployeeLifecycleService:
    @staticmethod
    def deactivate_and_recover_assets(db: Session, emp_id: str, actor: Employee, movement_reason: str = "OFFBOARDING_RECOVERY") -> dict:
        target = db.query(Employee).filter(Employee.employee_id == emp_id).first()
        if not target:
            raise ResourceNotFoundError("Employee", emp_id)
        if target.role == EmployeeRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="The Global System Administrator cannot be deactivated.")

        active = db.query(Tracking).filter(Tracking.emp_id == emp_id, Tracking.returned_at == None).all()
        for trk in active:
            StockService.return_asset(db, trk.tracking_id, actor, movement_reason)

        for r in db.query(Request).filter(Request.emp_id == emp_id).all():
            db.delete(r)
        for t in db.query(Tracking).filter(Tracking.emp_id == emp_id).all():
            db.delete(t)
        db.delete(target)

        db.commit()
        return {"status": "deleted", "employee_id": emp_id, "recovered_hardware": len(active)}
