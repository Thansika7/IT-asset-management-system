from __future__ import annotations

import os
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
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

ROLE_PERMISSION_TO_FLAGS = {
    "system:full_access": {
        "can_view_assets",
        "can_create_assets",
        "can_update_assets",
        "can_delete_assets",
        "can_create_request",
        "can_approve_request",
        "can_reject_request",
        "can_view_finance",
        "can_manage_finance",
        "can_view_tracking",
        "can_allocate_asset",
        "can_transfer_asset",
        "can_view_branch",
        "can_create_branch",
        "can_update_branch",
        "can_view_reports",
        "can_manage_users",
        "can_manage_permissions",
    },
    "requests:create": {"can_create_request"},
    "requests:approve": {"can_approve_request", "can_reject_request"},
    "requests:review": {"can_approve_request", "can_reject_request"},
    "requests:override": {"can_approve_request", "can_reject_request"},
    "assets:allocate": {"can_allocate_asset", "can_view_assets"},
    "assets:track": {"can_view_tracking", "can_view_assets"},
    "assets:transfer": {"can_transfer_asset", "can_view_tracking"},
    "assets:branch_view": {"can_view_assets", "can_view_branch"},
    "assets:view_assigned": {"can_view_assets"},
    "stock:manage": {"can_view_assets", "can_create_assets", "can_update_assets"},
    "employees:manage": {"can_manage_users"},
    "licenses:track": {"can_view_reports"},
    "warranty:track": {"can_view_reports"},
    "team_assets:view": {"can_view_assets"},
    "history:view_own": {"can_view_tracking"},
}


ROLE_HIERARCHY = [
    EmployeeRole.EMPLOYEE,
    EmployeeRole.SUPPORT_TEAM,
    EmployeeRole.HR,
    EmployeeRole.MANAGER,
    EmployeeRole.ORG_ADMIN,
    EmployeeRole.SUPER_ADMIN,
]


def _normalize_permission_token(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


@lru_cache(maxsize=64)
def _inherited_role_defaults(role: EmployeeRole) -> dict[str, dict[str, bool]]:
    """Higher roles inherit all lower-role defaults from the defined hierarchy."""
    try:
        rank = ROLE_HIERARCHY.index(role)
    except ValueError:
        rank = 0

    merged: dict[str, dict[str, bool]] = {}
    for inherited_role in ROLE_HIERARCHY[: rank + 1]:
        role_defaults = _normalize_permission_map(get_default_permission_json(inherited_role))
        merged = _merge_permission_maps(merged, role_defaults)
    return merged


def get_default_permission_json(role: EmployeeRole) -> dict:
    """Return a scoped JSON permission map for the given role."""
    if role == EmployeeRole.SUPER_ADMIN:
        return {
            "assets": {"view": True, "create": True, "update": True, "delete": True},
            "requests": {"view": True, "create": True, "approve": True, "reject": True, "triage": True},
            "finance": {"view": True, "manage": True},
            "tracking": {"view": True, "allocate": True, "transfer": True},
            "analytics": {"view": True},
            "cmdb": {"view": True, "create": True, "edit": True, "delete": True},
            "branches": {"view": True, "create": True, "update": True},
            "users": {"view": True, "manage": True, "permissions": True},
            "reports": {"view": True}
        }
    if role == EmployeeRole.ORG_ADMIN:
        return {
            "assets": {"view": True, "create": True, "update": True, "delete": True},
            "requests": {"view": True, "create": True, "approve": True, "reject": True, "triage": True},
            "finance": {"view": True, "manage": True},
            "tracking": {"view": True, "allocate": True, "transfer": True},
            "analytics": {"view": True},
            "cmdb": {"view": True, "create": True, "edit": True, "delete": True},
            "branches": {"view": True, "create": True, "update": True},
            "users": {"view": True, "manage": True, "permissions": True},
            "reports": {"view": True}
        }
    if role == EmployeeRole.MANAGER:
        return {
            "assets": {"view": True, "create": True, "update": True},
            "requests": {"view": True, "create": True, "approve": True, "reject": True},
            "tracking": {"view": True},
            "finance": {"view": True},
            "analytics": {"view": True},
            "cmdb": {"view": True, "create": True, "edit": True},
            "users": {"view": True}
        }
    if role == EmployeeRole.HR:
        return {
            "assets": {"view": True},
            "requests": {"view": True},
            "finance": {"view": True},
            "tracking": {"view": True},
            "analytics": {"view": True},
            "cmdb": {"view": True},
            "users": {"view": True, "manage": True},
            "reports": {"view": True}
        }
    if role == EmployeeRole.SUPPORT_TEAM:
        return {
            "assets": {"view": True, "create": True, "update": True},
            "requests": {"view": True, "triage": True, "execute": True},
            "tracking": {"view": True, "allocate": True, "transfer": True},
            "finance": {"view": True},
            "analytics": {"view": True},
            "cmdb": {"view": True},
        }
    if role == EmployeeRole.EMPLOYEE:
        return {
            "assets": {"view_own": True},
            "requests": {"view_own": True, "create": True},
            "tracking": {"view_own": True},
            "analytics": {"view": True},
        }
    return {}


def _normalize_permission_map(raw: dict | None) -> dict[str, dict[str, bool]]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, dict[str, bool]] = {}
    for module, actions in raw.items():
        if not isinstance(actions, dict):
            continue

        module_key = _normalize_permission_token(str(module))
        if not module_key:
            continue

        module_actions: dict[str, bool] = {}
        for action, allowed in actions.items():
            action_key = _normalize_permission_token(str(action))
            if not action_key:
                continue
            module_actions[action_key] = bool(allowed)

        if module_actions:
            normalized[module_key] = module_actions

    return normalized


def _merge_permission_maps(base: dict[str, dict[str, bool]], override: dict[str, dict[str, bool]]) -> dict[str, dict[str, bool]]:
    merged: dict[str, dict[str, bool]] = {module: dict(actions) for module, actions in base.items()}

    for module, actions in override.items():
        existing = merged.setdefault(module, {})
        for action, allowed in actions.items():
            existing[action] = bool(allowed)

    return merged


def create_default_permissions(role: EmployeeRole, user_override: dict | None = None) -> dict[str, dict[str, bool]]:
    role_defaults = _normalize_permission_map(get_default_permission_json(role))
    override = _normalize_permission_map(user_override)
    return _merge_permission_maps(role_defaults, override)


def get_effective_permissions(user: Employee) -> dict[str, dict[str, bool]]:
    role_defaults = _inherited_role_defaults(user.role)

    permission_row = getattr(user, "permissions", None)
    user_override = _normalize_permission_map(getattr(permission_row, "permissions_json", None) if permission_row else None)

    return _merge_permission_maps(role_defaults, user_override)


def has_permission(user: Employee, module: str, action: str) -> bool:
    if user.role == EmployeeRole.SUPER_ADMIN:
        return True
    if user.role == EmployeeRole.ORG_ADMIN:
        return True

    effective = get_effective_permissions(user)
    module_key = _normalize_permission_token(module)
    action_key = _normalize_permission_token(action)
    if not module_key or not action_key:
        return False

    module_scope = effective.get(module_key)
    if not isinstance(module_scope, dict):
        return False
    if bool(module_scope.get(action_key, False)):
        return True

    action_aliases = {
        "edit": "update",
        "update": "edit",
        "manage": "view",
        "view_own": "view",
        "view": "view_own",
        "approve": "review",
        "review": "approve",
    }
    alias = action_aliases.get(action_key)
    if alias and bool(module_scope.get(alias, False)):
        return True

    # Backward compatibility: grant module-level if a generic manage permission exists.
    if bool(module_scope.get("manage", False)):
        return True

    return False

def _build_default_role_permissions() -> dict[EmployeeRole, dict[str, bool]]:
    defaults: dict[EmployeeRole, dict[str, bool]] = {}
    for role, permissions in ROLE_PERMISSIONS.items():
        role_flags: dict[str, bool] = {}
        for permission in permissions:
            for flag in ROLE_PERMISSION_TO_FLAGS.get(permission, set()):
                role_flags[flag] = True
        defaults[role] = role_flags
    return defaults


DEFAULT_ROLE_PERMISSIONS = _build_default_role_permissions()

PERMISSION_FLAG_FIELDS = [
    "can_view_assets",
    "can_create_assets",
    "can_update_assets",
    "can_delete_assets",
    "can_create_request",
    "can_approve_request",
    "can_reject_request",
    "can_view_finance",
    "can_manage_finance",
    "can_view_tracking",
    "can_allocate_asset",
    "can_transfer_asset",
    "can_view_branch",
    "can_create_branch",
    "can_update_branch",
    "can_view_reports",
    "can_manage_users",
    "can_manage_permissions",
]

def get_default_permission_flags(role: EmployeeRole) -> dict[str, bool]:
    """LEGACY: Return a flat permission map for backward compatibility."""
    role_defaults = DEFAULT_ROLE_PERMISSIONS.get(role, {})
    return {flag: bool(role_defaults.get(flag, False)) for flag in PERMISSION_FLAG_FIELDS}


JSON_PERMISSION_TO_LEGACY_FLAG = {
    ("assets", "view"): "can_view_assets",
    ("assets", "create"): "can_create_assets",
    ("assets", "update"): "can_update_assets",
    ("assets", "delete"): "can_delete_assets",
    ("requests", "create"): "can_create_request",
    ("requests", "approve"): "can_approve_request",
    ("requests", "reject"): "can_reject_request",
    ("finance", "view"): "can_view_finance",
    ("finance", "manage"): "can_manage_finance",
    ("tracking", "view"): "can_view_tracking",
    ("tracking", "allocate"): "can_allocate_asset",
    ("tracking", "transfer"): "can_transfer_asset",
    ("branches", "view"): "can_view_branch",
    ("branches", "create"): "can_create_branch",
    ("branches", "update"): "can_update_branch",
    ("reports", "view"): "can_view_reports",
    ("users", "manage"): "can_manage_users",
    ("users", "permissions"): "can_manage_permissions",
}


def permission_json_to_legacy_flags(permissions_json: dict) -> dict[str, bool]:
    """Map scoped JSON permissions to legacy boolean columns for compatibility."""
    result = {flag: False for flag in PERMISSION_FLAG_FIELDS}
    if not isinstance(permissions_json, dict):
        return result
    for module, actions in permissions_json.items():
        if not isinstance(actions, dict):
            continue
        for action, allowed in actions.items():
            if not allowed:
                continue
            flag = JSON_PERMISSION_TO_LEGACY_FLAG.get(
                (_normalize_permission_token(str(module)), _normalize_permission_token(str(action)))
            )
            if flag:
                result[flag] = True
    return result


def _humanize_permission_key(value: str) -> str:
    return str(value).replace("_", " ").strip().title()


def get_permission_catalog() -> list[dict]:
    """Union of role defaults as module/action metadata for dynamic permission UIs."""
    union_map: dict[str, set[str]] = {}
    for role in EmployeeRole:
        perms = get_default_permission_json(role)
        if not isinstance(perms, dict):
            continue
        for module, actions in perms.items():
            if not isinstance(actions, dict):
                continue
            module_key = str(module)
            module_actions = union_map.setdefault(module_key, set())
            for action in actions.keys():
                module_actions.add(str(action))

    modules = []
    for module_key in sorted(union_map.keys()):
        actions = [
            {"key": action_key, "label": _humanize_permission_key(action_key)}
            for action_key in sorted(union_map[module_key])
        ]
        modules.append({
            "key": module_key,
            "label": _humanize_permission_key(module_key),
            "actions": actions,
        })
    return modules




def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _login_email_host_strict(raw_email: str) -> Optional[str]:
    """
    Normalized domain host from the login identifier (exact match against org domain).
    Rejects multiple @, whitespace in local/host, empty labels, and non-IDNA-safe hosts.
    """
    if raw_email is None:
        return None
    s = raw_email.strip().lower()
    if not s or s.count("@") != 1:
        return None
    local, host = s.split("@", 1)
    local, host = local.strip(), host.strip().strip(".")
    if not local or not host:
        return None
    if any(ch.isspace() for ch in local) or any(ch.isspace() for ch in host):
        return None
    if "@" in host:
        return None
    labels = host.split(".")
    if not labels or any(not lb for lb in labels):
        return None
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return ascii_host.lower()


def _org_domain_host_strict(raw_domain: Optional[str]) -> Optional[str]:
    """Normalize organization.domain config (strip scheme/path/port, drop leading www., IDNA)."""
    raw = (raw_domain or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if "://" not in lower:
        lower = f"https://{lower}"
    parsed = urlparse(lower)
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if not host:
        return None
    host = host.split(":")[0].strip(".")
    if host.startswith("www."):
        host = host[4:].strip(".")
    if not host:
        return None
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return ascii_host.lower()


def authenticate_user(db: Session, email: str, password: str) -> Employee | None:
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return None
    user = db.query(Employee).filter(Employee.email == email_norm, Employee.is_active == True).first()
    if not user or not user.password_hash:
        return None

    # Tenant users: company email host must exactly match the organization's configured
    # domain (strict parsing / IDNA). Super admin is exempt.
    if user.role != EmployeeRole.SUPER_ADMIN and user.organization_id and user.organization:
        configured = (user.organization.domain or "").strip()
        if configured:
            email_host = _login_email_host_strict(email_norm)
            org_host = _org_domain_host_strict(user.organization.domain)
            if not email_host or not org_host or email_host != org_host:
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

def get_current_user(
    request: Request,
    token: str=Depends(get_token_from_header_or_cookie),
    db: Session=Depends(get_db)
) -> Employee:
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

    # Super admin is only for platform-level operations and must not access
    # organization-scoped business endpoints.
    if user.role == EmployeeRole.SUPER_ADMIN:
        allowed_prefixes = (
            "/organizations",
            "/auth",
            "/health",
            "/openapi.json",
            "/docs",
            "/redoc",
        )
        if not request.url.path.startswith(allowed_prefixes):
            raise HTTPException(
                status_code=403,
                detail="Super Admin is restricted to organization management endpoints.",
            )
        
    # Only block users if organization subscription is SUSPENDED (not just inactive)
    if user.organization and user.role.value != "super_admin":
        from app.server.schema.organization import SubscriptionStatus
        if user.organization.subscription_status == SubscriptionStatus.SUSPENDED:
            raise HTTPException(
                status_code=403,
                detail="Organization subscription is suspended. Contact support."
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
