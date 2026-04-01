import uuid
from fastapi import APIRouter, Depends, HTTPException
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
from app.server.schema.onboarding_preset import OnboardingPreset

router=APIRouter(prefix="/employees", tags=["employees"])

@router.post("/register", response_model=EmployeeRead, status_code=201)
def register_employee(
    payload: EmployeeCreate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    email_lower=payload.email.lower()
    existing=db.query(Employee).filter(Employee.email==email_lower).first()
    if existing:
        raise InvalidStateError("The provided email address is already associated with an existing account.")
        
    if payload.phone:
        existing_phone = db.query(Employee).filter(Employee.phone == payload.phone).first()
        if existing_phone:
            raise InvalidStateError("The provided phone number is already associated with an existing account.")

    # Role Population Constraints
    # 1. Global Admin Limit
    if payload.role == EmployeeRole.ADMIN:
        admin_count = db.query(Employee).filter(Employee.role == EmployeeRole.ADMIN, Employee.is_active == True).count()
        if admin_count >= 1:
            raise HTTPException(status_code=400, detail="A Global System Administrator already exists. Only 1 Admin is allowed.")

    # 2. Branch-specific limits
    if payload.role in [EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR]:
        current_count = db.query(Employee).filter(
            Employee.branch == payload.branch,
            Employee.role == payload.role,
            Employee.is_active == True
        ).count()
        
        if payload.role == EmployeeRole.MANAGER and current_count >= 1:
            raise HTTPException(status_code=400, detail=f"Branch '{payload.branch}' already has a Manager. Only 1 is allowed per branch.")
        if payload.role == EmployeeRole.SUPPORT_TEAM and current_count >= 5:
            raise HTTPException(status_code=400, detail=f"Branch '{payload.branch}' already has a Support Team member. Only 1 is allowed per branch.")
        if payload.role == EmployeeRole.HR and current_count >= 3:
            raise HTTPException(status_code=400, detail=f"Branch '{payload.branch}' already has 3 HR members. Only 3 are allowed per branch.")

    # Enforcement: Singleton Manager per Branch
    if payload.role == EmployeeRole.MANAGER:
        existing_manager = db.query(Employee).filter(
            Employee.branch == payload.branch,
            Employee.role == EmployeeRole.MANAGER,
            Employee.is_active == True
        ).first()
        if existing_manager:
            raise InvalidStateError(f"A manager already exists for branch: {payload.branch or 'General'}")

    user=Employee(
        name=payload.name,
        email=email_lower,
        phone=payload.phone,
        branch=payload.branch,
        role=payload.role,
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    asset_ids = list(payload.onboarding_asset_ids)
    if payload.preset_id:
        pid = payload.preset_id.strip()
        preset = db.query(OnboardingPreset).filter(OnboardingPreset.preset_id == pid).first()
        if not preset:
            raise ResourceNotFoundError("OnboardingPreset", pid)
        if preset.target_role and preset.target_role != payload.role.value:
            raise InvalidStateError(
                f"This onboarding kit is for role '{preset.target_role}'. New employee role is '{payload.role.value}'."
            )
        if preset.branch:
            emp_branch = (payload.branch or "").strip() or None
            if emp_branch != preset.branch.strip():
                raise InvalidStateError(
                    f"This kit is for branch '{preset.branch}'. Set the new employee's branch to match (or use another kit)."
                )
        merged = []
        seen = set()
        for aid in preset.get_asset_ids() + asset_ids:
            if aid and aid not in seen:
                seen.add(aid)
                merged.append(aid)
        asset_ids = merged

    if asset_ids:
        from app.server.schema.tracking import AllocationType

        for aid in asset_ids:
            try:
                StockService.allocate_asset(db, aid, user.employee_id, AllocationType.PERMANENT, current_user, "ONBOARDING_PACKAGE")
            except Exception:
                pass

    db.commit()
    db.refresh(user)
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

    if target.role == EmployeeRole.ADMIN:
        raise HTTPException(status_code=403, detail="The Global System Administrator is a singleton and cannot be deactivated.")

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
    
    result = []
    for t in active:
        asset_info = None
        if t.asset:
            asset_info = {
                "name": t.asset.name,
                "brand": t.asset.brand,
                "category": t.asset.category.category_name if getattr(t.asset, "category", None) else None,
                "status": t.asset.asset_status.value if t.asset.asset_status else None
            }
        result.append({
            "tracking_id": t.tracking_id,
            "asset_id": t.asset_id,
            "is_acknowledged": t.is_acknowledged,
            "assigned_date": t.assigned_date.isoformat() if t.assigned_date else None,
            "allocation_type": t.allocation_type.value if t.allocation_type else "PERMANENT",
            "asset": asset_info
        })
        
    return {"employee_id": emp_id, "active_assets": result}
