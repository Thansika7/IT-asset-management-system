from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.server.auth.service import (
    authenticate_user,
    create_access_token,
    create_oauth_user,
    get_current_user,
    get_password_hash,
    get_role_permissions,
    require_permissions,
    require_roles,
    update_last_login,
)
from app.server.database.database import get_db
from app.server.models.api import EmployeeCreate, EmployeeRead, OAuthEmployeeCreate, Token
from app.server.schema import Employee, EmployeeRole

router=APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: EmployeeCreate, db: Session = Depends(get_db)):
    existing=db.query(Employee).filter(Employee.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered")

    user=Employee(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        branch=payload.branch,
        role=payload.role,
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/oauth/register", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def register_oauth_user(payload: OAuthEmployeeCreate, db: Session = Depends(get_db)):
    return create_oauth_user(
        db,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        branch=payload.branch,
        role=payload.role,
        oauth_provider=payload.oauth_provider,
        oauth_subject=payload.oauth_subject,
    )


@router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user=authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    update_last_login(db, user)
    access_token=create_access_token(subject=user.email, role=user.role)
    return Token(access_token=access_token)


@router.get("/me", response_model=EmployeeRead)
def read_current_user(current_user: Employee = Depends(get_current_user)):
    return current_user


@router.get("/admin", response_model=EmployeeRead)
def admin_only_profile(current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN))):
    return current_user


@router.get("/manager", response_model=EmployeeRead)
def manager_or_admin_profile(current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.MANAGER))):
    return current_user


@router.get("/hr", response_model=EmployeeRead)
def hr_or_admin_profile(current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.HR))):
    return current_user


@router.get("/support", response_model=EmployeeRead)
def support_or_admin_profile(current_user: Employee = Depends(require_roles(EmployeeRole.ADMIN, EmployeeRole.SUPPORT_TEAM))):
    return current_user


@router.get("/permissions")
def read_my_permissions(current_user: Employee = Depends(get_current_user)):
    return {"role": current_user.role.value, "permissions": sorted(get_role_permissions(current_user.role))}


@router.get("/requests/review", response_model=EmployeeRead)
def request_review_access(current_user: Employee = Depends(require_permissions("requests:review"))):
    return current_user
