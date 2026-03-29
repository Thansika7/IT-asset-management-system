from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee
from app.server.models.request import RequestCreate, RequestTriage, RequestReview

def get_inventory_across_branches(db: Session, category_name: str):
    from app.server.schema.category import Category
    query = db.query(
        Asset.branch,
        func.sum(Asset.unused).label("available_quantity")
    ).join(Category).filter(Category.category_name == category_name)
    
    return query.group_by(Asset.branch).all()

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
    
    # Check if asset is available in the current branch
    from app.server.schema.category import Category
    local_stock = db.query(func.sum(Asset.unused)).join(Category).filter(
        Asset.branch == req.employee.branch,
        Category.category_name == req.asset_category
    ).scalar() or 0
    
    if local_stock > 0:
        req.status = f"Fulfillment: {req.employee.branch}"
    else:
        # Check other branches
        other_stocks = get_inventory_across_branches(db, req.asset_category)
        if not other_stocks:
            raise HTTPException(status_code=400, detail="Asset not available in any branch")
        
        if ":" in payload.action_type:
            action, target = payload.action_type.split(":", 1)
            req.action_type = action
            req.status = f"Transfer from: {target}"
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail={
                    "message": "Local stock unavailable. Please use action_type 'TRANSFER:BranchName' to select a branch.",
                    "available_branches": [{"branch": s.branch, "quantity": s.available_quantity} for s in other_stocks]
                }
            )
    
    if not req.action_type: req.action_type = payload.action_type
    req.stage = "HR_VERIFICATION"
    db.commit()
    db.refresh(req)
    return req

def review_request_by_hr(db: Session, request_id: str, payload: RequestReview):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "HR_VERIFICATION").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in HR stage")
    
    if payload.is_approved:
        req.stage = "MANAGER_APPROVAL"
    else:
        req.status = "REJECTED BY HR"
        req.stage = "REJECTED"
    
    db.commit()
    db.refresh(req)
    return req

def review_request_by_manager(db: Session, request_id: str, payload: RequestReview):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "MANAGER_APPROVAL").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in Manager stage")
    
    if payload.is_approved:
        req.stage = "READY"
    else:
        req.status = "REJECTED BY MANAGER"
        req.stage = "REJECTED"
    
    db.commit()
    db.refresh(req)
    return req

def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: str = None):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "READY").first()
    if not req:
        raise HTTPException(status_code=400, detail="Invalid request state or not approved by Manager")
    
    # Parse target branch from status
    target_branch = req.employee.branch
    if "Transfer from: " in req.status:
        target_branch = req.status.replace("Transfer from: ", "")
    
    asset = db.query(Asset).filter(
        Asset.asset_id == provided_asset_id,
        Asset.branch == target_branch
    ).with_for_update().first()
    
    if not asset or asset.unused <= 0:
        raise HTTPException(status_code=400, detail=f"Target asset unavailable in branch {target_branch}")
    
    if req.action_type in ["NEW", "REPLACE", "TRANSFER"]:
        asset.unused -= 1
        asset.used += 1
        if asset.unused == 0:
            asset.asset_status = AssetStatus.ALLOCATED
        
        source_branch = req.employee.branch
        trk = Tracking(
            asset_id=asset.asset_id, emp_id=req.emp_id, branch=source_branch,
            from_branch=target_branch if target_branch != source_branch else None,
            to_branch=source_branch if target_branch != source_branch else None,
            movement_type=MovementType.ALLOCATE if req.action_type == "NEW" else MovementType.REPLACE,
            allocation_type=AllocationType.PERMANENT, movement_reason=req.reason
        )
        if target_branch != source_branch:
            asset.branch = source_branch
            
        db.add(trk)
        
        if req.action_type == "REPLACE" and broken_asset_id:
            broken = db.query(Asset).filter(Asset.asset_id == broken_asset_id).with_for_update().first()
            if broken:
                broken.asset_status = AssetStatus.RETIRED
            
    req.status = "Assigned"
    req.stage = "COMPLETED"
    db.commit()
    db.refresh(req)
    return {"status": "success", "executed_action": req.action_type}
