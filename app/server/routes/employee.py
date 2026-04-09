from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.server.auth.service import (
    create_default_permissions,
    get_default_permission_flags,
    get_effective_permissions,
    get_current_user,
    get_permission_catalog,
    get_password_hash,
    has_permission,
    permission_json_to_legacy_flags,
)
from sqlalchemy import or_, String, func
from app.server.database.database import get_db
from app.server.models.api import (
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    EmployeePermissionUpdate,
    EmployeePermissionRead,
    EmployeeListResponse,
    EmployeeFilterOptions,
    PermissionCatalogResponse,
    EmployeeAssetListResponse,
    EmployeeAssetItem,
    EmployeeAssetFilterOptions,
    EmployeeAssetHistoryResponse,
    EmployeeAssetHistoryItem,
    EmployeeAssetBulkAssignRequest,
    EmployeeAssetBulkAssignResponse,
    EmployeeAssetOwnershipAnalyticsResponse,
)
from app.server.models.request import RequestListResponse
from app.server.services.email_service import EmailService
from app.server.services.provisioning_service import generate_company_email, generate_temp_password
from app.server.services.employee_lifecycle_service import EmployeeLifecycleService
from app.server.database.tenant import apply_tenant_filter
from app.server.schema.employee import Employee, EmployeeRole, EmployeePermission
from app.server.schema.onboarding import OnboardingPreset
from app.server.schema.organization import Organization, Branch
from app.server.schema.tracking import Tracking
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.category import Category
from app.server.schema.request import Request
from app.server.middlewares.auth import require_permission, require_roles
from app.server.services.stock_service import StockService
from app.server.services.audit_service import AuditService
from app.server.services.employee_asset_service import EmployeeAssetService
from app.server.exceptions.base import InvalidStateError, ResourceNotFoundError
from app.server.schema.tracking import AllocationType

router=APIRouter(prefix="/employees", tags=["employees"])
me_router=APIRouter(prefix="/me", tags=["self_service"])


def _can_view_employee_directory(user: Employee) -> bool:
    return (
        user.role in {EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER}
        or has_permission(user, "users", "permissions")
        or has_permission(user, "users", "manage")
        or has_permission(user, "users", "view")
    )


@router.post("/register", response_model=EmployeeRead, status_code=201)
def register_employee(
    payload: EmployeeCreate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    if payload.password:
        email_lower = payload.email.lower()
        existing = db.query(Employee).filter(Employee.email == email_lower).first()
        if existing:
            raise InvalidStateError("The provided company email is already associated with an existing account.")
    else:
        email_lower = None

    if payload.phone:
        existing_phone = db.query(Employee).filter(Employee.phone == payload.phone).first()
        if existing_phone:
            raise InvalidStateError("The provided phone number is already associated with an existing account.")

    if payload.personal_email:
        pe = payload.personal_email.strip().lower()
        taken = db.query(Employee).filter(Employee.personal_email == pe).first()
        if taken:
            raise InvalidStateError("The provided personal email is already associated with an existing account.")

    if current_user.role == EmployeeRole.SUPER_ADMIN:
        resolved_organization_id = payload.organization_id or current_user.organization_id
    else:
        resolved_organization_id = current_user.organization_id
    if not resolved_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required (set on your account or provide it as a super admin).",
        )

    # Prefer branch_id; if UI sends branch name, resolve it to a branch_id in this organization.
    resolved_branch_id = payload.branch_id
    if not resolved_branch_id and payload.branch:
        branch_name = payload.branch.strip()
        if branch_name:
            branch_obj = (
                db.query(Branch)
                .filter(
                    Branch.organization_id == resolved_organization_id,
                    Branch.branch_name == branch_name,
                )
                .first()
            )
            if not branch_obj:
                raise HTTPException(status_code=400, detail="Invalid branch (no such branch in your organization)")
            resolved_branch_id = branch_obj.branch_id
    if resolved_branch_id:
        branch_obj = db.query(Branch).filter(Branch.branch_id == resolved_branch_id).first()
        if not branch_obj:
            raise HTTPException(status_code=400, detail="Invalid branch_id")
        if branch_obj.organization_id != resolved_organization_id:
            raise HTTPException(status_code=400, detail="branch_id does not belong to the selected organization")
    if current_user.role == EmployeeRole.HR:
        if current_user.branch_id and resolved_branch_id and resolved_branch_id != current_user.branch_id:
            raise HTTPException(status_code=403, detail="HR can register employees only in their own branch")
        if current_user.branch_id and not resolved_branch_id:
            resolved_branch_id = current_user.branch_id

    # Role Population Constraints
    # 1. Global Admin Limit
    if payload.role == EmployeeRole.SUPER_ADMIN:
        admin_count = db.query(Employee).filter(Employee.role == EmployeeRole.SUPER_ADMIN, Employee.is_active == True).count()
        if admin_count >= 1:
            raise HTTPException(status_code=400, detail="A Global System Administrator already exists. Only 1 Admin is allowed.")

    # 2. Branch-specific limits
    if payload.role in [EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR]:
        if not resolved_branch_id:
            raise HTTPException(status_code=400, detail="branch_id is required for manager/hr/support_team roles")
        current_count = db.query(Employee).filter(
            Employee.branch_id == resolved_branch_id,
            Employee.role == payload.role,
            Employee.is_active == True
        ).count()
        
        if payload.role == EmployeeRole.MANAGER and current_count >= 1:
            raise HTTPException(status_code=400, detail=f"Branch already has a Manager. Only 1 is allowed per branch.")
        if payload.role == EmployeeRole.SUPPORT_TEAM and current_count >= 5:
            raise HTTPException(status_code=400, detail=f"Branch already has a Support Team member. Only 1 is allowed per branch.")
        if payload.role == EmployeeRole.HR and current_count >= 3:
            raise HTTPException(status_code=400, detail=f"Branch already has 3 HR members. Only 3 are allowed per branch.")

    # Enforcement: Singleton Manager per Branch
    if payload.role == EmployeeRole.MANAGER:
        existing_manager = db.query(Employee).filter(
            Employee.branch_id == resolved_branch_id,
            Employee.role == EmployeeRole.MANAGER,
            Employee.is_active == True
        ).first()
        if existing_manager:
            raise InvalidStateError("A manager already exists for this branch.")

    temp_pw_for_mail: str | None = None
    if payload.password:
        user = Employee(
            name=payload.name,
            email=email_lower,
            personal_email=(payload.personal_email.strip().lower() if payload.personal_email else None),
            phone=payload.phone,
            organization_id=resolved_organization_id,
            branch_id=resolved_branch_id,
            role=payload.role,
            password_hash=get_password_hash(payload.password),
            password_reset_required=False,
            is_active=True,
        )
    else:
        org = db.query(Organization).filter(Organization.organization_id == resolved_organization_id).first()
        company_email = generate_company_email(payload.name, db, org.domain if org else None)
        temp_pw_for_mail = generate_temp_password()
        user = Employee(
            name=payload.name,
            email=company_email,
            personal_email=payload.personal_email.strip().lower(),
            phone=payload.phone,
            organization_id=resolved_organization_id,
            branch_id=resolved_branch_id,
            role=payload.role,
            password_hash=get_password_hash(temp_pw_for_mail),
            password_reset_required=True,
            is_active=True,
        )
    db.add(user)
    db.flush()

    # Assign default role permissions for all permission flags.
    default_perms = get_default_permission_flags(user.role)
    default_json = create_default_permissions(user.role)
    user.permissions = EmployeePermission(
        employee_id=user.employee_id,
        organization_id=user.organization_id,
        branch_id=user.branch_id,
        permissions_json=default_json,
        **default_perms
    )
    db.add(user.permissions)
    db.flush()


    if temp_pw_for_mail:
        EmailService.send_provisioning_credentials(user.personal_email, user.name, user.email, temp_pw_for_mail)

    asset_ids = list(payload.onboarding_asset_ids)

    if payload.preset_id:
        preset_query = db.query(OnboardingPreset).filter(OnboardingPreset.preset_id == payload.preset_id)
        if current_user.role != EmployeeRole.SUPER_ADMIN:
            preset_query = preset_query.filter(OnboardingPreset.organization_id == resolved_organization_id)
        preset = preset_query.first()
        if not preset:
            raise HTTPException(status_code=404, detail="Onboarding preset not found")

        if preset.target_role and preset.target_role != user.role.value:
            raise HTTPException(status_code=400, detail="Selected onboarding preset is not valid for the employee role")

        if preset.branch:
            if not resolved_branch_id:
                raise HTTPException(status_code=400, detail="Selected onboarding preset requires a branch")
            branch_obj = db.query(Branch).filter(Branch.branch_id == resolved_branch_id).first()
            if not branch_obj or branch_obj.branch_name != preset.branch:
                raise HTTPException(status_code=400, detail="Selected onboarding preset does not match employee branch")

        asset_ids = list(dict.fromkeys([*asset_ids, *(preset.asset_ids or [])]))

    if asset_ids:
        from app.server.schema.tracking import AllocationType

        for aid in asset_ids:
            try:
                StockService.allocate_asset(db, aid, user.employee_id, AllocationType.PERMANENT, current_user, "ONBOARDING_PACKAGE")
            except Exception:
                pass

    db.commit()
    db.refresh(user)
    return user

@router.get("/", response_model=EmployeeListResponse)
def list_employees(
    search: Optional[str]=None,
    status: Optional[str]=None,
    branch_id: Optional[str]=None,
    organization_id: Optional[str]=None,
    role: Optional[EmployeeRole]=None,
    page: int = 1,
    per_page: int = 20,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    if not _can_view_employee_directory(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions to view employees.")

    query=apply_tenant_filter(db.query(Employee), current_user, Employee)

    status_value = (status or "active").strip().lower()
    if status_value == "active":
        query = query.filter(Employee.is_active == True)
    elif status_value == "inactive":
        query = query.filter(Employee.is_active == False)
    elif status_value == "all":
        pass
    else:
        raise HTTPException(status_code=400, detail="status must be one of: active, inactive, all")
    
    if current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM] and current_user.branch_id:
        query = query.filter(Employee.branch_id == current_user.branch_id)
    
    if branch_id:
        query=query.filter(Employee.branch_id==branch_id)
    if organization_id and current_user.role == EmployeeRole.SUPER_ADMIN:
        query=query.filter(Employee.organization_id==organization_id)
    if role:
        query=query.filter(Employee.role==role)
        
    if search:
        search_filter = f"%{search}%"
        query = query.join(Branch, isouter=True).join(Organization, isouter=True).filter(
            or_(
                Employee.name.ilike(search_filter),
                Employee.email.ilike(search_filter),
                Employee.phone.ilike(search_filter),
                Employee.role.cast(String).ilike(search_filter),
                Branch.branch_name.ilike(search_filter),
                Organization.organization_name.ilike(search_filter)
            )
        )
        
    total = query.count()
    items = query.order_by(Employee.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }


@router.get("/filter-options", response_model=EmployeeFilterOptions)
def get_employee_filter_options(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if not _can_view_employee_directory(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions to view employees.")

    query = apply_tenant_filter(db.query(Employee), current_user, Employee)
    statuses = query.with_entities(Employee.is_active).distinct().all()
    roles = query.with_entities(Employee.role).distinct().all()

    status_values = ["active" if row[0] else "inactive" for row in statuses if row[0] is not None]
    role_values = [row[0].value if hasattr(row[0], "value") else str(row[0]) for row in roles if row[0] is not None]

    return {
        "statuses": sorted(set(status_values)),
        "roles": sorted(set(role_values)),
    }


@router.get("/permissions/catalog", response_model=PermissionCatalogResponse)
def get_permissions_catalog(
    current_user: Employee = Depends(get_current_user),
):
    if not _can_view_employee_directory(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions to view permission catalog.")
    return {"modules": get_permission_catalog()}


@router.get("/{emp_id}", response_model=EmployeeRead)
def get_employee(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM))
):
    emp=apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id==emp_id).first()
    if not emp:
        raise ResourceNotFoundError("Employee", emp_id)
    return emp


@router.put("/{emp_id}", response_model=EmployeeRead)
def update_employee(
    emp_id: str,
    payload: EmployeeUpdate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    target = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if target.role == EmployeeRole.SUPER_ADMIN and current_user.role != EmployeeRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super admin can edit super admin users")

    if payload.organization_id and current_user.role != EmployeeRole.SUPER_ADMIN:
        payload.organization_id = current_user.organization_id

    old_org_id = target.organization_id
    old_branch_id = target.branch_id

    if payload.organization_id:
        org = db.query(Organization).filter(Organization.organization_id == payload.organization_id).first()
        if not org:
            raise HTTPException(status_code=400, detail="Invalid organization_id")
        target.organization_id = payload.organization_id

    if payload.branch_id:
        branch = db.query(Branch).filter(Branch.branch_id == payload.branch_id).first()
        if not branch:
            raise HTTPException(status_code=400, detail="Invalid branch_id")
        if target.organization_id and branch.organization_id != target.organization_id:
            raise HTTPException(status_code=400, detail="branch_id does not belong to employee organization")
        target.branch_id = payload.branch_id

    if payload.name is not None:
        target.name = payload.name
    if payload.personal_email is not None:
        existing_personal = db.query(Employee).filter(
            Employee.personal_email == payload.personal_email,
            Employee.employee_id != emp_id,
        ).first()
        if existing_personal:
            raise HTTPException(status_code=400, detail="personal_email already in use")
        target.personal_email = payload.personal_email
    if payload.phone is not None:
        existing_phone = db.query(Employee).filter(
            Employee.phone == payload.phone,
            Employee.employee_id != emp_id,
        ).first()
        if existing_phone:
            raise HTTPException(status_code=400, detail="phone already in use")
        target.phone = payload.phone
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active

    if old_org_id != target.organization_id:
        AuditService.log_change(
            db,
            table_name="employees",
            record_id=target.employee_id,
            action="UPDATE",
            user=current_user,
            old_values={"organization_id": old_org_id},
            new_values={"organization_id": target.organization_id},
            reason="EMPLOYEE_ORGANIZATION_CHANGED",
        )
    if old_branch_id != target.branch_id:
        AuditService.log_change(
            db,
            table_name="employees",
            record_id=target.employee_id,
            action="UPDATE",
            user=current_user,
            old_values={"branch_id": old_branch_id},
            new_values={"branch_id": target.branch_id},
            reason="EMPLOYEE_BRANCH_CHANGED",
        )

    db.commit()
    db.refresh(target)
    return target

@router.post("/{emp_id}/deactivate")
def deactivate_employee(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    target=apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id==emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if target.role == EmployeeRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="The Global System Administrator is a singleton and cannot be deactivated.")

    return EmployeeLifecycleService.deactivate_and_recover_assets(db, emp_id, current_user, "OFFBOARDING_RECOVERY")

@router.get("/{emp_id}/assets", response_model=EmployeeAssetListResponse)
def get_employee_assets(
    emp_id: str,
    search: Optional[str] = None,
    status: Optional[str] = None,
    branch: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE))
):
    if current_user.role==EmployeeRole.EMPLOYEE and current_user.employee_id!=emp_id:
        raise ResourceNotFoundError("Employee", emp_id)
    return EmployeeAssetService.get_employee_assets(
        db=db,
        current_user=current_user,
        employee_id=emp_id,
        search=search,
        status=status,
        branch=branch,
        category=category,
        page=page,
        per_page=per_page,
    )


@router.get("/{emp_id}/assets/options", response_model=EmployeeAssetFilterOptions)
def get_employee_asset_filter_options(
    emp_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)),
):
    if current_user.role == EmployeeRole.EMPLOYEE and current_user.employee_id != emp_id:
        raise ResourceNotFoundError("Employee", emp_id)

    emp = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not emp:
        raise ResourceNotFoundError("Employee", emp_id)

    scoped = (
        apply_tenant_filter(db.query(Tracking), current_user, Tracking)
        .join(AssetInstance, Tracking.instance_id == AssetInstance.instance_id)
        .join(Asset, AssetInstance.asset_id == Asset.asset_id)
        .join(Category, Asset.category_id == Category.category_id, isouter=True)
        .join(Branch, AssetInstance.branch_id == Branch.branch_id, isouter=True)
        .filter(Tracking.emp_id == emp_id, Tracking.returned_at == None, Tracking.instance_id.isnot(None))
    )

    rows = scoped.with_entities(AssetInstance.status, Branch.branch_name, Category.category_name).distinct().all()
    statuses = sorted({r[0].value if hasattr(r[0], "value") else str(r[0]) for r in rows if r[0]})
    branches = sorted({(r[1] or "").strip() for r in rows if r[1]})
    categories = sorted({(r[2] or "").strip() for r in rows if r[2]})

    required_states = ["NEW", "AVAILABLE", "ASSIGNED", "IN_REPAIR", "NOT_USABLE", "RETIRED"]
    statuses = sorted(set(statuses + required_states))
    return {"statuses": statuses, "branches": branches, "categories": categories}


@router.get("/{emp_id}/assets/history", response_model=EmployeeAssetHistoryResponse)
def get_employee_asset_history(
    emp_id: str,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)),
):
    if current_user.role == EmployeeRole.EMPLOYEE and current_user.employee_id != emp_id:
        raise ResourceNotFoundError("Employee", emp_id)
    return EmployeeAssetService.get_employee_asset_history(
        db=db,
        current_user=current_user,
        employee_id=emp_id,
        page=page,
        per_page=per_page,
    )


@router.post("/{emp_id}/assets/bulk-assign", response_model=EmployeeAssetBulkAssignResponse)
def bulk_assign_employee_assets(
    emp_id: str,
    payload: EmployeeAssetBulkAssignRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM)),
):
    reason = (payload.reason or "BULK_ASSIGNMENT").strip() or "BULK_ASSIGNMENT"
    allocation_type_value = (payload.allocation_type or "PERMANENT").strip().upper()
    allocation_type = AllocationType.PERMANENT if allocation_type_value != AllocationType.TEMPORARY.value else AllocationType.TEMPORARY
    return EmployeeAssetService.bulk_assign_assets(
        db=db,
        current_user=current_user,
        employee_id=emp_id,
        instance_ids=payload.instance_ids,
        reason=reason,
        allocation_type=allocation_type,
    )


@router.get("/{emp_id}/assets/analytics", response_model=EmployeeAssetOwnershipAnalyticsResponse)
def get_employee_asset_analytics(
    emp_id: str,
    overdue_days: int = 30,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.HR, EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE)),
):
    if current_user.role == EmployeeRole.EMPLOYEE and current_user.employee_id != emp_id:
        raise ResourceNotFoundError("Employee", emp_id)
    return EmployeeAssetService.get_ownership_analytics(
        db=db,
        current_user=current_user,
        employee_id=emp_id,
        overdue_days=overdue_days,
    )

@router.get("/{emp_id}/permissions", response_model=EmployeePermissionRead)
def get_employee_permissions(
    emp_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_permission("users", "permissions"))
):
    target = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if not target.permissions:
        default_perms = get_default_permission_flags(target.role)
        default_json = create_default_permissions(target.role)
        target.permissions = EmployeePermission(
            employee_id=target.employee_id,
            organization_id=target.organization_id,
            branch_id=target.branch_id,
            permissions_json=default_json,
            **default_perms,
        )
        db.add(target.permissions)
        db.commit()
        db.refresh(target)
    elif not isinstance(target.permissions.permissions_json, dict):
        target.permissions.permissions_json = create_default_permissions(target.role)
        db.add(target.permissions)
        db.commit()
        db.refresh(target.permissions)

    return {
        "employee_id": target.employee_id,
        "permissions_json": get_effective_permissions(target),
        "temporary_permissions_json": target.permissions.temporary_permissions_json or {},
        "valid_from": target.permissions.valid_from,
        "valid_until": target.permissions.valid_until,
    }

@router.put("/{emp_id}/permissions", response_model=EmployeePermissionRead)
def update_employee_permissions(
    emp_id: str,
    payload: EmployeePermissionUpdate,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_permission("users", "permissions"))
):
    target = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == emp_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", emp_id)

    if current_user.employee_id == emp_id:
        raise HTTPException(status_code=403, detail="You cannot edit your own permissions.")

    if current_user.role == EmployeeRole.ORG_ADMIN:
        if target.role == EmployeeRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Organization Admin cannot modify permissions of a Global Admin.")

    if not target.permissions:
        default_perms = get_default_permission_flags(target.role)
        default_json = create_default_permissions(target.role)
        target.permissions = EmployeePermission(
            employee_id=target.employee_id,
            organization_id=target.organization_id,
            branch_id=target.branch_id,
            permissions_json=default_json,
            **default_perms,
        )
        db.add(target.permissions)

    payload_dict = payload.model_dump(exclude_unset=True)
    permissions_json = payload_dict.get("permissions_json", {})
    temporary_permissions_json = payload_dict.get("temporary_permissions_json", {})
    valid_from = payload_dict.get("valid_from")
    valid_until = payload_dict.get("valid_until")
    if not isinstance(permissions_json, dict):
        raise HTTPException(status_code=400, detail="permissions_json must be an object")
    if not isinstance(temporary_permissions_json, dict):
        raise HTTPException(status_code=400, detail="temporary_permissions_json must be an object")
    if valid_from and valid_until and valid_from > valid_until:
        raise HTTPException(status_code=400, detail="valid_from must be earlier than valid_until")

    normalized_permissions: dict[str, dict[str, bool]] = {}
    for module, actions in permissions_json.items():
        if not isinstance(actions, dict):
            continue
        module_key = str(module).strip()
        if not module_key:
            continue
        normalized_permissions[module_key] = {
            str(action).strip(): bool(allowed)
            for action, allowed in actions.items()
            if str(action).strip()
        }

    normalized_temporary_permissions: dict[str, dict[str, bool]] = {}
    for module, actions in temporary_permissions_json.items():
        if not isinstance(actions, dict):
            continue
        module_key = str(module).strip()
        if not module_key:
            continue
        normalized_temporary_permissions[module_key] = {
            str(action).strip(): bool(allowed)
            for action, allowed in actions.items()
            if str(action).strip()
        }

    old_permissions_json = target.permissions.permissions_json or {}
    old_temporary_permissions_json = target.permissions.temporary_permissions_json or {}
    old_valid_from = target.permissions.valid_from
    old_valid_until = target.permissions.valid_until

    target.permissions.permissions_json = normalized_permissions
    target.permissions.temporary_permissions_json = normalized_temporary_permissions
    target.permissions.valid_from = valid_from
    target.permissions.valid_until = valid_until
    for flag, value in permission_json_to_legacy_flags(normalized_permissions).items():
        setattr(target.permissions, flag, value)

    AuditService.log_change(
        db,
        table_name="employee_permissions",
        record_id=str(target.permissions.id or target.employee_id),
        action="UPDATE",
        user=current_user,
        old_values={
            "permissions_json": old_permissions_json,
            "temporary_permissions_json": old_temporary_permissions_json,
            "valid_from": old_valid_from.isoformat() if old_valid_from else None,
            "valid_until": old_valid_until.isoformat() if old_valid_until else None,
        },
        new_values={
            "permissions_json": normalized_permissions,
            "temporary_permissions_json": normalized_temporary_permissions,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
        },
        reason="PERMISSION_UPDATED",
    )
        
    db.commit()
    db.refresh(target.permissions)
    return {
        "employee_id": target.employee_id,
        "permissions_json": get_effective_permissions(target),
        "temporary_permissions_json": target.permissions.temporary_permissions_json or {},
        "valid_from": target.permissions.valid_from,
        "valid_until": target.permissions.valid_until,
    }


@me_router.get("/permissions", response_model=EmployeePermissionRead)
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    target = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == current_user.employee_id).first()
    if not target:
        raise ResourceNotFoundError("Employee", current_user.employee_id)

    if not target.permissions:
        default_perms = get_default_permission_flags(target.role)
        default_json = create_default_permissions(target.role)
        target.permissions = EmployeePermission(
            employee_id=target.employee_id,
            organization_id=target.organization_id,
            branch_id=target.branch_id,
            permissions_json=default_json,
            **default_perms,
        )
        db.add(target.permissions)
        db.commit()
        db.refresh(target.permissions)

    return {
        "employee_id": target.employee_id,
        "permissions_json": get_effective_permissions(target),
        "temporary_permissions_json": target.permissions.temporary_permissions_json or {},
        "valid_from": target.permissions.valid_from,
        "valid_until": target.permissions.valid_until,
    }


@me_router.get("/assets", response_model=EmployeeAssetListResponse)
def get_my_assets(
    search: Optional[str] = None,
    status: Optional[str] = None,
    branch: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    return get_employee_assets(
        emp_id=current_user.employee_id,
        search=search,
        status=status,
        branch=branch,
        category=category,
        page=page,
        per_page=per_page,
        db=db,
        current_user=current_user,
    )


@me_router.get("/requests", response_model=RequestListResponse)
def get_my_requests(
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    query = apply_tenant_filter(db.query(Request), current_user, Request).filter(Request.emp_id == current_user.employee_id)
    if status:
        query = query.filter(func.lower(Request.status) == status.strip().lower())

    total = query.count()
    items = (
        query.order_by(Request.req_date.desc())
        .offset((max(1, page) - 1) * max(1, per_page))
        .limit(max(1, per_page))
        .all()
    )

    return {
        "page": max(1, page),
        "per_page": max(1, per_page),
        "total": total,
        "items": items,
    }
