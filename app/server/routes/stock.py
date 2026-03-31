from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.stock import AssetCreate, StockAdd, StockResponse, AllocateRequest, ReturnRequest
from app.server.schema.asset import Asset
from app.server.schema.category import Category
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.services.stock_service import StockService

# Tagging as internal/manual-override to prioritize the automated Request lifecycle
router=APIRouter(prefix="/stock", tags=["stock_inventory_manual"])

@router.get("/", response_model=List[StockResponse])
def list_inventory_status(
    branch_name: Optional[str]=None, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM))
):
    """View full inventory snapshot across branches."""
    query=db.query(Asset)
    if branch_name:
        query=query.filter(Asset.branch==branch_name)
    return query.all()

@router.post("/", response_model=StockResponse, status_code=201)
def create_asset_entry(
    payload: AssetCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """Register a new hardware item in the system's catalog."""
    cat=db.query(Category).filter(Category.category_name==payload.category_name).first()
    if not cat:
        cat=Category(category_name=payload.category_name)
        db.add(cat)
        db.flush()

    asset=Asset(
        asset_id=payload.asset_id,
        name=payload.name,
        category_id=cat.category_id,
        branch=payload.branch,
        total_quantity=payload.total_quantity,
        unused=payload.unused,
        used=0
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset

@router.post("/add", response_model=StockResponse)
def add_new_stock(
    payload: StockAdd, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """Restock an asset and optionally record procurement data."""
    asset=StockService.add_stock(
        db, payload.asset_id, payload.quantity, current_user,
        cost=payload.cost, vendor_name=payload.vendor_name,
        vendor_contact=payload.vendor_contact, invoice_number=payload.invoice_number
    )
    db.commit()
    db.refresh(asset)
    return asset

@router.post("/allocate_manual_override")
def manual_allocate(
    payload: AllocateRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN))
):
    """Emergency manual allocation (Bypasses Request workflow)."""
    trk=StockService.allocate_asset(db, payload.asset_id, payload.emp_id, payload.allocation_type, current_user, payload.movement_reason)
    db.commit()
    return trk

@router.post("/return_manual_override")
def manual_return(
    payload: ReturnRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN))
):
    """Emergency manual return (Bypasses Request workflow)."""
    trk=StockService.return_asset(db, payload.tracking_id, current_user, payload.movement_reason)
    db.commit()
    return {"status": "success", "recovered_asset": trk.asset_id}
