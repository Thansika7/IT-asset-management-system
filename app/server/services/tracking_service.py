from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
from app.server.schema.tracking import Tracking
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.models.tracking import TrackingRead
from app.server.schema.employee import Employee, EmployeeRole
from app.server.database.tenant import apply_tenant_filter
from app.server.services.notification_service import NotificationPriority, NotificationService

class TrackingService:
    @staticmethod
    def _classify_expiry_attribute(attribute_name: str) -> Optional[str]:
        name = (attribute_name or "").strip().lower()
        if not name:
            return None

        if "warranty" in name or ("hardware" in name and ("expiry" in name or "expire" in name)):
            return "warranty"

        if (
            "license" in name
            or ("software" in name and ("expiry" in name or "expire" in name))
            or ("subscription" in name and ("expiry" in name or "expire" in name))
        ):
            return "license"

        return None

    @staticmethod
    def _get_expiry_value_map(db: Session, asset_id: str, attr_map: dict[str, list[str]]) -> dict[str, Optional[str]]:
        result = {"license": None, "warranty": None}
        for expiry_type, attribute_ids in attr_map.items():
            if not attribute_ids:
                continue
            row = db.query(AssetAttributeValue.value).filter(
                AssetAttributeValue.asset_id == asset_id,
                AssetAttributeValue.attribute_id.in_(attribute_ids)
            ).order_by(AssetAttributeValue.value.asc()).first()
            result[expiry_type] = row[0] if row else None
        return result

    @staticmethod
    def _get_expiry_value_map_bulk(db: Session, asset_ids: list[str], attr_map: dict[str, list[str]]) -> dict[str, dict[str, Optional[str]]]:
        out: dict[str, dict[str, Optional[str]]] = {
            asset_id: {"license": None, "warranty": None}
            for asset_id in asset_ids
        }
        if not asset_ids:
            return out

        license_attr_ids = attr_map.get("license", [])
        warranty_attr_ids = attr_map.get("warranty", [])
        all_attr_ids = [*license_attr_ids, *warranty_attr_ids]
        if not all_attr_ids:
            return out

        rows = (
            db.query(AssetAttributeValue.asset_id, AssetAttributeValue.attribute_id, AssetAttributeValue.value)
            .filter(
                AssetAttributeValue.asset_id.in_(asset_ids),
                AssetAttributeValue.attribute_id.in_(all_attr_ids),
            )
            .order_by(AssetAttributeValue.asset_id.asc(), AssetAttributeValue.value.asc())
            .all()
        )
        for asset_id, attr_id, value in rows:
            if attr_id in license_attr_ids and out[asset_id]["license"] is None:
                out[asset_id]["license"] = value
            if attr_id in warranty_attr_ids and out[asset_id]["warranty"] is None:
                out[asset_id]["warranty"] = value
        return out

    @staticmethod
    def _get_expiry_attr_map(db: Session) -> dict[str, list[str]]:
        attr_map = {"license": [], "warranty": []}
        for attr in db.query(AssetAttribute).all():
            expiry_type = TrackingService._classify_expiry_attribute(attr.attribute_name)
            if expiry_type:
                attr_map[expiry_type].append(attr.attribute_id)
        return attr_map

    @staticmethod
    def _map_tracking_record(rec: Tracking, expiry_values: dict[str, Optional[str]]) -> TrackingRead:
        data = TrackingRead.model_validate(rec)
        data.movement_type = rec.movement_type.value if hasattr(rec.movement_type, 'value') else rec.movement_type
        data.allocation_type = rec.allocation_type.value if hasattr(rec.allocation_type, 'value') else rec.allocation_type
        data.instance_id = rec.instance_id
        data.serial_number = rec.instance.serial_number if rec.instance else None
        data.status = "RETURNED" if rec.returned_at else (rec.instance.status.value if rec.instance and hasattr(rec.instance.status, "value") else None)
        data.assigned_to = rec.instance.assigned_to_id if rec.instance and rec.instance.assigned_to_id else rec.emp_id
        data.employee_name = rec.employee.name if rec.employee else None
        
        if rec.asset:
            data.asset_name = rec.asset.name
            if rec.asset.category:
                data.category = rec.asset.category.category_name
            if rec.asset.sub_category:
                data.sub_category = rec.asset.sub_category.sub_category_name

        data.license_expiry = expiry_values["license"]
        data.warranty_expiry = expiry_values["warranty"]
            
        return data

    @staticmethod
    def get_all_tracking(
        db: Session, 
        current_user: Employee, 
        search: Optional[str] = None, 
        status: Optional[str] = None,
        branch_id: Optional[str] = None,
        employee_id: Optional[str] = None,
        category_id: Optional[str] = None,
        movement_type: Optional[str] = None,
        transfer_status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> dict:
        from sqlalchemy import or_
        from app.server.schema.employee import Employee as EmployeeSchema
        from app.server.schema.category import Category
        
        query = apply_tenant_filter(db.query(Tracking), current_user, Tracking).outerjoin(Tracking.instance).outerjoin(Tracking.asset).outerjoin(Tracking.employee)
        
        # Scoping based on role
        if current_user.role == EmployeeRole.EMPLOYEE:
            query = query.filter(Tracking.emp_id == current_user.employee_id)
        elif current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM] and current_user.branch_id:
            query = query.filter(Tracking.branch_id == current_user.branch_id)
            
        if branch_id:
            query = query.filter(Tracking.branch_id == branch_id)

        if employee_id:
            query = query.filter(Tracking.emp_id == employee_id)

        if category_id:
            query = query.filter(Asset.category_id == category_id)

        if status:
            normalized = status.strip().upper()
            if normalized == "RETURNED":
                query = query.filter(Tracking.returned_at.isnot(None))
            elif normalized in {"NEW", "ASSIGNED", "IN_REPAIR", "NOT_USABLE"}:
                query = query.filter(Tracking.returned_at.is_(None), AssetInstance.status == normalized)

        if movement_type:
            query = query.filter(Tracking.movement_type == movement_type.upper())

        if transfer_status:
            query = query.filter(Tracking.transfer_status == transfer_status.upper())
            
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                or_(
                    Asset.name.ilike(search_filter),
                    Tracking.instance_id.ilike(search_filter),
                    AssetInstance.serial_number.ilike(search_filter),
                    EmployeeSchema.name.ilike(search_filter),
                    Tracking.emp_id.ilike(search_filter),
                    Tracking.movement_reason.ilike(search_filter)
                )
            )
            
        total = query.count()
        records = query.order_by(Tracking.assigned_date.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        attr_map = TrackingService._get_expiry_attr_map(db)
        expiry_map = TrackingService._get_expiry_value_map_bulk(db, [rec.asset_id for rec in records], attr_map)
        items = [TrackingService._map_tracking_record(rec, expiry_map.get(rec.asset_id, {"license": None, "warranty": None})) for rec in records]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page
        }

    @staticmethod
    def get_filter_options(db: Session, current_user: Employee) -> dict:
        from app.server.schema.organization import Branch
        from app.server.schema.organization import BranchStatus
        from app.server.schema.category import Category

        scoped = apply_tenant_filter(db.query(Tracking), current_user, Tracking)

        if current_user.role == EmployeeRole.EMPLOYEE:
            scoped = scoped.filter(Tracking.emp_id == current_user.employee_id)
        elif current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM] and current_user.branch_id:
            scoped = scoped.filter(Tracking.branch_id == current_user.branch_id)

        rows = scoped.with_entities(Tracking.branch_id, Tracking.emp_id).distinct().all()
        branch_ids = sorted({r[0] for r in rows if r[0]})
        employee_ids = sorted({r[1] for r in rows if r[1]})

        branch_map = {
            b.branch_id: b.branch_name
            for b in apply_tenant_filter(db.query(Branch), current_user, Branch)
            .filter(Branch.branch_id.in_(branch_ids))
            .filter(Branch.status == BranchStatus.ACTIVE)
            .all()
        } if branch_ids else {}

        employee_map = {
            e.employee_id: e.name
            for e in apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id.in_(employee_ids)).all()
        } if employee_ids else {}

        categories = [
            {"id": c.category_id, "name": c.category_name}
            for c in apply_tenant_filter(db.query(Category), current_user, Category).order_by(Category.category_name.asc()).all()
        ]

        statuses = [status.value for status in AssetStatus if status.value in {"NEW", "ASSIGNED", "IN_REPAIR", "NOT_USABLE"}]
        statuses.append("RETURNED")

        return {
            "statuses": statuses,
            "branches": [
                {"value": bid, "label": branch_map.get(bid, bid)}
                for bid in branch_ids
            ],
            "employees": [
                {"value": eid, "label": employee_map.get(eid, eid)}
                for eid in employee_ids
            ],
            "categories": categories,
        }

    @staticmethod
    def get_asset_history(db: Session, asset_id: str, current_user: Employee) -> List[TrackingRead]:
        records = apply_tenant_filter(db.query(Tracking), current_user, Tracking).filter(Tracking.asset_id == asset_id).order_by(Tracking.assigned_date.desc()).all()
        
        attr_map = TrackingService._get_expiry_attr_map(db)
        expiry_map = TrackingService._get_expiry_value_map_bulk(db, [r.asset_id for r in records], attr_map)

        return [TrackingService._map_tracking_record(r, expiry_map.get(r.asset_id, {"license": None, "warranty": None})) for r in records]

    @staticmethod
    def check_expirations_and_notify_support(db: Session, current_user: Employee):
        from app.server.services.email_service import EmailService

        attr_map = TrackingService._get_expiry_attr_map(db)

        attribute_ids = attr_map["license"] + attr_map["warranty"]
        if not attribute_ids:
            return []

        all_values = apply_tenant_filter(db.query(AssetAttributeValue), current_user, AssetAttributeValue).filter(
            AssetAttributeValue.attribute_id.in_(attribute_ids)
        ).all()

        expiring_assets = []
        today = date.today()
        classified_attrs = {}
        for attr in db.query(AssetAttribute).filter(AssetAttribute.attribute_id.in_(attribute_ids)).all():
            classified_attrs[attr.attribute_id] = TrackingService._classify_expiry_attribute(attr.attribute_name)

        for val in all_values:
            if not val.value:
                continue
            try:
                exp_date = datetime.strptime(val.value, "%Y-%m-%d").date()
                delta = (exp_date - today).days
                if 0 <= delta <= 30:
                    expiry_type = classified_attrs.get(val.attribute_id)
                    if not expiry_type:
                        continue
                    attr_name = "License" if expiry_type == "license" else "Warranty"
                    asset = apply_tenant_filter(db.query(Asset), current_user, Asset).filter(Asset.asset_id == val.asset_id).first()
                    expiring_assets.append({
                        "asset_id": val.asset_id,
                        "asset_name": asset.name if asset else "Unknown",
                        "type": attr_name,
                        "expiry_date": val.value,
                        "days_left": delta
                    })
            except ValueError:
                continue

        if expiring_assets:
            EmailService.notify_support_approaching_expiry(expiring_assets)
            NotificationService.emit(
                db,
                actor=current_user,
                recipient_scope=f"ORG:{current_user.organization_id or '-'}",
                event_type="LICENSE_EXPIRY_ALERT",
                title="License/Warranty Expiry Alert",
                message=f"{len(expiring_assets)} assets are expiring within 30 days.",
                priority=NotificationPriority.HIGH,
                dedup_key=f"expiry_alert:{current_user.organization_id}:{today.isoformat()}",
                cooldown_hours=24,
                metadata={"count": len(expiring_assets), "items": expiring_assets[:20]},
            )
        
        return expiring_assets
