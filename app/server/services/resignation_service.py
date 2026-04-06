from typing import Optional

from sqlalchemy.orm import Session

from app.server.exceptions.base import InvalidStateError
from app.server.models.request import RequestResponse
from app.server.schema.employee import Employee
from app.server.schema.request import Request
from app.server.services.audit_service import AuditService


class ResignationService:
    @staticmethod
    def submit(db: Session, user: Employee, reason: str, last_working_day: Optional[str] = None):
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidStateError("Resignation reason must not be blank.")

        payload_reason = reason.strip()
        if last_working_day:
            payload_reason = f"{payload_reason} (Last working day: {last_working_day.strip()})"

        resignation_request = Request(
            emp_id=user.employee_id,
            asset_name="Resignation request",
            asset_category="Resignation",
            reason=payload_reason,
            request_type="RESIGNATION",
            status="PENDING_SUPPORT",
            stage="HR_VERIFICATION",
            action_type=None,
            priority="P3",
            severity="MEDIUM",
            urgency="MEDIUM",
            resignation_status="PENDING",
        )

        db.add(resignation_request)
        db.commit()
        db.refresh(resignation_request)

        AuditService.log_change(
            db,
            "requests",
            resignation_request.request_id,
            "CREATE",
            user,
            None,
            {
                "status": resignation_request.status,
                "stage": resignation_request.stage,
                "request_type": resignation_request.request_type,
                "resignation_status": resignation_request.resignation_status,
            },
            "RESIGNATION_SUBMISSION",
        )

        return RequestResponse.model_validate(resignation_request)
