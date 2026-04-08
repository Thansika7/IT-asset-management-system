from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.auth.service import get_password_hash, get_default_permission_flags
from app.server.database.database import get_db
from app.server.models.api import EmployeeCreate, EmployeeRead, EmployeePermissionUpdate, EmployeePermissionRead
from app.server.services.email_service import EmailService
from app.server.services.provisioning_service import generate_company_email, generate_temp_password
from app.server.services.employee_lifecycle_service import EmployeeLifecycleService
from app.server.database.tenant import apply_tenant_filter
from app.server.schema.employee import Employee, EmployeeRole, EmployeePermission
from app.server.schema.organization import Organization, Branch
from app.server.schema.tracking import Tracking
from app.server.middlewares.auth import require_roles
from app.server.services.stock_service import StockService
from app.server.exceptions.base import InvalidStateError, ResourceNotFoundError

router=APIRouter(prefix="/employees", tags=["employees"])


@router.post("/register", response_model=EmployeeRead, status_code=201)
def register_employee(
    payload: EmployeeCreate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    if payload.password:
        email_lower = payload.email.lower()
        existing = db.query(Employee).filter(Employee.email == email_lower).first()
        if existing:
            raise InvalidStateError("The provided company email is already associated with an existing account.")
    else:
        email_lower = None

    if payload.phone:
        existing_phone = db.query(Employee).filter(Employee.phone == payload.phone).first()
        if existing_phone:
            raise InvalidStateError("The provided phone number is already associated with an existing account.")

    if payload.personal_email:
        pe = payload.personal_email.strip().lower()
        taken = db.query(Employee).filter(Employee.personal_email == pe).first()
        if taken:
            raise InvalidStateError("The provided personal email is already associated with an existing account.")

    if current_user.role == EmployeeRole.SUPER_ADMIN:
        resolved_organization_id = payload.organization_id or current_user.organization_id
    else:
        resolved_organization_id = current_user.organization_id
    if not resolved_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required (set on your account or provide it as a super admin).",
        )

    resolved_branch_id = payload.branch_id
    if resolved_branch_id:
        branch_obj = db.query(Branch).filter(Branch.branch_id == resolved_branch_id).first()
        if not branch_obj:
            raise HTTPException(status_code=400, detail="Invalid branch_id")
        if branch_obj.organization_id != resolved_organization_id:
            raise HTTPException(status_code=400, detail="branch_id does not belong to the selected organization")
    if current_user.role == EmployeeRole.HR:
        if current_user.branch_id and resolved_branch_id and resolved_branch_id != current_user.branch_id:
            raise HTTPException(status_code=403, detail="HR can register employees only in their own branch")
        if current_user.branch_id and not resolved_branch_id:
            resolved_branch_id = current_user.branch_id

    # Role Population Constraints
    # 1. Global Admin Limit
    if payload.role == EmployeeRole.SUPER_ADMIN:
        admin_count = db.query(Employee).filter(Employee.role == EmployeeRole.SUPER_ADMIN, Employee.is_active == True).count()
        if admin_count >= 1:
            raise HTTPException(status_code=400, detail="A Global System Administrator already exists. Only 1 Admin is allowed.")

    # 2. Branch-specific limits
    if payload.role in [EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR]:
        if not resolved_branch_id:
            raise HTTPException(status_code=400, detail="branch_id is required for manager/hr/support_team roles")
        current_count = db.query(Employee).filter(
            Employee.branch_id == resolved_branch_id,
            Employee.role == payload.role,
            Employee.is_active == True
        ).count()
        
        if payload.role == EmployeeRole.MANAGER and current_count >= 1:
            raise HTTPException(status_code=400, detail=f"Branch already has a Manager. Only 1 is allowed per branch.")
        if payload.role == EmployeeRole.SUPPORT_TEAM and current_count >= 5:
            raise HTTPException(status_code=400, detail=f"Branch already has a Support Team member. Only 1 is allowed per branch.")
        if payload.role == EmployeeRole.HR and current_count >= 3:
            raise HTTPException(status_code=400, detail=f"Branch already has 3 HR members. Only 3 are allowed per branch.")

    # Enforcement: Singleton Manager per Branch
    if payload.role == EmployeeRole.MANAGER:
        existing_manager = db.query(Employee).filter(
            Employee.branch_id == resolved_branch_id,
            Employee.role == EmployeeRole.MANAGER,
            Employee.is_active == True
        ).first()
        if existing_manager:
            raise InvalidStateError("A manager already exists for this branch.")

    temp_pw_for_mail: str | None = None
    if payload.password:
        user = Employee(
            name=payload.name,
            email=email_lower,
            personal_email=(payload.personal_email.strip().lower() if payload.personal_email else None),
            phone=payload.phone,
            organization_id=resolved_organization_id,
            branch_id=resolved_branch_id,
            role=payload.role,
            password_hash=get_password_hash(payload.password),
            password_reset_required=False,
            is_active=True,
        )
    else:
        org = db.query(Organization).filter(Organization.organization_id == resolved_organization_id).first()
        company_email = generate_company_email(payload.name, db, org.domain if org else None)
        temp_pw_for_mail = generate_temp_password()
        user = Employee(
            name=payload.name,
            email=company_email,
            personal_email=payload.personal_email.strip().lower(),
            phone=payload.phone,
            organization_id=resolved_organization_id,
            branch_id=resolved_branch_id,
            role=payload.role,
            password_hash=get_password_hash(temp_pw_for_mail),
            password_reset_required=True,
            is_active=True,
        )
    db.add(user)
    db.flush()

    # Assign default role permissions for all permission flags.
    default_perms = get_default_permission_flags(user.role)
    user.permissions = EmployeePermission(
        employee_id=user.employee_id,
        organization_id=user.organization_id,
        branch_id=user.branch_id,
        **default_perms
    )
    db.add(user.permissions)
    db.flush()

    if temp_pw_for_mail:
        EmailService.send_provisioning_credentials(user.personal_email, user.name, user.email, temp_pw_for_mail)

    asset_ids = list(payload.onboarding_asset_ids)

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
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER))
):
    query=apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.is_active==True)
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM] and current_user.branch_id:
        query = query.filter(Employee.branch_id == current_user.branch_id)
    if branch:
        query=query.filter(Employee.branch_id==branch)
    if role:
        query=query.filter(Employee.role==role)
    return query.all()

@router.get("/{emp_id}", response_model=EmployeeRead)
def get_employee(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM))
):
    emp=apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id==emp_id).first()
    if not emp:
        raise ResourceNotFoundError("Employee", emp_id)
    return emp

@router.post("/{emp_id}/deactivate")
def deactivate_employee(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    target=apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id==emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if target.role == EmployeeRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="The Global System Administrator is a singleton and cannot be deactivated.")

    return EmployeeLifecycleService.deactivate_and_recover_assets(db, emp_id, current_user, "OFFBOARDING_RECOVERY")

@router.get("/{emp_id}/assets")
def get_employee_assets(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE))
):
    if current_user.role==EmployeeRole.EMPLOYEE and current_user.employee_id!=emp_id:
        raise ResourceNotFoundError("Employee", emp_id)
        
    emp = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not emp:
        raise ResourceNotFoundError("Employee", emp_id)

    active=apply_tenant_filter(db.query(Tracking), current_user, Tracking).filter(Tracking.emp_id==emp_id, Tracking.returned_at==None).all()
    
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

@router.get("/{emp_id}/permissions", response_model=EmployeePermissionRead)
def get_employee_permissions(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN))
):
    target = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if not target.permissions:
        default_perms = get_default_permission_flags(target.role)
        target.permissions = EmployeePermission(
            employee_id=target.employee_id,
            organization_id=target.organization_id,
            branch_id=target.branch_id,
            **default_perms,
        )
        db.add(target.permissions)
        db.commit()
        db.refresh(target)
        
    return target.permissions

@router.put("/{emp_id}/permissions", response_model=EmployeePermissionRead)
def update_employee_permissions(
    emp_id: str,
    payload: EmployeePermissionUpdate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN))
):
    target = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if current_user.employee_id == emp_id:
        raise HTTPException(status_code=403, detail="You cannot edit your own permissions.")

    if current_user.role == EmployeeRole.ORG_ADMIN:
        if target.role == EmployeeRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Organization Admin cannot modify permissions of a Global Admin.")

    if not target.permissions:
        default_perms = get_default_permission_flags(target.role)
        target.permissions = EmployeePermission(
            employee_id=target.employee_id,
            organization_id=target.organization_id,
            branch_id=target.branch_id,
            **default_perms,
        )
        db.add(target.permissions)
        
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(target.permissions, key, value)
        
    db.commit()
    db.refresh(target.permissions)
    return target.permissions
