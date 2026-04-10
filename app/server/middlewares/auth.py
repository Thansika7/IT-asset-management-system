from fastapi import Depends, Request
from app.server.auth.service import get_current_user, has_permission
from app.server.database.tenant import TenantContext, build_tenant_context
from app.server.exceptions.base import UnauthorizedActionError
from app.server.schema.employee import Employee, EmployeeRole

PERMISSION_FLAG_TO_JSON_PATH = {
    "can_view_assets": ("assets", "view"),
    "can_create_assets": ("assets", "create"),
    "can_update_assets": ("assets", "update"),
    "can_delete_assets": ("assets", "delete"),
    "can_create_request": ("requests", "create"),
    "can_approve_request": ("requests", "approve"),
    "can_reject_request": ("requests", "reject"),
    "can_view_finance": ("finance", "view"),
    "can_manage_finance": ("finance", "manage"),
    "can_view_tracking": ("tracking", "view"),
    "can_allocate_asset": ("tracking", "allocate"),
    "can_transfer_asset": ("tracking", "transfer"),
    "can_view_branch": ("branches", "view"),
    "can_create_branch": ("branches", "create"),
    "can_update_branch": ("branches", "update"),
    "can_view_reports": ("reports", "view"),
    "can_manage_users": ("users", "manage"),
    "can_manage_permissions": ("users", "permissions"),
}


def require_permission(module: str, action: str):
    def permission_checker(current_user: Employee = Depends(get_current_user)) -> Employee:
        if has_permission(current_user, module, action):
            return current_user
        raise UnauthorizedActionError()

    return permission_checker


def require_module_access(module: str):
    """
    Enforce module-level API access using JSON permissions.

    Maps HTTP methods to actions while preserving backward compatibility:
    - GET/HEAD/OPTIONS -> view
    - POST -> create
    - PUT/PATCH -> edit
    - DELETE -> delete
    If the mapped action fails, mutating methods fall back to any granted action
    inside the module to avoid breaking existing role-only workflows.
    """

    method_to_action = {
        "GET": "view",
        "HEAD": "view",
        "OPTIONS": "view",
        "POST": "create",
        "PUT": "edit",
        "PATCH": "edit",
        "DELETE": "delete",
    }

    def module_checker(
        request: Request,
        current_user: Employee = Depends(get_current_user),
    ) -> Employee:
        action = method_to_action.get(request.method.upper(), "view")
        if has_permission(current_user, module, action):
            return current_user

        # Compatibility fallback for legacy flows where routes are role-guarded
        # but JSON action granularity may not yet be fully populated.
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            fallback_actions = ("manage", "update", "edit", "create", "approve", "triage", "execute", "view")
            for candidate in fallback_actions:
                if has_permission(current_user, module, candidate):
                    return current_user

        raise UnauthorizedActionError()

    return module_checker

def require_roles(*allowed_roles: EmployeeRole):
    allowed={role.value for role in allowed_roles}

    def role_checker(current_user: Employee=Depends(get_current_user)) -> Employee:
        if current_user.role.value not in allowed:
            raise UnauthorizedActionError()
        return current_user

    return role_checker

def RequirePermission(permission_flag: str):
    def permission_checker(current_user: Employee = Depends(get_current_user)) -> Employee:
        path = PERMISSION_FLAG_TO_JSON_PATH.get(permission_flag)
        if path and has_permission(current_user, path[0], path[1]):
            return current_user

        # Backward-compatibility fallback for still-populated legacy rows.
        if current_user.permissions and getattr(current_user.permissions, permission_flag, False):
                return current_user
        
        raise UnauthorizedActionError()
    return permission_checker


def get_tenant_context(current_user: Employee = Depends(get_current_user)) -> TenantContext:
    """Extract tenant context from authenticated JWT/session user."""
    return build_tenant_context(current_user)

