from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.server.schema.tracking import AssetLifecycle, LifecycleEvent
from app.server.schema.asset import AssetStatus
from app.server.schema.employee import Employee
from app.server.exceptions.base import ResourceNotFoundError
from typing import Optional
from datetime import datetime

class LifecycleService:
    """Manages asset instance lifecycle event tracking."""
    
    @staticmethod
    def log_event(
        db: Session,
        instance_id: str,
        asset_id: str,
        event_type: LifecycleEvent,
        performed_by: Employee,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        notes: Optional[str] = None,
        tracking_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AssetLifecycle:
        """
        Log a lifecycle event for an asset instance.
        
        Args:
            db: Database session
            instance_id: Asset instance ID
            asset_id: Asset ID
            event_type: LifecycleEvent enum value
            performed_by: Employee performing the action
            old_status: Previous status (if applicable)
            new_status: New status (if applicable)
            notes: Optional notes about the event
            tracking_id: Optional reference to Tracking record
            organization_id: Organization ID
            
        Returns:
            AssetLifecycle record created
        """
        lifecycle_event = AssetLifecycle(
            instance_id=instance_id,
            asset_id=asset_id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            performed_by=performed_by.employee_id,
            notes=notes,
            tracking_id=tracking_id,
            organization_id=organization_id,
            event_metadata=metadata,
        )
        db.add(lifecycle_event)
        db.flush()
        return lifecycle_event
    
    @staticmethod
    def get_instance_lifecycle(
        db: Session,
        instance_id: str,
        page: int = 1,
        per_page: int = 50
    ) -> dict:
        """
        Get complete lifecycle history for an asset instance.
        
        Returns paginated list of lifecycle events in reverse chronological order.
        """
        query = db.query(AssetLifecycle).filter(
            AssetLifecycle.instance_id == instance_id
        )
        
        total = query.count()
        events = query.order_by(
            AssetLifecycle.timestamp.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()
        
        return {
            "instance_id": instance_id,
            "events": [_serialize_lifecycle_event(e) for e in events],
            "total": total,
            "page": page,
            "per_page": per_page
        }
    
    @staticmethod
    def get_asset_lifecycle(
        db: Session,
        asset_id: str,
        page: int = 1,
        per_page: int = 50
    ) -> dict:
        """
        Get aggregate lifecycle history for all instances of an asset.
        
        Returns paginated list of all lifecycle events for the asset.
        """
        query = db.query(AssetLifecycle).filter(
            AssetLifecycle.asset_id == asset_id
        )
        
        total = query.count()
        events = query.order_by(
            AssetLifecycle.timestamp.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()
        
        return {
            "asset_id": asset_id,
            "events": [_serialize_lifecycle_event(e) for e in events],
            "total": total,
            "page": page,
            "per_page": per_page
        }
    
    @staticmethod
    def get_lifecycle_analytics(db: Session, asset_id: str) -> dict:
        """
        Calculate analytics based on lifecycle events.
        
        Returns counts and durations for repair, assignment, transfer history.
        """
        events = db.query(AssetLifecycle).filter(
            AssetLifecycle.asset_id == asset_id
        ).order_by(AssetLifecycle.timestamp).all()
        
        repair_count = sum(1 for e in events if e.event_type == LifecycleEvent.REPAIR_STARTED)
        assignment_count = sum(1 for e in events if e.event_type == LifecycleEvent.ASSIGNED)
        transfer_count = sum(1 for e in events if e.event_type == LifecycleEvent.TRANSFERRED)
        return_count = sum(1 for e in events if e.event_type == LifecycleEvent.RETURNED)
        
        # Calculate total downtime (repair duration)
        total_downtime_days = 0
        repair_start = None
        for e in events:
            if e.event_type == LifecycleEvent.REPAIR_STARTED:
                repair_start = e.timestamp
            elif e.event_type == LifecycleEvent.REPAIR_COMPLETED and repair_start:
                duration = (e.timestamp - repair_start).total_seconds() / (24 * 3600)
                total_downtime_days += duration
                repair_start = None
        
        # Determine current age
        created_event = next((e for e in events if e.event_type == LifecycleEvent.CREATED), None)
        age_days = 0
        if created_event:
            age_days = (datetime.utcnow() - created_event.timestamp.replace(tzinfo=None)).days
        
        return {
            "asset_id": asset_id,
            "repair_count": repair_count,
            "assignment_count": assignment_count,
            "transfer_count": transfer_count,
            "return_count": return_count,
            "total_downtime_days": round(total_downtime_days, 2),
            "age_days": age_days,
            "total_events": len(events)
        }
    
    @staticmethod
    def log_rollback(
        db: Session,
        instance_id: str,
        asset_id: str,
        performed_by: Employee,
        reason: str,
        organization_id: Optional[str] = None
    ) -> AssetLifecycle:
        """Log a rollback event (state transition that was undone)."""
        return LifecycleService.log_event(
            db,
            instance_id=instance_id,
            asset_id=asset_id,
            event_type=LifecycleEvent.ROLLBACK,
            performed_by=performed_by,
            notes=f"Rollback: {reason}",
            organization_id=organization_id
        )


def _serialize_lifecycle_event(event: AssetLifecycle) -> dict:
    """Convert AssetLifecycle ORM object to dict."""
    return {
        "lifecycle_id": event.lifecycle_id,
        "instance_id": event.instance_id,
        "asset_id": event.asset_id,
        "event_type": event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
        "old_status": event.old_status,
        "new_status": event.new_status,
        "performed_by": event.performed_by,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "notes": event.notes,
        "tracking_id": event.tracking_id,
        "metadata": event.event_metadata,
    }
