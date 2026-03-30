from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.server.auth.service import authenticate_user, create_access_token, update_last_login
from app.server.database.database import get_db
from app.server.models.api import Token
from app.server.exceptions.base import UnauthorizedActionError

router=APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm=Depends(),
    db: Session=Depends(get_db),
):
    user=authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise UnauthorizedActionError()
    update_last_login(db, user)
    access_token=create_access_token(subject=user.email, role=user.role)
    return Token(access_token=access_token)
