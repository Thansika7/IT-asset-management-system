"""Employee resignation workflow (Request rows with request_type=RESIGNATION)."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.server.exceptions.base import ResourceNotFoundError
from app.server.models.request import RequestResponse
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.request import Request
from app.server.services.email_service import EmailService
from app.server.services.employee_lifecycle_service import EmployeeLifecycleService
from app.server.services.request_service import RequestService


class ResignationService:
    STAGE_PENDING = "RESIGNATION_PENDING"

    @staticmethod
    def submit(db: Session, current_user: Employee, reason: str, last_working_day: Optional[str] = None) -> RequestResponse:
        if current_user.role != EmployeeRole.EMPLOYEE:
            raise HTTPException(status_code=403, detail="Only employees may submit resignation requests through this endpoint.")

        pending = (
            db.query(Request)
            .filter(
                Request.emp_id == current_user.employee_id,
                Request.request_type == "RESIGNATION",
                Request.resignation_status == "PENDING",
            )
            .first()
        )
        if pending:
            raise HTTPException(status_code=400, detail="You already have a pending resignation request.")

        extra = f" Last working day: {last_working_day}." if last_working_day else ""
        full_reason = (reason or "").strip() + extra

        req = Request(
            emp_id=current_user.employee_id,
            asset_name="Employee resignation",
            asset_category="HR",
            reason=full_reason.strip() or "Voluntary resignation",
            request_type="RESIGNATION",
            resignation_status="PENDING",
            status="PENDING_RESIGNATION",
            stage=ResignationService.STAGE_PENDING,
            priority="P3",
            severity="MEDIUM",
            urgency="MEDIUM",
            action_type=None,
        )
        db.add(req)
        db.commit()
        db.refresh(req)

        recipients = EmailService.collect_hr_admin_emails(db, branch=current_user.branch)
        EmailService.notify_resignation_request(current_user.name, current_user.email, full_reason, recipients)

        return RequestService._serialize_request(req)

    @staticmethod
    def list_resignations(db: Session, current_user: Employee) -> List[RequestResponse]:
        if current_user.role not in (EmployeeRole.ADMIN, EmployeeRole.HR):
            raise HTTPException(status_code=403, detail="Only HR or Admin can list resignation requests.")

        q = db.query(Request).options(joinedload(Request.employee)).filter(Request.request_type == "RESIGNATION")
        if current_user.role == EmployeeRole.HR:
            q = q.join(Request.employee).filter(Employee.branch == current_user.branch)
        rows = q.order_by(Request.req_date.desc()).all()
        return [RequestService._serialize_request(r) for r in rows]

    @staticmethod
    def approve(db: Session, request_id: str, approver: Employee) -> dict:
        if approver.role not in (EmployeeRole.ADMIN, EmployeeRole.HR):
            raise HTTPException(status_code=403, detail="Only HR or Admin can approve resignations.")

        req = (
            db.query(Request)
            .options(joinedload(Request.employee))
            .filter(Request.request_id == request_id, Request.request_type == "RESIGNATION")
            .with_for_update()
            .first()
        )
        if not req:
            raise ResourceNotFoundError("ResignationRequest", request_id)
        if req.resignation_status != "PENDING":
            raise HTTPException(status_code=400, detail="This resignation request is not pending.")
        if approver.role == EmployeeRole.HR and req.employee and req.employee.branch != approver.branch:
            raise HTTPException(status_code=403, detail="HR can only approve resignations from their own branch.")

        emp_id = req.emp_id
        req.resignation_status = "APPROVED"
        req.status = "COMPLETED"
        req.stage = "COMPLETED"

        off = EmployeeLifecycleService.deactivate_and_recover_assets(db, emp_id, approver, movement_reason="RESIGNATION_APPROVED")
        return {"request_id": request_id, "resignation_status": "APPROVED", **off}

    @staticmethod
    def reject(db: Session, request_id: str, approver: Employee, notes: Optional[str] = None) -> RequestResponse:
        if approver.role not in (EmployeeRole.ADMIN, EmployeeRole.HR):
            raise HTTPException(status_code=403, detail="Only HR or Admin can reject resignations.")

        req = (
            db.query(Request)
            .options(joinedload(Request.employee))
            .filter(Request.request_id == request_id, Request.request_type == "RESIGNATION")
            .with_for_update()
            .first()
        )
        if not req:
            raise ResourceNotFoundError("ResignationRequest", request_id)
        if req.resignation_status != "PENDING":
            raise HTTPException(status_code=400, detail="This resignation request is not pending.")
        if approver.role == EmployeeRole.HR and req.employee and req.employee.branch != approver.branch:
            raise HTTPException(status_code=403, detail="HR can only reject resignations from their own branch.")

        req.resignation_status = "REJECTED"
        req.status = "REJECTED"
        req.stage = "REJECTED"
        if notes:
            req.reason = (req.reason or "") + f" | Rejection notes: {notes.strip()}"
        db.commit()
        db.refresh(req)
        return RequestService._serialize_request(req)
