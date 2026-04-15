from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.models.software import (
    SoftwareAssignPayload,
    SoftwareAssignmentHistoryItem,
    SoftwareAssignmentResponse,
    SoftwareHardwareOption,
    SoftwareRemovePayload,
    SoftwareRemovalResponse,
    SoftwareUsageItem,
)
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.software_service import SoftwareService

router = APIRouter(
    prefix="/software",
    tags=["software"],
    dependencies=[Depends(require_module_access("requests"))],
)


@router.get("/hardware-options", response_model=list[SoftwareHardwareOption])
def list_software_hardware_options(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN)
    ),
):
    return SoftwareService.list_hardware_options(db, employee_id, current_user)


@router.post("/assign", response_model=SoftwareAssignmentResponse)
def assign_software(
    payload: SoftwareAssignPayload,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN)
    ),
):
    return SoftwareService.assign_software(db, payload, current_user)


@router.post("/remove", response_model=SoftwareRemovalResponse)
def remove_software(
    payload: SoftwareRemovePayload,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN)
    ),
):
    return SoftwareService.remove_software(db, payload, current_user)


@router.get("/history", response_model=list[SoftwareAssignmentHistoryItem])
def software_assignment_history(
    request_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR)
    ),
):
    return SoftwareService.assignment_history(db, current_user, request_id=request_id, employee_id=employee_id)


@router.get("/usage", response_model=list[SoftwareUsageItem])
def software_usage(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(
        require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR)
    ),
):
    return SoftwareService.usage_summary(db, current_user)
