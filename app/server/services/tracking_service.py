from sqlalchemy.orm import Session, aliased
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date
from app.server.schema.tracking import Tracking
from app.server.schema.asset import Asset
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.models.tracking import TrackingRead

class TrackingService:
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

        if "License Expiry" in attr_map:
            lic_val = db.query(AssetAttributeValue.value).filter(
                AssetAttributeValue.asset_id == rec.asset_id,
                AssetAttributeValue.attribute_id == attr_map["License Expiry"]
            ).scalar()
            data.license_expiry = lic_val
            
        if "Warranty Expiry" in attr_map:
            war_val = db.query(AssetAttributeValue.value).filter(
                AssetAttributeValue.asset_id == rec.asset_id,
                AssetAttributeValue.attribute_id == attr_map["Warranty Expiry"]
            ).scalar()
            data.warranty_expiry = war_val
            
        return data

    @staticmethod
    def get_all_tracking(db: Session, emp_id: Optional[str] = None) -> List[TrackingRead]:
        query = db.query(Tracking)
        if emp_id:
            query = query.filter(Tracking.emp_id == emp_id)
        
        records = query.order_by(Tracking.assigned_date.desc()).all()
        
        expiry_attrs = db.query(AssetAttribute).filter(
            AssetAttribute.attribute_name.in_(["License Expiry", "Warranty Expiry"])
        ).all()
        attr_map = {a.attribute_name: a.attribute_id for a in expiry_attrs}
        
        return [TrackingService._map_tracking_record(db, rec, attr_map) for rec in records]

    @staticmethod
    def get_asset_history(db: Session, asset_id: str) -> List[TrackingRead]:
        records = db.query(Tracking).filter(Tracking.asset_id == asset_id).order_by(Tracking.assigned_date.desc()).all()
        
        expiry_attrs = db.query(AssetAttribute).filter(
            AssetAttribute.attribute_name.in_(["License Expiry", "Warranty Expiry"])
        ).all()
        attr_map = {a.attribute_name: a.attribute_id for a in expiry_attrs}

        return [TrackingService._map_tracking_record(db, r, attr_map) for r in records]

    @staticmethod
    def check_expirations_and_notify_support(db: Session):
        from app.server.services.email_service import EmailService

        expiry_attrs = db.query(AssetAttribute).filter(
            AssetAttribute.attribute_name.in_(["License Expiry", "Warranty Expiry"])
        ).all()
        attr_map = {a.attribute_name: a.attribute_id for a in expiry_attrs}

        if not attr_map:
            return []

        all_values = db.query(AssetAttributeValue).filter(
            AssetAttributeValue.attribute_id.in_(list(attr_map.values()))
        ).all()

        expiring_assets = []
        today = date.today()

        for val in all_values:
            if not val.value:
                continue
            try:
                exp_date = datetime.strptime(val.value, "%Y-%m-%d").date()
                delta = (exp_date - today).days
                if 0 <= delta <= 30:
                    attr_name = "License" if val.attribute_id == attr_map.get("License Expiry") else "Warranty"
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
