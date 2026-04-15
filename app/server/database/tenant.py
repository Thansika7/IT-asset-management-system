from dataclasses import dataclass
from sqlalchemy.orm import Query
from typing import Type, TypeVar
from app.server.schema.employee import Employee, EmployeeRole

T = TypeVar("T")


@dataclass(frozen=True)
class TenantContext:
    organization_id: str | None
    branch_id: str | None
    role: EmployeeRole


BRANCH_SCOPED_ROLES = {
    EmployeeRole.HR,
    EmployeeRole.SUPPORT_TEAM,
    EmployeeRole.EMPLOYEE,
}


def build_tenant_context(current_user: Employee) -> TenantContext:
    return TenantContext(
        organization_id=current_user.organization_id,
        branch_id=current_user.branch_id,
        role=current_user.role,
    )


def apply_org_filter(query: Query, current_user: Employee, model: Type[T]) -> Query:
    if current_user.role == EmployeeRole.SUPER_ADMIN:
        return query
    if hasattr(model, "organization_id"):
        return query.filter(model.organization_id == current_user.organization_id)
    return query


def apply_branch_filter(query: Query, current_user: Employee, model: Type[T], allow_cross_branch: bool = False) -> Query:
    """
    Applies branch scope for branch-restricted roles.

    SUPER_ADMIN and ORG_ADMIN can see all branches within org scope.
    HR, SUPPORT_TEAM and EMPLOYEE are restricted to their branch (when model supports branch_id).
    MANAGER can view all branches within org scope.
    unless allow_cross_branch=True.
    """
    if current_user.role in {EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN}:
        return query
    if allow_cross_branch:
        return query
    if current_user.role in BRANCH_SCOPED_ROLES and hasattr(model, "branch_id") and current_user.branch_id:
        return query.filter(model.branch_id == current_user.branch_id)
    return query

def apply_tenant_filter(query: Query, current_user: Employee, model: Type[T], allow_cross_branch: bool = False) -> Query:
    """
    Applies the organization_id filter if the current user is not a SUPER_ADMIN.
    Expects the model to have an organization_id column.
    """
    query = apply_org_filter(query, current_user, model)
    query = apply_branch_filter(query, current_user, model, allow_cross_branch=allow_cross_branch)
    return query
