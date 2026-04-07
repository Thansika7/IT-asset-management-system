from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.server.database.database import get_db
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.organization import Organization, SubscriptionStatus, Branch, BranchStatus
from app.server.models.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    BranchCreate, BranchUpdate, BranchResponse
)
from app.server.middlewares.auth import require_roles, RequirePermission

router = APIRouter(prefix="/organizations", tags=["organizations"])

@router.post("/", response_model=OrganizationResponse)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN))
):
    existing_org = db.query(Organization).filter(Organization.domain == payload.domain).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="An organization with this domain already exists.")
    org = Organization(**payload.model_dump())
    db.add(org)
    db.commit()
    db.refresh(org)
    return org

@router.get("/", response_model=List[OrganizationResponse])
def get_organizations(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN))
):
    return db.query(Organization).all()

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
    
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(org, k, v)
    
    db.commit()
    db.refresh(org)
    return org

@router.post("/{org_id}/branches", response_model=BranchResponse)
def create_branch(
    org_id: str,
    payload: BranchCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(RequirePermission("can_create_branch"))
):
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        if current_user.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create branch for another organization")

    branch = Branch(**payload.model_dump(), organization_id=org_id)
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch

@router.get("/{org_id}/branches", response_model=List[BranchResponse])
def get_branches(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(RequirePermission("can_view_branch"))
):
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        if current_user.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view branches of another organization")
            
    return db.query(Branch).filter(Branch.organization_id == org_id).all()

@router.put("/{org_id}/branches/{branch_id}", response_model=BranchResponse)
def update_branch(
    org_id: str,
    branch_id: str,
    payload: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(RequirePermission("can_update_branch"))
):
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        if current_user.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot update branch of another organization")
            
    branch = db.query(Branch).filter(Branch.branch_id == branch_id, Branch.organization_id == org_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(branch, k, v)
        
    db.commit()
    db.refresh(branch)
    return branch
