from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.models.api import TokenPayload
from app.server.schema.employee import Employee, EmployeeRole

load_dotenv()

SECRET_KEY=os.getenv("SECRET_KEY", "dev_secret_key_change_me_in_production")
ALGORITHM=os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

pwd_context=CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ROLE_PERMISSIONS={
    EmployeeRole.SUPER_ADMIN: {
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
    EmployeeRole.ORG_ADMIN: {
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

DEFAULT_ROLE_PERMISSIONS = {
    EmployeeRole.SUPER_ADMIN: {
        "can_view_assets": True, "can_create_assets": True, "can_update_assets": True, "can_delete_assets": True,
        "can_create_request": True, "can_approve_request": True, "can_reject_request": True,
        "can_view_finance": True, "can_manage_finance": True,
        "can_view_tracking": True, "can_allocate_asset": True, "can_transfer_asset": True,
        "can_view_branch": True, "can_create_branch": True, "can_update_branch": True,
        "can_view_reports": True,
        "can_manage_users": True, "can_manage_permissions": True
    },
    EmployeeRole.ORG_ADMIN: {
        "can_view_assets": True, "can_create_assets": True, "can_update_assets": True, "can_delete_assets": True,
        "can_create_request": True, "can_approve_request": True, "can_reject_request": True,
        "can_view_finance": True, "can_manage_finance": True,
        "can_view_tracking": True, "can_allocate_asset": True, "can_transfer_asset": True,
        "can_view_branch": True, "can_create_branch": True, "can_update_branch": True,
        "can_view_reports": True,
        "can_manage_users": True, "can_manage_permissions": True
    },
    EmployeeRole.HR: {
        "can_view_assets": True, "can_view_branch": True, "can_manage_users": True, "can_view_reports": True
    },
    EmployeeRole.MANAGER: {
        "can_approve_request": True, "can_reject_request": True, "can_view_tracking": True, "can_view_reports": True
    },
    EmployeeRole.SUPPORT_TEAM: {
        "can_view_assets": True, "can_view_tracking": True, "can_allocate_asset": True, "can_transfer_asset": True, "can_update_assets": True
    },
    EmployeeRole.EMPLOYEE: {
        "can_create_request": True
    }
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> Employee | None:
    email_lower=email.lower()
    user=db.query(Employee).filter(Employee.email==email_lower, Employee.is_active==True).first()
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(
    subject: str,
    role: EmployeeRole,
    *,
    employee_id: Optional[str] = None,
    branch: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> str:
    expire=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload={
        "sub": subject,
        "role": role.value,
        "exp": expire,
    }
    if employee_id:
        payload["emp_id"] = employee_id
    if branch:
        payload["branch"] = branch
    if organization_id:
        payload["organization_id"] = organization_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def update_last_login(db: Session, user: Employee) -> None:
    user.last_login_at=datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)


def get_token_from_header_or_cookie(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme)
) -> str:
    if token:
        return token
    
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]
        return cookie_token
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_current_user(token: str=Depends(get_token_from_header_or_cookie), db: Session=Depends(get_db)) -> Employee:
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

    user=db.query(Employee).filter(Employee.email==token_data.sub.lower()).first()
    if not user or not user.is_active:
        raise credentials_exception
        
    if user.organization and user.role.value != "super_admin":
        from app.server.schema.organization import SubscriptionStatus
        if user.organization.subscription_status == SubscriptionStatus.INACTIVE:
            raise HTTPException(
                status_code=403,
                detail="Organization subscription is inactive. Contact support."
            )
            
    return user


def get_role_permissions(role: EmployeeRole) -> Set[str]:
    return ROLE_PERMISSIONS.get(role, set())


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
    email_lower=email.lower()
    existing=db.query(Employee).filter(Employee.email==email_lower).first()
    if existing:
        return existing

    user=Employee(
        name=name,
        email=email_lower,
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


def create_password_reset_token(email: str) -> str:
    """Create a password reset token that expires in 1 hour"""
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": email.lower(),
        "type": "password_reset",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify password reset token and return email if valid"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def generate_random_password(length: int = 12) -> str:
    """Generate a random password with mixed characters"""
    import secrets
    import string
    
    # Ensure at least one of each required character type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    
    # Fill the rest randomly
    remaining_length = length - len(password)
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password.extend(secrets.choice(all_chars) for _ in range(remaining_length))
    
    # Shuffle to avoid predictable patterns
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)
