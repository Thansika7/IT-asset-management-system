"""Shared employee offboarding: recover allocated assets and remove the employee row from the database."""

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.server.database.tenant import apply_tenant_filter
from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.request import Request
from app.server.schema.tracking import Tracking
from app.server.services.stock_service import StockService


class EmployeeLifecycleService:
    @staticmethod
    def validate_user_permission(actor: Employee) -> None:
        allowed = {EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN}
        if actor.role not in allowed:
            raise HTTPException(status_code=403, detail="Not authorized to deactivate employees.")

    @staticmethod
    def validate_tenant_scope(target: Employee, actor: Employee) -> None:
        if actor.role == EmployeeRole.SUPER_ADMIN:
            return
        if target.organization_id != actor.organization_id:
            raise HTTPException(status_code=403, detail="Cross-organization deactivation is not allowed.")

    @staticmethod
    def validate_branch_scope(target: Employee, actor: Employee) -> None:
        if actor.role in {EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN}:
            return
        if actor.branch_id and target.branch_id and actor.branch_id != target.branch_id:
            raise HTTPException(status_code=403, detail="Cross-branch deactivation is not allowed.")

    @staticmethod
    def deactivate_and_recover_assets(db: Session, emp_id: str, actor: Employee, movement_reason: str = "OFFBOARDING_RECOVERY") -> dict:
        EmployeeLifecycleService.validate_user_permission(actor)
        target = apply_tenant_filter(db.query(Employee), actor, Employee).filter(Employee.employee_id == emp_id).first()
        if not target:
            raise ResourceNotFoundError("Employee", emp_id)
        EmployeeLifecycleService.validate_tenant_scope(target, actor)
        EmployeeLifecycleService.validate_branch_scope(target, actor)
        if target.role == EmployeeRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="The Global System Administrator cannot be deactivated.")

        active = apply_tenant_filter(db.query(Tracking), actor, Tracking).filter(Tracking.emp_id == emp_id, Tracking.returned_at == None).all()
        for trk in active:
            StockService.return_asset(db, trk.tracking_id, actor, movement_reason)

        for r in apply_tenant_filter(db.query(Request), actor, Request).filter(Request.emp_id == emp_id).all():
            db.delete(r)
        for t in apply_tenant_filter(db.query(Tracking), actor, Tracking).filter(Tracking.emp_id == emp_id).all():
            db.delete(t)
        db.delete(target)

        db.commit()
        return {"status": "deleted", "employee_id": emp_id, "recovered_hardware": len(active)}
