from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.cmdb_service import CMDBService

router = APIRouter(
    prefix="/cmdb",
    tags=["cmdb"],
    dependencies=[Depends(require_module_access("cmdb"))],
)


class CIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ci_id: str
    ci_type: str
    name: str
    asset_id: Optional[str] = None
    status: str
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
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


class CIListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[CIRead]
    total: int
    page: int
    per_page: int


class CIRelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[CIRelRead]
    total: int
    page: int
    per_page: int


class CMDBOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ci_types: List[str]
    relationship_types: List[str]


class CMDBImpactItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ci_id: str
    name: str
    asset_id: Optional[str] = None
    status: str
    ci_type: str


class CMDBImpactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ci_id: str
    dependent_assets: List[CMDBImpactItem]
    dependent_services: List[CMDBImpactItem]
    impacted_ci_count: int


@router.get("/items", response_model=CIListResponse)
def list_ci(
    search: Optional[str] = None,
    ci_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    """
    List Configuration Items (CIs).
    
    Valid CI types: ASSET, SOFTWARE, SERVICE, USER, NETWORK_DEVICE, FURNITURE, CLOUD, OTHER
    
    Query Parameters:
    - search: Search by name or CI ID
    - ci_type: Filter by CI type (e.g., "ASSET", "SOFTWARE", "SERVICE")
    - page: Page number
    - per_page: Items per page
    """
    return CMDBService.list_items(
        db, 
        current_user, 
        search=search,
        ci_type=ci_type,
        page=page,
        per_page=per_page
    )


@router.get("/options", response_model=CMDBOptionsResponse)
def list_options(
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
    db: Session = Depends(get_db),
):
    return {
        "ci_types": sorted(CMDBService.VALID_CI_TYPES),
        "relationship_types": CMDBService.get_relationship_types(db, current_user),
    }



@router.post("/items", response_model=CIRead, status_code=201)
def create_ci(
    payload: CICreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER)),
):
    """
    Create a new Configuration Item (CI).
    
    Requires ADMIN or MANAGER role.
    
    Valid CI types: ASSET, SOFTWARE, SERVICE, USER, NETWORK_DEVICE, FURNITURE, CLOUD, OTHER
    Invalid types default to "OTHER".
    
    An optional asset_id can link this CI to a physical or digital asset.
    """
    r = CMDBService.create_item(
        db,
        current_user,
        ci_type=payload.ci_type,
        name=payload.name,
        asset_id=payload.asset_id,
        ci_status=payload.status,
    )
    return CIRead(
        ci_id=r.ci_id,
        ci_type=r.ci_type,
        name=r.name,
        asset_id=r.asset_id,
        status=r.status,
        organization_id=r.organization_id,
        branch_id=r.branch_id,
        created_at=r.created_at.isoformat() if r.created_at else None,
    )


@router.get("/relationships", response_model=CIRelListResponse)
def list_rels(
    ci_id: Optional[str] = None,
    search: Optional[str] = None,
    relationship_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    """
    List CI Relationships.
    
    Query Parameters:
    - ci_id: Filter relationships involving this CI (as source or target)
    
    Valid relationship types:
    - depends_on: Source depends on target (e.g., software depends on service)
    - connected_to: Bidirectional connection (e.g., device connected to network)
    - assigned_to: Source assigned/allocated to target (e.g., software to device, user to device)
    - hosted_on: Source is hosted/running on target (e.g., service hosted on server)
    - supports: Source physically/logically supports target (e.g., furniture supports monitor)
    """
    return CMDBService.list_relationships(
        db,
        current_user,
        ci_id=ci_id,
        search=search,
        relationship_type=relationship_type,
        page=page,
        per_page=per_page,
    )


@router.post("/relationships", response_model=CIRelRead, status_code=201)
def create_rel(
    payload: RelCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER)),
):
    """
    Create a CI Relationship.
    
    Requires ADMIN or MANAGER role.
    
    Valid relationship types:
    - depends_on: Source depends on target (e.g., software depends on service)
    - connected_to: Bidirectional connection (e.g., device connected to network)
    - assigned_to: Source assigned/allocated to target (e.g., software to device, user to device)
    - hosted_on: Source is hosted/running on target (e.g., service hosted on server)
    - supports: Source physically/logically supports target (e.g., furniture supports monitor)
    
    Both source_ci and target_ci must exist as Configuration Items.
    """
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


@router.get("/ci", response_model=CIListResponse)
def list_ci_module12(
    search: Optional[str] = None,
    ci_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    return CMDBService.list_items(
        db,
        current_user,
        search=search,
        ci_type=ci_type,
        page=page,
        per_page=per_page,
    )


@router.get("/ci/{ci_id}", response_model=CIRead)
def get_ci_by_id(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    payload = CMDBService.get_item_payload(db, ci_id, current_user)
    return CIRead(**payload)


@router.get("/ci/{ci_id}/impact", response_model=CMDBImpactResponse)
def get_ci_impact(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM)),
):
    payload = CMDBService.get_impact(db, ci_id, current_user)
    return CMDBImpactResponse(**payload)


@router.post("/relationship", response_model=CIRelRead, status_code=201)
def create_relationship_module12(
    payload: RelCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER)),
):
    try:
        rel = CMDBService.create_relationship(
            db,
            current_user,
            source_ci=payload.source_ci,
            target_ci=payload.target_ci,
            relationship_type=payload.relationship_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CIRelRead.model_validate(rel)
