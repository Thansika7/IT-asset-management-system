import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.server.auth.service import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    update_last_login,
    require_roles
)
from app.server.database.database import get_db
from app.server.models.api import EmployeeCreate, EmployeeRead, Token
from app.server.schema import Employee, EmployeeRole
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.request import Request

router=APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: EmployeeCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
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

    if payload.onboarding_asset_ids:
        for aid in payload.onboarding_asset_ids:
            asset=db.query(Asset).filter(Asset.asset_id==aid, Asset.branch==user.branch).with_for_update().first()
            if asset and asset.unused > 0:
                asset.unused -= 1
                asset.used += 1
                if asset.unused == 0: asset.asset_status=AssetStatus.ALLOCATED
                trk=Tracking(
                    asset_id=aid,
                    emp_id=user.employee_id,
                    branch=user.branch,
                    movement_type=MovementType.ONBOARD,
                    allocation_type=AllocationType.PERMANENT
                )
                db.add(trk)
                if asset.unused < asset.low_stock_threshold:
                    low_stock_req=Request(
                        emp_id=current_user.employee_id,
                        asset_name=asset.name,
                        reason=f"LOW STOCK ALERT: Asset '{asset.name}' has dropped securely below threshold. Remaining: {asset.unused}",
                        status="PENDING_SUPPORT",
                        action_type="NEW"
                    )
                    db.add(low_stock_req)
            else:
                fallback_asset=db.query(Asset).filter(Asset.asset_id==aid).first()
                asset_name=fallback_asset.name if fallback_asset else f"Asset {aid}"
                missing_req=Request(
                    emp_id=user.employee_id,
                    asset_name=asset_name,
                    reason="MISSING ONBOARDING ASSET: Insufficient local stock physically during Day-1 Registration.",
                    status="PENDING_SUPPORT",
                    action_type="NEW"
                )
                db.add(missing_req)
        db.commit()
    return user

@router.post("/deactivate/{emp_id}")
def deactivate_employee(
    emp_id: str, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.HR, EmployeeRole.ADMIN))
):
    target=db.query(Employee).filter(Employee.employee_id==emp_id).first()
    if not target: raise HTTPException(status_code=404)
    target.is_active=False
    active=db.query(Tracking).filter(Tracking.emp_id==emp_id, Tracking.returned_at==None).with_for_update().all()
    recovered=0
    for trk in active:
        asset=db.query(Asset).filter(Asset.asset_id==trk.asset_id).with_for_update().first()
        if asset:
            asset.used -= 1
            asset.unused += 1
            asset.asset_status=AssetStatus.ACTIVE
        trk.returned_at=func.now()
        ret=Tracking(
            asset_id=trk.asset_id,
            emp_id=emp_id,
            branch=trk.branch,
            movement_type=MovementType.OFFBOARD,
            allocation_type=trk.allocation_type,
            parent_tracking_id=trk.parent_tracking_id
        )
        db.add(ret)
        recovered += 1
    db.commit()
    return {"status": "deactivated", "recovered_hardware": recovered}

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
