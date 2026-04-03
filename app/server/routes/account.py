from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from app.server.database.database import get_db
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.services.account_service import AccountService
from app.server.models.account import ProcurementUpdate, MaintenanceLog, FinancialSummary

router=APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("/procure")
def record_procurement(
    payload: ProcurementUpdate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR))
):
    asset=AccountService.update_procurement(
        db, payload.asset_id, payload.cost, payload.vendor_name,
        payload.vendor_contact, payload.invoice_number, current_user, payload.reason
    )
    db.commit()
    return {"status": "success", "asset_id": asset.asset_id, "new_total_cost": asset.purchase_cost}

@router.post("/maintenance")
def log_maintenance(
    payload: MaintenanceLog,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    asset=AccountService.add_maintenance_cost(db, payload.asset_id, payload.cost, current_user, payload.reason)
    db.commit()
    return {"status": "success", "asset_id": asset.asset_id, "new_maintenance_total": asset.maintenance_total_cost}

@router.get("/summary", response_model=FinancialSummary)
def get_financial_summary(
    branch: Optional[str] = None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER))
):
    effective_branch = branch
    if current_user.role == EmployeeRole.MANAGER:
        effective_branch = current_user.branch
    return AccountService.get_financial_dashboard(db, effective_branch)

@router.get("/tco/{asset_id}")
def get_asset_tco(
    asset_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM))
):
    tco=AccountService.get_asset_tco(db, asset_id)
    return {"asset_id": asset_id, "total_cost_of_ownership": tco}

@router.post("/acknowledge/{tracking_id}")
def acknowledge_receipt(
    tracking_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.EMPLOYEE, EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM))
):
    trk=AccountService.acknowledge_asset(db, tracking_id, current_user)
    db.commit()
    return {"status": "acknowledged", "at": trk.acknowledged_at}
