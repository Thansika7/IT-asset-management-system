from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_roles
from app.server.models.request import RequestResponse
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.resignation_service import ResignationService

router = APIRouter(prefix="/resignations", tags=["resignations"])


class ResignationSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1)
    last_working_day: Optional[str] = None


class ResignationRejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = None


@router.get("/", response_model=List[RequestResponse])
def list_resignations(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR)),
):
    return ResignationService.list_resignations(db, current_user)


@router.put("/{request_id}/approve")
def approve_resignation(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR)),
):
    return ResignationService.approve(db, request_id, current_user)


@router.put("/{request_id}/reject", response_model=RequestResponse)
def reject_resignation(
    request_id: str,
    payload: ResignationRejectBody,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR)),
):
    return ResignationService.reject(db, request_id, current_user, notes=payload.notes)
