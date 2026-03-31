from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List

from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.asset import Asset
from app.server.schema.tracking import Tracking
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.email_service import EmailService

class CronService:
    @staticmethod
    def check_and_notify_expirations(db: Session):
        """
        Scans dynamic Asset Attributes for any 'warranty', 'license', or 'expire'
        values that exactly match today + 30 days. Uses string format YYYY-MM-DD.
        """
        target_date = datetime.utcnow().date() + timedelta(days=30)
        target_date_str = target_date.strftime("%Y-%m-%d")

        # 1. Find all expiring attributes
        expiring_values = db.query(AssetAttributeValue).join(AssetAttribute).filter(
            AssetAttributeValue.value == target_date_str,
            (AssetAttribute.attribute_name.ilike("%warranty%") |
             AssetAttribute.attribute_name.ilike("%license%") |
             AssetAttribute.attribute_name.ilike("%expire%"))
        ).all()

        if not expiring_values:
            return {"status": "success", "message": "No assets expiring in exactly 30 days"}

        notifications_sent = 0
        details = []

        for attr_val in expiring_values:
            asset = db.query(Asset).filter(Asset.asset_id == attr_val.asset_id).first()
            if not asset:
                continue
                
            attr_name = attr_val.attribute.attribute_name

            # 2. Find Current Physical Owner via Tracking
            active_tracking = db.query(Tracking).filter(
                Tracking.asset_id == asset.asset_id,
                Tracking.returned_at == None
            ).first()

            owner_email = None
            owner_name = "Not Assigned"
            branch = asset.branch # default to asset's default branch
            
            if active_tracking and active_tracking.employee:
                owner = active_tracking.employee
                owner_email = owner.email
                owner_name = owner.name
                branch = active_tracking.branch or owner.branch

            # 3. Find Support Team for the branch
            support_staff = db.query(Employee.email).filter(
                Employee.branch == branch,
                Employee.role == EmployeeRole.SUPPORT_TEAM,
                Employee.is_active == True
            ).all()
            support_emails = [s.email for s in support_staff if s.email]

            # 4. Dispatch Email
            recipients = support_emails
            if owner_email and owner_email not in recipients:
                recipients.append(owner_email)

            if recipients:
                EmailService.notify_asset_expiration(
                    asset_name=asset.name,
                    asset_id=asset.asset_id,
                    expiry_date=target_date_str,
                    attribute_name=attr_name,
                    owner_name=owner_name,
                    recipients=recipients
                )
                notifications_sent += 1
                details.append(f"{asset.name} ({attr_name}) -> {len(recipients)} recipients")

        return {
            "status": "success",
            "message": f"Processed {len(expiring_values)} expiring assets.",
            "emails_dispatched": notifications_sent,
            "details": details
        }
