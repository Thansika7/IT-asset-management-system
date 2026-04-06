from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.request import RequestCreate, RequestTriage, RequestReview, RequestResolve, RequestResponse, RequestHRVerify, RequestCrossBranchTransfer, RequestFormOptions
from app.server.schema.request import Request
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.auth.service import get_current_user
from app.server.services.request_service import RequestService

router=APIRouter(prefix="/requests", tags=["requests"])


@router.get("/form-options", response_model=RequestFormOptions)
def get_request_form_options(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return RequestService.get_request_form_options(db, current_user)

@router.get("/", response_model=List[RequestResponse])
def list_requests(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    severity: Optional[str] = None,
    urgency: Optional[str] = None,
    branch: Optional[str] = None,
    request_type: Optional[str] = None,
    sort_by_priority: bool = False,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    return RequestService.list_requests(
        db,
        current_user,
        status=status,
        priority=priority,
        severity=severity,
        urgency=urgency,
        branch=branch,
        sort_by_priority=sort_by_priority,
        request_type=request_type,
    )

@router.post("/", response_model=RequestResponse)
def create_request(
    payload: RequestCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.EMPLOYEE, EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM))
):
    return RequestService.create_asset_request(db, payload, current_user)

@router.post("/{request_id}/triage", response_model=RequestResponse)
def triage_request(
    request_id: str, 
    payload: RequestTriage, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    return RequestService.triage_asset_request(db, request_id, payload, current_user)

@router.post("/{request_id}/review/hr", response_model=RequestResponse)
def hr_review(
    request_id: str, 
    payload: RequestHRVerify, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_hr(db, request_id, payload, current_user)

@router.post("/{request_id}/review/manager", response_model=RequestResponse)
def manager_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER, EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_manager(db, request_id, payload, current_user)

@router.post("/{request_id}/review/admin", response_model=RequestResponse)
def admin_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_admin(db, request_id, payload, current_user)

@router.post("/{request_id}/execute")
def execute_request(
    request_id: str, 
    provided_asset_id: Optional[str] = None, 
    broken_asset_id: Optional[str] = None, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    req=RequestService.execute_asset_request(db, request_id, provided_asset_id, broken_asset_id, current_user)
    return {"status": "success", "executed_action": req.action_type, "new_status": req.status}

@router.post("/{request_id}/transfer-request", response_model=RequestResponse)
def transfer_request(
    request_id: str, 
    payload: RequestCrossBranchTransfer, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER))
):
    return RequestService.request_cross_branch_transfer(db, request_id, payload, current_user)

@router.post("/{request_id}/resolve")
def resolve_request(
    request_id: str,
    payload: RequestResolve,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    req=RequestService.resolve_service_request(db, request_id, payload, current_user)
    return {"status": "resolved", "final_action": "REPAIRED_AND_RETURNED", "new_status": req.status}
