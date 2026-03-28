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

router=APIRouter(prefix="/requests", tags=["requests"])

@router.post("/", response_model=RequestResponse)
def create_request(
    payload: RequestCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    req=Request(
        emp_id=current_user.employee_id,
        asset_name=payload.asset_name,
        asset_category=payload.asset_category,
        reason=payload.reason,
        status="PENDING_SUPPORT"
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req

@router.post("/{request_id}/triage", response_model=RequestResponse)
def triage_request(
    request_id: str, 
    payload: RequestTriage, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    req=db.query(Request).filter(Request.request_id==request_id).first()
    if not req: raise HTTPException(status_code=404)
    req.action_type=payload.action_type
    req.status="PENDING_MANAGER"
    db.commit()
    db.refresh(req)
    return req

@router.post("/{request_id}/review/manager", response_model=RequestResponse)
def manager_review(
    request_id: str, 
    payload: RequestReview, 
    branch_context: str, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER, EmployeeRole.ADMIN))
):
    req=db.query(Request).filter(Request.request_id==request_id).first()
    if not req: raise HTTPException(status_code=404)
    if not payload.is_approved:
        req.status="REJECTED"
    else:
        if req.action_type in ["NEW", "REPLACE"]:
            local_stock=db.query(func.sum(Asset.unused)).filter(
                Asset.name==req.asset_name, 
                Asset.branch==branch_context
            ).scalar() or 0
            if local_stock > 0:
                req.status="APPROVED_FOR_SUPPORT"
            else:
                req.status="PENDING_ADMIN"
        else:
            req.status="APPROVED_FOR_SUPPORT"
    db.commit()
    db.refresh(req)
    return req

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
        req.status="APPROVED_FOR_SUPPORT"
    else:
        req.status="REJECTED"
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
    req=db.query(Request).filter(Request.request_id==request_id, Request.status=="APPROVED_FOR_SUPPORT").first()
    if not req: raise HTTPException(status_code=400, detail="Invalid request state")
    
    if req.action_type in ["NEW", "REPLACE"]:
        asset=db.query(Asset).filter(Asset.asset_id==provided_asset_id).with_for_update().first()
        if not asset or asset.unused <= 0: raise HTTPException(status_code=400, detail="Target asset unavailable")
        asset.unused -= 1
        asset.used += 1
        if asset.unused == 0: asset.asset_status=AssetStatus.ALLOCATED
        trk=Tracking(
            asset_id=asset.asset_id, emp_id=req.emp_id, branch=asset.branch,
            movement_type=MovementType.ALLOCATE if req.action_type=="NEW" else MovementType.REPLACE,
            allocation_type=AllocationType.PERMANENT, movement_reason=req.reason
        )
        db.add(trk)
        if req.action_type == "REPLACE" and broken_asset_id:
            broken=db.query(Asset).filter(Asset.asset_id==broken_asset_id).with_for_update().first()
            if broken: broken.asset_status=AssetStatus.RETIRED
            
    elif req.action_type == "SERVICE":
        broken_trk=db.query(Tracking).filter(Tracking.asset_id==broken_asset_id, Tracking.returned_at==None).with_for_update().first()
        if broken_trk:
            broken=db.query(Asset).filter(Asset.asset_id==broken_asset_id).first()
            broken.asset_status=AssetStatus.IN_REPAIR
            temp_asset=db.query(Asset).filter(Asset.asset_id==provided_asset_id).with_for_update().first()
            if temp_asset and temp_asset.unused > 0:
                temp_asset.unused -= 1
                temp_asset.used += 1
                temp_trk=Tracking(
                    asset_id=temp_asset.asset_id, emp_id=req.emp_id, branch=temp_asset.branch,
                    movement_type=MovementType.REPAIR, allocation_type=AllocationType.TEMPORARY,
                    parent_tracking_id=broken_trk.tracking_id
                )
                db.add(temp_trk)
                
    elif req.action_type == "WARRANTY":
        if broken_asset_id:
            broken=db.query(Asset).filter(Asset.asset_id==broken_asset_id).first()
            if broken: broken.asset_status=AssetStatus.WARRANTY
            
    req.status="COMPLETED"
    db.commit()
    return {"status": "success", "executed_action": req.action_type}
