from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from typing import List, Optional

from app.server.database.database import get_db
from app.server.models.request import (
    AdminDirectAllocationCreate,
    AdminDirectAllocationResponse,
    RequestCreate,
    RequestCrossBranchTransfer,
    RequestFormOptions,
    RequestHRVerify,
    RequestListResponse,
    RequestManagerNotes,
    RequestNecessityRecommendationResponse,
    RequestResolve,
    RequestResponse,
    RequestReview,
    RequestTriage,
)
from app.server.schema.request import Request
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles
from app.server.auth.service import get_current_user
from app.server.services.request_necessity_ai_service import recommend_necessity_for_request
from app.server.services.request_service import RequestService

router=APIRouter(prefix="/requests", tags=["requests"])


@router.get("/form-options", response_model=RequestFormOptions)
def get_request_form_options(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return RequestService.get_request_form_options(db, current_user)

@router.get("/", response_model=RequestListResponse)
def list_requests(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    severity: Optional[str] = None,
    urgency: Optional[str] = None,
    branch: Optional[str] = None,
    request_type: Optional[str] = None,
    sort_by_priority: bool = False,
    page: int = 1,
    per_page: int = 20,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    return RequestService.list_requests(
        db,
        current_user,
        status=status,
        priority=priority,
        severity=severity,
        urgency=urgency,
        branch=branch,
        sort_by_priority=sort_by_priority,
        page=page,
        per_page=per_page,
        request_type=request_type,
    )

@router.post("/", response_model=RequestResponse)
def create_request(
    payload: RequestCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.EMPLOYEE, EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM))
):
    return RequestService.create_asset_request(db, payload, current_user)


@router.post("/{request_id}/recommend-necessity", response_model=RequestNecessityRecommendationResponse)
def recommend_necessity_for_request_route(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN)),
):
    """
    Gemini (gemini-2.5-flash) advisory for this ticket: whether the asset is likely needed,
    using the requester's assignments, branch stock, and recent requests. HR: same branch only.
    Requires GEMINI_API_KEY.
    """
    try:
        out = recommend_necessity_for_request(db, current_user, request_id)
        return RequestNecessityRecommendationResponse(**out)
    except ValueError as e:
        msg = str(e)
        if "GEMINI_API_KEY" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/{request_id}/triage", response_model=RequestResponse)
def triage_request(
    request_id: str, 
    payload: RequestTriage, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    return RequestService.triage_asset_request(db, request_id, payload, current_user)

@router.post("/{request_id}/review/hr", response_model=RequestResponse)
def hr_review(
    request_id: str, 
    payload: RequestHRVerify, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_hr(db, request_id, payload, current_user)

@router.post("/{request_id}/review/manager", response_model=RequestResponse)
def manager_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER, EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_manager(db, request_id, payload, current_user)

@router.post("/{request_id}/manager-notes", response_model=RequestResponse)
def update_manager_notes(
    request_id: str, 
    payload: RequestManagerNotes, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER, EmployeeRole.ADMIN))
):
    return RequestService.update_manager_notes(db, request_id, payload, current_user)

@router.delete("/{request_id}")
def delete_request(
    request_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.EMPLOYEE, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    return RequestService.delete_request(db, request_id, current_user)

@router.post("/{request_id}/review/admin", response_model=RequestResponse)
def admin_review(
    request_id: str, 
    payload: RequestReview, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.ADMIN))
):
    return RequestService.review_request_by_admin(db, request_id, payload, current_user)

@router.post("/{request_id}/execute")
def execute_request(
    request_id: str, 
    provided_asset_id: Optional[str] = None, 
    broken_asset_id: Optional[str] = None, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    req=RequestService.execute_asset_request(db, request_id, provided_asset_id, broken_asset_id, current_user)
    return {"status": "success", "executed_action": req.action_type, "new_status": req.status}

@router.post("/{request_id}/transfer-request", response_model=RequestResponse)
def transfer_request(
    request_id: str, 
    payload: RequestCrossBranchTransfer, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.MANAGER))
):
    return RequestService.request_cross_branch_transfer(db, request_id, payload, current_user)

@router.post("/{request_id}/resolve")
def resolve_request(
    request_id: str,
    payload: RequestResolve,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ADMIN))
):
    req=RequestService.resolve_service_request(db, request_id, payload, current_user)
    return {"status": "resolved", "final_action": "REPAIRED_AND_RETURNED", "new_status": req.status}


@router.post("/allocate/direct", response_model=AdminDirectAllocationResponse)
def direct_allocate_asset(
    payload: AdminDirectAllocationCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN))
):
    """
    Allows admin to directly allocate an asset to an employee without going through the request workflow.
    This bypasses all request approval stages and directly creates an allocation record.
    """
    from app.server.services.stock_service import StockService
    from app.server.schema.tracking import AllocationType
    from app.server.exceptions.base import ResourceNotFoundError, InsufficientStockError
    
    # Validate that the employee exists
    employee = db.query(Employee).filter(Employee.employee_id == payload.employee_id).first()
    if not employee:
        raise ResourceNotFoundError("Employee", payload.employee_id)
    
    # Convert allocation_type string to enum
    try:
        alloc_type = AllocationType[payload.allocation_type.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid allocation_type. Must be PERMANENT or TEMPORARY."
        )
    
    try:
        # Directly allocate the asset
        tracking = StockService.allocate_asset(
            db=db,
            asset_id=payload.asset_id,
            emp_id=payload.employee_id,
            alloc_type=alloc_type,
            user=current_user,
            reason=payload.reason
        )
        db.commit()
        
        return AdminDirectAllocationResponse(
            tracking_id=tracking.tracking_id,
            asset_id=tracking.asset_id,
            employee_id=tracking.emp_id,
            allocation_type=tracking.allocation_type.value,
            movement_reason=tracking.movement_reason,
            assigned_date=tracking.assigned_date
        )
    except (ResourceNotFoundError, InsufficientStockError) as e:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to allocate asset: {str(e)}"
        )
