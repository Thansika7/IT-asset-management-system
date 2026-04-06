from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.cmdb_service import CMDBService

router = APIRouter(prefix="/cmdb", tags=["cmdb"])


class CIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ci_id: str
    ci_type: str
    name: str
    asset_id: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class CIRelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    relationship_id: str
    source_ci: str
    target_ci: str
    relationship_type: str


class CICreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ci_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    asset_id: Optional[str] = None
    status: str = "ACTIVE"


class RelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ci: str
    target_ci: str
    relationship_type: str


@router.get("/items", response_model=List[CIRead])
def list_ci(
    ci_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    rows = CMDBService.list_items(db, current_user, ci_type=ci_type)
    return [
        CIRead(
            ci_id=r.ci_id,
            ci_type=r.ci_type,
            name=r.name,
            asset_id=r.asset_id,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.post("/items", response_model=CIRead, status_code=201)
def create_ci(
    payload: CICreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER)),
):
    r = CMDBService.create_item(
        db,
        current_user,
        ci_type=payload.ci_type,
        name=payload.name,
        asset_id=payload.asset_id,
        status=payload.status,
    )
    return CIRead(
        ci_id=r.ci_id,
        ci_type=r.ci_type,
        name=r.name,
        asset_id=r.asset_id,
        status=r.status,
        created_at=r.created_at.isoformat() if r.created_at else None,
    )


@router.get("/relationships", response_model=List[CIRelRead])
def list_rels(
    ci_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    rows = CMDBService.list_relationships(db, current_user, ci_id=ci_id)
    return [CIRelRead.model_validate(r) for r in rows]


@router.post("/relationships", response_model=CIRelRead, status_code=201)
def create_rel(
    payload: RelCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER)),
):
    try:
        r = CMDBService.create_relationship(
            db,
            current_user,
            source_ci=payload.source_ci,
            target_ci=payload.target_ci,
            relationship_type=payload.relationship_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return CIRelRead.model_validate(r)
