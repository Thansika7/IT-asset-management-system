from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.request import RequestCreate, RequestTriage, RequestReview, RequestResolve, RequestResponse
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.services.request_service import RequestService

router=APIRouter(prefix="/requests", tags=["requests"])

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

@router.post("/{request_id}/review/manager", response_model=RequestResponse)
def manager_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER, EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_manager(db, request_id, payload, current_user)

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

@router.post("/{request_id}/review/admin", response_model=RequestResponse)
def admin_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_admin(db, request_id, payload, current_user)
def resolve_request(
    request_id: str,
    payload: RequestResolve,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    req=RequestService.resolve_service_request(db, request_id, payload, current_user)
    return {"status": "resolved", "final_action": "REPAIRED_AND_RETURNED", "new_status": req.status}
