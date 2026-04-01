from typing import List

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.models.onboarding_preset import OnboardingPresetCreate, OnboardingPresetRead
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.onboarding_preset import OnboardingPreset
from app.server.middlewares.auth import require_roles
from app.server.exceptions.base import ResourceNotFoundError

router = APIRouter(prefix="/onboarding-presets", tags=["onboarding_presets"])


def _to_read(p: OnboardingPreset) -> OnboardingPresetRead:
    tr = None
    if p.target_role:
        try:
            tr = EmployeeRole(p.target_role)
        except ValueError:
            tr = None
    return OnboardingPresetRead(
        preset_id=p.preset_id,
        name=p.name,
        target_role=tr,
        branch=p.branch,
        asset_ids=p.get_asset_ids(),
        created_at=p.created_at,
    )


@router.get("/", response_model=List[OnboardingPresetRead])
def list_presets(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)
    ),
):
    rows = db.query(OnboardingPreset).order_by(OnboardingPreset.created_at.desc()).all()
    return [_to_read(r) for r in rows]


@router.post("/", response_model=OnboardingPresetRead, status_code=201)
def create_preset(
    payload: OnboardingPresetCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER)),
):
    p = OnboardingPreset(
        name=payload.name.strip(),
        target_role=payload.target_role.value if payload.target_role else None,
        branch=payload.branch,
    )
    p.set_asset_ids(payload.asset_ids)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_read(p)


@router.delete("/{preset_id}")
def delete_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER)),
):
    p = db.query(OnboardingPreset).filter(OnboardingPreset.preset_id == preset_id).first()
    if not p:
        raise ResourceNotFoundError("OnboardingPreset", preset_id)
    db.delete(p)
    db.commit()
    return Response(status_code=204)
