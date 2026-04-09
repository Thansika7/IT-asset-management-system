from __future__ import annotations

from threading import Lock
from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.server.database.tenant import apply_tenant_filter
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.category import AssetBehavior
from app.server.schema.employee import Employee
from app.server.schema.tracking import AssetLifecycle, LifecycleEvent
from app.server.schema.audit import AuditLog
from app.server.exceptions.base import ResourceNotFoundError
from app.server.services.audit_service import AuditService
from app.server.services.email_service import EmailService
from app.server.services.notification_service import NotificationPriority, NotificationService


class HealthService:
    """Unified health scoring using asset instances and lifecycle data."""

    DOWNTIME_THRESHOLD_DAYS = 30
    ALERT_THRESHOLD = 30
    CACHE_TTL_SECONDS = 120
    _cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
    _cache_lock = Lock()

    @staticmethod
    def _cache_key(current_user: Employee, instance_id: str) -> str:
        return f"{current_user.organization_id}:{instance_id}"

    @staticmethod
    def _cache_get(key: str) -> Optional[dict[str, Any]]:
        with HealthService._cache_lock:
            row = HealthService._cache.get(key)
            if not row:
                return None
            ts, payload = row
            if (datetime.now(timezone.utc) - ts).total_seconds() > HealthService.CACHE_TTL_SECONDS:
                HealthService._cache.pop(key, None)
                return None
            return dict(payload)

    @staticmethod
    def _cache_set(key: str, payload: dict[str, Any]) -> None:
        with HealthService._cache_lock:
            HealthService._cache[key] = (datetime.now(timezone.utc), dict(payload))

    @staticmethod
    def _resolve_behavior(instance: AssetInstance) -> str:
        model = instance.model
        if not model:
            return AssetBehavior.INSTANCE_BASED.value
        if model.asset_behavior:
            return str(model.asset_behavior)
        if model.category and model.category.asset_behavior:
            return str(model.category.asset_behavior)
        return AssetBehavior.INSTANCE_BASED.value

    @staticmethod
    def _is_applicable_behavior(behavior: str) -> bool:
        return behavior == AssetBehavior.INSTANCE_BASED.value

    @staticmethod
    def _classify(score: int) -> str:
        if score >= 90:
            return "EXCELLENT"
        if score >= 70:
            return "GOOD"
        if score >= 50:
            return "WARNING"
        if score >= 30:
            return "CRITICAL"
        return "REPLACE"

    @staticmethod
    def _age_years(instance: AssetInstance) -> float:
        purchase_date = instance.purchase_date or (instance.model.purchased_date if instance.model else None)
        if not purchase_date:
            return 0.0
        return max((date.today() - purchase_date).days / 365.0, 0.0)

    @staticmethod
    def _load_instance_lifecycle(db: Session, instance_id: str) -> list[AssetLifecycle]:
        return (
            db.query(AssetLifecycle)
            .filter(AssetLifecycle.instance_id == instance_id)
            .order_by(AssetLifecycle.timestamp.asc())
            .all()
        )

    @staticmethod
    def _load_lifecycle_for_instances(db: Session, instance_ids: list[str]) -> dict[str, list[AssetLifecycle]]:
        if not instance_ids:
            return {}
        rows = (
            db.query(AssetLifecycle)
            .filter(AssetLifecycle.instance_id.in_(instance_ids))
            .order_by(AssetLifecycle.instance_id.asc(), AssetLifecycle.timestamp.asc())
            .all()
        )
        grouped: dict[str, list[AssetLifecycle]] = {}
        for row in rows:
            grouped.setdefault(row.instance_id, []).append(row)
        return grouped

    @staticmethod
    def _repair_count(events: list[AssetLifecycle]) -> int:
        return sum(1 for e in events if e.event_type == LifecycleEvent.REPAIR_STARTED)

    @staticmethod
    def _downtime_days(events: list[AssetLifecycle], current_status: AssetStatus) -> float:
        total_days = 0.0
        start_ts: Optional[datetime] = None
        now = datetime.now(timezone.utc)

        for ev in events:
            if ev.event_type == LifecycleEvent.REPAIR_STARTED:
                start_ts = ev.timestamp
            elif ev.event_type == LifecycleEvent.REPAIR_COMPLETED and start_ts:
                total_days += max((ev.timestamp - start_ts).total_seconds(), 0) / 86400.0
                start_ts = None

        if start_ts and current_status == AssetStatus.IN_REPAIR:
            total_days += max((now - start_ts).total_seconds(), 0) / 86400.0

        return round(total_days, 2)

    @staticmethod
    def _status_penalty(status: AssetStatus) -> int:
        if status == AssetStatus.IN_REPAIR:
            return 20
        if status in (AssetStatus.NOT_USABLE, AssetStatus.DAMAGED, AssetStatus.LOST):
            return 60
        return 0

    @staticmethod
    def _build_instance_health(instance: AssetInstance, events: list[AssetLifecycle]) -> dict[str, Any]:
        behavior = HealthService._resolve_behavior(instance)
        applicable = HealthService._is_applicable_behavior(behavior)

        if not applicable:
            return {
                "instance_id": instance.instance_id,
                "asset_id": instance.asset_id,
                "asset_name": instance.model.name if instance.model else instance.asset_id,
                "asset_behavior": behavior,
                "applicable": False,
                "reason": "Health score applies only to instance_based categories",
                "score": None,
                "status": "SKIPPED",
                "recommendation": "N/A",
                "factors": {},
            }

        score = 100
        age_years = HealthService._age_years(instance)
        repair_count = HealthService._repair_count(events)
        downtime_days = HealthService._downtime_days(events, instance.status)
        warranty_expired = bool(instance.warranty_expiry and instance.warranty_expiry < date.today())

        # Prompt-prescribed penalties
        penalties: dict[str, int] = {
            "warranty_expired": 10 if warranty_expired else 0,
            "repair_count": repair_count * 8,
            "status": HealthService._status_penalty(instance.status),
            "age": 15 if age_years > 3 else 0,
            "downtime": 10 if downtime_days > HealthService.DOWNTIME_THRESHOLD_DAYS else 0,
        }

        for value in penalties.values():
            score -= value
        score = max(0, min(100, score))

        # Additional analytics using lifecycle data
        years = max(age_years, 1.0)
        repair_frequency_per_year = round(repair_count / years, 2)
        failure_events = sum(1 for e in events if e.event_type in (LifecycleEvent.DAMAGED, LifecycleEvent.REPLACED))
        failure_rate_per_year = round((repair_count + failure_events) / years, 2)

        status = HealthService._classify(score)
        recommendation = "REPLACE" if score < 30 else "MONITOR"

        return {
            "instance_id": instance.instance_id,
            "asset_id": instance.asset_id,
            "asset_name": instance.model.name if instance.model else instance.asset_id,
            "asset_behavior": behavior,
            "applicable": True,
            "score": score,
            "status": status,
            "recommendation": recommendation,
            "factors": {
                "repair_count": repair_count,
                "repair_frequency_per_year": repair_frequency_per_year,
                "asset_age_years": round(age_years, 2),
                "warranty_expired": warranty_expired,
                "downtime_days": downtime_days,
                "instance_status": instance.status.value if hasattr(instance.status, "value") else str(instance.status),
                "failure_rate_per_year": failure_rate_per_year,
            },
            "penalties": penalties,
        }

    @staticmethod
    def _maybe_emit_health_alert(db: Session, current_user: Employee, health: dict[str, Any], instance: AssetInstance) -> None:
        if not health.get("applicable"):
            return
        score = health.get("score")
        if score is None or score >= HealthService.ALERT_THRESHOLD:
            return

        recently_alerted = (
            db.query(AuditLog)
            .filter(
                AuditLog.table_name == "asset_instances",
                AuditLog.record_id == instance.instance_id,
                AuditLog.action == "UPDATE",
                AuditLog.reason == "HEALTH_ALERT_LOW_SCORE",
                AuditLog.changed_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            )
            .first()
        )
        if recently_alerted:
            return

        recipients = EmailService.collect_hr_admin_emails(db, instance.branch)
        if recipients:
            EmailService.notify_health_alert(
                recipients=recipients,
                asset_name=instance.model.name if instance.model else instance.asset_id,
                instance_id=instance.instance_id,
                score=int(score),
                classification=str(health.get("status")),
                recommendation=str(health.get("recommendation")),
                branch=instance.branch or "-",
            )
            NotificationService.emit(
                db,
                actor=current_user,
                recipient_scope=f"BRANCH:{instance.branch_id or '-'}",
                event_type="HEALTH_CRITICAL_ALERT",
                title="Critical Health Alert",
                message=f"Instance {instance.instance_id} health score dropped to {int(score)}.",
                priority=NotificationPriority.CRITICAL,
                dedup_key=f"health_alert:{instance.instance_id}",
                cooldown_hours=24,
                metadata={
                    "instance_id": instance.instance_id,
                    "asset_id": instance.asset_id,
                    "score": int(score),
                    "classification": str(health.get("status")),
                },
            )

        AuditService.log_change(
            db=db,
            table_name="asset_instances",
            record_id=instance.instance_id,
            action="UPDATE",
            user=current_user,
            old_values={"health_score": None},
            new_values={
                "health_score": score,
                "health_status": health.get("status"),
                "recommendation": health.get("recommendation"),
            },
            reason="HEALTH_ALERT_LOW_SCORE",
        )
        db.flush()

    @staticmethod
    def get_instance_health(db: Session, current_user: Employee, instance_id: str, emit_alerts: bool = True) -> dict[str, Any]:
        cache_key = HealthService._cache_key(current_user, instance_id)
        cached = HealthService._cache_get(cache_key)
        if cached and not emit_alerts:
            return cached

        instance = (
            apply_tenant_filter(
                db.query(AssetInstance)
                .options(
                    joinedload(AssetInstance.model).joinedload(Asset.category),
                    joinedload(AssetInstance.branch_rel),
                ),
                current_user,
                AssetInstance,
            )
            .filter(AssetInstance.instance_id == instance_id)
            .first()
        )
        if not instance:
            raise ResourceNotFoundError("AssetInstance", instance_id)

        events = HealthService._load_instance_lifecycle(db, instance_id)
        health = HealthService._build_instance_health(instance, events)
        HealthService._cache_set(cache_key, health)
        if emit_alerts:
            HealthService._maybe_emit_health_alert(db, current_user, health, instance)

        return health

    @staticmethod
    def get_asset_health(db: Session, current_user: Employee, asset_id: str, emit_alerts: bool = True) -> dict[str, Any]:
        asset = (
            apply_tenant_filter(
                db.query(Asset).options(joinedload(Asset.category)),
                current_user,
                Asset,
            )
            .filter(Asset.asset_id == asset_id)
            .first()
        )
        if not asset:
            raise ResourceNotFoundError("Asset", asset_id)

        instances = (
            apply_tenant_filter(
                db.query(AssetInstance)
                .options(
                    joinedload(AssetInstance.model).joinedload(Asset.category),
                    joinedload(AssetInstance.branch_rel),
                ),
                current_user,
                AssetInstance,
            )
            .filter(AssetInstance.asset_id == asset_id)
            .all()
        )

        events_by_instance = HealthService._load_lifecycle_for_instances(db, [i.instance_id for i in instances])

        instance_health: list[dict[str, Any]] = []
        applicable_scores: list[int] = []
        for inst in instances:
            events = events_by_instance.get(inst.instance_id, [])
            row = HealthService._build_instance_health(inst, events)
            instance_health.append(row)
            if row.get("applicable") and row.get("score") is not None:
                applicable_scores.append(int(row["score"]))
                if emit_alerts:
                    HealthService._maybe_emit_health_alert(db, current_user, row, inst)

        avg_score = round(sum(applicable_scores) / len(applicable_scores), 2) if applicable_scores else None
        avg_status = HealthService._classify(int(round(avg_score))) if avg_score is not None else "SKIPPED"

        return {
            "asset_id": asset.asset_id,
            "asset_name": asset.name,
            "asset_behavior": asset.asset_behavior or (asset.category.asset_behavior if asset.category else None),
            "score": avg_score,
            "status": avg_status,
            "recommendation": "REPLACE" if (avg_score is not None and avg_score < 30) else "MONITOR",
            "instances_total": len(instances),
            "instances_applicable": len(applicable_scores),
            "instances": instance_health,
        }

    @staticmethod
    def get_health_summary(db: Session, current_user: Employee, branch_id: Optional[str] = None) -> dict[str, Any]:
        query = apply_tenant_filter(
            db.query(AssetInstance).options(joinedload(AssetInstance.model).joinedload(Asset.category)),
            current_user,
            AssetInstance,
        )
        if branch_id:
            query = query.filter(AssetInstance.branch_id == branch_id)
        instances = query.all()

        events_by_instance = HealthService._load_lifecycle_for_instances(db, [i.instance_id for i in instances])

        counts = {
            "EXCELLENT": 0,
            "GOOD": 0,
            "WARNING": 0,
            "CRITICAL": 0,
            "REPLACE": 0,
            "SKIPPED": 0,
        }
        applicable_scores: list[int] = []
        replacement_candidates: list[dict[str, Any]] = []

        for inst in instances:
            events = events_by_instance.get(inst.instance_id, [])
            h = HealthService._build_instance_health(inst, events)
            status = str(h.get("status", "SKIPPED"))
            counts[status] = counts.get(status, 0) + 1
            score = h.get("score")
            if isinstance(score, int):
                applicable_scores.append(score)
                if score < 30:
                    replacement_candidates.append(
                        {
                            "instance_id": inst.instance_id,
                            "asset_id": inst.asset_id,
                            "asset_name": inst.model.name if inst.model else inst.asset_id,
                            "score": score,
                            "status": status,
                        }
                    )

        avg_score = round(sum(applicable_scores) / len(applicable_scores), 2) if applicable_scores else None

        replacement_candidates = sorted(replacement_candidates, key=lambda x: x["score"])[:20]

        return {
            "total_instances": len(instances),
            "applicable_instances": len(applicable_scores),
            "average_score": avg_score,
            "distribution": counts,
            "replacement_candidates": replacement_candidates,
        }
