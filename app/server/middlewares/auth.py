from fastapi import Depends
from app.server.auth.service import get_current_user
from app.server.exceptions.base import UnauthorizedActionError
from app.server.schema.employee import Employee, EmployeeRole

def require_roles(*allowed_roles: EmployeeRole):
    allowed={role.value for role in allowed_roles}

    def role_checker(current_user: Employee=Depends(get_current_user)) -> Employee:
        if current_user.role.value not in allowed:
            raise UnauthorizedActionError()
        return current_user

    return role_checker
