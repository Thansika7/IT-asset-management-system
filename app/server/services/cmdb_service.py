"""CMDB configuration items and relationships."""

from collections import deque
from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.asset import Asset
from app.server.schema.cmdb import CIRelationship, ConfigurationItem
from app.server.schema.employee import Employee, EmployeeRole
from app.server.database.tenant import apply_tenant_filter


class CMDBService:
    VALID_CI_TYPES = {"ASSET", "SOFTWARE", "SERVICE", "USER", "NETWORK_DEVICE", "FURNITURE", "CLOUD", "DATABASE", "SERVER", "OTHER"}
    VALID_REL_TYPES = {"DEPENDS_ON", "CONNECTED_TO", "HOSTED_ON", "PART_OF", "BACKUP_OF"}
    LEGACY_REL_TYPES = {"ASSIGNED_TO", "SUPPORTS"}

    @staticmethod
    def _normalize_ci_type(ci_type: str) -> str:
        token = (ci_type or "").strip().upper().replace(" ", "_").replace("-", "_")
        return token or "OTHER"

    @staticmethod
    def _normalize_relationship_type(relationship_type: str) -> str:
        token = (relationship_type or "").strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "DEPENDS_ON": "DEPENDS_ON",
            "CONNECTED_TO": "CONNECTED_TO",
            "HOSTED_ON": "HOSTED_ON",
            "PART_OF": "PART_OF",
            "BACKUP_OF": "BACKUP_OF",
            "ASSIGNED_TO": "ASSIGNED_TO",
            "SUPPORTS": "SUPPORTS",
        }
        normalized = aliases.get(token, token)
        if not normalized:
            raise ValueError("relationship_type is required")
        return normalized

    @staticmethod
    def _serialize_ci(row: ConfigurationItem) -> dict[str, Any]:
        return {
            "ci_id": row.ci_id,
            "ci_type": row.ci_type,
            "name": row.name,
            "asset_id": row.asset_id,
            "status": row.status,
            "organization_id": row.organization_id,
            "branch_id": row.branch_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _serialize_relationship(row: CIRelationship) -> dict[str, Any]:
        return {
            "relationship_id": row.relationship_id,
            "source_ci": row.source_ci,
            "target_ci": row.target_ci,
            "relationship_type": CMDBService._normalize_relationship_type(row.relationship_type),
        }

    @staticmethod
    def list_items(
        db: Session, 
        current_user: Employee, 
        search: Optional[str] = None,
        ci_type: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> dict:
        from sqlalchemy import or_
        
        if current_user.role not in (EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
            
        q = apply_tenant_filter(db.query(ConfigurationItem), current_user, ConfigurationItem)
        
        if ci_type:
            q = q.filter(func.upper(ConfigurationItem.ci_type) == CMDBService._normalize_ci_type(ci_type))
            
        if search:
            needle = f"%{search.strip()}%"
            q = q.filter(or_(
                ConfigurationItem.name.ilike(needle),
                ConfigurationItem.ci_id.ilike(needle),
                ConfigurationItem.asset_id.ilike(needle)
            ))
            
        total = q.count()
        rows = q.order_by(ConfigurationItem.name.asc()).offset((page - 1) * per_page).limit(per_page).all()
        items = [CMDBService._serialize_ci(r) for r in rows]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page
        }


    @staticmethod
    def get_item(db: Session, ci_id: str, current_user: Employee) -> ConfigurationItem:
        if current_user.role not in (EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        row = apply_tenant_filter(db.query(ConfigurationItem), current_user, ConfigurationItem).filter(ConfigurationItem.ci_id == ci_id).first()
        if not row:
            raise ResourceNotFoundError("ConfigurationItem", ci_id)
        return row

    @staticmethod
    def create_item(
        db: Session,
        current_user: Employee,
        *,
        ci_type: str,
        name: str,
        asset_id: Optional[str] = None,
        ci_status: str = "ACTIVE",
    ) -> ConfigurationItem:
        if current_user.role not in (EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

        t = CMDBService._normalize_ci_type(ci_type)
        resolved_org_id = current_user.organization_id
        resolved_branch_id = current_user.branch_id

        if asset_id:
            asset = (
                apply_tenant_filter(db.query(Asset), current_user, Asset)
                .filter(Asset.asset_id == asset_id)
                .first()
            )
            if not asset:
                raise ResourceNotFoundError("Asset", asset_id)
            resolved_org_id = asset.organization_id
            resolved_branch_id = asset.branch_id

        row = ConfigurationItem(
            ci_type=t, 
            name=name.strip(), 
            asset_id=asset_id, 
            status=ci_status.strip().upper(),
            organization_id=resolved_org_id,
            branch_id=resolved_branch_id,
        )
        db.add(row)
        db.flush()

        from app.server.services.audit_service import AuditService

        AuditService.log_change(
            db,
            table_name="configuration_items",
            record_id=row.ci_id,
            action="INSERT",
            user=current_user,
            old_values=None,
            new_values={
                "ci_type": row.ci_type,
                "name": row.name,
                "asset_id": row.asset_id,
                "status": row.status,
                "organization_id": row.organization_id,
                "branch_id": row.branch_id,
            },
            reason="CMDB_CI_CREATE",
        )

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list_relationships(
        db: Session,
        current_user: Employee,
        ci_id: Optional[str] = None,
        search: Optional[str] = None,
        relationship_type: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        from sqlalchemy import or_

        if current_user.role not in (EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        q = apply_tenant_filter(db.query(CIRelationship), current_user, CIRelationship)
        if ci_id:
            q = q.filter((CIRelationship.source_ci == ci_id) | (CIRelationship.target_ci == ci_id))
        if relationship_type:
            q = q.filter(
                func.upper(CIRelationship.relationship_type)
                == CMDBService._normalize_relationship_type(relationship_type)
            )
        if search:
            needle = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    CIRelationship.source_ci.ilike(needle),
                    CIRelationship.target_ci.ilike(needle),
                    CIRelationship.relationship_type.ilike(needle),
                    CIRelationship.relationship_id.ilike(needle),
                )
            )

        total = q.count()
        rows = q.order_by(CIRelationship.relationship_id.asc()).offset((page - 1) * per_page).limit(per_page).all()
        items = [CMDBService._serialize_relationship(r) for r in rows]
        return {"items": items, "total": total, "page": page, "per_page": per_page}

    @staticmethod
    def create_relationship(
        db: Session,
        current_user: Employee,
        *,
        source_ci: str,
        target_ci: str,
        relationship_type: str,
    ) -> CIRelationship:
        if current_user.role not in (EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

        if source_ci == target_ci:
            raise ValueError("source_ci and target_ci cannot be the same")

        source = (
            apply_tenant_filter(db.query(ConfigurationItem), current_user, ConfigurationItem)
            .filter(ConfigurationItem.ci_id == source_ci)
            .first()
        )
        target = (
            apply_tenant_filter(db.query(ConfigurationItem), current_user, ConfigurationItem)
            .filter(ConfigurationItem.ci_id == target_ci)
            .first()
        )
        if not source:
            raise ResourceNotFoundError("ConfigurationItem", source_ci)
        if not target:
            raise ResourceNotFoundError("ConfigurationItem", target_ci)

        if source.organization_id and target.organization_id and source.organization_id != target.organization_id:
            raise ValueError("Cross-organization CI relationships are not allowed")
        if source.branch_id and target.branch_id and source.branch_id != target.branch_id:
            raise ValueError("Cross-branch CI relationships are not allowed")

        rt = CMDBService._normalize_relationship_type(relationship_type)

        existing = (
            apply_tenant_filter(db.query(CIRelationship), current_user, CIRelationship)
            .filter(
                CIRelationship.source_ci == source_ci,
                CIRelationship.target_ci == target_ci,
                func.upper(CIRelationship.relationship_type) == rt,
            )
            .first()
        )
        if existing:
            return existing

        row = CIRelationship(
            source_ci=source_ci, 
            target_ci=target_ci, 
            relationship_type=rt,
            organization_id=source.organization_id or current_user.organization_id,
            branch_id=source.branch_id or target.branch_id or current_user.branch_id,
        )
        db.add(row)
        db.flush()

        from app.server.services.audit_service import AuditService

        AuditService.log_change(
            db,
            table_name="ci_relationships",
            record_id=row.relationship_id,
            action="INSERT",
            user=current_user,
            old_values=None,
            new_values={
                "source_ci": row.source_ci,
                "target_ci": row.target_ci,
                "relationship_type": row.relationship_type,
                "organization_id": row.organization_id,
                "branch_id": row.branch_id,
            },
            reason="CMDB_RELATIONSHIP_CREATE",
        )

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get_item_payload(db: Session, ci_id: str, current_user: Employee) -> dict[str, Any]:
        row = CMDBService.get_item(db, ci_id, current_user)
        return CMDBService._serialize_ci(row)

    @staticmethod
    def get_relationship_types(db: Session, current_user: Employee) -> list[str]:
        discovered = {
            r[0]
            for r in apply_tenant_filter(
                db.query(CIRelationship.relationship_type),
                current_user,
                CIRelationship,
            )
            .distinct()
            .all()
            if r[0]
        }
        normalized_discovered = {CMDBService._normalize_relationship_type(v) for v in discovered}
        return sorted(normalized_discovered | CMDBService.VALID_REL_TYPES | CMDBService.LEGACY_REL_TYPES)

    @staticmethod
    def get_impact(db: Session, ci_id: str, current_user: Employee) -> dict[str, Any]:
        CMDBService.get_item(db, ci_id, current_user)

        relationships = apply_tenant_filter(db.query(CIRelationship), current_user, CIRelationship).all()

        reverse_adj: dict[str, set[str]] = {}
        for rel in relationships:
            rel_type = CMDBService._normalize_relationship_type(rel.relationship_type)
            source = rel.source_ci
            target = rel.target_ci
            reverse_adj.setdefault(source, set())
            reverse_adj.setdefault(target, set())

            if rel_type == "CONNECTED_TO":
                reverse_adj[source].add(target)
                reverse_adj[target].add(source)
            else:
                reverse_adj[target].add(source)

        visited = {ci_id}
        q = deque([ci_id])
        impacted: set[str] = set()

        while q:
            node = q.popleft()
            for dep in reverse_adj.get(node, set()):
                if dep in visited:
                    continue
                visited.add(dep)
                impacted.add(dep)
                q.append(dep)

        if not impacted:
            return {
                "ci_id": ci_id,
                "dependent_assets": [],
                "dependent_services": [],
                "impacted_ci_count": 0,
            }

        impacted_rows = (
            apply_tenant_filter(db.query(ConfigurationItem), current_user, ConfigurationItem)
            .filter(ConfigurationItem.ci_id.in_(impacted))
            .all()
        )

        dependent_assets = [
            {
                "ci_id": row.ci_id,
                "name": row.name,
                "asset_id": row.asset_id,
                "status": row.status,
                "ci_type": row.ci_type,
            }
            for row in impacted_rows
            if row.asset_id or CMDBService._normalize_ci_type(row.ci_type) == "ASSET"
        ]
        dependent_services = [
            {
                "ci_id": row.ci_id,
                "name": row.name,
                "asset_id": row.asset_id,
                "status": row.status,
                "ci_type": row.ci_type,
            }
            for row in impacted_rows
            if CMDBService._normalize_ci_type(row.ci_type) == "SERVICE"
        ]

        return {
            "ci_id": ci_id,
            "dependent_assets": dependent_assets,
            "dependent_services": dependent_services,
            "impacted_ci_count": len(impacted_rows),
        }

    @staticmethod
    def mark_asset_cis_retired(
        db: Session,
        current_user: Employee,
        asset_id: str,
        reason: str = "ASSET_RETIRED",
    ) -> int:
        rows = (
            apply_tenant_filter(db.query(ConfigurationItem), current_user, ConfigurationItem)
            .filter(ConfigurationItem.asset_id == asset_id)
            .all()
        )
        if not rows:
            return 0

        from app.server.services.audit_service import AuditService

        updated = 0
        for row in rows:
            old_status = row.status
            if old_status == "RETIRED":
                continue
            row.status = "RETIRED"
            updated += 1

            AuditService.log_change(
                db,
                table_name="configuration_items",
                record_id=row.ci_id,
                action="UPDATE",
                user=current_user,
                old_values={"status": old_status},
                new_values={"status": row.status},
                reason=reason,
            )

        return updated
