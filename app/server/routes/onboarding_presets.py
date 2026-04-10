from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.models.stock import OnboardingPresetCreate, OnboardingPresetRead, OnboardingPresetListResponse
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.onboarding import OnboardingPreset

router = APIRouter(prefix="/onboarding-presets", tags=["onboarding_presets"])


@router.get("/", response_model=OnboardingPresetListResponse)
def list_onboarding_presets(
    search: Optional[str] = None,
    target_role: Optional[str] = None,
    branch: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER)),
):
    query = db.query(OnboardingPreset)
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        query = query.filter(OnboardingPreset.organization_id == current_user.organization_id)
    if target_role:
        query = query.filter(OnboardingPreset.target_role == target_role.strip().lower())
    if branch:
        query = query.filter(OnboardingPreset.branch.ilike(f"%{branch.strip()}%"))
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            or_(
                OnboardingPreset.name.ilike(needle),
                OnboardingPreset.preset_id.ilike(needle),
                OnboardingPreset.branch.ilike(needle),
                OnboardingPreset.target_role.ilike(needle),
            )
        )
    try:
        total = query.count()
        rows = query.order_by(OnboardingPreset.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        items = [OnboardingPresetRead.model_validate(row) for row in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    except ProgrammingError as exc:
        msg = str(getattr(exc.orig, "diag", getattr(exc.orig, "pgerror", exc)))
        if "onboarding_presets.organization_id" in msg or "column onboarding_presets.organization_id does not exist" in msg:
            raise HTTPException(
                status_code=500,
                detail="Database schema is out of date for onboarding_presets. "
                "Add organization_id column to onboarding_presets or run the latest migrations.",
            ) from exc
        raise


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
    try:
        db.commit()
        db.refresh(preset)
        return preset
    except ProgrammingError as exc:
        db.rollback()
        msg = str(getattr(exc.orig, "diag", getattr(exc.orig, "pgerror", exc)))
        if "onboarding_presets.organization_id" in msg or "column \"organization_id\" of relation \"onboarding_presets\" does not exist" in msg:
            raise HTTPException(
                status_code=500,
                detail="Database schema is out of date for onboarding_presets. "
                "Add organization_id column to onboarding_presets or run the latest migrations.",
            ) from exc
        raise


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
    try:
        db.commit()
        return {"status": "ok"}
    except ProgrammingError as exc:
        db.rollback()
        msg = str(getattr(exc.orig, "diag", getattr(exc.orig, "pgerror", exc)))
        if "onboarding_presets.organization_id" in msg or "column onboarding_presets.organization_id does not exist" in msg:
            raise HTTPException(
                status_code=500,
                detail="Database schema is out of date for onboarding_presets. "
                "Add organization_id column to onboarding_presets or run the latest migrations.",
            ) from exc
        raise
