from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List

from app.server.database.database import get_db
from app.server.models.request import RequestCreate, RequestTriage, RequestReview, RequestResponse
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import get_current_user
from app.server.middlewares.auth import require_roles
from app.server.services import request_service

router=APIRouter(prefix="/requests", tags=["requests"])

@router.get("/", response_model=List[RequestResponse])
def list_requests(
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    if current_user.role in [EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR, EmployeeRole.MANAGER]:
        return db.query(Request).all()
    return db.query(Request).filter(Request.emp_id == current_user.employee_id).all()

@router.post("/", response_model=RequestResponse)
def create_request(
    payload: RequestCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    return request_service.create_asset_request(db, payload, current_user)

@router.post("/{request_id}/triage", response_model=RequestResponse)
def triage_request(
    request_id: str, 
    payload: RequestTriage, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    return request_service.triage_asset_request(db, request_id, payload)

@router.post("/{request_id}/review/manager", response_model=RequestResponse)
def manager_review(
    request_id: str, 
    payload: RequestReview, 
    branch_context: str, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER, EmployeeRole.ADMIN))
):
    return request_service.review_request_by_manager(db, request_id, payload)

@router.post("/{request_id}/review/hr", response_model=RequestResponse)
def hr_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    return request_service.review_request_by_hr(db, request_id, payload)

@router.post("/{request_id}/review/admin", response_model=RequestResponse)
def admin_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN))
):

    req=db.query(Request).filter(Request.request_id==request_id).first()
    if not req: raise HTTPException(status_code=404)
    if payload.is_approved:
        req.status="WIP"
        req.stage="READY" 
    else:
        req.status="REJECTED"
        req.stage="REJECTED"
    db.commit()
    db.refresh(req)
    return req

@router.post("/{request_id}/execute")
def execute_request(
    request_id: str, 
    provided_asset_id: str, 
    broken_asset_id: str=None, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    return request_service.execute_asset_request(db, request_id, provided_asset_id, broken_asset_id)
