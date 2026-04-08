from sqlalchemy.orm import Session, Query
from typing import Type, TypeVar
from app.server.schema.employee import Employee, EmployeeRole

T = TypeVar("T")

def apply_tenant_filter(query: Query, current_user: Employee, model: Type[T]) -> Query:
    """
    Applies the organization_id filter if the current user is not a SUPER_ADMIN.
    Expects the model to have an organization_id column.
    """
    if current_user.role == EmployeeRole.SUPER_ADMIN:
        return query
        
    if hasattr(model, 'organization_id'):
        # ORG_ADMIN and below must only see their own organization data
        return query.filter(model.organization_id == current_user.organization_id)
        
    return query
