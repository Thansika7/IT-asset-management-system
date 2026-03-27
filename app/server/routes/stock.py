from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.stock import StockAdd, StockResponse, AllocateRequest, ReturnRequest
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import require_roles

router=APIRouter(prefix="/stock", tags=["stock"])

@router.get("/", response_model=List[StockResponse])
def get_all_stock(
    branch_name: Optional[str]=None, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM))
):
    query=db.query(Asset)
    if branch_name:
        query=query.filter(Asset.branch==branch_name)
    return query.all()

@router.post("/add", response_model=StockResponse)
def add_stock(
    payload: StockAdd, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity to add must be greater than 0")
    asset=db.query(Asset).filter(Asset.asset_id==payload.asset_id).with_for_update().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.total_quantity += payload.quantity
    asset.unused += payload.quantity
    db.commit()
    db.refresh(asset)
    return asset

@router.post("/allocate")
def allocate_asset(
    payload: AllocateRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    asset=db.query(Asset).filter(Asset.asset_id==payload.asset_id).with_for_update().first()
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    if asset.unused <= 0: raise HTTPException(status_code=400, detail="Insufficient localized stock")
    asset.unused -= 1
    asset.used += 1
    if asset.unused == 0: asset.asset_status=AssetStatus.ALLOCATED
    tracking=Tracking(
        asset_id=asset.asset_id, emp_id=payload.emp_id, branch=asset.branch,
        movement_type=MovementType.ALLOCATE, allocation_type=payload.allocation_type,
        movement_reason=payload.movement_reason, parent_tracking_id=payload.parent_tracking_id
    )
    db.add(tracking)
    db.commit()
    db.refresh(tracking)
    return tracking

@router.post("/return")
def return_asset(
    payload: ReturnRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    tracking=db.query(Tracking).filter(Tracking.tracking_id==payload.tracking_id, Tracking.returned_at==None).with_for_update().first()
    if not tracking: raise HTTPException(status_code=404, detail="Active unresolved explicit tracking record not found")
    asset=db.query(Asset).filter(Asset.asset_id==tracking.asset_id).with_for_update().first()
    tracking.returned_at=func.now()
    return_record=Tracking(
        asset_id=asset.asset_id, emp_id=tracking.emp_id, branch=asset.branch,
        movement_type=MovementType.RETURN, movement_reason=payload.movement_reason,
        allocation_type=tracking.allocation_type, parent_tracking_id=tracking.parent_tracking_id
    )
    db.add(return_record)
    asset.used -= 1
    asset.unused += 1
    asset.asset_status=AssetStatus.ACTIVE
    db.commit()
    return {"status": "success", "recovered_asset": asset.asset_id}
