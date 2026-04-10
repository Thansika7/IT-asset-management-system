from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.server.database.database import SessionLocal
from app.server.database.tenant import apply_tenant_filter
from app.server.schema.audit import AuditLog
from app.server.schema.employee import Employee
from app.server.services.email_service import EmailService


class NotificationPriority:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationService:
    """Notification reliability layer backed by existing audit_logs table."""

    _executor = ThreadPoolExecutor(max_workers=4)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _sanitize_scope(scope: str) -> str:
        token = (scope or "").strip()
        if not token:
            raise ValueError("notification recipient scope is required")
        return token

    @staticmethod
    def _dedup_reason(event_key: str) -> str:
        return f"NOTIFICATION_SENT::{event_key}"

    @staticmethod
    def _has_recent_notification(
        db: Session,
        current_user: Employee,
        recipient_scope: str,
        event_key: str,
        cooldown_hours: int,
    ) -> bool:
        cutoff = NotificationService._utc_now() - timedelta(hours=max(cooldown_hours, 1))
        reason = NotificationService._dedup_reason(event_key)
        row = (
            apply_tenant_filter(db.query(AuditLog), current_user, AuditLog)
            .filter(
                AuditLog.table_name == "notifications",
                AuditLog.record_id == recipient_scope,
                AuditLog.reason == reason,
                AuditLog.changed_at >= cutoff,
            )
            .first()
        )
        return bool(row)

    @staticmethod
    def _create_notification_log(
        db: Session,
        actor: Optional[Employee],
        recipient_scope: str,
        event_type: str,
        priority: str,
        title: str,
        message: str,
        event_key: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        now = NotificationService._utc_now()
        payload = {
            "event_type": event_type,
            "priority": priority,
            "title": title,
            "message": message,
            "read": False,
            "status": "PENDING",
            "retry_count": 0,
            "last_attempt": None,
            "event_key": event_key,
            "metadata": metadata or {},
        }
        row = AuditLog(
            table_name="notifications",
            record_id=recipient_scope,
            action="CREATE",
            old_values=None,
            new_values=payload,
            changed_by=actor.employee_id if actor else "SYSTEM",
            user_role=actor.role.value if actor else "SYSTEM",
            branch=actor.branch if actor else "SYSTEM",
            changed_at=now,
            reason=f"NOTIFICATION_CREATED::{event_key}",
            organization_id=actor.organization_id if actor else None,
            branch_id=actor.branch_id if actor else None,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def _mark_delivery_state(notification_id: str, status: str, retry_count: int, reason: str) -> None:
        db = SessionLocal()
        try:
            row = db.query(AuditLog).filter(AuditLog.audit_id == notification_id).first()
            if not row:
                return
            payload = dict(row.new_values or {})
            payload["status"] = status
            payload["retry_count"] = retry_count
            payload["last_attempt"] = NotificationService._utc_now().isoformat()
            row.action = "UPDATE"
            row.reason = reason
            row.new_values = payload
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _deliver_email_with_retry(notification_id: str, to_email: str, subject: str, html_body: str, max_attempts: int = 3) -> None:
        attempts = 0
        for idx in range(max_attempts):
            attempts = idx + 1
            ok = EmailService._send_email(to_email, subject, html_body)
            if ok:
                NotificationService._mark_delivery_state(
                    notification_id=notification_id,
                    status="SENT",
                    retry_count=attempts,
                    reason="NOTIFICATION_SENT",
                )
                return

        NotificationService._mark_delivery_state(
            notification_id=notification_id,
            status="FAILED",
            retry_count=attempts,
            reason="NOTIFICATION_FAILED",
        )

    @staticmethod
    def _deliver_batch(messages: list[tuple[str, str, str, str]]) -> None:
        for notification_id, to_email, subject, html_body in messages:
            NotificationService._deliver_email_with_retry(notification_id, to_email, subject, html_body)

    @staticmethod
    def emit(
        db: Session,
        *,
        actor: Optional[Employee],
        recipient_scope: str,
        event_type: str,
        title: str,
        message: str,
        priority: str = NotificationPriority.MEDIUM,
        dedup_key: Optional[str] = None,
        cooldown_hours: int = 24,
        metadata: Optional[dict[str, Any]] = None,
        email_to: Optional[str] = None,
        email_subject: Optional[str] = None,
        email_html: Optional[str] = None,
    ) -> Optional[str]:
        scope = NotificationService._sanitize_scope(recipient_scope)
        normalized_priority = str(priority or NotificationPriority.MEDIUM).strip().upper()
        if normalized_priority not in {
            NotificationPriority.LOW,
            NotificationPriority.MEDIUM,
            NotificationPriority.HIGH,
            NotificationPriority.CRITICAL,
        }:
            normalized_priority = NotificationPriority.MEDIUM

        event_key = dedup_key or f"{event_type}:{scope}"

        if actor and NotificationService._has_recent_notification(
            db,
            actor,
            scope,
            event_key,
            cooldown_hours=cooldown_hours,
        ):
            return None

        row = NotificationService._create_notification_log(
            db=db,
            actor=actor,
            recipient_scope=scope,
            event_type=event_type,
            priority=normalized_priority,
            title=title,
            message=message,
            event_key=event_key,
            metadata=metadata,
        )

        if email_to and email_subject and email_html:
            NotificationService._executor.submit(
                NotificationService._deliver_batch,
                [(row.audit_id, email_to, email_subject, email_html)],
            )

        return row.audit_id

    @staticmethod
    def _scope_filters(current_user: Employee) -> list[str]:
        scopes = [current_user.employee_id]
        if current_user.organization_id:
            scopes.append(f"ORG:{current_user.organization_id}")
        if current_user.branch_id:
            scopes.append(f"BRANCH:{current_user.branch_id}")
        return scopes

    @staticmethod
    def list_notifications(
        db: Session,
        current_user: Employee,
        unread_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        page = max(1, page)
        per_page = max(1, per_page)

        scopes = NotificationService._scope_filters(current_user)
        q = (
            apply_tenant_filter(db.query(AuditLog), current_user, AuditLog)
            .filter(
                AuditLog.table_name == "notifications",
                AuditLog.record_id.in_(scopes),
            )
            .order_by(AuditLog.changed_at.desc())
        )

        rows = q.offset((page - 1) * per_page).limit(per_page).all()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.new_values or {})
            if unread_only and bool(payload.get("read", False)):
                continue
            items.append(
                {
                    "notification_id": row.audit_id,
                    "scope": row.record_id,
                    "event_type": payload.get("event_type"),
                    "priority": payload.get("priority", NotificationPriority.MEDIUM),
                    "title": payload.get("title", "Notification"),
                    "message": payload.get("message", ""),
                    "status": payload.get("status", "PENDING"),
                    "retry_count": int(payload.get("retry_count") or 0),
                    "last_attempt": payload.get("last_attempt"),
                    "read": bool(payload.get("read", False)),
                    "changed_at": row.changed_at,
                }
            )

        if unread_only:
            total = len(items)
        else:
            total = q.count()

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    @staticmethod
    def mark_read(
        db: Session,
        current_user: Employee,
        notification_ids: Iterable[str],
    ) -> dict[str, Any]:
        scopes = NotificationService._scope_filters(current_user)
        ids = [str(v).strip() for v in notification_ids if str(v).strip()]
        if not ids:
            return {"updated": 0}

        rows = (
            apply_tenant_filter(db.query(AuditLog), current_user, AuditLog)
            .filter(
                AuditLog.table_name == "notifications",
                AuditLog.audit_id.in_(ids),
                AuditLog.record_id.in_(scopes),
            )
            .all()
        )

        updated = 0
        for row in rows:
            payload = dict(row.new_values or {})
            if bool(payload.get("read", False)):
                continue
            payload["read"] = True
            row.new_values = payload
            row.action = "UPDATE"
            row.reason = "NOTIFICATION_READ"
            updated += 1

        return {"updated": updated}
