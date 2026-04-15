from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.database.tenant import apply_tenant_filter
from app.server.middlewares.auth import require_module_access, require_roles
from app.server.schema.asset import Asset, AssetInstance
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.request import Request
from app.server.schema.tracking import MovementType, Tracking

router = APIRouter(
    prefix="/support",
    tags=["support"],
    dependencies=[Depends(require_module_access("requests"))],
)


@router.get("/in-repair-assets")
def list_in_repair_assets(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR)),
):
    rows = (
        apply_tenant_filter(db.query(Request), current_user, Request)
        .filter(Request.request_type == "SERVICE")
        .filter((Request.status == "IN_REPAIR") | (Request.stage == "IN_REPAIR"))
        .order_by(Request.service_start_date.desc().nullslast(), Request.req_date.desc())
        .all()
    )

    out = []
    for req in rows:
        out.append(
            {
                "request_id": req.request_id,
                "asset": req.asset_name,
                "employee": req.employee.name if req.employee else req.emp_id,
                "start_date": req.service_start_date,
                "expected_return": req.expected_return_date,
            }
        )
    return out


@router.get("/temp-assigned-assets")
def list_temp_assigned_assets(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPPORT_TEAM, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPER_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR)),
):
    temp_rows = (
        apply_tenant_filter(db.query(Tracking), current_user, Tracking)
        .filter(Tracking.movement_type == MovementType.TEMP_ASSIGNED)
        .filter(Tracking.returned_at.is_(None))
        .order_by(Tracking.assigned_date.desc())
        .all()
    )

    out = []
    for trk in temp_rows:
        req = (
            apply_tenant_filter(db.query(Request), current_user, Request)
            .filter(Request.temporary_tracking_id == trk.tracking_id)
            .first()
        )
        asset = apply_tenant_filter(db.query(Asset), current_user, Asset).filter(Asset.asset_id == trk.asset_id).first()
        out.append(
            {
                "tracking_id": trk.tracking_id,
                "asset": asset.name if asset else trk.asset_id,
                "employee": trk.employee.name if trk.employee else trk.emp_id,
                "start_date": trk.assigned_date,
                "expected_return": req.expected_return_date if req else None,
            }
        )

    return out
