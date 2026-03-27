import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.server.auth.service import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    update_last_login,
)
from app.server.database.database import get_db
from app.server.models.api import EmployeeCreate, EmployeeRead, Token
from app.server.schema import Employee

router=APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: EmployeeCreate, db: Session=Depends(get_db)):
    existing=db.query(Employee).filter(Employee.email==payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered")

    raw_password=str(uuid.uuid4())
    user=Employee(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        branch=payload.branch,
        role=payload.role,
        password_hash=get_password_hash(raw_password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user.generated_password=raw_password
    return user

@router.post("/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm=Depends(),
    db: Session=Depends(get_db),
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
