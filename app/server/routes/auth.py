from fastapi import APIRouter, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.server.auth.service import authenticate_user, create_access_token, update_last_login
from app.server.database.database import get_db
from app.server.models.api import Token
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
    access_token=create_access_token(subject=user.email, role=user.role)
    
    # Set the cookie for automatic authorization in Swagger UI
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
