"""
Deprecated compatibility wrapper for request workflow helpers.

RequestService is the canonical source of truth for lifecycle behavior.
This module keeps helper methods aligned with the current lifecycle states.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.server.schema.request import Request, RequestStatus, RequestType
from app.server.schema.asset import AssetInstance, AssetStatus
from app.server.schema.employee import Employee
from app.server.services.audit_service import AuditService
from app.server.services.stock_service import StockService


class RequestWorkflow:
    """Request lifecycle state machine."""
    
    @staticmethod
    def validate_request_type(request_type: str) -> None:
        """
        Validate that request_type is one of the supported types.
        
        Raises HTTPException if invalid.
        """
        valid_types = {"NEW", "SERVICE", "REPLACE", "RETURN", "TRANSFER"}
        if request_type.upper() not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid request_type '{request_type}'. Must be one of: {', '.join(sorted(valid_types))}"
            )

    @staticmethod
    def validate_instance_requirement(request_type: str, instance_id: str | None) -> None:
        """
        Validate that instance_id is provided when required by request_type.
        
        SERVICE/REPLACE/TRANSFER require instance_id.
        """
        req_type = request_type.upper()
        
        if req_type in {"SERVICE", "REPLACE", "TRANSFER"}:
            if not instance_id or not instance_id.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"request_type '{req_type}' requires instance_id. Cannot proceed without specifying the target instance."
                )

    @staticmethod
    def calculate_sla_due(request_date: datetime, priority: str) -> datetime:
        """
        Calculate SLA due date based on priority.
        
        CRITICAL: 1 hour
        HIGH: 4 hours
        MEDIUM: 24 hours
        LOW: 72 hours
        """
        priority_sla_hours = {
            "CRITICAL": 1,
            "HIGH": 4,
            "MEDIUM": 24,
            "LOW": 72,
        }
        
        hours = priority_sla_hours.get(priority.upper(), 24)
        return request_date + timedelta(hours=hours)

    @staticmethod
    def is_sla_breached(request_date: datetime, priority: str, status: RequestStatus) -> bool:
        """
        Check if SLA has been breached.
        
        SLA only applies to PENDING/TRIAGED/APPROVED/ASSIGNED states.
        COMPLETED/REJECTED/CANCELLED/CLOSED are not SLA-tracked.
        """
        if status in {RequestStatus.COMPLETED, RequestStatus.REJECTED, RequestStatus.CANCELLED, RequestStatus.CLOSED}:
            return False
        
        due_date = RequestWorkflow.calculate_sla_due(request_date, priority)
        now = datetime.now(timezone.utc)
        
        # Normalize timezones
        if request_date.tzinfo is None:
            request_date = request_date.replace(tzinfo=timezone.utc)
        
        return now > due_date

    @staticmethod
    def get_valid_state_transitions(current_status: RequestStatus) -> set[RequestStatus]:
        """
        Get valid next states from current status.
        
        SUBMITTED → HR_VALIDATED, HR_REJECTED, CANCELLED
        HR_VALIDATED → TRIAGED
        TRIAGED → APPROVED, REJECTED
        APPROVED → ASSIGNED, REJECTED, CLOSED
        ASSIGNED → COMPLETED, REJECTED
        HR_REJECTED → (terminal)
        REJECTED → (terminal)
        CANCELLED → (terminal)
        COMPLETED → CLOSED
        CLOSED → (terminal)
        """
        transitions = {
            RequestStatus.SUBMITTED: {RequestStatus.HR_VALIDATED, RequestStatus.HR_REJECTED, RequestStatus.CANCELLED},
            RequestStatus.HR_VALIDATED: {RequestStatus.TRIAGED},
            RequestStatus.TRIAGED: {RequestStatus.APPROVED, RequestStatus.REJECTED},
            RequestStatus.APPROVED: {RequestStatus.ASSIGNED, RequestStatus.REJECTED, RequestStatus.CLOSED},
            RequestStatus.ASSIGNED: {RequestStatus.COMPLETED, RequestStatus.REJECTED},
            RequestStatus.COMPLETED: {RequestStatus.CLOSED},
            RequestStatus.HR_REJECTED: set(),   # Terminal
            RequestStatus.REJECTED: set(),      # Terminal
            RequestStatus.CANCELLED: set(),     # Terminal
            RequestStatus.CLOSED: set(),        # Terminal
        }
        
        return transitions.get(current_status, set())

    @staticmethod
    def can_transition(current_status: RequestStatus, target_status: RequestStatus) -> bool:
        """Check if transition from current to target is valid."""
        valid_next = RequestWorkflow.get_valid_state_transitions(current_status)
        return target_status in valid_next

    @staticmethod
    def reserve_instance_for_request(
        db: Session,
        request: Request,
        instance_id: str,
        user: Employee
    ) -> AssetInstance:
        """
        Reserve an instance for a request during triage.
        
        Transitions instance from AVAILABLE → RESERVED (conceptually).
        Actually, we use a pseudo-status in request state, keeps instance AVAILABLE.
        
        Returns the reserved instance.
        """
        instance = db.query(AssetInstance).filter(
            AssetInstance.instance_id == instance_id
        ).with_for_update().first()
        
        if not instance:
            raise HTTPException(
                status_code=404,
                detail=f"Instance {instance_id} not found"
            )
        
        # Check instance is available for reservation
        if instance.status not in {AssetStatus.AVAILABLE, AssetStatus.NEW}:
            raise HTTPException(
                status_code=400,
                detail=f"Instance {instance_id} is in {instance.status} status. Cannot reserve non-available instances."
            )
        
        # Update request to track reserved instance
        request.instance_id = instance_id
        
        # Log audit entry
        AuditService.log_change(
            db, "asset_instances", instance_id, "RESERVE", user,
            {"reserved_by": None},
            {"reserved_by": request.request_id},
            f"Reserved for request {request.request_id}"
        )
        
        return instance

    @staticmethod
    def release_instance_from_request(
        db: Session,
        request: Request,
        user: Employee
    ) -> None:
        """
        Release a reserved instance (on rejection/cancellation).
        
        Instance returns to AVAILABLE state.
        """
        if not request.instance_id:
            return
        
        instance = db.query(AssetInstance).filter(
            AssetInstance.instance_id == request.instance_id
        ).with_for_update().first()
        
        if instance and instance.status in {AssetStatus.AVAILABLE, AssetStatus.NEW}:
            # No state change needed - instance was never modified
            AuditService.log_change(
                db, "asset_instances", instance.instance_id, "RELEASE", user,
                {"reserved_by": request.request_id},
                {"reserved_by": None},
                f"Released from request {request.request_id} (rejected/cancelled)"
            )

    @staticmethod
    def assign_instance_to_request(
        db: Session,
        request: Request,
        instance_id: str,
        employee_id: str,
        user: Employee
    ) -> AssetInstance:
        """
        Assign a reserved instance to an employee (after approval).
        
        Transitions instance from AVAILABLE → ASSIGNED.
        Updates tracking.
        """
        from app.server.schema.tracking import AllocationType
        
        instance = db.query(AssetInstance).filter(
            AssetInstance.instance_id == instance_id
        ).with_for_update().first()
        
        if not instance:
            raise HTTPException(
                status_code=404,
                detail=f"Instance {instance_id} not found"
            )
        
        # Perform allocation
        StockService.allocate_asset(
            db, instance.asset_id, employee_id,
            AllocationType.PERMANENT,
            user,
            reason=f"Assigned via request {request.request_id}"
        )
        
        return instance

    @staticmethod
    def reject_request(
        db: Session,
        request: Request,
        user: Employee
    ) -> None:
        """
        Reject a request and release any reserved instances.
        
        TRIAGED → REJECTED
        APPROVED → REJECTED
        """
        # Release reserved instance(s)
        RequestWorkflow.release_instance_from_request(db, request, user)
        
        # Update request state
        request.status = RequestStatus.REJECTED
        request.rejected_at = datetime.now(timezone.utc)

    @staticmethod
    def cancel_request(
        db: Session,
        request: Request,
        user: Employee
    ) -> None:
        """
        Cancel a request (user initiated).
        
        PENDING → CANCELLED
        """
        # If already triaged, release instance
        if request.status in {RequestStatus.TRIAGED, RequestStatus.APPROVED}:
            RequestWorkflow.release_instance_from_request(db, request, user)
        
        # Update request state
        request.status = RequestStatus.CANCELLED

    @staticmethod
    def complete_request(
        db: Session,
        request: Request,
        user: Employee
    ) -> None:
        """
        Complete a request (after assignment/resolution).
        
        ASSIGNED → COMPLETED
        """
        request.status = RequestStatus.COMPLETED
        request.completed_at = datetime.now(timezone.utc)
