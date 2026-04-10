from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy import func, or_

from app.server.auth.service import (
    get_password_hash,
    create_default_permissions,
    _login_email_host_strict,
    _org_domain_host_strict,
)
from app.server.database.database import get_db
from app.server.schema.employee import Employee, EmployeeRole, EmployeePermission
from app.server.schema.asset import Asset
from app.server.schema.organization import Organization, SubscriptionStatus, Branch, BranchStatus
from app.server.services.audit_service import AuditService
from app.server.models.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse, OrganizationOnboardResponse,
    OrganizationListResponse, BranchCreate, BranchUpdate, BranchResponse, BranchListResponse
)
from app.server.middlewares.auth import require_roles
from app.server.services.email_service import EmailService
from app.server.services.provisioning_service import generate_temp_password
from app.server.services.organization_delete_service import purge_organization

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("/", response_model=OrganizationOnboardResponse, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN))
):
    domain = payload.domain.strip().lower() if payload.domain else None

    existing_org_name = db.query(Organization).filter(
        func.lower(func.trim(Organization.organization_name)) == payload.organization_name.strip().lower()
    ).first()
    if existing_org_name:
        raise HTTPException(status_code=400, detail="An organization with this name already exists.")

    if domain:
        existing_org_domain = db.query(Organization).filter(
            func.lower(func.trim(Organization.domain)) == domain
        ).first()
        if existing_org_domain:
            raise HTTPException(status_code=400, detail="An organization with this domain already exists.")

        admin_host = _login_email_host_strict(payload.admin_work_email)
        org_host = _org_domain_host_strict(domain)
        if not admin_host or not org_host or admin_host != org_host:
            raise HTTPException(
                status_code=400,
                detail="Org admin work email domain must exactly match the organization domain (same rules as sign-in).",
            )

    existing_work_email = db.query(Employee).filter(
        func.lower(func.trim(Employee.email)) == payload.admin_work_email
    ).first()
    if existing_work_email:
        raise HTTPException(status_code=400, detail="Admin work email is already used by another employee.")

    existing_personal_email = db.query(Employee).filter(
        func.lower(func.trim(Employee.personal_email)) == payload.admin_personal_email
    ).first()
    if existing_personal_email:
        raise HTTPException(status_code=400, detail="Admin personal email is already used by another employee.")

    try:
        sub_status = SubscriptionStatus(payload.subscription_status or "ACTIVE")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid subscription_status")

    sub_start = payload.subscription_start_at or datetime.now(timezone.utc)
    sub_end = payload.subscription_end_at

    org = Organization(
        organization_name=payload.organization_name.strip(),
        domain=domain,
        subscription_status=sub_status,
        subscription_start_at=sub_start,
        subscription_end_at=sub_end,
    )
    db.add(org)
    db.flush()

    temp_password = generate_temp_password()
    admin = Employee(
        name=payload.admin_name,
        email=payload.admin_work_email,
        personal_email=payload.admin_personal_email,
        role=EmployeeRole.ORG_ADMIN,
        organization_id=org.organization_id,
        branch_id=None,
        password_hash=get_password_hash(temp_password),
        password_reset_required=True,
        is_active=True,
    )
    db.add(admin)
    db.flush()

    admin.permissions = EmployeePermission(
        employee_id=admin.employee_id,
        organization_id=org.organization_id,
        branch_id=None,
        permissions_json=create_default_permissions(EmployeeRole.ORG_ADMIN),
    )
    db.add(admin.permissions)

    db.commit()
    db.refresh(org)
    db.refresh(admin)

    EmailService.send_provisioning_credentials(
        personal_email=admin.personal_email,
        employee_name=admin.name,
        company_email=admin.email,
        temp_password=temp_password,
    )

    return OrganizationOnboardResponse(
        organization_id=org.organization_id,
        organization_name=org.organization_name,
        domain=org.domain,
        subscription_status=org.subscription_status.value if hasattr(org.subscription_status, "value") else str(org.subscription_status),
        subscription_start_at=org.subscription_start_at,
        subscription_end_at=org.subscription_end_at,
        org_admin_employee_id=admin.employee_id,
        org_admin_name=admin.name,
        org_admin_work_email=admin.email,
        org_admin_personal_email=admin.personal_email,
        created_at=org.created_at,
    )

@router.get("/", response_model=OrganizationListResponse)
def get_organizations(
    search: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    query = db.query(Organization)
    
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        if not current_user.organization_id:
            return {"items": [], "total": 0, "page": page, "per_page": per_page}
        query = query.filter(Organization.organization_id == current_user.organization_id)
        
    if status:
        query = query.filter(Organization.subscription_status == status.upper())
        
    if search:
        search_filter = f"%{search}%"
        query = query.outerjoin(Employee, (Employee.organization_id == Organization.organization_id) & (Employee.role == EmployeeRole.ORG_ADMIN)).filter(
            or_(
                Organization.organization_name.ilike(search_filter),
                Organization.domain.ilike(search_filter),
                Organization.subscription_status.astext.ilike(search_filter) if db.bind.dialect.name == 'postgresql' else Organization.subscription_status.ilike(search_filter),
                Employee.email.ilike(search_filter)
            )
        )
        
    total = query.count()
    items = query.order_by(Organization.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }


@router.put("/{org_id}", response_model=OrganizationResponse)
def update_organization(
    org_id: str,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN))
):
    org = db.query(Organization).filter(Organization.organization_id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    
    data = payload.model_dump(exclude_unset=True)
    if "subscription_status" in data:
        try:
            data["subscription_status"] = SubscriptionStatus(data["subscription_status"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid subscription_status")

    for k, v in data.items():
        setattr(org, k, v)

    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN)),
):
    org = db.query(Organization).filter(Organization.organization_id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if current_user.organization_id and current_user.organization_id == org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete the organization your account is assigned to.",
        )

    snapshot = {
        "organization_id": org.organization_id,
        "organization_name": org.organization_name,
        "domain": org.domain,
        "subscription_status": org.subscription_status.value
        if hasattr(org.subscription_status, "value")
        else str(org.subscription_status),
    }

    try:
        purge_organization(db, org)
        AuditService.log_change(db, "organizations", org_id, "DELETE", current_user, snapshot, None, "ORGANIZATION_DELETE")
        db.delete(org)
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.get("/{org_id}/admin")
def get_organization_admin_details(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN)),
):
    if current_user.role != EmployeeRole.SUPER_ADMIN and current_user.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view admin details for another organization")

    org = db.query(Organization).filter(Organization.organization_id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    admin = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.role == EmployeeRole.ORG_ADMIN,
        Employee.is_active == True,
    ).order_by(Employee.created_at.asc()).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization admin not found")

    return {
        "organization_id": org.organization_id,
        "organization_name": org.organization_name,
        "domain": org.domain,
        "subscription_status": org.subscription_status.value if hasattr(org.subscription_status, "value") else str(org.subscription_status),
        "subscription_start_at": org.subscription_start_at.isoformat() if org.subscription_start_at else None,
        "subscription_end_at": org.subscription_end_at.isoformat() if org.subscription_end_at else None,
        "org_admin_employee_id": admin.employee_id,
        "org_admin_name": admin.name,
        "org_admin_work_email": admin.email,
        "org_admin_personal_email": admin.personal_email,
        "org_admin_active": admin.is_active,
    }


@router.post("/{org_id}/revoke", response_model=OrganizationResponse)
def revoke_organization(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN)),
):
    org = db.query(Organization).filter(Organization.organization_id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org.subscription_status = SubscriptionStatus.INACTIVE
    db.commit()
    db.refresh(org)
    return org


@router.post("/{org_id}/restore", response_model=OrganizationResponse)
def restore_organization(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN)),
):
    org = db.query(Organization).filter(Organization.organization_id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org.subscription_status = SubscriptionStatus.ACTIVE
    db.commit()
    db.refresh(org)
    return org

@router.post("/{org_id}/branches", response_model=BranchResponse)
def create_branch(
    org_id: str,
    payload: BranchCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ORG_ADMIN))
):
    if current_user.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create branch for another organization")

    branch = Branch(**payload.model_dump(), organization_id=org_id)
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch

@router.get("/{org_id}/branches", response_model=BranchListResponse)
def get_branches(
    org_id: str,
    search: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        if current_user.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view branches of another organization")
            
    query = db.query(Branch).filter(Branch.organization_id == org_id)
    
    if status:
        query = query.filter(Branch.status == status.upper())
        
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Branch.branch_name.ilike(search_filter),
                Branch.location.ilike(search_filter),
                Branch.status.astext.ilike(search_filter) if db.bind.dialect.name == 'postgresql' else Branch.status.ilike(search_filter)
            )
        )
        
    total = query.count()
    items = query.order_by(Branch.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }


@router.put("/{org_id}/branches/{branch_id}", response_model=BranchResponse)
def update_branch(
    org_id: str,
    branch_id: str,
    payload: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ORG_ADMIN))
):
    if current_user.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot update branch of another organization")
            
    branch = db.query(Branch).filter(Branch.branch_id == branch_id, Branch.organization_id == org_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        try:
            data["status"] = BranchStatus(data["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid branch status")

    for k, v in data.items():
        setattr(branch, k, v)

    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/{org_id}/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    org_id: str,
    branch_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ORG_ADMIN)),
):
    if current_user.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete branch of another organization")

    branch = db.query(Branch).filter(Branch.branch_id == branch_id, Branch.organization_id == org_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    emp_n = db.query(func.count()).select_from(Employee).filter(Employee.branch_id == branch_id).scalar() or 0
    asset_n = db.query(func.count()).select_from(Asset).filter(Asset.branch_id == branch_id).scalar() or 0
    if emp_n > 0 or asset_n > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Branch has linked employees or assets; reassign or remove them before deletion.",
                "employees_count": int(emp_n),
                "assets_count": int(asset_n),
            },
        )

    snapshot = {
        "branch_id": branch.branch_id,
        "organization_id": branch.organization_id,
        "branch_name": branch.branch_name,
        "location": branch.location,
        "status": branch.status.value if hasattr(branch.status, "value") else str(branch.status),
    }
    AuditService.log_change(db, "branches", branch_id, "DELETE", current_user, snapshot, None, "BRANCH_DELETE")

    db.delete(branch)
    db.commit()
