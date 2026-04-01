from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
from app.server.schema.tracking import Tracking
from app.server.schema.asset import Asset
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.models.tracking import TrackingRead

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
    def _get_expiry_attr_map(db: Session) -> dict[str, list[str]]:
        attr_map = {"license": [], "warranty": []}
        for attr in db.query(AssetAttribute).all():
            expiry_type = TrackingService._classify_expiry_attribute(attr.attribute_name)
            if expiry_type:
                attr_map[expiry_type].append(attr.attribute_id)
        return attr_map

    @staticmethod
    def _map_tracking_record(db: Session, rec: Tracking, attr_map: dict) -> TrackingRead:
        data = TrackingRead.model_validate(rec)
        data.movement_type = rec.movement_type.value if hasattr(rec.movement_type, 'value') else rec.movement_type
        data.allocation_type = rec.allocation_type.value if hasattr(rec.allocation_type, 'value') else rec.allocation_type
        
        if rec.asset:
            data.asset_name = rec.asset.name
            if rec.asset.category:
                data.category = rec.asset.category.category_name
            if rec.asset.sub_category:
                data.sub_category = rec.asset.sub_category.sub_category_name

        expiry_values = TrackingService._get_expiry_value_map(db, rec.asset_id, attr_map)
        data.license_expiry = expiry_values["license"]
        data.warranty_expiry = expiry_values["warranty"]
            
        return data

    @staticmethod
    def get_all_tracking(db: Session, emp_id: Optional[str] = None, branch: Optional[str] = None) -> List[TrackingRead]:
        query = db.query(Tracking)
        if emp_id:
            query = query.filter(Tracking.emp_id == emp_id)
        if branch:
            query = query.filter(Tracking.branch == branch)
        
        records = query.order_by(Tracking.assigned_date.desc()).all()
        
        attr_map = TrackingService._get_expiry_attr_map(db)
        
        return [TrackingService._map_tracking_record(db, rec, attr_map) for rec in records]

    @staticmethod
    def get_asset_history(db: Session, asset_id: str) -> List[TrackingRead]:
        records = db.query(Tracking).filter(Tracking.asset_id == asset_id).order_by(Tracking.assigned_date.desc()).all()
        
        attr_map = TrackingService._get_expiry_attr_map(db)

        return [TrackingService._map_tracking_record(db, r, attr_map) for r in records]

    @staticmethod
    def check_expirations_and_notify_support(db: Session):
        from app.server.services.email_service import EmailService

        attr_map = TrackingService._get_expiry_attr_map(db)

        attribute_ids = attr_map["license"] + attr_map["warranty"]
        if not attribute_ids:
            return []

        all_values = db.query(AssetAttributeValue).filter(
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
                    asset = db.query(Asset).filter(Asset.asset_id == val.asset_id).first()
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
        
        return expiring_assets
