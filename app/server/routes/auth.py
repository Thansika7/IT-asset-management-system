from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.server.auth.service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    update_last_login,
    verify_password,
    get_password_hash,
    create_password_reset_token,
    verify_password_reset_token,
    generate_random_password,
)
from app.server.database.database import get_db
from app.server.models.api import EmployeeRead, Token, LoginRequest, PasswordChangeRequest, ForgotPasswordRequest
from app.server.schema.employee import Employee
from app.server.services.email_service import EmailService
from app.server.exceptions.base import UnauthorizedActionError

router=APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=Token)
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm=Depends(),
    db: Session=Depends(get_db),
):
    user=authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise UnauthorizedActionError()
    update_last_login(db, user)
    access_token=create_access_token(
        subject=user.email,
        role=user.role,
        employee_id=user.employee_id,
        branch=user.branch,
    )
    
    # Set the cookie for automatic authorization in Swagger UI
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True, 
        samesite='lax'
    )
    
    return Token(access_token=access_token)

@router.post("/login/json", response_model=Token)
def login_json(
    response: Response,
    payload: LoginRequest,
    db: Session=Depends(get_db),
):
    """
    Dedicated endpoint for React/JSON-based frontend clients.
    """
    user=authenticate_user(db, payload.username, payload.password)
    if not user:
        raise UnauthorizedActionError()
    update_last_login(db, user)
    access_token=create_access_token(
        subject=user.email,
        role=user.role,
        employee_id=user.employee_id,
        branch=user.branch,
    )
    
    # Also set a cookie for convenience, though frontend uses the token directly.
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True, 
        samesite='lax'
    )
    return Token(access_token=access_token)

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=EmployeeRead)
def get_me(current_user: Employee = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if not current_user.password_hash or not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.password_reset_required = False
    db.add(current_user)
    db.commit()
    return {"status": "ok", "password_reset_required": False}


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    user = db.query(Employee).filter(Employee.email == payload.email, Employee.is_active == True).first()
    if not user:
        # Don't reveal if email exists or not for security
        return {"message": "If an account with this email exists, a new password has been sent."}
    
    # Generate new password
    new_password = generate_random_password()
    user.password_hash = get_password_hash(new_password)
    user.password_reset_required = True  # Force password change on next login
    db.add(user)
    db.commit()
    
    # Send new password to personal email if available, otherwise to work email
    email_to_send = user.personal_email or user.email
    EmailService.send_password_reset_email(email_to_send, new_password, user.name)
    
    return {"message": "If an account with this email exists, a new password has been sent."}
