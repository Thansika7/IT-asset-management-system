import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.auth.service import get_password_hash
from app.server.database.database import get_db
from app.server.models.api import EmployeeCreate, EmployeeRead
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.tracking import Tracking
from app.server.middlewares.auth import require_roles
from app.server.services.stock_service import StockService
from app.server.exceptions.base import InvalidStateError, ResourceNotFoundError

router=APIRouter(prefix="/employees", tags=["employees"])

@router.post("/register", response_model=EmployeeRead, status_code=201)
def register_employee(
    payload: EmployeeCreate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    existing=db.query(Employee).filter(Employee.email==payload.email).first()
    if existing:
        raise InvalidStateError("The provided email address is already associated with an existing account.")

    raw_password=str(uuid.uuid4())
    user=Employee(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        branch=payload.branch,
        role=payload.role,
        password_hash=get_password_hash(raw_password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    if payload.onboarding_asset_ids:
        from app.server.schema.tracking import AllocationType
        for aid in payload.onboarding_asset_ids:
            try:
                StockService.allocate_asset(db, aid, user.employee_id, AllocationType.PERMANENT, current_user, "ONBOARDING_PACKAGE")
            except Exception:
                pass

    db.commit()
    db.refresh(user)
    user.generated_password=raw_password
    return user

@router.get("/", response_model=List[EmployeeRead])
def list_employees(
    branch: Optional[str]=None,
    role: Optional[EmployeeRole]=None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER))
):
    query=db.query(Employee).filter(Employee.is_active==True)
    if branch:
        query=query.filter(Employee.branch==branch)
    if role:
        query=query.filter(Employee.role==role)
    return query.all()

@router.get("/{emp_id}", response_model=EmployeeRead)
def get_employee(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM))
):
    emp=db.query(Employee).filter(Employee.employee_id==emp_id).first()
    if not emp:
        raise ResourceNotFoundError("Employee", emp_id)
    return emp

@router.post("/{emp_id}/deactivate")
def deactivate_employee(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    target=db.query(Employee).filter(Employee.employee_id==emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    target.is_active=False
    active=db.query(Tracking).filter(Tracking.emp_id==emp_id, Tracking.returned_at==None).all()
    for trk in active:
        StockService.return_asset(db, trk.tracking_id, current_user, "OFFBOARDING_RECOVERY")

    db.commit()
    return {"status": "deactivated", "employee_id": emp_id, "recovered_hardware": len(active)}

@router.get("/{emp_id}/assets")
def get_employee_assets(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE))
):
    if current_user.role==EmployeeRole.EMPLOYEE and current_user.employee_id!=emp_id:
        raise ResourceNotFoundError("Employee", emp_id)
    active=db.query(Tracking).filter(Tracking.emp_id==emp_id, Tracking.returned_at==None).all()
    return {"employee_id": emp_id, "active_assets": [{"tracking_id": t.tracking_id, "asset_id": t.asset_id, "is_acknowledged": t.is_acknowledged} for t in active]}
