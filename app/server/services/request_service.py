from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee
from app.server.models.request import RequestCreate, RequestTriage, RequestReview

def create_asset_request(db: Session, payload: RequestCreate, current_user: Employee):
    req = Request(
        emp_id=current_user.employee_id,
        asset_name=payload.asset_name,
        asset_category=payload.asset_category,
        reason=payload.reason,
        status="Pending",
        stage="SUPPORT"
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req

def triage_asset_request(db: Session, request_id: str, payload: RequestTriage):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "SUPPORT").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in Support stage")
    
    req.action_type = payload.action_type
    req.status = "WIP"
    req.stage = "MANAGER"
    db.commit()
    db.refresh(req)
    return req

def review_request_by_manager(db: Session, request_id: str, payload: RequestReview):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "MANAGER").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in Manager stage")
    
    if not payload.is_approved:
        req.status = "REJECTED"
        req.stage = "REJECTED"
    else:
        req.status = "WIP"
        req.stage = "HR"
    
    db.commit()
    db.refresh(req)
    return req

def review_request_by_hr(db: Session, request_id: str, payload: RequestReview):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "HR").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in HR stage")
    
    if payload.is_approved:
        req.status = "WIP"
        req.stage = "READY"
    else:
        req.status = "REJECTED"
        req.stage = "REJECTED"
    
    db.commit()
    db.refresh(req)
    return req

def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: str = None):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "READY").first()
    if not req:
        raise HTTPException(status_code=400, detail="Invalid request state or not approved by HR")
    
    if req.action_type in ["NEW", "REPLACE"]:
        asset = db.query(Asset).filter(Asset.asset_id == provided_asset_id).with_for_update().first()
        if not asset or asset.unused <= 0:
            raise HTTPException(status_code=400, detail="Target asset unavailable")
        
        asset.unused -= 1
        asset.used += 1
        if asset.unused == 0:
            asset.asset_status = AssetStatus.ALLOCATED
        
        trk = Tracking(
            asset_id=asset.asset_id, emp_id=req.emp_id, branch=asset.branch,
            movement_type=MovementType.ALLOCATE if req.action_type == "NEW" else MovementType.REPLACE,
            allocation_type=AllocationType.PERMANENT, movement_reason=req.reason
        )
        db.add(trk)
        
        if req.action_type == "REPLACE" and broken_asset_id:
            broken = db.query(Asset).filter(Asset.asset_id == broken_asset_id).with_for_update().first()
            if broken:
                broken.asset_status = AssetStatus.RETIRED
            
    elif req.action_type == "SERVICE":
        broken_trk = db.query(Tracking).filter(Tracking.asset_id == broken_asset_id, Tracking.returned_at == None).with_for_update().first()
        if broken_trk:
            broken = db.query(Asset).filter(Asset.asset_id == broken_asset_id).first()
            broken.asset_status = AssetStatus.IN_REPAIR
            temp_asset = db.query(Asset).filter(Asset.asset_id == provided_asset_id).with_for_update().first()
            if temp_asset and temp_asset.unused > 0:
                temp_asset.unused -= 1
                temp_asset.used += 1
                temp_trk = Tracking(
                    asset_id=temp_asset.asset_id, emp_id=req.emp_id, branch=temp_asset.branch,
                    movement_type=MovementType.REPAIR, allocation_type=AllocationType.TEMPORARY,
                    parent_tracking_id=broken_trk.tracking_id
                )
                db.add(temp_trk)
                
    elif req.action_type == "WARRANTY":
        if broken_asset_id:
            broken = db.query(Asset).filter(Asset.asset_id == broken_asset_id).first()
            if broken:
                broken.asset_status = AssetStatus.WARRANTY
            
    req.status = "Assigned"
    req.stage = "COMPLETED"
    db.commit()
    return {"status": "success", "executed_action": req.action_type}
