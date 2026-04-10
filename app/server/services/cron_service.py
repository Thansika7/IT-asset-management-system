from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import and_

from app.server.database.tenant import apply_tenant_filter
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.asset import Asset
from app.server.schema.tracking import Tracking
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.email_service import EmailService

class CronService:
    @staticmethod
    def check_and_notify_expirations(db: Session, current_user: Employee):
        """
        Scans dynamic Asset Attributes for any 'warranty', 'license', or 'expire'
        values that fall in a target date range (today + 30 days).
        """
        target_date = datetime.utcnow().date() + timedelta(days=30)
        target_date_str = target_date.strftime("%Y-%m-%d")
        target_date_next_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

        # 1. Find all expiring attributes
        expiring_values = apply_tenant_filter(
            db.query(AssetAttributeValue),
            current_user,
            AssetAttributeValue,
        ).join(AssetAttribute).filter(
            AssetAttributeValue.value.op("~")(r"^\d{4}-\d{2}-\d{2}$"),
            AssetAttributeValue.value >= target_date_str,
            AssetAttributeValue.value < target_date_next_str,
            (
                AssetAttribute.attribute_name.ilike("%warranty%")
                | AssetAttribute.attribute_name.ilike("%license%")
                | AssetAttribute.attribute_name.ilike("%expire%")
            ),
        ).all()

        if not expiring_values:
            return {"status": "success", "message": "No assets expiring in exactly 30 days"}

        notifications_sent = 0
        details = []

        for attr_val in expiring_values:
            asset = apply_tenant_filter(db.query(Asset), current_user, Asset).filter(Asset.asset_id == attr_val.asset_id).first()
            if not asset:
                continue
                
            attr_name = attr_val.attribute.attribute_name

            # 2. Find Current Physical Owner via Tracking
            active_tracking = apply_tenant_filter(db.query(Tracking), current_user, Tracking).filter(
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
            support_staff = apply_tenant_filter(db.query(Employee.email, Employee.branch), current_user, Employee).filter(
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
