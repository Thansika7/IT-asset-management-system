from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.stock import StockAdd, StockResponse, AllocateRequest, ReturnRequest
from app.server.schema.asset import Asset
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.services.stock_service import StockService

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
    asset=StockService.add_stock(db, payload.asset_id, payload.quantity, current_user)
    db.commit()
    db.refresh(asset)
    return asset

@router.post("/allocate")
def allocate_asset(
    payload: AllocateRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    trk=StockService.allocate_asset(db, payload.asset_id, payload.emp_id, payload.allocation_type, current_user, payload.movement_reason)
    db.commit()
    return trk

@router.post("/return")
def return_asset(
    payload: ReturnRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    trk=StockService.return_asset(db, payload.tracking_id, current_user, payload.movement_reason)
    db.commit()
    return {"status": "success", "recovered_asset": trk.asset_id}
