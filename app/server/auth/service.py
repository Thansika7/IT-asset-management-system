import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.models.api import TokenPayload
from app.server.schema import Employee, EmployeeRole

load_dotenv()

SECRET_KEY=os.getenv("SECRET_KEY")
ALGORITHM=os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

pwd_context=CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/token")

ROLE_PERMISSIONS={
    EmployeeRole.ADMIN: {
        "system:full_access",
        "requests:override",
        "requests:approve",
        "assets:allocate",
        "assets:track",
        "assets:transfer",
        "stock:manage",
        "employees:manage",
        "licenses:track",
        "warranty:track",
    },
    EmployeeRole.MANAGER: {
        "requests:approve",
        "requests:review",
        "assets:track",
        "stock:manage",
        "team_assets:view",
    },
    EmployeeRole.HR: {
        "employees:manage",
        "assets:branch_view",
        "licenses:track",
        "warranty:track",
    },
    EmployeeRole.SUPPORT_TEAM: {
        "assets:allocate",
        "assets:track",
        "assets:transfer",
        "stock:manage",
        "licenses:track",
        "warranty:track",
    },
    EmployeeRole.EMPLOYEE: {
        "requests:create",
        "requests:view_own",
        "assets:view_assigned",
        "history:view_own",
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> Optional[Employee]:
    user=db.query(Employee).filter(Employee.email==email).first()
    if not user or not user.password_hash or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(subject: str, role: EmployeeRole) -> str:
    expire=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload={
        "sub": subject,
        "role": role.value,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def update_last_login(db: Session, user: Employee) -> None:
    user.last_login_at=datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)


def get_current_user(token: str=Depends(oauth2_scheme), db: Session=Depends(get_db)) -> Employee:
    credentials_exception=HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_data=TokenPayload(**payload)
    except (JWTError, ValueError):
        raise credentials_exception

    user=db.query(Employee).filter(Employee.email==token_data.sub).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*allowed_roles: EmployeeRole):
    allowed={role.value for role in allowed_roles}

    def role_checker(current_user: Employee=Depends(get_current_user)) -> Employee:
        if current_user.role.value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return role_checker


def get_role_permissions(role: EmployeeRole) -> set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def require_permissions(*permissions: str):
    required=set(permissions)

    def permission_checker(current_user: Employee=Depends(get_current_user)) -> Employee:
        user_permissions=get_role_permissions(current_user.role)
        if not required.issubset(user_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return permission_checker


def create_oauth_user(
    db: Session,
    *,
    name: str,
    email: str,
    oauth_provider: str,
    oauth_subject: str,
    branch: Optional[str]=None,
    phone: Optional[str]=None,
    role: EmployeeRole=EmployeeRole.EMPLOYEE,
) -> Employee:
    existing=db.query(Employee).filter(Employee.email==email).first()
    if existing:
        return existing

    user=Employee(
        name=name,
        email=email,
        phone=phone,
        branch=branch,
        role=role,
        oauth_provider=oauth_provider,
        oauth_subject=oauth_subject,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
