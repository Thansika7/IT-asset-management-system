from sqlalchemy.orm import Session, aliased
from sqlalchemy import func
from typing import List, Optional
from app.server.schema.tracking import Tracking
from app.server.schema.asset import Asset
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.models.tracking import TrackingRead

class TrackingService:
    @staticmethod
    def get_all_tracking(db: Session, emp_id: Optional[str] = None) -> List[TrackingRead]:
        query = db.query(Tracking)
        if emp_id:
            query = query.filter(Tracking.emp_id == emp_id)
        
        records = query.order_by(Tracking.assigned_date.desc()).all()
        result = []
        
        expiry_attrs = db.query(AssetAttribute).filter(
            AssetAttribute.attribute_name.in_(["License Expiry", "Warranty Expiry"])
        ).all()
        attr_map = {a.attribute_name: a.attribute_id for a in expiry_attrs}
        
        for rec in records:
            data = TrackingRead.model_validate(rec)
            data.movement_type = rec.movement_type.value # Convert enum to string
            
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
            
            result.append(data)
            
        return result

    @staticmethod
    def get_asset_history(db: Session, asset_id: str) -> List[TrackingRead]:
        records = db.query(Tracking).filter(Tracking.asset_id == asset_id).order_by(Tracking.assigned_date.desc()).all()
        return [TrackingRead.model_validate(r) for r in records]
