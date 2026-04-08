from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.models.stock import OnboardingPresetCreate, OnboardingPresetRead
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.onboarding import OnboardingPreset

router = APIRouter(prefix="/onboarding-presets", tags=["onboarding_presets"])


@router.get("/", response_model=List[OnboardingPresetRead])
def list_onboarding_presets(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER)),
):
    query = db.query(OnboardingPreset)
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        query = query.filter(OnboardingPreset.organization_id == current_user.organization_id)
    return query.order_by(OnboardingPreset.created_at.desc()).all()


@router.post("/", response_model=OnboardingPresetRead, status_code=201)
def create_onboarding_preset(
    payload: OnboardingPresetCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER)),
):
    if current_user.role == EmployeeRole.SUPER_ADMIN and not current_user.organization_id:
        raise HTTPException(status_code=400, detail="Super admin must belong to an organization to create onboarding presets.")

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization is associated with current user.")

    preset = OnboardingPreset(
        organization_id=org_id,
        name=payload.name,
        target_role=payload.target_role.value if payload.target_role else None,
        branch=payload.branch,
        asset_ids=payload.asset_ids,
        created_by=current_user.employee_id,
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


@router.delete("/{preset_id}")
def delete_onboarding_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER)),
):
    query = db.query(OnboardingPreset).filter(OnboardingPreset.preset_id == preset_id)
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        query = query.filter(OnboardingPreset.organization_id == current_user.organization_id)

    preset = query.first()
    if not preset:
        raise HTTPException(status_code=404, detail="Onboarding preset not found")

    db.delete(preset)
    db.commit()
    return {"status": "ok"}
